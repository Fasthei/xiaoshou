"""Tests for the three AI insight cost guards.

Guard A — cache hit (same customer + same input_hash within 24 h)
Guard B — daily budget exceeded → 503
Guard C — per-customer concurrency lock → 409

All three use in-memory SQLite so no real DB or Redis is needed.
Redis calls in Guard C are monkeypatched.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightRun


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def customer(db):
    c = Customer(
        id=42,
        customer_code="GUARD-001",
        customer_name="护栏测试公司",
        customer_status="prospect",
        industry="SaaS",
        is_deleted=False,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ---------------------------------------------------------------------------
# Guard A — cache hit
# ---------------------------------------------------------------------------

class TestCacheGuard:
    def test_cache_miss_when_no_prior_run(self, db, customer):
        from app.agents.insight_cost_guard import check_cache

        result = check_cache(db, customer.id, "abc123hash")
        assert result.allowed is True
        assert result.cached_run is None

    def test_cache_miss_when_hash_differs(self, db, customer):
        from app.agents.insight_cost_guard import check_cache

        # Insert a completed run with a different hash
        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=5,
            input_hash="old_hash_xyz",
        )
        db.add(run)
        db.commit()

        result = check_cache(db, customer.id, "new_hash_abc")
        assert result.allowed is True

    def test_cache_miss_when_run_too_old(self, db, customer):
        from app.agents.insight_cost_guard import check_cache

        # Insert a completed run with matching hash but > 24 h ago
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=5,
            input_hash="same_hash",
        )
        db.add(run)
        db.commit()
        # Manually backdate started_at
        db.execute(
            __import__("sqlalchemy").text(
                "UPDATE customer_insight_run SET started_at = :ts WHERE id = :id"
            ),
            {"ts": old_time.replace(tzinfo=None), "id": run.id},
        )
        db.commit()

        result = check_cache(db, customer.id, "same_hash")
        assert result.allowed is True

    def test_cache_hit_returns_existing_run(self, db, customer):
        from app.agents.insight_cost_guard import check_cache

        # Insert a fresh completed run with matching hash
        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=8,
            input_hash="same_hash",
            summary="# 缓存摘要",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        result = check_cache(db, customer.id, "same_hash")
        assert result.allowed is False
        assert result.reason == "cache_hit"
        assert result.cached_run is not None
        assert result.cached_run.id == run.id
        assert result.cached_run.summary == "# 缓存摘要"

    def test_cache_miss_when_run_still_running(self, db, customer):
        """A run with status='running' must not satisfy the cache."""
        from app.agents.insight_cost_guard import check_cache

        run = CustomerInsightRun(
            customer_id=customer.id,
            status="running",
            steps_total=12, steps_done=0,
            input_hash="same_hash",
        )
        db.add(run)
        db.commit()

        result = check_cache(db, customer.id, "same_hash")
        assert result.allowed is True


# ---------------------------------------------------------------------------
# Guard B — daily budget
# ---------------------------------------------------------------------------

class TestBudgetGuard:
    def test_budget_allowed_when_no_spend(self, db):
        from app.agents.insight_cost_guard import check_daily_budget

        with patch.dict("os.environ", {"INSIGHT_DAILY_BUDGET_USD": "10.0"}):
            result = check_daily_budget(db)
        assert result.allowed is True

    def test_budget_blocked_when_spent_exceeds_cap(self, db, customer):
        from app.agents.insight_cost_guard import check_daily_budget

        # Insert completed runs that used up $9.99 today
        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=12,
            input_hash="h1",
            cost_usd=9.99,
        )
        db.add(run)
        db.commit()

        # With budget $10.00 and worst-case run ~$0.87, headroom < projected → block
        with patch.dict("os.environ", {"INSIGHT_DAILY_BUDGET_USD": "10.0"}):
            result = check_daily_budget(db)

        # $10 - $9.99 = $0.01 headroom < projected_max → should block
        assert result.allowed is False
        assert "预算已用完" in result.reason
        assert "请明天再试" in result.reason

    def test_budget_allowed_when_well_under_cap(self, db, customer):
        from app.agents.insight_cost_guard import check_daily_budget

        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=3,
            input_hash="h2",
            cost_usd=0.01,
        )
        db.add(run)
        db.commit()

        with patch.dict("os.environ", {"INSIGHT_DAILY_BUDGET_USD": "100.0"}):
            result = check_daily_budget(db)
        assert result.allowed is True

    def test_budget_message_contains_spent_and_limit(self, db, customer):
        from app.agents.insight_cost_guard import check_daily_budget

        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=12,
            input_hash="h3",
            cost_usd=9.99,
        )
        db.add(run)
        db.commit()

        with patch.dict("os.environ", {"INSIGHT_DAILY_BUDGET_USD": "10.0"}):
            result = check_daily_budget(db)

        assert result.allowed is False
        assert "10.00" in result.reason  # budget limit in message


# ---------------------------------------------------------------------------
# Guard C — concurrency lock
# ---------------------------------------------------------------------------

class TestConcurrencyGuard:
    def _make_fake_redis(self, setnx_returns: bool):
        """Return a fake Redis client where SET NX returns setnx_returns."""
        client = MagicMock()
        client.ping.return_value = True
        # redis-py SET with nx=True returns True on success, None on failure
        client.set.return_value = True if setnx_returns else None
        client.delete.return_value = 1
        return client

    def test_lock_acquired_when_no_concurrent_run(self):
        from app.agents.insight_cost_guard import check_concurrency, release_run_lock

        fake_redis = self._make_fake_redis(setnx_returns=True)
        with patch("app.agents.insight_cost_guard._get_redis_client", return_value=fake_redis):
            result = check_concurrency(customer_id=42)
            assert result.allowed is True

            # Clean up
            release_run_lock(customer_id=42)
            fake_redis.delete.assert_called_once()

    def test_lock_blocked_when_run_already_active(self):
        from app.agents.insight_cost_guard import check_concurrency

        # SETNX returns None → lock already held by another run
        fake_redis = self._make_fake_redis(setnx_returns=False)
        with patch("app.agents.insight_cost_guard._get_redis_client", return_value=fake_redis):
            result = check_concurrency(customer_id=42)

        assert result.allowed is False
        assert "正在运行中" in result.reason
        assert "请等待" in result.reason

    def test_lock_allows_when_redis_unavailable(self):
        """If Redis is down, the guard degrades gracefully and allows the run."""
        from app.agents.insight_cost_guard import check_concurrency

        with patch("app.agents.insight_cost_guard._get_redis_client", return_value=None):
            result = check_concurrency(customer_id=99)

        assert result.allowed is True

    def test_different_customers_get_independent_locks(self):
        from app.agents.insight_cost_guard import _lock_key

        assert _lock_key(1) != _lock_key(2)
        assert "1" in _lock_key(1)
        assert "2" in _lock_key(2)


# ---------------------------------------------------------------------------
# Cost estimation helpers
# ---------------------------------------------------------------------------

class TestCostEstimation:
    def test_estimate_run_cost_usd(self):
        from app.agents.insight_cost_guard import estimate_run_cost_usd

        # 1000 prompt + 1000 completion with default prices
        cost = estimate_run_cost_usd(prompt_tokens=1000, completion_tokens=1000)
        assert cost > 0
        assert cost < 1.0  # sanity: less than $1 for 2k tokens

    def test_record_run_cost_writes_to_db(self, db, customer):
        from app.agents.insight_cost_guard import record_run_cost

        run = CustomerInsightRun(
            customer_id=customer.id,
            status="completed",
            steps_total=12, steps_done=4,
            input_hash="hhh",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        record_run_cost(db, run, {"prompt": 5000, "completion": 2000})

        db.refresh(run)
        assert run.cost_usd is not None
        assert float(run.cost_usd) > 0

    def test_input_hash_is_stable(self):
        from app.agents.insight_cost_guard import compute_input_hash

        h1 = compute_input_hash("follow", "contract", "note")
        h2 = compute_input_hash("follow", "contract", "note")
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex

    def test_input_hash_changes_with_content(self):
        from app.agents.insight_cost_guard import compute_input_hash

        h1 = compute_input_hash("follow_a", "contract", "note")
        h2 = compute_input_hash("follow_b", "contract", "note")
        assert h1 != h2
