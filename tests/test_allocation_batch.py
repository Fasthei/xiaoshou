"""Tests for POST /api/allocations/batch (v2 折扣明细批量创建订单)."""
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
def seed_customer(db_session):
    c = Customer(
        customer_code="BATCH-C1",
        customer_name="批量测试客户",
        customer_status="active",
        is_deleted=False,
        current_resource_count=0,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture()
def seed_resources(db_session):
    r1 = Resource(
        resource_code="BATCH-R1", resource_type="cloud",
        total_quantity=200, allocated_quantity=0, available_quantity=200,
        unit_cost=Decimal("10.00"), resource_status="AVAILABLE", is_deleted=False,
    )
    r2 = Resource(
        resource_code="BATCH-R2", resource_type="cloud",
        total_quantity=200, allocated_quantity=0, available_quantity=200,
        unit_cost=Decimal("20.00"), resource_status="AVAILABLE", is_deleted=False,
    )
    r3 = Resource(
        resource_code="BATCH-R3", resource_type="cloud",
        total_quantity=200, allocated_quantity=0, available_quantity=200,
        unit_cost=Decimal("30.00"), resource_status="AVAILABLE", is_deleted=False,
    )
    db_session.add_all([r1, r2, r3])
    db_session.commit()
    for r in (r1, r2, r3):
        db_session.refresh(r)
    return r1, r2, r3


def test_batch_creates_multi_resource(client, db_session, seed_customer, seed_resources):
    """3 行明细应创建 3 条 allocation，每条带正确的 unit_price 和 discount_rate。

    新口径：
      - discount_rate 必填（不可 None；云后付费下销售下单必须定折扣率）
      - unit_price **可**空（后付费销售不预知单价，账单中心从 cc_usage 反算）
    """
    r1, r2, r3 = seed_resources
    cid = seed_customer.id

    payload = {
        "customer_id": cid,
        "lines": [
            {"resource_id": r1.id, "quantity": 2, "unit_price": "15.00", "discount_rate": "10.00"},
            {"resource_id": r2.id, "quantity": 3, "unit_price": "25.00", "discount_rate": "5.00"},
            # 第 3 行演示 unit_price 可空（后付费）
            {"resource_id": r3.id, "quantity": 1, "discount_rate": "0.00"},
        ],
    }
    r = client.post("/api/allocations/batch", json=payload)
    assert r.status_code == 200, r.text

    body = r.json()
    assert "batch_code" in body
    assert "created" in body
    created = body["created"]
    assert len(created) == 3

    # Verify each line has correct unit_price / discount_rate
    prices = {float(item["unit_price"]) if item["unit_price"] is not None else None for item in created}
    assert 15.0 in prices
    assert 25.0 in prices
    assert None in prices   # 第 3 行 unit_price 可空

    discount_rates = sorted(float(item["discount_rate"]) for item in created)
    assert discount_rates == [0.0, 5.0, 10.0]

    # Verify DB rows
    db_allocs = db_session.query(Allocation).filter(
        Allocation.customer_id == cid
    ).all()
    assert len(db_allocs) == 3


def test_batch_invalid_resource_id_returns_4xx(client, seed_customer):
    """不存在的 resource_id 应返回 4xx 错误。"""
    cid = seed_customer.id
    payload = {
        "customer_id": cid,
        "lines": [
            {"resource_id": 999999, "quantity": 1, "unit_price": "10.00",
             "discount_rate": "0.00"},
        ],
    }
    r = client.post("/api/allocations/batch", json=payload)
    assert r.status_code >= 400, r.text


def test_batch_validates_quantity_ge_1(client, seed_customer, seed_resources):
    """quantity=0 应返回 422 (schema validation error)。"""
    r1 = seed_resources[0]
    cid = seed_customer.id
    payload = {
        "customer_id": cid,
        "lines": [
            {"resource_id": r1.id, "quantity": 0, "unit_price": "10.00",
             "discount_rate": "0.00"},
        ],
    }
    r = client.post("/api/allocations/batch", json=payload)
    assert r.status_code == 422, r.text


def test_batch_discount_rate_required(client, seed_customer, seed_resources):
    """新口径：discount_rate 必填；省略或 null 应返回 422。"""
    r1 = seed_resources[0]
    payload = {
        "customer_id": seed_customer.id,
        "lines": [
            {"resource_id": r1.id, "quantity": 1, "unit_price": "10.00"},
        ],
    }
    r = client.post("/api/allocations/batch", json=payload)
    assert r.status_code == 422, r.text


def test_batch_total_cost_calculation_with_discount(client, db_session, seed_customer, seed_resources):
    """折扣率 10% 时，total_price = unit_price * quantity，total_cost 正确计算。

    resource unit_cost=10, 下单 quantity=5, unit_price=18 (折后), discount_rate=10
    expected total_price = 18 * 5 = 90
    expected total_cost  = 10 * 5 = 50  (基于 resource.unit_cost)
    """
    r1 = seed_resources[0]  # unit_cost=10
    cid = seed_customer.id

    payload = {
        "customer_id": cid,
        "lines": [
            {
                "resource_id": r1.id,
                "quantity": 5,
                "unit_price": "18.00",
                "discount_rate": "10.00",
            }
        ],
    }
    resp = client.post("/api/allocations/batch", json=payload)
    assert resp.status_code == 200, resp.text

    item = resp.json()["created"][0]
    assert float(item["total_price"]) == pytest.approx(90.0)
    assert float(item["total_cost"]) == pytest.approx(50.0)
    assert float(item["discount_rate"]) == pytest.approx(10.0)
