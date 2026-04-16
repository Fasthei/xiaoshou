"""AlertRule API — 自定义预警规则 CRUD + 触发列表."""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.alert_rule import AlertRule
from app.models.customer import Customer


_RULE_TYPES = {"cost_upper", "cost_lower", "payment_overdue"}


# ---------- Schemas ----------
class AlertRuleBase(BaseModel):
    customer_id: Optional[int] = Field(None, description="客户ID, 空=全局规则")
    rule_name: str = Field(..., max_length=200)
    rule_type: str = Field(..., description="cost_upper/cost_lower/payment_overdue")
    threshold_value: Optional[Decimal] = None
    threshold_unit: Optional[str] = "CNY"
    enabled: Optional[bool] = True
    notes: Optional[str] = None


class AlertRuleCreate(AlertRuleBase):
    pass


class AlertRulePatch(BaseModel):
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    threshold_value: Optional[Decimal] = None
    threshold_unit: Optional[str] = None
    enabled: Optional[bool] = None
    notes: Optional[str] = None


class AlertRuleResponse(AlertRuleBase):
    id: int
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


router = APIRouter(prefix="/api/alert-rules", tags=["预警规则"])


# ---------- CRUD ----------
@router.get("", response_model=List[AlertRuleResponse], summary="规则列表")
def list_rules(
    customer_id: Optional[int] = Query(None, description="按客户过滤, 可含全局"),
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(AlertRule)
    if customer_id is not None:
        # 指定客户时同时返回全局规则
        q = q.filter((AlertRule.customer_id == customer_id) | (AlertRule.customer_id.is_(None)))
    if enabled is not None:
        q = q.filter(AlertRule.enabled == enabled)
    return q.order_by(AlertRule.id.desc()).all()


@router.post("", response_model=AlertRuleResponse, summary="创建规则")
def create_rule(
    payload: AlertRuleCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    if payload.rule_type not in _RULE_TYPES:
        raise HTTPException(400, f"rule_type 必须是 {sorted(_RULE_TYPES)}")
    if payload.customer_id is not None:
        exists = db.query(Customer).filter(
            Customer.id == payload.customer_id, Customer.is_deleted == False,  # noqa: E712
        ).first()
        if not exists:
            raise HTTPException(404, "客户不存在")

    data = payload.model_dump()
    row = AlertRule(**data)
    # created_by 若能解析 sales_user 关系可写, 否则留 None (此处简化留 None)
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.patch("/{rule_id}", response_model=AlertRuleResponse, summary="更新规则")
def patch_rule(
    rule_id: int,
    payload: AlertRulePatch,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not row:
        raise HTTPException(404, "规则不存在")
    patch = payload.model_dump(exclude_unset=True)
    if "rule_type" in patch and patch["rule_type"] not in _RULE_TYPES:
        raise HTTPException(400, f"rule_type 必须是 {sorted(_RULE_TYPES)}")
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row); db.commit(); db.refresh(row)
    return row


@router.delete("/{rule_id}", summary="删除规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = db.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not row:
        raise HTTPException(404, "规则不存在")
    db.delete(row); db.commit()
    return {"ok": True}


@router.get("/triggered", response_model=List[AlertRuleResponse],
            summary="当前触发的规则 (简化: 列出所有启用的规则)")
def list_triggered(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    # TODO: detail 算法 — 需结合 usage/payment 动态判断是否真的触发
    return (
        db.query(AlertRule)
        .filter(AlertRule.enabled == True)  # noqa: E712
        .order_by(AlertRule.id.desc())
        .all()
    )
