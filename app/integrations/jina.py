"""Jina AI Reader + Search — used to enrich customer info and discover leads.

- Search:  POST https://s.jina.ai/  body {q}           →  { data: [{title,url,description,content}] }
- Reader:  GET  https://r.jina.ai/<target-url>          →  markdown of the page

All calls use Bearer token `JINA_API_KEY`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class JinaSearchResult:
    title: str
    url: str
    description: str = ""
    content: str = ""


class JinaClient:
    def __init__(self, api_key: str, timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if extra:
            h.update(extra)
        return h

    def search(self, query: str, num: int = 8) -> List[JinaSearchResult]:
        """Web search via s.jina.ai → JSON."""
        if not self.api_key:
            raise RuntimeError("JINA_API_KEY not configured")
        url = "https://s.jina.ai/"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.post(
                url,
                headers=self._headers({"Content-Type": "application/json", "Accept": "application/json"}),
                json={"q": query, "num": num},
            )
            r.raise_for_status()
            body = r.json()
        items = body.get("data") or []
        return [
            JinaSearchResult(
                title=it.get("title", ""),
                url=it.get("url", ""),
                description=it.get("description", ""),
                content=it.get("content", ""),
            )
            for it in items
        ]

    def read(self, url: str, max_chars: int = 20000) -> str:
        """Fetch clean markdown of an arbitrary URL via r.jina.ai."""
        if not self.api_key:
            raise RuntimeError("JINA_API_KEY not configured")
        target = url.strip()
        if not target.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        endpoint = f"https://r.jina.ai/{target}"
        with httpx.Client(timeout=self.timeout) as c:
            r = c.get(endpoint, headers=self._headers())
            r.raise_for_status()
            text = r.text
        return text[:max_chars]


# ------------------ Helpers extracted for customer enrich ------------------

_DESC_CANDIDATES = [
    r"公司简介[:：]?\s*(.+?)(?:\n\n|\Z)",
    r"关于[^\n]{0,20}?\n+(.+?)(?:\n\n|\Z)",
    r"About Us?\s*\n+(.+?)(?:\n\n|\Z)",
]


def guess_industry(text: str) -> Optional[str]:
    """Very lightweight industry heuristic."""
    t = text.lower()
    rules = [
        ("金融", r"(金融|银行|证券|保险|fintech|finance)"),
        ("医疗", r"(医疗|医院|医药|healthcare|pharma)"),
        ("教育", r"(教育|培训|education|edtech)"),
        ("电商", r"(电商|零售|retail|e-commerce|ecommerce)"),
        ("制造", r"(制造|工厂|manufactur)"),
        ("能源", r"(能源|电力|新能源|energy|power)"),
        ("云计算", r"(云计算|云平台|saas|cloud)"),
        ("AI", r"(人工智能|大模型|generative ai|ai|llm|machine learning)"),
        ("安全", r"(网络安全|信息安全|security|cybersec)"),
        ("游戏", r"(游戏|game|gaming)"),
        ("汽车", r"(汽车|automotive|新能源汽车|ev)"),
    ]
    for name, pat in rules:
        if re.search(pat, t):
            return name
    return None


def extract_description(text: str, limit: int = 240) -> Optional[str]:
    for pat in _DESC_CANDIDATES:
        m = re.search(pat, text, flags=re.DOTALL)
        if m:
            s = m.group(1).strip()
            s = re.sub(r"\s+", " ", s)
            return s[:limit]
    return None
