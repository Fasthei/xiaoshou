"""Tests for the usage_surge trigger service.

Uses SQLAlchemy in-memory SQLite so no real DB is required.
Each test verifies exactly one behaviour of evaluate_usage_surge_rules(db).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.services.usage_surge_trigger import evaluate_usage_surge_rules


# ---------------------------------------------------------------------------
# Shared fixture — one in-memory SQLite per test
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    """Return a fresh SQLAlchemy Session backed by an in-memory SQLite DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_customer(db, code: str = "CUST-001") -> Customer:
    c = Customer(
        customer_code=code,
        customer_name=f"Test {code}",
        customer_status="active",
        lifecycle_stage="active",
        is_deleted=False,
    )
    db.add(c)
    db.flush()
    return c


def _make_rule(db, customer_id=None, threshold: float = 30.0) -> AlertRule:
    r = AlertRule(
        customer_id=customer_id,
        rule_name="测试激增规则",
        rule_type="usage_surge",
        threshold_value=Decimal(str(threshold)),
        enabled=True,
    )
    db.add(r)
    db.flush()
    return r


def _make_usage(db, customer_code: str, d: date, cost: float, service: str = "EC2") -> CCUsage:
    """Insert a CCUsage row with raw structured as accounts list."""
    row = CCUsage(
        customer_code=customer_code,
        date=d,
        total_cost=Decimal(str(cost)),
        raw={"accounts": [{"service": service, "cost": cost}]},
    )
    db.add(row)
    db.flush()
    return row


def _today() -> date:
    return date.today()


def _prev_month_date() -> date:
    """Return a date that is safely in the previous calendar month."""
    first_of_this_month = _today().replace(day=1)
    return first_of_this_month - timedelta(days=1)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_no_rules_returns_zero(db):
    """When there are no alert rules in the DB the trigger returns 0 alerts created."""
    # DB is empty — no alert rules at all
    result = evaluate_usage_surge_rules(db)
    assert result == 0


def test_threshold_not_exceeded(db):
    """When MoM surge is below the threshold, no alert is created."""
    customer = _make_customer(db, "CUST-LOW")
    _make_rule(db, customer_id=customer.id, threshold=50.0)

    # Previous month: $100, current month: $120 (+20%, below 50% threshold)
    prev_date = _prev_month_date()
    curr_date = _today()
    _make_usage(db, "CUST-LOW", prev_date, 100.0, service="CloudStorage")
    _make_usage(db, "CUST-LOW", curr_date, 120.0, service="CloudStorage")
    db.commit()

    result = evaluate_usage_surge_rules(db)

    assert result == 0
    assert db.query(AlertEvent).count() == 0


def test_threshold_exceeded_creates_alert(db):
    """When MoM usage exceeds the configured threshold an alert row is inserted."""
    customer = _make_customer(db, "CUST-HIGH")
    rule = _make_rule(db, customer_id=customer.id, threshold=30.0)

    # Previous month: $100, current month: $150 (+50%, exceeds 30% threshold)
    prev_date = _prev_month_date()
    curr_date = _today()
    _make_usage(db, "CUST-HIGH", prev_date, 100.0, service="EC2")
    _make_usage(db, "CUST-HIGH", curr_date, 150.0, service="EC2")
    db.commit()

    result = evaluate_usage_surge_rules(db)

    assert result == 1

    events = db.query(AlertEvent).all()
    assert len(events) == 1
    ev = events[0]
    assert ev.alert_rule_id == rule.id
    assert ev.customer_id == customer.id
    assert ev.service == "EC2"
    assert ev.alert_type == "usage_surge"
    # actual_pct should be roughly 50%
    assert ev.actual_pct is not None
    assert float(ev.actual_pct) == pytest.approx(50.0, abs=0.1)


def test_dedup_within_same_month(db):
    """When an alert already exists for this customer+service+month, no duplicate is inserted."""
    today = _today()
    month_str = today.strftime("%Y-%m")

    customer = _make_customer(db, "CUST-DUP")
    rule = _make_rule(db, customer_id=customer.id, threshold=10.0)

    # Previous month: $100, current month: $180 (+80%, well above 10% threshold)
    prev_date = _prev_month_date()
    _make_usage(db, "CUST-DUP", prev_date, 100.0, service="RDS")
    _make_usage(db, "CUST-DUP", today, 180.0, service="RDS")

    # Pre-seed an existing AlertEvent for the same dedup key
    existing = AlertEvent(
        alert_rule_id=rule.id,
        alert_type="usage_surge",
        customer_id=customer.id,
        service="RDS",
        month=month_str,
        actual_pct=Decimal("80.00"),
        threshold_value=rule.threshold_value,
        message="pre-existing alert",
    )
    db.add(existing)
    db.commit()

    # Trigger should detect the unique constraint violation and dedup
    result = evaluate_usage_surge_rules(db)

    assert result == 0
    # Count must stay at exactly 1 — no duplicate row
    assert db.query(AlertEvent).count() == 1
