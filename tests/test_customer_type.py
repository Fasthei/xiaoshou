"""Coverage for customer_type / referrer / channel_notes / end_user_label fields (CLAUDE.md 3.6)."""
from __future__ import annotations

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


def test_create_channel_customer_with_referrer_and_notes(client):
    payload = {
        "customer_code": "CH-001",
        "customer_name": "渠道商A",
        "customer_status": "active",
        "customer_type": "channel",
        "referrer": "合作伙伴 B 推荐",
        "channel_notes": "该渠道服务的终端用户包括: 厂家C, 经销商D",
    }
    r = client.post("/api/customers", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_type"] == "channel"
    assert data["referrer"] == "合作伙伴 B 推荐"
    assert data["channel_notes"].startswith("该渠道服务的")


def test_create_direct_customer_default_type(client):
    payload = {
        "customer_code": "DR-001",
        "customer_name": "直客A",
        "customer_status": "potential",
    }
    r = client.post("/api/customers", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    # customer_type 不传时, 由 DB 默认或 null
    # 我们允许两种情况: 后端给 "direct" 或 null (schema 是 Optional)
    assert data.get("customer_type") in (None, "direct")
    assert data.get("referrer") is None
    assert data.get("channel_notes") is None


def test_allocation_with_end_user_label(client):
    # seed: create channel customer + 1 resource first
    client.post("/api/customers", json={
        "customer_code": "CH-002", "customer_name": "CH2", "customer_status": "active",
        "customer_type": "channel",
    })
    client.post("/api/resources", json={
        "resource_code": "R-1", "resource_type": "ORIGINAL", "cloud_provider": "AWS",
        "account_name": "aws-1", "total_quantity": 100, "resource_status": "AVAILABLE",
    })

    body = {
        "customer_id": 1,
        "resource_id": 1,
        "allocated_quantity": 5,
        "unit_price": 20.0,
        "end_user_label": "终端用户 alpha",
    }
    r = client.post("/api/allocations", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["end_user_label"] == "终端用户 alpha"


def test_update_customer_to_channel(client):
    # create as direct
    r = client.post("/api/customers", json={
        "customer_code": "CH-003", "customer_name": "moved", "customer_status": "active",
    })
    cid = r.json()["id"]
    # PUT to channel
    r = client.put(f"/api/customers/{cid}", json={
        "customer_type": "channel", "referrer": "转介绍 X", "channel_notes": "渠道备忘",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["customer_type"] == "channel"
    assert data["referrer"] == "转介绍 X"
    assert data["channel_notes"] == "渠道备忘"
