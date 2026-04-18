from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AllocationHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    allocation_id: int
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None
    at: datetime
    operator_casdoor_id: Optional[str] = None


class CancelAllocationBody(BaseModel):
    reason: Optional[str] = None
