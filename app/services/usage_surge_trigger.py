"""usage_surge_trigger — 用量激增预警触发器.

算法 (方案 A: service 级聚合, 不含 sku):
  对每条 enabled=true && rule_type='usage_surge' 的规则:
    1. 确定客户范围 (规则有 customer_id → 单客户; 否则全库客户)
    2. 对每个客户, 从 cc_usage.raw.accounts[] 按 service 聚合当月 vs 上月总费用
    3. service 环比增幅 >= threshold_value% → 触发, 插入 alert_event (去重)
  返回本次新增触发数量.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.cc_usage import CCUsage
from app.models.customer import Customer

logger = logging.getLogger(__name__)


def _ym_prev(year: int, month: int) -> Tuple[int, int]:
    """返回上一个月的 (year, month)."""
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _month_date_range(year: int, month: int) -> Tuple[date, date]:
    """返回 (start_inclusive, end_exclusive) 日期区间."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return start, end


def _aggregate_service_cost(rows: List[CCUsage]) -> Dict[str, float]:
    """从 cc_usage 行列表中按 service 聚合总费用.

    cc_usage.raw 结构: {"accounts": [{"service": "...", "cost": float, ...}]}
    若 raw 为空或格式不符, 退回 total_cost 聚合到 "云服务" 桶.
    """
    svc_cost: Dict[str, float] = {}
    for row in rows:
        raw = row.raw or {}
        accounts = raw.get("accounts") if isinstance(raw, dict) else None
        if accounts and isinstance(accounts, list):
            for entry in accounts:
                if not isinstance(entry, dict):
                    continue
                svc = (entry.get("service") or "云服务").strip() or "云服务"
                cost = float(entry.get("cost") or 0)
                svc_cost[svc] = svc_cost.get(svc, 0.0) + cost
        else:
            # fallback: total_cost 归入 "云服务"
            svc_cost["云服务"] = svc_cost.get("云服务", 0.0) + float(row.total_cost or 0)
    return svc_cost


def _fetch_month_usage(
    db: Session, customer_code: str, year: int, month: int,
) -> Dict[str, float]:
    """查询指定客户指定月的 service 级费用聚合."""
    start, end = _month_date_range(year, month)
    rows = db.query(CCUsage).filter(
        CCUsage.customer_code == customer_code,
        CCUsage.date >= start,
        CCUsage.date < end,
    ).all()
    return _aggregate_service_cost(rows)


def _evaluate_customer(
    db: Session,
    rule: AlertRule,
    customer: Customer,
    this_year: int,
    this_month: int,
    month_str: str,
    threshold_pct: float,
) -> int:
    """对单个客户评估 usage_surge 规则, 返回新触发数量."""
    if not customer.customer_code:
        return 0

    prev_year, prev_month = _ym_prev(this_year, this_month)
    curr_svc = _fetch_month_usage(db, customer.customer_code, this_year, this_month)
    prev_svc = _fetch_month_usage(db, customer.customer_code, prev_year, prev_month)

    if not curr_svc and not prev_svc:
        return 0

    triggered = 0
    for svc, curr_cost in curr_svc.items():
        prev_cost = prev_svc.get(svc, 0.0)
        if prev_cost <= 0:
            # 上月无数据, 无法计算环比, 跳过
            continue
        pct = (curr_cost - prev_cost) / prev_cost * 100.0
        if pct < threshold_pct:
            continue

        # 触发: 尝试插入 alert_event (唯一键去重, 用 savepoint 保护)
        message = (
            f"Service {svc} 用量环比 +{pct:.1f}%"
            f" (当月 ¥{curr_cost:.2f} vs 上月 ¥{prev_cost:.2f})"
        )
        event = AlertEvent(
            alert_rule_id=rule.id,
            alert_type="usage_surge",
            customer_id=customer.id,
            service=svc[:200],
            month=month_str,
            actual_pct=Decimal(str(round(pct, 2))),
            threshold_value=rule.threshold_value,
            message=message,
        )
        try:
            db.begin_nested()  # savepoint — rollback 只回滚到此点
            db.add(event)
            db.flush()
            triggered += 1
            logger.info(
                "usage_surge triggered: rule=%s customer=%s service=%s pct=%.1f%%",
                rule.id, customer.id, svc, pct,
            )
        except IntegrityError:
            db.rollback()  # 回滚到 savepoint, 不影响外层事务
            logger.debug(
                "usage_surge dedup skip: rule=%s customer=%s service=%s month=%s",
                rule.id, customer.id, svc, month_str,
            )

    return triggered


def evaluate_usage_surge_rules(db: Session) -> int:
    """评估所有启用的 usage_surge 规则, 触发并记录预警事件.

    Returns:
        本次新增触发的 alert_event 数量.
    """
    today = date.today()
    this_year, this_month = today.year, today.month
    month_str = f"{this_year:04d}-{this_month:02d}"

    rules: List[AlertRule] = db.query(AlertRule).filter(
        AlertRule.enabled == True,  # noqa: E712
        AlertRule.rule_type == "usage_surge",
    ).all()

    if not rules:
        logger.info("evaluate_usage_surge_rules: no enabled usage_surge rules found")
        return 0

    total_triggered = 0

    for rule in rules:
        threshold_pct = float(rule.threshold_value or 0)
        if threshold_pct <= 0:
            logger.warning("rule %s has threshold_value <= 0, skipping", rule.id)
            continue

        try:
            if rule.customer_id is not None:
                # 单客户规则
                customer = db.query(Customer).filter(
                    Customer.id == rule.customer_id,
                    Customer.is_deleted == False,  # noqa: E712
                ).first()
                customers = [customer] if customer else []
            else:
                # 全局规则: 评估所有未删除客户
                customers = db.query(Customer).filter(
                    Customer.is_deleted == False,  # noqa: E712
                ).all()

            for customer in customers:
                n = _evaluate_customer(
                    db, rule, customer,
                    this_year, this_month, month_str, threshold_pct,
                )
                total_triggered += n

        except Exception as exc:
            db.rollback()
            logger.exception("evaluate rule %s failed: %s", rule.id, exc)
            continue

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("evaluate_usage_surge_rules commit failed: %s", exc)
        return 0

    logger.info(
        "evaluate_usage_surge_rules done: rules=%d triggered=%d month=%s",
        len(rules), total_triggered, month_str,
    )
    return total_triggered
