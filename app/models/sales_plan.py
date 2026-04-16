"""Sales plan — 销售工作计划 (日/周/月)."""
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Date, Text, ForeignKey, Integer, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class SalesPlan(Base):
    """销售工作计划: 日/周/月计划，与销售成员一对多。"""
    __tablename__ = "sales_plan"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("sales_user.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    plan_date = Column(Date, nullable=False, index=True,
                       comment="计划基准日期 (日计划=当日; 周计划=周一; 月计划=当月1日)")
    plan_type = Column(String(10), nullable=False,
                       comment="daily | weekly | monthly")
    title = Column(String(200), nullable=True)
    content = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, default="pending",
                    comment="pending | in_progress | done | cancelled")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_sales_plan_user_date", "user_id", "plan_date"),
    )
