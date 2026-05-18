"""客户生命周期 stage 变更 / 审批 / 回流 API.

stage 列表:
    lead -> contacting -> active
    任意 stage -> lost (瞬态, 审批通过立即回 lead)

自动升 (不走审批, 直接改 customer.lifecycle_stage, 同时在 customer_stage_request
插一行 status='approved' decided_by='system' 做审计) 由各业务端点埋点调用
`auto_advance_stage()`。

人工变更 (sales 申请 -> 主管批) 走本文件下半部分的 request/approve/reject 流程。
回流 (recycle) 到 lead 也要主管批。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth, require_roles
from app.database import get_db
from app.models.customer import Customer
from app.models.customer_stage_request import CustomerStageRequest

logger = logging.getLogger(__name__)

STAGES = ("lead", "contacting", "active", "lost")
STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}


# ---------- schemas ----------

class StageRequestBody(BaseModel):
    to_stage: str = Field(..., description="目标 stage")
    reason: Optional[str] = Field(None, description="申请理由")


class RecycleBody(BaseModel):
    reason: str = Field(..., description="回流原因 (必填)")


class StageRejectBody(BaseModel):
    comment: Optional[str] = None


class StageRequestOut(BaseModel):
    id: int
    customer_id: int
    customer_name: Optional[str] = None  # joined from customer.customer_name (含已 soft-delete)
    from_stage: str
    to_stage: str
    reason: Optional[str]
    status: str
    requested_by: Optional[str]
    requester_name: Optional[str] = None  # alias of requested_by, 兼容前端字段
    decided_by: Optional[str]
    decision_comment: Optional[str]
    created_at: Optional[datetime]
    decided_at: Optional[datetime]

    class Config:
        from_attributes = True


def _to_out(req: "CustomerStageRequest", db: Session) -> dict:
    """Serialize a stage_request with joined customer_name + requester_name alias."""
    cust_name: Optional[str] = None
    if req.customer_id:
        c = db.query(Customer.customer_name).filter(Customer.id == req.customer_id).first()
        if c:
            cust_name = c[0]
    return {
        "id": req.id,
        "customer_id": req.customer_id,
        "customer_name": cust_name,
        "from_stage": req.from_stage,
        "to_stage": req.to_stage,
        "reason": req.reason,
        "status": req.status,
        "requested_by": req.requested_by,
        "requester_name": req.requested_by,
        "decided_by": req.decided_by,
        "decision_comment": req.decision_comment,
        "created_at": req.created_at,
        "decided_at": req.decided_at,
    }


# ---------- helpers (also used by hooks) ----------

def auto_advance_stage(
    db: Session,
    customer: Customer,
    to_stage: str,
    reason: str,
    *,
    only_if_in: Optional[tuple[str, ...]] = None,
) -> bool:
    """Automatic stage advance (no approval).

    - Only advances if new stage is strictly later in STAGE_ORDER.
    - If ``only_if_in`` is set, current stage must be in that tuple.
    - Always writes a customer_stage_request audit row (status='approved',
      decided_by='system').

    Returns True if the stage was changed.
    """
    if to_stage not in STAGE_ORDER:
        return False
    current = customer.lifecycle_stage or "lead"
    if only_if_in is not None and current not in only_if_in:
        return False
    if STAGE_ORDER[to_stage] <= STAGE_ORDER.get(current, 0):
        return False

    now = datetime.utcnow()
    audit = CustomerStageRequest(
        customer_id=customer.id,
        from_stage=current,
        to_stage=to_stage,
        reason=reason,
        status="approved",
        requested_by="system",
        decided_by="system",
        decided_at=now,
    )
    customer.lifecycle_stage = to_stage
    db.add(customer)
    db.add(audit)
    return True


# ---------- routers ----------

# Customer-scoped: /api/customers/{id}/stage/...
customer_router = APIRouter(prefix="/api/customers", tags=["客户生命周期"])
# Top-level: /api/stage-requests/...
request_router = APIRouter(prefix="/api/stage-requests", tags=["客户生命周期"])


def _get_customer(db: Session, customer_id: int) -> Customer:
    c = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not c:
        raise HTTPException(404, "客户不存在")
    return c


def _requester_label(user: Optional[CurrentUser]) -> Optional[str]:
    if not user:
        return None
    return getattr(user, "sub", None) or getattr(user, "name", None)


@customer_router.post("/{customer_id}/stage/request", response_model=StageRequestOut,
                      summary="销售申请 stage 变更 (待主管批)")
def request_stage_change(
    customer_id: int,
    body: StageRequestBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    if body.to_stage not in STAGE_ORDER:
        raise HTTPException(400, f"非法 to_stage: {body.to_stage}, 允许 {list(STAGES)}")
    customer = _get_customer(db, customer_id)
    req = CustomerStageRequest(
        customer_id=customer.id,
        from_stage=customer.lifecycle_stage or "lead",
        to_stage=body.to_stage,
        reason=body.reason,
        status="pending",
        requested_by=_requester_label(user),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@customer_router.post("/{customer_id}/recycle", response_model=StageRequestOut,
                      summary="申请退回商机池 (回流到 lead)")
def request_recycle(
    customer_id: int,
    body: RecycleBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    customer = _get_customer(db, customer_id)
    if (customer.lifecycle_stage or "lead") == "lead":
        raise HTTPException(400, "客户已是 lead, 无需回流")
    req = CustomerStageRequest(
        customer_id=customer.id,
        from_stage=customer.lifecycle_stage or "lead",
        to_stage="lead",
        reason=body.reason,
        status="pending",
        requested_by=_requester_label(user),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@customer_router.get("/{customer_id}/stage-history", response_model=List[StageRequestOut],
                     summary="客户 stage 变更流水")
def stage_history(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    return (
        db.query(CustomerStageRequest)
        .filter(CustomerStageRequest.customer_id == customer_id)
        .order_by(CustomerStageRequest.id.desc())
        .all()
    )


@request_router.get("", response_model=List[StageRequestOut], summary="待审批列表")
def list_stage_requests(
    status: str = "pending",
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    rows = (
        db.query(CustomerStageRequest)
        .filter(CustomerStageRequest.status == status)
        .order_by(CustomerStageRequest.id.desc())
        .all()
    )
    return [_to_out(r, db) for r in rows]


@request_router.post("/{request_id}/approve", response_model=StageRequestOut,
                     summary="主管批准 stage 变更",
                     dependencies=[Depends(require_roles("sales-manager", "admin"))])
def approve_stage_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    req = db.query(CustomerStageRequest).filter(CustomerStageRequest.id == request_id).first()
    if not req:
        raise HTTPException(404, "申请不存在")
    if req.status != "pending":
        raise HTTPException(400, f"申请已处理: {req.status}")
    # 客户可能已被硬删/软删；这种情况下仍允许主管"通过"申请以清理积压，
    # 只是不再修改客户阶段（无对象可改）。
    customer = (
        db.query(Customer).filter(Customer.id == req.customer_id).first()
    )

    now = datetime.utcnow()
    if customer is not None and not getattr(customer, "is_deleted", False):
        if req.to_stage == "lost":
            # lost 是瞬态：审批通过立即回到 lead（商机池），附带回流标记
            customer.lifecycle_stage = "lead"
            customer.recycled_from_stage = req.from_stage
            customer.recycle_reason = req.reason or "流失回收"
            customer.recycled_at = now
        else:
            customer.lifecycle_stage = req.to_stage
            if req.to_stage == "lead":
                customer.recycled_from_stage = req.from_stage
                customer.recycle_reason = req.reason
                customer.recycled_at = now
        db.add(customer)

    req.status = "approved"
    req.decided_by = _requester_label(user)
    req.decided_at = now
    db.add(req)
    db.commit()
    db.refresh(req)
    return _to_out(req, db)


@request_router.post("/{request_id}/reject", response_model=StageRequestOut,
                     summary="主管驳回",
                     dependencies=[Depends(require_roles("sales-manager", "admin"))])
def reject_stage_request(
    request_id: int,
    body: StageRejectBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    req = db.query(CustomerStageRequest).filter(CustomerStageRequest.id == request_id).first()
    if not req:
        raise HTTPException(404, "申请不存在")
    if req.status != "pending":
        raise HTTPException(400, f"申请已处理: {req.status}")

    req.status = "rejected"
    req.decided_by = _requester_label(user)
    req.decision_comment = body.comment
    req.decided_at = datetime.utcnow()
    db.add(req)
    db.commit()
    db.refresh(req)
    return _to_out(req, db)
