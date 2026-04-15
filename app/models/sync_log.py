from sqlalchemy import BigInteger, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class SyncLog(Base):
    """Audit trail for data synced from upstream systems (gongdan, cloudcost)."""

    __tablename__ = "sync_log"

    id = Column(BigInteger, primary_key=True, index=True)
    source_system = Column(String(32), nullable=False, comment="gongdan / cloudcost")
    sync_type = Column(String(32), nullable=False, comment="customers / resources / ...")
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    pulled_count = Column(Integer, default=0)
    created_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    status = Column(String(16), default="running", comment="running/success/failed")
    last_error = Column(Text)
    triggered_by = Column(String(128), comment="user.sub or 'system'")
