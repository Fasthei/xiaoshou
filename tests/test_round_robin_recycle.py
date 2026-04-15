"""Round-robin assignment + expire-recycle + external API auth gate."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from main import app


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
def seed_ai_customers(db_session):
    # 6 AI-industry prospects to round-robin
    for i in range(1, 7):
        db_session.add(Customer(
            id=i, customer_code=f"C-{i}", customer_name=f"AI客户{i}",
            customer_status="prospect", industry="AI", is_deleted=False,
        ))
    db_session.commit()


# ---------- round-robin ----------

def test_round_robin_distributes_evenly(client, seed_ai_customers, db_session):
    u1 = client.post("/api/sales/users", json={"name": "U1"}).json()
    u2 = client.post("/api/sales/users", json={"name": "U2"}).json()
    u3 = client.post("/api/sales/users", json={"name": "U3"}).json()

    r = client.post("/api/sales/rules", json={
        "name": "AI 轮询", "industry": "AI",
        "sales_user_ids": [u1["id"], u2["id"], u3["id"]],
        "priority": 10,
    })
    assert r.status_code == 200, r.text
    rule = r.json()
    assert rule["cursor"] == 0
    assert rule["sales_user_ids"] == [u1["id"], u2["id"], u3["id"]]

    resp = client.post("/api/sales/auto-assign", json={"dry_run": False}).json()
    assert resp["total_assigned"] == 6

    # Verify round-robin distribution: each user gets 2 customers (6/3)
    db_session.expire_all()
    counts = {}
    for c in db_session.query(Customer).filter(Customer.sales_user_id.isnot(None)).all():
        counts[c.sales_user_id] = counts.get(c.sales_user_id, 0) + 1
    assert counts[u1["id"]] == 2
    assert counts[u2["id"]] == 2
    assert counts[u3["id"]] == 2

    # Cursor should be 6 (0 through 5 rotated)
    rules = client.get("/api/sales/rules").json()
    assert rules[0]["cursor"] == 6


def test_round_robin_dry_run_does_not_advance_cursor(client, seed_ai_customers, db_session):
    u1 = client.post("/api/sales/users", json={"name": "U1"}).json()
    u2 = client.post("/api/sales/users", json={"name": "U2"}).json()

    client.post("/api/sales/rules", json={
        "name": "轮询", "industry": "AI",
        "sales_user_ids": [u1["id"], u2["id"]], "priority": 10,
    })

    # Dry-run twice — peek should always show cursor=0 choice (u1)
    for _ in range(2):
        r = client.post("/api/sales/auto-assign", json={"dry_run": True}).json()
        # All 6 customers should peek at u1 (cursor stays 0)
        peeked = {it["sales_user_id"] for it in r["items"]}
        assert peeked == {u1["id"]}

    # cursor unchanged
    assert client.get("/api/sales/rules").json()[0]["cursor"] == 0


def test_rule_requires_target(client, db_session):
    r = client.post("/api/sales/rules", json={"name": "空规则"})
    assert r.status_code == 400
    assert "sales_user_id" in r.json()["detail"] or "指定" in r.json()["detail"]


def test_round_robin_with_bad_user_id_rejected(client, db_session):
    client.post("/api/sales/users", json={"name": "U1"})  # id=1
    r = client.post("/api/sales/rules", json={
        "name": "坏 id", "sales_user_ids": [1, 999],
    })
    assert r.status_code == 400


# ---------- expire recycle ----------

def test_auto_recycle_pulls_stale_assignments(client, db_session):
    u1 = client.post("/api/sales/users", json={"name": "U1"}).json()
    # customer with last_follow_time 60 days ago — should be recycled at 30d threshold
    stale = Customer(
        id=1, customer_code="C-STALE", customer_name="久未跟进",
        customer_status="active", is_deleted=False,
        sales_user_id=u1["id"], last_follow_time=datetime.now() - timedelta(days=60),
    )
    # customer with last_follow_time 5 days ago — fresh
    fresh = Customer(
        id=2, customer_code="C-FRESH", customer_name="新鲜",
        customer_status="active", is_deleted=False,
        sales_user_id=u1["id"], last_follow_time=datetime.now() - timedelta(days=5),
    )
    # customer never followed — also stale
    never = Customer(
        id=3, customer_code="C-NEVER", customer_name="从未联系",
        customer_status="prospect", is_deleted=False,
        sales_user_id=u1["id"], last_follow_time=None,
    )
    # unassigned customer — should not be scanned
    unassigned = Customer(
        id=4, customer_code="C-UN", customer_name="未分配",
        customer_status="prospect", is_deleted=False,
        sales_user_id=None, last_follow_time=None,
    )
    for c in [stale, fresh, never, unassigned]:
        db_session.add(c)
    db_session.commit()

    # dry run
    r = client.post("/api/sales/auto-recycle", json={"stale_days": 30, "dry_run": True}).json()
    assert r["total_scanned"] == 2  # stale + never
    assert r["total_recycled"] == 0
    db_session.expire_all()
    # nothing changed
    assert db_session.query(Customer).get(1).sales_user_id == u1["id"]

    # real run
    r = client.post("/api/sales/auto-recycle", json={"stale_days": 30, "dry_run": False}).json()
    assert r["total_recycled"] == 2
    db_session.expire_all()
    assert db_session.query(Customer).get(1).sales_user_id is None  # stale → recycled
    assert db_session.query(Customer).get(2).sales_user_id == u1["id"]  # fresh kept
    assert db_session.query(Customer).get(3).sales_user_id is None  # never → recycled

    # Log entries written with trigger=recycle
    logs = client.get("/api/customers/1/assignment-log").json()
    assert logs[0]["trigger"] == "recycle"
    assert logs[0]["to_user_id"] is None


# ---------- capacity limit ----------

def test_capacity_limit_skips_full_user_in_round_robin(client, seed_ai_customers, db_session):
    """U1 is full (max=1 and already has 1 customer), U2 has room — round-robin
    should direct all new assignments to U2 for this rule."""
    u1 = client.post("/api/sales/users", json={"name": "U1", "max_customers": 1}).json()
    u2 = client.post("/api/sales/users", json={"name": "U2", "max_customers": 100}).json()

    # Pre-fill U1 to capacity by directly assigning one customer
    client.patch(f"/api/customers/1/assign", json={"sales_user_id": u1["id"]})

    client.post("/api/sales/rules", json={
        "name": "AI 轮询带容量", "industry": "AI",
        "sales_user_ids": [u1["id"], u2["id"]], "priority": 10,
    })

    # remaining 5 AI customers → all should go to U2 (U1 is capped)
    resp = client.post("/api/sales/auto-assign", json={"dry_run": False}).json()
    assert resp["total_assigned"] == 5

    db_session.expire_all()
    counts = {}
    for c in db_session.query(Customer).filter(Customer.sales_user_id.isnot(None)).all():
        counts[c.sales_user_id] = counts.get(c.sales_user_id, 0) + 1
    # U1 stays at 1 (full), U2 gets all 5
    assert counts[u1["id"]] == 1
    assert counts[u2["id"]] == 5


def test_capacity_limit_single_user_mode_skips_entirely(client, seed_ai_customers, db_session):
    """Single-user rule whose target is at capacity: every customer reports
    'matched but all候选超容量' and nothing is assigned."""
    u1 = client.post("/api/sales/users", json={"name": "U1", "max_customers": 1}).json()
    client.patch("/api/customers/1/assign", json={"sales_user_id": u1["id"]})

    client.post("/api/sales/rules", json={
        "name": "AI → U1 单人", "industry": "AI",
        "sales_user_id": u1["id"], "priority": 10,
    })

    resp = client.post("/api/sales/auto-assign", json={"dry_run": False}).json()
    assert resp["total_assigned"] == 0  # all 5 remaining AI 客户 blocked by capacity
    assert all("超容量" in it["reason"] for it in resp["items"]
               if it["matched_rule_id"] is not None)


def test_sales_load_endpoint(client, seed_ai_customers, db_session):
    u1 = client.post("/api/sales/users", json={"name": "满额", "max_customers": 2}).json()
    u2 = client.post("/api/sales/users", json={"name": "无限", "max_customers": None}).json()
    client.patch("/api/customers/1/assign", json={"sales_user_id": u1["id"]})
    client.patch("/api/customers/2/assign", json={"sales_user_id": u1["id"]})
    client.patch("/api/customers/3/assign", json={"sales_user_id": u2["id"]})

    r = client.get("/api/sales/users/load").json()
    by_id = {x["id"]: x for x in r}
    assert by_id[u1["id"]]["current_count"] == 2
    assert by_id[u1["id"]]["max_customers"] == 2
    assert by_id[u1["id"]]["load_pct"] == 100
    assert by_id[u2["id"]]["current_count"] == 1
    assert by_id[u2["id"]]["load_pct"] == -1  # no cap


def test_activity_recent_merges_sources(client, seed_ai_customers, db_session):
    # Create a follow-up and an assignment to populate two activity sources
    client.post("/api/customers/1/follow-ups", json={"kind": "call", "title": "首电"})
    u = client.post("/api/sales/users", json={"name": "U"}).json()
    client.patch("/api/customers/1/assign", json={"sales_user_id": u["id"]})

    r = client.get("/api/sales/activity/recent?limit=10").json()
    kinds = {x["kind"] for x in r}
    assert "follow_up" in kinds
    assert "assignment" in kinds
    # Sorted descending by `at`
    times = [x["at"] for x in r]
    assert times == sorted(times, reverse=True)


# ---------- external API auth ----------

def test_external_ping_no_auth(client):
    r = client.get("/api/external/meta/ping")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_external_requires_api_key(client):
    r = client.get("/api/external/customers")
    assert r.status_code == 401


def test_external_with_valid_api_key(client, db_session, monkeypatch):
    # test_config.py's _reload_settings() wipes our lru_cache and any
    # previously-patched Settings instance. Wrap get_settings so every caller
    # (including the request handler) sees our patched key regardless of
    # module reloads that happened earlier in the session.
    from app import config as _cfg

    class _Patched:
        SUPER_OPS_API_KEY = "testkey-zzz"
        XIAOSHOU_INTERNAL_API_KEY = ""

    import app.api.external as ext_mod
    monkeypatch.setattr(ext_mod, "get_settings", lambda: _Patched())

    # seed one customer
    db_session.add(Customer(
        id=1, customer_code="C-X", customer_name="外部测试客户",
        customer_status="active", is_deleted=False,
    ))
    db_session.commit()

    r = client.get("/api/external/customers", headers={"X-Api-Key": "testkey-zzz"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_code"] == "C-X"

    # wrong key → 401
    r = client.get("/api/external/customers", headers={"X-Api-Key": "wrong"})
    assert r.status_code == 401
