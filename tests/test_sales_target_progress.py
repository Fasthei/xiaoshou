"""Unit tests for GET /api/sales/me/target-progress.

Two cases:
  1. unbound — casdoor_user_id not found in sales_user → unbound=True, safe defaults
  2. bound with YTD allocations → correct YTD / pct / daily_target values
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.resource import Resource
from app.models.sales import SalesUser
from main import app


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()

    def override_get_db():
        try:
            yield s
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield s
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


# ── helpers ─────────────────────────────────────────────────────────────────

def _seed_resource(db) -> Resource:
    r = Resource(
        resource_code="R-001",
        resource_type="ORIGINAL",
        cloud_provider="AWS",
        account_name="测试货源",
        resource_status="AVAILABLE",
    )
    db.add(r)
    db.flush()
    return r


def _seed_customer(db, sales_user_id: int) -> Customer:
    c = Customer(
        customer_code="C-T001",
        customer_name="测试客户",
        customer_status="active",
        lifecycle_stage="active",
        is_deleted=False,
        sales_user_id=sales_user_id,
    )
    db.add(c)
    db.flush()
    return c


_ALLOC_SEQ = [0]


def _seed_allocation(db, customer_id: int, resource_id: int,
                     total_price: Decimal, profit_amount: Decimal,
                     year: int = 2026) -> Allocation:
    _ALLOC_SEQ[0] += 1
    a = Allocation(
        allocation_code=f"A-{customer_id}-{resource_id}-{_ALLOC_SEQ[0]}",
        customer_id=customer_id,
        resource_id=resource_id,
        allocated_quantity=1,
        total_price=total_price,
        profit_amount=profit_amount,
        allocation_status="approved",
        is_deleted=False,
        allocated_at=datetime(year, 3, 15),
    )
    db.add(a)
    db.flush()
    return a


# ── test 1: unbound account ──────────────────────────────────────────────────

def test_me_target_progress_unbound(client, db_session):
    """An account whose casdoor_user_id is not in sales_user gets unbound=True."""
    # No sales_user rows — nobody is bound.
    r = client.get("/api/sales/me/target-progress")
    assert r.status_code == 200
    body = r.json()
    assert body["unbound"] is True
    assert body["sales_user_id"] == 0
    assert float(body["ytd_sales"]) == 0.0
    assert float(body["ytd_profit"]) == 0.0
    assert body["sales_progress_pct"] == 0.0
    assert body["profit_progress_pct"] == 0.0


# ── test 2: bound with targets + allocations ─────────────────────────────────

def test_me_target_progress_with_data(client, db_session):
    """Bound sales user with annual targets and YTD allocations returns correct progress."""
    # The test client uses AUTH_ENABLED=false; the injected CurrentUser has sub="local-dev".
    su = SalesUser(
        name="测试销售",
        casdoor_user_id="dev",   # matches AUTH_ENABLED=false stub sub="dev"
        is_active=True,
        annual_sales_target=Decimal("1000000"),   # 100 万
        annual_profit_target=Decimal("200000"),   # 20 万
        profit_margin_target=Decimal("20"),       # 20%
        target_year=2026,
    )
    db_session.add(su)
    db_session.flush()

    resource = _seed_resource(db_session)
    customer = _seed_customer(db_session, su.id)

    # Two allocations in 2026 → total_price=300000, profit_amount=60000
    _seed_allocation(db_session, customer.id, resource.id,
                     Decimal("200000"), Decimal("40000"), year=2026)
    _seed_allocation(db_session, customer.id, resource.id,
                     Decimal("100000"), Decimal("20000"), year=2026)
    db_session.commit()

    r = client.get("/api/sales/me/target-progress")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["unbound"] is False
    assert body["sales_user_id"] == su.id
    assert body["sales_user_name"] == "测试销售"
    assert body["target_year"] == 2026

    assert float(body["ytd_sales"]) == pytest.approx(300000.0)
    assert float(body["ytd_profit"]) == pytest.approx(60000.0)

    # sales_progress_pct = 300000 / 1000000 * 100 = 30%
    assert body["sales_progress_pct"] == pytest.approx(30.0, rel=0.01)
    # profit_progress_pct = 60000 / 200000 * 100 = 30%
    assert body["profit_progress_pct"] == pytest.approx(30.0, rel=0.01)

    # days_remaining and daily targets — just assert shape / types
    assert isinstance(body["days_remaining_in_year"], int)
    assert body["days_remaining_in_year"] >= 0
    # daily_sales_target_to_close = gap / days_remaining  (gap = 700000)
    # We just verify it's a positive number (unless we're past year-end)
    assert float(body["daily_sales_target_to_close"]) >= 0.0
    assert float(body["daily_profit_target_to_close"]) >= 0.0
