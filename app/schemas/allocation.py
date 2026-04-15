from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class AllocationBase(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    resource_id: int = Field(..., description="货源ID")
    allocated_quantity: int = Field(..., description="分配数量")
    unit_price: Decimal = Field(..., description="单位售价")
    remark: Optional[str] = Field(None, description="备注")


class AllocationCreate(AllocationBase):
    pass


class AllocationUpdate(BaseModel):
    allocated_quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    allocation_status: Optional[str] = None
    delivery_status: Optional[str] = None
    remark: Optional[str] = None


class AllocationResponse(AllocationBase):
    id: int
    allocation_code: str
    unit_cost: Optional[Decimal]
    total_cost: Optional[Decimal]
    total_price: Optional[Decimal]
    profit_amount: Optional[Decimal]
    profit_rate: Optional[Decimal]
    allocation_status: str
    allocated_by: Optional[int]
    allocated_at: Optional[datetime]
    delivery_status: Optional[str]
    delivery_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AllocationListResponse(BaseModel):
    total: int
    items: list[AllocationResponse]


class AllocationProfitResponse(BaseModel):
    allocation_id: int
    total_cost: Decimal
    total_price: Decimal
    profit_amount: Decimal
    profit_rate: Decimal
