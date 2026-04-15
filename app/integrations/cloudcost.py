"""Client for 云管 (cloudcost).

Read-only per docs/AI-BRAIN-API.md. No auth currently. We only use the subset
needed to resolve customer_code -> resource (货源) listings.

Canonical mapping (see SSO.md §data-model):
  xiaoshou.customer.customer_code   ← gongdan.customer.customerCode (source of truth)
  cloudcost.service_account         ← one or more 货源 bound to a customer
  matching key                      = service_account.external_project_id

If the deployment uses a different key (e.g. supplier_name), set
CLOUDCOST_MATCH_FIELD env var.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

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
    def __init__(self, endpoint: str, timeout: float = 15.0, match_field: str = "external_project_id"):
        self.base = endpoint.rstrip("/")
        self.timeout = timeout
        # Which ServiceAccount attribute is matched against xiaoshou.customer_code
        self.match_field = match_field

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout)

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
            return [SupplySource(**{k: item.get(k) for k in SupplySource.__dataclass_fields__}) for item in r.json()]

    def list_service_accounts(
        self, provider: Optional[str] = None, page: int = 1, page_size: int = 200
    ) -> List[ServiceAccount]:
        params = {"page": page, "page_size": page_size}
        if provider:
            params["provider"] = provider
        with self._client() as c:
            r = c.get(f"{self.base}/api/service-accounts/", params=params)
            r.raise_for_status()
            return [
                ServiceAccount(**{k: item.get(k) for k in ServiceAccount.__dataclass_fields__})
                for item in r.json()
            ]

    # ---------- Alerts / Bills / Dashboard ----------
    def alerts_rule_status(self, month: Optional[str] = None) -> list:
        params = {"month": month} if month else None
        with self._client() as c:
            r = c.get(f"{self.base}/api/alerts/rule-status", params=params)
            r.raise_for_status()
            return r.json()

    def bills(self, month: Optional[str] = None, status: Optional[str] = None,
              page: int = 1, page_size: int = 50) -> list:
        params = {"page": page, "page_size": page_size}
        if month: params["month"] = month
        if status: params["status"] = status
        with self._client() as c:
            r = c.get(f"{self.base}/api/bills/", params=params)
            r.raise_for_status()
            return r.json()

    def dashboard_bundle(self, month: str, granularity: str = "daily", service_limit: int = 10) -> dict:
        with self._client() as c:
            r = c.get(f"{self.base}/api/dashboard/bundle",
                      params={"month": month, "granularity": granularity, "service_limit": service_limit})
            r.raise_for_status()
            return r.json()

    def sync_last(self) -> Optional[str]:
        try:
            with self._client() as c:
                r = c.get(f"{self.base}/api/sync/last")
                r.raise_for_status()
                return (r.json() or {}).get("last_sync")
        except Exception:
            return None

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
