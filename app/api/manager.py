"""销售主管 dashboard KPI endpoints.

/api/manager/kpis              — 商机 / 转化率 / 增长率 / 回款率
/api/manager/sales-performance — 每名销售的进度卡片
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.cc_bill import CCBill
from app.models.customer import Customer
from app.models.sales import SalesUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/manager", tags=["销售主管 dashboard"])


# ---------- helpers ----------

def _current_month_str() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """Given YYYY-MM, return [start_of_month, start_of_next_month) as datetimes."""
    y, m = int(month[:4]), int(month[5:7])
    start = datetime(y, m, 1)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    end = datetime(ny, nm, 1)
    return start, end


def _prev_month(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
    return f"{py:04d}-{pm:02d}"


def _approved_gmv_for_month(db: Session, month: str) -> Decimal:
    """Sum allocation.total_price where allocated_at falls in month AND approval_status=approved.

    Uses getattr-based column check so this degrades gracefully if the
    approval_status column does not yet exist (feature in parallel development).
    """
    start, end = _month_bounds(month)
    try:
        # Probe column existence: Allocation.approval_status as SQLA attr
        has_col = hasattr(Allocation, "approval_status")
        q = db.query(Allocation).filter(
            Allocation.is_deleted == False,  # noqa: E712
            Allocation.allocated_at >= start,
            Allocation.allocated_at < end,
        )
        if has_col:
            q = q.filter(getattr(Allocation, "approval_status") == "approved")
        rows = q.all()
    except Exception as e:
        logger.warning("approved GMV query failed (%s) — returning 0", e)
        return Decimal("0")

    total = Decimal("0")
    for a in rows:
        v = getattr(a, "total_price", None)
        if v is None:
            continue
        try:
            total += Decimal(str(v))
        except Exception:
            continue
    return total


def _approved_gmv_ytd(db: Session, year: int) -> dict[int, Decimal]:
    """Year-to-date GMV grouped by sales_user_id (via customer.sales_user_id).

    Returns {sales_user_id: Decimal}.
    """
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)
    out: dict[int, Decimal] = {}
    try:
        has_col = hasattr(Allocation, "approval_status")
        q = (
            db.query(Allocation, Customer.sales_user_id)
            .join(Customer, Customer.id == Allocation.customer_id)
            .filter(
                Allocation.is_deleted == False,  # noqa: E712
                Allocation.allocated_at >= start,
                Allocation.allocated_at < end,
            )
        )
        if has_col:
            q = q.filter(getattr(Allocation, "approval_status") == "approved")
        for a, sid in q.all():
            if sid is None:
                continue
            v = getattr(a, "total_price", None)
            if v is None:
                continue
            try:
                out[int(sid)] = out.get(int(sid), Decimal("0")) + Decimal(str(v))
            except Exception:
                continue
    except Exception as e:
        logger.warning("YTD GMV by sales failed (%s) — returning empty map", e)
    return out


# ---------- KPIs ----------

@router.get("/kpis", summary="销售主管仪表盘 4 大 KPI")
def get_manager_kpis(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    m = month or _current_month_str()
    start, end = _month_bounds(m)

    # 1. opportunities — 本月新建的 active 客户数
    try:
        opportunities = (
            db.query(func.count(Customer.id))
            .filter(
                Customer.is_deleted == False,  # noqa: E712
                Customer.customer_status == "active",
                Customer.created_at >= start,
                Customer.created_at < end,
            )
            .scalar()
            or 0
        )
    except Exception as e:
        logger.warning("opportunities count failed: %s", e)
        opportunities = 0

    # 2. conversion_rate — 近 90 天: count(active) / count(active+potential+inactive)
    try:
        window_start = datetime.utcnow() - timedelta(days=90)
        recent = db.query(Customer).filter(
            Customer.is_deleted == False,  # noqa: E712
            Customer.created_at >= window_start,
        ).all()
        denom = sum(
            1 for c in recent
            if (c.customer_status or "") in ("active", "potential", "inactive")
        )
        numer = sum(1 for c in recent if (c.customer_status or "") == "active")
        conversion_rate = (numer / denom) if denom > 0 else 0.0
    except Exception as e:
        logger.warning("conversion_rate calc failed: %s", e)
        conversion_rate = 0.0

    # 3. growth_rate — 本月 GMV / 上月 GMV - 1
    this_gmv = _approved_gmv_for_month(db, m)
    prev_gmv = _approved_gmv_for_month(db, _prev_month(m))
    if prev_gmv and prev_gmv > 0:
        try:
            growth_rate = float(this_gmv / prev_gmv) - 1.0
        except Exception:
            growth_rate = 0.0
    else:
        growth_rate = 0.0

    # 4. payment_rate — 本月 paid 账单数 / confirmed+paid 账单数 (confirmed 指已确认的)
    try:
        paid_cnt = (
            db.query(func.count(CCBill.id))
            .filter(CCBill.month == m, CCBill.status == "paid")
            .scalar()
            or 0
        )
        confirmed_cnt = (
            db.query(func.count(CCBill.id))
            .filter(CCBill.month == m, CCBill.status.in_(["confirmed", "paid"]))
            .scalar()
            or 0
        )
        payment_rate = (paid_cnt / confirmed_cnt) if confirmed_cnt > 0 else 0.0
    except Exception as e:
        logger.warning("payment_rate calc failed: %s", e)
        payment_rate = 0.0

    return {
        "month": m,
        "opportunities": int(opportunities),
        "conversion_rate": float(conversion_rate),
        "growth_rate": float(growth_rate),
        "payment_rate": float(payment_rate),
    }


# ---------- sales-performance ----------

@router.get("/sales-performance", summary="销售业绩进度卡片")
def get_sales_performance(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> List[dict[str, Any]]:
    m = month or _current_month_str()
    year = int(m[:4])

    try:
        sales = db.query(SalesUser).filter(SalesUser.is_active == True).all()  # noqa: E712
    except Exception as e:
        logger.warning("load sales list failed: %s", e)
        return []

    # customer_count per sales_user (active + not deleted)
    customer_counts: dict[int, int] = {}
    try:
        rows = (
            db.query(Customer.sales_user_id, func.count(Customer.id))
            .filter(
                Customer.is_deleted == False,  # noqa: E712
                Customer.sales_user_id.isnot(None),
            )
            .group_by(Customer.sales_user_id)
            .all()
        )
        customer_counts = {int(sid): int(cnt) for sid, cnt in rows if sid is not None}
    except Exception as e:
        logger.warning("customer_count group failed: %s", e)

    ytd_map = _approved_gmv_ytd(db, year)

    out: List[dict[str, Any]] = []
    for s in sales:
        sid = int(s.id)
        ytd_gmv = ytd_map.get(sid, Decimal("0"))
        target = s.annual_profit_target
        try:
            target_dec = Decimal(str(target)) if target is not None else Decimal("0")
        except Exception:
            target_dec = Decimal("0")
        if target_dec > 0:
            progress_pct = float(ytd_gmv / target_dec) * 100.0
        else:
            progress_pct = 0.0

        out.append({
            "id": sid,
            "name": s.name,
            "customer_count": customer_counts.get(sid, 0),
            "ytd_gmv": float(ytd_gmv),
            "target_gmv": float(target_dec),
            "progress_pct": progress_pct,
        })

    return out
