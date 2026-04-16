from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


class CustomerContactBase(BaseModel):
    contact_name: str = Field(..., description="联系人姓名")
    contact_title: Optional[str] = Field(None, description="职位")
    contact_phone: Optional[str] = Field(None, description="电话")
    contact_email: Optional[str] = Field(None, description="邮箱")
    contact_wechat: Optional[str] = Field(None, description="微信")
    is_primary: bool = Field(False, description="是否主联系人")


class CustomerContactCreate(CustomerContactBase):
    pass


class CustomerContactResponse(CustomerContactBase):
    id: int
    customer_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerBase(BaseModel):
    customer_code: str = Field(..., description="客户编号")
    customer_name: str = Field(..., description="客户名称")
    customer_short_name: Optional[str] = Field(None, description="客户简称")
    industry: Optional[str] = Field(None, description="所属行业")
    region: Optional[str] = Field(None, description="所属地区")
    customer_level: Optional[str] = Field(None, description="客户级别")
    customer_status: str = Field(..., description="客户状态 potential/active/formal/inactive/frozen")
    sales_user_id: Optional[int] = Field(None, description="所属销售")
    operation_user_id: Optional[int] = Field(None, description="所属运营")
    source_label: Optional[str] = Field(None, description="来源描述 (用户手填)")
    employee_size: Optional[int] = None
    annual_revenue: Optional[Decimal] = None
    last_meeting_at: Optional[datetime] = None
    trade_count: Optional[int] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    note: Optional[str] = None


class CustomerCreate(CustomerBase):
    customer_status: str = Field("potential", description="客户状态, 默认潜在客户")


class CustomerCreateLite(BaseModel):
    """Relaxed create payload used by frontend new-customer form (status optional, defaults to potential)."""
    customer_code: str
    customer_name: str
    customer_short_name: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    customer_level: Optional[str] = None
    customer_status: Optional[str] = Field("potential")
    sales_user_id: Optional[int] = None
    operation_user_id: Optional[int] = None
    source_label: Optional[str] = None


class CustomerUpdate(BaseModel):
    customer_name: Optional[str] = None
    customer_short_name: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    customer_level: Optional[str] = None
    customer_status: Optional[str] = None
    sales_user_id: Optional[int] = None
    operation_user_id: Optional[int] = None
    source_label: Optional[str] = None
    employee_size: Optional[int] = None
    annual_revenue: Optional[Decimal] = None
    last_meeting_at: Optional[datetime] = None
    trade_count: Optional[int] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    note: Optional[str] = None


class CustomerResponse(CustomerBase):
    id: int
    current_resource_count: int
    current_month_consumption: Decimal
    next_month_forecast: Optional[Decimal]
    first_deal_time: Optional[datetime]
    last_follow_time: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    contacts: list[CustomerContactResponse] = []
    sales_user_name: Optional[str] = None

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    total: int
    items: list[CustomerResponse]
