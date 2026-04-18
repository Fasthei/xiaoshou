"""Tests for POST /api/contracts/{contract_id}/upload endpoint.

Coverage:
- 503 when Azure Blob Storage is not configured
- 400 when an unsupported file type is uploaded (e.g. .exe)
- 400 when an empty file is uploaded
- 413 when a file exceeding 10 MB is uploaded
- 200 success path with monkeypatched blob helpers, verifying file_url is persisted
"""
from __future__ import annotations

import io

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
# Fixtures
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
    """Create one customer + one contract ready for upload tests."""
    customer = Customer(
        customer_name="测试客户",
        customer_code="TC001",
        customer_status="active",
    )
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)

    contract = Contract(
        customer_id=customer.id,
        contract_code="CT-TEST-001",
        title="测试合同",
        status="active",
    )
    db_session.add(contract)
    db_session.commit()
    db_session.refresh(contract)
    return contract


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _upload(client, contract_id: int, *, filename: str, content: bytes, content_type: str):
    return client.post(
        f"/api/contracts/{contract_id}/upload",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_upload_contract_file_blob_not_configured(client, seeded_contract, monkeypatch):
    """Returns 503 when AZURE_STORAGE_CONNECTION_STRING is not set."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: False)

    resp = _upload(
        client,
        seeded_contract.id,
        filename="contract.pdf",
        content=b"%PDF-1.4 minimal pdf content",
        content_type="application/pdf",
    )

    assert resp.status_code == 503, resp.text
    assert "Azure Blob Storage" in resp.json()["detail"]


def test_upload_contract_invalid_file_type(client, seeded_contract, monkeypatch):
    """Returns 400 when the uploaded file has an unsupported extension/MIME type."""
    import app.integrations.azure_blob as blob_mod
    # Even if blob were configured, validation should happen first
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = _upload(
        client,
        seeded_contract.id,
        filename="malware.exe",
        content=b"MZ\x90\x00fake exe content",
        content_type="application/octet-stream",
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert "不支持的文件类型" in detail


def test_upload_contract_empty_file(client, seeded_contract, monkeypatch):
    """Returns 400 when the uploaded file has zero bytes."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = _upload(
        client,
        seeded_contract.id,
        filename="empty.pdf",
        content=b"",
        content_type="application/pdf",
    )

    assert resp.status_code == 400, resp.text
    assert "空" in resp.json()["detail"]


def test_upload_contract_too_large(client, seeded_contract, monkeypatch):
    """Returns 413 when the uploaded file exceeds the 10 MB hard cap."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    ten_mb_plus_one = b"x" * (10 * 1024 * 1024 + 1)
    resp = _upload(
        client,
        seeded_contract.id,
        filename="huge.pdf",
        content=ten_mb_plus_one,
        content_type="application/pdf",
    )

    assert resp.status_code == 413, resp.text
    assert "10MB" in resp.json()["detail"]


def test_upload_contract_success_updates_file_url(client, seeded_contract, db_session, monkeypatch):
    """On success the contract row has file_url, file_name, file_size, mime_type set."""
    import app.integrations.azure_blob as blob_mod
    import app.api.contract as contract_mod

    fake_url = "https://account.blob.core.windows.net/xiaoshou-contracts/contract/1/abc-contract.pdf"

    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    monkeypatch.setattr(
        blob_mod,
        "upload_bytes",
        lambda data, filename, content_type, prefix="": ("fake-blob-name", fake_url),
    )
    # No old file to delete
    monkeypatch.setattr(blob_mod, "delete_blob", lambda url: None)

    pdf_content = b"%PDF-1.4 a minimal but non-empty pdf"
    resp = _upload(
        client,
        seeded_contract.id,
        filename="contract.pdf",
        content=pdf_content,
        content_type="application/pdf",
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_url"] == fake_url
    assert body["file_name"] == "contract.pdf"
    assert body["file_size"] == len(pdf_content)
    assert body["mime_type"] == "application/pdf"

    # Verify the DB row was actually persisted
    db_session.expire_all()
    refreshed = db_session.query(Contract).filter(Contract.id == seeded_contract.id).first()
    assert refreshed.file_url == fake_url
    assert refreshed.file_name == "contract.pdf"


def test_upload_contract_not_found(client, monkeypatch):
    """Returns 404 when contract_id does not exist."""
    import app.integrations.azure_blob as blob_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)

    resp = _upload(
        client,
        contract_id=999999,
        filename="contract.pdf",
        content=b"%PDF non-empty",
        content_type="application/pdf",
    )

    assert resp.status_code == 404, resp.text
