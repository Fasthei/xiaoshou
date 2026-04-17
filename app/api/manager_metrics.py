"""主管 dashboard 指标 + 漏斗 + 异常告警 (基于 lifecycle_stage)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_stage_request import CustomerStageRequest
from app.models.follow_up import CustomerFollowUp
from app.models.payment import Payment
from app.models.sales import SalesUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metrics", tags=["主管指标"])

STAGES = ("lead", "contacting", "active", "lost")

# 卡 stage 过久阈值 (天)
STAGE_STUCK_THRESHOLDS = {
    "contacting": 14,
}


def _current_month_str() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    y, m = int(month[:4]), int(month[5:7])
    start = datetime(y, m, 1)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return start, datetime(ny, nm, 1)


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{py:04d}-{pm:02d}"


@router.get("/dashboard", summary="主管核心 5 大指标")
def dashboard(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    m = month or _current_month_str()
    start, end = _month_bounds(m)
    prev_start, prev_end = _month_bounds(_prev_month(m))

    base = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712

    # 1. new_opportunities — 本月 new customer 且 stage 已脱离 lead
    try:
        new_opps = base.filter(
            Customer.created_at >= start,
            Customer.created_at < end,
            Customer.lifecycle_stage.in_(("contacting", "active")),
        ).count()
    except Exception as e:
        logger.warning("new_opportunities failed: %s", e)
        new_opps = 0

    # 2. conversion_rate — 有 active 进度 / 总 leads
    try:
        total_leads = base.filter(Customer.lifecycle_stage == "lead").count()
        total_active_progress = base.filter(
            Customer.lifecycle_stage.in_(("contacting", "active"))
        ).count()
        denom = total_leads + total_active_progress
        conversion_rate = (total_active_progress / denom) if denom > 0 else 0.0
    except Exception as e:
        logger.warning("conversion_rate failed: %s", e)
        conversion_rate = 0.0

    # 3. deal_rate — 过去 30 天 active / (contacting+active) (累积)
    try:
        window = datetime.utcnow() - timedelta(days=30)
        active_recent = base.filter(
            Customer.lifecycle_stage == "active",
            Customer.updated_at >= window,
        ).count()
        contacting_recent = base.filter(
            Customer.lifecycle_stage == "contacting",
            Customer.updated_at >= window,
        ).count()
        deal_denom = active_recent + contacting_recent
        deal_rate = (active_recent / deal_denom) if deal_denom > 0 else 0.0
    except Exception as e:
        logger.warning("deal_rate failed: %s", e)
        deal_rate = 0.0

    # 4. growth_rate — (本月 active - 上月 active) / 上月 active
    try:
        this_active = base.filter(
            Customer.lifecycle_stage == "active",
            Customer.updated_at >= start,
            Customer.updated_at < end,
        ).count()
        prev_active = base.filter(
            Customer.lifecycle_stage == "active",
            Customer.updated_at >= prev_start,
            Customer.updated_at < prev_end,
        ).count()
        growth_rate = ((this_active - prev_active) / prev_active) if prev_active > 0 else 0.0
    except Exception as e:
        logger.warning("growth_rate failed: %s", e)
        growth_rate = 0.0

    # 5. collection_rate — sum(已收款) / sum(合同金额)
    try:
        received_sum = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
            Payment.status == "received"
        ).scalar() or Decimal("0")
        contract_sum = db.query(func.coalesce(func.sum(Contract.amount), 0)).filter(
            Contract.status == "active"
        ).scalar() or Decimal("0")
        collection_rate = (float(received_sum) / float(contract_sum)) if float(contract_sum) > 0 else 0.0
    except Exception as e:
        logger.warning("collection_rate failed: %s", e)
        collection_rate = 0.0

    return {
        "month": m,
        "new_opportunities": int(new_opps),
        "conversion_rate": float(conversion_rate),
        "deal_rate": float(deal_rate),
        "growth_rate": float(growth_rate),
        "collection_rate": float(collection_rate),
    }


@router.get("/team-profit", summary="销售团队年度销售额 / 利润 / 利润率 聚合")
def team_profit(
    year: Optional[int] = Query(None, description="目标年份, 默认当前年"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    """聚合全团队 (active sales) 的年度目标和已完成:
    - 目标: sum(sales_user.annual_sales_target/annual_profit_target)
    - 已完成: 聚合当年 allocation (total_price / profit_amount), 以销售名下客户为界
    - 利润率目标 / 实际 由上述派生
    """
    from app.models.customer import Customer as _C

    now_year = year or datetime.utcnow().year
    # 目标聚合 (仅 active 销售)
    t_row = (
        db.query(
            func.coalesce(func.sum(SalesUser.annual_sales_target), 0),
            func.coalesce(func.sum(SalesUser.annual_profit_target), 0),
        )
        .filter(SalesUser.is_active == True)  # noqa: E712
        .one()
    )
    team_sales_target = float(t_row[0] or 0)
    team_profit_target = float(t_row[1] or 0)

    # 已完成聚合: 本年所有 active 销售名下客户的 allocation
    try:
        active_ids = [u.id for u in db.query(SalesUser.id).filter(SalesUser.is_active == True).all()]  # noqa: E712
        if active_ids:
            a_row = (
                db.query(
                    func.coalesce(func.sum(Allocation.total_price), 0),
                    func.coalesce(func.sum(Allocation.profit_amount), 0),
                )
                .join(_C, _C.id == Allocation.customer_id)
                .filter(_C.sales_user_id.in_(active_ids))
                .filter(Allocation.is_deleted == False)  # noqa: E712
                .filter(
                    func.coalesce(
                        func.extract("year", Allocation.allocated_at),
                        func.extract("year", Allocation.created_at),
                    ) == now_year
                )
                .one()
            )
            team_sales_achieved = float(a_row[0] or 0)
            team_profit_achieved = float(a_row[1] or 0)
        else:
            team_sales_achieved = 0.0
            team_profit_achieved = 0.0
    except Exception as e:
        logger.warning("team_profit achieved aggregation failed: %s", e)
        team_sales_achieved = 0.0
        team_profit_achieved = 0.0

    rate_target = (team_profit_target / team_sales_target) if team_sales_target > 0 else 0.0
    rate_actual = (team_profit_achieved / team_sales_achieved) if team_sales_achieved > 0 else 0.0

    return {
        "year": now_year,
        "team_annual_sales_target": team_sales_target,
        "team_annual_sales_achieved": team_sales_achieved,
        "team_annual_profit_target": team_profit_target,
        "team_annual_profit_achieved": team_profit_achieved,
        "team_profit_rate_target": rate_target,
        "team_profit_rate_actual": rate_actual,
    }


@router.get("/team-funnel", summary="每个销售的 stage 漏斗")
def team_funnel(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> List[dict[str, Any]]:
    try:
        sales = db.query(SalesUser).filter(SalesUser.is_active == True).all()  # noqa: E712
    except Exception as e:
        logger.warning("team_funnel load sales failed: %s", e)
        return []

    rows = (
        db.query(Customer.sales_user_id, Customer.lifecycle_stage, func.count(Customer.id))
        .filter(
            Customer.is_deleted == False,  # noqa: E712
            Customer.sales_user_id.isnot(None),
        )
        .group_by(Customer.sales_user_id, Customer.lifecycle_stage)
        .all()
    )
    agg: dict[int, dict[str, int]] = {}
    for sid, stage, cnt in rows:
        if sid is None:
            continue
        bucket = agg.setdefault(int(sid), {s: 0 for s in STAGES})
        if stage in bucket:
            bucket[stage] = int(cnt)

    out: List[dict[str, Any]] = []
    for s in sales:
        sid = int(s.id)
        out.append({
            "sales_user_id": sid,
            "name": s.name,
            "stages": agg.get(sid, {st: 0 for st in STAGES}),
        })
    return out


@router.get("/stage-alerts", summary="卡在 stage 过久的客户告警")
def stage_alerts(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> List[dict[str, Any]]:
    now = datetime.utcnow()

    # 找每个 customer 最近一次进入当前 stage 的时间:
    # 用 customer_stage_request 里 status='approved' AND to_stage=customer.lifecycle_stage 的最新一条。
    # 若无, 退回到 customer.updated_at 作为 stage 进入时间近似。
    alerts: List[dict[str, Any]] = []
    customers = db.query(Customer).filter(
        Customer.is_deleted == False,  # noqa: E712
        Customer.lifecycle_stage.in_(tuple(STAGE_STUCK_THRESHOLDS.keys())),
    ).all()

    for c in customers:
        threshold = STAGE_STUCK_THRESHOLDS.get(c.lifecycle_stage)
        if not threshold:
            continue
        last_req = (
            db.query(CustomerStageRequest)
            .filter(
                CustomerStageRequest.customer_id == c.id,
                CustomerStageRequest.status == "approved",
                CustomerStageRequest.to_stage == c.lifecycle_stage,
            )
            .order_by(CustomerStageRequest.id.desc())
            .first()
        )
        entered = last_req.decided_at if last_req and last_req.decided_at else c.updated_at or c.created_at
        if not entered:
            continue
        days_stuck = (now - entered).days
        if days_stuck >= threshold:
            alerts.append({
                "customer_id": c.id,
                "customer_name": c.customer_name,
                "stage": c.lifecycle_stage,
                "days_stuck": days_stuck,
                "threshold": threshold,
            })
    alerts.sort(key=lambda x: x["days_stuck"], reverse=True)
    return alerts


# ---------- 销售个人视图 ----------

def _resolve_my_sales_user(db: Session, user: CurrentUser) -> Optional[SalesUser]:
    """通过 casdoor_user_id (sub) 找到当前登录用户对应的本地 SalesUser。
    找不到返回 None (上游 endpoint 会退化成 mock 数据, 保证前端永远能渲染)。
    """
    sub = getattr(user, "sub", None)
    if not sub:
        return None
    return db.query(SalesUser).filter(SalesUser.casdoor_user_id == sub).first()


@router.get("/my-kpi", summary="当前销售个人 KPI: 年度目标达成 + 本月指标")
def my_kpi(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    su = _resolve_my_sales_user(db, user)
    now = datetime.utcnow()
    year = now.year
    month_start, month_end = _month_bounds(_current_month_str())

    if su is None:
        # 未绑定本地 sales_user → 返回 mock/空数据, 让前端渲染占位态
        return {
            "sales_user_id": None,
            "sales_user_name": user.name or "未知销售",
            "target_year": year,
            "annual_target": 0,
            "ytd_achievement": 0,
            "progress_pct": 0.0,
            "gap": 0,
            "month": _current_month_str(),
            "month_new_opportunities": 0,
            "month_follow_ups": 0,
            "month_deals": 0,
            "month_signed_amount": 0,
            "unbound": True,
        }

    target_year = su.target_year or year
    annual_target = float(su.annual_profit_target) if su.annual_profit_target else 0.0

    # YTD 毛利 (年度)
    from decimal import Decimal as _D
    ytd_row = (
        db.query(func.coalesce(func.sum(Allocation.profit_amount), 0))
        .join(Customer, Customer.id == Allocation.customer_id)
        .filter(Customer.sales_user_id == su.id)
        .filter(Allocation.is_deleted == False)  # noqa: E712
        .filter(
            func.coalesce(
                func.extract("year", Allocation.allocated_at),
                func.extract("year", Allocation.created_at),
            ) == target_year
        )
        .scalar()
    )
    ytd = float(ytd_row or 0)
    progress_pct = round(ytd * 100.0 / annual_target, 2) if annual_target > 0 else 0.0
    gap = max(0.0, annual_target - ytd)

    # 本月: 新增商机 (new customer assigned to me this month AND stage != lead)
    try:
        month_new_opps = (
            db.query(Customer)
            .filter(Customer.is_deleted == False)  # noqa: E712
            .filter(Customer.sales_user_id == su.id)
            .filter(Customer.created_at >= month_start, Customer.created_at < month_end)
            .count()
        )
    except Exception as e:
        logger.warning("my-kpi month_new_opps failed: %s", e)
        month_new_opps = 0

    # 本月: 跟进次数
    try:
        month_fu = (
            db.query(CustomerFollowUp)
            .join(Customer, Customer.id == CustomerFollowUp.customer_id)
            .filter(Customer.sales_user_id == su.id)
            .filter(CustomerFollowUp.created_at >= month_start, CustomerFollowUp.created_at < month_end)
            .count()
        )
    except Exception as e:
        logger.warning("my-kpi month_fu failed: %s", e)
        month_fu = 0

    # 本月: 成单数 + 签约金额 (allocation where allocated_at in month, approved)
    try:
        month_alloc_rows = (
            db.query(
                func.count(Allocation.id),
                func.coalesce(func.sum(Allocation.amount), 0),
            )
            .join(Customer, Customer.id == Allocation.customer_id)
            .filter(Customer.sales_user_id == su.id)
            .filter(Allocation.is_deleted == False)  # noqa: E712
            .filter(
                func.coalesce(Allocation.allocated_at, Allocation.created_at) >= month_start,
                func.coalesce(Allocation.allocated_at, Allocation.created_at) < month_end,
            )
            .one()
        )
        month_deals = int(month_alloc_rows[0] or 0)
        month_signed = float(month_alloc_rows[1] or 0)
    except Exception as e:
        logger.warning("my-kpi month_alloc failed: %s", e)
        month_deals = 0
        month_signed = 0.0

    return {
        "sales_user_id": su.id,
        "sales_user_name": su.name,
        "target_year": target_year,
        "annual_target": annual_target,
        "ytd_achievement": ytd,
        "progress_pct": progress_pct,
        "gap": gap,
        "month": _current_month_str(),
        "month_new_opportunities": month_new_opps,
        "month_follow_ups": month_fu,
        "month_deals": month_deals,
        "month_signed_amount": month_signed,
        "unbound": False,
    }


@router.get("/my-todos", summary="当前销售代办: 到期跟进 + 长期冷落客户")
def my_todos(
    stale_days: int = Query(14, ge=1, le=180, description="多少天没跟进算冷落"),
    upcoming_days: int = Query(7, ge=1, le=60, description="未来 N 天到期的 next_action"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    su = _resolve_my_sales_user(db, user)
    if su is None:
        return {"unbound": True, "due": [], "stale": []}

    now = datetime.utcnow()
    upcoming_cutoff = now + timedelta(days=upcoming_days)
    stale_cutoff = now - timedelta(days=stale_days)

    # 到期跟进: 该销售名下的客户的最新一条 follow_up 的 next_action_at 在未来 N 天内
    # (或已经过期但未完成)
    due_items: List[dict[str, Any]] = []
    try:
        # Subquery: latest follow_up per customer
        from sqlalchemy import and_ as _and
        latest_fu_sq = (
            db.query(
                CustomerFollowUp.customer_id.label("cid"),
                func.max(CustomerFollowUp.id).label("max_id"),
            )
            .group_by(CustomerFollowUp.customer_id)
            .subquery()
        )
        rows = (
            db.query(CustomerFollowUp, Customer)
            .join(latest_fu_sq, _and(
                latest_fu_sq.c.cid == CustomerFollowUp.customer_id,
                latest_fu_sq.c.max_id == CustomerFollowUp.id,
            ))
            .join(Customer, Customer.id == CustomerFollowUp.customer_id)
            .filter(Customer.sales_user_id == su.id)
            .filter(Customer.is_deleted == False)  # noqa: E712
            .filter(CustomerFollowUp.next_action_at.isnot(None))
            .filter(CustomerFollowUp.next_action_at <= upcoming_cutoff)
            .order_by(CustomerFollowUp.next_action_at.asc())
            .limit(50)
            .all()
        )
        for fu, c in rows:
            due_items.append({
                "customer_id": c.id,
                "customer_code": c.customer_code,
                "customer_name": c.customer_name,
                "last_follow_at": fu.created_at.isoformat() if fu.created_at else None,
                "last_follow_title": fu.title,
                "next_action_at": fu.next_action_at.isoformat() if fu.next_action_at else None,
                "next_action_hint": (fu.content or "")[:80] if fu.content else None,
                "overdue": fu.next_action_at < now if fu.next_action_at else False,
            })
    except Exception as e:
        logger.warning("my-todos due failed: %s", e)

    # 长期冷落: 名下客户 last_follow_time < stale_cutoff (或为空)
    stale_items: List[dict[str, Any]] = []
    try:
        cs = (
            db.query(Customer)
            .filter(Customer.is_deleted == False)  # noqa: E712
            .filter(Customer.sales_user_id == su.id)
            .filter(
                (Customer.last_follow_time == None)  # noqa: E711
                | (Customer.last_follow_time < stale_cutoff)
            )
            .order_by(Customer.last_follow_time.asc())
            .limit(50)
            .all()
        )
        for c in cs:
            days_since = None
            if c.last_follow_time:
                days_since = (now - c.last_follow_time).days
            stale_items.append({
                "customer_id": c.id,
                "customer_code": c.customer_code,
                "customer_name": c.customer_name,
                "last_follow_at": c.last_follow_time.isoformat() if c.last_follow_time else None,
                "days_since_follow": days_since,
            })
    except Exception as e:
        logger.warning("my-todos stale failed: %s", e)

    return {
        "unbound": False,
        "sales_user_id": su.id,
        "sales_user_name": su.name,
        "stale_days": stale_days,
        "upcoming_days": upcoming_days,
        "due": due_items,
        "stale": stale_items,
    }
