"""复杂报表 / BI 后端 — /api/reports/*

5 个 endpoint，全部 require_roles('sales-manager', 'admin')。
不引入 pandas / numpy，纯 SQLAlchemy 聚合 + Python 切片。
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.customer_stage_request import CustomerStageRequest
from app.models.sales import SalesUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["报表BI"])

# 角色守卫 dependency
_manager_dep = Depends(require_roles("sales-manager", "admin"))


# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────

def _parse_date(d: Optional[str], *, end_inclusive: bool = False) -> Optional[datetime]:
    """'YYYY-MM-DD' 或 'YYYY-MM' → datetime; None → None.

    当输入形如 'YYYY-MM' 且 end_inclusive=True 时，返回下个月 1 日（作为闭区间
    右端 → 开区间右端）。这样前端传 start=2025-11 end=2026-04 被正确解读为
    "2025-11-01 ≤ t < 2026-05-01"，即 11 月到 4 月的整月区间。
    """
    if not d:
        return None
    # YYYY-MM-DD 精确
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        pass
    # YYYY-MM 月粒度
    try:
        dt = datetime.strptime(d, "%Y-%m")
    except ValueError:
        return None
    if end_inclusive:
        if dt.month == 12:
            return datetime(dt.year + 1, 1, 1)
        return datetime(dt.year, dt.month + 1, 1)
    return dt


def _to_month_label(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _profit_rate(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return round((price - cost) / price * 100, 2)


# ──────────────────────────────────────────────
# 1. sales-trend
# ──────────────────────────────────────────────

@router.get("/sales-trend", summary="销售趋势聚合")
def sales_trend(
    dim: Optional[str] = Query(None, description="month | customer | sales | region | industry"),
    dimension: Optional[str] = Query(None, description="同 dim (前端别名)"),
    from_: Optional[str] = Query(None, alias="from", description="起始日期 YYYY-MM-DD 或 YYYY-MM"),
    to: Optional[str] = Query(None, description="截止日期 YYYY-MM-DD 或 YYYY-MM"),
    start: Optional[str] = Query(None, description="同 from (前端别名)"),
    end: Optional[str] = Query(None, description="同 to (前端别名)"),
    db: Session = Depends(get_db),
    _=_manager_dep,
) -> List[dict]:
    # 别名映射：前端传 dimension/start/end，后端原来叫 dim/from/to
    dim = (dim or dimension or "month")
    from_ = from_ or start
    to = to or end
    """按不同维度聚合 allocation 的销售额 / 利润 / 笔数。"""
    from_dt = _parse_date(from_)
    to_dt = _parse_date(to, end_inclusive=True)

    q = (
        db.query(Allocation)
        .join(Customer, Customer.id == Allocation.customer_id)
        .filter(Allocation.is_deleted == False)  # noqa: E712
        .filter(Customer.is_deleted == False)  # noqa: E712
    )
    if from_dt:
        q = q.filter(
            func.coalesce(Allocation.allocated_at, Allocation.created_at) >= from_dt
        )
    if to_dt:
        q = q.filter(
            func.coalesce(Allocation.allocated_at, Allocation.created_at) < to_dt
        )

    rows: List[Allocation] = q.all()

    # 按 dim 分桶
    buckets: dict[str, dict] = {}

    for alloc in rows:
        cust = alloc.customer
        if dim == "month":
            ref = alloc.allocated_at or alloc.created_at
            label = _to_month_label(ref) if ref else "未知"
        elif dim == "customer":
            label = cust.customer_name if cust else "未知"
        elif dim == "sales":
            # sales_user_id → name via SalesUser lookup cached lazily
            label = str(cust.sales_user_id) if cust and cust.sales_user_id else "未分配"
        elif dim == "region":
            label = (cust.region or "未知") if cust else "未知"
        elif dim == "industry":
            label = (cust.industry or "未知") if cust else "未知"
        else:
            label = "未知"

        if label not in buckets:
            buckets[label] = {"label": label, "total_sales": 0.0, "total_profit": 0.0, "count": 0}
        b = buckets[label]
        b["total_sales"] += _safe_float(alloc.total_price)
        b["total_profit"] += _safe_float(alloc.profit_amount)
        b["count"] += 1

    # If dim=sales, resolve sales_user names
    if dim == "sales":
        raw_ids = set()
        for k in list(buckets.keys()):
            try:
                raw_ids.add(int(k))
            except (ValueError, TypeError):
                pass
        if raw_ids:
            users = db.query(SalesUser).filter(SalesUser.id.in_(list(raw_ids))).all()
            id_to_name = {str(u.id): u.name for u in users}
            new_buckets: dict[str, dict] = {}
            for k, v in buckets.items():
                resolved = id_to_name.get(k, k)
                if resolved not in new_buckets:
                    new_buckets[resolved] = {**v, "label": resolved}
                else:
                    new_buckets[resolved]["total_sales"] += v["total_sales"]
                    new_buckets[resolved]["total_profit"] += v["total_profit"]
                    new_buckets[resolved]["count"] += v["count"]
            buckets = new_buckets

    result = sorted(buckets.values(), key=lambda x: x["label"])
    for r in result:
        r["total_sales"] = round(r["total_sales"], 2)
        r["total_profit"] = round(r["total_profit"], 2)
        # 兼容前端字段
        r["period"] = r["label"]
        r["revenue"] = r["total_sales"]
        r["orders"] = r["count"]
        r["customers"] = r["count"]  # sales-trend 按维度聚合，没拆客户独立数；暂用 orders
    return result


# ──────────────────────────────────────────────
# 2. profit-analysis
# ──────────────────────────────────────────────

@router.get("/profit-analysis", summary="利润分析（多维度拆解）")
def profit_analysis(
    dim: Optional[str] = Query(None, description="month | customer | sales | region | industry"),
    dimension: Optional[str] = Query(None, description="同 dim (前端别名)"),
    breakdown: Optional[str] = Query(None, description="customer_level | industry"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    start: Optional[str] = Query(None, description="同 from (前端别名)"),
    end: Optional[str] = Query(None, description="同 to (前端别名)"),
    db: Session = Depends(get_db),
    _=_manager_dep,
) -> List[dict]:
    dim = (dim or dimension or "month")
    from_ = from_ or start
    to = to or end
    """按主维度 + 拆解维度的双层聚合，返回成本 / 售价 / 利润 / 利润率。"""
    from_dt = _parse_date(from_)
    to_dt = _parse_date(to, end_inclusive=True)

    q = (
        db.query(Allocation)
        .join(Customer, Customer.id == Allocation.customer_id)
        .filter(Allocation.is_deleted == False)  # noqa: E712
        .filter(Customer.is_deleted == False)  # noqa: E712
    )
    if from_dt:
        q = q.filter(
            func.coalesce(Allocation.allocated_at, Allocation.created_at) >= from_dt
        )
    if to_dt:
        q = q.filter(
            func.coalesce(Allocation.allocated_at, Allocation.created_at) < to_dt
        )

    rows: List[Allocation] = q.all()

    def _get_dim_label(alloc: Allocation) -> str:
        cust = alloc.customer
        if dim == "month":
            ref = alloc.allocated_at or alloc.created_at
            return _to_month_label(ref) if ref else "未知"
        elif dim == "customer":
            return cust.customer_name if cust else "未知"
        elif dim == "sales":
            return str(cust.sales_user_id) if cust and cust.sales_user_id else "未分配"
        elif dim == "region":
            return (cust.region or "未知") if cust else "未知"
        elif dim == "industry":
            return (cust.industry or "未知") if cust else "未知"
        return "未知"

    def _get_breakdown_label(alloc: Allocation) -> str:
        cust = alloc.customer
        if not cust:
            return "未知"
        if breakdown == "customer_level":
            return cust.customer_level or "未知"
        elif breakdown == "industry":
            return cust.industry or "未知"
        return "全部"

    # key = (label, breakdown_label)
    buckets: dict[tuple, dict] = {}

    for alloc in rows:
        lbl = _get_dim_label(alloc)
        bd_lbl = _get_breakdown_label(alloc)
        key = (lbl, bd_lbl)
        if key not in buckets:
            buckets[key] = {
                "label": lbl,
                "breakdown_label": bd_lbl,
                "total_cost": 0.0,
                "total_price": 0.0,
                "profit_amount": 0.0,
            }
        b = buckets[key]
        b["total_cost"] += _safe_float(alloc.total_cost)
        b["total_price"] += _safe_float(alloc.total_price)
        b["profit_amount"] += _safe_float(alloc.profit_amount)

    result = []
    for v in sorted(buckets.values(), key=lambda x: (x["label"], x["breakdown_label"])):
        v["total_cost"] = round(v["total_cost"], 2)
        v["total_price"] = round(v["total_price"], 2)
        v["profit_amount"] = round(v["profit_amount"], 2)
        v["profit_rate"] = _profit_rate(v["total_price"], v["total_cost"])
        # 兼容前端字段
        v["period"] = v["label"]
        v["revenue"] = v["total_price"]
        v["cost"] = v["total_cost"]
        v["profit"] = v["profit_amount"]
        result.append(v)
    return result


# ──────────────────────────────────────────────
# 3. funnel
# ──────────────────────────────────────────────

@router.get("/funnel", summary="销售漏斗（stage 转化率）")
def funnel(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    start: Optional[str] = Query(None, description="同 from (前端别名)"),
    end: Optional[str] = Query(None, description="同 to (前端别名)"),
    dimension: Optional[str] = Query(None, description="占位接受前端参数"),
    db: Session = Depends(get_db),
    _=_manager_dep,
):
    """基于 customer.lifecycle_stage 当前分布计算漏斗转化率。
    返回 list 形态便于前端表格/漏斗图直接渲染，同时附 `_summary` 原始汇总。
    """
    from_ = from_ or start
    to = to or end
    from_dt = _parse_date(from_)
    to_dt = _parse_date(to, end_inclusive=True)

    base_q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if from_dt:
        base_q = base_q.filter(Customer.created_at >= from_dt)
    if to_dt:
        base_q = base_q.filter(Customer.created_at < to_dt)

    customers = base_q.all()

    lead_count = sum(1 for c in customers if c.lifecycle_stage == "lead")
    contacting_count = sum(1 for c in customers if c.lifecycle_stage == "contacting")
    active_count = sum(1 for c in customers if c.lifecycle_stage == "active")

    total = lead_count + contacting_count + active_count
    lead_to_contacting_rate = round(
        (contacting_count + active_count) / total * 100, 2
    ) if total > 0 else 0.0
    contacting_to_active_rate = round(
        active_count / (contacting_count + active_count) * 100, 2
    ) if (contacting_count + active_count) > 0 else 0.0

    # avg_lead_to_active_days: from first customer_stage_request approved entry
    # (lead→contacting) to first approved (contacting→active) per customer
    cust_ids = [c.id for c in customers if c.lifecycle_stage == "active"]
    avg_days: Optional[float] = None
    if cust_ids:
        # fetch all approved stage requests for those customers
        reqs = (
            db.query(CustomerStageRequest)
            .filter(
                CustomerStageRequest.customer_id.in_(cust_ids),
                CustomerStageRequest.status == "approved",
            )
            .order_by(CustomerStageRequest.customer_id, CustomerStageRequest.decided_at)
            .all()
        )
        # group by customer_id
        by_customer: dict[int, list] = {}
        for r in reqs:
            by_customer.setdefault(r.customer_id, []).append(r)

        deltas: list[float] = []
        for cid, cust_reqs in by_customer.items():
            # find first lead→contacting entry time
            first_contact = next(
                (r.decided_at for r in cust_reqs if r.to_stage == "contacting"),
                None,
            )
            first_active = next(
                (r.decided_at for r in cust_reqs if r.to_stage == "active"),
                None,
            )
            if first_contact and first_active and first_active > first_contact:
                deltas.append((first_active - first_contact).total_seconds() / 86400)
        if deltas:
            avg_days = round(sum(deltas) / len(deltas), 1)

    # 新口径：返回列表 [{stage, label, count, rate?}]，前端 FunnelPoint[] 可直渲
    return [
        {"stage": "lead", "label": "商机池",
         "count": lead_count, "rate": None},
        {"stage": "contacting", "label": "跟进中",
         "count": contacting_count, "rate": lead_to_contacting_rate},
        {"stage": "active", "label": "正式客户",
         "count": active_count, "rate": contacting_to_active_rate},
        # 附件：lead→active 平均天数，作为元指标项
        {"stage": "avg_lead_to_active_days", "label": "lead→active 平均天数",
         "count": avg_days if avg_days is not None else 0, "rate": None},
    ]


# ──────────────────────────────────────────────
# 4. yoy (Year-over-Year / Month-over-Month)
# ──────────────────────────────────────────────

def _period_bounds(period_str: str, period_type: str) -> tuple[datetime, datetime]:
    """返回 (start, end_exclusive) for a period string like '2026-03' or '2026-Q1'."""
    if period_type == "month":
        y, m = int(period_str[:4]), int(period_str[5:7])
        start = datetime(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        return start, datetime(ny, nm, 1)
    else:  # quarter
        y = int(period_str[:4])
        q = int(period_str[6])
        sm = (q - 1) * 3 + 1
        em = sm + 3
        return datetime(y, sm, 1), datetime(y if em <= 12 else y + 1, em if em <= 12 else em - 12, 1)


def _prev_period(period_str: str, period_type: str) -> str:
    if period_type == "month":
        y, m = int(period_str[:4]), int(period_str[5:7])
        py, pm = (y - 1, 12) if m == 1 else (y, m - 1)
        return f"{py:04d}-{pm:02d}"
    else:
        y = int(period_str[:4])
        q = int(period_str[6])
        if q == 1:
            return f"{y - 1:04d}-Q4"
        return f"{y:04d}-Q{q - 1}"


def _yoy_period(period_str: str, period_type: str) -> str:
    if period_type == "month":
        y, m = int(period_str[:4]), int(period_str[5:7])
        return f"{y - 1:04d}-{m:02d}"
    else:
        y = int(period_str[:4])
        q = int(period_str[6])
        return f"{y - 1:04d}-Q{q}"


def _sum_metric(db: Session, metric: str, start: datetime, end: datetime) -> float:
    col = Allocation.total_price if metric == "sales" else Allocation.profit_amount
    row = (
        db.query(func.coalesce(func.sum(col), 0))
        .filter(Allocation.is_deleted == False)  # noqa: E712
        .filter(
            func.coalesce(Allocation.allocated_at, Allocation.created_at) >= start,
            func.coalesce(Allocation.allocated_at, Allocation.created_at) < end,
        )
        .scalar()
    )
    return _safe_float(row)


def _generate_periods(period: str, now: datetime) -> list[str]:
    """Generate all periods (months or quarters) up to now within current year."""
    if period == "month":
        periods = []
        for m in range(1, now.month + 1):
            periods.append(f"{now.year:04d}-{m:02d}")
        return periods
    else:
        quarters = []
        current_q = (now.month - 1) // 3 + 1
        for q in range(1, current_q + 1):
            quarters.append(f"{now.year:04d}-Q{q}")
        return quarters


@router.get("/yoy", summary="同比 / 环比分析")
def yoy(
    metric: str = Query("sales", description="sales | profit"),
    period: Optional[str] = Query(None, description="month | quarter"),
    dimension: Optional[str] = Query(None, description="前端别名; month/quarter/year/salesperson → 映射 period"),
    start: Optional[str] = Query(None, description="前端占位参数，yoy 目前按当年生成"),
    end: Optional[str] = Query(None, description="前端占位参数"),
    db: Session = Depends(get_db),
    _=_manager_dep,
) -> List[dict]:
    # 前端传 dimension=month/quarter/year/salesperson；仅 month/quarter 与 yoy period 概念对齐
    if dimension in ("month", "quarter"):
        period = period or dimension
    period = period or "month"
    """当年每个 period 的指标值，附同比 (yoy_pct) 和环比 (mom_pct)。"""
    now = datetime.utcnow()
    periods = _generate_periods(period, now)

    result = []
    prev_current: Optional[float] = None

    for p in periods:
        start, end = _period_bounds(p, period)
        current = _sum_metric(db, metric, start, end)

        prev_p = _prev_period(p, period)
        prev_start, prev_end = _period_bounds(prev_p, period)
        previous = _sum_metric(db, metric, prev_start, prev_end)

        yoy_p = _yoy_period(p, period)
        yoy_start, yoy_end = _period_bounds(yoy_p, period)
        yoy_val = _sum_metric(db, metric, yoy_start, yoy_end)

        yoy_pct: Optional[float] = None
        if yoy_val > 0:
            yoy_pct = round((current - yoy_val) / yoy_val * 100, 2)

        mom_pct: Optional[float] = None
        if previous > 0:
            mom_pct = round((current - previous) / previous * 100, 2)

        result.append({
            "period": p,
            "current": round(current, 2),
            "previous": round(previous, 2),
            "yoy_pct": yoy_pct,
            "mom_pct": mom_pct,
            # 前端别名
            "current_year": round(current, 2),
            "last_year": round(yoy_val, 2),
            "yoy": (yoy_pct / 100.0) if yoy_pct is not None else None,
            "mom": (mom_pct / 100.0) if mom_pct is not None else None,
        })
        prev_current = current

    return result


# ──────────────────────────────────────────────
# 5. export CSV
# ──────────────────────────────────────────────

def _rows_to_csv(headers: list[str], rows: list[list[Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue()


def _sales_trend_to_csv(data: List[dict]) -> tuple[list[str], list[list]]:
    headers = ["维度标签", "销售额", "利润", "笔数"]
    rows = [[d["label"], d["total_sales"], d["total_profit"], d["count"]] for d in data]
    return headers, rows


def _profit_analysis_to_csv(data: List[dict]) -> tuple[list[str], list[list]]:
    headers = ["维度标签", "拆解标签", "总成本", "总售价", "利润金额", "利润率(%)"]
    rows = [
        [d["label"], d["breakdown_label"], d["total_cost"], d["total_price"],
         d["profit_amount"], d["profit_rate"]]
        for d in data
    ]
    return headers, rows


def _funnel_to_csv(data) -> tuple[list[str], list[list]]:
    headers = ["阶段", "数量", "转化率(%)"]
    rows = []
    # 新口径 data 是 list[{stage,label,count,rate}]；向后兼容老 dict
    if isinstance(data, list):
        for d in data:
            rows.append([d.get("stage") or "", d.get("count", ""), d.get("rate") if d.get("rate") is not None else ""])
    elif isinstance(data, dict):
        rows.extend([
            ["lead", data.get("lead", ""), ""],
            ["contacting", data.get("contacting", ""), data.get("lead_to_contacting_rate", "")],
            ["active", data.get("active", ""), data.get("contacting_to_active_rate", "")],
            ["avg_lead_to_active_days", data.get("avg_lead_to_active_days") or "", ""],
        ])
    return headers, rows


def _yoy_to_csv(data: List[dict]) -> tuple[list[str], list[list]]:
    headers = ["周期", "当期", "上期", "同比(%)", "环比(%)"]
    rows = [
        [d["period"], d["current"], d["previous"],
         d["yoy_pct"] if d["yoy_pct"] is not None else "",
         d["mom_pct"] if d["mom_pct"] is not None else ""]
        for d in data
    ]
    return headers, rows


@router.get("/export", summary="报表 CSV 导出")
def export_report(
    type: str = Query(..., description="sales-trend | profit | funnel | yoy"),
    format: str = Query("csv", description="csv（xlsx 暂不实现）"),
    dim: str = Query("month"),
    breakdown: Optional[str] = Query(None),
    metric: str = Query("sales"),
    period: str = Query("month"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=_manager_dep,
):
    """调对应 endpoint 拿数据，流式返回 CSV。xlsx 留 TODO。"""
    # TODO: implement xlsx format when openpyxl is available
    if format != "csv":
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="仅支持 format=csv，xlsx 暂未实现")

    if type == "sales-trend":
        data = sales_trend(
            dim=dim, dimension=None, from_=from_, to=to,
            start=None, end=None, db=db, _=None,
        )
        headers, rows = _sales_trend_to_csv(data)
    elif type == "profit":
        data = profit_analysis(
            dim=dim, dimension=None, breakdown=breakdown,
            from_=from_, to=to, start=None, end=None, db=db, _=None,
        )
        headers, rows = _profit_analysis_to_csv(data)
    elif type == "funnel":
        data = funnel(
            from_=from_, to=to, start=None, end=None,
            dimension=None, db=db, _=None,
        )
        headers, rows = _funnel_to_csv(data)
    elif type == "yoy":
        data = yoy(
            metric=metric, period=period, dimension=None,
            start=None, end=None, db=db, _=None,
        )
        headers, rows = _yoy_to_csv(data)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"未知 type: {type}")

    csv_content = _rows_to_csv(headers, rows)

    filename = f"report_{type}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
