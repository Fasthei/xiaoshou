"""Tests for /api/bills/by-customer — 新口径 (2026-04)

业务硬口径:
  原价   = cc_usage.total_cost (不再读 cc_bill)
  折扣率 = 最新 approved allocation.discount_rate (按 customer × resource)
  覆盖   = bill_adjustment 按 (customer, resource, month) 覆盖折扣 / 加手续费
  折后   = 原价 × (1 − 有效折扣率/100) + surcharge
"""
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
from app.models.allocation import Allocation
from app.models.bill_adjustment import BillAdjustment
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


def _usage(customer_code, d, cost):
    return CCUsage(
        customer_code=customer_code, date=d,
        total_cost=Decimal(str(cost)),
        total_usage=Decimal("0"),
        record_count=1,
    )


def _approved_alloc(customer_id, resource_id, discount_pct, code):
    return Allocation(
        allocation_code=code,
        customer_id=customer_id,
        resource_id=resource_id,
        allocated_quantity=1,
        allocation_status="PENDING",
        approval_status="approved",
        discount_rate=Decimal(str(discount_pct)),
    )


@pytest.fixture()
def seed(db_session):
    """硬规则 fixture：
    customer 1 分配了 2 个 resource (proj-azure-001 / proj-aws-001)，
    cc_usage 各自有当月金额；没有 allocation → 折扣率默认 0，折后=原价。
    """
    c1 = Customer(id=1, customer_code="C001", customer_name="福星",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    c2 = Customer(id=2, customer_code="C002", customer_name="空客户",
                  customer_status="active", lifecycle_stage="active", is_deleted=False)
    r1 = Resource(id=5, resource_code="res-azure-1", resource_type="ORIGINAL",
                  cloud_provider="AZURE", account_name="ocid-prod",
                  identifier_field="proj-azure-001",
                  resource_status="active")
    r2 = Resource(id=8, resource_code="res-aws-1", resource_type="ORIGINAL",
                  cloud_provider="AWS", account_name="aws-main",
                  identifier_field="proj-aws-001",
                  resource_status="active")
    db_session.add_all([
        c1, c2, r1, r2,
        CustomerResource(customer_id=1, resource_id=5),
        CustomerResource(customer_id=1, resource_id=8),
        _usage("proj-azure-001", date(2026, 4, 1), "100"),
        _usage("proj-azure-001", date(2026, 4, 2), "700"),  # 合计 800
        _usage("proj-aws-001",   date(2026, 4, 3), "434.56"),
    ])
    db_session.commit()


def test_by_customer_aggregates_usage_without_allocation(client, seed):
    """无订单时，折扣率=0，折后=原价=用量。"""
    r = client.get("/api/bills/by-customer?month=2026-04")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1  # C002 无分配关系
    row = data[0]
    assert row["customer_id"] == 1
    assert row["resource_count"] == 2
    assert row["total_original_cost"] == 1234.56
    assert row["total_final_cost"] == 1234.56
    assert row["total_discount_rate"] == 0.0
    res_map = {x["resource_id"]: x for x in row["resources"]}
    assert res_map[5]["original_cost"] == 800.0
    assert res_map[5]["final_cost"] == 800.0
    assert res_map[5]["has_allocation"] is False


def test_by_customer_empty_month(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12")
    assert r.status_code == 200
    assert r.json() == []


def test_by_customer_include_empty(client, seed):
    r = client.get("/api/bills/by-customer?month=2099-12&include_empty=true")
    assert r.status_code == 200
    data = r.json()
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
    # 3 条 cc_usage 横跨 3 天
    assert len(data["items"]) == 3
    assert data["total_cost"] == 1234.56


def test_drill_down_404_for_unknown_customer(client, seed):
    r = client.get("/api/bills/by-customer/999?month=2026-04")
    assert r.status_code == 404


def test_rejects_bad_month(client, seed):
    r = client.get("/api/bills/by-customer?month=not-a-month")
    assert r.status_code == 422


def test_allocation_discount_applies(client, db_session):
    """有 approved allocation 时，折扣率生效。
    原价 1000 + 订单折扣 25% → 折后 750。
    """
    c = Customer(id=10, customer_code="DISC", customer_name="折扣客户",
                 customer_status="active", lifecycle_stage="active", is_deleted=False)
    r = Resource(id=20, resource_code="res-disc", resource_type="ORIGINAL",
                 cloud_provider="AZURE", identifier_field="proj-disc-1",
                 resource_status="active")
    db_session.add_all([
        c, r,
        CustomerResource(customer_id=10, resource_id=20),
        _usage("proj-disc-1", date(2026, 4, 1), "1000"),
        _approved_alloc(customer_id=10, resource_id=20, discount_pct="25", code="A1"),
    ])
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    assert r_resp.status_code == 200
    row = next(x for x in r_resp.json() if x["customer_id"] == 10)
    assert row["total_original_cost"] == 1000.0
    assert row["total_final_cost"] == 750.0
    assert row["total_discount_rate"] == 0.25
    res = row["resources"][0]
    assert res["original_cost"] == 1000.0
    assert res["final_cost"] == 750.0
    assert res["discount_rate"] == 0.25
    assert res["discount_rate_pct"] == 25.0
    assert res["has_allocation"] is True
    assert res["has_adjustment"] is False


def test_bill_adjustment_override_overrides_order_discount(client, db_session):
    """bill_adjustment.discount_rate_override 优先于订单折扣。
    订单 25% + 覆盖 10% → 有效 10%。
    """
    c = Customer(id=11, customer_code="OVR", customer_name="覆盖客户",
                 customer_status="active", is_deleted=False)
    r = Resource(id=21, resource_code="res-ovr", resource_type="ORIGINAL",
                 cloud_provider="AWS", identifier_field="proj-ovr",
                 resource_status="active")
    db_session.add_all([
        c, r,
        CustomerResource(customer_id=11, resource_id=21),
        _usage("proj-ovr", date(2026, 4, 15), "1000"),
        _approved_alloc(customer_id=11, resource_id=21, discount_pct="25", code="A2"),
        BillAdjustment(
            customer_id=11, resource_id=21, month="2026-04",
            discount_rate_override=Decimal("10"),  # 覆盖成 10%
            surcharge=None, notes="账单修正",
        ),
    ])
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    row = next(x for x in r_resp.json() if x["customer_id"] == 11)
    assert row["total_original_cost"] == 1000.0
    assert row["total_final_cost"] == 900.0        # 1000 × 0.9
    assert row["total_discount_rate"] == 0.1
    res = row["resources"][0]
    assert res["discount_rate_pct"] == 25.0         # 订单折扣原值
    assert res["discount_override"] == 10.0          # 覆盖值
    assert res["has_adjustment"] is True


def test_bill_adjustment_surcharge_added_to_final(client, db_session):
    """surcharge 直接加在折后价上；可正可负。"""
    c = Customer(id=12, customer_code="SUR", customer_name="手续费客户",
                 customer_status="active", is_deleted=False)
    r = Resource(id=22, resource_code="res-sur", resource_type="ORIGINAL",
                 cloud_provider="GCP", identifier_field="proj-sur",
                 resource_status="active")
    db_session.add_all([
        c, r,
        CustomerResource(customer_id=12, resource_id=22),
        _usage("proj-sur", date(2026, 4, 1), "1000"),
        _approved_alloc(customer_id=12, resource_id=22, discount_pct="10", code="A3"),
        BillAdjustment(
            customer_id=12, resource_id=22, month="2026-04",
            discount_rate_override=None,  # 沿用订单 10%
            surcharge=Decimal("50"), notes="开票手续费",
        ),
    ])
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    row = next(x for x in r_resp.json() if x["customer_id"] == 12)
    # 1000 × 0.9 + 50 = 950
    assert row["total_final_cost"] == 950.0
    res = row["resources"][0]
    assert res["surcharge"] == 50.0


def test_non_approved_allocation_ignored(client, db_session):
    """pending 订单不参与折扣率计算。"""
    c = Customer(id=13, customer_code="PEND", customer_name="待审批",
                 customer_status="active", is_deleted=False)
    r = Resource(id=23, resource_code="res-pend", resource_type="ORIGINAL",
                 cloud_provider="AZURE", identifier_field="proj-pend",
                 resource_status="active")
    # pending 订单 discount=30%，但不生效
    pending_alloc = Allocation(
        allocation_code="P1",
        customer_id=13, resource_id=23, allocated_quantity=1,
        allocation_status="PENDING",
        approval_status="pending",
        discount_rate=Decimal("30"),
    )
    db_session.add_all([
        c, r,
        CustomerResource(customer_id=13, resource_id=23),
        _usage("proj-pend", date(2026, 4, 1), "100"),
        pending_alloc,
    ])
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    row = next(x for x in r_resp.json() if x["customer_id"] == 13)
    assert row["total_final_cost"] == 100.0   # 无折扣
    assert row["resources"][0]["has_allocation"] is False


def test_latest_approved_allocation_wins(client, db_session):
    """同一 (customer, resource) 多条 approved → 取 approved_at 最新那条。"""
    from datetime import datetime as _dt
    c = Customer(id=14, customer_code="LATE", customer_name="多订单",
                 customer_status="active", is_deleted=False)
    r = Resource(id=24, resource_code="res-late", resource_type="ORIGINAL",
                 cloud_provider="AWS", identifier_field="proj-late",
                 resource_status="active")
    old_alloc = Allocation(
        allocation_code="OLD",
        customer_id=14, resource_id=24, allocated_quantity=1,
        allocation_status="PENDING", approval_status="approved",
        discount_rate=Decimal("5"),
        approved_at=_dt(2026, 1, 1),
    )
    new_alloc = Allocation(
        allocation_code="NEW",
        customer_id=14, resource_id=24, allocated_quantity=1,
        allocation_status="PENDING", approval_status="approved",
        discount_rate=Decimal("20"),
        approved_at=_dt(2026, 3, 1),
    )
    db_session.add_all([
        c, r,
        CustomerResource(customer_id=14, resource_id=24),
        _usage("proj-late", date(2026, 4, 1), "1000"),
        old_alloc, new_alloc,
    ])
    db_session.commit()

    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    row = next(x for x in r_resp.json() if x["customer_id"] == 14)
    assert row["total_final_cost"] == 800.0  # 1000 × 0.80 (取最新 20%)


def test_customer_without_allocation_link_sees_nothing(client, db_session):
    """未建 customer_resource 时，哪怕同名也不归属。"""
    c = Customer(id=30, customer_code="ACME", customer_name="ACME",
                 customer_status="active", is_deleted=False)
    db_session.add_all([
        c,
        _usage("ACME", date(2026, 4, 1), "500"),  # 同名但无分配关系
    ])
    db_session.commit()
    r_resp = client.get("/api/bills/by-customer?month=2026-04")
    ids = {x["customer_id"] for x in r_resp.json()}
    assert 30 not in ids


def test_by_customer_export_csv(client, seed):
    r = client.get("/api/bills/by-customer-export?month=2026-04")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert "福星" in text
    assert "res-azure-1" in text
    assert "res-aws-1" in text


# ---------- 行级授权回归 ----------

def _override_as(user: CurrentUser):
    app.dependency_overrides[require_auth] = lambda: user


def _reset_auth_override():
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture()
def seed_sales_scoped(db_session):
    """两个销售各一客户，每人一条 cc_usage。"""
    alice = SalesUser(id=101, name="Alice",
                      casdoor_user_id="sub-uuid-alice", is_active=True)
    bob = SalesUser(id=102, name="Bob",
                    casdoor_user_id="sub-uuid-bob", is_active=True)
    c_alice = Customer(id=201, customer_code="A01", customer_name="Alice 的客户",
                       customer_status="active", is_deleted=False, sales_user_id=101)
    c_bob = Customer(id=202, customer_code="B01", customer_name="Bob 的客户",
                     customer_status="active", is_deleted=False, sales_user_id=102)
    r_alice = Resource(id=301, resource_code="res-a1", resource_type="ORIGINAL",
                       cloud_provider="AZURE", identifier_field="proj-alice",
                       resource_status="active")
    r_bob = Resource(id=302, resource_code="res-b1", resource_type="ORIGINAL",
                     cloud_provider="AWS", identifier_field="proj-bob",
                     resource_status="active")
    db_session.add_all([
        alice, bob, c_alice, c_bob, r_alice, r_bob,
        CustomerResource(customer_id=201, resource_id=301),
        CustomerResource(customer_id=202, resource_id=302),
        _usage("proj-alice", date(2026, 4, 1), "100"),
        _usage("proj-bob", date(2026, 4, 1), "200"),
    ])
    db_session.commit()


def test_sales_with_uuid_sub_sees_own_customer(client, seed_sales_scoped):
    _override_as(CurrentUser(
        sub="sub-uuid-alice", name="alice", roles=["sales"], raw={},
    ))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        assert r.status_code == 200
        ids = {x["customer_id"] for x in r.json()}
        assert ids == {201}
    finally:
        _reset_auth_override()


def test_sales_not_in_sales_table_sees_nothing(client, seed_sales_scoped):
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
    _override_as(CurrentUser(
        sub="sub-uuid-manager", name="mgr", roles=["sales-manager"], raw={},
    ))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        ids = {x["customer_id"] for x in r.json()}
        assert ids == {201, 202}
    finally:
        _reset_auth_override()


def test_legacy_int_sub_fallback(client, db_session):
    db_session.add_all([
        SalesUser(id=501, name="Legacy", casdoor_user_id=None, is_active=True),
        Customer(id=601, customer_code="L01", customer_name="Legacy 客户",
                 customer_status="active", is_deleted=False, sales_user_id=501),
        Resource(id=701, resource_code="res-l", resource_type="ORIGINAL",
                 cloud_provider="AWS", identifier_field="proj-l",
                 resource_status="active"),
        CustomerResource(customer_id=601, resource_id=701),
        _usage("proj-l", date(2026, 4, 1), "50"),
    ])
    db_session.commit()

    _override_as(CurrentUser(sub="501", name="legacy", roles=["sales"], raw={}))
    try:
        r = client.get("/api/bills/by-customer?month=2026-04")
        ids = {x["customer_id"] for x in r.json()}
        assert 601 in ids
    finally:
        _reset_auth_override()
