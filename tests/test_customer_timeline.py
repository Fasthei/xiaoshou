"""Coverage for GET /api/customers/{id}/timeline.

§3.4: 时间线只展示真实业务动作。
  * gongdan 来源客户 -- created/updated 桩事件被吞掉, 但跟进 / 合同 / 分配
    / AI 洞察 / stage 审批仍照常展示。
  * 直客 -- created 事件展示, 加上后续业务动作。
事件按时间倒序合并。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.allocation import Allocation
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightRun
from app.models.customer_stage_request import CustomerStageRequest
from app.models.follow_up import CustomerFollowUp
from main import app


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()

    def override():
        try:
            yield s
        finally:
            pass

    app.dependency_overrides[get_db] = override
    try:
        yield s
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _mk_customer(db, *, name: str, code: str, source: str | None = None,
                 created_at: datetime | None = None) -> Customer:
    c = Customer(
        customer_name=name, customer_code=code, customer_status="active",
        source_system=source,
    )
    if created_at is not None:
        c.created_at = created_at
        c.updated_at = created_at
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_gongdan_origin_with_followup_returns_only_followup(client, db_session):
    """gongdan 来源客户 + 一条跟进 → 仅返回 1 个 follow_up 事件 (created/updated 被吞)."""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="工单客户A", code="GD-001",
        source="gongdan", created_at=base,
    )
    fu = CustomerFollowUp(
        customer_id=cust.id,
        kind="call",
        title="首次电话",
        content="客户很感兴趣",
        created_at=base + timedelta(days=1),
    )
    db_session.add(fu)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    assert r.status_code == 200, r.text
    events = r.json()
    assert len(events) == 1, events
    ev = events[0]
    assert ev["kind"] == "follow_up"
    assert ev["color"] == "cyan"
    assert "首次电话" in ev["detail"]


def test_gongdan_origin_followup_reply_kind(client, db_session):
    """回复 (parent_follow_up_id 非空) → kind=follow_up_reply。"""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="工单客户B", code="GD-002",
        source="gongdan", created_at=base,
    )
    parent = CustomerFollowUp(
        customer_id=cust.id, kind="note", title="主留言",
        content="留言内容", created_at=base + timedelta(days=1),
    )
    db_session.add(parent)
    db_session.commit()
    db_session.refresh(parent)
    reply = CustomerFollowUp(
        customer_id=cust.id, kind="note", title="回复",
        content="收到", parent_follow_up_id=parent.id,
        created_at=base + timedelta(days=2),
    )
    db_session.add(reply)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    assert r.status_code == 200
    events = r.json()
    kinds = [e["kind"] for e in events]
    assert "follow_up_reply" in kinds
    assert "follow_up" in kinds


def test_direct_customer_contract_allocation_descending(client, db_session):
    """直客 + 合同 + 分配 → created + contract + allocation 至少 3 个事件按时间倒序。"""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="直客A", code="DC-001",
        source="manual", created_at=base,
    )
    ct = Contract(
        customer_id=cust.id, contract_code="C-001", title="年框",
        status="active", created_at=base + timedelta(days=2),
    )
    db_session.add(ct)
    alloc = Allocation(
        allocation_code="A-001", customer_id=cust.id, resource_id=999,
        allocated_quantity=10, allocation_status="active",
        created_at=base + timedelta(days=5),
    )
    db_session.add(alloc)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    assert r.status_code == 200, r.text
    events = r.json()
    kinds = [e["kind"] for e in events]
    assert "created" in kinds
    assert "contract" in kinds
    assert "allocation" in kinds
    # 时间倒序: allocation (day +5) → contract (day +2) → created (day 0)
    timestamps = [e["at"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)


def test_stage_request_pending_color_orange(client, db_session):
    """pending 阶段审批 → color=orange, 只有 stage_request, 没有 stage_decision。"""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="直客B", code="DC-002",
        source="manual", created_at=base,
    )
    sr = CustomerStageRequest(
        customer_id=cust.id, from_stage="lead", to_stage="contacting",
        status="pending", requested_by="alice",
        created_at=base + timedelta(days=1),
    )
    db_session.add(sr)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    assert r.status_code == 200
    events = r.json()
    sr_events = [e for e in events if e["kind"] == "stage_request"]
    assert len(sr_events) == 1
    assert sr_events[0]["color"] == "orange"
    assert not [e for e in events if e["kind"] == "stage_decision"]


def test_stage_request_approved_emits_decision(client, db_session):
    """approved + decided_at → 同时发出 stage_request(green) + stage_decision(green)。"""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="直客C", code="DC-003",
        source="manual", created_at=base,
    )
    sr = CustomerStageRequest(
        customer_id=cust.id, from_stage="lead", to_stage="contacting",
        status="approved", requested_by="alice", decided_by="boss",
        created_at=base + timedelta(days=1),
        decided_at=base + timedelta(days=2),
    )
    db_session.add(sr)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    events = r.json()
    submit = [e for e in events if e["kind"] == "stage_request"]
    decision = [e for e in events if e["kind"] == "stage_decision"]
    assert len(submit) == 1 and submit[0]["color"] == "green"
    assert len(decision) == 1 and decision[0]["color"] == "green"


def test_insight_run_event(client, db_session):
    """AI 洞察 run → kind=insight, color=magenta。"""
    base = datetime(2026, 4, 1, 10, 0, 0)
    cust = _mk_customer(
        db_session, name="直客D", code="DC-004",
        source="manual", created_at=base,
    )
    run = CustomerInsightRun(
        customer_id=cust.id, status="completed",
        started_at=base + timedelta(days=1),
        completed_at=base + timedelta(days=1, seconds=12),
    )
    db_session.add(run)
    db_session.commit()

    r = client.get(f"/api/customers/{cust.id}/timeline")
    events = r.json()
    insight = [e for e in events if e["kind"] == "insight"]
    assert len(insight) == 1
    assert insight[0]["color"] == "magenta"
    assert "completed" in insight[0]["detail"]
