"""CustomerStageRequest — 客户 stage 变更申请审批流水 + 审计."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class CustomerStageRequest(Base):
    """客户 stage 变更申请 (sales 发起, 主管审批) + 自动升级审计 (decided_by='system')."""
    __tablename__ = "customer_stage_request"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    from_stage = Column(String(20), nullable=False, comment="原 stage")
    to_stage = Column(String(20), nullable=False, comment="目标 stage")
    reason = Column(Text, nullable=True, comment="申请理由")
    status = Column(String(20), default="pending", nullable=False,
                    comment="pending | approved | rejected")
    requested_by = Column(String(200), nullable=True, comment="sub 或 name")
    decided_by = Column(String(200), nullable=True, comment="sub/name, 或 'system' 表示自动")
    decision_comment = Column(Text, nullable=True, comment="审批意见")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    decided_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_stage_request_customer", "customer_id"),
        Index("ix_stage_request_status", "status"),
    )
