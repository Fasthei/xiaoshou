"""Unit tests for integration clients (no real network)."""
import httpx
import pytest

from app.integrations.gongdan import GongdanClient, GongdanCustomer
from app.integrations.cloudcost import CloudCostClient, ServiceAccount


def test_gongdan_list_customers(monkeypatch):
    captured = {}

    def fake_get(self, url, headers=None, **kw):
        captured["url"] = url
        captured["headers"] = headers
        req = httpx.Request("GET", url)
        return httpx.Response(
            200, request=req,
            json=[
                {"id": "u1", "customerCode": "CUST-001", "name": "A", "tier": "KEY"},
                {"id": "u2", "customerCode": "CUST-002", "name": "B"},
            ],
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    c = GongdanClient("https://gongdan.example", "gd_live_xxx")
    items = c.list_customers()
    assert captured["url"].endswith("/api/customers")
    assert captured["headers"]["X-Api-Key"] == "gd_live_xxx"
    assert [i.customer_code for i in items] == ["CUST-001", "CUST-002"]
    assert isinstance(items[0], GongdanCustomer)


def test_gongdan_requires_key():
    c = GongdanClient("https://gongdan.example", "")
    with pytest.raises(RuntimeError):
        c.list_customers()


def test_cloudcost_resources_for_customer(monkeypatch):
    def fake_get(self, url, params=None, **kw):
        req = httpx.Request("GET", url)
        return httpx.Response(
            200, request=req,
            json=[
                {"id": 1, "name": "acc-1", "provider": "aws", "external_project_id": "CUST-001"},
                {"id": 2, "name": "acc-2", "provider": "azure", "external_project_id": "CUST-002"},
                {"id": 3, "name": "acc-3", "provider": "aws", "external_project_id": "CUST-001"},
            ],
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    c = CloudCostClient("https://cloudcost.example")
    out = c.resources_for_customer("CUST-001")
    assert [a.id for a in out] == [1, 3]
    assert all(isinstance(a, ServiceAccount) for a in out)


def test_cloudcost_match_field_override(monkeypatch):
    def fake_get(self, url, params=None, **kw):
        req = httpx.Request("GET", url)
        return httpx.Response(
            200, request=req,
            json=[
                {"id": 1, "name": "acc-1", "provider": "aws", "supplier_name": "长虹佳华"},
                {"id": 2, "name": "acc-2", "provider": "aws", "supplier_name": "其他"},
            ],
        )

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    c = CloudCostClient("https://cloudcost.example", match_field="supplier_name")
    out = c.resources_for_customer("长虹佳华")
    assert [a.id for a in out] == [1]
