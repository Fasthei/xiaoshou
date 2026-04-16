"""Verify that bridge / trend / customer_resources return a graceful 502 JSON
instead of a blank 500 / Bad Gateway when cloudcost is unhappy.

Covers four cloudcost failure modes:
  1. connection timeout
  2. upstream 500
  3. non-JSON body
  4. JSON but missing expected keys

Matches task STEP 3 acceptance criteria:
  response.status_code == 502
  response.json()["detail"] contains "云管"
"""
from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import bridge, trend, customer_resources
from app.integrations import cloudcost as cc_module
from app.integrations.cloudcost import CloudCostClient


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _patch_httpx_client(monkeypatch, handler: Callable[[httpx.Request], httpx.Response]):
    """Force every CloudCostClient._client() call to use a MockTransport."""
    transport = httpx.MockTransport(handler)

    def fake_client(self):  # noqa: ANN001
        return httpx.Client(transport=transport, headers=self._headers(), timeout=self.timeout)

    monkeypatch.setattr(CloudCostClient, "_client", fake_client)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(bridge.router)
    app.include_router(trend.router)
    app.include_router(customer_resources.router)
    return app


@pytest.fixture
def client(monkeypatch):
    # Point settings at a dummy endpoint — we never hit the network thanks to MockTransport.
    monkeypatch.setenv("CLOUDCOST_ENDPOINT", "https://cc.example")
    # Bust the settings lru_cache so our env override is picked up.
    from app.config import get_settings
    get_settings.cache_clear()
    return TestClient(_build_app())


# --------------------------------------------------------------------------- #
# Failure-mode tests                                                          #
# --------------------------------------------------------------------------- #


def test_bridge_alerts_timeout_returns_502(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout", request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/bridge/alerts?month=2026-04")
    assert r.status_code == 502, r.text
    body = r.json()
    assert "云管" in body["detail"]
    assert "ConnectTimeout" in body["detail"]


def test_bridge_bills_upstream_500_returns_502(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream exploded", request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/bridge/bills?month=2026-04&page_size=100")
    assert r.status_code == 502, r.text
    body = r.json()
    assert "云管" in body["detail"]
    # httpx raises HTTPStatusError on raise_for_status()
    assert "HTTPStatusError" in body["detail"] or "HTTPError" in body["detail"]


def test_bridge_alerts_non_json_returns_502(client, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<html>I am not JSON</html>",
            request=request,
        )

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/bridge/alerts?month=2026-04")
    assert r.status_code == 502, r.text
    body = r.json()
    assert "云管" in body["detail"]
    assert "DecodingError" in body["detail"] or "JSONDecodeError" in body["detail"]


def test_bridge_dashboard_missing_keys_returns_200_empty(client, monkeypatch):
    """Missing ``trend`` key should degrade gracefully; dashboard itself
    returns whatever cloudcost sent, since it's a pass-through."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hello": "world"}, request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/bridge/dashboard?month=2026-04")
    assert r.status_code == 200
    assert r.json() == {"hello": "world"}


def test_trend_daily_missing_keys_returns_empty_list(client, monkeypatch):
    """Trend endpoint should gracefully return [] when ``trend`` key is absent."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"something_else": [1, 2, 3]}, request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/trend/daily?days=14")
    assert r.status_code == 200
    assert r.json() == []


def test_trend_daily_upstream_401_returns_502(client, monkeypatch):
    """The production root-cause: cloudcost started enforcing auth → 401."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"}, request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/trend/daily?days=14")
    assert r.status_code == 502, r.text
    body = r.json()
    assert "云管" in body["detail"]


def test_trend_daily_non_dict_bundle_returns_empty_list(client, monkeypatch):
    """If cloudcost returns a top-level list instead of dict, CloudCostClient
    coerces it to ``{}`` so the handler degrades to an empty trend list
    rather than 500."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3], request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get("/api/trend/daily?days=14")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_cloudcost_client_sends_auth_headers(monkeypatch):
    """Verify the client forwards API key / bearer token when env provides them."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=[], request=request)

    monkeypatch.setenv("CLOUDCOST_API_KEY", "cc_live_xxx")
    monkeypatch.setenv("CLOUDCOST_M2M_TOKEN", "ey.test.jwt")

    transport = httpx.MockTransport(handler)
    client = CloudCostClient("https://cc.example")

    def fake_client(self):  # noqa: ANN001
        return httpx.Client(transport=transport, headers=self._headers(), timeout=self.timeout)

    monkeypatch.setattr(CloudCostClient, "_client", fake_client)
    client.alerts_rule_status("2026-04")
    assert captured["headers"].get("x-api-key") == "cc_live_xxx"
    assert captured["headers"].get("authorization") == "Bearer ey.test.jwt"


def test_cloudcost_client_forwards_explicit_bearer(monkeypatch):
    """Explicit bearer_token (e.g. user's Casdoor JWT) wins over env M2M token.

    Production scenario: cloudcost has AUTH_ENFORCED=true and shares Casdoor
    with xiaoshou. Bridge/trend/customer_resources handlers extract the caller's
    Authorization header and forward it via bearer_token=; this must win.
    """
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=[], request=request)

    # Env M2M still set — the user bearer MUST still win.
    monkeypatch.setenv("CLOUDCOST_M2M_TOKEN", "ey.m2m.should-be-ignored")

    transport = httpx.MockTransport(handler)
    client = CloudCostClient("https://cc.example", bearer_token="ey.user.casdoor.jwt")

    def fake_client(self):  # noqa: ANN001
        return httpx.Client(transport=transport, headers=self._headers(), timeout=self.timeout)

    monkeypatch.setattr(CloudCostClient, "_client", fake_client)
    client.alerts_rule_status("2026-04")
    assert captured["headers"].get("authorization") == "Bearer ey.user.casdoor.jwt"


def test_bridge_alerts_forwards_caller_bearer_to_cloudcost(client, monkeypatch):
    """End-to-end: /api/bridge/alerts must forward the incoming Authorization
    header to cloudcost. This is the exact bug that caused 4 routes to 502 in
    production after cloudcost enabled AUTH_ENFORCED."""
    # Disable auth so we don't need a signed JWT; the handler still must copy
    # whatever Authorization header the caller sends to the upstream call.
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=[], request=request)

    _patch_httpx_client(monkeypatch, handler)
    r = client.get(
        "/api/bridge/alerts?month=2026-04",
        headers={"Authorization": "Bearer ey.caller.casdoor"},
    )
    assert r.status_code == 200, r.text
    assert captured["headers"].get("authorization") == "Bearer ey.caller.casdoor"


def test_cloudcost_non_json_raises_decoding_error():
    """Unit-level: _parse_json raises httpx.DecodingError (not plain JSONDecodeError)."""
    req = httpx.Request("GET", "https://cc.example/api/foo")
    r = httpx.Response(
        200,
        headers={"Content-Type": "text/html"},
        text="<html>nope</html>",
        request=req,
    )
    with pytest.raises(httpx.DecodingError):
        CloudCostClient._parse_json(r)


def test_customer_resources_endpoint_fails_gracefully_when_cloudcost_down(monkeypatch):
    """End-to-end: /api/customers/{id}/resources returns graceful 502 on cloudcost failure."""
    # Build a small app with a fake DB dependency that returns one customer.
    from app.database import get_db
    from app.models.customer import Customer

    class _FakeCustomer:
        id = 2
        customer_code = "CUST-002"
        is_deleted = False

    class _FakeQuery:
        def filter(self, *a, **kw):
            return self

        def first(self):
            return _FakeCustomer()

    class _FakeDb:
        def query(self, *a, **kw):
            return _FakeQuery()

    monkeypatch.setenv("CLOUDCOST_ENDPOINT", "https://cc.example")
    from app.config import get_settings
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout", request=request)

    transport = httpx.MockTransport(handler)

    def fake_client(self):  # noqa: ANN001
        return httpx.Client(transport=transport, headers=self._headers(), timeout=self.timeout)

    monkeypatch.setattr(CloudCostClient, "_client", fake_client)

    app = FastAPI()
    app.include_router(customer_resources.router)
    app.dependency_overrides[get_db] = lambda: _FakeDb()

    c = TestClient(app)
    r = c.get("/api/customers/2/resources")
    assert r.status_code == 502, r.text
    body = r.json()
    assert "云管" in body["detail"]
    assert "ReadTimeout" in body["detail"]
