"""Coverage for POST /api/orders — 多货源 + 合同一体化 (CLAUDE.md 3.1)."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
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


def _seed_resources(client, n=2):
    """Create n resources each with total_quantity=100 AVAILABLE."""
    ids = []
    for i in range(1, n + 1):
        r = client.post("/api/resources", json={
            "resource_code": f"R-{i}",
            "resource_type": "cloud",
            "cloud_provider": "AWS",
            "account_name": f"aws-{i}",
            "total_quantity": 100,
            "unit_cost": 5.0,
            "resource_status": "AVAILABLE",
        })
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    return ids


def test_create_order_with_new_customer_and_two_resources(client):
    r_ids = _seed_resources(client, 2)
    payload_customer = {
        "customer_code": "ORD-CUST-1",
        "customer_name": "新建订单客户 A",
        "customer_type": "channel",
        "referrer": "老客户 X 转介绍",
        "channel_notes": "终端用户是 A 厂",
        "customer_status": "potential",
    }
    resources = [
        {"resource_id": r_ids[0], "quantity": 3, "unit_price": 10.0, "end_user_label": "终端 alpha"},
        {"resource_id": r_ids[1], "quantity": 2, "unit_price": 20.0, "end_user_label": "终端 beta"},
    ]
    form = {
        "customer_json": json.dumps(payload_customer),
        "resources_json": json.dumps(resources),
        "contract_code": "CN-TEST-1",
        "contract_title": "测试合同",
        "contract_amount": "50000.00",
    }
    r = client.post("/api/orders", data=form)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_code"] == "ORD-CUST-1"
    assert len(data["allocation_ids"]) == 2
    assert data["contract_id"] is not None
    assert data["approval_status"] == "pending"


def test_create_order_with_existing_customer_single_resource(client):
    # seed customer directly
    cr = client.post("/api/customers", json={
        "customer_code": "EXIST-1",
        "customer_name": "已存在客户",
        "customer_status": "active",
    })
    cid = cr.json()["id"]
    r_ids = _seed_resources(client, 1)

    form = {
        "customer_id": str(cid),
        "resources_json": json.dumps([
            {"resource_id": r_ids[0], "quantity": 1, "unit_price": 15.0},
        ]),
    }
    r = client.post("/api/orders", data=form)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_id"] == cid
    assert len(data["allocation_ids"]) == 1
    # 未传合同信息, 合同应为空
    assert data["contract_id"] is None
    assert data["approval_status"] == "pending"


def test_create_order_rejects_empty_resources(client):
    form = {
        "customer_json": json.dumps({
            "customer_code": "XY-1", "customer_name": "XY", "customer_status": "potential",
        }),
        "resources_json": json.dumps([]),
    }
    r = client.post("/api/orders", data=form)
    assert r.status_code == 400
    assert "至少" in r.json().get("detail", "")


def test_create_order_rejects_missing_customer_info(client):
    form = {"resources_json": json.dumps([{"resource_id": 1, "quantity": 1}])}
    r = client.post("/api/orders", data=form)
    assert r.status_code == 400
    assert "customer" in r.json().get("detail", "")
