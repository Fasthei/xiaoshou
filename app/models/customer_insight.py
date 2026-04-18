"""Customer Insight Agent — runs and discovered facts."""
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Text, ForeignKey, Integer,
    UniqueConstraint, Index, Numeric,
)

# BigInteger on SQLite doesn't autoincrement; compile to INTEGER PRIMARY KEY
# under SQLite so the in-memory test DB works, while staying BIGINT on Postgres.
_PK = BigInteger().with_variant(Integer(), "sqlite")
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class CustomerInsightRun(Base):
    """One execution of the customer-insight agent against a customer."""
    __tablename__ = "customer_insight_run"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running",
                    comment="running | completed | failed")
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    steps_total = Column(Integer, nullable=False, default=12)
    steps_done = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    summary = Column(Text, nullable=True, comment="Final markdown summary by the agent")
    token_usage_json = Column(Text, nullable=True, comment="JSON: {prompt, completion, total}")
    triggered_by = Column(BigInteger, nullable=True, comment="user id that clicked the button")
    cost_usd = Column(Numeric(10, 6), nullable=True, comment="Estimated OpenAI cost for this run (USD)")
    input_hash = Column(String(64), nullable=True, comment="sha256 of serialised input; used for 24h cache dedup")

    facts = relationship("CustomerInsightFact", back_populates="run",
                         cascade="all, delete-orphan")


class CustomerInsightFact(Base):
    """One atomic fact discovered by the agent about a customer.

    Deduped per-customer by fingerprint = sha1(category::normalized_content).
    A single fact is attributed to the run that first discovered it;
    subsequent runs that find the same fact are skipped (no-op).
    """
    __tablename__ = "customer_insight_fact"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    run_id = Column(BigInteger, ForeignKey("customer_insight_run.id"), nullable=False)
    category = Column(String(20), nullable=False,
                      comment="basic | people | tech | news | event | other")
    content = Column(Text, nullable=False)
    source_url = Column(String(1000), nullable=True)
    fingerprint = Column(String(40), nullable=False, comment="sha1 hex")
    discovered_at = Column(DateTime, server_default=func.now(), nullable=False)

    run = relationship("CustomerInsightRun", back_populates="facts")

    __table_args__ = (
        UniqueConstraint("customer_id", "fingerprint", name="uq_fact_customer_fingerprint"),
        Index("ix_fact_customer_category", "customer_id", "category"),
    )
