"""Client for 云管 (cloudcost).

Historically read-only and unauthenticated per docs/AI-BRAIN-API.md. Cloudcost
has since started requiring auth on all deployments (``AUTH_ENFORCED=true``),
so this client now forwards credentials in one of three ways:

- Explicit ``bearer_token`` arg → sent as ``Authorization: Bearer`` (highest
  priority; used by bridge/trend/customer_resources handlers to forward the
  caller's Casdoor JWT, since xiaoshou and cloudcost share the same Casdoor).
- ``CLOUDCOST_API_KEY`` env      → sent as ``X-Api-Key`` (optional fallback).
- ``CLOUDCOST_M2M_TOKEN`` env    → sent as ``Authorization: Bearer``
  (M2M fallback; only used when no explicit ``bearer_token`` is provided).

All three are optional: unset ⇒ anonymous calls (for tests / legacy deploys).

Canonical mapping (see SSO.md §data-model):
  xiaoshou.customer.customer_code   ← gongdan.customer.customerCode (source of truth)
  cloudcost.service_account         ← one or more 货源 bound to a customer
  matching key                      = service_account.external_project_id

If the deployment uses a different key (e.g. supplier_name), set
CLOUDCOST_MATCH_FIELD env var.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ServiceAccount:
    id: int
    name: str
    provider: str
    supplier_name: Optional[str] = None
    supply_source_id: Optional[int] = None
    external_project_id: Optional[str] = None
    status: Optional[str] = None


@dataclass
class SupplySource:
    id: int
    supplier_id: int
    supplier_name: str
    provider: str
    account_count: int


class CloudCostClient:
    def __init__(
        self,
        endpoint: str,
        timeout: float = 15.0,
        match_field: str = "external_project_id",
        api_key: Optional[str] = None,
        m2m_token: Optional[str] = None,
        bearer_token: Optional[str] = None,
    ):
        self.base = endpoint.rstrip("/")
        self.timeout = timeout
        # Which ServiceAccount attribute is matched against xiaoshou.customer_code
        self.match_field = match_field
        # Explicit forwarded bearer (e.g. caller's Casdoor JWT) takes precedence.
        self.bearer_token = bearer_token or None
        # Optional credentials (fall back to env so callers don't need to plumb them).
        self.api_key = api_key if api_key is not None else os.getenv("CLOUDCOST_API_KEY", "") or None
        self.m2m_token = (
            m2m_token if m2m_token is not None else os.getenv("CLOUDCOST_M2M_TOKEN", "") or None
        )

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            h["X-Api-Key"] = self.api_key
        # Explicit forwarded caller token wins over the M2M fallback — cloudcost
        # and xiaoshou share the same Casdoor, so forwarding the user's JWT is
        # both sufficient and preserves per-user audit context downstream.
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        elif self.m2m_token:
            h["Authorization"] = f"Bearer {self.m2m_token}"
        return h

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, headers=self._headers())

    @staticmethod
    def _parse_json(r: httpx.Response) -> Any:
        """Parse JSON or raise a uniform error that upstream handlers can render cleanly."""
        try:
            return r.json()
        except (json.JSONDecodeError, ValueError) as e:
            # Mask body snippet at most 120 chars
            snippet = (r.text or "")[:120].replace("\n", " ")
            raise httpx.DecodingError(f"cloudcost returned non-JSON: {snippet}") from e

    def health(self) -> bool:
        try:
            with self._client() as c:
                return c.get(f"{self.base}/api/health").status_code == 200
        except Exception as e:
            logger.warning("cloudcost health failed: %s", e)
            return False

    def list_supply_sources(self) -> List[SupplySource]:
        with self._client() as c:
            r = c.get(f"{self.base}/api/suppliers/supply-sources/all")
            r.raise_for_status()
            data = self._parse_json(r) or []
            return [
                SupplySource(**{k: item.get(k) for k in SupplySource.__dataclass_fields__})
                for item in data if isinstance(item, dict)
            ]

    def list_service_accounts(
        self, provider: Optional[str] = None, page: int = 1, page_size: int = 200
    ) -> List[ServiceAccount]:
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if provider:
            params["provider"] = provider
        with self._client() as c:
            r = c.get(f"{self.base}/api/service-accounts/", params=params)
            r.raise_for_status()
            data = self._parse_json(r) or []
            # Cloudcost may return either a bare list or {"items": [...]} — tolerate both.
            if isinstance(data, dict):
                data = data.get("items") or data.get("data") or []
            return [
                ServiceAccount(**{k: item.get(k) for k in ServiceAccount.__dataclass_fields__})
                for item in data if isinstance(item, dict)
            ]

    # ---------- Alerts / Bills / Dashboard ----------
    def alerts_rule_status(self, month: Optional[str] = None) -> list:
        params = {"month": month} if month else None
        with self._client() as c:
            r = c.get(f"{self.base}/api/alerts/rule-status", params=params)
            r.raise_for_status()
            data = self._parse_json(r)
            if isinstance(data, dict):
                data = data.get("items") or data.get("data") or []
            return data if isinstance(data, list) else []

    def bills(self, month: Optional[str] = None, status: Optional[str] = None,
              page: int = 1, page_size: int = 50) -> Any:
        params: Dict[str, Any] = {"page": page, "page_size": page_size}
        if month:
            params["month"] = month
        if status:
            params["status"] = status
        with self._client() as c:
            r = c.get(f"{self.base}/api/bills/", params=params)
            r.raise_for_status()
            return self._parse_json(r)

    def dashboard_bundle(self, month: str, granularity: str = "daily", service_limit: int = 10) -> dict:
        with self._client() as c:
            r = c.get(f"{self.base}/api/dashboard/bundle",
                      params={"month": month, "granularity": granularity, "service_limit": service_limit})
            r.raise_for_status()
            data = self._parse_json(r)
            return data if isinstance(data, dict) else {}

    def sync_last(self) -> Optional[str]:
        try:
            with self._client() as c:
                r = c.get(f"{self.base}/api/sync/last")
                r.raise_for_status()
                data = self._parse_json(r) or {}
                if not isinstance(data, dict):
                    return None
                return data.get("last_sync")
        except Exception:
            return None

    def get_customer_usage(self, account_id: int, days: int = 30) -> Any:
        """Pull per-service-account cost breakdown for last N days.

        Calls cloudcost `/api/service-accounts/{id}/costs?start_date=&end_date=`.
        Returns raw JSON (shape varies; callers must tolerate both list and dict).

        NOTE: Legacy endpoint. New sync code should prefer
        :meth:`metering_detail` / :meth:`metering_daily`, which are the
        standardised metering interfaces (see docs/CLOUDCOST_API.md §"已接入").
        """
        from datetime import datetime, timedelta
        end = datetime.utcnow().date()
        start = end - timedelta(days=max(1, int(days)))
        params = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        with self._client() as c:
            r = c.get(f"{self.base}/api/service-accounts/{account_id}/costs", params=params)
            r.raise_for_status()
            return self._parse_json(r)

    # ---------- /api/auth/me ----------

    def auth_me(self) -> Dict[str, Any]:
        """GET /api/auth/me — whoami against cloudcost, forwarded bearer required.

        Returns cloudcost's user object (shape dictated by cloudcost). Used for
        dual-system login probes and diagnostics.
        """
        with self._client() as c:
            r = c.get(f"{self.base}/api/auth/me")
            r.raise_for_status()
            data = self._parse_json(r)
            return data if isinstance(data, dict) else {}

    # ---------- /api/metering/* — standardised metering reads ----------
    # All metering endpoints accept a date range + optional account filter.
    # Convention:
    #   start_date / end_date : YYYY-MM-DD (inclusive)
    #   account_id            : single cloudcost service_account.id (optional)
    #   page / page_size      : pagination on *detail* only
    # Response shape is either a bare list or {"items":[...], "total":N};
    # callers should use :meth:`_extract_items` / helpers below.

    @staticmethod
    def _extract_items(data: Any) -> List[Dict[str, Any]]:
        """Tolerate both bare-list and {items|data: [...]} shapes."""
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("items", "data", "rows", "results"):
                v = data.get(key)
                if isinstance(v, list):
                    return [x for x in v if isinstance(x, dict)]
        return []

    def _metering_get(self, path: str, params: Dict[str, Any]) -> Any:
        """Internal GET helper for /api/metering/* endpoints."""
        # Filter out None values so we don't send literal ?k=None.
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        with self._client() as c:
            r = c.get(f"{self.base}{path}", params=clean)
            r.raise_for_status()
            return self._parse_json(r)

    def metering_summary(
        self,
        month: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """GET /api/metering/summary — total cost / usage over the range.

        Either ``month`` (YYYY-MM) or an explicit ``start_date``+``end_date`` pair
        must be provided. Returns a flat dict like
        ``{"total_cost": N, "total_usage": N, "record_count": N, ...}``.
        """
        data = self._metering_get("/api/metering/summary", {
            "month": month,
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        })
        return data if isinstance(data, dict) else {}

    def metering_daily(
        self,
        start_date: str,
        end_date: str,
        account_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """GET /api/metering/daily — day-by-day cost/usage buckets.

        Returns a list of ``{"date": "YYYY-MM-DD", "total_cost": N,
        "total_usage": N, "record_count": N}`` rows ordered by date.
        """
        data = self._metering_get("/api/metering/daily", {
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        })
        return self._extract_items(data)

    def metering_by_service(
        self,
        start_date: str,
        end_date: str,
        account_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """GET /api/metering/by-service — cost/usage split per cloud service."""
        data = self._metering_get("/api/metering/by-service", {
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        })
        return self._extract_items(data)

    def metering_detail(
        self,
        start_date: str,
        end_date: str,
        account_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 500,
    ) -> List[Dict[str, Any]]:
        """GET /api/metering/detail — row-level metering records (paginated).

        Returns the items on this page. Callers driving a full sync should
        iterate until fewer than ``page_size`` items come back, or use
        :meth:`metering_detail_iter`.
        """
        data = self._metering_get("/api/metering/detail", {
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
            "page": page,
            "page_size": page_size,
        })
        return self._extract_items(data)

    def metering_detail_count(
        self,
        start_date: str,
        end_date: str,
        account_id: Optional[int] = None,
    ) -> int:
        """GET /api/metering/detail/count — total rows that match the filter."""
        data = self._metering_get("/api/metering/detail/count", {
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        })
        if isinstance(data, dict):
            for k in ("count", "total", "total_count"):
                v = data.get(k)
                if isinstance(v, int):
                    return v
                try:
                    return int(v)
                except (TypeError, ValueError):
                    continue
        try:
            return int(data)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    def metering_detail_iter(
        self,
        start_date: str,
        end_date: str,
        account_id: Optional[int] = None,
        page_size: int = 500,
        max_pages: int = 500,
    ):
        """Generator: stream every /api/metering/detail row, page by page.

        Safety cap ``max_pages`` prevents unbounded loops if cloudcost returns
        the same non-empty page forever.
        """
        page = 1
        while page <= max_pages:
            items = self.metering_detail(
                start_date=start_date,
                end_date=end_date,
                account_id=account_id,
                page=page,
                page_size=page_size,
            )
            if not items:
                return
            for it in items:
                yield it
            if len(items) < page_size:
                return
            page += 1

    # ---------- /api/billing/* — detailed billing lines ----------
    # `bills()` (legacy /api/bills/) is the monthly aggregate; billing/detail
    # exposes per-line items that roll up into a bill, useful for audits.

    def billing_detail(
        self,
        month: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 200,
    ) -> List[Dict[str, Any]]:
        """GET /api/billing/detail — billing line items (paginated)."""
        data = self._metering_get("/api/billing/detail", {
            "month": month,
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
            "page": page,
            "page_size": page_size,
        })
        return self._extract_items(data)

    def billing_detail_count(
        self,
        month: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        account_id: Optional[int] = None,
    ) -> int:
        """GET /api/billing/detail/count — row count that matches the filter."""
        data = self._metering_get("/api/billing/detail/count", {
            "month": month,
            "start_date": start_date,
            "end_date": end_date,
            "account_id": account_id,
        })
        if isinstance(data, dict):
            for k in ("count", "total", "total_count"):
                v = data.get(k)
                if isinstance(v, int):
                    return v
                try:
                    return int(v)
                except (TypeError, ValueError):
                    continue
        try:
            return int(data)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    # ---------- resource resolution ----------

    def resources_for_customer(self, customer_code: str) -> List[ServiceAccount]:
        """Return 货源 entries whose `match_field` equals the given customer_code.

        Cached across the call: we pull the full list once (≤ 500 accounts) and filter locally.
        Good enough for the volumes we expect; can be replaced with a server-side filter
        if cloudcost later adds `?external_project_id=` to its query params.
        """
        all_accounts = self.list_service_accounts(page=1, page_size=500)
        out: List[ServiceAccount] = []
        for a in all_accounts:
            val = getattr(a, self.match_field, None)
            if val and str(val) == str(customer_code):
                out.append(a)
        return out
