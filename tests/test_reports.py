"""Tests for /api/reports/* endpoints.

Covers:
1. sales-trend dim=month 聚合正确
2. profit-analysis 切片（breakdown=customer_level）
3. funnel 转化率计算
4. export csv 第一行是表头 + 行数对得上
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.customer_stage_request import CustomerStageRequest
from app.models.resource import Resource
from main import app


# ──────────────────────────────────────────────
# fixtures
# ──────────────────────────────────────────────

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
    """Seed two customers (different levels/industry) + two allocations in different months."""
    r1 = Resource(
        resource_code="R001", resource_type="ORIGINAL",
        resource_status="AVAILABLE", is_deleted=False,
    )
    db_session.add(r1)
    db_session.flush()

    c1 = Customer(
        customer_name="客户Alpha", customer_status="active",
        lifecycle_stage="active", is_deleted=False,
        industry="科技", region="华东", customer_level="A",
    )
    c2 = Customer(
        customer_name="客户Beta", customer_status="active",
        lifecycle_stage="contacting", is_deleted=False,
        industry="金融", region="华北", customer_level="B",
    )
    c3 = Customer(
        customer_name="客户Gamma", customer_status="active",
        lifecycle_stage="lead", is_deleted=False,
        industry="科技", region="华南", customer_level="A",
    )
    db_session.add_all([c1, c2, c3])
    db_session.flush()

    # 2026-03 allocation for c1
    a1 = Allocation(
        allocation_code="A001",
        customer_id=c1.id,
        resource_id=r1.id,
        allocated_quantity=10,
        total_cost=Decimal("80.00"),
        total_price=Decimal("100.00"),
        profit_amount=Decimal("20.00"),
        profit_rate=Decimal("20.00"),
        allocation_status="approved",
        allocated_at=datetime(2026, 3, 15),
        is_deleted=False,
    )
    # 2026-04 allocation for c1
    a2 = Allocation(
        allocation_code="A002",
        customer_id=c1.id,
        resource_id=r1.id,
        allocated_quantity=5,
        total_cost=Decimal("40.00"),
        total_price=Decimal("60.00"),
        profit_amount=Decimal("20.00"),
        profit_rate=Decimal("33.33"),
        allocation_status="approved",
        allocated_at=datetime(2026, 4, 10),
        is_deleted=False,
    )
    # 2026-04 allocation for c2 (different customer)
    a3 = Allocation(
        allocation_code="A003",
        customer_id=c2.id,
        resource_id=r1.id,
        allocated_quantity=8,
        total_cost=Decimal("150.00"),
        total_price=Decimal("200.00"),
        profit_amount=Decimal("50.00"),
        profit_rate=Decimal("25.00"),
        allocation_status="approved",
        allocated_at=datetime(2026, 4, 20),
        is_deleted=False,
    )
    db_session.add_all([a1, a2, a3])
    db_session.commit()
    return {"c1": c1, "c2": c2, "c3": c3, "a1": a1, "a2": a2, "a3": a3}


# ──────────────────────────────────────────────
# 1. sales-trend dim=month
# ──────────────────────────────────────────────

def test_sales_trend_month_aggregation(client, seed):
    """dim=month 应按月份聚合，2026-03 和 2026-04 分开，金额对得上。"""
    r = client.get("/api/reports/sales-trend?dim=month")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

    by_month = {row["label"]: row for row in data}
    assert "2026-03" in by_month
    assert "2026-04" in by_month

    mar = by_month["2026-03"]
    assert mar["total_sales"] == 100.0
    assert mar["total_profit"] == 20.0
    assert mar["count"] == 1

    apr = by_month["2026-04"]
    assert apr["total_sales"] == pytest.approx(260.0)   # 60 + 200
    assert apr["total_profit"] == pytest.approx(70.0)   # 20 + 50
    assert apr["count"] == 2


def test_sales_trend_date_filter(client, seed):
    """from/to 参数应正确过滤。"""
    r = client.get("/api/reports/sales-trend?dim=month&from=2026-04-01&to=2026-05-01")
    assert r.status_code == 200
    data = r.json()
    labels = [row["label"] for row in data]
    assert "2026-03" not in labels
    assert "2026-04" in labels


def test_sales_trend_dim_industry(client, seed):
    """dim=industry 应按行业聚合。"""
    r = client.get("/api/reports/sales-trend?dim=industry")
    assert r.status_code == 200
    data = r.json()
    by_industry = {row["label"]: row for row in data}
    # 科技: a1(100) + a2(60) = 160; 金融: a3(200)
    assert "科技" in by_industry
    assert "金融" in by_industry
    assert by_industry["科技"]["total_sales"] == pytest.approx(160.0)
    assert by_industry["金融"]["total_sales"] == pytest.approx(200.0)


# ──────────────────────────────────────────────
# 2. profit-analysis breakdown
# ──────────────────────────────────────────────

def test_profit_analysis_breakdown_customer_level(client, seed):
    """breakdown=customer_level 应按客户级别拆解利润。"""
    r = client.get("/api/reports/profit-analysis?dim=month&breakdown=customer_level")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

    # A 级客户：c1 两条（profit 20+20=40），B 级客户：c2 一条（profit 50）
    level_totals: dict[str, float] = {}
    for row in data:
        bd = row["breakdown_label"]
        level_totals[bd] = level_totals.get(bd, 0.0) + row["profit_amount"]

    assert level_totals.get("A", 0.0) == pytest.approx(40.0)
    assert level_totals.get("B", 0.0) == pytest.approx(50.0)


def test_profit_analysis_has_profit_rate(client, seed):
    """每行应包含 profit_rate 字段。"""
    r = client.get("/api/reports/profit-analysis?dim=month")
    assert r.status_code == 200
    data = r.json()
    for row in data:
        assert "profit_rate" in row
        assert isinstance(row["profit_rate"], float)


# ──────────────────────────────────────────────
# 3. funnel
# ──────────────────────────────────────────────

def _funnel_by_stage(resp_json):
    """新口径：funnel 返回 list[{stage, count, rate}]；把它索引回 dict 方便断言."""
    return {item["stage"]: item for item in resp_json}


def test_funnel_stage_counts(client, seed):
    """漏斗应正确统计各 stage 数量。seed 有: active=1, contacting=1, lead=1。"""
    r = client.get("/api/reports/funnel")
    assert r.status_code == 200
    by_stage = _funnel_by_stage(r.json())
    assert by_stage["lead"]["count"] == 1
    assert by_stage["contacting"]["count"] == 1
    assert by_stage["active"]["count"] == 1


def test_funnel_conversion_rates(client, seed):
    """lead_to_contacting_rate = (contacting+active)/(total) * 100 = 2/3 * 100 ≈ 66.67。"""
    r = client.get("/api/reports/funnel")
    assert r.status_code == 200
    by_stage = _funnel_by_stage(r.json())
    # contacting 行 rate = lead_to_contacting_rate
    assert by_stage["contacting"]["rate"] == pytest.approx(66.67, abs=0.1)
    # active 行 rate = contacting_to_active_rate
    assert by_stage["active"]["rate"] == pytest.approx(50.0, abs=0.1)


def test_funnel_avg_days_with_stage_requests(client, db_session, seed):
    """avg_lead_to_active_days 应根据 stage request 历史计算。"""
    c1 = seed["c1"]
    # Add stage requests: lead→contacting approved on 2026-01-01, contacting→active on 2026-01-11 → 10 days
    sr1 = CustomerStageRequest(
        customer_id=c1.id,
        from_stage="lead", to_stage="contacting",
        status="approved",
        decided_at=datetime(2026, 1, 1),
    )
    sr2 = CustomerStageRequest(
        customer_id=c1.id,
        from_stage="contacting", to_stage="active",
        status="approved",
        decided_at=datetime(2026, 1, 11),
    )
    db_session.add_all([sr1, sr2])
    db_session.commit()

    r = client.get("/api/reports/funnel")
    assert r.status_code == 200
    by_stage = _funnel_by_stage(r.json())
    assert by_stage["avg_lead_to_active_days"]["count"] == pytest.approx(10.0, abs=0.5)


# ──────────────────────────────────────────────
# 4. export CSV
# ──────────────────────────────────────────────

def _parse_csv(content: str) -> tuple[list[str], list[list[str]]]:
    if content.startswith("\ufeff"):
        content = content[1:]
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return [], []
    return rows[0], rows[1:]


def test_export_csv_sales_trend_header_and_rows(client, seed):
    """export?type=sales-trend 应返回 CSV，第一行是表头，数据行数对得上。"""
    r = client.get("/api/reports/export?type=sales-trend&format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]

    header, data = _parse_csv(r.text)
    assert header == ["维度标签", "销售额", "利润", "笔数"]
    # seed has 2 months: 2026-03 and 2026-04
    assert len(data) == 2


def test_export_csv_profit_analysis_header(client, seed):
    """export?type=profit 应返回利润分析表头。"""
    r = client.get("/api/reports/export?type=profit&format=csv")
    assert r.status_code == 200
    header, data = _parse_csv(r.text)
    assert header == ["维度标签", "拆解标签", "总成本", "总售价", "利润金额", "利润率(%)"]
    assert len(data) >= 1


def test_export_csv_funnel_header(client, seed):
    """export?type=funnel 应返回漏斗表头。"""
    r = client.get("/api/reports/export?type=funnel&format=csv")
    assert r.status_code == 200
    header, data = _parse_csv(r.text)
    assert header == ["阶段", "数量", "转化率(%)"]
    assert len(data) == 4  # lead, contacting, active, avg_lead_to_active_days


def test_export_csv_yoy_header(client, seed):
    """export?type=yoy 应返回 YoY 表头。"""
    r = client.get("/api/reports/export?type=yoy&format=csv")
    assert r.status_code == 200
    header, data = _parse_csv(r.text)
    assert header == ["周期", "当期", "上期", "同比(%)", "环比(%)"]
    assert len(data) >= 1


def test_export_csv_rejects_xlsx(client, seed):
    """format=xlsx 应返回 400。"""
    r = client.get("/api/reports/export?type=sales-trend&format=xlsx")
    assert r.status_code == 400


def test_export_csv_rejects_unknown_type(client, seed):
    """未知 type 应返回 400。"""
    r = client.get("/api/reports/export?type=unknown&format=csv")
    assert r.status_code == 400
