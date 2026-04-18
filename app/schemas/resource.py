from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ResourceBase(BaseModel):
    resource_code: str = Field(..., description="货源编号")
    resource_type: str = Field(..., description="货源类型：ORIGINAL/OTHER")
    cloud_provider: Optional[str] = Field(None, description="云厂商：AWS/AZURE/GCP")
    identifier_field: Optional[str] = Field(None, description="标识字段")
    account_name: Optional[str] = Field(None, description="账号名称")
    definition_name: Optional[str] = Field(None, description="定义名称")
    cloud_account_id: Optional[str] = Field(None, description="云账号ID")
    total_quantity: Optional[int] = Field(None, description="总数量")
    unit_cost: Optional[Decimal] = Field(None, description="单位成本")
    suggested_price: Optional[Decimal] = Field(None, description="建议销售价")
    resource_status: str = Field(..., description="状态")


class ResourceCreate(ResourceBase):
    pass


class ResourceUpdate(BaseModel):
    resource_type: Optional[str] = None
    cloud_provider: Optional[str] = None
    total_quantity: Optional[int] = None
    unit_cost: Optional[Decimal] = None
    suggested_price: Optional[Decimal] = None
    resource_status: Optional[str] = None


class ResourceResponse(ResourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    allocated_quantity: int
    available_quantity: Optional[int]
    last_sync_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ResourceListResponse(BaseModel):
    total: int
    items: list[ResourceResponse]
