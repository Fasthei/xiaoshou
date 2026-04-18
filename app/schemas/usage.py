from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime, date
from decimal import Decimal


class UsageRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    resource_id: int
    allocation_id: Optional[int]
    usage_date: datetime
    usage_amount: Optional[Decimal]
    usage_cost: Optional[Decimal]
    created_at: datetime


class UsageListResponse(BaseModel):
    total: int
    items: list[UsageRecordResponse]


class UsageSummaryResponse(BaseModel):
    customer_id: int
    total_usage: Decimal
    total_cost: Decimal
    record_count: int
    start_date: date
    end_date: date


class UsageTrendResponse(BaseModel):
    date: date
    usage_amount: Decimal
    usage_cost: Decimal
