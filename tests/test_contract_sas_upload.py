"""Tests for SAS direct-upload endpoints.

Coverage:
- GET /api/contracts/{id}/upload-url → returns sas_url + blob_name (monkeypatched)
- GET /api/contracts/{id}/upload-url → 503 when Azure not configured
- GET /api/contracts/{id}/upload-url → 400 for unsupported file type
- GET /api/contracts/{id}/upload-url → 404 for missing contract
- POST /api/contracts/{id}/upload-confirm → contract.file_url updated
- POST /api/contracts/{id}/upload-confirm → 503 when Azure not configured
- POST /api/contracts/{id}/upload-confirm → 422 when blob does not exist yet
- POST /api/contracts/{id}/upload-confirm → 404 for missing contract
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.contract import Contract
from app.models.customer import Customer
from main import app


# ---------------------------------------------------------------------------
# Fixtures (same pattern as test_contract_upload.py)
# ---------------------------------------------------------------------------

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
def seeded_contract(db_session) -> Contract:
    """One customer + one contract, ready for upload tests."""
    customer = Customer(
        customer_name="测试客户SAS",
        customer_code="TC-SAS-001",
        customer_status="active",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    contract = Contract(
        customer_id=customer.id,
        contract_code="CT-SAS-001",
        title="SAS测试合同",
        status="active",
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    return contract


# ---------------------------------------------------------------------------
# GET /upload-url tests
# ---------------------------------------------------------------------------

def test_get_upload_url_success(client, seeded_contract, monkeypatch):
    """Returns sas_url and blob_name when Azure is configured."""
    import app.integrations.azure_blob as blob_mod

    fake_expires = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    fake_sas_url = "https://account.blob.core.windows.net/xiaoshou-contracts/contract/1/abc.pdf?sig=xxx"

    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    monkeypatch.setattr(
        blob_mod,
        "generate_upload_sas",
        lambda blob_name, content_type, ttl_minutes=15: (fake_sas_url, fake_expires),
    )

    resp = client.get(
        f"/api/contracts/{seeded_contract.id}/upload-url",
        params={"filename": "contract.pdf", "content_type": "application/pdf"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sas_url"] == fake_sas_url
    assert "blob_name" in body
    assert body["blob_name"].startswith(f"contract/{seeded_contract.id}/")
    assert body["blob_name"].endswith("contract.pdf")
    assert "expires_at" in body


def test_get_upload_url_not_configured(client, seeded_contract, monkeypatch):
    """Returns 503 when Azure Blob Storage is not configured."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: False)

    resp = client.get(
        f"/api/contracts/{seeded_contract.id}/upload-url",
        params={"filename": "contract.pdf", "content_type": "application/pdf"},
    )

    assert resp.status_code == 503, resp.text
    assert "Azure Blob Storage" in resp.json()["detail"]


def test_get_upload_url_unsupported_type(client, seeded_contract, monkeypatch):
    """Returns 400 for unsupported file types."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = client.get(
        f"/api/contracts/{seeded_contract.id}/upload-url",
        params={"filename": "virus.exe", "content_type": "application/octet-stream"},
    )

    assert resp.status_code == 400, resp.text
    assert "不支持的文件类型" in resp.json()["detail"]


def test_get_upload_url_contract_not_found(client, monkeypatch):
    """Returns 404 when contract does not exist."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = client.get(
        "/api/contracts/999999/upload-url",
        params={"filename": "contract.pdf", "content_type": "application/pdf"},
    )

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# POST /upload-confirm tests
# ---------------------------------------------------------------------------

def test_upload_confirm_success(client, seeded_contract, db_session, monkeypatch):
    """Contract.file_url is updated after a successful confirm."""
    import app.integrations.azure_blob as blob_mod

    fake_blob_name = f"contract/{seeded_contract.id}/abc-contract.pdf"
    fake_file_url = f"https://account.blob.core.windows.net/xiaoshou-contracts/{fake_blob_name}"

    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    monkeypatch.setattr(blob_mod, "head_blob", lambda name: True)
    monkeypatch.setattr(blob_mod, "blob_url", lambda name: fake_file_url)
    monkeypatch.setattr(blob_mod, "delete_blob", lambda url: None)

    resp = client.post(
        f"/api/contracts/{seeded_contract.id}/upload-confirm",
        json={
            "blob_name": fake_blob_name,
            "file_size": 12345,
            "content_type": "application/pdf",
            "file_name": "contract.pdf",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_url"] == fake_file_url
    assert body["file_size"] == 12345
    assert body["mime_type"] == "application/pdf"

    # Verify DB was actually updated
    db_session.expire_all()
    refreshed = db_session.query(Contract).filter(Contract.id == seeded_contract.id).first()
    assert refreshed.file_url == fake_file_url
    assert refreshed.file_name == "contract.pdf"
    assert refreshed.file_size == 12345


def test_upload_confirm_not_configured(client, seeded_contract, monkeypatch):
    """Returns 503 when Azure Blob Storage is not configured."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: False)

    resp = client.post(
        f"/api/contracts/{seeded_contract.id}/upload-confirm",
        json={"blob_name": "contract/1/abc.pdf"},
    )

    assert resp.status_code == 503, resp.text
    assert "Azure Blob Storage" in resp.json()["detail"]


def test_upload_confirm_blob_not_yet_uploaded(client, seeded_contract, monkeypatch):
    """Returns 422 when blob does not yet exist in Azure (upload incomplete)."""
    import app.integrations.azure_blob as blob_mod

    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    monkeypatch.setattr(blob_mod, "head_blob", lambda name: False)

    resp = client.post(
        f"/api/contracts/{seeded_contract.id}/upload-confirm",
        json={"blob_name": "contract/1/missing.pdf"},
    )

    assert resp.status_code == 422, resp.text
    assert "尚不存在" in resp.json()["detail"]


def test_upload_confirm_contract_not_found(client, monkeypatch):
    """Returns 404 when contract does not exist."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = client.post(
        "/api/contracts/999999/upload-confirm",
        json={"blob_name": "contract/999999/abc.pdf"},
    )

    assert resp.status_code == 404, resp.text
