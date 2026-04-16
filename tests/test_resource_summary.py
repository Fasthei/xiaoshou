"""Coverage for /api/resources/summary aggregation endpoint."""
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


def test_resource_summary_aggregation(client):
    # 3 AVAILABLE on AZURE, 1 ALLOCATED on AWS, 1 EXHAUSTED on AZURE
    payloads = [
        {"resource_code": "S-1", "resource_type": "ORIGINAL", "cloud_provider": "AZURE",
         "account_name": "az-1", "total_quantity": 100, "resource_status": "AVAILABLE"},
        {"resource_code": "S-2", "resource_type": "ORIGINAL", "cloud_provider": "AZURE",
         "account_name": "az-2", "total_quantity": 50, "resource_status": "AVAILABLE"},
        {"resource_code": "S-3", "resource_type": "ORIGINAL", "cloud_provider": "AZURE",
         "account_name": "az-3", "total_quantity": 200, "resource_status": "AVAILABLE"},
        {"resource_code": "S-4", "resource_type": "ORIGINAL", "cloud_provider": "AWS",
         "account_name": "aws-1", "total_quantity": 30, "resource_status": "ALLOCATED"},
        {"resource_code": "S-5", "resource_type": "ORIGINAL", "cloud_provider": "AZURE",
         "account_name": "az-exh", "total_quantity": 0, "resource_status": "EXHAUSTED"},
    ]
    for p in payloads:
        r = client.post("/api/resources", json=p)
        assert r.status_code == 200, r.text

    r = client.get("/api/resources/summary")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["total"] == 5
    assert data["by_status"]["AVAILABLE"] == 3
    assert data["by_status"]["ALLOCATED"] == 1
    assert data["by_status"]["EXHAUSTED"] == 1

    providers = {row["provider"]: row for row in data["by_provider"]}
    assert providers["AZURE"]["total"] == 4
    assert providers["AWS"]["total"] == 1

    # Top available only contains AVAILABLE status, sorted desc by available_quantity
    top = data["top_available"]
    assert len(top) == 3
    assert top[0]["resource_code"] == "S-3"
    assert top[0]["available_quantity"] == 200
    assert top[1]["resource_code"] == "S-1"
    assert all(t["provider"] == "AZURE" for t in top)
