from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class AllocationBase(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    resource_id: int = Field(..., description="货源ID")
    allocated_quantity: int = Field(..., description="分配数量")
    unit_price: Optional[Decimal] = Field(
        None,
        description="单位售价（后付费可空；销售不预知单价时留 NULL，"
                    "账单中心从 cc_usage 反算原价 × (1-折扣)）",
    )
    remark: Optional[str] = Field(None, description="备注")
    end_user_label: Optional[str] = Field(None, description="渠道订单下终端用户标签 (仅 channel 客户)")


class AllocationCreate(AllocationBase):
    pass


class AllocationUpdate(BaseModel):
    allocated_quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    allocation_status: Optional[str] = None
    delivery_status: Optional[str] = None
    remark: Optional[str] = None


class AllocationResponse(AllocationBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    allocation_code: str
    unit_cost: Optional[Decimal]
    total_cost: Optional[Decimal]
    total_price: Optional[Decimal]
    profit_amount: Optional[Decimal]
    profit_rate: Optional[Decimal]
    discount_rate: Optional[Decimal] = None
    unit_price_after_discount: Optional[Decimal] = None
    allocation_status: str
    allocated_by: Optional[int]
    allocated_at: Optional[datetime]
    delivery_status: Optional[str]
    delivery_at: Optional[datetime]
    # 审批工作流
    approval_status: Optional[str] = None
    approver_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    approval_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AllocationListResponse(BaseModel):
    total: int
    items: list[AllocationResponse]


class AllocationProfitResponse(BaseModel):
    allocation_id: int
    total_cost: Decimal
    total_price: Decimal
    profit_amount: Decimal
    profit_rate: Decimal


class AllocationApprovalRequest(BaseModel):
    approval_status: str = Field(..., description="approved 或 rejected")
    approval_note: Optional[str] = Field(None, description="审批备注")


class AllocationBatchLine(BaseModel):
    """一条订单明细。

    业务口径（云后付费）：
    - resource_id：必选（每个货源是独立折扣主体）
    - discount_rate：必填（%，可为 0，可为负表加价）
    - quantity：必填（即使后付费也要有约定量，可填 1 占位）
    - unit_price / unit_cost：**可选**。后付费下销售不预知单价，
      所以允许留空；账单侧以 cc_usage 做原价、再乘该折扣率出折后。
    """
    resource_id: int = Field(..., description="货源 ID（必选）")
    quantity: int = Field(..., ge=1)
    unit_cost: Optional[Decimal] = Field(None, description="折前单价 / 成本（后付费可空）")
    unit_price: Optional[Decimal] = Field(None, description="折后单价（后付费可空）")
    discount_rate: Decimal = Field(..., description="折扣率 % (0-100, 可负)；必填")
    end_user_label: Optional[str] = None
    remark: Optional[str] = None


class AllocationBatchCreate(BaseModel):
    customer_id: int
    contract_id: Optional[int] = None
    lines: list[AllocationBatchLine]


class AllocationBatchResponse(BaseModel):
    batch_code: str
    created: list[AllocationResponse]
