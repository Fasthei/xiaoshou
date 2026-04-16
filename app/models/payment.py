"""Payment — 客户收款计划与实收记录."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Numeric, Date, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class Payment(Base):
    """收款记录: 计划收款 + 实际收款 + 超期追踪."""
    __tablename__ = "payment"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    contract_id = Column(BigInteger, ForeignKey("contract.id", ondelete="SET NULL"),
                         nullable=True, index=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False, comment="金额")
    expected_date = Column(Date, nullable=False, comment="预期收款日期")
    received_date = Column(Date, nullable=True, comment="实际收款日期")
    status = Column(String(20), default="pending", nullable=False,
                    comment="pending | received | overdue | cancelled")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_payment_customer", "customer_id"),
        Index("ix_payment_status", "status"),
        Index("ix_payment_expected", "expected_date"),
    )
