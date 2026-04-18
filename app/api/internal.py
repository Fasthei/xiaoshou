"""Internal API consumed by the 云管 system to pull allocation records.

Auth: accepts either
- Authorization: Bearer <Casdoor client_credentials JWT> whose `aud` is in
  CASDOOR_INTERNAL_ALLOWED_CLIENTS, OR
- X-Internal-Api-Key: <static key> matching XIAOSHOU_INTERNAL_API_KEY (bootstrap).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.integrations.casdoor_m2m import verify_internal
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.resource import Resource
from app.services.usage_surge_trigger import evaluate_usage_surge_rules
from app.services.contract_expiry_trigger import evaluate_contract_expiring_rules

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["内部 M2M"])


def _auth(request: Request, x_internal_api_key: Optional[str] = Header(None)) -> None:
    auth = request.headers.get("authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else None
    if not verify_internal(token, x_internal_api_key):
        raise HTTPException(401, "internal auth failed")


@router.get("/allocations", summary="供云管拉取分配结果（货源编号↔客户编号）")
def export_allocations(
    since: Optional[str] = Query(None, description="ISO8601，只返回 updated_at>=since"),
    limit: int = Query(1000, ge=1, le=5000),
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(Allocation, Customer, Resource) \
        .join(Customer, Customer.id == Allocation.customer_id) \
        .join(Resource, Resource.id == Allocation.resource_id) \
        .filter(Allocation.is_deleted == False)  # noqa: E712

    if since:
        try:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "invalid `since`, expect ISO8601")
        q = q.filter(Allocation.updated_at >= dt)

    rows = q.order_by(Allocation.updated_at.desc()).limit(limit).all()

    items = []
    for a, c, r in rows:
        items.append({
            "allocation_code": a.allocation_code,
            "customer_code": c.customer_code,
            "resource_code": r.resource_code,
            "allocated_quantity": a.allocated_quantity,
            "unit_cost": float(a.unit_cost) if a.unit_cost is not None else None,
            "unit_price": float(a.unit_price) if a.unit_price is not None else None,
            "total_cost": float(a.total_cost) if a.total_cost is not None else None,
            "total_price": float(a.total_price) if a.total_price is not None else None,
            "profit_amount": float(a.profit_amount) if a.profit_amount is not None else None,
            "allocation_status": a.allocation_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })
    return {"total": len(items), "items": items}


@router.post(
    "/cron/usage-surge",
    summary="用量激增预警 cron 触发（外部定时任务调用）",
    description=(
        "评估所有启用的 usage_surge 预警规则并写入 alert_event。\n\n"
        "Auth: 与 /api/internal/* 同——接受 X-Internal-Api-Key 或 M2M Bearer JWT。\n\n"
        "推荐调度频率：每小时一次（每天也可，取决于业务监控精度需求）。\n"
        "Azure Container Apps 用法：建 Scheduled Job，Command 为\n"
        "`curl -sf -X POST $API_BASE/api/internal/cron/usage-surge "
        "-H 'X-Internal-Api-Key: $XIAOSHOU_INTERNAL_API_KEY'`。"
    ),
)
def cron_usage_surge(
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    """触发 usage_surge 规则评估。失败时返回 500，不阻塞调用方重试。"""
    try:
        triggered = evaluate_usage_surge_rules(db)
    except Exception as exc:
        logger.exception("cron_usage_surge failed: %s", exc)
        raise HTTPException(500, f"usage_surge evaluation error: {exc}") from exc

    logger.info("cron_usage_surge: triggered=%d", triggered)
    return {
        "ok": True,
        "triggered_events": triggered,
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
    }


@router.post(
    "/cron/contract-expiring",
    summary="合同到期提醒 cron 触发（外部定时任务调用）",
    description=(
        "评估所有启用的 contract_expiring 预警规则并写入 alert_event。\n\n"
        "Auth: 与 /api/internal/* 同——接受 X-Internal-Api-Key 或 M2M Bearer JWT。\n\n"
        "推荐调度频率：每天一次。\n"
        "Azure Container Apps 用法：建 Scheduled Job，Command 为\n"
        "`curl -sf -X POST $API_BASE/api/internal/cron/contract-expiring "
        "-H 'X-Internal-Api-Key: $XIAOSHOU_INTERNAL_API_KEY'`。"
    ),
)
def cron_contract_expiring(
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    """触发 contract_expiring 规则评估。失败时返回 500，不阻塞调用方重试。"""
    try:
        triggered = evaluate_contract_expiring_rules(db)
    except Exception as exc:
        logger.exception("cron_contract_expiring failed: %s", exc)
        raise HTTPException(500, f"contract_expiring evaluation error: {exc}") from exc

    logger.info("cron_contract_expiring: triggered=%d", triggered)
    return {
        "ok": True,
        "triggered_events": triggered,
        "evaluated_at": datetime.utcnow().isoformat() + "Z",
    }
