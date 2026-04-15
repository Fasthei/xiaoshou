"""Thin pass-through endpoints that forward to cloudcost (云管) for UI consumption.

These live in xiaoshou so the SPA has a single origin to talk to and shares the
user's Casdoor token. Read-only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.integrations import CloudCostClient

router = APIRouter(prefix="/api/bridge", tags=["云管桥接"])


def _cloud() -> CloudCostClient:
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")
    return CloudCostClient(s.CLOUDCOST_ENDPOINT, match_field=s.CLOUDCOST_MATCH_FIELD)


@router.get("/alerts", summary="预警规则执行态（代理云管）")
def alerts(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
           _: CurrentUser = Depends(require_auth)):
    try:
        return _cloud().alerts_rule_status(month)
    except Exception as e:
        raise HTTPException(502, f"cloudcost alerts 查询失败: {e}")


@router.get("/bills", summary="月度账单列表（代理云管）")
def bills(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
          status: Optional[str] = None, page: int = 1, page_size: int = 50,
          _: CurrentUser = Depends(require_auth)):
    try:
        return _cloud().bills(month=month, status=status, page=page, page_size=page_size)
    except Exception as e:
        raise HTTPException(502, f"cloudcost bills 查询失败: {e}")


@router.get("/dashboard", summary="云管 dashboard bundle（代理）")
def dashboard(month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
              _: CurrentUser = Depends(require_auth)):
    m = month or datetime.utcnow().strftime("%Y-%m")
    try:
        return _cloud().dashboard_bundle(m)
    except Exception as e:
        raise HTTPException(502, f"cloudcost dashboard 查询失败: {e}")
