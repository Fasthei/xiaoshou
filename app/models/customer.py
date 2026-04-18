from sqlalchemy import Column, BigInteger, String, Integer, Numeric, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

# BigInteger PK isn't auto-increment under SQLite — compile to INTEGER in that
# dialect so in-memory tests can insert without supplying id. No Postgres impact.
_PK = BigInteger().with_variant(Integer(), "sqlite")


class Customer(Base):
    """客户表"""
    __tablename__ = "customer"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_code = Column(String(50), unique=True, nullable=True, comment="客户编号 (手工建可空, gongdan 同步后回填)")
    customer_name = Column(String(200), nullable=False, comment="客户名称")
    customer_short_name = Column(String(100), comment="客户简称")
    industry = Column(String(50), comment="所属行业")
    region = Column(String(50), comment="所属地区")
    customer_level = Column(String(20), comment="客户级别")
    customer_status = Column(String(32), nullable=False, comment="客户状态 (向后兼容, 未来由 lifecycle_stage 取代)")
    sales_user_id = Column(BigInteger, comment="所属销售")
    operation_user_id = Column(BigInteger, comment="所属运营")
    first_deal_time = Column(DateTime, comment="首次成交时间")
    last_follow_time = Column(DateTime, comment="最近跟进时间")
    current_resource_count = Column(Integer, default=0, comment="当前在用资源数")
    current_month_consumption = Column(Numeric(15, 2), default=0, comment="当前月消耗")
    next_month_forecast = Column(Numeric(15, 2), comment="预计下月消耗")
    source_system = Column(String(50), comment="来源系统")
    source_id = Column(String(100), comment="来源系统ID")
    source_label = Column(String(50), comment="来源描述 (用户手填, 如 朋友推荐/展会)")
    # --- 生命周期 stage (PR-8 客户生命周期重构) ---
    # 3 个 stage: lead / contacting / active
    # 旧 customer_status 字段保留但弃用，新代码只读 lifecycle_stage
    lifecycle_stage = Column(String(20), nullable=False, default='lead',
                             server_default='lead',
                             comment='生命周期 stage: lead/contacting/active')
    recycled_from_stage = Column(String(20), nullable=True,
                                 comment='上次从哪个 stage 回流到 lead')
    recycle_reason = Column(Text, nullable=True, comment='回流原因')
    recycled_at = Column(DateTime, nullable=True, comment='回流时间')
    # --- 扩展档案字段 (PR-7 客户档案四件套 / 字段扩展) ---
    employee_size = Column(Integer, comment="员工规模")
    annual_revenue = Column(Numeric(18, 2), comment="年营收 (RMB)")
    last_meeting_at = Column(DateTime, comment="最近面谈时间")
    trade_count = Column(Integer, default=0, comment="累计交易次数")
    website = Column(String(500), comment="公司官网")
    linkedin_url = Column(String(500), comment="LinkedIn 公司主页")
    note = Column(Text, comment="业务备注 / 标签")
    # --- 客户来源 & 类型 (转介绍 / 渠道商) ---
    customer_type = Column(String(20), default="direct", server_default="direct", comment="客户类型 direct(直客) / channel(渠道)")
    referrer = Column(String(200), comment="转介绍来源文本（老客户/合作伙伴推荐）")
    channel_notes = Column(Text, comment="渠道客户专属: 渠道方透露的终端用户说明")
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

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
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
