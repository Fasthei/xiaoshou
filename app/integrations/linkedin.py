"""LinkedIn via RapidAPI — host `fresh-linkedin-profile-data.p.rapidapi.com`.

Active endpoints confirmed by probing (403 = endpoint missing, 429 = rate limit but exists):
  /company/details              GET  ?linkedin_url=...
  /search-companies             GET/POST
  /get-linkedin-profile         GET  ?linkedin_url=...
  /profile                      GET  ?url=...
  /list-jobs                    GET

Subscribe at https://rapidapi.com/freshdata-freshdata-default/api/fresh-linkedin-profile-data/ first.

Errors from upstream:
  {"message":"You are not subscribed to this API."}   -> 402 here
  {"message":"Too many requests"}                    -> 429 here
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LinkedInCompanyBrief:
    name: str
    linkedin_url: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    employee_count: Optional[int] = None
    description: Optional[str] = None
    raw: Dict[str, Any] = None  # type: ignore


class LinkedInClient:
    def __init__(self, api_key: str, host: str = "fresh-linkedin-profile-data.p.rapidapi.com", timeout: float = 15.0):
        self.key = api_key
        self.host = host
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"x-rapidapi-host": self.host, "x-rapidapi-key": self.key}

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"https://{self.host}{path}"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(url, headers=self._headers(), params=params)
        if r.status_code == 403:
            raise RuntimeError("LinkedIn API: not subscribed (403). Subscribe on RapidAPI first.")
        if r.status_code == 429:
            raise RuntimeError("LinkedIn API: rate limit hit (429). Upgrade plan or wait.")
        r.raise_for_status()
        return r.json()

    def search_companies(self, keyword: str, page: int = 1) -> List[LinkedInCompanyBrief]:
        data = self._get("/search-companies", {"keyword": keyword, "page": page})
        items = data.get("data") or data.get("results") or (data if isinstance(data, list) else [])
        out: List[LinkedInCompanyBrief] = []
        for it in items[:20]:
            out.append(
                LinkedInCompanyBrief(
                    name=it.get("name") or it.get("title", ""),
                    linkedin_url=it.get("linkedin_url") or it.get("url", ""),
                    domain=it.get("website") or it.get("domain"),
                    industry=it.get("industry"),
                    headquarters=it.get("headquarters") or it.get("location"),
                    employee_count=it.get("employee_count") or it.get("staff_count"),
                    description=it.get("description") or it.get("tagline"),
                    raw=it,
                )
            )
        return out

    def get_company(self, linkedin_url: str) -> LinkedInCompanyBrief:
        it = self._get("/company/details", {"linkedin_url": linkedin_url})
        data = it.get("data") if isinstance(it, dict) and "data" in it else it
        return LinkedInCompanyBrief(
            name=data.get("company_name") or data.get("name", ""),
            linkedin_url=linkedin_url,
            domain=data.get("website") or data.get("domain"),
            industry=data.get("industry"),
            headquarters=data.get("headquarters"),
            employee_count=data.get("employee_count") or data.get("staff_count"),
            description=data.get("about") or data.get("description"),
            raw=data,
        )

    def get_profile(self, linkedin_url: str) -> Dict[str, Any]:
        return self._get("/get-linkedin-profile", {"linkedin_url": linkedin_url})
