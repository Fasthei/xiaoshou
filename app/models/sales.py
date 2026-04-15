"""Sales team + lead assignment rules + assignment history."""
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Text, ForeignKey, Integer,
    Boolean, JSON, Index,
)
from sqlalchemy.sql import func
from app.database import Base

# Same trick as customer_insight.py — BigInteger autoincrement doesn't
# work under SQLite (in-memory test DB) but does under Postgres. Using
# with_variant keeps prod on BIGINT while tests get INTEGER PRIMARY KEY.
_PK = BigInteger().with_variant(Integer(), "sqlite")


class SalesUser(Base):
    """本地销售人员档案，用于商机分配。与 Casdoor 用户松耦合（casdoor_user_id 可空）。"""
    __tablename__ = "sales_user"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), nullable=True)
    phone = Column(String(50), nullable=True)
    casdoor_user_id = Column(String(100), nullable=True, comment="Casdoor 用户ID, 可空")
    regions = Column(JSON, nullable=True, comment="负责区域 JSON 数组, 例: ['华东','华北']")
    industries = Column(JSON, nullable=True, comment="擅长行业 JSON 数组")
    is_active = Column(Boolean, default=True, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class LeadAssignmentRule(Base):
    """分配规则。匹配 (industry, region, customer_level) 任意组合，priority 低的先命中。"""
    __tablename__ = "lead_assignment_rule"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="规则名, 便于管理")
    industry = Column(String(50), nullable=True, comment="匹配行业, 空=不限")
    region = Column(String(50), nullable=True, comment="匹配地区, 空=不限")
    customer_level = Column(String(20), nullable=True, comment="匹配客户级别, 空=不限")
    sales_user_id = Column(BigInteger, ForeignKey("sales_user.id"), nullable=False)
    priority = Column(Integer, default=100, nullable=False, comment="小优先, 默认100")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_rule_match", "industry", "region", "customer_level", "is_active", "priority"),
    )


class LeadAssignmentLog(Base):
    """每次分配 / 再分配的审计流水。"""
    __tablename__ = "lead_assignment_log"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    from_user_id = Column(BigInteger, ForeignKey("sales_user.id"), nullable=True)
    to_user_id = Column(BigInteger, ForeignKey("sales_user.id"), nullable=True)
    reason = Column(Text, nullable=True)
    trigger = Column(String(20), nullable=False, default="manual",
                     comment="manual | auto | import")
    rule_id = Column(BigInteger, ForeignKey("lead_assignment_rule.id"), nullable=True,
                     comment="若 trigger=auto, 对应命中的规则")
    at = Column(DateTime, server_default=func.now(), nullable=False)
    operator_casdoor_id = Column(String(100), nullable=True, comment="触发者的 Casdoor 用户ID")
