from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AllocationHistoryOut(BaseModel):
    id: int
    allocation_id: int
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None
    at: datetime
    operator_casdoor_id: Optional[str] = None

    class Config:
        from_attributes = True


class CancelAllocationBody(BaseModel):
    reason: Optional[str] = None
