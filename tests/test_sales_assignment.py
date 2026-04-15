"""Sales team CRUD + rule-matching engine + assignment logging.

Uses in-memory SQLite (same pattern as test_customer_insight_agent).
Auth is disabled via conftest (AUTH_ENABLED=false) so TestClient hits
routes directly — the dependency override swaps get_db to our test session.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from app.models.sales import LeadAssignmentLog, LeadAssignmentRule, SalesUser
from main import app


@pytest.fixture()
def db_session():
    # StaticPool so every connection shares the same in-memory SQLite DB —
    # otherwise tables created on connection #1 are invisible to request
    # connection #2, and tests see 'no such table'.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()

    def override_get_db():
        try:
            yield s
        finally:
            pass  # keep open across requests in the test

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield s
    finally:
        s.close()
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(db_session):
    return TestClient(app)


@pytest.fixture()
def seed_customers(db_session):
    cs = [
        Customer(id=1, customer_code="C-A", customer_name="云能源A", customer_status="prospect",
                 industry="能源", region="华东", is_deleted=False),
        Customer(id=2, customer_code="C-B", customer_name="AI 创业B", customer_status="prospect",
                 industry="AI", region="华北", is_deleted=False),
        Customer(id=3, customer_code="C-C", customer_name="已分配C", customer_status="active",
                 industry="金融", region="华东", sales_user_id=1, is_deleted=False),
    ]
    for c in cs:
        db_session.add(c)
    db_session.commit()
    return cs


# ---------- users + rules CRUD ----------

def test_sales_users_crud(client):
    # list initially empty
    r = client.get("/api/sales/users"); assert r.status_code == 200; assert r.json() == []

    # create
    r = client.post("/api/sales/users", json={
        "name": "张三", "email": "z3@x.com", "regions": ["华东"], "industries": ["能源", "AI"],
    })
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert r.json()["name"] == "张三"

    # update
    r = client.patch(f"/api/sales/users/{uid}", json={"note": "王牌"})
    assert r.status_code == 200
    assert r.json()["note"] == "王牌"

    # deactivate
    r = client.delete(f"/api/sales/users/{uid}")
    assert r.status_code == 200
    # default list hides inactive
    r = client.get("/api/sales/users"); assert r.json() == []
    r = client.get("/api/sales/users?active_only=false"); assert len(r.json()) == 1


def test_rules_crud_requires_existing_sales_user(client):
    r = client.post("/api/sales/rules", json={
        "name": "默认", "sales_user_id": 999,
    })
    assert r.status_code == 400  # sales user not found

    u = client.post("/api/sales/users", json={"name": "李四"}).json()
    r = client.post("/api/sales/rules", json={
        "name": "华东能源", "industry": "能源", "region": "华东",
        "sales_user_id": u["id"], "priority": 10,
    })
    assert r.status_code == 200
    rid = r.json()["id"]

    # update
    r = client.patch(f"/api/sales/rules/{rid}", json={"priority": 5})
    assert r.status_code == 200 and r.json()["priority"] == 5

    # delete
    r = client.delete(f"/api/sales/rules/{rid}"); assert r.status_code == 200


# ---------- assign + audit log ----------

def test_assign_creates_log_entry(client, seed_customers, db_session):
    u = client.post("/api/sales/users", json={"name": "王五"}).json()

    r = client.patch(f"/api/customers/1/assign", json={
        "sales_user_id": u["id"], "reason": "本周起归王五",
    })
    assert r.status_code == 200, r.text
    assert r.json()["sales_user_id"] == u["id"]

    db_session.expire_all()
    c = db_session.query(Customer).get(1)
    assert c.sales_user_id == u["id"]

    logs = client.get("/api/customers/1/assignment-log").json()
    assert len(logs) == 1
    assert logs[0]["to_user_id"] == u["id"]
    assert logs[0]["trigger"] == "manual"
    assert logs[0]["reason"] == "本周起归王五"


def test_reassign_records_from_and_to(client, seed_customers, db_session):
    u1 = client.post("/api/sales/users", json={"name": "U1"}).json()
    u2 = client.post("/api/sales/users", json={"name": "U2"}).json()

    client.patch("/api/customers/1/assign", json={"sales_user_id": u1["id"]})
    client.patch("/api/customers/1/assign", json={"sales_user_id": u2["id"], "reason": "转交"})

    logs = client.get("/api/customers/1/assignment-log").json()
    assert len(logs) == 2
    # newest first
    assert logs[0]["from_user_id"] == u1["id"]
    assert logs[0]["to_user_id"] == u2["id"]


# ---------- auto-assign rule engine ----------

def test_auto_assign_picks_highest_priority_match(client, seed_customers, db_session):
    ua = client.post("/api/sales/users", json={"name": "华东专员"}).json()
    ub = client.post("/api/sales/users", json={"name": "通吃"}).json()

    # Specific rule: 能源/华东 → ua, priority 10
    client.post("/api/sales/rules", json={
        "name": "华东能源", "industry": "能源", "region": "华东",
        "sales_user_id": ua["id"], "priority": 10,
    })
    # Wildcard: anything → ub, priority 100
    client.post("/api/sales/rules", json={
        "name": "兜底", "sales_user_id": ub["id"], "priority": 100,
    })

    # dry run first
    r = client.post("/api/sales/auto-assign", json={"dry_run": True})
    assert r.status_code == 200
    result = r.json()
    assert result["dry_run"] is True
    assert result["total_scanned"] == 2  # only unassigned: id=1, id=2 (id=3 already has sales_user)
    assert result["total_assigned"] == 0  # dry-run doesn't commit

    # Check matches
    by_id = {it["customer_id"]: it for it in result["items"]}
    assert by_id[1]["sales_user_id"] == ua["id"]  # 能源/华东 → specific
    assert by_id[2]["sales_user_id"] == ub["id"]  # AI/华北 → wildcard

    # Real run
    r = client.post("/api/sales/auto-assign", json={"dry_run": False})
    assert r.status_code == 200
    assert r.json()["total_assigned"] == 2

    db_session.expire_all()
    c1 = db_session.query(Customer).get(1)
    c2 = db_session.query(Customer).get(2)
    c3 = db_session.query(Customer).get(3)
    assert c1.sales_user_id == ua["id"]
    assert c2.sales_user_id == ub["id"]
    assert c3.sales_user_id == 1  # untouched (was already assigned, only_unassigned=true)

    # Audit log present
    logs = client.get("/api/customers/1/assignment-log").json()
    assert len(logs) == 1
    assert logs[0]["trigger"] == "auto"
    assert logs[0]["rule_id"] is not None


def test_auto_assign_reports_no_rule_matched(client, seed_customers, db_session):
    # No rules configured
    r = client.post("/api/sales/auto-assign", json={"dry_run": False})
    assert r.status_code == 200
    result = r.json()
    assert result["total_assigned"] == 0
    assert all(it["matched_rule_id"] is None for it in result["items"])


def test_unassign_by_sending_null(client, seed_customers, db_session):
    # customer 3 is currently assigned (sales_user_id=1); create that user first
    client.post("/api/sales/users", json={"name": "初始"})  # id=1

    r = client.patch("/api/customers/3/assign", json={"sales_user_id": None, "reason": "暂时空档"})
    assert r.status_code == 200
    assert r.json()["sales_user_id"] is None
    db_session.expire_all()
    assert db_session.query(Customer).get(3).sales_user_id is None
