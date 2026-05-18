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
from app.integrations import CloudCostClient, GongdanClient
from app.models.customer import Customer
from app.models.resource import Resource
from app.models.sync_log import SyncLog
from app.api.customer_stage import auto_advance_stage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["同步"])


@router.post("/customers/from-ticket", summary="从工单系统同步客户编号")
def sync_customers_from_ticket(
    dry_run: bool = Query(False, description="仅预览差异，不落库"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """议题 B 两级删除策略：
      - 工单拉到的客户：create/update 到本地（source_system='gongdan'）
      - 本地有 source_system='gongdan'、lifecycle_stage='active' 但远端没了的
        → 降级到 'lead' 商机池；demoted_at/demoted_reason 记录来龙
      - 工单名字又冒出来但本地已 is_deleted=true (硬删墓碑) → skip 不复活
    """
    s = get_settings()
    if not s.GONGDAN_ENDPOINT or not s.GONGDAN_API_KEY:
        raise HTTPException(400, "GONGDAN_ENDPOINT / GONGDAN_API_KEY not configured")

    log = SyncLog(
        source_system="gongdan", sync_type="customers",
        triggered_by=f"{user.sub}:{user.name}", status="running",
    )
    db.add(log); db.commit(); db.refresh(log)

    client = GongdanClient(s.GONGDAN_ENDPOINT, s.GONGDAN_API_KEY)
    created = updated = skipped = errors = demoted = tombstoned = 0
    try:
        remote = client.list_customers()
        log.pulled_count = len(remote)
        remote_codes = {rc.customer_code for rc in remote if rc.customer_code}

        overrides: list[str] = []
        for rc in remote:
            if not rc.customer_code or not rc.name:
                skipped += 1
                continue
            try:
                # 墓碑拦截：本地存在 customer_code 且 is_deleted=true → 不复活
                tombstone = db.query(Customer).filter(
                    Customer.customer_code == rc.customer_code,
                    Customer.is_deleted == True,  # noqa: E712
                ).first()
                if tombstone is not None:
                    tombstoned += 1
                    skipped += 1
                    continue

                existing = db.query(Customer).filter(
                    Customer.customer_code == rc.customer_code,
                    Customer.is_deleted == False,  # noqa: E712
                ).first()
                if existing:
                    if existing.source_system != "gongdan":
                        # 冲突: 本地手工建的与工单编号撞车 -> 以工单为准, 删本地
                        overrides.append(
                            f"{rc.customer_code}: local id={existing.id} "
                            f"source_system={existing.source_system!r} "
                            f"name={existing.customer_name!r} -> replaced by gongdan"
                        )
                        if not dry_run:
                            # 软删本地 + INSERT 新工单记录
                            existing.is_deleted = True
                            existing.customer_code = (
                                f"{existing.customer_code}__overridden_{existing.id}"
                            )
                            db.add(existing)
                            db.flush()
                            new_c = Customer(
                                customer_code=rc.customer_code,
                                customer_name=rc.name,
                                customer_status="formal",
                                lifecycle_stage="active",
                                source_system="gongdan",
                                source_id=rc.id,
                            )
                            db.add(new_c)
                        updated += 1
                    else:
                        # 本地已是工单来源: 走原来的 update 逻辑 + 自动升 active
                        changed = False
                        if existing.customer_name != rc.name:
                            existing.customer_name = rc.name
                            changed = True
                        if existing.source_id != rc.id:
                            existing.source_id = rc.id
                            changed = True
                        # 若之前因工单侧消失而被降级，现在上游回来了 → 清除降级标记
                        if existing.demoted_at is not None:
                            existing.demoted_at = None
                            existing.demoted_reason = None
                            changed = True
                        # Auto lifecycle: gongdan 里有 = formalized -> active
                        if not dry_run:
                            stage_bumped = auto_advance_stage(
                                db, existing, "active",
                                reason=f"gongdan 同步: customer_code={rc.customer_code} 已正式建档",
                            )
                            if stage_bumped:
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
                            customer_status="formal",
                            lifecycle_stage="active",
                            source_system="gongdan",
                            source_id=rc.id,
                        ))
            except Exception as e:
                logger.exception("sync customer %s failed: %s", rc.customer_code, e)
                errors += 1

        # === 降级：本地 gongdan 来源 + active + is_deleted=false 但远端没了 ===
        absent_locals = db.query(Customer).filter(
            Customer.source_system == "gongdan",
            Customer.is_deleted == False,  # noqa: E712
            Customer.lifecycle_stage == "active",
            Customer.customer_code.isnot(None),
        ).all()
        for c in absent_locals:
            if c.customer_code in remote_codes:
                continue
            # 工单侧不再有该 customer_code → 降级
            demoted += 1
            if not dry_run:
                c.lifecycle_stage = "lead"
                c.recycled_from_stage = "active"
                c.recycle_reason = "gongdan 同步: 上游客户已消失, 自动降级回商机池"
                c.recycled_at = datetime.utcnow()
                c.demoted_at = datetime.utcnow()
                c.demoted_reason = "gongdan 侧已删除"
                db.add(c)

        if not dry_run:
            db.commit()

        log.created_count = created
        log.updated_count = updated
        log.skipped_count = skipped
        log.error_count = errors
        log.status = "success" if errors == 0 else "failed"
        log.finished_at = datetime.utcnow()
        notes: list[str] = []
        if demoted:
            notes.append(f"[demoted] {demoted} 个正式客户因上游消失降级到商机池")
        if tombstoned:
            notes.append(f"[tombstoned] {tombstoned} 个同名客户命中硬删墓碑, 未复活")
        if overrides:
            notes.append("[overrides] 本地手工客户被工单覆盖:\n" + "\n".join(overrides))
        if notes:
            log.last_error = ("\n".join(notes))[:2000]
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
        "demoted": demoted,
        "tombstoned": tombstoned,
        "sync_log_id": log.id,
    }


@router.post("/resources/from-cloudcost", summary="从云管镜像货源到本地 resource 表")
def sync_resources_from_cloudcost(
    dry_run: bool = Query(False),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """议题 B: 云管侧消失的货源 → 本地软删 (is_deleted=true, deleted_at)；
    customer_resource 关联保留以便审计 / 手工解绑。
    本地已软删的同 resource_code → skip（墓碑不复活）。
    """
    s = get_settings()
    if not s.CLOUDCOST_ENDPOINT:
        raise HTTPException(400, "CLOUDCOST_ENDPOINT not configured")

    log = SyncLog(
        source_system="cloudcost", sync_type="resources",
        triggered_by=f"{user.sub}:{user.name}", status="running",
    )
    db.add(log); db.commit(); db.refresh(log)

    client = CloudCostClient(s.CLOUDCOST_ENDPOINT)
    created = updated = skipped = errors = soft_deleted = tombstoned = 0
    try:
        accounts = client.list_service_accounts(page=1, page_size=500)
        log.pulled_count = len(accounts)
        remote_codes = {f"cc-{a.id}" for a in accounts}

        for a in accounts:
            try:
                code = f"cc-{a.id}"          # stable canonical 货源编号
                # 墓碑：同 code 已被软删 → skip（不复活）
                tomb = db.query(Resource).filter(
                    Resource.resource_code == code,
                    Resource.is_deleted == True,  # noqa: E712
                ).first()
                if tomb is not None:
                    tombstoned += 1
                    skipped += 1
                    continue

                existing = db.query(Resource).filter(
                    Resource.resource_code == code, Resource.is_deleted == False,  # noqa: E712
                ).first()
                payload = dict(
                    resource_code=code,
                    resource_type="cloud",
                    cloud_provider=(a.provider or "").upper() or None,
                    account_name=a.name,
                    definition_name=a.supplier_name,
                    identifier_field=a.external_project_id,
                    resource_status="AVAILABLE" if (a.status or "active") == "active" else (a.status or "UNKNOWN").upper(),
                    source_system="cloudcost",
                    source_id=str(a.id),
                    last_sync_time=datetime.utcnow(),
                )
                if existing:
                    changed = False
                    for k, v in payload.items():
                        if getattr(existing, k, None) != v:
                            setattr(existing, k, v); changed = True
                    if changed:
                        updated += 1
                        if not dry_run: db.add(existing)
                    else:
                        skipped += 1
                else:
                    created += 1
                    if not dry_run: db.add(Resource(**payload))
            except Exception as e:
                logger.exception("sync resource %s failed: %s", a.id, e)
                errors += 1

        # === 软删云管消失的资源 ===
        absent_locals = db.query(Resource).filter(
            Resource.source_system == "cloudcost",
            Resource.is_deleted == False,  # noqa: E712
        ).all()
        for r in absent_locals:
            if r.resource_code in remote_codes:
                continue
            soft_deleted += 1
            if not dry_run:
                r.is_deleted = True
                r.deleted_at = datetime.utcnow()
                r.resource_status = "DECOMMISSIONED"
                db.add(r)

        if not dry_run:
            db.commit()

        log.created_count = created
        log.updated_count = updated
        log.skipped_count = skipped
        log.error_count = errors
        log.status = "success" if errors == 0 else "failed"
        log.finished_at = datetime.utcnow()
        notes: list[str] = []
        if soft_deleted:
            notes.append(f"[soft_deleted] {soft_deleted} 个云管侧消失的货源已软删")
        if tombstoned:
            notes.append(f"[tombstoned] {tombstoned} 个同 resource_code 命中墓碑, 未复活")
        if notes:
            log.last_error = "\n".join(notes)[:2000]
        db.add(log); db.commit()
    except Exception as e:
        log.status = "failed"; log.last_error = str(e)[:2000]
        log.finished_at = datetime.utcnow()
        db.add(log); db.commit()
        raise HTTPException(502, f"云管同步失败: {e}")

    return {
        "dry_run": dry_run, "pulled": log.pulled_count,
        "created": created, "updated": updated, "skipped": skipped, "errors": errors,
        "soft_deleted": soft_deleted,
        "tombstoned": tombstoned,
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
