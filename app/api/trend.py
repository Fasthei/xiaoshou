"""GET /api/trend/daily — 14-day spending trend from 云管 for dashboard sparklines."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.integrations import CloudCostClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trend", tags=["趋势"])


class DailyPoint(BaseModel):
    date: str
    cost: float


def _bad_gateway(e: BaseException) -> JSONResponse:
    msg = str(e) if str(e) else repr(e)
    if "\nFor more information" in msg:
        msg = msg.split("\nFor more information", 1)[0]
    msg = msg.strip()[:200]
    logger.warning("trend: cloudcost unavailable: %s: %s", type(e).__name__, msg)
    return JSONResponse(
        status_code=502,
        content={"detail": f"云管暂不可达: {type(e).__name__}: {msg}"},
    )


@router.get(
    "/daily",
    summary="近 14 天云消耗趋势（云管）",
    responses={
        200: {"model": List[DailyPoint]},
        502: {"description": "云管暂不可达"},
    },
)
def daily(
    days: int = Query(14, ge=1, le=60),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")
    now = datetime.utcnow()
    m_now = now.strftime("%Y-%m")
    try:
        bundle = CloudCostClient(s.CLOUDCOST_ENDPOINT).dashboard_bundle(m_now, "daily", 1)
        if not isinstance(bundle, dict):
            raise TypeError(f"expected dict, got {type(bundle).__name__}")
        points = bundle.get("trend") or []
        if not isinstance(points, list):
            points = []
        points = sorted(points, key=lambda p: (p or {}).get("date", ""))[-days:]
        return [
            DailyPoint(
                date=(p or {}).get("date", ""),
                cost=float((p or {}).get("cost", 0) or 0),
            ).model_dump()
            for p in points
        ]
    except HTTPException:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError, Exception) as e:
        return _bad_gateway(e)
