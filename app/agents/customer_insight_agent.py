"""Customer Insight Agent — GPT-5.4 plans & invokes Jina / LinkedIn tools.

Non-goals:
- No truth verification (breadth > depth, per product owner).
- No conversation: it's a single button-click → stream of events → final summary.

Increment semantics:
- Prior fact fingerprints for this customer are injected into the system prompt
  so the model is nudged to find NEW information and not repeat itself.
- Dispatcher also dedups at write-time: if fingerprint already in DB, the call
  is a no-op (emits `fact_skipped_duplicate`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.openai_client import deployment_name, get_azure_openai_client
from app.config import get_settings
from app.integrations.jina import JinaClient
from app.integrations.linkedin import LinkedInClient
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightFact, CustomerInsightRun

logger = logging.getLogger(__name__)

MAX_ITERS = 12
MAX_TOOL_RESULT_CHARS = 6000  # cap what we feed back into the model
CATEGORIES = {"basic", "people", "tech", "news", "event", "other"}

# OpenAI tool definitions — these names are what the model will call.
TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "jina_search",
            "description": "General web search. Use for company news, product info, key people, events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (Chinese or English)."},
                    "num": {"type": "integer", "minimum": 1, "maximum": 15, "default": 8},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jina_read",
            "description": "Fetch a URL and return clean markdown. Use to read a page you found via jina_search.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "linkedin_search",
            "description": "Search LinkedIn for companies by keyword. Returns brief company profiles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1, "maximum": 5, "default": 1},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "linkedin_company",
            "description": "Fetch a LinkedIn company's full profile by its LinkedIn URL.",
            "parameters": {
                "type": "object",
                "properties": {"linkedin_url": {"type": "string"}},
                "required": ["linkedin_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_fact",
            "description": (
                "Persist one discovered atomic fact about the target customer. "
                "Call this for every useful piece of information you find. "
                "Do NOT fabricate — if unsure, don't record."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": sorted(CATEGORIES),
                        "description": "basic=公司基础, people=关键人, tech=技术栈, news=近期新闻, event=事件(融资/发布/变动), other=其他",
                    },
                    "content": {
                        "type": "string",
                        "description": "One self-contained sentence in Chinese.",
                    },
                    "source_url": {"type": "string", "description": "Where you found it (optional)."},
                },
                "required": ["category", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Terminate the investigation and emit a final markdown summary for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary_markdown": {"type": "string", "description": "Markdown digest of the most useful findings."},
                },
                "required": ["summary_markdown"],
            },
        },
    },
]


# ---------- helpers ----------

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def fingerprint(category: str, content: str) -> str:
    return hashlib.sha1(f"{category}::{_normalize(content)}".encode("utf-8")).hexdigest()


def _truncate(s: str, n: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n...[truncated {len(s) - n} chars]"


@dataclass
class _Emitter:
    """Wraps the caller-provided emit callback and also updates the run row."""
    emit: Callable[[str, Dict[str, Any]], None]
    db: Session
    run: CustomerInsightRun

    def __call__(self, event: str, payload: Dict[str, Any]) -> None:
        try:
            self.emit(event, payload)
        except Exception:  # noqa: BLE001 — never let SSE errors break the agent
            logger.exception("emit failed")


# ---------- tool execution ----------

def _build_tool_runners(
    db: Session,
    customer: Customer,
    run: CustomerInsightRun,
    emit: _Emitter,
):
    s = get_settings()
    jina = JinaClient(api_key=s.JINA_API_KEY) if s.JINA_API_KEY else None
    linkedin = LinkedInClient(api_key=s.RAPIDAPI_KEY, host=s.LINKEDIN_API_HOST) if s.RAPIDAPI_KEY else None

    def _require_jina():
        if not jina:
            raise RuntimeError("JINA_API_KEY not configured")
        return jina

    def _require_linkedin():
        if not linkedin:
            raise RuntimeError("RAPIDAPI_KEY not configured")
        return linkedin

    def jina_search(args: dict) -> str:
        results = _require_jina().search(args["query"], num=int(args.get("num", 8)))
        return json.dumps(
            [{"title": r.title, "url": r.url, "description": r.description[:280]} for r in results],
            ensure_ascii=False,
        )

    def jina_read(args: dict) -> str:
        text = _require_jina().read(args["url"], max_chars=MAX_TOOL_RESULT_CHARS)
        return text

    def linkedin_search(args: dict) -> str:
        items = _require_linkedin().search_companies(args["keyword"], page=int(args.get("page", 1)))
        return json.dumps(
            [
                {
                    "name": i.name, "linkedin_url": i.linkedin_url, "domain": i.domain,
                    "industry": i.industry, "headquarters": i.headquarters,
                    "employee_count": i.employee_count,
                    "description": (i.description or "")[:300],
                }
                for i in items
            ],
            ensure_ascii=False,
        )

    def linkedin_company(args: dict) -> str:
        c = _require_linkedin().get_company(args["linkedin_url"])
        return json.dumps(
            {
                "name": c.name, "linkedin_url": c.linkedin_url, "domain": c.domain,
                "industry": c.industry, "headquarters": c.headquarters,
                "employee_count": c.employee_count,
                "description": (c.description or "")[:1200],
            },
            ensure_ascii=False,
        )

    def record_fact(args: dict) -> str:
        category = args.get("category") or "other"
        if category not in CATEGORIES:
            category = "other"
        content = (args.get("content") or "").strip()
        if not content:
            return json.dumps({"ok": False, "reason": "empty content"})
        fp = fingerprint(category, content)
        source_url = (args.get("source_url") or "").strip() or None

        fact = CustomerInsightFact(
            customer_id=customer.id,
            run_id=run.id,
            category=category,
            content=content,
            source_url=source_url,
            fingerprint=fp,
        )
        db.add(fact)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            emit("fact_skipped_duplicate", {"category": category, "content": content[:200], "fingerprint": fp})
            return json.dumps({"ok": True, "duplicate": True, "fingerprint": fp})
        db.refresh(fact)
        emit(
            "fact_recorded",
            {
                "id": fact.id, "category": category, "content": content,
                "source_url": source_url, "fingerprint": fp,
            },
        )
        return json.dumps({"ok": True, "id": fact.id, "fingerprint": fp})

    return {
        "jina_search": jina_search,
        "jina_read": jina_read,
        "linkedin_search": linkedin_search,
        "linkedin_company": linkedin_company,
        "record_fact": record_fact,
    }


# ---------- system prompt ----------

def _build_system_prompt(customer: Customer, prior_facts: List[CustomerInsightFact]) -> str:
    known = ""
    if prior_facts:
        lines = [
            f"- [{f.category}] {f.content}"[:280] for f in prior_facts[:20]
        ]
        known = "\n\n已知事实（勿重复）:\n" + "\n".join(lines)

    return f"""你是一个客户洞察研究员。目标是围绕下面这家客户，**广撒网**收集公开信息 —— 人、事、技术栈、近期动态、行业位置都要抓，**追求广度，不需要严格求证**。

目标客户:
- 名称: {customer.customer_name}
- 编号: {customer.customer_code}
- 已知行业: {customer.industry or '未知'}

可用工具:
- jina_search(query, num): 通用网页搜索
- jina_read(url): 读取 URL 的正文 markdown
- linkedin_search(keyword): 搜 LinkedIn 公司列表
- linkedin_company(linkedin_url): 获取 LinkedIn 公司详情
- record_fact(category, content, source_url): **每发现 1 条有用信息立即调用这个工具保存**
- finish(summary_markdown): 完成。务必在结束前调用，输出中文 markdown 总结。

研究计划建议（你可以偏离）:
1. 先 jina_search 公司官网和简介
2. 若有官网, jina_read 它抓 about / products
3. linkedin_search 拿公司 profile, 必要时 linkedin_company 取详情
4. jina_search 近 6 个月的新闻、融资、产品发布、高管变动
5. 每找到一条就 record_fact, 注意分类
6. 最后 finish, 给一段 markdown 总结 (标题 + 要点 + 建议跟进方向){known}

约束:
- 最多 {MAX_ITERS} 轮工具调用
- 找不到就 finish, 不要编造
- record_fact 的 content 用一句自洽的中文
"""


# ---------- main loop ----------

def run_customer_insight_agent(
    db: Session,
    customer: Customer,
    run: CustomerInsightRun,
    emit: Callable[[str, Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Synchronous run. emit(event, payload) pushes SSE events."""

    emitter = _Emitter(emit=emit, db=db, run=run)
    client = get_azure_openai_client()
    tools = _build_tool_runners(db, customer, run, emitter)

    prior = (
        db.query(CustomerInsightFact)
        .filter(CustomerInsightFact.customer_id == customer.id)
        .order_by(CustomerInsightFact.id.desc())
        .limit(20)
        .all()
    )

    system_prompt = _build_system_prompt(customer, prior)
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请对客户「{customer.customer_name}」做一次洞察研究。"},
    ]

    emitter("run_started", {"run_id": run.id, "customer_id": customer.id, "max_steps": MAX_ITERS})

    final_summary: Optional[str] = None
    token_usage = {"prompt": 0, "completion": 0, "total": 0}

    for step in range(1, MAX_ITERS + 1):
        emitter("step_progress", {"done": step - 1, "total": MAX_ITERS})
        t0 = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=deployment_name(),
                messages=messages,  # type: ignore[arg-type]
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.4,
                max_tokens=1400,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("LLM call failed")
            emitter("error", {"phase": "llm", "message": str(e)})
            raise

        if getattr(resp, "usage", None):
            token_usage["prompt"] += resp.usage.prompt_tokens or 0
            token_usage["completion"] += resp.usage.completion_tokens or 0
            token_usage["total"] += resp.usage.total_tokens or 0

        choice = resp.choices[0]
        msg = choice.message
        tool_calls = getattr(msg, "tool_calls", None) or []

        # Append the assistant message (with tool_calls) to history
        assistant_entry: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls
            ]
        messages.append(assistant_entry)

        if msg.content:
            emitter("thinking", {"text": (msg.content or "")[:800]})

        if not tool_calls:
            # model produced a plain answer without calling finish — treat as final
            final_summary = msg.content or ""
            break

        stop = False
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "finish":
                final_summary = (args.get("summary_markdown") or "").strip() or None
                messages.append({
                    "role": "tool", "tool_call_id": tc.id, "name": name,
                    "content": json.dumps({"ok": True}),
                })
                emitter("finishing", {"summary_preview": (final_summary or "")[:400]})
                stop = True
                continue

            runner = tools.get(name)
            emitter("tool_call", {"name": name, "args": args})
            if not runner:
                result = json.dumps({"ok": False, "error": f"unknown tool: {name}"})
            else:
                try:
                    result = runner(args)
                except Exception as e:  # noqa: BLE001
                    result = json.dumps({"ok": False, "error": str(e)})
                    emitter("tool_error", {"name": name, "error": str(e)})

            preview = result[:400]
            emitter("tool_result", {"name": name, "preview": preview})
            messages.append({
                "role": "tool", "tool_call_id": tc.id, "name": name,
                "content": _truncate(result),
            })

        emitter("step_progress", {"done": step, "total": MAX_ITERS})

        if stop:
            break

        if time.monotonic() - t0 > 120:
            logger.warning("step exceeded 120s wall clock, continuing")

    # Persist final state on the run row
    run.steps_done = min(step, MAX_ITERS)
    run.summary = final_summary
    run.token_usage_json = json.dumps(token_usage)
    run.status = "completed"
    from sqlalchemy.sql import func as _func
    run.completed_at = _func.now()
    db.add(run)
    db.commit()

    emitter("done", {
        "summary": final_summary, "token_usage": token_usage, "steps_done": run.steps_done,
    })
    return {"summary": final_summary, "token_usage": token_usage, "steps_done": run.steps_done}
