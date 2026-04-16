"""Contract model for customer contracts."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Date, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

# BigInteger PK isn't auto-increment under SQLite — compile to INTEGER in that
# dialect so in-memory tests can insert without supplying id.
_PK = BigInteger().with_variant(Integer(), "sqlite")


class Contract(Base):
    """客户合同表"""
    __tablename__ = "contract"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    contract_code = Column(String(80), unique=True, nullable=False, comment="合同编号")
    title = Column(String(200), comment="合同标题")
    amount = Column(Numeric(15, 2), comment="合同金额")
    start_date = Column(Date, comment="开始日期")
    end_date = Column(Date, comment="结束日期")
    status = Column(String(20), default="active", comment="状态: active/expired/terminated")
    notes = Column(Text, comment="备注")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_contract_customer", "customer_id"),
    )
