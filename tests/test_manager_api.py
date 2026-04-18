"""Tests for /api/manager/kpis + /api/manager/sales-performance."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.allocation import Allocation
from app.models.cc_bill import CCBill
from app.models.customer import Customer
from app.models.resource import Resource
from app.models.sales import SalesUser
from main import app


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


def test_kpis_empty_db_returns_zero(client):
    r = client.get("/api/manager/kpis?month=2026-04")
    assert r.status_code == 200
    body = r.json()
    # All 4 required fields present
    for field in ("opportunities", "conversion_rate", "growth_rate", "payment_rate"):
        assert field in body
    # Correct types
    assert isinstance(body["opportunities"], int)
    assert isinstance(body["conversion_rate"], float)
    assert isinstance(body["growth_rate"], float)
    assert isinstance(body["payment_rate"], float)
    # Empty DB -> all zero
    assert body["opportunities"] == 0
    assert body["conversion_rate"] == 0.0
    assert body["growth_rate"] == 0.0
    assert body["payment_rate"] == 0.0


def test_kpis_counts_opportunities_in_month(client, db_session):
    # 2 customers active, 1 of them created in April — so only 1 opportunity.
    now = datetime(2026, 4, 10)
    older = datetime(2026, 2, 1)
    db_session.add(Customer(
        customer_code="C1", customer_name="A", customer_status="active",
        lifecycle_stage="active", created_at=now, is_deleted=False,
    ))
    db_session.add(Customer(
        customer_code="C2", customer_name="B", customer_status="active",
        lifecycle_stage="active", created_at=older, is_deleted=False,
    ))
    db_session.add(Customer(
        customer_code="C3", customer_name="C", customer_status="potential",
        lifecycle_stage="lead", created_at=now, is_deleted=False,
    ))
    db_session.commit()

    body = client.get("/api/manager/kpis?month=2026-04").json()
    assert body["opportunities"] == 1


def test_kpis_payment_rate_from_cc_bill(client, db_session):
    # 2 confirmed, 1 paid → payment_rate should be 1/2 = 0.5
    db_session.add(CCBill(remote_id=1, month="2026-04", status="paid",
                          final_cost=Decimal("100")))
    db_session.add(CCBill(remote_id=2, month="2026-04", status="confirmed",
                          final_cost=Decimal("100")))
    db_session.add(CCBill(remote_id=3, month="2026-04", status="draft",
                          final_cost=Decimal("100")))
    db_session.commit()

    body = client.get("/api/manager/kpis?month=2026-04").json()
    # paid=1, confirmed+paid=2 → 0.5
    assert body["payment_rate"] == pytest.approx(0.5)


def test_sales_performance_empty_ok(client):
    r = client.get("/api/manager/sales-performance?month=2026-04")
    assert r.status_code == 200
    assert r.json() == []


def test_sales_performance_returns_cards(client, db_session):
    s = SalesUser(
        id=1, name="张三", is_active=True,
        annual_profit_target=Decimal("100000"), target_year=2026,
    )
    db_session.add(s)
    # 2 customers assigned to sales 1
    db_session.add(Customer(
        customer_code="C1", customer_name="A", customer_status="active",
        sales_user_id=1, is_deleted=False,
    ))
    db_session.add(Customer(
        customer_code="C2", customer_name="B", customer_status="active",
        sales_user_id=1, is_deleted=False,
    ))
    db_session.commit()

    r = client.get("/api/manager/sales-performance?month=2026-04")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    for field in ("id", "name", "customer_count", "ytd_gmv", "target_gmv", "progress_pct"):
        assert field in row
    assert row["id"] == 1
    assert row["name"] == "张三"
    assert row["customer_count"] == 2
    assert row["target_gmv"] == 100000.0
    # No allocations yet → ytd_gmv = 0 → progress_pct = 0
    assert row["ytd_gmv"] == 0.0
    assert row["progress_pct"] == 0.0
