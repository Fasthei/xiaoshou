"""Verify a Casdoor-issued M2M (client_credentials) token.

Used to secure xiaoshou's internal endpoint that cloudcost pulls — we accept
any Casdoor token whose `aud` is in CASDOOR_INTERNAL_ALLOWED_CLIENTS.

If an internal API key is also configured (XIAOSHOU_INTERNAL_API_KEY), that
is accepted as an alternative so cloudcost can be wired up before its Casdoor
client is provisioned.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from app.auth.casdoor import CasdoorAuthError, verify_jwt

logger = logging.getLogger(__name__)


def allowed_clients() -> List[str]:
    raw = os.getenv("CASDOOR_INTERNAL_ALLOWED_CLIENTS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


def static_internal_key() -> str:
    return os.getenv("XIAOSHOU_INTERNAL_API_KEY", "")


def verify_internal(token_or_key: Optional[str], header_api_key: Optional[str]) -> bool:
    """Authorize an internal caller by Casdoor M2M JWT OR static API key.

    Returns True if the caller is authorized.
    """
    # Static API key branch (for cloudcost before it joins Casdoor)
    if header_api_key and static_internal_key() and header_api_key == static_internal_key():
        return True

    if not token_or_key:
        return False

    try:
        claims = verify_jwt(token_or_key)
    except CasdoorAuthError as e:
        logger.info("internal M2M verify failed: %s", e)
        return False

    aud = claims.get("aud")
    auds = aud if isinstance(aud, list) else [aud] if aud else []
    allowed = set(allowed_clients())
    if allowed and not allowed.intersection(set(auds)):
        logger.info("internal M2M aud %s not in allowlist %s", auds, allowed)
        return False
    return True
