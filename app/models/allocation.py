from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class Allocation(Base):
    """分配表"""
    __tablename__ = "allocation"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    allocation_code = Column(String(50), unique=True, nullable=False, comment="分配编号")
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False)
    resource_id = Column(BigInteger, ForeignKey("resource.id"), nullable=False)
    allocated_quantity = Column(Integer, nullable=False, comment="分配数量")
    unit_cost = Column(Numeric(15, 4), comment="单位成本")
    unit_price = Column(Numeric(15, 4), comment="单位售价")
    total_cost = Column(Numeric(15, 2), comment="总成本")
    total_price = Column(Numeric(15, 2), comment="总售价")
    profit_amount = Column(Numeric(15, 2), comment="毛利金额")
    profit_rate = Column(Numeric(5, 2), comment="毛利率")
    discount_rate = Column(Numeric(5, 2), nullable=True, comment="折扣率 % (可负表示加价)")
    unit_price_after_discount = Column(Numeric(15, 2), nullable=True, comment="折后单价")
    allocation_status = Column(String(20), nullable=False, comment="分配状态")
    allocated_by = Column(BigInteger, comment="分配人")
    allocated_at = Column(DateTime, comment="分配时间")
    delivery_status = Column(String(20), comment="交付状态")
    delivery_at = Column(DateTime, comment="交付时间")
    remark = Column(Text, comment="备注")
    # 审批工作流（additive, nullable）
    approval_status = Column(String(20), default="pending", comment="审批状态: pending/approved/rejected")
    approver_id = Column(Integer, nullable=True, comment="审批人 sales_user.id（软外键）")
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    approval_note = Column(String(500), nullable=True, comment="审批备注")
    # 渠道客户订单专属: 该货源给渠道方哪个终端用户的备忘
    end_user_label = Column(String(200), nullable=True, comment="渠道订单下终端用户标签")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    # 关系
    customer = relationship("Customer", back_populates="allocations")
    resource = relationship("Resource", back_populates="allocations")
