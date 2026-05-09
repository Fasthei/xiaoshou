"""Tests for POST /api/contracts/{contract_id}/upload (single-file append).

Coverage:
- 503 when Azure Blob Storage is not configured
- 400 when an unsupported file type is uploaded (e.g. .exe)
- 400 when an empty file is uploaded
- 413 when a file exceeds the configured size cap (cap monkeypatched smaller for speed)
- 200 success path: a new ContractAttachment row is created (existing rows preserved)
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
from app.models.contract_attachment import ContractAttachment
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
    """Returns 413 when the uploaded file exceeds the configured size cap.

    We monkeypatch the cap down to 1KB so we don't have to allocate 100MB+1
    bytes in the test process — the behaviour we care about is that the cap
    is enforced and the 413 message echoes the limit.
    """
    import app.integrations.azure_blob as blob_mod
    import app.api.contract as contract_mod
    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    monkeypatch.setattr(contract_mod, "MAX_UPLOAD_SIZE", 1024)  # 1 KB cap

    payload = b"x" * (1024 + 1)
    resp = _upload(
        client,
        seeded_contract.id,
        filename="huge.pdf",
        content=payload,
        content_type="application/pdf",
    )

    assert resp.status_code == 413, resp.text
    # The error message echoes the cap as MB; with 1KB cap → "0MB"
    assert "MB 上限" in resp.json()["detail"]


def test_upload_contract_appends_attachment(client, seeded_contract, db_session, monkeypatch):
    """On success a new ContractAttachment row is appended (not a replace)."""
    import app.integrations.azure_blob as blob_mod

    fake_url_a = "https://account.blob.core.windows.net/xiaoshou-contracts/contract/1/abc-a.pdf"
    fake_url_b = "https://account.blob.core.windows.net/xiaoshou-contracts/contract/1/abc-b.pdf"

    monkeypatch.setattr(blob_mod, "is_configured", lambda: True)
    fake_urls = iter([("a-blob", fake_url_a), ("b-blob", fake_url_b)])
    monkeypatch.setattr(
        blob_mod,
        "upload_bytes",
        lambda data, filename, content_type, prefix="": next(fake_urls),
    )
    monkeypatch.setattr(blob_mod, "delete_blob", lambda url: None)

    resp = _upload(
        client,
        seeded_contract.id,
        filename="a.pdf",
        content=b"%PDF-1.4 first",
        content_type="application/pdf",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_url"] == fake_url_a
    assert body["file_name"] == "a.pdf"

    # Second upload appends; first should still exist.
    resp = _upload(
        client,
        seeded_contract.id,
        filename="b.pdf",
        content=b"%PDF-1.4 second",
        content_type="application/pdf",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["file_url"] == fake_url_b

    db_session.expire_all()
    rows = db_session.query(ContractAttachment).filter(
        ContractAttachment.contract_id == seeded_contract.id,
    ).all()
    urls = sorted(r.file_url for r in rows)
    assert urls == sorted([fake_url_a, fake_url_b]), "second upload must append, not replace"


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
