"""Tests for the contract_expiry_trigger service.

Uses SQLAlchemy in-memory SQLite so no real DB is required.
Each test verifies exactly one behaviour of evaluate_contract_expiring_rules(db).
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
from app.models.contract import Contract
from app.models.customer import Customer
from app.services.contract_expiry_trigger import evaluate_contract_expiring_rules


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


def _make_rule(db, customer_id=None, threshold_days: int = 30) -> AlertRule:
    r = AlertRule(
        customer_id=customer_id,
        rule_name="合同到期提醒规则",
        rule_type="contract_expiring",
        threshold_value=Decimal(str(threshold_days)),
        threshold_unit="days",
        enabled=True,
    )
    db.add(r)
    db.flush()
    return r


def _make_contract(
    db,
    customer_id: int,
    end_date: date,
    status: str = "active",
    code: str = "CONTRACT-001",
    title: str = "测试合同",
) -> Contract:
    c = Contract(
        customer_id=customer_id,
        contract_code=code,
        title=title,
        status=status,
        end_date=end_date,
    )
    db.add(c)
    db.flush()
    return c


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_in_window_creates_alert(db):
    """合同 25 天后到期, 规则 30 天窗口 → 触发, alert_event 多一行."""
    customer = _make_customer(db, "CUST-EXP-1")
    rule = _make_rule(db, customer_id=customer.id, threshold_days=30)

    end_date = date.today() + timedelta(days=25)
    contract = _make_contract(db, customer.id, end_date, code="C-WIN-001")
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 1
    events = db.query(AlertEvent).all()
    assert len(events) == 1
    ev = events[0]
    assert ev.alert_rule_id == rule.id
    assert ev.customer_id == customer.id
    assert ev.alert_type == "contract_expiring"
    assert ev.service == "contract"
    assert ev.month == end_date.strftime("%Y-%m")
    assert contract.contract_code in ev.message
    assert "25 天" in ev.message


def test_outside_window(db):
    """合同 60 天后到期, 规则 30 天窗口 → 不触发."""
    customer = _make_customer(db, "CUST-EXP-2")
    _make_rule(db, customer_id=customer.id, threshold_days=30)

    end_date = date.today() + timedelta(days=60)
    _make_contract(db, customer.id, end_date, code="C-OUT-001")
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 0
    assert db.query(AlertEvent).count() == 0


def test_already_expired_not_triggered(db):
    """status='expired' 的合同不触发, 即使 end_date 在窗口内."""
    customer = _make_customer(db, "CUST-EXP-3")
    _make_rule(db, customer_id=customer.id, threshold_days=30)

    end_date = date.today() + timedelta(days=10)
    _make_contract(db, customer.id, end_date, status="expired", code="C-EXP-001")
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 0
    assert db.query(AlertEvent).count() == 0


def test_null_end_date_skipped(db):
    """end_date 为 NULL 的合同不触发."""
    customer = _make_customer(db, "CUST-EXP-4")
    _make_rule(db, customer_id=customer.id, threshold_days=30)

    c = Contract(
        customer_id=customer.id,
        contract_code="C-NULL-001",
        title="无日期合同",
        status="active",
        end_date=None,
    )
    db.add(c)
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 0
    assert db.query(AlertEvent).count() == 0


def test_dedup_same_month(db):
    """同一 (rule, customer, 'contract', month) 已存在 alert_event → 不重复插入."""
    customer = _make_customer(db, "CUST-EXP-5")
    rule = _make_rule(db, customer_id=customer.id, threshold_days=30)

    end_date = date.today() + timedelta(days=10)
    month_str = end_date.strftime("%Y-%m")
    _make_contract(db, customer.id, end_date, code="C-DUP-001")

    # Pre-seed existing alert for the same dedup key
    existing = AlertEvent(
        alert_rule_id=rule.id,
        alert_type="contract_expiring",
        customer_id=customer.id,
        service="contract",
        month=month_str,
        threshold_value=rule.threshold_value,
        message="pre-existing",
    )
    db.add(existing)
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 0
    assert db.query(AlertEvent).count() == 1


def test_global_rule_scans_all_customers(db):
    """全局规则 (customer_id=None) 扫全量客户合同."""
    c1 = _make_customer(db, "CUST-G1")
    c2 = _make_customer(db, "CUST-G2")
    rule = _make_rule(db, customer_id=None, threshold_days=30)

    end_date = date.today() + timedelta(days=15)
    _make_contract(db, c1.id, end_date, code="C-G1-001")
    _make_contract(db, c2.id, end_date, code="C-G2-001")
    db.commit()

    result = evaluate_contract_expiring_rules(db)

    assert result == 2
    events = db.query(AlertEvent).filter(AlertEvent.alert_rule_id == rule.id).all()
    assert len(events) == 2
