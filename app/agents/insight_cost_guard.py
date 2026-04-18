"""Insight cost-guard helpers — cache, daily budget, concurrency lock.

Three guardrails called by the API layer *before* spawning the agent thread:

  Guard A – Cache (24 h, same customer + same input_hash)
  Guard B – Daily budget cap (env INSIGHT_DAILY_BUDGET_USD, default $10)
  Guard C – Per-customer concurrency lock (Redis SETNX, 5-min TTL)

All three return a simple result object; the API translates failures to HTTP
responses so the agent core (customer_insight_agent.py) stays unaware.

Design constraints:
- No new Python dependencies (redis==5.0.1 already in requirements.txt).
- Redis is optional: if the connection fails or REDIS_URL is not set the
  concurrency guard degrades gracefully (logs a warning, allows the run).
- Cost estimation uses gpt-4o pricing as a conservative proxy for Azure
  deployments; the exact model price can be overridden via env vars.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func as sqlfunc, text
from sqlalchemy.orm import Session

from app.models.customer_insight import CustomerInsightRun

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants (all overridable via environment)
# ---------------------------------------------------------------------------

CACHE_TTL_HOURS: int = 24
LOCK_TTL_SECONDS: int = 300  # 5 minutes

# USD per 1 000 tokens (conservative gpt-4o proxy; tune if needed)
PRICE_PER_1K_PROMPT_USD: float = float(os.environ.get("INSIGHT_PRICE_PER_1K_PROMPT", "0.005"))
PRICE_PER_1K_COMPLETION_USD: float = float(os.environ.get("INSIGHT_PRICE_PER_1K_COMPLETION", "0.015"))


def _daily_budget_usd() -> float:
    return float(os.environ.get("INSIGHT_DAILY_BUDGET_USD", "10.0"))


def _lock_key(customer_id: int) -> str:
    return f"insight:lock:customer:{customer_id}"


# ---------------------------------------------------------------------------
# Guard result type
# ---------------------------------------------------------------------------

@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    cached_run: Optional[CustomerInsightRun] = None


# ---------------------------------------------------------------------------
# Guard A — cache
# ---------------------------------------------------------------------------

def compute_input_hash(follow_ups_repr: str, contracts_repr: str, notes_repr: str) -> str:
    """Stable sha256 of the three input blobs concatenated with a separator."""
    payload = "\x00".join([follow_ups_repr, contracts_repr, notes_repr])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_input_hash_from_db(db: Session, customer_id: int) -> str:
    """Pull the raw data needed for the hash directly from the DB.

    We hash the repr of follow-up titles+contents, active contract codes,
    and the customer note — the same fields the agent injects into its prompt.
    Changing any of these will produce a different hash and bypass the cache.
    """
    from app.models.follow_up import CustomerFollowUp
    from app.models.contract import Contract
    from app.models.customer import Customer

    try:
        customer = db.query(Customer).filter(Customer.id == customer_id).first()
        note = getattr(customer, "note", "") or ""

        follow_ups = (
            db.query(CustomerFollowUp)
            .filter(CustomerFollowUp.customer_id == customer_id)
            .order_by(CustomerFollowUp.created_at.desc())
            .limit(10)
            .all()
        )
        fu_repr = json.dumps(
            [{"title": f.title, "content": (f.content or "")[:200]} for f in follow_ups],
            ensure_ascii=False, sort_keys=True,
        )

        contracts = (
            db.query(Contract)
            .filter(Contract.customer_id == customer_id, Contract.status == "active")
            .order_by(Contract.start_date.desc())
            .all()
        )
        ct_repr = json.dumps(
            [{"code": c.contract_code, "title": c.title, "amount": str(c.amount)} for c in contracts],
            ensure_ascii=False, sort_keys=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("build_input_hash_from_db failed, using empty hash")
        fu_repr, ct_repr, note = "", "", ""

    return compute_input_hash(fu_repr, ct_repr, note)


def check_cache(db: Session, customer_id: int, input_hash: str) -> GuardResult:
    """Return GuardResult(allowed=False, cached_run=<run>) if a fresh identical run exists."""
    try:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)
        # started_at is server_default=func.now() which stores naive UTC on PG
        cached = (
            db.query(CustomerInsightRun)
            .filter(
                CustomerInsightRun.customer_id == customer_id,
                CustomerInsightRun.input_hash == input_hash,
                CustomerInsightRun.status == "completed",
                CustomerInsightRun.started_at >= cutoff,
            )
            .order_by(CustomerInsightRun.id.desc())
            .first()
        )
        if cached:
            logger.info(
                "insight cache hit: customer=%s run=%s input_hash=%s…",
                customer_id, cached.id, input_hash[:8],
            )
            return GuardResult(allowed=False, reason="cache_hit", cached_run=cached)
    except Exception:  # noqa: BLE001
        logger.exception("check_cache query failed, allowing run")
    return GuardResult(allowed=True)


# ---------------------------------------------------------------------------
# Guard B — daily budget
# ---------------------------------------------------------------------------

def estimate_run_cost_usd(prompt_tokens: int = 0, completion_tokens: int = 0) -> float:
    """Estimate cost for a completed run from its token counts."""
    return (
        prompt_tokens / 1000 * PRICE_PER_1K_PROMPT_USD
        + completion_tokens / 1000 * PRICE_PER_1K_COMPLETION_USD
    )


def estimate_max_run_cost_usd() -> float:
    """Conservative upper bound for one run (12 iters × ~1400 completion tokens each)."""
    max_prompt = 12 * 8000   # system prompt + history grows per step
    max_completion = 12 * 1400
    return estimate_run_cost_usd(max_prompt, max_completion)


def get_today_spent_usd(db: Session) -> float:
    """Sum cost_usd of all completed runs started today (UTC)."""
    try:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        result = (
            db.query(sqlfunc.coalesce(sqlfunc.sum(CustomerInsightRun.cost_usd), 0))
            .filter(
                CustomerInsightRun.status == "completed",
                CustomerInsightRun.started_at >= today_start,
                CustomerInsightRun.cost_usd.isnot(None),
            )
            .scalar()
        )
        return float(result or 0)
    except Exception:  # noqa: BLE001
        logger.exception("get_today_spent_usd failed, returning 0")
        return 0.0


def check_daily_budget(db: Session) -> GuardResult:
    """Block if today's spend + one worst-case run would exceed the daily cap."""
    budget = _daily_budget_usd()
    spent = get_today_spent_usd(db)
    headroom = budget - spent
    projected = estimate_max_run_cost_usd()
    if headroom < projected:
        msg = (
            f"今日 AI 洞察预算已用完（已用 ${spent:.4f} / 上限 ${budget:.2f}），"
            "请明天再试"
        )
        logger.warning("insight budget exceeded: spent=%.4f budget=%.2f", spent, budget)
        return GuardResult(allowed=False, reason=msg)
    return GuardResult(allowed=True)


def record_run_cost(db: Session, run: CustomerInsightRun, token_usage: dict) -> None:
    """Write cost_usd back to the run row after the agent finishes."""
    try:
        prompt = token_usage.get("prompt", 0)
        completion = token_usage.get("completion", 0)
        cost = estimate_run_cost_usd(prompt, completion)
        run.cost_usd = cost
        db.add(run)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("record_run_cost failed")


# ---------------------------------------------------------------------------
# Guard C — per-customer concurrency lock (Redis SETNX)
# ---------------------------------------------------------------------------

def _get_redis_client():
    """Return a redis.Redis client or None if Redis is unavailable."""
    try:
        import redis as redis_lib
        from app.config import get_settings
        s = get_settings()
        url = s.effective_redis_url
        client = redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=2)
        client.ping()
        return client
    except Exception:  # noqa: BLE001
        logger.warning("Redis unavailable — concurrency guard disabled")
        return None


def acquire_run_lock(customer_id: int) -> bool:
    """Set NX lock for customer. Returns True if lock acquired, False if already held."""
    client = _get_redis_client()
    if client is None:
        return True  # degrade gracefully: allow run
    key = _lock_key(customer_id)
    try:
        acquired = client.set(key, "1", nx=True, ex=LOCK_TTL_SECONDS)
        return bool(acquired)
    except Exception:  # noqa: BLE001
        logger.warning("acquire_run_lock redis error, allowing run")
        return True


def release_run_lock(customer_id: int) -> None:
    """Release the concurrency lock for customer."""
    client = _get_redis_client()
    if client is None:
        return
    key = _lock_key(customer_id)
    try:
        client.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("release_run_lock redis error (key=%s)", key)


def check_concurrency(customer_id: int) -> GuardResult:
    """Block if this customer already has a run in progress."""
    if not acquire_run_lock(customer_id):
        return GuardResult(
            allowed=False,
            reason="该客户的 AI 洞察正在运行中，请等待",
        )
    return GuardResult(allowed=True)
