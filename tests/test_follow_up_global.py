"""Global follow-up list endpoint tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.follow_up import CustomerFollowUp
from app.models.sales import SalesUser
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


def test_global_follow_ups_returns_all(client, db_session):
    """两个客户各加一条跟进，全局接口返回 total=2。"""
    cid1 = client.post("/api/customers", json={
        "customer_code": "GFU-1", "customer_name": "全局客户甲", "customer_status": "active",
    }).json()["id"]
    cid2 = client.post("/api/customers", json={
        "customer_code": "GFU-2", "customer_name": "全局客户乙", "customer_status": "active",
    }).json()["id"]

    client.post(f"/api/customers/{cid1}/follow-ups", json={
        "kind": "call", "title": "电话1", "content": "沟通产品方案",
    })
    client.post(f"/api/customers/{cid2}/follow-ups", json={
        "kind": "email", "title": "邮件1", "content": "发送报价单",
    })

    r = client.get("/api/follow-ups?days=30")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_global_follow_ups_filter_by_customer(client, db_session):
    """按 customer_id 过滤只返回该客户的跟进。"""
    cid1 = client.post("/api/customers", json={
        "customer_code": "GFU-A", "customer_name": "过滤甲", "customer_status": "active",
    }).json()["id"]
    cid2 = client.post("/api/customers", json={
        "customer_code": "GFU-B", "customer_name": "过滤乙", "customer_status": "active",
    }).json()["id"]

    client.post(f"/api/customers/{cid1}/follow-ups", json={
        "kind": "note", "title": "甲的备注",
    })
    client.post(f"/api/customers/{cid2}/follow-ups", json={
        "kind": "note", "title": "乙的备注",
    })

    r = client.get(f"/api/follow-ups?days=30&customer_id={cid1}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["customer_id"] == cid1
    assert data["items"][0]["customer_name"] == "过滤甲"


# ---------- inbox filter by to_sales_user_id ----------

def test_inbox_filters_by_to_sales_user_id(client, db_session):
    """收件箱只返回 to_sales_user_id=当前用户对应 sales_user.id 的留言。

    AUTH_ENABLED=false 时 require_auth 返回 CurrentUser(sub='dev')。
    因此在 DB 中建一个 casdoor_user_id='dev' 的 SalesUser (id=1)，
    inbox 应只看到 to_sales_user_id=1 的 2 条，不含 to=2 的第 3 条。
    """
    # Create sales user whose casdoor_user_id matches the dev token sub='dev'
    su1 = SalesUser(name="Dev User", is_active=True, casdoor_user_id="dev")
    su2 = SalesUser(name="Other User", is_active=True, casdoor_user_id="other")
    db_session.add_all([su1, su2])
    db_session.commit()
    db_session.refresh(su1)
    db_session.refresh(su2)

    # Create a customer to attach follow-ups to
    cid = client.post("/api/customers", json={
        "customer_code": "INBOX-C1", "customer_name": "收件箱客户", "customer_status": "active",
    }).json()["id"]

    # Insert follow-ups directly in DB to control to_sales_user_id precisely
    fu1 = CustomerFollowUp(
        customer_id=cid, kind="note", title="给我的留言1",
        to_sales_user_id=su1.id,
    )
    fu2 = CustomerFollowUp(
        customer_id=cid, kind="note", title="给我的留言2",
        to_sales_user_id=su1.id,
    )
    fu3 = CustomerFollowUp(
        customer_id=cid, kind="note", title="给另一个人的留言",
        to_sales_user_id=su2.id,
    )
    db_session.add_all([fu1, fu2, fu3])
    db_session.commit()

    r = client.get("/api/follow-ups/inbox")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    for item in data["items"]:
        assert item["to_sales_user_id"] == su1.id


# ---------- reply creates thread ----------

def test_reply_creates_thread(client, db_session):
    """创建 follow_up A，再创建 parent_follow_up_id=A.id 的 follow_up B；
    查询客户跟进列表时 B 的 parent_follow_up_id 应指向 A.id。
    """
    cid = client.post("/api/customers", json={
        "customer_code": "THREAD-C1", "customer_name": "线程测试客户", "customer_status": "active",
    }).json()["id"]

    # Create parent follow-up A
    resp_a = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "note", "title": "原帖A", "content": "问题描述",
    })
    assert resp_a.status_code == 200, resp_a.text
    a_id = resp_a.json()["id"]

    # Create reply B with parent_follow_up_id pointing to A
    resp_b = client.post(f"/api/customers/{cid}/follow-ups", json={
        "kind": "comment", "title": "回复B", "content": "回复内容",
        "parent_follow_up_id": a_id,
    })
    assert resp_b.status_code == 200, resp_b.text
    b_data = resp_b.json()
    b_id = b_data["id"]
    assert b_data["parent_follow_up_id"] == a_id

    # Fetch the follow-up list for this customer; B should appear with parent_follow_up_id=A
    r = client.get(f"/api/customers/{cid}/follow-ups")
    assert r.status_code == 200, r.text
    items = r.json()

    # Find B in the list
    b_in_list = next((item for item in items if item["id"] == b_id), None)
    assert b_in_list is not None, "Reply B not found in follow-up list"
    assert b_in_list["parent_follow_up_id"] == a_id

    # Find A in the list as well (it exists as a separate row)
    a_in_list = next((item for item in items if item["id"] == a_id), None)
    assert a_in_list is not None, "Parent A not found in follow-up list"
