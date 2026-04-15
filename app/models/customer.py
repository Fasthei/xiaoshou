from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Customer(Base):
    """客户表"""
    __tablename__ = "customer"

    id = Column(BigInteger, primary_key=True, index=True)
    customer_code = Column(String(50), unique=True, nullable=False, comment="客户编号")
    customer_name = Column(String(200), nullable=False, comment="客户名称")
    customer_short_name = Column(String(100), comment="客户简称")
    industry = Column(String(50), comment="所属行业")
    region = Column(String(50), comment="所属地区")
    customer_level = Column(String(20), comment="客户级别")
    customer_status = Column(String(20), nullable=False, comment="客户状态")
    sales_user_id = Column(BigInteger, comment="所属销售")
    operation_user_id = Column(BigInteger, comment="所属运营")
    first_deal_time = Column(DateTime, comment="首次成交时间")
    last_follow_time = Column(DateTime, comment="最近跟进时间")
    current_resource_count = Column(Integer, default=0, comment="当前在用资源数")
    current_month_consumption = Column(Numeric(15, 2), default=0, comment="当前月消耗")
    next_month_forecast = Column(Numeric(15, 2), comment="预计下月消耗")
    source_system = Column(String(50), comment="来源系统")
    source_id = Column(String(100), comment="来源系统ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_by = Column(BigInteger)
    updated_by = Column(BigInteger)
    is_deleted = Column(Boolean, default=False)

    # 关系
    contacts = relationship("CustomerContact", back_populates="customer")
    allocations = relationship("Allocation", back_populates="customer")


class CustomerContact(Base):
    """客户联系人表"""
    __tablename__ = "customer_contact"

    id = Column(BigInteger, primary_key=True, index=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False)
    contact_name = Column(String(100), nullable=False, comment="联系人姓名")
    contact_title = Column(String(50), comment="职位")
    contact_phone = Column(String(20), comment="电话")
    contact_email = Column(String(100), comment="邮箱")
    contact_wechat = Column(String(50), comment="微信")
    is_primary = Column(Boolean, default=False, comment="是否主联系人")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, default=False)

    # 关系
    customer = relationship("Customer", back_populates="contacts")
