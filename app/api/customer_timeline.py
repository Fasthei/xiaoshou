"""GET /api/customers/{id}/timeline — chronological events for a customer.

Sources: local allocation history + sync logs that touched customers + enrich
operations (synthesised).
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.sync_log import SyncLog

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


class TimelineEvent(BaseModel):
    at: str
    kind: str          # created | updated | allocation | sync
    title: str
    detail: str = ""
    color: str = "blue"


@router.get("/{customer_id}/timeline", response_model=List[TimelineEvent],
            summary="客户相关事件时间线")
def customer_timeline(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    c = db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()  # noqa: E712
    if not c:
        raise HTTPException(404, "客户不存在")

    events: List[TimelineEvent] = []

    if c.created_at:
        events.append(TimelineEvent(
            at=c.created_at.isoformat(), kind="created",
            title=f"客户建档：{c.customer_code}",
            detail=f"来源 {c.source_system or '手工'}",
            color="green",
        ))
    if c.updated_at and c.updated_at != c.created_at:
        events.append(TimelineEvent(
            at=c.updated_at.isoformat(), kind="updated",
            title="客户资料更新",
            detail=f"状态 {c.customer_status} · 行业 {c.industry or '-'}",
            color="blue",
        ))

    allocs = db.query(Allocation).filter(
        Allocation.customer_id == c.id, Allocation.is_deleted == False,  # noqa: E712
    ).order_by(Allocation.created_at.desc()).limit(50).all()
    for a in allocs:
        events.append(TimelineEvent(
            at=(a.created_at or datetime.utcnow()).isoformat(),
            kind="allocation",
            title=f"新增分配 {a.allocation_code}",
            detail=f"数量 {a.allocated_quantity} · 毛利 ¥{a.profit_amount or 0} · 状态 {a.allocation_status}",
            color="purple",
        ))

    # System-level sync logs touching "customers"
    syncs = db.query(SyncLog).filter(SyncLog.sync_type == "customers") \
        .order_by(SyncLog.id.desc()).limit(5).all()
    for s in syncs:
        events.append(TimelineEvent(
            at=(s.started_at or datetime.utcnow()).isoformat(),
            kind="sync",
            title=f"从 {s.source_system} 同步客户",
            detail=f"拉取 {s.pulled_count} · 新增 {s.created_count} · 状态 {s.status}",
            color="cyan",
        ))

    events.sort(key=lambda e: e.at, reverse=True)
    return events
