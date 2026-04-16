"""cc_bill — 本地镜像的云管月度账单."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, DateTime, Text, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")
_JSON = JSONB().with_variant(JSON(), "sqlite")


class CCBill(Base):
    """云管月度账单, upsert by remote_id (unique).

    customer_code: 从云管 bill.external_project_id / account 的
    external_project_id 推断 (可能为空).
    """
    __tablename__ = "cc_bill"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    remote_id = Column(Integer, unique=True, index=True, comment="云管原始 bill.id")
    month = Column(String(7), nullable=False, comment="YYYY-MM")
    provider = Column(String(40))
    original_cost = Column(Numeric(15, 2), comment="原始成本")
    markup_rate = Column(Numeric(10, 4), comment="加价率")
    final_cost = Column(Numeric(15, 2), comment="加价后成本")
    adjustment = Column(Numeric(15, 2), comment="调整金额")
    status = Column(String(20), comment="draft / confirmed / paid ...")
    notes = Column(Text)
    customer_code = Column(String(80), index=True, comment="从 external_project_id 推断")
    sync_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    raw = Column(_JSON, comment="原始云管 bill 对象")

    __table_args__ = (
        Index("ix_cc_bill_month", "month"),
        Index("ix_cc_bill_customer", "customer_code"),
    )
