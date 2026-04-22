"""云管数据本地化: sync 接口 + 本地读取接口.

前端客户详情用量/预警/账单 tab 从 local 读; 云管数据通过 sync 接口拉到本地表
(cc_usage / cc_alert / cc_bill). 不再每次走 bridge 实时代理.

同步业务逻辑集中在 app.services.cloudcost_sync；这里只负责：
    1. HTTP 路由入参校验
    2. 构造 CloudCostClient（可回退到转发用户 bearer）
    3. 调用 service function
    4. 把 service 返回的 dict 按 HTTP 口径返回（错误 → 502）
"""
from __future__ import annotations

import logging
from datetime import date as date_cls, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth, require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.cc_usage import CCUsage
from app.models.cc_alert import CCAlert
from app.models.cc_bill import CCBill
from app.services.cloudcost_sync import (
    build_cloud_client,
    current_month as _current_month,
    do_sync_alerts,
    do_sync_bills,
    do_sync_incremental,
    do_sync_usage_for_customer,
    last_successful_sync_at,
)

logger = logging.getLogger(__name__)

sync_router = APIRouter(prefix="/api/sync/cloudcost", tags=["云管本地化同步"])
local_router = APIRouter(prefix="/api/customers", tags=["客户-本地云管数据"])


# ---------- helpers ----------

def _bearer_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _client_for(request: Request):
    try:
        return build_cloud_client(bearer_token=_bearer_from_request(request))
    except RuntimeError as e:
        raise HTTPException(400, str(e))


def _triggered_by(user: CurrentUser) -> str:
    return f"{user.sub}:{user.name}"


def _raise_if_error(result: Dict[str, Any]) -> None:
    if not result.get("ok") and result.get("error"):
        raise HTTPException(502, f"云管同步失败: {result['error']}")


# ---------- M2: sync endpoints ----------

@sync_router.post("/usage", summary="从云管同步某客户用量到本地 cc_usage 表")
def sync_cloudcost_usage(
    request: Request,
    customer_id: int = Query(..., description="xiaoshou.customer.id"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    client = _client_for(request)
    result = do_sync_usage_for_customer(
        db, client, _triggered_by(user), customer, days=days,
    )
    _raise_if_error(result)
    return result


@sync_router.get(
    "/last-sync",
    summary="查询最近一次成功同步的时间戳（前端用于显示距上次同步 X 天）",
)
def get_last_sync(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    ts = last_successful_sync_at(db)
    return {
        "last_sync_at": ts.isoformat() + "Z" if ts else None,
    }


@sync_router.post(
    "/run",
    summary="增量同步云管 → 本地 (账单/用量/预警)；距上次成功同步以来的时间差",
    dependencies=[Depends(require_roles("sales-manager", "admin", "ops", "operation", "operations"))],
)
def sync_cloudcost_run(
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """账单中心`同步云管`按钮入口。

    - days 由后端根据 sync_log 里最近一次 success 的 started_at 自动算；首次
      同步 days=365.
    - 三段子任务各自写 SyncLog；本 endpoint 只做编排和汇总。
    - 任一子任务 errors>0 则整体返回 ok=false，但已成功的子任务数据已落库。
    """
    client = _client_for(request)
    result = do_sync_incremental(db, client, _triggered_by(user))
    return result


@sync_router.post("/alerts", summary="从云管同步预警规则快照到本地 cc_alert 表")
def sync_cloudcost_alerts(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    client = _client_for(request)
    result = do_sync_alerts(db, client, _triggered_by(user), month=month)
    _raise_if_error(result)
    return result


@sync_router.post("/bills", summary="从云管同步月度账单到本地 cc_bill 表")
def sync_cloudcost_bills(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    client = _client_for(request)
    result = do_sync_bills(db, client, _triggered_by(user), month=month)
    _raise_if_error(result)
    return result


# ---------- M2: local read endpoints ----------

@local_router.get("/{customer_id}/local-usage", summary="客户用量 (本地 cc_usage)")
def get_local_usage(
    customer_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    end = date_cls.today()
    start = end - timedelta(days=days)
    rows = db.query(CCUsage).filter(
        CCUsage.customer_code == customer.customer_code,
        CCUsage.date >= start, CCUsage.date <= end,
    ).order_by(CCUsage.date.asc()).all()

    total_cost = Decimal("0")
    total_usage = Decimal("0")
    record_count = 0
    by_date: List[Dict[str, Any]] = []
    for r in rows:
        total_cost += Decimal(r.total_cost or 0)
        total_usage += Decimal(r.total_usage or 0)
        record_count += int(r.record_count or 0)
        by_date.append({
            "date": r.date.isoformat() if r.date else None,
            "usage": float(r.total_usage or 0),
            "cost": float(r.total_cost or 0),
        })

    # by_service 聚合 (从 raw.accounts 里扒)
    service_agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        raw = r.raw or {}
        if isinstance(raw, dict):
            for sub in (raw.get("accounts") or []):
                if not isinstance(sub, dict):
                    continue
                svc = sub.get("service") or "云服务"
                slot = service_agg.setdefault(svc, {"usage": 0.0, "cost": 0.0})
                slot["usage"] += float(sub.get("usage") or 0)
                slot["cost"] += float(sub.get("cost") or 0)

    by_service = [
        {"service": k, "usage": v["usage"], "cost": v["cost"]}
        for k, v in sorted(service_agg.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    ]

    last_sync = None
    if rows:
        last_sync = max((r.sync_at for r in rows if r.sync_at), default=None)

    return {
        "customer_id": customer_id,
        "customer_code": customer.customer_code,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "total_cost": float(total_cost),
        "total_usage": float(total_usage),
        "record_count": record_count,
        "by_date": by_date,
        "by_service": by_service,
        "last_sync_at": last_sync.isoformat() if last_sync else None,
    }


@local_router.get("/{customer_id}/local-alerts", summary="客户预警 (本地 cc_alert)")
def get_local_alerts(
    customer_id: int,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    m = month or _current_month()
    q = db.query(CCAlert).filter(
        CCAlert.external_project_id == customer.customer_code,
        CCAlert.month == m,
    ).order_by(CCAlert.triggered.desc(), CCAlert.id.desc())
    rows = q.all()

    last_sync = max((r.sync_at for r in rows if r.sync_at), default=None) if rows else None
    return {
        "customer_id": customer_id,
        "customer_code": customer.customer_code,
        "month": m,
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "threshold_type": r.threshold_type,
                "threshold_value": float(r.threshold_value) if r.threshold_value is not None else None,
                "actual": float(r.actual) if r.actual is not None else None,
                "pct": float(r.pct) if r.pct is not None else None,
                "triggered": bool(r.triggered),
                "account_name": r.account_name,
                "provider": r.provider,
                "external_project_id": r.external_project_id,
                "month": r.month,
                "sync_at": r.sync_at.isoformat() if r.sync_at else None,
            }
            for r in rows
        ],
        "last_sync_at": last_sync.isoformat() if last_sync else None,
    }


@local_router.get("/{customer_id}/local-bills", summary="客户账单 (本地 cc_bill)")
def get_local_bills(
    customer_id: int,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    q = db.query(CCBill).filter(CCBill.customer_code == customer.customer_code)
    if month:
        q = q.filter(CCBill.month == month)
    rows = q.order_by(CCBill.month.desc(), CCBill.id.desc()).all()

    last_sync = max((r.sync_at for r in rows if r.sync_at), default=None) if rows else None
    return {
        "customer_id": customer_id,
        "customer_code": customer.customer_code,
        "month_filter": month,
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "remote_id": r.remote_id,
                "month": r.month,
                "provider": r.provider,
                "original_cost": float(r.original_cost) if r.original_cost is not None else None,
                "markup_rate": float(r.markup_rate) if r.markup_rate is not None else None,
                "final_cost": float(r.final_cost) if r.final_cost is not None else None,
                "amount": float(r.final_cost) if r.final_cost is not None else None,
                "adjustment": float(r.adjustment) if r.adjustment is not None else None,
                "status": r.status,
                "notes": r.notes,
                "customer_code": r.customer_code,
                "sync_at": r.sync_at.isoformat() if r.sync_at else None,
            }
            for r in rows
        ],
        "last_sync_at": last_sync.isoformat() if last_sync else None,
    }
