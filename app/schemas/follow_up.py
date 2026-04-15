from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


FOLLOW_UP_KINDS = {"call", "meeting", "email", "wechat", "note", "other"}
OUTCOMES = {"positive", "neutral", "negative", "needs_followup"}


class FollowUpCreate(BaseModel):
    kind: str = Field("note", description="call|meeting|email|wechat|note|other")
    title: str
    content: Optional[str] = None
    outcome: Optional[str] = None
    next_action_at: Optional[datetime] = None


class FollowUpOut(BaseModel):
    id: int
    customer_id: int
    kind: str
    title: str
    content: Optional[str] = None
    outcome: Optional[str] = None
    next_action_at: Optional[datetime] = None
    operator_casdoor_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CompletenessOut(BaseModel):
    customer_id: int
    score: int = Field(..., ge=0, le=100)
    tier: str = Field(..., description="red|yellow|green")
    missing: List[str]
    present: List[str]
