"""AlertRule — 用户自定义预警规则 (费用上限/下限/收款超期等)."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Boolean, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class AlertRule(Base):
    """客户/全局维度的自定义预警规则。"""
    __tablename__ = "alert_rule"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    # 空 customer_id 表示全局规则
    customer_id = Column(BigInteger, ForeignKey("customer.id", ondelete="CASCADE"),
                         nullable=True, index=True)
    rule_name = Column(String(200), nullable=False, comment="规则名称")
    rule_type = Column(String(40), nullable=False,
                       comment="cost_upper | cost_lower | payment_overdue")
    threshold_value = Column(Numeric(15, 2), nullable=True, comment="阈值")
    threshold_unit = Column(String(20), default="CNY", comment="阈值单位")
    enabled = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(BigInteger, ForeignKey("sales_user.id", ondelete="SET NULL"),
                        nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_alert_rule_customer", "customer_id"),
    )
