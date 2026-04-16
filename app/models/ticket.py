"""Ticket local mirror of gongdan tickets.

We mirror a minimal subset for the customer-detail drawer (ticket number, title,
status, timestamps) plus the full raw payload so we can extract more fields later
without another round-trip.
"""
from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, String
from sqlalchemy.sql import func

from app.database import Base

# BigInteger PK isn't auto-increment under SQLite — compile to INTEGER in that
# dialect so in-memory tests can insert without supplying id. No Postgres impact.
_PK = BigInteger().with_variant(Integer(), "sqlite")


class Ticket(Base):
    """Local mirror of a gongdan ticket.

    Uniqueness:
        ``ticket_code`` (= gongdan ticketNumber, e.g. "TK-2026-296691") is unique.

    Per-customer lookup:
        ``customer_code`` is indexed so the drawer can ``WHERE customer_code = ?``.
    """

    __tablename__ = "ticket"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    # gongdan ticketNumber — stable, human-readable, unique
    ticket_code = Column(String(100), unique=True, nullable=False, comment="工单编号 (gongdan ticketNumber)")
    # gongdan internal UUID — kept separately for traceability / deep-linking
    remote_id = Column(String(64), index=True, comment="gongdan 内部 UUID")
    customer_code = Column(String(80), index=True, comment="客户编号 (CUST-xxx)")
    title = Column(String(500), comment="工单标题 (description 前若干字)")
    status = Column(String(40), comment="OPEN / IN_PROGRESS / CLOSED / ...")
    created_at_remote = Column(DateTime, comment="gongdan createdAt")
    updated_at_remote = Column(DateTime, comment="gongdan updatedAt")
    sync_at = Column(DateTime, server_default=func.now(), comment="最近一次同步时间")
    raw = Column(JSON, comment="原始 gongdan ticket 结构 (便于后续扩字段)")


Index("ix_ticket_customer_code", Ticket.customer_code)
