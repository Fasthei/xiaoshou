"""Tests for /api/bills/by-customer (本地聚合)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.cc_bill import CCBill
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
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
def seed(db_session):
    c1 = Customer(id=1, customer_code="C001", customer_name="福星",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    c2 = Customer(id=2, customer_code="C002", customer_name="空客户",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    r1 = Resource(id=5, resource_code="res-azure-1", resource_type="ORIGINAL",
                  cloud_provider="AZURE", account_name="ocid-prod", resource_status="active")
    r2 = Resource(id=8, resource_code="res-aws-1", resource_type="ORIGINAL",
                  cloud_provider="AWS", account_name="aws-main", resource_status="active")
    link1 = CustomerResource(customer_id=1, resource_id=5)
    link2 = CustomerResource(customer_id=1, resource_id=8)
    b1 = CCBill(remote_id=1, month="2026-04", provider="AZURE",
                original_cost=Decimal("800"), final_cost=Decimal("800.00"),
                status="confirmed", customer_code="C001")
    b2 = CCBill(remote_id=2, month="2026-04", provider="AWS",
                original_cost=Decimal("434.56"), final_cost=Decimal("434.56"),
                status="confirmed", customer_code="C001")
    # cc_usage for day drill
    u1 = CCUsage(customer_code="C001", date=date(2026, 4, 1),
                 total_cost=Decimal("100.00"), total_usage=Decimal("10"), record_count=5)
    u2 = CCUsage(customer_code="C001", date=date(2026, 4, 2),
                 total_cost=Decimal("200.00"), total_usage=Decimal("20"), record_count=8)
    for x in (c1, c2, r1, r2, link1, link2, b1, b2, u1, u2):
        db_session.add(x)
    db_session.commit()


def test_by_customer_aggregates_linked_resources(client, seed):
    r = client.get("/api/bills/by-customer?month=2026-04")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1  # C002 has no links, excluded
    row = data[0]
    assert row["customer_id"] == 1
    assert row["customer_name"] == "福星"
    assert row["resource_count"] == 2
    assert row["total_cost"] == 1234.56
    res_map = {x["resource_id"]: x for x in row["resources"]}
    assert res_map[5]["cost"] == 800.00
    assert res_map[8]["cost"] == 434.56
    assert res_map[5]["cloud_provider"] == "AZURE"


def test_by_customer_empty_month(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12")
    assert r.status_code == 200
    # has links but no bills and no usage -> excluded by default
    assert r.json() == []


def test_by_customer_include_empty(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12&include_empty=true")
    assert r.status_code == 200
    data = r.json()
    # both customers returned, but C002 has no resources
    ids = {row["customer_id"] for row in data}
    assert 1 in ids


def test_drill_down_by_resource(client, seed):
    r = client.get("/api/bills/by-customer/1?month=2026-04&granularity=resource")
    assert r.status_code == 200
    data = r.json()
    assert data["granularity"] == "resource"
    assert data["total_cost"] == 1234.56
    assert len(data["items"]) == 2


def test_drill_down_by_day(client, seed):
    r = client.get("/api/bills/by-customer/1?month=2026-04&granularity=day")
    assert r.status_code == 200
    data = r.json()
    assert data["granularity"] == "day"
    assert data["total_cost"] == 300.00
    assert len(data["items"]) == 2
    assert data["items"][0]["date"] == "2026-04-01"


def test_drill_down_404_for_unknown_customer(client, seed):
    r = client.get("/api/bills/by-customer/999?month=2026-04")
    assert r.status_code == 404


def test_rejects_bad_month(client, seed):
    r = client.get("/api/bills/by-customer?month=not-a-month")
    assert r.status_code == 422


def test_by_customer_export_csv(client, seed):
    r = client.get("/api/bills/by-customer-export?month=2026-04")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "福星" in text
    assert "res-azure-1" in text
    assert "res-aws-1" in text
