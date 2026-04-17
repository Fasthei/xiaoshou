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
    # 新语义: by_provider 每项不再带 allocated/available/rate, 改成按 status 分桶
    assert "allocated" not in providers["AZURE"]
    assert "allocation_rate" not in providers["AZURE"]
    assert providers["AZURE"]["by_status"]["AVAILABLE"] == 3
    assert providers["AZURE"]["by_status"]["EXHAUSTED"] == 1
    assert providers["AWS"]["by_status"]["ALLOCATED"] == 1

    # Top available 只筛 AVAILABLE, 不返回 available_quantity (云管没这字段)
    top = data["top_available"]
    assert len(top) == 3  # 只 3 条 AVAILABLE (S-1, S-2, S-3)
    assert all(t["provider"] == "AZURE" for t in top)
    codes = {t["resource_code"] for t in top}
    assert codes == {"S-1", "S-2", "S-3"}
    # 不应再暴露本地凑的 quantity 字段
    assert "available_quantity" not in top[0]
    assert "allocated_quantity" not in top[0]

    # 口径一致性不变量: 顶部 KPI 可用数 == sum(by_provider[*].available) == by_status.AVAILABLE
    assert data["available"] == data["by_status"]["AVAILABLE"]
    assert sum(p["available"] for p in data["by_provider"]) == data["by_status"]["AVAILABLE"]
    assert providers["AZURE"]["available"] == 3
    assert providers["AWS"]["available"] == 0


def test_resource_summary_empty_state(client):
    """空库也要返回一致口径 (available = 0)."""
    r = client.get("/api/resources/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["available"] == 0
    assert data["by_provider"] == []
    assert data["top_available"] == []
