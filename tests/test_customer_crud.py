"""Coverage for /api/customers CRUD + contacts + list filters.

Backfill tests for legacy code that had zero pytest coverage before PR-6.
"""
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


def test_create_customer_and_fetch(client):
    r = client.post("/api/customers", json={
        "customer_code": "C-1", "customer_name": "酷睿科技",
        "customer_status": "potential", "industry": "AI",
    })
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    r = client.get(f"/api/customers/{cid}")
    assert r.status_code == 200
    assert r.json()["customer_name"] == "酷睿科技"


def test_create_customer_duplicate_code_rejected(client):
    client.post("/api/customers", json={
        "customer_code": "C-DUP", "customer_name": "First", "customer_status": "active",
    })
    r = client.post("/api/customers", json={
        "customer_code": "C-DUP", "customer_name": "Second", "customer_status": "active",
    })
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]


def test_update_customer(client):
    cid = client.post("/api/customers", json={
        "customer_code": "C-UP", "customer_name": "Old", "customer_status": "potential",
    }).json()["id"]

    r = client.put(f"/api/customers/{cid}", json={"customer_name": "New", "industry": "金融"})
    assert r.status_code == 200
    assert r.json()["customer_name"] == "New"
    assert r.json()["industry"] == "金融"


def test_list_filters(client):
    client.post("/api/customers", json={"customer_code": "A1", "customer_name": "AI1", "customer_status": "active", "industry": "AI"})
    client.post("/api/customers", json={"customer_code": "A2", "customer_name": "金融1", "customer_status": "active", "industry": "金融"})
    client.post("/api/customers", json={"customer_code": "A3", "customer_name": "AI2", "customer_status": "potential", "industry": "AI"})

    # industry filter
    r = client.get("/api/customers?industry=AI").json()
    assert r["total"] == 2

    # status filter
    r = client.get("/api/customers?customer_status=potential").json()
    assert r["total"] == 1

    # keyword
    r = client.get("/api/customers?keyword=金融").json()
    assert r["total"] == 1


def test_update_nonexistent_customer_404(client):
    r = client.put("/api/customers/99999", json={"customer_name": "x"})
    assert r.status_code == 404


def test_add_contact(client):
    cid = client.post("/api/customers", json={
        "customer_code": "C-CT", "customer_name": "With contacts", "customer_status": "active",
    }).json()["id"]

    r = client.post(f"/api/customers/{cid}/contacts", json={
        "contact_name": "张三", "contact_phone": "13888888888", "is_primary": True,
    })
    assert r.status_code == 200
    assert r.json()["contact_name"] == "张三"


def test_pagination(client):
    for i in range(25):
        client.post("/api/customers", json={
            "customer_code": f"P{i}", "customer_name": f"P{i}", "customer_status": "active",
        })

    r = client.get("/api/customers?page=1&page_size=10").json()
    assert r["total"] == 25
    assert len(r["items"]) == 10

    r = client.get("/api/customers?page=3&page_size=10").json()
    assert len(r["items"]) == 5
