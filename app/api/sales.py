"""Sales team + lead assignment API.

Endpoints:
    GET/POST                      /api/sales/users
    PATCH/DELETE                  /api/sales/users/{id}
    GET/POST                      /api/sales/rules
    PATCH/DELETE                  /api/sales/rules/{id}
    PATCH                         /api/customers/{id}/assign
    POST                          /api/sales/auto-assign
    GET                           /api/customers/{id}/assignment-log
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.customer import Customer
from app.models.sales import LeadAssignmentLog, LeadAssignmentRule, SalesUser
from app.schemas.sales import (
    ActivityItem,
    AssignBody, AssignmentLogOut, AutoAssignBody, AutoAssignItem, AutoAssignResult,
    RecycleBody, RecycleItem, RecycleResult,
    RuleCreate, RuleOut, RuleUpdate,
    SalesLoadItem, SalesUserCreate, SalesUserOut, SalesUserUpdate,
)
from sqlalchemy import func as _sql_func

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sales", tags=["销售团队 / 分配"])

# Second router — endpoints mounted under /api/customers/{id}/... live here.
# Kept separate so main.py can slot both under the auth dep list.
customer_scoped = APIRouter(prefix="/api/customers", tags=["销售团队 / 分配"])


# ---------- sales users CRUD ----------

@router.get("/users", response_model=List[SalesUserOut], summary="销售列表")
def list_users(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(SalesUser)
    if active_only:
        q = q.filter(SalesUser.is_active == True)  # noqa: E712
    return q.order_by(SalesUser.id.asc()).all()


@router.post("/users", response_model=SalesUserOut, summary="新增销售")
def create_user(
    body: SalesUserCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    user = SalesUser(**body.model_dump())
    db.add(user); db.commit(); db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=SalesUserOut, summary="更新销售")
def update_user(
    user_id: int,
    body: SalesUserUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    user = db.query(SalesUser).filter(SalesUser.id == user_id).first()
    if not user:
        raise HTTPException(404, "销售不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    db.add(user); db.commit(); db.refresh(user)
    return user


@router.get("/users/load", response_model=List[SalesLoadItem],
            summary="销售负载: 每人当前客户数 / 容量 / 占比")
def sales_load(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    users = db.query(SalesUser).order_by(SalesUser.id.asc()).all()
    # Aggregate customer counts per sales_user_id
    rows = (
        db.query(Customer.sales_user_id, _sql_func.count(Customer.id))
        .filter(Customer.is_deleted == False)  # noqa: E712
        .filter(Customer.sales_user_id.isnot(None))
        .group_by(Customer.sales_user_id)
        .all()
    )
    counts = {uid: n for uid, n in rows}
    out: List[SalesLoadItem] = []
    for u in users:
        current = counts.get(u.id, 0)
        if u.max_customers:
            pct = min(100, round(current * 100 / u.max_customers))
        else:
            pct = -1
        out.append(SalesLoadItem(
            id=u.id, name=u.name,
            current_count=current, max_customers=u.max_customers,
            load_pct=pct, is_active=u.is_active,
        ))
    return out


@router.delete("/users/{user_id}", summary="停用销售 (软删)")
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    user = db.query(SalesUser).filter(SalesUser.id == user_id).first()
    if not user:
        raise HTTPException(404, "销售不存在")
    user.is_active = False
    db.add(user); db.commit()
    return {"ok": True, "id": user_id}


# ---------- rules CRUD ----------

@router.get("/rules", response_model=List[RuleOut], summary="分配规则列表")
def list_rules(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(LeadAssignmentRule)
    if active_only:
        q = q.filter(LeadAssignmentRule.is_active == True)  # noqa: E712
    return q.order_by(LeadAssignmentRule.priority.asc(), LeadAssignmentRule.id.asc()).all()


def _validate_rule_targets(db: Session, single_id: Optional[int], ids: Optional[List[int]]):
    if not single_id and not ids:
        raise HTTPException(400, "必须指定 sales_user_id 或 sales_user_ids")
    if ids:
        if len(ids) < 1:
            raise HTTPException(400, "sales_user_ids 至少 1 个")
        found = db.query(SalesUser.id).filter(SalesUser.id.in_(ids)).all()
        if len(found) != len(set(ids)):
            raise HTTPException(400, "sales_user_ids 包含不存在的销售")
    if single_id:
        if not db.query(SalesUser).filter(SalesUser.id == single_id).first():
            raise HTTPException(400, "sales_user_id 对应销售不存在")


@router.post("/rules", response_model=RuleOut, summary="新建分配规则")
def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    _validate_rule_targets(db, body.sales_user_id, body.sales_user_ids)
    rule = LeadAssignmentRule(**body.model_dump())
    db.add(rule); db.commit(); db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut, summary="更新规则")
def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    rule = db.query(LeadAssignmentRule).filter(LeadAssignmentRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")
    data = body.model_dump(exclude_unset=True)
    if "sales_user_id" in data or "sales_user_ids" in data:
        single = data.get("sales_user_id", rule.sales_user_id)
        multi = data.get("sales_user_ids", rule.sales_user_ids)
        _validate_rule_targets(db, single, multi)
        if "sales_user_ids" in data:
            rule.cursor = 0  # reset cursor when pool changes
    for k, v in data.items():
        setattr(rule, k, v)
    db.add(rule); db.commit(); db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", summary="删除规则")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    rule = db.query(LeadAssignmentRule).filter(LeadAssignmentRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "规则不存在")
    db.delete(rule); db.commit()
    return {"ok": True, "id": rule_id}


# ---------- rule matching engine ----------

def _match_rule(customer: Customer, rules: List[LeadAssignmentRule]) -> Optional[LeadAssignmentRule]:
    """Pick the highest-priority (lowest .priority) active rule whose non-null
    fields all match the customer. A rule with all nullable fields empty is a
    wildcard — useful as a catch-all with high .priority number.
    """
    for rule in rules:  # rules are already sorted by priority asc
        if not rule.is_active:
            continue
        if rule.industry and customer.industry != rule.industry:
            continue
        if rule.region and customer.region != rule.region:
            continue
        if rule.customer_level and customer.customer_level != rule.customer_level:
            continue
        return rule
    return None


def _pick_target_user(
    rule: LeadAssignmentRule,
    capacity: Optional[dict] = None,
) -> Optional[int]:
    """Given a matched rule, pick the sales_user_id to assign to.
    If round-robin (sales_user_ids non-empty), use cursor and increment it,
    skipping any user at/over capacity (if capacity map given).
    Otherwise fall back to rule.sales_user_id (returns None if over capacity).
    Caller is responsible for committing the cursor mutation.
    """
    ids = rule.sales_user_ids or []
    if isinstance(ids, list) and len(ids) > 0:
        # Try up to len(ids) slots, skipping over-capacity users
        for _try in range(len(ids)):
            idx = (rule.cursor or 0) % len(ids)
            uid = ids[idx]
            rule.cursor = (rule.cursor or 0) + 1
            if capacity is None or not _over_capacity(uid, capacity):
                return uid
        return None  # all users at capacity
    uid = rule.sales_user_id
    if uid and capacity is not None and _over_capacity(uid, capacity):
        return None
    return uid


def _over_capacity(uid: int, capacity: dict) -> bool:
    entry = capacity.get(uid)
    if not entry:
        return False
    max_c = entry.get("max")
    if not max_c:
        return False
    return entry.get("current", 0) >= max_c


# ---------- customer-scoped endpoints ----------

@customer_scoped.patch("/{customer_id}/assign", summary="分配 / 再分配客户")
def assign_customer(
    customer_id: int,
    body: AssignBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    new_uid = body.sales_user_id
    if new_uid is not None:
        target = db.query(SalesUser).filter(SalesUser.id == new_uid, SalesUser.is_active == True).first()  # noqa: E712
        if not target:
            raise HTTPException(400, "目标销售不存在或已停用")

    from_uid = customer.sales_user_id
    customer.sales_user_id = new_uid
    db.add(customer)
    log = LeadAssignmentLog(
        customer_id=customer.id,
        from_user_id=from_uid,
        to_user_id=new_uid,
        reason=body.reason,
        trigger="manual",
        operator_casdoor_id=getattr(user, "sub", None) if user else None,
    )
    db.add(log)
    db.commit()
    return {"ok": True, "customer_id": customer.id, "sales_user_id": new_uid, "log_id": log.id}


@customer_scoped.get("/{customer_id}/assignment-log", response_model=List[AssignmentLogOut],
                     summary="该客户的分配历史")
def get_assignment_log(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    return (
        db.query(LeadAssignmentLog)
        .filter(LeadAssignmentLog.customer_id == customer_id)
        .order_by(LeadAssignmentLog.id.desc())
        .all()
    )


# ---------- auto assignment ----------

@router.post("/auto-assign", response_model=AutoAssignResult, summary="对未分配客户自动跑规则分配")
def auto_assign(
    body: AutoAssignBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    rules = (
        db.query(LeadAssignmentRule)
        .filter(LeadAssignmentRule.is_active == True)  # noqa: E712
        .order_by(LeadAssignmentRule.priority.asc(), LeadAssignmentRule.id.asc())
        .all()
    )

    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if body.only_unassigned:
        q = q.filter(Customer.sales_user_id.is_(None))
    customers = q.all()

    # Build capacity map: {uid: {current, max}} for all sales users
    users = db.query(SalesUser).filter(SalesUser.is_active == True).all()  # noqa: E712
    count_rows = (
        db.query(Customer.sales_user_id, _sql_func.count(Customer.id))
        .filter(Customer.is_deleted == False)  # noqa: E712
        .filter(Customer.sales_user_id.isnot(None))
        .group_by(Customer.sales_user_id).all()
    )
    current_counts = {uid: n for uid, n in count_rows}
    capacity = {
        u.id: {"current": current_counts.get(u.id, 0), "max": u.max_customers}
        for u in users
    }

    results: List[AutoAssignItem] = []
    assigned_count = 0
    operator = getattr(user, "sub", None) if user else None

    for c in customers:
        matched = _match_rule(c, rules)
        if not matched:
            results.append(AutoAssignItem(
                customer_id=c.id, customer_code=c.customer_code,
                matched_rule_id=None, sales_user_id=None,
                reason="no rule matched",
            ))
            continue

        if body.dry_run:
            # For dry-run, peek the next assignee WITHOUT advancing the cursor;
            # also check capacity so the preview matches real behavior.
            ids = matched.sales_user_ids or []
            peek = None
            mode_note = ""
            if isinstance(ids, list) and ids:
                # peek first available non-capped from cursor position
                for off in range(len(ids)):
                    candidate = ids[((matched.cursor or 0) + off) % len(ids)]
                    if not _over_capacity(candidate, capacity):
                        peek = candidate; break
                mode_note = f"轮询[{len(ids)}]" + ("" if peek else " 全部超限")
            else:
                peek = matched.sales_user_id
                if peek and _over_capacity(peek, capacity):
                    mode_note = "单人超限"; peek = None
                else:
                    mode_note = "单人"
            results.append(AutoAssignItem(
                customer_id=c.id, customer_code=c.customer_code,
                matched_rule_id=matched.id, sales_user_id=peek,
                reason=f"(dry-run) via '{matched.name}' [{mode_note}]",
            ))
            continue

        target_uid = _pick_target_user(matched, capacity=capacity)
        if target_uid is None:
            results.append(AutoAssignItem(
                customer_id=c.id, customer_code=c.customer_code,
                matched_rule_id=matched.id, sales_user_id=None,
                reason=f"matched '{matched.name}' but all候选超容量",
            ))
            continue
        from_uid = c.sales_user_id
        c.sales_user_id = target_uid
        db.add(c); db.add(matched)  # matched may have mutated cursor
        db.add(LeadAssignmentLog(
            customer_id=c.id, from_user_id=from_uid, to_user_id=target_uid,
            reason=f"auto-assign via rule '{matched.name}'", trigger="auto",
            rule_id=matched.id, operator_casdoor_id=operator,
        ))
        assigned_count += 1
        # Update capacity map so next iteration sees this assignment
        if target_uid in capacity:
            capacity[target_uid]["current"] = capacity[target_uid].get("current", 0) + 1
        results.append(AutoAssignItem(
            customer_id=c.id, customer_code=c.customer_code,
            matched_rule_id=matched.id, sales_user_id=target_uid,
            reason=f"assigned via rule '{matched.name}'",
        ))

    if not body.dry_run and assigned_count:
        db.commit()

    return AutoAssignResult(
        total_scanned=len(customers),
        total_assigned=assigned_count,
        items=results,
        dry_run=body.dry_run,
    )


# ---------- expire-recycle ----------

@router.post("/auto-recycle", response_model=RecycleResult,
             summary="过期回收: 把超过 N 天没跟进的客户退回未分配池")
def auto_recycle(
    body: RecycleBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """扫描 sales_user_id 非空 + (last_follow_time 为空 或 < now - stale_days) 的客户,
    把 sales_user_id 置 null, 并在 lead_assignment_log 写 trigger=recycle 流水。
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=body.stale_days)
    operator = getattr(user, "sub", None) if user else None

    candidates = (
        db.query(Customer)
        .filter(Customer.is_deleted == False)  # noqa: E712
        .filter(Customer.sales_user_id.isnot(None))
        .filter((Customer.last_follow_time == None) | (Customer.last_follow_time < cutoff))  # noqa: E711
        .all()
    )

    items: List[RecycleItem] = []
    recycled = 0

    for c in candidates:
        reason = (
            f"超 {body.stale_days} 天未跟进 (last_follow_time="
            f"{c.last_follow_time.isoformat() if c.last_follow_time else '从未跟进'})"
        )
        items.append(RecycleItem(
            customer_id=c.id, customer_code=c.customer_code,
            from_user_id=c.sales_user_id,
            last_follow_time=c.last_follow_time, reason=reason,
        ))
        if body.dry_run:
            continue
        from_uid = c.sales_user_id
        c.sales_user_id = None
        db.add(c)
        db.add(LeadAssignmentLog(
            customer_id=c.id, from_user_id=from_uid, to_user_id=None,
            reason=reason, trigger="recycle", operator_casdoor_id=operator,
        ))
        recycled += 1

    if not body.dry_run and recycled:
        db.commit()

    return RecycleResult(
        total_scanned=len(candidates), total_recycled=recycled,
        stale_days=body.stale_days, dry_run=body.dry_run, items=items,
    )


# ---------- casdoor sync ----------

from pydantic import BaseModel as _BM


class CasdoorSyncBody(_BM):
    dry_run: bool = False


class CasdoorSyncItem(_BM):
    casdoor_user_id: str
    name: str
    email: Optional[str] = None
    action: str  # created | updated | unchanged | skipped


class CasdoorSyncResp(_BM):
    total_fetched: int
    created: int
    updated: int
    unchanged: int
    skipped: int
    items: List[CasdoorSyncItem]
    dry_run: bool


def _fetch_casdoor_users() -> List[dict]:
    """Pull members of the `sales` role from Casdoor and return their full user objects.

    Flow:
      1) GET /api/get-role?id={ORG}/sales  → role.users = ["built-in/admin", ...]
      2) For each "owner/name" ref, GET /api/get-user?id=owner/name  → full user dict

    Using client_credentials (basic auth with clientId + clientSecret).
    This scopes who becomes a SalesUser to exactly those assigned the sales
    role in Casdoor — rather than pulling everyone in an org.
    """
    import httpx
    from app.config import get_settings as _get
    s = _get()
    if not s.CASDOOR_ENDPOINT or not s.CASDOOR_CLIENT_ID or not s.CASDOOR_CLIENT_SECRET:
        raise HTTPException(400, "Casdoor 未配置完整 (endpoint/client_id/secret)")
    org = s.CASDOOR_ORG or "built-in"
    role_id = f"{org}/sales"

    with httpx.Client(timeout=30.0, auth=(s.CASDOOR_CLIENT_ID, s.CASDOOR_CLIENT_SECRET)) as c:
        rr = c.get(f"{s.CASDOOR_ENDPOINT}/api/get-role", params={"id": role_id})
        if rr.status_code >= 400:
            raise HTTPException(502, f"Casdoor get-role {rr.status_code}: {rr.text[:200]}")
        role_body = rr.json()
        role = role_body.get("data") if isinstance(role_body, dict) else role_body
        if not role or not isinstance(role, dict):
            raise HTTPException(400, f"Casdoor 没有 role {role_id}, 请先建角色 + 给用户 assign")
        user_refs = role.get("users") or []
        if not user_refs:
            return []

        users: List[dict] = []
        for ref in user_refs:
            # ref is "owner/name"
            ur = c.get(f"{s.CASDOOR_ENDPOINT}/api/get-user", params={"id": ref})
            if ur.status_code >= 400:
                logger.warning("Casdoor get-user %s failed: %s", ref, ur.status_code)
                continue
            ud = ur.json()
            u = ud.get("data") if isinstance(ud, dict) else ud
            if isinstance(u, dict) and u:
                users.append(u)
        return users


@router.post("/users/sync-from-casdoor", response_model=CasdoorSyncResp,
             summary="从 Casdoor 拉取用户并 upsert 成销售成员")
def sync_users_from_casdoor(
    body: CasdoorSyncBody,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    """对每个 Casdoor 用户: 以 casdoor_user_id 匹配:
       - 不存在 → 创建 (name/email 来自 Casdoor, 其他字段空, is_active=True)
       - 存在 → 更新 name/email, 保留手工字段 (regions, industries, max_customers, note)
       本地已存在的 SalesUser (casdoor_user_id 非空) 但 Casdoor 已没这个用户 → 停用。
    """
    fetched = _fetch_casdoor_users()
    items: List[CasdoorSyncItem] = []
    created = updated = unchanged = skipped = 0
    seen_ids: set[str] = set()

    for u in fetched:
        # Casdoor user object fields
        uid = (u.get("id") or "").strip()
        name = (u.get("displayName") or u.get("name") or "").strip()
        email = (u.get("email") or "").strip() or None
        is_admin = bool(u.get("isAdmin") or u.get("isGlobalAdmin"))
        is_forbidden = bool(u.get("isForbidden") or u.get("isDeleted"))

        if not uid or not name:
            skipped += 1
            items.append(CasdoorSyncItem(
                casdoor_user_id=uid or "-", name=name or "-",
                email=email, action="skipped",
            ))
            continue

        if is_forbidden:
            skipped += 1
            items.append(CasdoorSyncItem(
                casdoor_user_id=uid, name=name, email=email, action="skipped",
            ))
            continue

        seen_ids.add(uid)
        existing = db.query(SalesUser).filter(SalesUser.casdoor_user_id == uid).first()
        if existing:
            changed = False
            if existing.name != name:
                existing.name = name; changed = True
            if (existing.email or None) != email:
                existing.email = email; changed = True
            if not existing.is_active:
                existing.is_active = True; changed = True
            if changed:
                if not body.dry_run:
                    db.add(existing)
                updated += 1
                items.append(CasdoorSyncItem(
                    casdoor_user_id=uid, name=name, email=email, action="updated",
                ))
            else:
                unchanged += 1
                items.append(CasdoorSyncItem(
                    casdoor_user_id=uid, name=name, email=email, action="unchanged",
                ))
        else:
            if not body.dry_run:
                db.add(SalesUser(
                    name=name, email=email, casdoor_user_id=uid,
                    is_active=True,
                    note=("(来自 Casdoor, admin=true)" if is_admin else "(来自 Casdoor)"),
                ))
            created += 1
            items.append(CasdoorSyncItem(
                casdoor_user_id=uid, name=name, email=email, action="created",
            ))

    # Deactivate local Casdoor-linked users who disappeared from Casdoor
    if seen_ids and not body.dry_run:
        locals_ = db.query(SalesUser).filter(
            SalesUser.casdoor_user_id.isnot(None),
            SalesUser.is_active == True,  # noqa: E712
        ).all()
        for u in locals_:
            if u.casdoor_user_id not in seen_ids:
                u.is_active = False
                db.add(u)
                items.append(CasdoorSyncItem(
                    casdoor_user_id=u.casdoor_user_id, name=u.name, email=u.email,
                    action="skipped",  # treated like skipped since gone upstream
                ))
                skipped += 1

    if not body.dry_run:
        db.commit()

    return CasdoorSyncResp(
        total_fetched=len(fetched),
        created=created, updated=updated, unchanged=unchanged, skipped=skipped,
        items=items, dry_run=body.dry_run,
    )


# ---------- recent activity stream ----------

@router.get("/activity/recent", response_model=List[ActivityItem],
            summary="最近活动流: 跟进 + 分配 + AI 洞察 混合时序")
def recent_activity(
    limit: int = 20,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    """Aggregate last N events across follow-ups, assignment logs, and insight
    runs. Simple server-side union + in-memory sort; cheap enough for a
    dashboard widget. For high traffic we'd move to a materialized view.
    """
    from app.models.customer_insight import CustomerInsightRun
    from app.models.follow_up import CustomerFollowUp

    fus = (
        db.query(CustomerFollowUp, Customer.customer_name)
        .join(Customer, Customer.id == CustomerFollowUp.customer_id)
        .order_by(CustomerFollowUp.id.desc()).limit(limit).all()
    )
    logs = (
        db.query(LeadAssignmentLog, Customer.customer_name)
        .join(Customer, Customer.id == LeadAssignmentLog.customer_id)
        .order_by(LeadAssignmentLog.id.desc()).limit(limit).all()
    )
    runs = (
        db.query(CustomerInsightRun, Customer.customer_name)
        .join(Customer, Customer.id == CustomerInsightRun.customer_id)
        .order_by(CustomerInsightRun.id.desc()).limit(limit).all()
    )

    merged: List[ActivityItem] = []
    for fu, cname in fus:
        merged.append(ActivityItem(
            kind="follow_up",
            at=(fu.created_at.isoformat() if fu.created_at else ""),
            customer_id=fu.customer_id, customer_name=cname,
            title=f"[{fu.kind}] {fu.title}",
            detail=(fu.content or "")[:200] if fu.content else None,
        ))
    for log, cname in logs:
        merged.append(ActivityItem(
            kind="assignment",
            at=(log.at.isoformat() if log.at else ""),
            customer_id=log.customer_id, customer_name=cname,
            title=f"{log.trigger}: {log.from_user_id or '-'} → {log.to_user_id or '退池'}",
            detail=log.reason,
        ))
    for run, cname in runs:
        merged.append(ActivityItem(
            kind="insight_run",
            at=(run.started_at.isoformat() if run.started_at else ""),
            customer_id=run.customer_id, customer_name=cname,
            title=f"AI 洞察运行 #{run.id} ({run.status}) 步数 {run.steps_done}/{run.steps_total}",
            detail=(run.summary or "")[:200] if run.summary else None,
        ))

    merged.sort(key=lambda x: x.at, reverse=True)
    return merged[:limit]
