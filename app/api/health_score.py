"""Customer health score — aggregates 4 dimensions into a 0-100 score + radar data."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.customer import Customer

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


def _score(customer: Customer, allocations: int, has_recent: bool, has_contact: bool) -> Dict[str, int]:
    """Return radar-chart dimensions, each 0-100."""
    consumption = float(customer.current_month_consumption or 0)
    # consumption curve: 0 → 20, 1000 → 85, 10000+ → 95
    consumption_score = min(95, int(20 + 0.065 * consumption))

    # activity: has_recent OR follow-up within 30 days → high
    last = customer.last_follow_time
    if last and (datetime.utcnow() - last).days <= 30:
        activity = 90
    elif has_recent:
        activity = 70
    elif last and (datetime.utcnow() - last).days <= 90:
        activity = 50
    else:
        activity = 25

    engagement = 40 + 12 * min(allocations, 5)     # each allocation up to 5 counts
    completeness = 30 + (30 if customer.industry else 0) + (20 if customer.region else 0) + (20 if has_contact else 0)

    return {
        "consumption": consumption_score,
        "activity": activity,
        "engagement": min(100, engagement),
        "completeness": min(100, completeness),
    }


@router.get("/{customer_id}/health", summary="客户健康分")
def customer_health(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    c = db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()  # noqa: E712
    if not c:
        raise HTTPException(404, "客户不存在")

    alloc_count = db.query(Allocation).filter(
        Allocation.customer_id == c.id, Allocation.is_deleted == False,  # noqa: E712
    ).count()
    has_recent = db.query(Allocation).filter(
        Allocation.customer_id == c.id,
        Allocation.is_deleted == False,  # noqa: E712
        Allocation.updated_at >= datetime.utcnow() - timedelta(days=30),
    ).first() is not None
    has_contact = bool(getattr(c, "contacts", None))

    radar = _score(c, alloc_count, has_recent, has_contact)
    score = int(sum(radar.values()) / 4)
    tier = "green" if score >= 75 else "yellow" if score >= 50 else "red"

    return {
        "customer_id": c.id,
        "customer_code": c.customer_code,
        "score": score,
        "tier": tier,
        "radar": radar,
        "tips": [
            "补全行业/地区以提升完整度" if radar["completeness"] < 70 else None,
            "30 天内跟进以保持活跃度" if radar["activity"] < 60 else None,
            "推荐新增货源分配促活" if radar["engagement"] < 60 else None,
        ],
    }
