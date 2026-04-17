"""customer_resource — 客户 ↔ 货源 关联表 (手工勾选).

正式客户 (customer_status=formal) 通过此表关联多个本地 resource. 用于:
- 客户详情「关联货源」Tab 勾选/删除
- 客户用量/费用按货源聚合 (cc_usage × resource)
"""
from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class CustomerResource(Base):
    __tablename__ = "customer_resource"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    resource_id = Column(BigInteger, ForeignKey("resource.id"), nullable=False, index=True)
    note = Column(String(200), comment="备注, 例如此货源的用途 (legacy)")
    end_user_label = Column(String(200), comment="渠道客户终端用户备忘（可选）")
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(String(200), comment="Casdoor sub 或 sales_user.id")

    __table_args__ = (
        UniqueConstraint("customer_id", "resource_id", name="uq_customer_resource"),
        Index("ix_customer_resource_customer", "customer_id"),
        Index("ix_customer_resource_resource", "resource_id"),
    )
