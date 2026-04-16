"""cc_alert — 本地镜像的云管预警规则快照 (by rule_id + month)."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Boolean, DateTime,
    UniqueConstraint, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class CCAlert(Base):
    """云管预警快照, upsert by (rule_id, month).

    external_project_id 对应云管 service_account.external_project_id
    (= xiaoshou.customer.customer_code 的候选匹配键).
    """
    __tablename__ = "cc_alert"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    rule_id = Column(Integer, comment="云管预警规则 ID")
    rule_name = Column(String(200), comment="规则名")
    threshold_type = Column(String(40), comment="amount / percent / ...")
    threshold_value = Column(Numeric(15, 2))
    actual = Column(Numeric(15, 2), comment="实际值")
    pct = Column(Numeric(8, 2), comment="达标比例 %")
    triggered = Column(Boolean, default=False, comment="是否触发")
    account_name = Column(String(200))
    provider = Column(String(40))
    external_project_id = Column(String(200), index=True, comment="= customer_code 候选")
    month = Column(String(7), comment="YYYY-MM")
    sync_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("rule_id", "month", name="uq_cc_alert_rule_month"),
        Index("ix_cc_alert_external", "external_project_id"),
    )
