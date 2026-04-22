"""云管数据同步服务层 — 被 /api/sync/cloudcost/* (用户触发) 和
/api/internal/cron/sync-cloudcost-* (M2M cron) 共用.

职责：
    1. 从 cloudcost 拉账单 / 用量 / 预警.
    2. 写入本地 cc_bill / cc_usage / cc_alert.
    3. 统一维护 SyncLog 审计记录.

接口约定：所有 do_sync_* 函数接收 (db, client, triggered_by, ...)；
返回标准化 dict（包含 sync_log_id / 计数 / warning）；
异常不往外抛——全部吞入 SyncLog，由调用方决定是否转 HTTP 5xx.
"""
from __future__ import annotations

import logging
from datetime import datetime, date as date_cls, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.integrations import CloudCostClient
from app.models.customer import Customer
from app.models.cc_usage import CCUsage
from app.models.cc_alert import CCAlert
from app.models.cc_bill import CCBill
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)


# ---------- 通用 helpers ----------

def current_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _dec(v: Any, default: Any = 0) -> Optional[Decimal]:
    if v is None:
        return Decimal(str(default)) if default is not None else None
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(str(default)) if default is not None else None


def build_cloud_client(bearer_token: Optional[str] = None) -> CloudCostClient:
    """构造 CloudCostClient.

    优先用 CLOUDCOST_API_KEY（云管推荐的 AI/自动化鉴权方式；适合 cron/M2M）；
    若未配置则回退到转发调用方 Casdoor JWT（仅用户触发的路径上会提供）.
    """
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise RuntimeError("CLOUDCOST_ENDPOINT not configured")
    api_key = s.CLOUDCOST_API_KEY or None
    return CloudCostClient(
        s.CLOUDCOST_ENDPOINT,
        match_field=s.CLOUDCOST_MATCH_FIELD,
        api_key=api_key,
        bearer_token=bearer_token if not api_key else None,
    )


def _new_sync_log(db: Session, sync_type: str, triggered_by: str) -> SyncLog:
    log = SyncLog(
        source_system="cloudcost", sync_type=sync_type,
        triggered_by=triggered_by[:128], status="running",
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


# ---------- 账单同步 ----------

def do_sync_bills(
    db: Session, client: CloudCostClient, triggered_by: str,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    """同步云管月度账单 → cc_bill. 失败时写 SyncLog 但不抛异常."""
    m = month or current_month()
    log = _new_sync_log(db, f"bills:{m}", triggered_by)
    created = updated = skipped = errors = 0
    pulled = 0
    error_msg: Optional[str] = None

    try:
        raw = client.bills(month=m, page=1, page_size=500)
        items = raw if isinstance(raw, list) else (
            (raw or {}).get("items") or (raw or {}).get("data") or []
        ) if isinstance(raw, dict) else []
        if not isinstance(items, list):
            items = []
        pulled = len(items)

        # external_project_id → customer_code map（账单 customer_code 推断）
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
    except Exception as e:
        db.rollback()
        logger.exception("sync bills failed: %s", e)
        errors += 1
        error_msg = str(e)

    status = "success" if errors == 0 else "failed"
    _finish_log(db, log, status, pulled, created, updated, skipped, errors, error_msg)

    return {
        "ok": errors == 0,
        "month": m, "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
        "error": error_msg,
    }


# ---------- 预警同步 ----------

def do_sync_alerts(
    db: Session, client: CloudCostClient, triggered_by: str,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    m = month or current_month()
    log = _new_sync_log(db, f"alerts:{m}", triggered_by)
    created = updated = skipped = errors = 0
    pulled = 0
    error_msg: Optional[str] = None

    try:
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
    except Exception as e:
        db.rollback()
        logger.exception("sync alerts failed: %s", e)
        errors += 1
        error_msg = str(e)

    status = "success" if errors == 0 else "failed"
    _finish_log(db, log, status, pulled, created, updated, skipped, errors, error_msg)

    return {
        "ok": errors == 0,
        "month": m, "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
        "error": error_msg,
    }


# ---------- 用量同步（按客户 / 全量） ----------

def do_sync_usage_for_customer(
    db: Session, client: CloudCostClient, triggered_by: str,
    customer: Customer, days: int = 30,
) -> Dict[str, Any]:
    """拉近 N 天用量 upsert 到 cc_usage (by customer_code+date)."""
    log = _new_sync_log(db, f"usage:{customer.customer_code}", triggered_by)
    created = updated = skipped = errors = 0
    pulled = 0
    warnings: List[str] = []
    error_msg: Optional[str] = None

    try:
        accounts = client.list_service_accounts(page=1, page_size=500)
        code = str(customer.customer_code or "").strip()

        matched = [
            a for a in accounts
            if (a.external_project_id and str(a.external_project_id) == code)
        ]
        if not matched:
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
                "ok": True,
                "customer_id": customer.id, "customer_code": code, "days": days,
                "matched_accounts": 0, "pulled": 0, "created": 0, "updated": 0,
                "skipped": 0, "errors": 0, "sync_log_id": log.id,
                "warning": "; ".join(warnings),
            }

        agg: Dict[str, Dict[str, Any]] = {}
        end_d = date_cls.today()
        start_d = end_d - timedelta(days=max(1, int(days)))
        start_iso = start_d.isoformat()
        end_iso = end_d.isoformat()

        for a in matched:
            items_iter: Optional[List[Dict[str, Any]]] = None
            used_metering = False
            try:
                metering_rows = list(client.metering_detail_iter(
                    start_date=start_iso, end_date=end_iso,
                    account_id=a.id, page_size=500,
                ))
                used_metering = True
                items_iter = metering_rows
                pulled += len(metering_rows)
            except Exception as e:
                logger.warning(
                    "metering_detail account=%s failed, falling back to /costs: %s",
                    a.id, e,
                )

            if items_iter is None:
                try:
                    raw = client.get_customer_usage(a.id, days=days)
                except Exception as e:
                    logger.warning("get_customer_usage account=%s failed: %s", a.id, e)
                    errors += 1
                    continue

                legacy_items = raw if isinstance(raw, list) else (
                    (raw or {}).get("items") if isinstance(raw, dict) else None
                ) or (
                    (raw or {}).get("data") if isinstance(raw, dict) else None
                ) or []
                if not isinstance(legacy_items, list):
                    legacy_items = []
                items_iter = [x for x in legacy_items if isinstance(x, dict)]
                pulled += len(items_iter)

            for it in items_iter:
                if not isinstance(it, dict):
                    continue
                d_raw = (it.get("date") or it.get("usage_date")
                         or it.get("bill_date") or it.get("day")
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
                cost = _dec(
                    it.get("cost") or it.get("total_cost")
                    or it.get("amount") or it.get("final_cost") or 0
                )
                usage_ = _dec(
                    it.get("usage") or it.get("total_usage")
                    or it.get("quantity") or 0
                )
                slot["total_cost"] += cost or Decimal("0")
                slot["total_usage"] += usage_ or Decimal("0")
                slot["record_count"] += 1
                slot["raw"]["accounts"].append({
                    "account_id": a.id,
                    "service": (it.get("service") or it.get("service_name")
                                or it.get("name") or "云服务"),
                    "cost": float(cost or 0),
                    "usage": float(usage_ or 0),
                    "date": d_iso,
                    "source": "metering" if used_metering else "legacy",
                })

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
    except Exception as e:
        db.rollback()
        logger.exception("sync usage for customer=%s failed: %s", customer.id, e)
        errors += 1
        error_msg = str(e)

    status = "success" if errors == 0 else "failed"
    _finish_log(db, log, status, pulled, created, updated, skipped, errors,
                error_msg or ("; ".join(warnings) if warnings else None))

    return {
        "ok": errors == 0,
        "customer_id": customer.id, "customer_code": customer.customer_code,
        "days": days, "matched_accounts": len(matched),
        "pulled": pulled, "created": created, "updated": updated,
        "skipped": skipped, "errors": errors, "sync_log_id": log.id,
        "warning": "; ".join(warnings) if warnings else None,
        "error": error_msg,
    }


def last_successful_sync_at(db: Session) -> Optional[datetime]:
    """返回最近一次 cloudcost 侧 SyncLog 状态=success 的 started_at。

    用于"距离上次同步的增量同步"语义 —— 新 endpoint POST /run 据此计算 days。
    """
    row = (
        db.query(SyncLog)
        .filter(
            SyncLog.source_system == "cloudcost",
            SyncLog.status == "success",
        )
        .order_by(SyncLog.started_at.desc())
        .first()
    )
    return row.started_at if row else None


def do_sync_incremental(
    db: Session, client: CloudCostClient, triggered_by: str,
    fallback_days: int = 365, max_days: int = 365,
) -> Dict[str, Any]:
    """一键增量同步 —— 距上次成功同步至今的天数.

    计算 days:
      - 有上次成功记录: days = max(1, ceil((now - last).total_seconds() / 86400))
      - 无记录 (首次): days = fallback_days
      - 上限 max_days

    执行顺序:
      1. bills (当月) — cloudcost 月度账单每日增量更新，当月覆盖一次即可
      2. alerts (当月) — 规则快照
      3. usage-all (days) — 真正的时间差增量

    三段单独计数；整体 ok 当且仅当三段都 errors=0.
    """
    now = datetime.utcnow()
    last = last_successful_sync_at(db)
    if last is None:
        days = fallback_days
    else:
        delta = (now - last).total_seconds() / 86400
        # 向上取整并至少 1；上次同步<24h 也拉 1 天，确保"今天当日"数据补齐
        import math
        days = max(1, math.ceil(delta))
    days = min(days, max_days)

    m = current_month()
    bills_r = do_sync_bills(db, client, triggered_by, month=m)
    alerts_r = do_sync_alerts(db, client, triggered_by, month=m)
    usage_r = do_sync_usage_all(db, client, triggered_by, days=days)

    all_ok = bool(bills_r.get("ok") and alerts_r.get("ok") and usage_r.get("ok"))
    return {
        "ok": all_ok,
        "last_sync_at": last.isoformat() + "Z" if last else None,
        "days_covered": days,
        "started_at": now.isoformat() + "Z",
        "bills": bills_r,
        "alerts": alerts_r,
        "usage": {
            # usage_r.per_customer 对前端过于冗长，剔掉
            k: v for k, v in usage_r.items() if k != "per_customer"
        },
    }


def do_sync_usage_all(
    db: Session, client: CloudCostClient, triggered_by: str,
    days: int = 30,
) -> Dict[str, Any]:
    """遍历所有未删除的客户，逐一同步其 cc_usage。汇总计数."""
    log = _new_sync_log(db, f"usage-all:{days}d", triggered_by)
    total_customers = 0
    total_matched = 0
    total_pulled = total_created = total_updated = total_errors = 0
    per_customer: List[Dict[str, Any]] = []
    error_msg: Optional[str] = None

    try:
        customers = db.query(Customer).filter(
            Customer.is_deleted == False,  # noqa: E712
            Customer.customer_code.isnot(None),
        ).all()
        total_customers = len(customers)

        for c in customers:
            # 单客户的同步会自己写 SyncLog —— 这里是汇总，所以不再重复
            r = do_sync_usage_for_customer(db, client, triggered_by, c, days=days)
            total_matched += int(r.get("matched_accounts") or 0)
            total_pulled += int(r.get("pulled") or 0)
            total_created += int(r.get("created") or 0)
            total_updated += int(r.get("updated") or 0)
            total_errors += int(r.get("errors") or 0)
            per_customer.append({
                "customer_id": r.get("customer_id"),
                "customer_code": r.get("customer_code"),
                "matched_accounts": r.get("matched_accounts"),
                "pulled": r.get("pulled"), "created": r.get("created"),
                "updated": r.get("updated"), "errors": r.get("errors"),
            })
    except Exception as e:
        logger.exception("sync usage-all failed: %s", e)
        total_errors += 1
        error_msg = str(e)

    status = "success" if total_errors == 0 else "failed"
    _finish_log(
        db, log, status,
        total_pulled, total_created, total_updated, 0, total_errors, error_msg,
    )

    return {
        "ok": total_errors == 0,
        "days": days,
        "customers_processed": total_customers,
        "matched_accounts_total": total_matched,
        "pulled": total_pulled, "created": total_created,
        "updated": total_updated, "errors": total_errors,
        "sync_log_id": log.id,
        "per_customer": per_customer,
        "error": error_msg,
    }
