"""Tests for /api/bills/export CSV endpoint."""
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
from app.models.cc_bill import CCBill
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
def seed(db_session):
    c1 = Customer(
        id=1, customer_code="C001", customer_name="阿里云客户A",
        customer_status="active", is_deleted=False,
    )
    c2 = Customer(
        id=2, customer_code="C002", customer_name="腾讯云客户B",
        customer_status="active", is_deleted=False,
    )
    b1 = CCBill(
        remote_id=1001, month="2026-04", provider="aliyun",
        original_cost=Decimal("100.00"), adjustment=Decimal("5.00"),
        final_cost=Decimal("105.00"), status="confirmed",
        customer_code="C001",
    )
    b2 = CCBill(
        remote_id=1002, month="2026-04", provider="tencent",
        original_cost=Decimal("200.00"), adjustment=Decimal("0.00"),
        final_cost=Decimal("200.00"), status="paid",
        customer_code="C002",
    )
    b3 = CCBill(
        remote_id=1003, month="2026-03", provider="aliyun",
        original_cost=Decimal("50.00"), final_cost=Decimal("50.00"),
        status="paid", customer_code="C001",
    )
    for x in (c1, c2, b1, b2, b3):
        db_session.add(x)
    db_session.commit()


def _parse_csv(content: str) -> tuple[list[str], list[list[str]]]:
    # Strip BOM if present
    if content.startswith("\ufeff"):
        content = content[1:]
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    return rows[0], rows[1:]


def test_export_csv_returns_csv_and_filters_by_month(client, seed):
    r = client.get("/api/bills/export?month=2026-04")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")

    header, data = _parse_csv(r.text)
    assert header == [
        "月份", "客户名称", "客户编号", "货源编号",
        "原始成本", "调价", "最终金额", "状态", "创建时间",
    ]
    # Only 2 rows for 2026-04
    assert len(data) == 2
    # customer_name is joined in from customer table
    names = {row[1] for row in data}
    assert names == {"阿里云客户A", "腾讯云客户B"}

    # Verify columns roughly
    a_row = next(r for r in data if r[2] == "C001")
    assert a_row[0] == "2026-04"
    assert a_row[1] == "阿里云客户A"
    assert a_row[4] == "100.00"
    assert a_row[5] == "5.00"
    assert a_row[6] == "105.00"
    assert a_row[7] == "confirmed"


def test_export_csv_filters_by_status(client, seed):
    r = client.get("/api/bills/export?month=2026-04&status=paid")
    assert r.status_code == 200
    _, data = _parse_csv(r.text)
    assert len(data) == 1
    assert data[0][2] == "C002"
    assert data[0][7] == "paid"


def test_export_csv_filters_by_customer_code(client, seed):
    r = client.get("/api/bills/export?month=2026-04&customer_code=C001")
    assert r.status_code == 200
    _, data = _parse_csv(r.text)
    assert len(data) == 1
    assert data[0][2] == "C001"
    assert data[0][1] == "阿里云客户A"


def test_export_csv_empty_month(client, seed):
    r = client.get("/api/bills/export?month=2099-12")
    assert r.status_code == 200
    _, data = _parse_csv(r.text)
    assert data == []


def test_export_csv_rejects_bad_month(client, seed):
    r = client.get("/api/bills/export?month=not-a-month")
    assert r.status_code == 422
