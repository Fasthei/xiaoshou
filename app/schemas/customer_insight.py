from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class InsightFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    content: str
    source_url: Optional[str] = None
    run_id: int
    discovered_at: datetime


class InsightRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    steps_total: int
    steps_done: int
    error_message: Optional[str] = None
    summary: Optional[str] = None
    fact_count: int = 0
    duration_ms: Optional[int] = None


class InsightRunDetail(InsightRunOut):
    facts: List[InsightFactOut] = []
