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
from app.services.cloudcost_sync import (
    build_cloud_client,
    do_sync_alerts,
    do_sync_bills,
    do_sync_usage_all,
)
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


# ---------- 云管数据同步 cron ----------
#
# 这三个入口把 /api/sync/cloudcost/* 的业务逻辑暴露给 M2M 调度器（Azure Container
# App Job / Logic App / 外部 cron），用 X-Internal-Api-Key 或 M2M JWT 鉴权。
#
# 推荐调度频率：
#   bills   → 每天一次（云管月度账单通常每日增量更新）
#   usage   → 每小时一次（或至少每 4 小时）
#   alerts  → 每小时一次（与 cron/usage-surge 对齐）
#
# 调用方式：
#   curl -sf -X POST $API_BASE/api/internal/cron/sync-cloudcost-bills \
#        -H "X-Internal-Api-Key: $XIAOSHOU_INTERNAL_API_KEY"


@router.post(
    "/cron/sync-cloudcost-bills",
    summary="云管账单同步 cron（拉 cc_bill）",
)
def cron_sync_cloudcost_bills(
    month: Optional[str] = Query(
        None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM；默认当月",
    ),
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    try:
        client = build_cloud_client()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    try:
        result = do_sync_bills(db, client, triggered_by="cron:internal", month=month)
    except Exception as exc:
        logger.exception("cron_sync_bills failed: %s", exc)
        raise HTTPException(500, f"sync bills error: {exc}") from exc

    logger.info(
        "cron_sync_bills month=%s pulled=%s created=%s updated=%s errors=%s",
        result.get("month"), result.get("pulled"),
        result.get("created"), result.get("updated"), result.get("errors"),
    )
    return result


@router.post(
    "/cron/sync-cloudcost-usage",
    summary="云管用量同步 cron（遍历所有客户，拉 cc_usage）",
)
def cron_sync_cloudcost_usage(
    days: int = Query(30, ge=1, le=365, description="回溯天数"),
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    try:
        client = build_cloud_client()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    try:
        result = do_sync_usage_all(db, client, triggered_by="cron:internal", days=days)
    except Exception as exc:
        logger.exception("cron_sync_usage failed: %s", exc)
        raise HTTPException(500, f"sync usage error: {exc}") from exc

    logger.info(
        "cron_sync_usage days=%s customers=%s pulled=%s created=%s updated=%s errors=%s",
        result.get("days"), result.get("customers_processed"),
        result.get("pulled"), result.get("created"),
        result.get("updated"), result.get("errors"),
    )
    # per_customer 列表对 cron 日志来说过于冗长，剔除掉返回
    result.pop("per_customer", None)
    return result


@router.post(
    "/cron/sync-cloudcost-alerts",
    summary="云管预警规则快照同步 cron（拉 cc_alert）",
)
def cron_sync_cloudcost_alerts(
    month: Optional[str] = Query(
        None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM；默认当月",
    ),
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    try:
        client = build_cloud_client()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    try:
        result = do_sync_alerts(db, client, triggered_by="cron:internal", month=month)
    except Exception as exc:
        logger.exception("cron_sync_alerts failed: %s", exc)
        raise HTTPException(500, f"sync alerts error: {exc}") from exc

    logger.info(
        "cron_sync_alerts month=%s pulled=%s created=%s updated=%s errors=%s",
        result.get("month"), result.get("pulled"),
        result.get("created"), result.get("updated"), result.get("errors"),
    )
    return result
