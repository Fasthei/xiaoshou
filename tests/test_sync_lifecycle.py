"""议题 B 两级删除策略回归测试。

1. 工单同步：远端消失的正式客户 → 本地降级到 lead + demoted_*
2. 工单同名 + 本地墓碑 → skip (不复活)
3. 云管同步：远端消失的货源 → is_deleted=true + deleted_at
4. 商机池硬删 endpoint: 只允许 lead 状态；写 is_deleted + deletion_*
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import Base, get_db
from app.models.customer import Customer
from app.models.resource import Resource
from main import app
import app.api.sync as sync_mod


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


@pytest.fixture(autouse=True)
def _enable_gongdan_settings(monkeypatch):
    s = get_settings()
    # 只要非空；GongdanClient 会被 stub 掉
    monkeypatch.setattr(s, "GONGDAN_ENDPOINT", "http://gongdan.test", raising=False)
    monkeypatch.setattr(s, "GONGDAN_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(s, "CLOUDCOST_ENDPOINT", "http://cloudcost.test", raising=False)


class _FakeRC:
    def __init__(self, code, name, rid=""):
        self.customer_code = code
        self.name = name
        self.id = rid


class _FakeGongdanClient:
    def __init__(self, remote: list[_FakeRC]):
        self._remote = remote

    def list_customers(self):
        return self._remote


class _FakeSvcAcct:
    def __init__(self, aid: int, name: str, ext: str | None):
        self.id = aid
        self.name = name
        self.provider = "AWS"
        self.supplier_name = None
        self.external_project_id = ext
        self.status = "active"


class _FakeCloudClient:
    def __init__(self, accounts):
        self._accounts = accounts

    def list_service_accounts(self, page=1, page_size=500):
        return list(self._accounts)


def _stub_gongdan(monkeypatch, remote):
    monkeypatch.setattr(sync_mod, "GongdanClient", lambda *a, **k: _FakeGongdanClient(remote))


def _stub_cloudcost(monkeypatch, accounts):
    monkeypatch.setattr(sync_mod, "CloudCostClient", lambda *a, **k: _FakeCloudClient(accounts))


# ---------- 工单同步降级 ----------

def test_gongdan_sync_demotes_missing_customer(client, db_session, monkeypatch):
    """本地有 source_system=gongdan + active + code='C1' 的客户，但远端没了 → 降级到 lead."""
    db_session.add(Customer(
        id=1, customer_code="C1", customer_name="老客户",
        customer_status="formal", lifecycle_stage="active",
        source_system="gongdan", is_deleted=False,
    ))
    db_session.commit()

    _stub_gongdan(monkeypatch, remote=[_FakeRC("C2", "新客户", rid="g-C2")])
    r = client.post("/api/sync/customers/from-ticket")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["demoted"] == 1
    assert body["created"] == 1

    db_session.expire_all()
    old = db_session.query(Customer).filter_by(customer_code="C1").one()
    assert old.lifecycle_stage == "lead"
    assert old.demoted_at is not None
    assert old.demoted_reason == "gongdan 侧已删除"
    assert old.is_deleted is False


def test_gongdan_sync_tombstone_blocks_resurrection(client, db_session, monkeypatch):
    """本地 is_deleted=true 的同 code 客户 → 工单同名时 skip 不复活."""
    db_session.add(Customer(
        id=2, customer_code="DEAD", customer_name="被删的",
        customer_status="potential", lifecycle_stage="lead",
        source_system="gongdan", is_deleted=True,
        deleted_at=datetime.utcnow(),
    ))
    db_session.commit()

    _stub_gongdan(monkeypatch, remote=[_FakeRC("DEAD", "重新出现的名字", rid="g-x")])
    r = client.post("/api/sync/customers/from-ticket")
    assert r.status_code == 200
    body = r.json()
    assert body["tombstoned"] == 1
    assert body["created"] == 0
    # 本地不会多出一条 is_deleted=false 的 DEAD
    alive = db_session.query(Customer).filter_by(
        customer_code="DEAD", is_deleted=False,
    ).count()
    assert alive == 0


def test_gongdan_sync_reactivates_demoted_on_return(client, db_session, monkeypatch):
    """被降级的 gongdan 客户，如果工单侧又回来 → 清除 demoted 标记 + 升回 active."""
    now = datetime.utcnow()
    db_session.add(Customer(
        id=3, customer_code="BACK", customer_name="回来的客户",
        customer_status="potential", lifecycle_stage="lead",
        source_system="gongdan", is_deleted=False,
        demoted_at=now, demoted_reason="gongdan 侧已删除",
    ))
    db_session.commit()

    _stub_gongdan(monkeypatch, remote=[_FakeRC("BACK", "回来的客户", rid="g-BACK")])
    r = client.post("/api/sync/customers/from-ticket")
    assert r.status_code == 200
    db_session.expire_all()
    c = db_session.query(Customer).filter_by(customer_code="BACK").one()
    assert c.lifecycle_stage == "active"
    assert c.demoted_at is None
    assert c.demoted_reason is None


def test_gongdan_sync_skips_manual_customers(client, db_session, monkeypatch):
    """source_system != gongdan 的手工客户不受降级影响."""
    db_session.add(Customer(
        id=4, customer_code="M1", customer_name="手工建",
        customer_status="active", lifecycle_stage="active",
        source_system="manual", is_deleted=False,
    ))
    db_session.commit()

    _stub_gongdan(monkeypatch, remote=[])  # 远端啥都没
    r = client.post("/api/sync/customers/from-ticket")
    assert r.status_code == 200
    assert r.json()["demoted"] == 0


# ---------- 云管货源同步软删 ----------

def test_cloudcost_sync_soft_deletes_missing_resource(client, db_session, monkeypatch):
    """云管没这个 account 了 → 本地 resource is_deleted=true + deleted_at."""
    db_session.add(Resource(
        id=1, resource_code="cc-99", resource_type="cloud",
        cloud_provider="AWS", identifier_field="proj-old",
        resource_status="AVAILABLE",
        source_system="cloudcost", source_id="99",
        is_deleted=False,
    ))
    db_session.commit()

    _stub_cloudcost(monkeypatch, accounts=[
        _FakeSvcAcct(100, "new-acct", "proj-new"),
    ])
    r = client.post("/api/sync/resources/from-cloudcost")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["soft_deleted"] == 1

    db_session.expire_all()
    r_ = db_session.query(Resource).filter_by(resource_code="cc-99").one()
    assert r_.is_deleted is True
    assert r_.deleted_at is not None
    assert r_.resource_status == "DECOMMISSIONED"


def test_cloudcost_sync_tombstone_blocks_same_code(client, db_session, monkeypatch):
    """本地 is_deleted=true 的 cc-50 → 云管同 account 回来时 skip 不复活."""
    db_session.add(Resource(
        id=2, resource_code="cc-50", resource_type="cloud",
        cloud_provider="AWS", resource_status="DECOMMISSIONED",
        source_system="cloudcost", is_deleted=True,
        deleted_at=datetime.utcnow(),
    ))
    db_session.commit()

    _stub_cloudcost(monkeypatch, accounts=[
        _FakeSvcAcct(50, "reused", "proj-reused"),
    ])
    r = client.post("/api/sync/resources/from-cloudcost")
    assert r.status_code == 200
    body = r.json()
    assert body["tombstoned"] == 1
    alive = db_session.query(Resource).filter_by(
        resource_code="cc-50", is_deleted=False,
    ).count()
    assert alive == 0


# ---------- 商机池硬删 endpoint ----------

def _admin():
    app.dependency_overrides[require_auth] = lambda: CurrentUser(
        sub="admin", name="admin", roles=["admin"], raw={},
    )


def _reset():
    app.dependency_overrides.pop(require_auth, None)


def test_hard_delete_in_lead_pool(client, db_session):
    db_session.add(Customer(
        id=100, customer_code="LEAD-1", customer_name="一个商机",
        customer_status="potential", lifecycle_stage="lead",
        source_system="manual", is_deleted=False,
    ))
    db_session.commit()

    _admin()
    try:
        r = client.post("/api/customers/100/hard-delete", json={"reason": "测试"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["customer_code"] == "LEAD-1"
        assert body["deletion_reason"] == "测试"

        db_session.expire_all()
        c = db_session.query(Customer).filter_by(id=100).one()
        assert c.is_deleted is True
        assert c.deleted_at is not None
        assert c.deleted_by.startswith("admin")
    finally:
        _reset()


def test_hard_delete_blocks_active_stage(client, db_session):
    """active 客户必须先退回商机池才能删."""
    db_session.add(Customer(
        id=101, customer_code="ACT", customer_name="正式客户",
        customer_status="active", lifecycle_stage="active",
        source_system="gongdan", is_deleted=False,
    ))
    db_session.commit()

    _admin()
    try:
        r = client.post("/api/customers/101/hard-delete", json={"reason": "x"})
        assert r.status_code == 400
        c = db_session.query(Customer).filter_by(id=101).one()
        assert c.is_deleted is False
    finally:
        _reset()


def test_archive_list_shows_deleted(client, db_session):
    db_session.add_all([
        Customer(id=110, customer_code="D1", customer_name="活",
                 customer_status="potential", lifecycle_stage="lead",
                 is_deleted=False),
        Customer(id=111, customer_code="D2", customer_name="死",
                 customer_status="potential", lifecycle_stage="lead",
                 is_deleted=True, deleted_at=datetime.utcnow(),
                 deleted_by="tester:t", deletion_reason="测试"),
    ])
    db_session.commit()

    _admin()
    try:
        r = client.get("/api/customers/archive/list")
        assert r.status_code == 200
        ids = {x["id"] for x in r.json()}
        assert 111 in ids
        assert 110 not in ids
    finally:
        _reset()
