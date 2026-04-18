"""Customer Insight Agent HTTP API — SSE streaming + history queries."""
from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Generator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agents.customer_insight_agent import MAX_ITERS, run_customer_insight_agent
from app.agents.insight_cost_guard import (
    build_input_hash_from_db,
    check_cache,
    check_concurrency,
    check_daily_budget,
    record_run_cost,
    release_run_lock,
)
from app.auth import CurrentUser, require_auth
from app.database import SessionLocal, get_db
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightFact, CustomerInsightRun
from app.schemas.customer_insight import InsightFactOut, InsightRunDetail, InsightRunOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/customer", tags=["客户洞察 Agent"])


def _sse_format(event: str, data: dict) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")


def _stream_generator(customer_id: int, user_id: Optional[int]) -> Generator[bytes, None, None]:
    """Run the agent in a worker thread, stream events as SSE bytes.

    Uses its own DB session (separate from the FastAPI request session) so
    that the stream can survive the request's dependency teardown.

    Three cost guards are applied before the agent thread is spawned:
      A) Cache — 24 h identical-input dedup
      B) Daily budget cap (INSIGHT_DAILY_BUDGET_USD, default $10)
      C) Per-customer concurrency lock (Redis SETNX, 5-min TTL)
    """
    q: "queue.Queue[tuple[str, dict] | None]" = queue.Queue(maxsize=256)
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(
            Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
        ).first()
    except Exception as e:  # noqa: BLE001 — DB transient errors shouldn't crash the stream
        logger.exception("customer lookup failed")
        db.close()
        yield _sse_format("error", {"message": f"客户查询失败: {e}"})
        return
    if not customer:
        db.close()
        yield _sse_format("error", {"message": "客户不存在"})
        return

    # ---- Guard A: cache (same customer + same input hash within 24 h) ----
    input_hash = build_input_hash_from_db(db, customer_id)
    cache_result = check_cache(db, customer_id, input_hash)
    if not cache_result.allowed:
        cached_run = cache_result.cached_run
        db.close()
        yield _sse_format("cache_hit", {
            "run_id": cached_run.id,
            "customer_id": customer_id,
            "summary": cached_run.summary,
            "message": "24h 内已有相同输入的洞察结果，直接复用",
        })
        return

    # ---- Guard B: daily budget cap ----
    budget_result = check_daily_budget(db)
    if not budget_result.allowed:
        db.close()
        yield _sse_format("error", {"message": budget_result.reason, "code": "budget_exceeded"})
        return

    # ---- Guard C: per-customer concurrency lock ----
    concurrency_result = check_concurrency(customer_id)
    if not concurrency_result.allowed:
        db.close()
        yield _sse_format("error", {"message": concurrency_result.reason, "code": "already_running"})
        return

    run = CustomerInsightRun(
        customer_id=customer.id, status="running",
        steps_total=MAX_ITERS, steps_done=0, triggered_by=user_id,
        input_hash=input_hash,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    def emit(event: str, data: dict) -> None:
        try:
            q.put_nowait((event, data))
        except queue.Full:
            logger.warning("SSE queue full, dropping event %s", event)

    def worker():
        try:
            result = run_customer_insight_agent(db, customer, run, emit)
            # Write cost_usd back to the run row
            token_usage = result.get("token_usage", {}) if result else {}
            record_run_cost(db, run, token_usage)
        except Exception as e:  # noqa: BLE001
            logger.exception("agent run failed")
            run.status = "failed"
            run.error_message = str(e)[:2000]
            try:
                db.add(run)
                db.commit()
            except Exception:
                db.rollback()
            emit("error", {"message": str(e)})
        finally:
            release_run_lock(customer_id)
            q.put(None)  # sentinel
            db.close()

    t = threading.Thread(target=worker, daemon=True, name=f"insight-run-{run.id}")
    t.start()

    # Initial handshake event so the client knows the run_id immediately.
    yield _sse_format("run_created", {"run_id": run.id, "customer_id": customer.id})

    try:
        while True:
            item = q.get()
            if item is None:
                break
            event, data = item
            yield _sse_format(event, data)
    except GeneratorExit:
        # Client disconnected mid-stream; the worker thread is daemon and will
        # finish (and persist) on its own. Do not re-raise as an error event.
        logger.info("SSE client disconnected for run %s", getattr(run, "id", None))
        raise


@router.post("/{customer_id}/insight/run", summary="运行 AI 洞察 Agent (SSE 流)")
def start_insight_run(
    customer_id: int,
    user: CurrentUser = Depends(require_auth),
):
    """Stream AI insight events via SSE.

    Cost guards (cache / budget / concurrency) run inside _stream_generator
    before the agent thread is spawned. Failures are communicated as SSE
    error / cache_hit events with a 'code' field so the frontend can
    distinguish guard rejections from agent errors:
      code=budget_exceeded  → HTTP 503 semantics
      code=already_running  → HTTP 409 semantics
      cache_hit event       → no new run created, existing summary returned
    """
    user_id = getattr(user, "id", None) if user else None
    return StreamingResponse(
        _stream_generator(customer_id, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/Azure FD)
        },
    )


@router.get("/{customer_id}/insight/runs", response_model=List[InsightRunOut],
            summary="该客户历史运行列表")
def list_runs(
    customer_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    from sqlalchemy import func as sqlfunc
    rows = (
        db.query(CustomerInsightRun, sqlfunc.count(CustomerInsightFact.id).label("fact_count"))
        .outerjoin(CustomerInsightFact, CustomerInsightFact.run_id == CustomerInsightRun.id)
        .filter(CustomerInsightRun.customer_id == customer_id)
        .group_by(CustomerInsightRun.id)
        .order_by(CustomerInsightRun.id.desc())
        .limit(limit)
        .all()
    )
    result = []
    for run, fact_count in rows:
        out = InsightRunOut.model_validate(run)
        out.fact_count = fact_count or 0
        if run.started_at and run.completed_at:
            delta = run.completed_at - run.started_at
            out.duration_ms = int(delta.total_seconds() * 1000)
        result.append(out)
    return result


@router.get("/{customer_id}/insight/runs/{run_id}", response_model=InsightRunDetail,
            summary="单次运行详情 + facts")
def get_run(
    customer_id: int, run_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    run = db.query(CustomerInsightRun).filter(
        CustomerInsightRun.id == run_id,
        CustomerInsightRun.customer_id == customer_id,
    ).first()
    if not run:
        raise HTTPException(404, "运行不存在")
    facts = (
        db.query(CustomerInsightFact)
        .filter(CustomerInsightFact.run_id == run_id)
        .order_by(CustomerInsightFact.id.asc())
        .all()
    )
    out = InsightRunDetail.model_validate(run)
    out.facts = [InsightFactOut.model_validate(f) for f in facts]
    return out


@router.get("/{customer_id}/insight/facts", response_model=List[InsightFactOut],
            summary="该客户所有 facts (可按 category 过滤)")
def list_facts(
    customer_id: int,
    category: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(CustomerInsightFact).filter(CustomerInsightFact.customer_id == customer_id)
    if category:
        q = q.filter(CustomerInsightFact.category == category)
    return q.order_by(CustomerInsightFact.id.desc()).limit(limit).all()
