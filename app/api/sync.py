"""Admin-triggered sync endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations import GongdanClient
from app.models.customer import Customer
from app.models.sync_log import SyncLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["同步"])


@router.post("/customers/from-ticket", summary="从工单系统同步客户编号")
def sync_customers_from_ticket(
    dry_run: bool = Query(False, description="仅预览差异，不落库"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    s = get_settings()
    if not s.GONGDAN_ENDPOINT or not s.GONGDAN_API_KEY:
        raise HTTPException(400, "GONGDAN_ENDPOINT / GONGDAN_API_KEY not configured")

    log = SyncLog(
        source_system="gongdan", sync_type="customers",
        triggered_by=f"{user.sub}:{user.name}", status="running",
    )
    db.add(log); db.commit(); db.refresh(log)

    client = GongdanClient(s.GONGDAN_ENDPOINT, s.GONGDAN_API_KEY)
    created = updated = skipped = errors = 0
    try:
        remote = client.list_customers()
        log.pulled_count = len(remote)

        for rc in remote:
            if not rc.customer_code or not rc.name:
                skipped += 1
                continue
            try:
                existing = db.query(Customer).filter(
                    Customer.customer_code == rc.customer_code,
                    Customer.is_deleted == False,  # noqa: E712
                ).first()
                if existing:
                    changed = False
                    if existing.customer_name != rc.name:
                        existing.customer_name = rc.name
                        changed = True
                    if existing.source_system != "gongdan":
                        existing.source_system = "gongdan"
                        existing.source_id = rc.id
                        changed = True
                    if changed:
                        updated += 1
                        if not dry_run:
                            db.add(existing)
                    else:
                        skipped += 1
                else:
                    created += 1
                    if not dry_run:
                        db.add(Customer(
                            customer_code=rc.customer_code,
                            customer_name=rc.name,
                            customer_status="active",
                            source_system="gongdan",
                            source_id=rc.id,
                        ))
            except Exception as e:
                logger.exception("sync customer %s failed: %s", rc.customer_code, e)
                errors += 1

        if not dry_run:
            db.commit()

        log.created_count = created
        log.updated_count = updated
        log.skipped_count = skipped
        log.error_count = errors
        log.status = "success" if errors == 0 else "failed"
        log.finished_at = datetime.utcnow()
        db.add(log); db.commit()
    except Exception as e:
        logger.exception("sync failed: %s", e)
        log.status = "failed"
        log.last_error = str(e)[:2000]
        log.finished_at = datetime.utcnow()
        db.add(log); db.commit()
        raise HTTPException(502, f"工单系统同步失败: {e}")

    return {
        "dry_run": dry_run,
        "pulled": log.pulled_count,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "sync_log_id": log.id,
    }


@router.get("/logs", summary="同步历史")
def sync_logs(
    limit: int = Query(20, ge=1, le=200),
    source: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(SyncLog).order_by(SyncLog.id.desc())
    if source:
        q = q.filter(SyncLog.source_system == source)
    items = q.limit(limit).all()
    return [
        {
            "id": x.id,
            "source_system": x.source_system,
            "sync_type": x.sync_type,
            "status": x.status,
            "pulled": x.pulled_count,
            "created": x.created_count,
            "updated": x.updated_count,
            "skipped": x.skipped_count,
            "errors": x.error_count,
            "triggered_by": x.triggered_by,
            "started_at": x.started_at.isoformat() if x.started_at else None,
            "finished_at": x.finished_at.isoformat() if x.finished_at else None,
            "last_error": x.last_error,
        }
        for x in items
    ]
