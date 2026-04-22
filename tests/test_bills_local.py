"""Tests for /api/bills/by-customer (本地聚合)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import CurrentUser, require_auth
from app.database import Base, get_db
from app.models.cc_bill import CCBill
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource
from app.models.sales import SalesUser
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
def seed(db_session):
    """账单聚合 fixture — 遵守新的 join 语义：
       customer → customer_resource → resource.identifier_field → cc_bill/cc_usage
    """
    c1 = Customer(id=1, customer_code="C001", customer_name="福星",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    c2 = Customer(id=2, customer_code="C002", customer_name="空客户",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    # resource.identifier_field 是云管 external_project_id，和 cc_bill.customer_code 一致
    r1 = Resource(id=5, resource_code="res-azure-1", resource_type="ORIGINAL",
                  cloud_provider="AZURE", account_name="ocid-prod",
                  identifier_field="proj-azure-001",
                  resource_status="active")
    r2 = Resource(id=8, resource_code="res-aws-1", resource_type="ORIGINAL",
                  cloud_provider="AWS", account_name="aws-main",
                  identifier_field="proj-aws-001",
                  resource_status="active")
    link1 = CustomerResource(customer_id=1, resource_id=5)
    link2 = CustomerResource(customer_id=1, resource_id=8)
    # cc_bill.customer_code 对齐到 resource.identifier_field
    b1 = CCBill(remote_id=1, month="2026-04", provider="AZURE",
                original_cost=Decimal("800"), final_cost=Decimal("800.00"),
                status="confirmed", customer_code="proj-azure-001")
    b2 = CCBill(remote_id=2, month="2026-04", provider="AWS",
                original_cost=Decimal("434.56"), final_cost=Decimal("434.56"),
                status="confirmed", customer_code="proj-aws-001")
    # cc_usage for day drill — 两条分别落在各自 identifier 上
    u1 = CCUsage(customer_code="proj-azure-001", date=date(2026, 4, 1),
                 total_cost=Decimal("100.00"), total_usage=Decimal("10"), record_count=5)
    u2 = CCUsage(customer_code="proj-aws-001", date=date(2026, 4, 2),
                 total_cost=Decimal("200.00"), total_usage=Decimal("20"), record_count=8)
    for x in (c1, c2, r1, r2, link1, link2, b1, b2, u1, u2):
        db_session.add(x)
    db_session.commit()


def test_by_customer_aggregates_linked_resources(client, seed):
    r = client.get("/api/bills/by-customer?month=2026-04")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1  # C002 has no links, excluded
    row = data[0]
    assert row["customer_id"] == 1
    assert row["customer_name"] == "福星"
    assert row["resource_count"] == 2
    assert row["total_cost"] == 1234.56
    res_map = {x["resource_id"]: x for x in row["resources"]}
    assert res_map[5]["cost"] == 800.00
    assert res_map[8]["cost"] == 434.56
    assert res_map[5]["cloud_provider"] == "AZURE"


def test_by_customer_empty_month(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12")
    assert r.status_code == 200
    # has links but no bills and no usage -> excluded by default
    assert r.json() == []


def test_by_customer_include_empty(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12&include_empty=true")
    assert r.status_code == 200
    data = r.json()
    # both customers returned, but C002 has no resources
    ids = {row["customer_id"] for row in data}
    assert 1 in ids


def test_drill_down_by_resource(client, seed):
    r = client.get("/api/bills/by-customer/1?month=2026-04&granularity=resource")
    assert r.status_code == 200
    data = r.json()
    assert data["granularity"] == "resource"
    assert data["total_cost"] == 1234.56
    assert len(data["items"]) == 2


def test_drill_down_by_day(client, seed):
    r = client.get("/api/bills/by-customer/1?month=2026-04&granularity=day")
    assert r.status_code == 200
    data = r.json()
    assert data["granularity"] == "day"
    assert data["total_cost"] == 300.00
    assert len(data["items"]) == 2
    assert data["items"][0]["date"] == "2026-04-01"


def test_drill_down_404_for_unknown_customer(client, seed):
    r = client.get("/api/bills/by-customer/999?month=2026-04")
    assert r.status_code == 404


def test_rejects_bad_month(client, seed):
    r = client.get("/api/bills/by-customer?month=not-a-month")
    assert r.status_code == 422


def test_by_customer_exposes_original_and_final_with_discount(client, db_session):
    """硬规则：每个货源行与客户汇总都要同时带原价、折扣率、折后价。"""
    c = Customer(id=10, customer_code="DISC", customer_name="折扣客户",
                 customer_status="active", lifecycle_stage="active", is_deleted=False)
    r = Resource(id=20, resource_code="res-disc", resource_type="ORIGINAL",
                 cloud_provider="AZURE", identifier_field="proj-disc-1",
                 resource_status="active")
    link = CustomerResource(customer_id=10, resource_id=20)
    # original 1000, final 750 → discount 25%
    b = CCBill(remote_id=100, month="2026-04", provider="AZURE",
               original_cost=Decimal("1000"), final_cost=Decimal("750"),
               status="confirmed", customer_code="proj-disc-1")
    for x in (c, r, link, b):
        db_session.add(x)
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    assert r_resp.status_code == 200
    row = next(x for x in r_resp.json() if x["customer_id"] == 10)
    # customer 级三元组
    assert row["total_original_cost"] == 1000.0
    assert row["total_final_cost"] == 750.0
    assert row["total_discount_rate"] == 0.25
    assert row["total_cost"] == 750.0  # 向后兼容别名
    # resource 级三元组
    res = row["resources"][0]
    assert res["original_cost"] == 1000.0
    assert res["final_cost"] == 750.0
    assert res["discount_rate"] == 0.25

    # 单客户下钻也要同三元组
    detail = client.get(
        f"/api/bills/by-customer/10?month=2026-04&granularity=resource",
    ).json()
    assert detail["total_original_cost"] == 1000.0
    assert detail["total_final_cost"] == 750.0
    assert detail["total_discount_rate"] == 0.25
    assert detail["items"][0]["discount_rate"] == 0.25


def test_customer_without_allocation_sees_nothing_even_if_code_matches(client, db_session):
    """业务规则 #3：无销售分配关系时，云管数据不归入该客户（哪怕 code 巧合）。"""
    c = Customer(id=30, customer_code="ACME", customer_name="ACME",
                 customer_status="active", is_deleted=False)
    # 故意不建 customer_resource；cc_bill.customer_code 巧和 customer.customer_code 同
    db_session.add(c)
    db_session.add(CCBill(
        remote_id=900, month="2026-04", provider="AZURE",
        original_cost=Decimal("1000"), final_cost=Decimal("900"),
        status="confirmed", customer_code="ACME",
    ))
    db_session.commit()
    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    assert r_resp.status_code == 200
    ids = {x["customer_id"] for x in r_resp.json()}
    assert 30 not in ids, "未分配的客户不应看到任何账单"


def test_by_customer_export_csv(client, seed):
    r = client.get("/api/bills/by-customer-export?month=2026-04")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "福星" in text
    assert "res-azure-1" in text
    assert "res-aws-1" in text


# ---------- 行级授权回归测试 ----------
#
# 回归历史 bug：`_sales_filter_clause` 之前用 `int(user.sub)` 强转 Casdoor UUID
# 必然抛 ValueError → 退化成 `Customer.id == -1` → 所有普通销售啥也看不见。
# 正确链路：user.sub → SalesUser.casdoor_user_id → SalesUser.id → Customer.sales_user_id。

def _override_as(user: CurrentUser):
    """上下文：把 require_auth 替换为返回指定 CurrentUser。"""
    app.dependency_overrides[require_auth] = lambda: user


def _reset_auth_override():
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture()
def seed_sales_scoped(db_session):
    """两个销售 + 两个客户，每人一个客户。"""
    alice = SalesUser(id=101, name="Alice",
                      casdoor_user_id="sub-uuid-alice", is_active=True)
    bob = SalesUser(id=102, name="Bob",
                    casdoor_user_id="sub-uuid-bob", is_active=True)
    # customer.sales_user_id = 本地 sales_user.id（不是 Casdoor sub）
    c_alice = Customer(id=201, customer_code="A01", customer_name="Alice 的客户",
                       customer_status="active", is_deleted=False, sales_user_id=101)
    c_bob = Customer(id=202, customer_code="B01", customer_name="Bob 的客户",
                     customer_status="active", is_deleted=False, sales_user_id=102)
    res = Resource(id=301, resource_code="res-1", resource_type="ORIGINAL",
                   cloud_provider="AZURE", identifier_field="proj-1",
                   resource_status="active")
    db_session.add_all([
        alice, bob, c_alice, c_bob, res,
        CustomerResource(customer_id=201, resource_id=301),
        CustomerResource(customer_id=202, resource_id=301),
        CCBill(remote_id=1, month="2026-04", provider="AZURE",
               original_cost=Decimal("100"), final_cost=Decimal("100"),
               status="confirmed", customer_code="proj-1"),
    ])
    db_session.commit()


def test_sales_with_uuid_sub_sees_own_customer(client, seed_sales_scoped):
    """Casdoor UUID sub 的销售通过 casdoor_user_id 反查能看到自己的客户。"""
    _override_as(CurrentUser(
        sub="sub-uuid-alice", name="alice", roles=["sales"], raw={},
    ))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        assert r.status_code == 200
        rows = r.json()
        ids = {x["customer_id"] for x in rows}
        assert ids == {201}, f"alice 只应看到自己的客户 201, 实际: {ids}"
    finally:
        _reset_auth_override()


def test_sales_not_in_sales_table_sees_nothing(client, seed_sales_scoped):
    """未建档的 Casdoor 用户以 sales 身份登录应返回空，而不是看到全部或崩溃。"""
    _override_as(CurrentUser(
        sub="sub-uuid-unknown", name="ghost", roles=["sales"], raw={},
    ))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        _reset_auth_override()


def test_sales_cannot_drill_other_customer(client, seed_sales_scoped):
    """alice 不能下钻 bob 的客户详情。"""
    _override_as(CurrentUser(
        sub="sub-uuid-alice", name="alice", roles=["sales"], raw={},
    ))
    try:
        own = client.get("/api/bills/by-customer/201?month=2026-04")
        assert own.status_code == 200
        other = client.get("/api/bills/by-customer/202?month=2026-04")
        assert other.status_code == 403
    finally:
        _reset_auth_override()


def test_sales_manager_sees_all(client, seed_sales_scoped):
    """sales-manager 不过滤 sales_user_id，看全部客户。"""
    _override_as(CurrentUser(
        sub="sub-uuid-manager", name="mgr", roles=["sales-manager"], raw={},
    ))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        assert r.status_code == 200
        ids = {x["customer_id"] for x in r.json()}
        assert ids == {201, 202}
    finally:
        _reset_auth_override()


def test_legacy_int_sub_fallback(client, db_session):
    """兼容老部署: 某些环境直接把整数 sub 当 sales_user.id 写入。"""
    # sales_user.id=501 但 casdoor_user_id 留空 → 走整数 fallback 分支
    db_session.add_all([
        SalesUser(id=501, name="Legacy", casdoor_user_id=None, is_active=True),
        Customer(id=601, customer_code="L01", customer_name="Legacy 客户",
                 customer_status="active", is_deleted=False, sales_user_id=501),
        Resource(id=701, resource_code="res-l", resource_type="ORIGINAL",
                 cloud_provider="AWS", identifier_field="proj-l",
                 resource_status="active"),
        CustomerResource(customer_id=601, resource_id=701),
        CCBill(remote_id=2, month="2026-04", provider="AWS",
               original_cost=Decimal("50"), final_cost=Decimal("50"),
               status="confirmed", customer_code="proj-l"),
    ])
    db_session.commit()

    _override_as(CurrentUser(sub="501", name="legacy", roles=["sales"], raw={}))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        assert r.status_code == 200
        ids = {x["customer_id"] for x in r.json()}
        assert 601 in ids
    finally:
        _reset_auth_override()
