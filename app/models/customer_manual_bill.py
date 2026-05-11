"""customer_manual_bill — 销售/运营手工录入的过往账单 (区别于云管同步的 cc_bill)."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Date, DateTime, Text, ForeignKey, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class CustomerManualBill(Base):
    """客户手工录入的过往账单 (附件可选, 单文件)。"""
    __tablename__ = "customer_manual_bill"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(
        BigInteger,
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), comment="标题")
    amount = Column(Numeric(15, 2), comment="金额")
    bill_date = Column(Date, comment="账单时间")
    notes = Column(Text, comment="备注")
    # 单附件 (PDF/Word/图片)
    file_url = Column(String(500), comment="Blob URL")
    file_name = Column(String(200), comment="原始文件名")
    file_size = Column(Integer, comment="文件大小(字节)")
    mime_type = Column(String(80), comment="MIME 类型")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_customer_manual_bill_customer", "customer_id"),
    )
