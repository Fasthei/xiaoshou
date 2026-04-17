"""客户生命周期 stage 重构 — 端到端测试.

覆盖:
  - 建 customer 默认 lead
  - 跟进 -> 自动升 contacting
  - 创建 allocation -> customer 保持 contacting (不再自动升)
  - 审批 allocation -> customer 保持 contacting (stage 不受订单审批影响)
  - 申请 stage 变更 -> pending, customer 未变
  - 主管批 -> customer 更新
  - recycle -> 回 lead + 记录 recycled_from_stage
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.customer import Customer
from app.models.customer_stage_request import CustomerStageRequest
from app.models.resource import Resource
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


def _create_customer(client, code="C-ST1", name="Stage Test"):
    r = client.post("/api/customers", json={
        "customer_code": code, "customer_name": name, "customer_status": "potential",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- default stage ----------

def test_new_customer_defaults_to_lead(client, db_session):
    cid = _create_customer(client)
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"


# ---------- follow-up -> contacting ----------

def test_follow_up_auto_advances_to_contacting(client, db_session):
    cid = _create_customer(client)
    r = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "call", "title": "初次电话", "outcome": "positive",
    })
    assert r.status_code == 200, r.text
    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "contacting"

    # Audit row written
    audits = db_session.query(CustomerStageRequest).filter(
        CustomerStageRequest.customer_id == cid
    ).all()
    assert any(a.to_stage == "contacting" and a.decided_by == "system" for a in audits)


def test_second_follow_up_does_not_regress(client, db_session):
    cid = _create_customer(client)
    # Put customer directly at active
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    c.lifecycle_stage = "active"
    db_session.commit()

    client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "call", "title": "常规回访",
    })
    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "active"  # not regressed to contacting


# ---------- allocation -> order_pending / order_approved ----------

def _seed_resource(db, qty=100):
    r = Resource(
        resource_code="RES-1", resource_type="cloud",
        total_quantity=qty, allocated_quantity=0, available_quantity=qty,
        unit_cost=10, resource_status="AVAILABLE", is_deleted=False,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_create_allocation_does_not_change_stage(client, db_session):
    """销售创建订单不再自动升 stage，customer 保持原 stage."""
    cid = _create_customer(client)
    res = _seed_resource(db_session)

    r = client.post("/api/allocations", json={
        "customer_id": cid, "resource_id": res.id,
        "allocated_quantity": 5, "unit_price": 20,
    })
    assert r.status_code == 200, r.text
    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"  # unchanged


def test_allocation_approval_does_not_change_stage(client, db_session):
    """订单审批通过不影响 customer.lifecycle_stage，stage 由 gongdan sync 控制."""
    cid = _create_customer(client)
    res = _seed_resource(db_session)
    alloc = client.post("/api/allocations", json={
        "customer_id": cid, "resource_id": res.id,
        "allocated_quantity": 5, "unit_price": 20,
    }).json()

    r = client.patch(f"/api/allocations/{alloc['id']}/approval", json={
        "approval_status": "approved",
    })
    assert r.status_code == 200, r.text
    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"  # unchanged


# ---------- request / approve / reject ----------

def test_request_stage_change_creates_pending_does_not_apply(client, db_session):
    cid = _create_customer(client)
    r = client.post(f"/api/customers/{cid}/stage/request", json={
        "to_stage": "active", "reason": "客户已下大单",
    })
    assert r.status_code == 200, r.text
    req_id = r.json()["id"]
    assert r.json()["status"] == "pending"

    # customer.lifecycle_stage should still be 'lead'
    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"


def test_approve_stage_request_applies_change(client, db_session):
    cid = _create_customer(client)
    req = client.post(f"/api/customers/{cid}/stage/request", json={
        "to_stage": "active", "reason": "客户已下大单",
    }).json()

    r = client.post(f"/api/stage-requests/{req['id']}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"

    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "active"


def test_reject_stage_request(client, db_session):
    cid = _create_customer(client)
    req = client.post(f"/api/customers/{cid}/stage/request", json={
        "to_stage": "active",
    }).json()
    r = client.post(f"/api/stage-requests/{req['id']}/reject", json={"comment": "数据不足"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert r.json()["decision_comment"] == "数据不足"

    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"


# ---------- recycle ----------

def test_recycle_request_then_approve_resets_to_lead(client, db_session):
    cid = _create_customer(client)
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    c.lifecycle_stage = "contacting"
    db_session.commit()

    req = client.post(f"/api/customers/{cid}/recycle", json={
        "reason": "沟通多次无下文",
    }).json()
    assert req["status"] == "pending"
    assert req["to_stage"] == "lead"

    r = client.post(f"/api/stage-requests/{req['id']}/approve")
    assert r.status_code == 200

    db_session.expire_all()
    c = db_session.query(Customer).filter(Customer.id == cid).first()
    assert c.lifecycle_stage == "lead"
    assert c.recycled_from_stage == "contacting"
    assert c.recycle_reason == "沟通多次无下文"
    assert c.recycled_at is not None


def test_recycle_rejects_when_already_lead(client):
    cid = _create_customer(client)
    r = client.post(f"/api/customers/{cid}/recycle", json={"reason": "x"})
    assert r.status_code == 400


# ---------- history ----------

def test_stage_history_returns_audit_rows(client, db_session):
    cid = _create_customer(client)
    client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "call", "title": "t",
    })
    r = client.get(f"/api/customers/{cid}/stage-history")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["to_stage"] == "contacting"


# ---------- manager metrics dashboard ----------

def test_metrics_dashboard_smoke(client, db_session):
    # Seed a couple customers
    _create_customer(client, "M1", "A")
    cid2 = _create_customer(client, "M2", "B")
    c = db_session.query(Customer).filter(Customer.id == cid2).first()
    c.lifecycle_stage = "active"
    db_session.commit()

    r = client.get("/api/metrics/dashboard")
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("new_opportunities", "conversion_rate", "deal_rate",
              "growth_rate", "collection_rate"):
        assert k in data


def test_metrics_team_funnel_returns_list(client):
    r = client.get("/api/metrics/team-funnel")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_metrics_stage_alerts_returns_list(client):
    r = client.get("/api/metrics/stage-alerts")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
