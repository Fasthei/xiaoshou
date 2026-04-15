from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class InsightFactOut(BaseModel):
    id: int
    category: str
    content: str
    source_url: Optional[str] = None
    run_id: int
    discovered_at: datetime

    class Config:
        from_attributes = True


class InsightRunOut(BaseModel):
    id: int
    customer_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps_total: int
    steps_done: int
    error_message: Optional[str] = None
    summary: Optional[str] = None

    class Config:
        from_attributes = True


class InsightRunDetail(InsightRunOut):
    facts: List[InsightFactOut] = []
