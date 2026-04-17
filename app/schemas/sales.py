from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class SalesUserBase(BaseModel):
    name: str = Field(..., max_length=100)
    email: Optional[str] = None
    phone: Optional[str] = None
    casdoor_user_id: Optional[str] = None
    regions: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    max_customers: Optional[int] = Field(None, ge=1, description="容量上限, 空=不限")
    is_active: bool = True
    note: Optional[str] = None
    annual_profit_target: Optional[Decimal] = Field(None, description="年度毛利目标")
    annual_sales_target: Optional[Decimal] = Field(None, description="年度销售额目标")
    target_year: Optional[int] = Field(None, description="目标年份, 例 2026")


class SalesUserCreate(SalesUserBase):
    pass


class SalesUserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    casdoor_user_id: Optional[str] = None
    regions: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    max_customers: Optional[int] = None
    is_active: Optional[bool] = None
    note: Optional[str] = None
    annual_profit_target: Optional[Decimal] = None
    annual_sales_target: Optional[Decimal] = None
    target_year: Optional[int] = None


class SalesLoadItem(BaseModel):
    id: int
    name: str
    current_count: int
    max_customers: Optional[int] = None
    load_pct: int = Field(..., description="0-100, -1 if no cap set")
    is_active: bool


class ActivityItem(BaseModel):
    kind: str = Field(..., description="follow_up | assignment | insight_run")
    at: str
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    title: str
    detail: Optional[str] = None


class SalesUserOut(SalesUserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RuleBase(BaseModel):
    name: str = Field(..., max_length=100)
    industry: Optional[str] = None
    region: Optional[str] = None
    customer_level: Optional[str] = None
    sales_user_id: Optional[int] = Field(None, description="单人模式, 与 sales_user_ids 互斥")
    sales_user_ids: Optional[List[int]] = Field(None, description="轮询模式候选 id 列表")
    priority: int = 100
    is_active: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    customer_level: Optional[str] = None
    sales_user_id: Optional[int] = None
    sales_user_ids: Optional[List[int]] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class RuleOut(RuleBase):
    id: int
    cursor: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class RecycleBody(BaseModel):
    stale_days: int = Field(30, ge=1, le=365, description="超 N 天无跟进视为过期")
    dry_run: bool = False


class RecycleItem(BaseModel):
    customer_id: int
    customer_code: str
    from_user_id: Optional[int]
    last_follow_time: Optional[datetime]
    reason: str


class RecycleResult(BaseModel):
    total_scanned: int
    total_recycled: int
    stale_days: int
    dry_run: bool
    items: List[RecycleItem]


class AssignBody(BaseModel):
    sales_user_id: Optional[int] = Field(None, description="设为 null 可取消分配")
    reason: Optional[str] = None


class AutoAssignBody(BaseModel):
    dry_run: bool = False
    only_unassigned: bool = True


class AutoAssignItem(BaseModel):
    customer_id: int
    customer_code: str
    matched_rule_id: Optional[int] = None
    sales_user_id: Optional[int] = None
    reason: str


class AutoAssignResult(BaseModel):
    total_scanned: int
    total_assigned: int
    items: List[AutoAssignItem]
    dry_run: bool


class AssignmentLogOut(BaseModel):
    id: int
    customer_id: int
    from_user_id: Optional[int] = None
    to_user_id: Optional[int] = None
    reason: Optional[str] = None
    trigger: str
    rule_id: Optional[int] = None
    at: datetime
    operator_casdoor_id: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- 年度目标 + 进度 ----------

class TargetSetBody(BaseModel):
    annual_profit_target: Decimal = Field(..., description="年度毛利目标金额")
    target_year: int = Field(..., ge=2000, le=2100)


class TargetProgressOut(BaseModel):
    sales_user_id: int
    sales_user_name: str
    target_year: Optional[int] = None
    annual_profit_target: Optional[Decimal] = None
    ytd_profit: Decimal = Field(Decimal("0"), description="当年累计毛利")
    progress_pct: float = Field(0.0, description="0-100 或 0-200 的进度百分比")
    allocations_count: int = 0
    last_update: Optional[datetime] = None


# ---------- 工作计划 CRUD ----------

class SalesPlanBase(BaseModel):
    user_id: int
    plan_date: date
    plan_type: str = Field(..., description="daily | weekly | monthly")
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    status: str = Field("pending", description="pending | in_progress | done | cancelled")


class SalesPlanCreate(SalesPlanBase):
    pass


class SalesPlanUpdate(BaseModel):
    plan_date: Optional[date] = None
    plan_type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[str] = None


class SalesPlanOut(SalesPlanBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
