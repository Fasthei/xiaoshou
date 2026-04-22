"""bill_adjustment API — 账单中心按 (客户 × 货源 × 月) 覆盖折扣率 / 加手续费。

只有 sales / sales-manager / admin 能写；权限读侧复用 bills_by_customer 的
行级过滤 (销售只能读自己名下客户的 adjustment)。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth, require_roles
from app.database import get_db
from app.models.bill_adjustment import BillAdjustment
from app.models.customer import Customer
from app.models.sales import SalesUser


router = APIRouter(prefix="/api/bills/adjustment", tags=["账单-覆盖折扣"])


# ---------- schemas ----------

class BillAdjustmentIn(BaseModel):
    customer_id: int
    resource_id: int
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    discount_rate_override: Optional[Decimal] = Field(
        None, description="覆盖折扣率 %（0-100, 可负）；NULL=沿用订单折扣",
    )
    surcharge: Optional[Decimal] = Field(
        None, description="附加手续费（可正可负）",
    )
    notes: Optional[str] = None


class BillAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    resource_id: int
    month: str
    discount_rate_override: Optional[Decimal] = None
    surcharge: Optional[Decimal] = None
    notes: Optional[str] = None
    updated_by: Optional[str] = None


# ---------- helpers ----------

_MANAGER_ROLES = {"sales-manager", "admin", "ops", "operation", "operations"}


def _can_see_all(user: CurrentUser) -> bool:
    return any(user.has_role(r) for r in _MANAGER_ROLES)


def _assert_can_touch_customer(db: Session, user: CurrentUser, customer_id: int) -> Customer:
    """sales 只能改自己的客户; manager 系列不受限。"""
    cust = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not cust:
        raise HTTPException(404, "客户不存在")
    if _can_see_all(user):
        return cust
    # 反查本地 sales_user.id
    su = db.query(SalesUser).filter(SalesUser.casdoor_user_id == user.sub).first()
    sid: Optional[int]
    if su:
        sid = int(su.id)
    else:
        try:
            sid = int(user.sub)
        except (TypeError, ValueError):
            sid = None
    if sid is None or cust.sales_user_id != sid:
        raise HTTPException(403, "无权修改该客户账单")
    return cust


# ---------- endpoints ----------

@router.get("", summary="查询账单覆盖（按客户/月份）", response_model=list[BillAdjustmentOut])
def list_adjustments(
    customer_id: int = Query(...),
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    _assert_can_touch_customer(db, user, customer_id)
    q = db.query(BillAdjustment).filter(BillAdjustment.customer_id == customer_id)
    if month:
        q = q.filter(BillAdjustment.month == month)
    return q.order_by(BillAdjustment.updated_at.desc()).all()


@router.put(
    "",
    summary="upsert 覆盖（customer × resource × month 唯一）",
    response_model=BillAdjustmentOut,
    dependencies=[Depends(require_roles("sales", "sales-manager", "admin"))],
)
def upsert_adjustment(
    payload: BillAdjustmentIn,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    _assert_can_touch_customer(db, user, payload.customer_id)
    row = db.query(BillAdjustment).filter(
        BillAdjustment.customer_id == payload.customer_id,
        BillAdjustment.resource_id == payload.resource_id,
        BillAdjustment.month == payload.month,
    ).first()
    stamp = f"{user.sub}:{user.name}"[:200]
    if row:
        row.discount_rate_override = payload.discount_rate_override
        row.surcharge = payload.surcharge
        row.notes = payload.notes
        row.updated_by = stamp
    else:
        row = BillAdjustment(
            customer_id=payload.customer_id,
            resource_id=payload.resource_id,
            month=payload.month,
            discount_rate_override=payload.discount_rate_override,
            surcharge=payload.surcharge,
            notes=payload.notes,
            updated_by=stamp,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "",
    summary="清除覆盖（还原为订单折扣，不含手续费）",
    dependencies=[Depends(require_roles("sales", "sales-manager", "admin"))],
)
def delete_adjustment(
    customer_id: int = Query(...),
    resource_id: int = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    _assert_can_touch_customer(db, user, customer_id)
    row = db.query(BillAdjustment).filter(
        BillAdjustment.customer_id == customer_id,
        BillAdjustment.resource_id == resource_id,
        BillAdjustment.month == month,
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return {"deleted": bool(row)}
