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
from app.models.cc_bill import CCBill
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource
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
    """Customer + linked resource whose identifier_field = "PROJ-X1".

    The new sync flow matches service_accounts by resource.identifier_field,
    not by customer.customer_code. We mirror that via customer_resource here.
    """
    c = Customer(
        id=1, customer_code="CUST-X1", customer_name="X1 客户",
        customer_status="active", lifecycle_stage="active", is_deleted=False,
    )
    r = Resource(
        id=1, resource_code="res-proj-x1", resource_type="cloud",
        cloud_provider="AZURE", identifier_field="PROJ-X1",
        resource_status="AVAILABLE",
    )
    link = CustomerResource(customer_id=1, resource_id=1)
    db_session.add_all([c, r, link])
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
    # Customer has a resource with identifier_field "PROJ-X1",
    # but cloud side has no account with that external_project_id.
    fake = _FakeCloud(accounts=[_svc(99, "OTHER-PROJ")])
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=1&days=7")
    assert r.status_code == 200
    body = r.json()
    assert body["matched_accounts"] == 0
    assert body["pulled"] == 0
    assert "warning" in body and "没有任何 external_project_id 命中" in (body.get("warning") or "")

    # Nothing written to cc_usage
    assert db_session.query(CCUsage).count() == 0


def test_usage_sync_customer_without_resources_returns_warning(
    client, db_session, monkeypatch,
):
    """新口径: 没分配货源 (无 customer_resource) 就不去云管拉数据."""
    c = Customer(
        id=42, customer_code="CUST-Y", customer_name="无分配客户",
        customer_status="active", is_deleted=False,
    )
    db_session.add(c)
    db_session.commit()

    fake = _FakeCloud(
        accounts=[_svc(10, "PROJ-Y")],
        metering_rows=[{"_account_id": 10, "date": date.today().isoformat(),
                        "cost": "1", "usage": 1}],
    )
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=42&days=3")
    assert r.status_code == 200
    body = r.json()
    assert body["matched_accounts"] == 0
    assert body["pulled"] == 0
    assert "未分配任何带 identifier_field" in (body.get("warning") or "")
    # 未调用云管 service_accounts —— 早期返回；metering_calls 空
    assert fake.metering_calls == []
    assert db_session.query(CCUsage).count() == 0


def test_bills_sync_resolves_customer_code_via_account_id(
    client, db_session, monkeypatch,
):
    """回归 Bug A: cc_bill.customer_code 必须等于 service_account.external_project_id.

    云管账单 item 通常只带 account_id / service_account_id, 不直接带
    external_project_id; 同步时必须用 account_id 反查 service_account,
    拿到 external_project_id, 再写入 cc_bill.customer_code。
    之前的实现构造了一个 identity mapping (external_project_id →
    external_project_id), 结果 cc_bill.customer_code 全部写成 NULL。
    """

    class _FakeBillsCloud:
        def __init__(self):
            # 两个账号，分别属于不同的 external_project_id
            self._accounts = [_svc(101, "PROJ-A"), _svc(102, "PROJ-B")]

        def list_service_accounts(self, page=1, page_size=500):
            return list(self._accounts)

        def bills(self, month=None, page=1, page_size=500, **kw):
            # 模拟云管账单响应: 只有 account_id 字段, 没有 external_project_id
            return [
                {"id": 9001, "account_id": 101, "month": month,
                 "original_cost": "100", "final_cost": "90", "status": "draft"},
                {"id": 9002, "service_account_id": 102, "month": month,
                 "original_cost": "200", "final_cost": "180", "status": "confirmed"},
                # item 自带 external_project_id 时也应直接用
                {"id": 9003, "external_project_id": "PROJ-A", "month": month,
                 "original_cost": "50", "final_cost": "45", "status": "draft"},
            ]

    fake = _FakeBillsCloud()
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/bills?month=2026-04")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["pulled"] == 3
    assert body["created"] == 3
    assert body["errors"] == 0

    bills = db_session.query(CCBill).order_by(CCBill.remote_id).all()
    assert len(bills) == 3
    by_remote = {b.remote_id: b for b in bills}
    # account_id=101 反查 → PROJ-A
    assert by_remote[9001].customer_code == "PROJ-A"
    # service_account_id=102 反查 → PROJ-B
    assert by_remote[9002].customer_code == "PROJ-B"
    # 自带 external_project_id → 直接用
    assert by_remote[9003].customer_code == "PROJ-A"


def test_usage_sync_stores_by_external_project_id_not_customer_code(
    client, db_session, monkeypatch,
):
    """回归: cc_usage.customer_code 必须等于 external_project_id, 不是 CUST-XXX.

    读侧 bills_local.py 是按 resource.identifier_field (=external_project_id)
    去 join cc_usage 的; 写侧不能存 customer.customer_code。
    """
    c = Customer(
        id=77, customer_code="CUST-Z", customer_name="Z",
        customer_status="active", is_deleted=False,
    )
    r1 = Resource(id=77, resource_code="res-z-1", resource_type="cloud",
                  cloud_provider="AZURE", identifier_field="PROJ-Z-1",
                  resource_status="AVAILABLE")
    r2 = Resource(id=78, resource_code="res-z-2", resource_type="cloud",
                  cloud_provider="AZURE", identifier_field="PROJ-Z-2",
                  resource_status="AVAILABLE")
    db_session.add_all([
        c, r1, r2,
        CustomerResource(customer_id=77, resource_id=77),
        CustomerResource(customer_id=77, resource_id=78),
    ])
    db_session.commit()

    today = date.today()
    fake = _FakeCloud(
        accounts=[_svc(1, "PROJ-Z-1"), _svc(2, "PROJ-Z-2")],
        metering_rows=[
            {"_account_id": 1, "date": today.isoformat(),
             "cost": "10", "usage": 1, "service": "S1"},
            {"_account_id": 2, "date": today.isoformat(),
             "cost": "20", "usage": 2, "service": "S2"},
        ],
    )
    _install_fake_cloud(monkeypatch, fake)
    _stub_sync_log(monkeypatch)

    r = client.post("/api/sync/cloudcost/usage?customer_id=77&days=3")
    assert r.status_code == 200, r.text
    assert r.json()["matched_accounts"] == 2

    rows = db_session.query(CCUsage).order_by(CCUsage.customer_code).all()
    codes = {row.customer_code for row in rows}
    # 每个 external_project_id 单独一条; 不能把所有都聚合到 CUST-Z 下
    assert codes == {"PROJ-Z-1", "PROJ-Z-2"}
    assert "CUST-Z" not in codes
