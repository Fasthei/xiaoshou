"""Tests for GET /api/metrics/team-profit (ManagerPanorama 团队销售目标聚合)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from app.models.allocation import Allocation
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


@pytest.fixture()
def three_sales_users(db_session):
    """3 个 active 销售用户，annual_sales_target 分别 100 / 200 / 300。"""
    s1 = SalesUser(name="Sales A", is_active=True, annual_sales_target=Decimal("100.00"))
    s2 = SalesUser(name="Sales B", is_active=True, annual_sales_target=Decimal("200.00"))
    s3 = SalesUser(name="Sales C", is_active=True, annual_sales_target=Decimal("300.00"))
    db_session.add_all([s1, s2, s3])
    db_session.commit()
    for s in (s1, s2, s3):
        db_session.refresh(s)
    return s1, s2, s3


def test_team_profit_total_sales_target_is_sum(client, three_sales_users):
    """3 个销售各 100/200/300 → total_annual_sales_target == 600。"""
    r = client.get("/api/metrics/team-profit")
    assert r.status_code == 200, r.text

    body = r.json()
    assert "team_annual_sales_target" in body
    assert body["team_annual_sales_target"] == pytest.approx(600.0)


def test_team_profit_response_contains_required_fields(client, three_sales_users):
    """响应包含 year / team_annual_sales_target / team_annual_sales_achieved 等关键字段。"""
    r = client.get("/api/metrics/team-profit")
    assert r.status_code == 200, r.text

    body = r.json()
    required = (
        "year",
        "team_annual_sales_target",
        "team_annual_sales_achieved",
        "team_annual_profit_target",
        "team_annual_profit_achieved",
        "team_profit_rate_target",
        "team_profit_rate_actual",
    )
    for field in required:
        assert field in body, f"Missing field: {field}"


def test_team_profit_achieved_aggregates_allocations(client, db_session, three_sales_users):
    """team_annual_sales_achieved 聚合当年 allocation.total_price（名下客户）。

    s1 名下客户有 total_price=500 的 allocation → achieved 包含 500。
    """
    from datetime import datetime
    s1, s2, s3 = three_sales_users
    year = datetime.utcnow().year

    # Seed a resource (resource_id is NOT NULL on allocation)
    res = Resource(
        resource_code="PANO-R1", resource_type="cloud",
        total_quantity=100, allocated_quantity=0, available_quantity=100,
        unit_cost=Decimal("200.00"), resource_status="AVAILABLE", is_deleted=False,
    )
    db_session.add(res)
    db_session.commit()
    db_session.refresh(res)

    # Customer assigned to s1
    c = Customer(
        customer_code="PANO-C1",
        customer_name="全景测试客户",
        customer_status="active",
        sales_user_id=s1.id,
        is_deleted=False,
        current_resource_count=0,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    # Allocation for that customer in current year
    alloc = Allocation(
        allocation_code=f"PANO-ALLOC-{year}",
        customer_id=c.id,
        resource_id=res.id,
        allocated_quantity=1,
        unit_cost=Decimal("200.00"),
        unit_price=Decimal("500.00"),
        total_cost=Decimal("200.00"),
        total_price=Decimal("500.00"),
        profit_amount=Decimal("300.00"),
        profit_rate=Decimal("60.00"),
        allocation_status="PENDING",
        approval_status="approved",
        allocated_at=datetime(year, 6, 1),
        is_deleted=False,
    )
    db_session.add(alloc)
    db_session.commit()

    r = client.get(f"/api/metrics/team-profit?year={year}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team_annual_sales_achieved"] == pytest.approx(500.0)


def test_team_profit_excludes_inactive_sales_from_target(client, db_session):
    """inactive 销售的目标不计入 team_annual_sales_target。"""
    active_s = SalesUser(name="Active", is_active=True, annual_sales_target=Decimal("100.00"))
    inactive_s = SalesUser(name="Inactive", is_active=False, annual_sales_target=Decimal("9999.00"))
    db_session.add_all([active_s, inactive_s])
    db_session.commit()

    r = client.get("/api/metrics/team-profit")
    assert r.status_code == 200, r.text
    body = r.json()
    # Only active sales target counted: 100, not 9999
    assert body["team_annual_sales_target"] == pytest.approx(100.0)
