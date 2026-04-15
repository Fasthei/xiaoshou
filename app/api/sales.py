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
    AssignBody, AssignmentLogOut, AutoAssignBody, AutoAssignItem, AutoAssignResult,
    RecycleBody, RecycleItem, RecycleResult,
    RuleCreate, RuleOut, RuleUpdate,
    SalesUserCreate, SalesUserOut, SalesUserUpdate,
)

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


def _pick_target_user(rule: LeadAssignmentRule) -> Optional[int]:
    """Given a matched rule, pick the sales_user_id to assign to.
    If round-robin (sales_user_ids non-empty), use cursor and increment it.
    Otherwise fall back to rule.sales_user_id.
    Caller is responsible for committing the cursor mutation.
    """
    ids = rule.sales_user_ids or []
    if isinstance(ids, list) and len(ids) > 0:
        idx = (rule.cursor or 0) % len(ids)
        uid = ids[idx]
        rule.cursor = (rule.cursor or 0) + 1
        return uid
    return rule.sales_user_id


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
            # For dry-run, peek at the next assignee WITHOUT advancing the cursor
            ids = matched.sales_user_ids or []
            if isinstance(ids, list) and ids:
                peek = ids[(matched.cursor or 0) % len(ids)]
                mode = f"轮询候选[{len(ids)}] cursor={matched.cursor}"
            else:
                peek = matched.sales_user_id
                mode = "单人"
            results.append(AutoAssignItem(
                customer_id=c.id, customer_code=c.customer_code,
                matched_rule_id=matched.id, sales_user_id=peek,
                reason=f"(dry-run) via '{matched.name}' [{mode}]",
            ))
            continue

        target_uid = _pick_target_user(matched)
        from_uid = c.sales_user_id
        c.sales_user_id = target_uid
        db.add(c); db.add(matched)  # matched may have mutated cursor
        db.add(LeadAssignmentLog(
            customer_id=c.id, from_user_id=from_uid, to_user_id=target_uid,
            reason=f"auto-assign via rule '{matched.name}'", trigger="auto",
            rule_id=matched.id, operator_casdoor_id=operator,
        ))
        assigned_count += 1
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
