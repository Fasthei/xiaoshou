"""bill_adjustment — 账单中心每月对 (客户 × 货源) 的折扣 / 手续费覆盖。

默认情况下账单中心按"最新 approved allocation.discount_rate"算折扣。
销售在账单中心"编辑"一行可写入 bill_adjustment，覆盖该月的折扣率并/或加手续费。
"""
from sqlalchemy import (
    Column, BigInteger, Integer, Numeric, String, DateTime,
    UniqueConstraint, Index,
)
from sqlalchemy.sql import func

from app.database import Base


# BigInteger autoincrement 在 SQLite 下不工作（测试 in-memory DB）；
# with_variant 让本地测试用 INTEGER PK，生产 Postgres 仍是 BIGINT。
_PK = BigInteger().with_variant(Integer(), "sqlite")


class BillAdjustment(Base):
    __tablename__ = "bill_adjustment"

    id = Column(_PK, primary_key=True, autoincrement=True)
    customer_id = Column(BigInteger, nullable=False, comment="customer.id")
    resource_id = Column(BigInteger, nullable=False, comment="resource.id")
    month = Column(String(7), nullable=False, comment="YYYY-MM")
    discount_rate_override = Column(
        Numeric(5, 2), nullable=True,
        comment="覆盖折扣率 %（0-100, 可负表示加价）；NULL=沿用订单",
    )
    surcharge = Column(
        Numeric(15, 2), nullable=True,
        comment="附加手续费（可正可负）",
    )
    notes = Column(String(500), nullable=True, comment="备注")
    updated_by = Column(String(200), nullable=True, comment="user.sub:name")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "customer_id", "resource_id", "month",
            name="uq_bill_adj_cust_res_month",
        ),
        Index("ix_bill_adj_customer_month", "customer_id", "month"),
    )
