"""Allocation change-log — one row per field-level change on an allocation.

Emitted from the allocation API endpoints whenever quantity/price/status/etc.
are mutated. Used by the frontend to render a variant trail per allocation,
and by the 'cancelled' tab to show soft-deleted allocations with metadata.
"""
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Text, ForeignKey, Integer,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class AllocationHistory(Base):
    __tablename__ = "allocation_history"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    allocation_id = Column(BigInteger, ForeignKey("allocation.id"), nullable=False, index=True)
    field = Column(String(50), nullable=False, comment="改了哪个字段: quantity|unit_price|status|cancel|...")
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    at = Column(DateTime, server_default=func.now(), nullable=False)
    operator_casdoor_id = Column(String(100), nullable=True)
