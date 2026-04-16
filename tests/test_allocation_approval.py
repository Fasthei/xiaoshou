"""Allocation approval workflow: default status, PATCH /approval, status filter."""
from __future__ import annotations

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
def seed_customer_resource(db_session):
    c = Customer(id=1, customer_code="C1", customer_name="Test",
                 customer_status="active", is_deleted=False,
                 current_resource_count=0)
    r = Resource(id=1, resource_code="R1", resource_type="vm",
                 resource_status="available",
                 total_quantity=100, allocated_quantity=0, available_quantity=100,
                 unit_cost=Decimal("10"), is_deleted=False)
    db_session.add(c)
    db_session.add(r)
    db_session.commit()
    return c, r


@pytest.fixture()
def seed_sales_user(db_session):
    # AUTH_ENABLED=false so require_auth returns CurrentUser(sub="dev").
    # Mirror that sub in a SalesUser row so the API can map it to sales_user.id.
    su = SalesUser(id=42, name="dev-approver", casdoor_user_id="dev", is_active=True)
    db_session.add(su)
    db_session.commit()
    return su


def _create_allocation(client):
    body = {
        "customer_id": 1,
        "resource_id": 1,
        "allocated_quantity": 5,
        "unit_price": 20,
        "remark": "t",
    }
    r = client.post("/api/allocations", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_allocation_defaults_to_pending(client, seed_customer_resource):
    data = _create_allocation(client)
    assert data["approval_status"] == "pending"
    assert data["approver_id"] is None
    assert data["approved_at"] is None
    assert data["approval_note"] is None


def test_patch_approval_sets_fields(client, seed_customer_resource, seed_sales_user):
    created = _create_allocation(client)
    alloc_id = created["id"]

    r = client.patch(
        f"/api/allocations/{alloc_id}/approval",
        json={"approval_status": "approved", "approval_note": "looks good"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approval_status"] == "approved"
    assert body["approval_note"] == "looks good"
    assert body["approver_id"] == 42
    assert body["approved_at"] is not None


def test_patch_approval_rejected(client, seed_customer_resource, seed_sales_user):
    created = _create_allocation(client)
    alloc_id = created["id"]

    r = client.patch(
        f"/api/allocations/{alloc_id}/approval",
        json={"approval_status": "rejected", "approval_note": "missing info"},
    )
    assert r.status_code == 200
    assert r.json()["approval_status"] == "rejected"


def test_patch_approval_rejects_invalid_status(client, seed_customer_resource):
    created = _create_allocation(client)
    alloc_id = created["id"]

    r = client.patch(
        f"/api/allocations/{alloc_id}/approval",
        json={"approval_status": "maybe"},
    )
    assert r.status_code == 400


def test_list_filter_by_approval_status(client, seed_customer_resource, seed_sales_user):
    # Create 3 allocations; approve 1, reject 1, leave 1 pending.
    a1 = _create_allocation(client)
    a2 = _create_allocation(client)
    a3 = _create_allocation(client)

    client.patch(f"/api/allocations/{a1['id']}/approval",
                 json={"approval_status": "approved"})
    client.patch(f"/api/allocations/{a2['id']}/approval",
                 json={"approval_status": "rejected"})

    r = client.get("/api/allocations?approval_status=pending").json()
    assert r["total"] == 1
    assert r["items"][0]["id"] == a3["id"]

    r = client.get("/api/allocations?approval_status=approved").json()
    assert r["total"] == 1
    assert r["items"][0]["id"] == a1["id"]

    r = client.get("/api/allocations?approval_status=rejected").json()
    assert r["total"] == 1
    assert r["items"][0]["id"] == a2["id"]
