"""contract_expiry_trigger — 合同到期提醒触发器.

算法:
  对每条 enabled=true && rule_type='contract_expiring' 的规则:
    1. threshold_value = 提前天数 (如 30/60/90)
    2. 确定客户范围 (规则有 customer_id → 单客户; 否则全量)
    3. 扫 contract: status='active' && end_date in [today, today+threshold_value]
    4. 触发写 alert_event, 去重 key=(alert_rule_id, customer_id, 'contract', end_date 月份)
  返回本次新增触发数.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.alert_event import AlertEvent
from app.models.alert_rule import AlertRule
from app.models.contract import Contract
from app.models.customer import Customer

logger = logging.getLogger(__name__)


def evaluate_contract_expiring_rules(db: Session) -> int:
    """评估所有启用的 contract_expiring 规则, 触发并记录预警事件.

    Returns:
        本次新增触发的 alert_event 数量.
    """
    today = date.today()

    rules: List[AlertRule] = db.query(AlertRule).filter(
        AlertRule.enabled == True,  # noqa: E712
        AlertRule.rule_type == "contract_expiring",
    ).all()

    if not rules:
        logger.info("evaluate_contract_expiring_rules: no enabled contract_expiring rules found")
        return 0

    total_triggered = 0

    for rule in rules:
        threshold_days = int(rule.threshold_value or 0)
        if threshold_days <= 0:
            logger.warning("rule %s has threshold_value <= 0, skipping", rule.id)
            continue

        window_end = today + timedelta(days=threshold_days)

        try:
            # 构建合同查询
            contract_q = db.query(Contract).filter(
                Contract.status == "active",
                Contract.end_date.isnot(None),
                Contract.end_date >= today,
                Contract.end_date <= window_end,
            )

            if rule.customer_id is not None:
                contract_q = contract_q.filter(Contract.customer_id == rule.customer_id)

            contracts = contract_q.all()

            for contract in contracts:
                days_left = (contract.end_date - today).days
                month_str = contract.end_date.strftime("%Y-%m")

                message = (
                    f"合同 {contract.contract_code}"
                    f" ({contract.title or '无标题'}) 还有 {days_left} 天到期"
                )

                event = AlertEvent(
                    alert_rule_id=rule.id,
                    alert_type="contract_expiring",
                    customer_id=contract.customer_id,
                    service="contract",
                    month=month_str,
                    actual_pct=None,
                    threshold_value=rule.threshold_value,
                    message=message,
                )
                try:
                    db.begin_nested()  # savepoint
                    db.add(event)
                    db.flush()
                    total_triggered += 1
                    logger.info(
                        "contract_expiring triggered: rule=%s customer=%s contract=%s days_left=%d",
                        rule.id, contract.customer_id, contract.contract_code, days_left,
                    )
                except IntegrityError:
                    db.rollback()  # 回滚到 savepoint
                    logger.debug(
                        "contract_expiring dedup skip: rule=%s customer=%s contract=%s month=%s",
                        rule.id, contract.customer_id, contract.contract_code, month_str,
                    )

        except Exception as exc:
            db.rollback()
            logger.exception("evaluate contract_expiring rule %s failed: %s", rule.id, exc)
            continue

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("evaluate_contract_expiring_rules commit failed: %s", exc)
        return 0

    logger.info(
        "evaluate_contract_expiring_rules done: rules=%d triggered=%d",
        len(rules), total_triggered,
    )
    return total_triggered
