"""GET /api/trend/daily — 14-day spending trend from 云管 for dashboard sparklines."""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.integrations import CloudCostClient

router = APIRouter(prefix="/api/trend", tags=["趋势"])


class DailyPoint(BaseModel):
    date: str
    cost: float


@router.get("/daily", response_model=List[DailyPoint], summary="近 14 天云消耗趋势（云管）")
def daily(
    days: int = Query(14, ge=1, le=60),
    _: CurrentUser = Depends(require_auth),
):
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")
    now = datetime.utcnow()
    m_now = now.strftime("%Y-%m")
    try:
        bundle = CloudCostClient(s.CLOUDCOST_ENDPOINT).dashboard_bundle(m_now, "daily", 1)
    except Exception as e:
        raise HTTPException(502, f"云管 dashboard 查询失败: {e}")
    points = (bundle.get("trend") or [])
    # keep last N points
    points = sorted(points, key=lambda p: p.get("date", ""))[-days:]
    return [DailyPoint(date=p.get("date", ""), cost=float(p.get("cost", 0) or 0)) for p in points]
