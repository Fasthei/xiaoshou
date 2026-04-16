"""Ticket mirror API.

Two endpoints:
  * POST /api/sync/tickets/from-gongdan — admin pulls gongdan tickets and upserts into local ``ticket`` table.
  * GET  /api/customers/{id}/tickets    — per-customer list consumed by the detail drawer (精简字段).

Admin trigger reuses ``sync_log`` for auditability (source='gongdan', type='tickets').
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations import GongdanClient
from app.models.customer import Customer
from app.models.sync_log import SyncLog
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)

# Two distinct prefixes so the routes land on the right URLs; both exported.
sync_router = APIRouter(prefix="/api/sync", tags=["同步"])
customer_scoped = APIRouter(prefix="/api/customers", tags=["客户管理"])


# ---------- helpers ----------

def _parse_iso(value: Any) -> Optional[datetime]:
    """Best-effort ISO-8601 parser (gongdan sends Z-suffixed timestamps)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        # store naive UTC (to match other timestamps in the DB)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return None


def _derive_title(raw: Dict[str, Any]) -> str:
    """Pick the most useful human-readable label from a gongdan ticket.

    gongdan doesn't have a dedicated ``title`` — use description (trimmed) and
    fall back to request example / ticketNumber.
    """
    for key in ("description", "requestExample", "ticketNumber"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            s = v.strip().replace("\n", " ")
            return s[:497] + "..." if len(s) > 500 else s
    return ""


def _customer_code_of(raw: Dict[str, Any]) -> Optional[str]:
    cust = raw.get("customer")
    if isinstance(cust, dict):
        code = cust.get("customerCode")
        if isinstance(code, str) and code:
            return code
    # fallback flat key (defensive against API shape drift)
    flat = raw.get("customerCode")
    return flat if isinstance(flat, str) and flat else None


# ---------- routes ----------

@sync_router.post("/tickets/from-gongdan", summary="从工单系统同步工单到本地镜像")
def sync_tickets_from_gongdan(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """Pull every gongdan ticket and upsert into local ``ticket``.

    Returns counts in the same shape as /api/sync/customers/from-ticket so the
    frontend can reuse its success toast.
    """
    s = get_settings()
    if not s.GONGDAN_ENDPOINT or not s.GONGDAN_API_KEY:
        raise HTTPException(400, "GONGDAN_ENDPOINT / GONGDAN_API_KEY not configured")

    log = SyncLog(
        source_system="gongdan", sync_type="tickets",
        triggered_by=f"{user.sub}:{user.name}", status="running",
    )
    db.add(log); db.commit(); db.refresh(log)

    client = GongdanClient(s.GONGDAN_ENDPOINT, s.GONGDAN_API_KEY)
    created = updated = skipped = errors = 0
    try:
        remote = client.list_tickets()
        log.pulled_count = len(remote)

        now = datetime.utcnow()
        for raw in remote:
            try:
                ticket_code = raw.get("ticketNumber")
                if not ticket_code:
                    skipped += 1
                    continue
                payload = dict(
                    ticket_code=str(ticket_code),
                    remote_id=str(raw.get("id") or "") or None,
                    customer_code=_customer_code_of(raw),
                    title=_derive_title(raw),
                    status=str(raw.get("status") or "")[:40] or None,
                    created_at_remote=_parse_iso(raw.get("createdAt")),
                    updated_at_remote=_parse_iso(raw.get("updatedAt")),
                    sync_at=now,
                    raw=raw,
                )
                existing = db.query(Ticket).filter(Ticket.ticket_code == payload["ticket_code"]).first()
                if existing:
                    changed = False
                    for k, v in payload.items():
                        if getattr(existing, k, None) != v:
                            setattr(existing, k, v); changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.add(Ticket(**payload))
                    created += 1
            except Exception as e:
                logger.exception("sync ticket failed: %s", e)
                errors += 1

        db.commit()
        log.created_count = created
        log.updated_count = updated
        log.skipped_count = skipped
        log.error_count = errors
        log.status = "success" if errors == 0 else "failed"
        log.finished_at = datetime.utcnow()
        db.add(log); db.commit()
    except Exception as e:
        logger.exception("sync tickets failed: %s", e)
        log.status = "failed"
        log.last_error = str(e)[:2000]
        log.finished_at = datetime.utcnow()
        db.add(log); db.commit()
        raise HTTPException(502, f"工单同步失败: {e}")

    return {
        "pulled": log.pulled_count,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "sync_log_id": log.id,
    }


@customer_scoped.get("/{customer_id}/tickets", summary="该客户的本地工单列表 (精简字段)")
def list_customer_tickets(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> List[Dict[str, Any]]:
    """Return every mirrored ticket for the customer, newest first.

    Only precise fields UI needs: 编号 / 标题 / 状态 / 创建时间.
    """
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    if not customer.customer_code:
        return []

    rows = (
        db.query(Ticket)
        .filter(Ticket.customer_code == customer.customer_code)
        .order_by(Ticket.created_at_remote.desc().nullslast(), Ticket.id.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "created_at": t.created_at_remote.isoformat() if t.created_at_remote else None,
            "updated_at": t.updated_at_remote.isoformat() if t.updated_at_remote else None,
        }
        for t in rows
    ]
