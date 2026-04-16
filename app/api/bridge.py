"""Thin pass-through endpoints that forward to cloudcost (云管) for UI consumption.

These live in xiaoshou so the SPA has a single origin to talk to and shares the
user's Casdoor token. Read-only.

Error handling policy:
  Cloudcost may be unreachable, slow, degraded, or return unexpected shapes. In
  every such case we respond with HTTP 502 + a JSON body of
  ``{"detail": "云管暂不可达: <ExceptionType>: <short message>"}`` so the SPA can
  render a friendly banner instead of a blank Bad Gateway from the ingress.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.integrations import CloudCostClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bridge", tags=["云管桥接"])


def _bearer_from_request(request: Request) -> Optional[str]:
    """Extract the raw bearer token from the incoming Authorization header.

    Cloudcost shares the same Casdoor as xiaoshou, so forwarding the caller's
    JWT is sufficient (verified live: curl -H 'Authorization: Bearer $TOKEN'
    cloudcost/api/alerts/rule-status → 200).
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _cloud(request: Request) -> CloudCostClient:
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")
    return CloudCostClient(
        s.CLOUDCOST_ENDPOINT,
        match_field=s.CLOUDCOST_MATCH_FIELD,
        bearer_token=_bearer_from_request(request),
    )


def _bad_gateway(e: BaseException) -> JSONResponse:
    """Uniform 502 JSON so the SPA doesn't see a blank Bad Gateway from ingress."""
    msg = str(e) if str(e) else repr(e)
    # Trim noisy httpx footers / long bodies.
    if "\nFor more information" in msg:
        msg = msg.split("\nFor more information", 1)[0]
    msg = msg.strip()[:200]
    logger.warning("bridge: cloudcost unavailable: %s: %s", type(e).__name__, msg)
    return JSONResponse(
        status_code=502,
        content={"detail": f"云管暂不可达: {type(e).__name__}: {msg}"},
    )


@router.get("/alerts", summary="预警规则执行态（代理云管）")
def alerts(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    try:
        return _cloud(request).alerts_rule_status(month)
    except HTTPException:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError, Exception) as e:
        return _bad_gateway(e)


@router.get("/bills", summary="月度账单列表（代理云管）")
def bills(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    _: CurrentUser = Depends(require_auth),
) -> Any:
    try:
        return _cloud(request).bills(month=month, status=status, page=page, page_size=page_size)
    except HTTPException:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError, Exception) as e:
        return _bad_gateway(e)


@router.get("/dashboard", summary="云管 dashboard bundle（代理）")
def dashboard(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    m = month or datetime.utcnow().strftime("%Y-%m")
    try:
        return _cloud(request).dashboard_bundle(m)
    except HTTPException:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError, Exception) as e:
        return _bad_gateway(e)
