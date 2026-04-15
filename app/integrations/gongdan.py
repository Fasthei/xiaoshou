"""Client for the 工单 (gongdan) system.

Only needs a read of the customer list. Auth is a static API key passed as
`X-Api-Key` (mechanism confirmed in gongdan/backend/src/common/guards/api-key.guard.ts).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

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

    def health(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as c:
                r = c.get(f"{self.base}/api/customers", headers=self._headers())
                return r.status_code < 500
        except Exception as e:
            logger.warning("gongdan health failed: %s", e)
            return False
