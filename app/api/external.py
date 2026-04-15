"""External API for 超级运营中心 (super-ops) — read-only snapshot of xiaoshou data.

Auth: X-Api-Key header matching SUPER_OPS_API_KEY env var. Separate from
the /api/internal/* path (which 云管 uses) so the two channels can rotate
credentials independently.

All endpoints are GET + read-only. No writes. No cross-customer listing
of sensitive fields beyond what the SPA already exposes to auth'd users.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.allocation import Allocation
from app.models.allocation_history import AllocationHistory
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightFact, CustomerInsightRun
from app.models.resource import Resource
from app.models.sales import LeadAssignmentLog, LeadAssignmentRule, SalesUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/external", tags=["超级运营中心 (external)"])


def _auth(x_api_key: Optional[str] = Header(None, alias="X-Api-Key")) -> None:
    s = get_settings()
    valid = {s.SUPER_OPS_API_KEY, s.XIAOSHOU_INTERNAL_API_KEY}
    valid.discard("")
    valid.discard(None)
    if not x_api_key or x_api_key not in valid:
        raise HTTPException(401, "invalid X-Api-Key")


# ---------- customers ----------

@router.get("/customers", summary="客户快照 (分页)")
def list_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    industry: Optional[str] = None,
    region: Optional[str] = None,
    customer_status: Optional[str] = None,
    sales_user_id: Optional[int] = None,
    only_unassigned: bool = False,
    updated_since: Optional[str] = Query(None, description="ISO 8601; 仅返回 updated_at >= since"),
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if industry: q = q.filter(Customer.industry == industry)
    if region: q = q.filter(Customer.region == region)
    if customer_status: q = q.filter(Customer.customer_status == customer_status)
    if sales_user_id: q = q.filter(Customer.sales_user_id == sales_user_id)
    if only_unassigned: q = q.filter(Customer.sales_user_id.is_(None))
    if updated_since:
        try:
            dt = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "invalid updated_since")
        q = q.filter(Customer.updated_at >= dt)

    total = q.count()
    items = q.order_by(Customer.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "id": c.id, "customer_code": c.customer_code, "customer_name": c.customer_name,
            "industry": c.industry, "region": c.region, "customer_level": c.customer_level,
            "customer_status": c.customer_status,
            "sales_user_id": c.sales_user_id, "operation_user_id": c.operation_user_id,
            "current_resource_count": c.current_resource_count,
            "current_month_consumption": float(c.current_month_consumption or 0),
            "source_system": c.source_system, "source_id": c.source_id,
            "last_follow_time": c.last_follow_time.isoformat() if c.last_follow_time else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        } for c in items],
    }


@router.get("/customers/{customer_id}", summary="单客户详情")
def get_customer(
    customer_id: int,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    c = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not c:
        raise HTTPException(404, "客户不存在")
    return {
        "id": c.id, "customer_code": c.customer_code, "customer_name": c.customer_name,
        "industry": c.industry, "region": c.region,
        "customer_level": c.customer_level, "customer_status": c.customer_status,
        "sales_user_id": c.sales_user_id,
        "current_month_consumption": float(c.current_month_consumption or 0),
        "last_follow_time": c.last_follow_time.isoformat() if c.last_follow_time else None,
        "source_system": c.source_system, "source_id": c.source_id,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ---------- allocations ----------

@router.get("/allocations", summary="分配记录快照")
def list_allocations(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    include_cancelled: bool = False,
    customer_id: Optional[int] = None,
    updated_since: Optional[str] = None,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(Allocation).filter(Allocation.is_deleted == False)  # noqa: E712
    if not include_cancelled:
        q = q.filter(Allocation.allocation_status != "CANCELLED")
    if customer_id: q = q.filter(Allocation.customer_id == customer_id)
    if updated_since:
        try:
            dt = datetime.fromisoformat(updated_since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "invalid updated_since")
        q = q.filter(Allocation.updated_at >= dt)
    total = q.count()
    items = q.order_by(Allocation.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "id": a.id, "allocation_code": a.allocation_code,
            "customer_id": a.customer_id, "resource_id": a.resource_id,
            "allocated_quantity": a.allocated_quantity,
            "unit_cost": float(a.unit_cost) if a.unit_cost is not None else None,
            "unit_price": float(a.unit_price) if a.unit_price is not None else None,
            "total_cost": float(a.total_cost) if a.total_cost is not None else None,
            "total_price": float(a.total_price) if a.total_price is not None else None,
            "profit_amount": float(a.profit_amount) if a.profit_amount is not None else None,
            "allocation_status": a.allocation_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        } for a in items],
    }


@router.get("/allocations/{allocation_id}/history", summary="分配变更流水")
def get_allocation_history(
    allocation_id: int,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(AllocationHistory)
        .filter(AllocationHistory.allocation_id == allocation_id)
        .order_by(AllocationHistory.id.asc())
        .all()
    )
    return {"allocation_id": allocation_id, "items": [{
        "id": l.id, "field": l.field, "old_value": l.old_value,
        "new_value": l.new_value, "reason": l.reason,
        "at": l.at.isoformat() if l.at else None,
    } for l in logs]}


# ---------- resources ----------

@router.get("/resources", summary="货源快照")
def list_resources(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(Resource).filter(Resource.is_deleted == False)  # noqa: E712
    total = q.count()
    items = q.order_by(Resource.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total, "page": page, "page_size": page_size,
        "items": [{
            "id": r.id, "resource_code": r.resource_code,
            "resource_type": r.resource_type,
            "cloud_provider": getattr(r, "cloud_provider", None),
            "total_quantity": r.total_quantity,
            "allocated_quantity": r.allocated_quantity,
            "available_quantity": r.available_quantity,
            "unit_cost": float(r.unit_cost) if r.unit_cost is not None else None,
            "suggested_price": float(r.suggested_price) if r.suggested_price is not None else None,
            "resource_status": r.resource_status,
        } for r in items],
    }


# ---------- sales team ----------

@router.get("/sales/users", summary="销售成员")
def list_sales_users(
    active_only: bool = True,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(SalesUser)
    if active_only:
        q = q.filter(SalesUser.is_active == True)  # noqa: E712
    return {"items": [{
        "id": u.id, "name": u.name, "email": u.email, "phone": u.phone,
        "casdoor_user_id": u.casdoor_user_id,
        "regions": u.regions, "industries": u.industries,
        "is_active": u.is_active,
    } for u in q.order_by(SalesUser.id.asc()).all()]}


@router.get("/sales/rules", summary="分配规则")
def list_rules(
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    return {"items": [{
        "id": r.id, "name": r.name,
        "industry": r.industry, "region": r.region, "customer_level": r.customer_level,
        "sales_user_id": r.sales_user_id, "sales_user_ids": r.sales_user_ids,
        "cursor": r.cursor, "priority": r.priority, "is_active": r.is_active,
    } for r in db.query(LeadAssignmentRule).order_by(LeadAssignmentRule.priority.asc()).all()]}


@router.get("/customers/{customer_id}/assignment-log", summary="客户分配历史")
def get_assignment_log(
    customer_id: int,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(LeadAssignmentLog)
        .filter(LeadAssignmentLog.customer_id == customer_id)
        .order_by(LeadAssignmentLog.id.asc())
        .all()
    )
    return {"customer_id": customer_id, "items": [{
        "id": l.id, "from_user_id": l.from_user_id, "to_user_id": l.to_user_id,
        "trigger": l.trigger, "rule_id": l.rule_id, "reason": l.reason,
        "at": l.at.isoformat() if l.at else None,
    } for l in logs]}


# ---------- insight facts ----------

@router.get("/customers/{customer_id}/insight/facts", summary="客户 AI 洞察事实库")
def list_insight_facts(
    customer_id: int,
    category: Optional[str] = None,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(CustomerInsightFact).filter(CustomerInsightFact.customer_id == customer_id)
    if category:
        q = q.filter(CustomerInsightFact.category == category)
    return {"customer_id": customer_id, "items": [{
        "id": f.id, "category": f.category, "content": f.content,
        "source_url": f.source_url, "fingerprint": f.fingerprint,
        "run_id": f.run_id,
        "discovered_at": f.discovered_at.isoformat() if f.discovered_at else None,
    } for f in q.order_by(CustomerInsightFact.id.asc()).all()]}


@router.get("/customers/{customer_id}/insight/runs", summary="客户 AI 洞察运行列表")
def list_insight_runs(
    customer_id: int,
    _a: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    return {"customer_id": customer_id, "items": [{
        "id": r.id, "status": r.status,
        "steps_total": r.steps_total, "steps_done": r.steps_done,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "summary": r.summary,
    } for r in db.query(CustomerInsightRun).filter(
        CustomerInsightRun.customer_id == customer_id
    ).order_by(CustomerInsightRun.id.desc()).all()]}


# ---------- meta ----------

@router.get("/meta/ping", summary="活性检查 (免鉴权的 /api/external 入口嗅探)")
def ping():
    return {"ok": True, "service": "xiaoshou-external", "ts": datetime.now().isoformat()}
