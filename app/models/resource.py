from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Boolean, DateTime, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class Resource(Base):
    """货源表"""
    __tablename__ = "resource"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    resource_code = Column(String(100), unique=True, nullable=False, comment="货源编号")
    resource_type = Column(String(20), nullable=False, comment="货源类型：ORIGINAL/OTHER")
    cloud_provider = Column(String(20), comment="云厂商：AWS/AZURE/GCP")
    identifier_field = Column(String(200), comment="标识字段")
    account_name = Column(String(200), comment="账号名称")
    definition_name = Column(String(200), comment="定义名称")
    cloud_account_id = Column(String(100), comment="云账号ID")
    total_quantity = Column(Integer, comment="总数量")
    allocated_quantity = Column(Integer, default=0, comment="已分配数量")
    available_quantity = Column(Integer, comment="可分配数量")
    unit_cost = Column(Numeric(15, 4), comment="单位成本")
    suggested_price = Column(Numeric(15, 4), comment="建议销售价")
    resource_status = Column(String(20), nullable=False, comment="状态")
    source_system = Column(String(50), comment="来源系统")
    source_id = Column(String(100), comment="来源系统ID")
    last_sync_time = Column(DateTime, comment="最近同步时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    # 关系
    allocations = relationship("Allocation", back_populates="resource")
