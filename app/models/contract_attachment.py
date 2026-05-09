"""Contract attachment model — one contract can have many file attachments."""
from sqlalchemy import (
    Column, BigInteger, Integer, String, DateTime, ForeignKey, Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class ContractAttachment(Base):
    """合同附件表 — 一个合同记录可挂多份文件 (PDF/Word/图片)。"""
    __tablename__ = "contract_attachment"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    contract_id = Column(
        BigInteger,
        ForeignKey("contract.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_url = Column(String(500), nullable=False, comment="Blob URL")
    file_name = Column(String(200), comment="原始文件名")
    file_size = Column(Integer, comment="文件大小(字节)")
    mime_type = Column(String(80), comment="MIME 类型")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    contract = relationship("Contract", back_populates="attachments")

    __table_args__ = (
        Index("ix_contract_attachment_contract", "contract_id"),
    )
