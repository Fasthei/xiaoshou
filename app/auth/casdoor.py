"""
Casdoor OIDC / JWT verification.

校验流程（纯后端、无外部 SDK 依赖）：
1. 启动后懒加载 Casdoor 应用的公钥 PEM（来自配置 CASDOOR_CERT，
   或远端 /api/get-cert?name=<app>）。
2. 收到请求 → 取 Authorization: Bearer <jwt>。
3. python-jose 用 RS256 + 公钥验签，校验 iss / aud(client_id) / exp。
4. 返回解析后的 claims（sub / name / email / roles 等）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx
from jose import jwt, JWTError

from app.config import get_settings

logger = logging.getLogger(__name__)


class CasdoorAuthError(Exception):
    pass


_PEM_CACHE: Optional[str] = None


def _load_public_key_pem() -> str:
    """Load Casdoor application's signing cert (PEM)."""
    global _PEM_CACHE
    if _PEM_CACHE:
        return _PEM_CACHE

    s = get_settings()
    if s.CASDOOR_CERT and "BEGIN" in s.CASDOOR_CERT:
        _PEM_CACHE = s.CASDOOR_CERT.replace("\\n", "\n")
        return _PEM_CACHE

    if not s.CASDOOR_ENDPOINT or not s.CASDOOR_APP_NAME:
        raise CasdoorAuthError("CASDOOR_ENDPOINT / CASDOOR_APP_NAME not configured")

    url = f"{s.CASDOOR_ENDPOINT.rstrip('/')}/api/get-cert"
    params = {"id": f"{s.CASDOOR_ORG}/{s.CASDOOR_APP_NAME}"}
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        cert = (data.get("data") or {}).get("certificate") or data.get("certificate")
        if not cert:
            raise CasdoorAuthError(f"empty cert from Casdoor: {data}")
        _PEM_CACHE = cert
        return cert
    except Exception as e:
        raise CasdoorAuthError(f"failed to fetch Casdoor cert: {e}") from e


def verify_jwt(token: str) -> Dict[str, Any]:
    """Verify a Casdoor-issued JWT and return its claims."""
    s = get_settings()
    pem = _load_public_key_pem()
    try:
        claims = jwt.decode(
            token,
            pem,
            algorithms=["RS256"],
            audience=s.CASDOOR_CLIENT_ID or None,
            options={"verify_aud": bool(s.CASDOOR_CLIENT_ID)},
        )
    except JWTError as e:
        raise CasdoorAuthError(f"invalid token: {e}") from e

    # Optional issuer check
    iss = claims.get("iss", "")
    expected_iss = s.CASDOOR_ENDPOINT.rstrip("/")
    if expected_iss and iss and not iss.startswith(expected_iss):
        raise CasdoorAuthError(f"unexpected issuer: {iss}")

    return claims


def exchange_code_for_token(code: str, state: str = "") -> Dict[str, Any]:
    """OAuth2 code -> access_token (server-side callback)."""
    s = get_settings()
    url = f"{s.CASDOOR_ENDPOINT.rstrip('/')}/api/login/oauth/access_token"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": s.CASDOOR_CLIENT_ID,
        "client_secret": s.CASDOOR_CLIENT_SECRET,
        "redirect_uri": s.CASDOOR_REDIRECT_URI,
    }
    with httpx.Client(timeout=10.0) as client:
        r = client.post(url, data=payload)
        r.raise_for_status()
        return r.json()


def authorize_url(state: str = "xiaoshou") -> str:
    s = get_settings()
    return (
        f"{s.CASDOOR_ENDPOINT.rstrip('/')}/login/oauth/authorize"
        f"?client_id={s.CASDOOR_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={s.CASDOOR_REDIRECT_URI}"
        f"&scope=read"
        f"&state={state}"
    )
