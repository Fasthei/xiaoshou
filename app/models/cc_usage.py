"""cc_usage — 本地镜像的云管每日用量 (by customer_code + date)."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Date, DateTime,
    UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")
_JSON = JSONB().with_variant(JSON(), "sqlite")


class CCUsage(Base):
    """每个客户 × 每日 一条, upsert by (customer_code, date)."""
    __tablename__ = "cc_usage"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_code = Column(String(80), nullable=False, index=True, comment="xiaoshou.customer_code")
    date = Column(Date, nullable=False, comment="用量日期")
    total_cost = Column(Numeric(15, 2), default=0, comment="当日总成本 ¥")
    total_usage = Column(Numeric(20, 4), default=0, comment="当日总用量")
    record_count = Column(Integer, default=0, comment="底层云管行数")
    raw = Column(_JSON, comment="raw cloudcost 聚合数据 (按 service 拆分等)")
    sync_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("customer_code", "date", name="uq_cc_usage_customer_date"),
        Index("ix_cc_usage_customer", "customer_code"),
    )
