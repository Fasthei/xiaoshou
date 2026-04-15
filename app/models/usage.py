from sqlalchemy import Column, BigInteger, String, Numeric, DateTime
from sqlalchemy.sql import func
from app.database import Base


class UsageRecord(Base):
    """用量记录表"""
    __tablename__ = "usage_record"

    id = Column(BigInteger, primary_key=True, index=True)
    customer_id = Column(BigInteger, nullable=False, index=True, comment="客户ID")
    resource_id = Column(BigInteger, nullable=False, index=True, comment="货源ID")
    allocation_id = Column(BigInteger, index=True, comment="分配ID")
    usage_date = Column(DateTime, nullable=False, index=True, comment="使用日期")
    usage_amount = Column(Numeric(15, 4), comment="使用量")
    usage_cost = Column(Numeric(15, 2), comment="使用成本")
    source_system = Column(String(50), comment="来源系统")
    created_at = Column(DateTime, server_default=func.now())
