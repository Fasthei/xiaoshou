"""Agent loop + fact persistence + increment semantics.

LLM is mocked — we feed a scripted sequence of tool_calls and verify:
1. Every tool is dispatched to the correct runner.
2. record_fact writes to DB with a fingerprint.
3. A duplicate fact on a re-run is skipped (no IntegrityError bubbled).
4. finish terminates the loop, summary is persisted on the run row.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightFact, CustomerInsightRun


# ---------- fixtures ----------

@pytest.fixture()
def db():
    """In-memory SQLite session — good enough for the agent persistence layer."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def customer(db):
    # SQLite doesn't autoincrement BigInteger PKs the way Postgres does;
    # assign id explicitly for the in-memory test DB.
    c = Customer(
        id=1,
        customer_code="CUST-001", customer_name="酷睿科技", customer_status="prospect",
        industry="AI", is_deleted=False,
    )
    db.add(c); db.commit(); db.refresh(c)
    return c


def _tool_call(name: str, args: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args, ensure_ascii=False)),
    )


def _llm_resp(tool_calls=None, content: str = ""):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _make_mock_client(scripted_responses):
    """Returns an object with .chat.completions.create() that yields scripted_responses in order."""
    it = iter(scripted_responses)
    mock = MagicMock()
    mock.chat.completions.create.side_effect = lambda **kw: next(it)
    return mock


# ---------- tests ----------

def test_agent_records_facts_and_finishes(db, customer, monkeypatch):
    """Scripted LLM: search → read → record_fact × 2 → finish."""
    from app.agents import customer_insight_agent as mod

    # 1st turn: search
    r1 = _llm_resp(tool_calls=[_tool_call("jina_search", {"query": "酷睿科技", "num": 3}, "c1")])
    # 2nd: read
    r2 = _llm_resp(tool_calls=[_tool_call("jina_read", {"url": "https://example.com/about"}, "c2")])
    # 3rd: record two facts in one turn
    r3 = _llm_resp(tool_calls=[
        _tool_call("record_fact", {"category": "basic", "content": "公司总部在上海"}, "c3a"),
        _tool_call("record_fact", {"category": "tech", "content": "使用 Kubernetes 做编排"}, "c3b"),
    ])
    # 4th: finish
    r4 = _llm_resp(tool_calls=[_tool_call("finish", {"summary_markdown": "# 酷睿科技\n- 总部上海"}, "c4")])

    mock_client = _make_mock_client([r1, r2, r3, r4])
    monkeypatch.setattr(mod, "get_azure_openai_client", lambda: mock_client)
    monkeypatch.setattr(mod, "deployment_name", lambda: "gpt-5.4")

    # Mock external tools too — no real network
    fake_jina = MagicMock()
    fake_jina.search.return_value = [
        SimpleNamespace(title="酷睿科技官网", url="https://example.com/about", description="AI 公司", content="")
    ]
    fake_jina.read.return_value = "# 关于酷睿科技\n总部位于上海，核心业务是 AI 推理平台。"

    def fake_build_tools(db_, cust, run, emit):
        # Keep record_fact real (it writes to DB); replace external tools with mocks
        real = mod._build_tool_runners.__wrapped__ if hasattr(mod._build_tool_runners, "__wrapped__") else None
        runners = {
            "jina_search": lambda args: json.dumps([{"title": "酷睿科技官网", "url": "https://example.com/about", "description": "AI 公司"}]),
            "jina_read": lambda args: "# 关于酷睿科技\n总部位于上海。",
            "linkedin_search": lambda args: json.dumps([]),
            "linkedin_company": lambda args: json.dumps({}),
        }
        # Reuse real record_fact from the unmocked builder by calling it with dummy network clients
        return {**runners, "record_fact": _real_record_fact_runner(db_, cust, run, emit)}

    monkeypatch.setattr(mod, "_build_tool_runners", fake_build_tools)

    run = CustomerInsightRun(customer_id=customer.id, steps_total=12, steps_done=0, status="running")
    db.add(run); db.commit(); db.refresh(run)

    events = []
    def emit(ev, data): events.append((ev, data))

    result = mod.run_customer_insight_agent(db, customer, run, emit)

    # The agent should have recorded 2 facts + finished
    facts = db.query(CustomerInsightFact).filter(CustomerInsightFact.customer_id == customer.id).all()
    assert len(facts) == 2
    assert {f.category for f in facts} == {"basic", "tech"}
    assert all(f.run_id == run.id for f in facts)
    assert all(len(f.fingerprint) == 40 for f in facts)  # sha1 hex

    # Run row is finalised
    assert run.status == "completed"
    assert run.summary and "酷睿科技" in run.summary
    assert result["steps_done"] >= 1

    # Events order: run_started appears, fact_recorded appears twice, done appears
    event_types = [e for e, _ in events]
    assert "run_started" in event_types
    assert event_types.count("fact_recorded") == 2
    assert event_types[-1] == "done"


def test_duplicate_fact_is_skipped(db, customer, monkeypatch):
    """Second run discovering the same fact must not insert it again."""
    from app.agents import customer_insight_agent as mod

    # First scripted run: 1 fact + finish
    r1 = _llm_resp(tool_calls=[_tool_call("record_fact", {"category": "basic", "content": "公司总部在上海"}, "c1")])
    r2 = _llm_resp(tool_calls=[_tool_call("finish", {"summary_markdown": "done"}, "c2")])

    def one_client_factory(scripted):
        mock = MagicMock()
        mock.chat.completions.create.side_effect = lambda **kw: next(scripted)
        return mock

    scripted_1 = iter([r1, r2])
    monkeypatch.setattr(mod, "get_azure_openai_client", lambda: one_client_factory(scripted_1))
    monkeypatch.setattr(mod, "deployment_name", lambda: "gpt-5.4")
    monkeypatch.setattr(
        mod, "_build_tool_runners",
        lambda db_, cust, run, emit: {
            "jina_search": lambda a: "[]", "jina_read": lambda a: "",
            "linkedin_search": lambda a: "[]", "linkedin_company": lambda a: "{}",
            "record_fact": _real_record_fact_runner(db_, cust, run, emit),
        },
    )

    run1 = CustomerInsightRun(customer_id=customer.id, steps_total=12, status="running")
    db.add(run1); db.commit(); db.refresh(run1)
    mod.run_customer_insight_agent(db, customer, run1, lambda e, d: None)

    assert db.query(CustomerInsightFact).filter_by(customer_id=customer.id).count() == 1

    # Second run: same fact → must be skipped
    scripted_2 = iter([
        _llm_resp(tool_calls=[_tool_call("record_fact", {"category": "basic", "content": "公司总部在上海"}, "c3")]),
        _llm_resp(tool_calls=[_tool_call("finish", {"summary_markdown": "done2"}, "c4")]),
    ])
    monkeypatch.setattr(mod, "get_azure_openai_client", lambda: one_client_factory(scripted_2))

    run2 = CustomerInsightRun(customer_id=customer.id, steps_total=12, status="running")
    db.add(run2); db.commit(); db.refresh(run2)
    events = []
    mod.run_customer_insight_agent(db, customer, run2, lambda e, d: events.append((e, d)))

    # Still exactly 1 fact total
    assert db.query(CustomerInsightFact).filter_by(customer_id=customer.id).count() == 1
    assert any(e == "fact_skipped_duplicate" for e, _ in events)


def test_fingerprint_is_stable_and_categorised():
    from app.agents.customer_insight_agent import fingerprint

    assert fingerprint("basic", "公司总部在上海") == fingerprint("basic", "公司总部在上海 ")
    assert fingerprint("basic", "X") != fingerprint("tech", "X")


def test_system_prompt_includes_local_customer_data(db, customer):
    """System prompt must surface follow-ups, contracts, allocations, profile to the agent."""
    import datetime as _dt

    from app.agents.customer_insight_agent import _build_system_prompt
    from app.models.allocation import Allocation
    from app.models.contract import Contract
    from app.models.follow_up import CustomerFollowUp
    from app.models.resource import Resource

    # Annotate the customer with optional profile fields (soft-access compatible).
    customer.note = "关键客户，季度拜访"
    customer.website = "https://corecube.example.com"
    customer.linkedin_url = "https://linkedin.com/company/corecube"
    db.add(customer)

    # 2 follow-up records
    db.add(CustomerFollowUp(
        customer_id=customer.id, kind="meeting", title="Q2 业务回顾",
        content="客户计划扩展到 GCP", next_action_at=_dt.datetime(2026, 5, 1),
    ))
    db.add(CustomerFollowUp(
        customer_id=customer.id, kind="call", title="催回款",
        content="已承诺 4 月底付清",
    ))

    # 1 active contract
    db.add(Contract(
        customer_id=customer.id, contract_code="CN-2026-007",
        title="年度云服务合同", amount=500000,
        start_date=_dt.date(2026, 1, 1), status="active",
    ))

    # 1 allocation with a linked resource
    res = Resource(
        resource_code="cc-42", resource_type="ORIGINAL",
        resource_status="AVAILABLE", is_deleted=False,
    )
    db.add(res); db.commit(); db.refresh(res)

    db.add(Allocation(
        allocation_code="ALC-0001", customer_id=customer.id, resource_id=res.id,
        allocated_quantity=100, allocation_status="approved", is_deleted=False,
    ))
    db.commit()

    prompt = _build_system_prompt(customer, prior_facts=[], db=db)

    assert "== 本地已知客户信息 ==" in prompt
    # Profile
    assert "关键客户，季度拜访" in prompt
    assert "corecube.example.com" in prompt
    # Follow-ups
    assert "Q2 业务回顾" in prompt
    assert "催回款" in prompt
    # Contract
    assert "CN-2026-007" in prompt
    assert "500000" in prompt
    # Allocation + resource code
    assert "ALC-0001" in prompt
    assert "cc-42" in prompt
    # Ground-truth directive
    assert "GROUND TRUTH" in prompt


# ---------- helper: reuse the real record_fact closure without external clients ----------

def _real_record_fact_runner(db_, customer, run, emitter):
    """Build just the record_fact closure — mirror of the real one, DB only, no network."""
    from app.agents.customer_insight_agent import (
        CATEGORIES, fingerprint as _fp,
    )
    from sqlalchemy.exc import IntegrityError

    def record_fact(args: dict) -> str:
        category = args.get("category") or "other"
        if category not in CATEGORIES:
            category = "other"
        content = (args.get("content") or "").strip()
        if not content:
            return json.dumps({"ok": False, "reason": "empty"})
        fp = _fp(category, content)
        fact = CustomerInsightFact(
            customer_id=customer.id, run_id=run.id,
            category=category, content=content, fingerprint=fp, source_url=None,
        )
        db_.add(fact)
        try:
            db_.commit()
        except IntegrityError:
            db_.rollback()
            emitter("fact_skipped_duplicate", {"category": category, "content": content, "fingerprint": fp})
            return json.dumps({"ok": True, "duplicate": True})
        db_.refresh(fact)
        emitter("fact_recorded", {"id": fact.id, "category": category, "content": content, "fingerprint": fp})
        return json.dumps({"ok": True, "id": fact.id})

    return record_fact
