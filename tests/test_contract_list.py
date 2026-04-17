"""Coverage for GET /api/contracts (global list + pagination + filtering)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from app.models.contract import Contract
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


def _mk_customer(db, name: str, code: str) -> Customer:
    c = Customer(customer_name=name, customer_code=code, customer_status="active")
    db.add(c); db.commit(); db.refresh(c)
    return c


def _mk_contract(db, customer_id: int, code: str, title: str = "", status: str = "active") -> Contract:
    row = Contract(customer_id=customer_id, contract_code=code, title=title, status=status)
    db.add(row); db.commit(); db.refresh(row)
    return row


def test_contract_list_empty(client):
    r = client.get("/api/contracts")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_contract_list_pagination_and_filter(client, db_session):
    cust_a = _mk_customer(db_session, "客户A", "CA")
    cust_b = _mk_customer(db_session, "客户B", "CB")

    # 5 active contracts under A, 2 expired under B
    for i in range(5):
        _mk_contract(db_session, cust_a.id, f"A-{i}", title=f"年框-{i}", status="active")
    for i in range(2):
        _mk_contract(db_session, cust_b.id, f"B-{i}", title=f"测试-{i}", status="expired")

    # Full list
    r = client.get("/api/contracts")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 7
    assert len(data["items"]) == 7

    # Pagination
    r = client.get("/api/contracts?page=1&page_size=3")
    assert r.json()["total"] == 7
    assert len(r.json()["items"]) == 3
    r = client.get("/api/contracts?page=3&page_size=3")
    assert len(r.json()["items"]) == 1

    # filter by customer_id
    r = client.get(f"/api/contracts?customer_id={cust_b.id}")
    d = r.json()
    assert d["total"] == 2
    assert all(it["customer_id"] == cust_b.id for it in d["items"])

    # filter by status
    r = client.get("/api/contracts?status=expired")
    assert r.json()["total"] == 2

    # keyword: contract_code
    r = client.get("/api/contracts?keyword=A-1")
    d = r.json()
    assert d["total"] == 1
    assert d["items"][0]["contract_code"] == "A-1"

    # keyword: title substring
    r = client.get("/api/contracts?keyword=测试")
    assert r.json()["total"] == 2
