"""Global follow-up list endpoint tests."""
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
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
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


def test_global_follow_ups_returns_all(client, db_session):
    """两个客户各加一条跟进，全局接口返回 total=2。"""
    cid1 = client.post("/api/customers", json={
        "customer_code": "GFU-1", "customer_name": "全局客户甲", "customer_status": "active",
    }).json()["id"]
    cid2 = client.post("/api/customers", json={
        "customer_code": "GFU-2", "customer_name": "全局客户乙", "customer_status": "active",
    }).json()["id"]

    client.post(f"/api/customers/{cid1}/follow-ups", json={
        "kind": "call", "title": "电话1", "content": "沟通产品方案",
    })
    client.post(f"/api/customers/{cid2}/follow-ups", json={
        "kind": "email", "title": "邮件1", "content": "发送报价单",
    })

    r = client.get("/api/follow-ups?days=30")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_global_follow_ups_filter_by_customer(client, db_session):
    """按 customer_id 过滤只返回该客户的跟进。"""
    cid1 = client.post("/api/customers", json={
        "customer_code": "GFU-A", "customer_name": "过滤甲", "customer_status": "active",
    }).json()["id"]
    cid2 = client.post("/api/customers", json={
        "customer_code": "GFU-B", "customer_name": "过滤乙", "customer_status": "active",
    }).json()["id"]

    client.post(f"/api/customers/{cid1}/follow-ups", json={
        "kind": "note", "title": "甲的备注",
    })
    client.post(f"/api/customers/{cid2}/follow-ups", json={
        "kind": "note", "title": "乙的备注",
    })

    r = client.get(f"/api/follow-ups?days=30&customer_id={cid1}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_id"] == cid1
    assert data["items"][0]["customer_name"] == "过滤甲"
