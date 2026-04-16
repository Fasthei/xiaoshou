"""Payment API — 收款计划 + 实收 + 超期追踪."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.contract import Contract


_STATUSES = {"pending", "received", "overdue", "cancelled"}


# ---------- Schemas ----------
class PaymentBase(BaseModel):
    customer_id: int
    contract_id: Optional[int] = None
    amount: Decimal
    expected_date: date
    received_date: Optional[date] = None
    status: Optional[str] = "pending"
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    pass


class PaymentPatch(BaseModel):
    contract_id: Optional[int] = None
    amount: Optional[Decimal] = None
    expected_date: Optional[date] = None
    received_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    mark_received: Optional[bool] = Field(None, description="True 时自动设 received_date=today, status=received")


class PaymentResponse(PaymentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/payments", tags=["收款"])


# ---------- CRUD ----------
@router.get("", response_model=List[PaymentResponse], summary="收款列表")
def list_payments(
    customer_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(Payment)
    if customer_id is not None:
        q = q.filter(Payment.customer_id == customer_id)
    if status is not None:
        if status not in _STATUSES:
            raise HTTPException(400, f"status 必须是 {sorted(_STATUSES)}")
        q = q.filter(Payment.status == status)
    return q.order_by(Payment.expected_date.desc(), Payment.id.desc()).all()


@router.post("", response_model=PaymentResponse, summary="登记收款计划/实收")
def create_payment(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == payload.customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")
    if payload.contract_id is not None:
        contract = db.query(Contract).filter(Contract.id == payload.contract_id).first()
        if not contract:
            raise HTTPException(404, "合同不存在")
    if payload.status and payload.status not in _STATUSES:
        raise HTTPException(400, f"status 必须是 {sorted(_STATUSES)}")

    row = Payment(**payload.model_dump())
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch("/{payment_id}", response_model=PaymentResponse, summary="更新收款 (支持 mark_received)")
def patch_payment(
    payment_id: int,
    payload: PaymentPatch,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = db.query(Payment).filter(Payment.id == payment_id).first()
    if not row:
        raise HTTPException(404, "收款记录不存在")

    patch = payload.model_dump(exclude_unset=True)
    mark_received = patch.pop("mark_received", None)
    if mark_received:
        row.received_date = date.today()
        row.status = "received"
    if "status" in patch and patch["status"] not in _STATUSES:
        raise HTTPException(400, f"status 必须是 {sorted(_STATUSES)}")
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.get("/overdue", response_model=List[PaymentResponse],
            summary="超期未收款 (pending 且 expected_date < today)")
def list_overdue(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    today = date.today()
    return (
        db.query(Payment)
        .filter(Payment.status == "pending", Payment.expected_date < today)
        .order_by(Payment.expected_date.asc())
        .all()
    )
