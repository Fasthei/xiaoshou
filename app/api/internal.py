"""Internal API consumed by the 云管 system to pull allocation records.

Auth: accepts either
- Authorization: Bearer <Casdoor client_credentials JWT> whose `aud` is in
  CASDOOR_INTERNAL_ALLOWED_CLIENTS, OR
- X-Internal-Api-Key: <static key> matching XIAOSHOU_INTERNAL_API_KEY (bootstrap).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.integrations.casdoor_m2m import verify_internal
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.resource import Resource

router = APIRouter(prefix="/api/internal", tags=["内部 M2M"])


def _auth(request: Request, x_internal_api_key: Optional[str] = Header(None)) -> None:
    auth = request.headers.get("authorization", "")
    token = auth.split(" ", 1)[1].strip() if auth.lower().startswith("bearer ") else None
    if not verify_internal(token, x_internal_api_key):
        raise HTTPException(401, "internal auth failed")


@router.get("/allocations", summary="供云管拉取分配结果（货源编号↔客户编号）")
def export_allocations(
    since: Optional[str] = Query(None, description="ISO8601，只返回 updated_at>=since"),
    limit: int = Query(1000, ge=1, le=5000),
    _auth_dep: None = Depends(_auth),
    db: Session = Depends(get_db),
):
    q = db.query(Allocation, Customer, Resource) \
        .join(Customer, Customer.id == Allocation.customer_id) \
        .join(Resource, Resource.id == Allocation.resource_id) \
        .filter(Allocation.is_deleted == False)  # noqa: E712

    if since:
        try:
            dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "invalid `since`, expect ISO8601")
        q = q.filter(Allocation.updated_at >= dt)

    rows = q.order_by(Allocation.updated_at.desc()).limit(limit).all()

    items = []
    for a, c, r in rows:
        items.append({
            "allocation_code": a.allocation_code,
            "customer_code": c.customer_code,
            "resource_code": r.resource_code,
            "allocated_quantity": a.allocated_quantity,
            "unit_cost": float(a.unit_cost) if a.unit_cost is not None else None,
            "unit_price": float(a.unit_price) if a.unit_price is not None else None,
            "total_cost": float(a.total_cost) if a.total_cost is not None else None,
            "total_price": float(a.total_price) if a.total_price is not None else None,
            "profit_amount": float(a.profit_amount) if a.profit_amount is not None else None,
            "allocation_status": a.allocation_status,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
        })
    return {"total": len(items), "items": items}
