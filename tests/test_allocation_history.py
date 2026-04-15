"""Allocation cancel + history streaming."""
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
        try: yield s
        finally: pass
    app.dependency_overrides[get_db] = override
    try: yield s
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


@pytest.fixture()
def seed(db_session):
    c = Customer(id=1, customer_code="C1", customer_name="Test", customer_status="active",
                 is_deleted=False, current_resource_count=0)
    r = Resource(id=1, resource_code="R1", resource_type="vm", resource_status="available",
                 total_quantity=100, allocated_quantity=10, available_quantity=90,
                 unit_cost=Decimal("10"), is_deleted=False)
    a = Allocation(id=1, allocation_code="A1", customer_id=1, resource_id=1,
                   allocated_quantity=10, unit_cost=Decimal("10"), unit_price=Decimal("15"),
                   total_cost=Decimal("100"), total_price=Decimal("150"),
                   profit_amount=Decimal("50"), profit_rate=Decimal("50"),
                   allocation_status="PENDING", is_deleted=False)
    for x in (c, r, a): db_session.add(x)
    db_session.commit()
    return a


def test_update_creates_history_entries(client, seed, db_session):
    # PATCH-style update (PUT in allocation API) changes quantity & price
    r = client.put("/api/allocations/1", json={"allocated_quantity": 5, "unit_price": 20})
    assert r.status_code == 200, r.text

    hist = client.get("/api/allocations/1/history").json()
    fields = {h["field"] for h in hist}
    assert "allocated_quantity" in fields
    assert "unit_price" in fields
    # old→new captured
    q = [h for h in hist if h["field"] == "allocated_quantity"][0]
    assert q["old_value"] == "10" and q["new_value"] == "5"


def test_cancel_marks_cancelled_and_returns_resource(client, seed, db_session):
    r = client.post("/api/allocations/1/cancel", json={"reason": "客户退单"})
    assert r.status_code == 200
    assert r.json()["allocation_status"] == "CANCELLED"

    db_session.expire_all()
    alloc = db_session.query(Allocation).get(1)
    assert alloc.allocation_status == "CANCELLED"

    # resource allocated_quantity 减回 10
    res = db_session.query(Resource).get(1)
    assert int(res.allocated_quantity) == 0
    assert int(res.available_quantity) == 100

    # history has cancel entry with reason
    hist = client.get("/api/allocations/1/history").json()
    cancel_entries = [h for h in hist if h["field"] == "cancel"]
    assert len(cancel_entries) == 1
    assert cancel_entries[0]["old_value"] == "PENDING"
    assert cancel_entries[0]["new_value"] == "CANCELLED"
    assert cancel_entries[0]["reason"] == "客户退单"


def test_cancel_already_cancelled_rejected(client, seed, db_session):
    client.post("/api/allocations/1/cancel", json={"reason": "first"})
    r = client.post("/api/allocations/1/cancel", json={"reason": "second"})
    assert r.status_code == 400


def test_list_allocations_by_status(client, seed, db_session):
    # current is PENDING
    r = client.get("/api/allocations?allocation_status=PENDING").json()
    assert r["total"] == 1

    client.post("/api/allocations/1/cancel", json={"reason": "x"})

    # PENDING count drops
    r = client.get("/api/allocations?allocation_status=PENDING").json()
    assert r["total"] == 0

    # CANCELLED count
    r = client.get("/api/allocations?allocation_status=CANCELLED").json()
    assert r["total"] == 1
