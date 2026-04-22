"""Tests for /api/bills/adjustment — 账单中心覆盖 (折扣率 / 手续费)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_auth
from app.database import Base, get_db
from app.models.bill_adjustment import BillAdjustment
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


def _admin_override():
    app.dependency_overrides[require_auth] = lambda: CurrentUser(
        sub="admin", name="admin", roles=["admin"], raw={},
    )


def _reset_override():
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture()
def seed(db_session):
    db_session.add_all([
        Customer(id=1, customer_code="C1", customer_name="客户 1",
                 customer_status="active", is_deleted=False),
        Resource(id=11, resource_code="res-1", resource_type="cloud",
                 cloud_provider="AWS", identifier_field="proj-1",
                 resource_status="active"),
    ])
    db_session.commit()


def test_put_creates_adjustment(client, db_session, seed):
    _admin_override()
    try:
        r = client.put("/api/bills/adjustment", json={
            "customer_id": 1, "resource_id": 11, "month": "2026-04",
            "discount_rate_override": "10.00",
            "surcharge": "50.00",
            "notes": "财务调整",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["customer_id"] == 1
        assert body["month"] == "2026-04"
        assert Decimal(body["discount_rate_override"]) == Decimal("10.00")
        assert Decimal(body["surcharge"]) == Decimal("50.00")
        row = db_session.query(BillAdjustment).filter_by(
            customer_id=1, resource_id=11, month="2026-04",
        ).one()
        assert row.notes == "财务调整"
    finally:
        _reset_override()


def test_put_upserts_existing(client, db_session, seed):
    _admin_override()
    try:
        # create
        client.put("/api/bills/adjustment", json={
            "customer_id": 1, "resource_id": 11, "month": "2026-04",
            "discount_rate_override": "10",
        })
        # update same key
        r = client.put("/api/bills/adjustment", json={
            "customer_id": 1, "resource_id": 11, "month": "2026-04",
            "discount_rate_override": "20",
            "surcharge": "5",
            "notes": "改了",
        })
        assert r.status_code == 200
        body = r.json()
        assert Decimal(body["discount_rate_override"]) == Decimal("20.00")
        # 只有一条
        rows = db_session.query(BillAdjustment).all()
        assert len(rows) == 1
    finally:
        _reset_override()


def test_get_list_by_customer(client, seed):
    _admin_override()
    try:
        client.put("/api/bills/adjustment", json={
            "customer_id": 1, "resource_id": 11, "month": "2026-04",
            "discount_rate_override": "15",
        })
        r = client.get("/api/bills/adjustment?customer_id=1&month=2026-04")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["customer_id"] == 1
    finally:
        _reset_override()


def test_delete_adjustment(client, db_session, seed):
    _admin_override()
    try:
        client.put("/api/bills/adjustment", json={
            "customer_id": 1, "resource_id": 11, "month": "2026-04",
            "discount_rate_override": "15",
        })
        assert db_session.query(BillAdjustment).count() == 1
        r = client.delete(
            "/api/bills/adjustment?customer_id=1&resource_id=11&month=2026-04"
        )
        assert r.status_code == 200
        assert r.json()["deleted"] is True
        assert db_session.query(BillAdjustment).count() == 0
    finally:
        _reset_override()


def test_sales_can_only_touch_own_customer(client, db_session):
    """sales 角色只能改自己名下的客户；其他人 403."""
    db_session.add_all([
        SalesUser(id=1, name="Alice", casdoor_user_id="sub-alice", is_active=True),
        SalesUser(id=2, name="Bob", casdoor_user_id="sub-bob", is_active=True),
        Customer(id=100, customer_code="ALICE", customer_name="Alice的客户",
                 customer_status="active", is_deleted=False, sales_user_id=1),
        Customer(id=200, customer_code="BOB", customer_name="Bob的客户",
                 customer_status="active", is_deleted=False, sales_user_id=2),
        Resource(id=50, resource_code="res", resource_type="cloud",
                 cloud_provider="AWS", identifier_field="p",
                 resource_status="active"),
    ])
    db_session.commit()

    app.dependency_overrides[require_auth] = lambda: CurrentUser(
        sub="sub-alice", name="alice", roles=["sales"], raw={},
    )
    try:
        # 改自己的 OK
        r1 = client.put("/api/bills/adjustment", json={
            "customer_id": 100, "resource_id": 50, "month": "2026-04",
            "discount_rate_override": "10",
        })
        assert r1.status_code == 200, r1.text
        # 改别人的 403
        r2 = client.put("/api/bills/adjustment", json={
            "customer_id": 200, "resource_id": 50, "month": "2026-04",
            "discount_rate_override": "10",
        })
        assert r2.status_code == 403
    finally:
        _reset_override()
