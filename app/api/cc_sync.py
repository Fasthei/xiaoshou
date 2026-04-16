"""云管数据本地化: sync 接口 + 本地读取接口.

前端客户详情用量/预警/账单 tab 从 local 读; 云管数据通过 sync 接口拉到本地表
(cc_usage / cc_alert / cc_bill). 不再每次走 bridge 实时代理.
"""
from __future__ import annotations

import logging
from datetime import datetime, date as date_cls, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations import CloudCostClient
from app.models.customer import Customer
from app.models.cc_usage import CCUsage
from app.models.cc_alert import CCAlert
from app.models.cc_bill import CCBill
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)

sync_router = APIRouter(prefix="/api/sync/cloudcost", tags=["云管本地化同步"])
local_router = APIRouter(prefix="/api/customers", tags=["客户-本地云管数据"])


# ---------- helpers ----------

def _bearer_from_request(request: Request) -> Optional[str]:
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


def _current_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _dec(v: Any, default: Any = 0) -> Optional[Decimal]:
    if v is None:
        return Decimal(str(default)) if default is not None else None
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(str(default)) if default is not None else None


def _new_sync_log(
    db: Session, sync_type: str, user: CurrentUser,
) -> SyncLog:
    log = SyncLog(
        source_system="cloudcost", sync_type=sync_type,
        triggered_by=f"{user.sub}:{user.name}", status="running",
    )
    db.add(log); db.commit(); db.refresh(log)
    return log


def _finish_log(db: Session, log: SyncLog, status: str,
                pulled: int, created: int, updated: int,
                skipped: int, errors: int, err_msg: Optional[str] = None) -> None:
    log.pulled_count = pulled
    log.created_count = created
    log.updated_count = updated
    log.skipped_count = skipped
    log.error_count = errors
    log.status = status
    log.finished_at = datetime.utcnow()
    if err_msg:
        log.last_error = err_msg[:2000]
    db.add(log); db.commit()


# ---------- M2: sync endpoints ----------

@sync_router.post("/usage", summary="从云管同步客户用量到本地 cc_usage 表")
def sync_cloudcost_usage(
    request: Request,
    customer_id: int = Query(..., description="xiaoshou.customer.id"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """给定客户, 调云管拉近 N 天用量, upsert cc_usage (by customer_code+date).

    匹配逻辑:
      1. 调 cloudcost.list_service_accounts() 拉全部货源.
      2. service_account.external_project_id == customer.customer_code → 主匹配.
      3. 若不匹配, 再看 supplier_name == customer_code 做次级匹配.
      4. 仍不匹配 → skip, 写 sync_log warning.
    """
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    log = _new_sync_log(db, f"usage:{customer.customer_code}", user)
    created = updated = skipped = errors = 0
    pulled = 0
    warnings: List[str] = []

    try:
        client = _cloud(request)
        accounts = client.list_service_accounts(page=1, page_size=500)

        # Match service accounts → this customer
        code = str(customer.customer_code or "").strip()
        matched = [
            a for a in accounts
            if (a.external_project_id and str(a.external_project_id) == code)
        ]
        if not matched:
            # 次级匹配: supplier_name
            matched = [
                a for a in accounts
                if (a.supplier_name and str(a.supplier_name) == code)
            ]
            if matched:
                warnings.append(f"使用 supplier_name 做次级匹配命中 {len(matched)} 个货源")

        if not matched:
            warnings.append(f"customer_code={code} 在云管 external_project_id/supplier_name 均未命中")
            _finish_log(db, log, "success", pulled, created, updated, skipped, errors,
                        "; ".join(warnings))
            return {
                "customer_id": customer_id, "customer_code": code, "days": days,
                "matched_accounts": 0, "pulled": 0, "created": 0, "updated": 0,
                "skipped": 0, "errors": 0, "sync_log_id": log.id,
                "warning": "; ".join(warnings),
            }

        # Aggregate daily rows across all matched accounts
        # { date_iso: {"total_cost":D, "total_usage":D, "record_count":int, "raw":{"accounts":[...]}} }
        agg: Dict[str, Dict[str, Any]] = {}

        for a in matched:
            try:
                raw = client.get_customer_usage(a.id, days=days)
            except Exception as e:
                logger.warning("get_customer_usage account=%s failed: %s", a.id, e)
                errors += 1
                continue

            # cloudcost 可能返回 list 或 dict{"items":[...]}
            items = raw if isinstance(raw, list) else (
                (raw or {}).get("items") if isinstance(raw, dict) else None
            ) or (
                (raw or {}).get("data") if isinstance(raw, dict) else None
            ) or []
            if not isinstance(items, list):
                items = []
            pulled += len(items)

            for it in items:
                if not isinstance(it, dict):
                    continue
                d_raw = (it.get("date") or it.get("bill_date") or it.get("day")
                         or it.get("cost_date") or "")
                d_iso = str(d_raw)[:10]
                if not d_iso:
                    continue
                slot = agg.setdefault(d_iso, {
                    "total_cost": Decimal("0"),
                    "total_usage": Decimal("0"),
                    "record_count": 0,
                    "raw": {"accounts": []},
                })
                cost = _dec(it.get("cost") or it.get("total_cost") or it.get("amount") or 0)
                usage_ = _dec(it.get("usage") or it.get("total_usage") or it.get("quantity") or 0)
                slot["total_cost"] += cost or Decimal("0")
                slot["total_usage"] += usage_ or Decimal("0")
                slot["record_count"] += 1
                slot["raw"]["accounts"].append({
                    "account_id": a.id, "service": it.get("service") or it.get("name"),
                    "cost": float(cost or 0), "usage": float(usage_ or 0),
                    "date": d_iso,
                })

        # upsert into cc_usage
        for d_iso, vals in agg.items():
            try:
                try:
                    d_obj = date_cls.fromisoformat(d_iso)
                except Exception:
                    continue
                existing = db.query(CCUsage).filter(
                    CCUsage.customer_code == code, CCUsage.date == d_obj,
                ).first()
                if existing:
                    existing.total_cost = vals["total_cost"]
                    existing.total_usage = vals["total_usage"]
                    existing.record_count = vals["record_count"]
                    existing.raw = vals["raw"]
                    existing.sync_at = datetime.utcnow()
                    db.add(existing)
                    updated += 1
                else:
                    db.add(CCUsage(
                        customer_code=code, date=d_obj,
                        total_cost=vals["total_cost"],
                        total_usage=vals["total_usage"],
                        record_count=vals["record_count"],
                        raw=vals["raw"],
                    ))
                    created += 1
            except Exception as e:
                logger.exception("upsert cc_usage %s %s failed: %s", code, d_iso, e)
                errors += 1

        db.commit()
        _finish_log(db, log, "success" if errors == 0 else "failed",
                    pulled, created, updated, skipped, errors,
                    "; ".join(warnings) if warnings else None)
    except Exception as e:
        db.rollback()
        logger.exception("sync usage failed: %s", e)
        _finish_log(db, log, "failed", pulled, created, updated, skipped, errors + 1, str(e))
        raise HTTPException(502, f"云管用量同步失败: {e}")

    return {
        "customer_id": customer_id, "customer_code": code, "days": days,
        "matched_accounts": len(matched),
        "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
        "warning": "; ".join(warnings) if warnings else None,
    }


@sync_router.post("/alerts", summary="从云管同步预警规则快照到本地 cc_alert 表")
def sync_cloudcost_alerts(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    m = month or _current_month()
    log = _new_sync_log(db, f"alerts:{m}", user)
    created = updated = skipped = errors = 0
    pulled = 0
    try:
        client = _cloud(request)
        items = client.alerts_rule_status(m)
        pulled = len(items) if isinstance(items, list) else 0

        for it in items or []:
            if not isinstance(it, dict):
                skipped += 1
                continue
            try:
                rule_id = it.get("rule_id") or it.get("id")
                if rule_id is None:
                    skipped += 1
                    continue
                rule_id_i = int(rule_id)
                payload = dict(
                    rule_id=rule_id_i,
                    rule_name=(it.get("rule_name") or it.get("name") or "")[:200] or None,
                    threshold_type=(it.get("threshold_type") or it.get("type") or "")[:40] or None,
                    threshold_value=_dec(it.get("threshold_value") or it.get("threshold"), None),
                    actual=_dec(it.get("actual") or it.get("actual_value"), None),
                    pct=_dec(it.get("pct") or it.get("percent"), None),
                    triggered=bool(it.get("triggered") or it.get("is_triggered") or False),
                    account_name=(it.get("account_name") or it.get("account") or "")[:200] or None,
                    provider=(it.get("provider") or "")[:40] or None,
                    external_project_id=(it.get("external_project_id")
                                         or it.get("customer_code") or "")[:200] or None,
                    month=m,
                )
                existing = db.query(CCAlert).filter(
                    CCAlert.rule_id == rule_id_i, CCAlert.month == m,
                ).first()
                if existing:
                    changed = False
                    for k, v in payload.items():
                        if getattr(existing, k, None) != v:
                            setattr(existing, k, v); changed = True
                    existing.sync_at = datetime.utcnow()
                    db.add(existing)
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(CCAlert(**payload))
                    created += 1
            except Exception as e:
                logger.exception("upsert cc_alert failed: %s", e)
                errors += 1

        db.commit()
        _finish_log(db, log, "success" if errors == 0 else "failed",
                    pulled, created, updated, skipped, errors)
    except Exception as e:
        db.rollback()
        logger.exception("sync alerts failed: %s", e)
        _finish_log(db, log, "failed", pulled, created, updated, skipped, errors + 1, str(e))
        raise HTTPException(502, f"云管预警同步失败: {e}")

    return {
        "month": m, "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
    }


@sync_router.post("/bills", summary="从云管同步月度账单到本地 cc_bill 表")
def sync_cloudcost_bills(
    request: Request,
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    m = month or _current_month()
    log = _new_sync_log(db, f"bills:{m}", user)
    created = updated = skipped = errors = 0
    pulled = 0
    try:
        client = _cloud(request)
        raw = client.bills(month=m, page=1, page_size=500)
        items = raw if isinstance(raw, list) else (
            (raw or {}).get("items") or (raw or {}).get("data") or []
        ) if isinstance(raw, dict) else []
        if not isinstance(items, list):
            items = []
        pulled = len(items)

        # Build external_project_id → customer_code map via service accounts
        # (用作账单 customer_code 推断)
        project_to_code: Dict[str, str] = {}
        try:
            accounts = client.list_service_accounts(page=1, page_size=500)
            for a in accounts:
                if a.external_project_id:
                    project_to_code[str(a.external_project_id)] = str(a.external_project_id)
        except Exception:
            pass

        for it in items:
            if not isinstance(it, dict):
                skipped += 1
                continue
            try:
                remote_id = it.get("id")
                if remote_id is None:
                    skipped += 1
                    continue
                remote_id_i = int(remote_id)
                ext = (it.get("external_project_id") or it.get("customer_code") or "")
                customer_code = project_to_code.get(str(ext)) if ext else None
                if not customer_code and ext:
                    customer_code = str(ext)

                payload = dict(
                    remote_id=remote_id_i,
                    month=(it.get("month") or m)[:7],
                    provider=(it.get("provider") or "")[:40] or None,
                    original_cost=_dec(it.get("original_cost") or it.get("original_amount"), None),
                    markup_rate=_dec(it.get("markup_rate"), None),
                    final_cost=_dec(it.get("final_cost") or it.get("amount")
                                    or it.get("total_amount"), None),
                    adjustment=_dec(it.get("adjustment"), None),
                    status=(it.get("status") or "")[:20] or None,
                    notes=it.get("notes"),
                    customer_code=(customer_code or "")[:80] or None,
                    raw=it,
                )
                existing = db.query(CCBill).filter(CCBill.remote_id == remote_id_i).first()
                if existing:
                    changed = False
                    for k, v in payload.items():
                        if getattr(existing, k, None) != v:
                            setattr(existing, k, v); changed = True
                    existing.sync_at = datetime.utcnow()
                    db.add(existing)
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(CCBill(**payload))
                    created += 1
            except Exception as e:
                logger.exception("upsert cc_bill failed: %s", e)
                errors += 1

        db.commit()
        _finish_log(db, log, "success" if errors == 0 else "failed",
                    pulled, created, updated, skipped, errors)
    except Exception as e:
        db.rollback()
        logger.exception("sync bills failed: %s", e)
        _finish_log(db, log, "failed", pulled, created, updated, skipped, errors + 1, str(e))
        raise HTTPException(502, f"云管账单同步失败: {e}")

    return {
        "month": m, "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
    }


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
