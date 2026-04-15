"""Follow-up log + completeness score + CSV import/export."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer, CustomerContact
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


# ---------- follow-up log ----------

def test_follow_up_crud_and_last_follow_time_bump(client, db_session):
    cid = client.post("/api/customers", json={
        "customer_code": "C-FU", "customer_name": "FU Test", "customer_status": "active",
    }).json()["id"]

    # initial: no follow-ups, no last_follow_time
    assert client.get(f"/api/customers/{cid}/follow-ups").json() == []

    # create
    r = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "call", "title": "首次电话联系", "content": "介绍产品",
        "outcome": "positive",
    })
    assert r.status_code == 200, r.text
    fu_id = r.json()["id"]
    assert r.json()["kind"] == "call"

    # customer.last_follow_time bumped
    c = client.get(f"/api/customers/{cid}").json()
    assert c["last_follow_time"] is not None

    # meeting kind also bumps last_meeting_at
    r = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "meeting", "title": "面访", "outcome": "positive",
    })
    c = client.get(f"/api/customers/{cid}").json()
    assert c.get("last_meeting_at") is not None

    # list is descending
    fus = client.get(f"/api/customers/{cid}/follow-ups").json()
    assert len(fus) == 2
    assert fus[0]["kind"] == "meeting"

    # delete
    client.delete(f"/api/customers/{cid}/follow-ups/{fu_id}")
    assert len(client.get(f"/api/customers/{cid}/follow-ups").json()) == 1


def test_follow_up_invalid_kind_rejected(client, db_session):
    cid = client.post("/api/customers", json={
        "customer_code": "C-BAD", "customer_name": "Bad", "customer_status": "active",
    }).json()["id"]
    r = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "ultra-mega", "title": "x",
    })
    assert r.status_code == 400


# ---------- completeness score ----------

def test_completeness_red_green_yellow(client, db_session):
    # Minimal customer: only name + status (score = 10 for name; status not weighted)
    cid = client.post("/api/customers", json={
        "customer_code": "C-EMPTY", "customer_name": "空档案", "customer_status": "prospect",
    }).json()["id"]
    c = client.get(f"/api/customers/{cid}/completeness").json()
    assert c["tier"] == "red"
    assert c["score"] == 10  # only customer_name weighted field present
    assert "行业" in c["missing"]

    # Fill a few → yellow
    client.put(f"/api/customers/{cid}", json={
        "industry": "AI", "region": "华东", "customer_level": "KEY",
        "sales_user_id": 1, "employee_size": 200,
    })
    c = client.get(f"/api/customers/{cid}/completeness").json()
    assert c["score"] == 60  # 10 name + 10 ind + 10 region + 10 level + 10 sales + 10 emp
    assert c["tier"] == "yellow"

    # Fill rest → green
    client.put(f"/api/customers/{cid}", json={
        "annual_revenue": 10_000_000, "website": "https://x.com",
    })
    # Add primary contact for +15
    client.post(f"/api/customers/{cid}/contacts", json={
        "contact_name": "张三", "is_primary": True,
    })
    # Add follow-up so last_follow_time is set (+8)
    client.post(f"/api/customers/{cid}/follow-ups", json={"kind": "note", "title": "x"})

    c = client.get(f"/api/customers/{cid}/completeness").json()
    assert c["tier"] == "green"
    assert c["score"] == 100
    assert "行业" in c["present"]
    assert "主联系人" in c["present"]


def test_completeness_missing_customer_404(client, db_session):
    r = client.get("/api/customers/99999/completeness")
    assert r.status_code == 404


# ---------- CSV export ----------

def test_export_csv(client, db_session):
    client.post("/api/customers", json={
        "customer_code": "E1", "customer_name": "导出 1", "customer_status": "active",
        "industry": "AI",
    })
    client.post("/api/customers", json={
        "customer_code": "E2", "customer_name": "导出 2", "customer_status": "active",
    })

    r = client.get("/api/customers/bulk/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "customer_code" in text
    assert "E1" in text
    assert "E2" in text
    assert "导出 1" in text


# ---------- CSV import ----------

def test_import_csv_creates_and_updates(client, db_session):
    # Pre-existing customer we expect to UPDATE
    client.post("/api/customers", json={
        "customer_code": "IMP-1", "customer_name": "旧名称", "customer_status": "prospect",
    })

    csv_bytes = (
        "customer_code,customer_name,industry,region,employee_size\n"
        "IMP-1,新名称,AI,华东,500\n"            # update
        "IMP-2,全新客户,金融,华北,120\n"         # create
        ",缺 code 的行会跳过,xx,yy,\n"            # skipped
    ).encode("utf-8")

    r = client.post(
        "/api/customers/bulk/import.csv",
        files={"file": ("in.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["updated"] == 1
    assert data["created"] == 1
    assert data["skipped"] == 1

    # Verify DB state
    c1 = client.get("/api/customers?keyword=IMP-1").json()["items"][0]
    assert c1["customer_name"] == "新名称"
    assert c1["industry"] == "AI"
    assert c1["employee_size"] == 500

    c2 = client.get("/api/customers?keyword=IMP-2").json()["items"][0]
    assert c2["customer_name"] == "全新客户"
    assert c2["industry"] == "金融"


def test_import_csv_dry_run(client, db_session):
    csv_bytes = b"customer_code,customer_name\nDRY-1,DRY One\n"
    r = client.post(
        "/api/customers/bulk/import.csv?dry_run=true",
        files={"file": ("x.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200
    assert r.json()["created"] == 1
    assert r.json()["dry_run"] is True

    # Nothing actually created
    r2 = client.get("/api/customers?keyword=DRY").json()
    assert r2["total"] == 0
