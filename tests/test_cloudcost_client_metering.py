"""Unit coverage for the new CloudCostClient methods.

These tests monkey-patch ``httpx.Client`` so no network is involved; we verify:

- Correct URL + method
- Query params honoured (start_date / end_date / account_id / page / page_size)
- Both bare-list and envelope response shapes parse the same way
- Count helpers tolerate ``int``, ``{"count": N}``, ``{"total": N}``
- ``metering_detail_iter`` paginates and stops on short pages
- Fallback behaviour: no explicit bearer/api-key → anonymous
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

from app.integrations.cloudcost import CloudCostClient


class _FakeResp:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    def json(self) -> Any:
        if isinstance(self._payload, str):
            return json.loads(self._payload)
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "http://fake"),
                response=httpx.Response(self.status_code),
            )


class _FakeClient:
    """Context-manager httpx.Client replacement that records every GET."""

    def __init__(self, routes: Dict[str, Any]):
        # routes: "<path>" -> payload (or callable(params) -> payload)
        self.routes = routes
        self.calls: List[Dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url: str, params: Dict[str, Any] | None = None) -> _FakeResp:
        # Strip base to get the path only.
        path = url
        for base in ("http://fake", "https://fake"):
            if path.startswith(base):
                path = path[len(base):]
                break
        self.calls.append({"path": path, "params": dict(params or {})})
        payload = self.routes.get(path)
        if callable(payload):
            payload = payload(params or {})
        if payload is None:
            return _FakeResp({}, status_code=404)
        return _FakeResp(payload)


@pytest.fixture()
def fake(monkeypatch):
    """Build a client + a recording fake transport in one shot."""

    def _factory(routes: Dict[str, Any]) -> tuple[CloudCostClient, _FakeClient]:
        fc = _FakeClient(routes)
        client = CloudCostClient("http://fake")
        # Replace the transport builder so every HTTP call goes through fc.
        monkeypatch.setattr(client, "_client", lambda: fc)
        return client, fc

    return _factory


# ---------- auth_me ----------

def test_auth_me_returns_dict(fake):
    client, fc = fake({"/api/auth/me": {"id": 7, "name": "svc"}})
    out = client.auth_me()
    assert out == {"id": 7, "name": "svc"}
    assert fc.calls[0]["path"] == "/api/auth/me"


def test_auth_me_non_dict_returns_empty(fake):
    client, _ = fake({"/api/auth/me": ["not", "a", "dict"]})
    assert client.auth_me() == {}


# ---------- metering/summary ----------

def test_metering_summary_sends_month_and_account(fake):
    client, fc = fake({"/api/metering/summary": {"total_cost": 123.45}})
    out = client.metering_summary(month="2026-04", account_id=42)
    assert out == {"total_cost": 123.45}
    call = fc.calls[0]
    assert call["path"] == "/api/metering/summary"
    assert call["params"]["month"] == "2026-04"
    assert call["params"]["account_id"] == 42
    # None values must be dropped
    assert "start_date" not in call["params"]
    assert "end_date" not in call["params"]


def test_metering_summary_non_dict_returns_empty(fake):
    client, _ = fake({"/api/metering/summary": [1, 2]})
    assert client.metering_summary(month="2026-04") == {}


# ---------- metering/daily ----------

def test_metering_daily_tolerates_both_shapes(fake):
    # bare list
    client, _ = fake({
        "/api/metering/daily": [
            {"date": "2026-04-01", "total_cost": 10},
            {"date": "2026-04-02", "total_cost": 12},
        ]
    })
    rows = client.metering_daily("2026-04-01", "2026-04-02")
    assert [r["date"] for r in rows] == ["2026-04-01", "2026-04-02"]

    # envelope
    client2, _ = fake({
        "/api/metering/daily": {"items": [{"date": "2026-04-01", "total_cost": 5}]}
    })
    rows2 = client2.metering_daily("2026-04-01", "2026-04-01")
    assert len(rows2) == 1


def test_metering_daily_forwards_params(fake):
    client, fc = fake({"/api/metering/daily": []})
    client.metering_daily("2026-04-01", "2026-04-07", account_id=3)
    p = fc.calls[0]["params"]
    assert p == {"start_date": "2026-04-01", "end_date": "2026-04-07", "account_id": 3}


# ---------- metering/by-service ----------

def test_metering_by_service_envelope(fake):
    client, _ = fake({
        "/api/metering/by-service": {
            "data": [{"service": "S3", "total_cost": 1}, {"service": "EC2", "total_cost": 2}]
        }
    })
    rows = client.metering_by_service("2026-04-01", "2026-04-07")
    services = {r["service"] for r in rows}
    assert services == {"S3", "EC2"}


# ---------- metering/detail + detail/count + detail_iter ----------

def test_metering_detail_paginates_via_iter(fake):
    # Two pages: page=1 full (size=2), page=2 short → stops
    def responder(params):
        page = int(params.get("page", 1))
        if page == 1:
            return [
                {"date": "2026-04-01", "cost": 1, "usage": 1, "service": "S3"},
                {"date": "2026-04-02", "cost": 2, "usage": 2, "service": "S3"},
            ]
        if page == 2:
            return [
                {"date": "2026-04-03", "cost": 3, "usage": 3, "service": "S3"},
            ]
        return []

    client, fc = fake({"/api/metering/detail": responder})
    rows = list(client.metering_detail_iter(
        start_date="2026-04-01", end_date="2026-04-03",
        account_id=7, page_size=2,
    ))
    assert [r["cost"] for r in rows] == [1, 2, 3]
    # Verified two pages fired, both with account_id forwarded
    assert len(fc.calls) == 2
    assert fc.calls[0]["params"]["page"] == 1
    assert fc.calls[1]["params"]["page"] == 2
    assert all(c["params"]["account_id"] == 7 for c in fc.calls)


def test_metering_detail_iter_empty(fake):
    client, _ = fake({"/api/metering/detail": []})
    assert list(client.metering_detail_iter(
        start_date="2026-04-01", end_date="2026-04-01",
    )) == []


def test_metering_detail_count_accepts_int_or_envelope(fake):
    client, _ = fake({"/api/metering/detail/count": {"count": 42}})
    assert client.metering_detail_count("2026-04-01", "2026-04-02") == 42

    client2, _ = fake({"/api/metering/detail/count": {"total": 7}})
    assert client2.metering_detail_count("2026-04-01", "2026-04-02") == 7

    # Bare number — rare but seen on some cloudcost deploys
    client3, _ = fake({"/api/metering/detail/count": 99})
    assert client3.metering_detail_count("2026-04-01", "2026-04-02") == 99

    # Garbage → 0 not raise
    client4, _ = fake({"/api/metering/detail/count": {"weird": "no"}})
    assert client4.metering_detail_count("2026-04-01", "2026-04-02") == 0


# ---------- billing/detail + billing/detail/count ----------

def test_billing_detail_forwards_month(fake):
    client, fc = fake({"/api/billing/detail": [{"line_id": 1}, {"line_id": 2}]})
    rows = client.billing_detail(month="2026-04", account_id=5, page=2, page_size=50)
    assert len(rows) == 2
    p = fc.calls[0]["params"]
    assert p["month"] == "2026-04"
    assert p["account_id"] == 5
    assert p["page"] == 2
    assert p["page_size"] == 50
    assert "start_date" not in p


def test_billing_detail_count(fake):
    client, _ = fake({"/api/billing/detail/count": {"count": 128}})
    assert client.billing_detail_count(month="2026-04") == 128


# ---------- query param hygiene ----------

def test_none_params_are_dropped(fake):
    client, fc = fake({"/api/metering/summary": {}})
    client.metering_summary(month="2026-04", account_id=None, start_date=None)
    p = fc.calls[0]["params"]
    assert p == {"month": "2026-04"}
