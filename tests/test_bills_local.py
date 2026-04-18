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
    """账单聚合 fixture — 遵守新的 join 语义：
       customer → customer_resource → resource.identifier_field → cc_bill/cc_usage
    """
    c1 = Customer(id=1, customer_code="C001", customer_name="福星",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    c2 = Customer(id=2, customer_code="C002", customer_name="空客户",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    # resource.identifier_field 是云管 external_project_id，和 cc_bill.customer_code 一致
    r1 = Resource(id=5, resource_code="res-azure-1", resource_type="ORIGINAL",
                  cloud_provider="AZURE", account_name="ocid-prod",
                  identifier_field="proj-azure-001",
                  resource_status="active")
    r2 = Resource(id=8, resource_code="res-aws-1", resource_type="ORIGINAL",
                  cloud_provider="AWS", account_name="aws-main",
                  identifier_field="proj-aws-001",
                  resource_status="active")
    link1 = CustomerResource(customer_id=1, resource_id=5)
    link2 = CustomerResource(customer_id=1, resource_id=8)
    # cc_bill.customer_code 对齐到 resource.identifier_field
    b1 = CCBill(remote_id=1, month="2026-04", provider="AZURE",
                original_cost=Decimal("800"), final_cost=Decimal("800.00"),
                status="confirmed", customer_code="proj-azure-001")
    b2 = CCBill(remote_id=2, month="2026-04", provider="AWS",
                original_cost=Decimal("434.56"), final_cost=Decimal("434.56"),
                status="confirmed", customer_code="proj-aws-001")
    # cc_usage for day drill — 两条分别落在各自 identifier 上
    u1 = CCUsage(customer_code="proj-azure-001", date=date(2026, 4, 1),
                 total_cost=Decimal("100.00"), total_usage=Decimal("10"), record_count=5)
    u2 = CCUsage(customer_code="proj-aws-001", date=date(2026, 4, 2),
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


def test_by_customer_exposes_original_and_final_with_discount(client, db_session):
    """硬规则：每个货源行与客户汇总都要同时带原价、折扣率、折后价。"""
    c = Customer(id=10, customer_code="DISC", customer_name="折扣客户",
                 customer_status="active", lifecycle_stage="active", is_deleted=False)
    r = Resource(id=20, resource_code="res-disc", resource_type="ORIGINAL",
                 cloud_provider="AZURE", identifier_field="proj-disc-1",
                 resource_status="active")
    link = CustomerResource(customer_id=10, resource_id=20)
    # original 1000, final 750 → discount 25%
    b = CCBill(remote_id=100, month="2026-04", provider="AZURE",
               original_cost=Decimal("1000"), final_cost=Decimal("750"),
               status="confirmed", customer_code="proj-disc-1")
    for x in (c, r, link, b):
        db_session.add(x)
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    assert r_resp.status_code == 200
    row = next(x for x in r_resp.json() if x["customer_id"] == 10)
    # customer 级三元组
    assert row["total_original_cost"] == 1000.0
    assert row["total_final_cost"] == 750.0
    assert row["total_discount_rate"] == 0.25
    assert row["total_cost"] == 750.0  # 向后兼容别名
    # resource 级三元组
    res = row["resources"][0]
    assert res["original_cost"] == 1000.0
    assert res["final_cost"] == 750.0
    assert res["discount_rate"] == 0.25

    # 单客户下钻也要同三元组
    detail = client.get(
        f"/api/bills/by-customer/10?month=2026-04&granularity=resource",
    ).json()
    assert detail["total_original_cost"] == 1000.0
    assert detail["total_final_cost"] == 750.0
    assert detail["total_discount_rate"] == 0.25
    assert detail["items"][0]["discount_rate"] == 0.25


def test_customer_without_allocation_sees_nothing_even_if_code_matches(client, db_session):
    """业务规则 #3：无销售分配关系时，云管数据不归入该客户（哪怕 code 巧合）。"""
    c = Customer(id=30, customer_code="ACME", customer_name="ACME",
                 customer_status="active", is_deleted=False)
    # 故意不建 customer_resource；cc_bill.customer_code 巧和 customer.customer_code 同
    db_session.add(c)
    db_session.add(CCBill(
        remote_id=900, month="2026-04", provider="AZURE",
        original_cost=Decimal("1000"), final_cost=Decimal("900"),
        status="confirmed", customer_code="ACME",
    ))
    db_session.commit()
    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    assert r_resp.status_code == 200
    ids = {x["customer_id"] for x in r_resp.json()}
    assert 30 not in ids, "未分配的客户不应看到任何账单"


def test_by_customer_export_csv(client, seed):
    r = client.get("/api/bills/by-customer-export?month=2026-04")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "福星" in text
    assert "res-azure-1" in text
    assert "res-aws-1" in text
