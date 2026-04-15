"""FastAPI auth dependency — verifies Casdoor JWT on protected routes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.casdoor import CasdoorAuthError, verify_jwt
from app.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    sub: str
    name: str
    email: str = ""
    owner: str = ""
    roles: List[str] = None  # type: ignore[assignment]
    raw: dict = None  # type: ignore[assignment]

    def has_role(self, role: str) -> bool:
        return bool(self.roles) and role in self.roles


def _claims_to_user(claims: dict) -> CurrentUser:
    roles_field = claims.get("roles") or []
    if isinstance(roles_field, list) and roles_field and isinstance(roles_field[0], dict):
        roles = [r.get("name", "") for r in roles_field if r.get("name")]
    elif isinstance(roles_field, list):
        roles = [str(r) for r in roles_field]
    else:
        roles = []
    return CurrentUser(
        sub=claims.get("sub", ""),
        name=claims.get("name") or claims.get("preferred_username", ""),
        email=claims.get("email", ""),
        owner=claims.get("owner", ""),
        roles=roles,
        raw=claims,
    )


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[CurrentUser]:
    """Returns user if a valid token is provided; None otherwise. Never raises."""
    s = get_settings()
    if not s.AUTH_ENABLED:
        return CurrentUser(sub="dev", name="dev", roles=["admin"], raw={})
    if not creds:
        return None
    try:
        claims = verify_jwt(creds.credentials)
    except CasdoorAuthError:
        return None
    return _claims_to_user(claims)


async def require_auth(
    user: Optional[CurrentUser] = Depends(get_current_user),
) -> CurrentUser:
    """Protected-route dependency — 401 if no valid token."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
