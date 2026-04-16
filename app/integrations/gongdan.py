"""Client for the 工单 (gongdan) system.

Reads customers and tickets. Auth is a static API key passed as `X-Api-Key`
(mechanism confirmed in gongdan/backend/src/common/guards/api-key.guard.ts).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class GongdanCustomer:
    id: str
    customer_code: str
    name: str
    tier: str = "NORMAL"


class GongdanClient:
    def __init__(self, endpoint: str, api_key: str, timeout: float = 15.0):
        self.base = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    def list_customers(self) -> List[GongdanCustomer]:
        """GET /api/customers — returns every customer, no pagination."""
        if not self.api_key:
            raise RuntimeError("GONGDAN_API_KEY not configured")
        url = f"{self.base}/api/customers"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(url, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        out: List[GongdanCustomer] = []
        for item in data:
            out.append(
                GongdanCustomer(
                    id=str(item.get("id") or ""),
                    customer_code=str(item.get("customerCode") or ""),
                    name=str(item.get("name") or ""),
                    tier=str(item.get("tier") or "NORMAL"),
                )
            )
        return out

    def list_tickets(self, page_size: int = 200, max_pages: int = 50) -> List[Dict[str, Any]]:
        """GET /api/tickets — paginated; walks until exhausted or max_pages.

        gongdan returns ``{tickets: [...], total, page, pageSize, totalPages}``.
        We defensively accept both that and a raw list shape in case of version
        drift. Returns the raw ticket dicts (callers pluck what they need).
        """
        if not self.api_key:
            raise RuntimeError("GONGDAN_API_KEY not configured")
        url = f"{self.base}/api/tickets"
        collected: List[Dict[str, Any]] = []
        with httpx.Client(timeout=self.timeout) as c:
            page = 1
            while page <= max_pages:
                r = c.get(url, headers=self._headers(), params={"page": page, "pageSize": page_size})
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list):
                    collected.extend(data)
                    break  # list shape → no pagination envelope
                items = data.get("tickets") or data.get("items") or []
                collected.extend(items)
                total_pages = int(data.get("totalPages") or 1)
                if page >= total_pages or not items:
                    break
                page += 1
        return collected

    def health(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base}/api/customers", headers=self._headers())
                return r.status_code < 500
        except Exception as e:
            logger.warning("gongdan health failed: %s", e)
            return False
