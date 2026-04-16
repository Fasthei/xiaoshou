"""GET /api/customers/{id}/resources — bridge to 云管.

Resolve a customer's 货源 list by calling cloudcost and filtering service-accounts
whose {match_field} equals customer_code.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations import CloudCostClient
from app.models.customer import Customer


def _bearer_from_request(request: Request):
    """Forward the caller's Casdoor bearer token to cloudcost (shared Casdoor)."""
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


def _bad_gateway(e: BaseException) -> JSONResponse:
    msg = str(e) if str(e) else repr(e)
    if "\nFor more information" in msg:
        msg = msg.split("\nFor more information", 1)[0]
    msg = msg.strip()[:200]
    logger.warning("customer_resources: cloudcost unavailable: %s: %s", type(e).__name__, msg)
    return JSONResponse(
        status_code=502,
        content={"detail": f"云管暂不可达: {type(e).__name__}: {msg}"},
    )


@router.get("/{customer_id}/resources", summary="该客户在云管侧的关联货源")
def customer_resources(
    request: Request,
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")

    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    client = CloudCostClient(
        s.CLOUDCOST_ENDPOINT,
        match_field=s.CLOUDCOST_MATCH_FIELD,
        bearer_token=_bearer_from_request(request),
    )
    try:
        accounts = client.resources_for_customer(customer.customer_code)
    except HTTPException:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError, Exception) as e:
        return _bad_gateway(e)

    return {
        "customer_code": customer.customer_code,
        "match_field": s.CLOUDCOST_MATCH_FIELD,
        "total": len(accounts),
        "items": [
            {
                "resource_id": a.id,                        # cloudcost service_account.id
                "resource_name": a.name,
                "provider": a.provider,
                "supply_source_id": a.supply_source_id,     # 货源编号（规范字段）
                "supplier_name": a.supplier_name,
                "external_project_id": a.external_project_id,
                "status": a.status,
            }
            for a in accounts
        ],
    }
