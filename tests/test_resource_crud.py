"""Coverage for /api/resources CRUD (legacy code, zero pytest coverage before PR-8)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.resource import Resource
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


def test_create_resource_and_fetch(client):
    r = client.post("/api/resources", json={
        "resource_code": "R-001", "resource_type": "ORIGINAL",
        "cloud_provider": "AZURE", "total_quantity": 100,
        "unit_cost": "120.50", "suggested_price": "180.00",
        "resource_status": "AVAILABLE",
    })
    assert r.status_code == 200, r.text
    rid = r.json()["id"]

    got = client.get(f"/api/resources/{rid}")
    assert got.status_code == 200
    assert got.json()["resource_code"] == "R-001"


def test_create_duplicate_code_rejected(client):
    client.post("/api/resources", json={
        "resource_code": "R-DUP", "resource_type": "ORIGINAL",
        "resource_status": "AVAILABLE",
    })
    r = client.post("/api/resources", json={
        "resource_code": "R-DUP", "resource_type": "OTHER",
        "resource_status": "AVAILABLE",
    })
    assert r.status_code == 400


def test_list_filters(client):
    client.post("/api/resources", json={"resource_code": "A1", "resource_type": "ORIGINAL",
                                         "cloud_provider": "AZURE", "resource_status": "AVAILABLE"})
    client.post("/api/resources", json={"resource_code": "A2", "resource_type": "OTHER",
                                         "cloud_provider": "AWS", "resource_status": "AVAILABLE"})
    client.post("/api/resources", json={"resource_code": "A3", "resource_type": "ORIGINAL",
                                         "cloud_provider": "AZURE", "resource_status": "EXHAUSTED"})

    # type filter
    r = client.get("/api/resources?resource_type=ORIGINAL").json()
    assert r["total"] == 2

    # provider filter
    r = client.get("/api/resources?cloud_provider=AWS").json()
    assert r["total"] == 1

    # status filter
    r = client.get("/api/resources?resource_status=EXHAUSTED").json()
    assert r["total"] == 1


def test_available_quantity_derived(client, db_session):
    # Create resource with total + allocated_quantity
    client.post("/api/resources", json={
        "resource_code": "AQ-1", "resource_type": "ORIGINAL",
        "total_quantity": 100, "resource_status": "AVAILABLE",
    })
    # Directly patch allocated_quantity and verify list shows them
    res = db_session.query(Resource).filter(Resource.resource_code == "AQ-1").first()
    res.allocated_quantity = 30
    res.available_quantity = 70
    db_session.add(res); db_session.commit()

    item = client.get("/api/resources?keyword=AQ").json()["items"][0]
    assert item["allocated_quantity"] == 30
    assert item["available_quantity"] == 70


def test_update_resource(client):
    rid = client.post("/api/resources", json={
        "resource_code": "R-UP", "resource_type": "ORIGINAL",
        "total_quantity": 10, "resource_status": "AVAILABLE",
    }).json()["id"]

    r = client.put(f"/api/resources/{rid}", json={
        "total_quantity": 50, "suggested_price": "99.99",
    })
    assert r.status_code == 200
    assert r.json()["total_quantity"] == 50
    # Numeric column stores with fixed scale (4 decimals)
    from decimal import Decimal
    assert Decimal(r.json()["suggested_price"]) == Decimal("99.99")


def test_available_endpoint(client, db_session):
    client.post("/api/resources", json={
        "resource_code": "AVAIL-1", "resource_type": "ORIGINAL",
        "total_quantity": 100, "resource_status": "AVAILABLE",
    })
    # Mark one as exhausted
    client.post("/api/resources", json={
        "resource_code": "AVAIL-2", "resource_type": "ORIGINAL",
        "total_quantity": 0, "resource_status": "EXHAUSTED",
    })

    r = client.get("/api/resources/available").json()
    # /available returns only AVAILABLE status
    codes = [it["resource_code"] for it in r.get("items", [])]
    assert "AVAIL-1" in codes
    assert "AVAIL-2" not in codes
