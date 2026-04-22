"""End-to-end sync coverage for the upgraded /api/sync/cloudcost/usage path.

We stub :class:`CloudCostClient` so no HTTP runs; the test proves:

1. metering_detail_iter is consumed first, and its rows land in cc_usage with
   raw.accounts[*].source == "metering".
2. If metering_detail_iter raises (cloudcost deploy hasn't landed yet), the
   sync falls back to get_customer_usage() and still writes rows with
   raw.accounts[*].source == "legacy".
3. Local aggregation shape matches what bills_local.py expects
   (total_cost / total_usage / record_count / raw.accounts list).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.sync_log import SyncLog
from main import app
from app.integrations.cloudcost import ServiceAccount
import app.api.cc_sync as cc_sync
import app.services.cloudcost_sync as cloudcost_sync


# ---------- Fixtures ----------

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
def seed_customer(db_session):
    c = Customer(
        id=1, customer_code="PROJ-X1", customer_name="X1 客户",
        customer_status="active", lifecycle_stage="active", is_deleted=False,
    )
    db_session.add(c)
    db_session.commit()
    return c


# ---------- Fake cloudcost client ----------

class _FakeCloud:
    """Minimum surface cc_sync.sync_cloudcost_usage uses."""

    def __init__(
        self,
        accounts: List[ServiceAccount],
        metering_rows: Optional[List[Dict[str, Any]]] = None,
        metering_fails: bool = False,
        legacy_rows: Optional[List[Dict[str, Any]]] = None,
    ):
        self._accounts = accounts
        self._metering_rows = metering_rows or []
        self._metering_fails = metering_fails
        self._legacy_rows = legacy_rows or []
        self.metering_calls: List[Dict[str, Any]] = []
        self.legacy_calls: List[int] = []

    def list_service_accounts(self, page: int = 1, page_size: int = 200):
        return list(self._accounts)

    def metering_detail_iter(
        self, start_date: str, end_date: str, account_id: Optional[int] = None,
        page_size: int = 500, max_pages: int = 500,
    ) -> Iterable[Dict[str, Any]]:
        self.metering_calls.append({
            "start_date": start_date, "end_date": end_date,
            "account_id": account_id,
        })
        if self._metering_fails:
            raise RuntimeError("cloudcost metering 尚未部署")
        for r in self._metering_rows:
            if account_id is None or r.get("_account_id") == account_id:
                yield r

    def get_customer_usage(self, account_id: int, days: int = 30):
        self.legacy_calls.append(account_id)
        return [r for r in self._legacy_rows if r.get("_account_id") == account_id]


# ---------- Helpers ----------

def _install_fake_cloud(monkeypatch, fake: _FakeCloud) -> None:
    # cc_sync._client_for(request) is the HTTP-layer factory — override it so
    # every route invocation under test returns the stubbed cloudcost client.
    monkeypatch.setattr(cc_sync, "_client_for", lambda _request: fake)


def _stub_sync_log(monkeypatch) -> None:
    """Avoid SQLite's reluctance to auto-generate BigInteger PKs.

    Production runs on Postgres where BigInteger + server-side sequence just
    works; SQLite in-memory doesn't auto-fill BigInteger PKs, so we replace
    _new_sync_log / _finish_log with noops that never touch the DB.
    After the sync refactor these helpers live on app.services.cloudcost_sync.
    """
    from datetime import datetime as _dt

    _counter = {"n": 0}

    def _fake_new_sync_log(db, sync_type, triggered_by):
        _counter["n"] += 1
        log = SyncLog(
            id=_counter["n"],
            source_system="cloudcost", sync_type=sync_type,
            status="running", started_at=_dt.utcnow(),
            triggered_by=triggered_by,
        )
        return log

    def _fake_finish_log(db, log, status, pulled, created, updated, skipped, errors, err_msg=None):
        log.status = status
        log.pulled_count = pulled
        log.created_count = created
        log.updated_count = updated
        log.skipped_count = skipped
        log.error_count = errors
        log.last_error = err_msg

    monkeypatch.setattr(cloudcost_sync, "_new_sync_log", _fake_new_sync_log)
    monkeypatch.setattr(cloudcost_sync, "_finish_log", _fake_finish_log)


def _svc(id_: int, ext: str, supplier: Optional[str] = None) -> ServiceAccount:
    return ServiceAccount(
        id=id_,
        name=f"acct-{id_}",
        provider="AZURE",
        supplier_name=supplier,
        supply_source_id=None,
        external_project_id=ext,
        status="AVAILABLE",
    )


# ---------- Tests ----------

def test_usage_sync_uses_metering_detail_first(client, db_session, seed_customer, monkeypatch):
    # Two matched service accounts; metering rows span 2 days.
    today = date.today()
    d1 = today.isoformat()
    d2 = (today - timedelta(days=1)).isoformat()

    fake = _FakeCloud(
        accounts=[_svc(10, "PROJ-X1"), _svc(11, "PROJ-X1")],
        metering_rows=[
            {"_account_id": 10, "date": d1, "cost": "5.00", "usage": 10, "service": "S3"},
            {"_account_id": 10, "date": d2, "cost": "3.00", "usage": 6, "service": "S3"},
            {"_account_id": 11, "date": d1, "cost": "2.00", "usage": 4, "service_name": "EC2"},
        ],
    )
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=1&days=7")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_accounts"] == 2
    # 3 metering rows pulled across 2 accounts
    assert body["pulled"] == 3
    assert body["errors"] == 0
    # Both metering calls fired, one per account
    assert len(fake.metering_calls) == 2
    # Legacy fallback never hit
    assert fake.legacy_calls == []

    rows = (
        db_session.query(CCUsage)
        .filter(CCUsage.customer_code == "PROJ-X1")
        .order_by(CCUsage.date)
        .all()
    )
    # 2 distinct dates → 2 cc_usage rows
    assert len(rows) == 2
    by_date = {r.date.isoformat(): r for r in rows}

    # d2: only acct 10 (3.00 / 6) → 1 record
    r_d2 = by_date[d2]
    assert Decimal(r_d2.total_cost) == Decimal("3.00")
    assert Decimal(r_d2.total_usage) == Decimal("6")
    assert r_d2.record_count == 1
    accounts_d2 = r_d2.raw["accounts"]
    assert len(accounts_d2) == 1
    assert accounts_d2[0]["account_id"] == 10
    assert accounts_d2[0]["source"] == "metering"

    # d1: acct 10 (5 / 10) + acct 11 (2 / 4) → 2 records
    r_d1 = by_date[d1]
    assert Decimal(r_d1.total_cost) == Decimal("7.00")
    assert Decimal(r_d1.total_usage) == Decimal("14")
    assert r_d1.record_count == 2
    services = {a["service"] for a in r_d1.raw["accounts"]}
    assert services == {"S3", "EC2"}
    assert all(a["source"] == "metering" for a in r_d1.raw["accounts"])


def test_usage_sync_falls_back_to_legacy_when_metering_raises(
    client, db_session, seed_customer, monkeypatch,
):
    today = date.today()
    d = today.isoformat()

    fake = _FakeCloud(
        accounts=[_svc(20, "PROJ-X1")],
        metering_fails=True,
        legacy_rows=[
            {"_account_id": 20, "date": d, "cost": "9.99", "usage": 42, "service": "Blob"},
        ],
    )
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=1&days=3")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_accounts"] == 1
    assert body["errors"] == 0
    # metering was attempted (and failed), then legacy was called
    assert len(fake.metering_calls) == 1
    assert fake.legacy_calls == [20]

    row = db_session.query(CCUsage).filter_by(customer_code="PROJ-X1").one()
    assert Decimal(row.total_cost) == Decimal("9.99")
    assert row.record_count == 1
    assert row.raw["accounts"][0]["source"] == "legacy"


def test_usage_sync_no_matching_account_returns_warning(
    client, db_session, seed_customer, monkeypatch,
):
    # No service account matches PROJ-X1
    fake = _FakeCloud(accounts=[_svc(99, "OTHER-PROJ")])
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=1&days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["matched_accounts"] == 0
    assert body["pulled"] == 0
    assert "warning" in body and "未命中" in (body.get("warning") or "")

    # Nothing written to cc_usage
    assert db_session.query(CCUsage).count() == 0


def test_usage_sync_supplier_name_fallback(client, db_session, seed_customer, monkeypatch):
    # external_project_id miss, supplier_name hit
    today = date.today()
    d = today.isoformat()
    fake = _FakeCloud(
        accounts=[_svc(30, "UNRELATED", supplier="PROJ-X1")],
        metering_rows=[
            {"_account_id": 30, "date": d, "cost": "1.50", "usage": 3, "service": "Cost"},
        ],
    )
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=1&days=3")
    assert r.status_code == 200
    body = r.json()
    assert body["matched_accounts"] == 1
    assert body["pulled"] == 1

    row = db_session.query(CCUsage).filter_by(customer_code="PROJ-X1").one()
    assert Decimal(row.total_cost) == Decimal("1.50")
