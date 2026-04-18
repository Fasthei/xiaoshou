"""alert_event — 本地触发的预警事件记录 (usage_surge 等)."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, DateTime, Text,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class AlertEvent(Base):
    """本地计算产生的预警事件, 一行=一次触发记录.

    区别于 cc_alert (云管镜像预警), 这里存的是 xiaoshou 自己计算的预警.
    去重键: (alert_rule_id, customer_id, service, month)
    """
    __tablename__ = "alert_event"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    alert_rule_id = Column(
        BigInteger, ForeignKey("alert_rule.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    alert_type = Column(String(40), nullable=False, comment="usage_surge | ...")
    customer_id = Column(
        BigInteger, ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="触发客户; NULL=全局规则触发但无特定客户",
    )
    service = Column(String(200), nullable=True, comment="触发的 service 名称")
    month = Column(String(7), nullable=False, comment="YYYY-MM 触发月份")
    actual_pct = Column(Numeric(10, 2), nullable=True, comment="实际环比增幅 %")
    threshold_value = Column(Numeric(15, 2), nullable=True, comment="规则阈值快照")
    message = Column(Text, nullable=True, comment="告警描述")
    triggered_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "alert_rule_id", "customer_id", "service", "month",
            name="uq_alert_event_dedup",
        ),
        Index("ix_alert_event_type_month", "alert_type", "month"),
    )
