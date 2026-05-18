"""测试手工录入过往账单 API (含货币类型)."""
import pytest
from decimal import Decimal
from datetime import date


def test_create_manual_bill_with_currency(client, db_session, sample_customer):
    """测试新建过往账单时指定货币类型."""
    payload = {
        "title": "Q1 2026 账单",
        "amount": 5000.00,
        "currency": "CNY",
        "bill_date": "2026-03-31",
        "notes": "第一季度账单",
    }
    resp = client.post(
        f"/api/customers/{sample_customer.id}/manual-bills",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Q1 2026 账单"
    assert Decimal(str(data["amount"])) == Decimal("5000.00")
    assert data["currency"] == "CNY"
    assert data["bill_date"] == "2026-03-31"
    assert data["notes"] == "第一季度账单"


def test_create_manual_bill_default_currency(client, db_session, sample_customer):
    """测试新建过往账单时不指定货币，应默认为 USD."""
    payload = {
        "title": "默认货币账单",
        "amount": 1000.00,
    }
    resp = client.post(
        f"/api/customers/{sample_customer.id}/manual-bills",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "USD"


def test_update_manual_bill_currency(client, db_session, sample_customer):
    """测试更新过往账单的货币类型."""
    # 先创建
    payload = {
        "title": "测试账单",
        "amount": 2000.00,
        "currency": "USD",
    }
    resp = client.post(
        f"/api/customers/{sample_customer.id}/manual-bills",
        json=payload,
    )
    assert resp.status_code == 200
    bill_id = resp.json()["id"]

    # 更新货币
    update_payload = {
        "currency": "EUR",
        "amount": 1800.00,
    }
    resp = client.patch(
        f"/api/manual-bills/{bill_id}",
        json=update_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["currency"] == "EUR"
    assert Decimal(str(data["amount"])) == Decimal("1800.00")


def test_list_manual_bills_with_currency(client, db_session, sample_customer):
    """测试列出过往账单时包含货币信息."""
    # 创建多个不同货币的账单
    bills = [
        {"title": "USD 账单", "amount": 1000.00, "currency": "USD"},
        {"title": "CNY 账单", "amount": 5000.00, "currency": "CNY"},
        {"title": "EUR 账单", "amount": 800.00, "currency": "EUR"},
    ]
    for bill in bills:
        resp = client.post(
            f"/api/customers/{sample_customer.id}/manual-bills",
            json=bill,
        )
        assert resp.status_code == 200

    # 列出所有账单
    resp = client.get(f"/api/customers/{sample_customer.id}/manual-bills")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    # 验证每个账单都有货币字段
    currencies = {b["currency"] for b in data}
    assert currencies == {"USD", "CNY", "EUR"}
