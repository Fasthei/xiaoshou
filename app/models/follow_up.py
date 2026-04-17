"""CustomerFollowUp — 销售手动记录的每次跟进事件。

与 customer_insight_run (AI 抓事实) 互补:
  insight_fact 是 agent 自动从网络抓的公开信息;
  follow_up 是销售面访/电话/邮件后手动记的互动日志。
"""
from sqlalchemy import (
    Column, BigInteger, String, DateTime, Text, ForeignKey, Integer, Index,
)
from sqlalchemy.sql import func
from app.database import Base

_PK = BigInteger().with_variant(Integer(), "sqlite")


class CustomerFollowUp(Base):
    __tablename__ = "customer_follow_up"

    id = Column(_PK, primary_key=True, index=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("customer.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False, default="note",
                  comment="call | meeting | email | wechat | note | other")
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    outcome = Column(String(30), nullable=True,
                     comment="positive | neutral | negative | needs_followup")
    next_action_at = Column(DateTime, nullable=True, comment="下一步动作时间")
    operator_casdoor_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    # 定向留言 / 回复线程
    to_sales_user_id = Column(BigInteger, nullable=True, index=True,
                              comment="定向留言的目标销售 sales_user.id（null=普通跟进）")
    parent_follow_up_id = Column(BigInteger, ForeignKey("customer_follow_up.id"),
                                 nullable=True,
                                 comment="回复时指向上一条 comment 的 id")

    __table_args__ = (
        Index("ix_follow_up_customer_created", "customer_id", "created_at"),
    )
