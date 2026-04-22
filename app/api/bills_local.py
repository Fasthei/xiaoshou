"""本地账单聚合 API — 按客户 × 销售分配货源 聚合。

硬口径（产品定稿 / docs/CLOUDCOST_API.md §4）:

  原价     = cc_usage.total_cost  (per identifier × month)
             —— 云管实际结算金额；销售系统**不再读 cc_bill** 的
             original_cost / final_cost，避免暴露云管成本视角。
  折扣率   = (客户 × 货源) 最近一条 approved allocation.discount_rate
             —— 销售下订单时定的，按货源粒度；未审批订单不参与。
  折扣覆盖 = bill_adjustment (customer × resource × month)
             若存在 override_discount_rate → 优先用它
             若有 surcharge → 叠加在折后价上（可正可负）
  折后价   = 原价 × (1 − 有效折扣率/100) + surcharge

Join key:
  resource.identifier_field = cc_usage.customer_code
                            = 云管 service_account.external_project_id

权限（CLAUDE.md §3）:
  - sales-manager / admin / ops: 可看全部客户
  - sales: 只能看 customer.sales_user_id == 本地 sales_user.id 的客户
    （本地 id 经 SalesUser.casdoor_user_id == user.sub 反查）
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.bill_adjustment import BillAdjustment
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource
from app.models.sales import SalesUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bills", tags=["账单-本地聚合"])


_MANAGER_ROLES = {"sales-manager", "admin", "ops", "operation", "operations"}


def _can_see_all(user: CurrentUser) -> bool:
    return any(user.has_role(r) for r in _MANAGER_ROLES)


def _resolve_my_sales_user_id(db: Session, user: CurrentUser) -> Optional[int]:
    """Casdoor sub (UUID) → 本地 sales_user.id.

    customer.sales_user_id 是本地 sales_user.id (BigInt)，不是 Casdoor sub。
    必须经 SalesUser.casdoor_user_id == user.sub 反查本地 id；
    兜底：某些部署把整数 sub 当 sales_user.id 直接写入。
    返回 None 表示该用户在 sales_user 表里找不到记录（视为零可见）。
    """
    if not user.sub:
        return None
    su = db.query(SalesUser).filter(SalesUser.casdoor_user_id == user.sub).first()
    if su:
        return int(su.id)
    try:
        return int(user.sub)
    except (TypeError, ValueError):
        return None


def _sales_filter_clause(db: Session, user: CurrentUser):
    sid = _resolve_my_sales_user_id(db, user)
    if sid is None:
        return Customer.id == -1  # 永不匹配，宁空勿漏
    return Customer.sales_user_id == sid


def _month_date_range(month: str) -> Tuple[date, date]:
    """'2026-04' -> (date(2026,4,1), date(2026,5,1))  (end exclusive)."""
    y, m = month.split("-")
    y_i, m_i = int(y), int(m)
    start = date(y_i, m_i, 1)
    end = date(y_i + 1, 1, 1) if m_i == 12 else date(y_i, m_i + 1, 1)
    return start, end


def _decimal_to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------- 数据拉取 ----------

def _fetch_usage_by_identifier(
    db: Session, identifiers: List[str], month: str,
) -> Dict[str, float]:
    """按 identifier_field 汇总当月 cc_usage.total_cost。"""
    out: Dict[str, float] = defaultdict(float)
    if not identifiers:
        return out
    start, end = _month_date_range(month)
    for u in db.query(CCUsage).filter(
        CCUsage.customer_code.in_(identifiers),
        CCUsage.date >= start,
        CCUsage.date < end,
    ).all():
        if u.customer_code:
            out[u.customer_code] += _decimal_to_float(u.total_cost)
    return out


def _fetch_discounts_by_cust_res(
    db: Session, pairs: List[Tuple[int, int]],
) -> Dict[Tuple[int, int], float]:
    """(customer_id, resource_id) → 最近一条 approved allocation.discount_rate (%)

    - 只看 approval_status='approved' 且非软删
    - 多条命中时取最新 approved_at (fallback: created_at)
    - 未命中返回 0.0
    """
    out: Dict[Tuple[int, int], float] = {}
    if not pairs:
        return out
    cust_ids = list({p[0] for p in pairs})
    res_ids = list({p[1] for p in pairs})
    q = (
        db.query(Allocation)
        .filter(
            Allocation.is_deleted == False,  # noqa: E712
            Allocation.approval_status == "approved",
            Allocation.customer_id.in_(cust_ids),
            Allocation.resource_id.in_(res_ids),
        )
        .order_by(Allocation.approved_at.desc(), Allocation.created_at.desc())
    )
    # Latest-wins per (cid, rid)
    for a in q.all():
        key = (int(a.customer_id), int(a.resource_id))
        if key in out:
            continue
        out[key] = _decimal_to_float(a.discount_rate) if a.discount_rate is not None else 0.0
    return out


def _fetch_adjustments(
    db: Session, pairs: List[Tuple[int, int]], month: str,
) -> Dict[Tuple[int, int], BillAdjustment]:
    """(customer_id, resource_id) → bill_adjustment 当月 row."""
    out: Dict[Tuple[int, int], BillAdjustment] = {}
    if not pairs:
        return out
    cust_ids = list({p[0] for p in pairs})
    res_ids = list({p[1] for p in pairs})
    for adj in db.query(BillAdjustment).filter(
        BillAdjustment.month == month,
        BillAdjustment.customer_id.in_(cust_ids),
        BillAdjustment.resource_id.in_(res_ids),
    ).all():
        out[(int(adj.customer_id), int(adj.resource_id))] = adj
    return out


# ---------- 单行计算 ----------

def _compute_row(
    original: float,
    order_discount_pct: float,
    adjustment: Optional[BillAdjustment],
) -> Tuple[float, float, float, float]:
    """Return (original, final, effective_discount_ratio_0_1, surcharge).

    effective_discount_pct = override_discount_rate if adjustment 有覆盖 else order_discount_pct
    surcharge              = adjustment.surcharge (可正可负)
    final                  = original × (1 − effective/100) + surcharge
    """
    eff_pct = order_discount_pct
    surcharge = 0.0
    if adjustment is not None:
        if adjustment.discount_rate_override is not None:
            eff_pct = _decimal_to_float(adjustment.discount_rate_override)
        if adjustment.surcharge is not None:
            surcharge = _decimal_to_float(adjustment.surcharge)
    discounted = original * (1.0 - (eff_pct / 100.0))
    final = discounted + surcharge
    # discount_ratio 以 0..1 口径返回（保持老前端兼容）
    return original, final, eff_pct / 100.0, surcharge


# ---------- 端点 ----------

@router.get("/by-customer", summary="按客户聚合当月账单 (订单折扣 × 覆盖 × 手续费)")
def bills_by_customer(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (默认当月)"),
    include_empty: bool = Query(False, description="是否返回无关联货源/金额=0的客户"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
) -> Any:
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")

    # 1) 授权客户集
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if not _can_see_all(user):
        q = q.filter(_sales_filter_clause(db, user))
    customers = q.all()
    if not customers:
        return []
    cust_by_id = {c.id: c for c in customers}

    # 2) customer_resource → (cid, rid) pairs
    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id.in_(cust_by_id.keys()),
    ).all()
    cust_to_res_ids: Dict[int, List[int]] = defaultdict(list)
    for link in links:
        cust_to_res_ids[link.customer_id].append(link.resource_id)
    if not cust_to_res_ids and not include_empty:
        return []

    # 3) 货源元数据
    all_res_ids = {rid for rids in cust_to_res_ids.values() for rid in rids}
    resources = (
        db.query(Resource).filter(Resource.id.in_(all_res_ids)).all()
        if all_res_ids else []
    )
    res_by_id = {r.id: r for r in resources}
    all_identifiers = [r.identifier_field for r in resources if r.identifier_field]

    # 4) 云管用量 + 订单折扣 + 账单覆盖
    usages_by_id = _fetch_usage_by_identifier(db, all_identifiers, month)
    pairs = [(cid, rid) for cid, rids in cust_to_res_ids.items() for rid in rids]
    discounts = _fetch_discounts_by_cust_res(db, pairs)
    adjustments = _fetch_adjustments(db, pairs, month)

    # 5) 每个 (客户 × 货源) 一行；客户聚合
    result: List[Dict[str, Any]] = []
    for cid, cust in cust_by_id.items():
        res_ids = cust_to_res_ids.get(cid, [])
        if not res_ids and not include_empty:
            continue
        cust_resources = [res_by_id[rid] for rid in res_ids if rid in res_by_id]

        resource_rows: List[Dict[str, Any]] = []
        orig_sum = 0.0
        final_sum = 0.0
        for r in cust_resources:
            usage = usages_by_id.get(r.identifier_field or "", 0.0)
            pct = discounts.get((cid, r.id), 0.0)
            adj = adjustments.get((cid, r.id))
            orig, final, dr_ratio, surcharge = _compute_row(usage, pct, adj)
            orig_sum += orig
            final_sum += final
            resource_rows.append({
                "resource_id": r.id,
                "resource_code": r.resource_code,
                "cloud_provider": r.cloud_provider,
                "account_name": r.account_name,
                "identifier_field": r.identifier_field,
                "original_cost": round(orig, 2),
                "discount_rate": round(dr_ratio, 4),        # 0..1
                "discount_rate_pct": round(pct, 2),         # 订单折扣 %
                "discount_override": (
                    float(adj.discount_rate_override)
                    if adj is not None and adj.discount_rate_override is not None else None
                ),
                "surcharge": round(surcharge, 2),
                "final_cost": round(final, 2),
                "cost": round(final, 2),                    # 旧别名
                "has_allocation": (cid, r.id) in discounts,
                "has_adjustment": adj is not None,
                "adjustment_notes": adj.notes if adj is not None else None,
            })

        if orig_sum == 0 and final_sum == 0 and not include_empty:
            continue

        total_dr_ratio = (orig_sum - final_sum) / orig_sum if orig_sum else 0.0
        result.append({
            "customer_id": cid,
            "customer_name": cust.customer_name,
            "customer_code": cust.customer_code,
            "month": month,
            "total_original_cost": round(orig_sum, 2),
            "total_discount_rate": round(total_dr_ratio, 4),
            "total_final_cost": round(final_sum, 2),
            "total_cost": round(final_sum, 2),              # 旧别名
            "resource_count": len(cust_resources),
            "resources": resource_rows,
        })
    result.sort(key=lambda x: x["total_cost"], reverse=True)
    return result


@router.get(
    "/by-customer/{customer_id}",
    summary="单客户下钻: 按货源 / 按日",
)
def bills_by_customer_detail(
    customer_id: int,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    granularity: str = Query("resource", pattern=r"^(resource|day)$"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
) -> Any:
    cust = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not cust:
        raise HTTPException(404, "客户不存在")

    # 权限
    if not _can_see_all(user):
        sid = _resolve_my_sales_user_id(db, user)
        if sid is None or cust.sales_user_id != sid:
            raise HTTPException(403, "无权查看该客户账单")

    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id == customer_id,
    ).all()
    res_ids = [l.resource_id for l in links]
    resources = (
        db.query(Resource).filter(Resource.id.in_(res_ids)).all()
        if res_ids else []
    )
    identifiers = [r.identifier_field for r in resources if r.identifier_field]

    if granularity == "resource":
        usages_by_id = _fetch_usage_by_identifier(db, identifiers, month)
        pairs = [(customer_id, r.id) for r in resources]
        discounts = _fetch_discounts_by_cust_res(db, pairs)
        adjustments = _fetch_adjustments(db, pairs, month)

        items = []
        orig_sum = 0.0
        final_sum = 0.0
        for r in resources:
            usage = usages_by_id.get(r.identifier_field or "", 0.0)
            pct = discounts.get((customer_id, r.id), 0.0)
            adj = adjustments.get((customer_id, r.id))
            orig, final, dr_ratio, surcharge = _compute_row(usage, pct, adj)
            orig_sum += orig
            final_sum += final
            items.append({
                "resource_id": r.id,
                "resource_code": r.resource_code,
                "cloud_provider": r.cloud_provider,
                "account_name": r.account_name,
                "identifier_field": r.identifier_field,
                "original_cost": round(orig, 2),
                "discount_rate": round(dr_ratio, 4),
                "discount_rate_pct": round(pct, 2),
                "discount_override": (
                    float(adj.discount_rate_override)
                    if adj is not None and adj.discount_rate_override is not None else None
                ),
                "surcharge": round(surcharge, 2),
                "final_cost": round(final, 2),
                "cost": round(final, 2),
                "has_allocation": (customer_id, r.id) in discounts,
                "has_adjustment": adj is not None,
            })
        total_dr_ratio = (orig_sum - final_sum) / orig_sum if orig_sum else 0.0
        return {
            "customer_id": customer_id,
            "customer_name": cust.customer_name,
            "month": month,
            "granularity": "resource",
            "total_original_cost": round(orig_sum, 2),
            "total_discount_rate": round(total_dr_ratio, 4),
            "total_final_cost": round(final_sum, 2),
            "total_cost": round(final_sum, 2),
            "items": items,
        }

    # granularity == "day": 跨该客户所有分配货源 cc_usage 按日合并
    start, end = _month_date_range(month)
    daily: Dict[str, Dict[str, float]] = {}
    if identifiers:
        for u in db.query(CCUsage).filter(
            CCUsage.customer_code.in_(identifiers),
            CCUsage.date >= start,
            CCUsage.date < end,
        ).all():
            if not u.date:
                continue
            key = u.date.isoformat()
            bucket = daily.setdefault(key, {"total_cost": 0.0, "total_usage": 0.0, "record_count": 0})
            bucket["total_cost"] += _decimal_to_float(u.total_cost)
            bucket["total_usage"] += _decimal_to_float(u.total_usage)
            bucket["record_count"] += u.record_count or 0

    items = [
        {
            "date": d,
            "total_cost": round(b["total_cost"], 2),
            "total_usage": round(b["total_usage"], 4),
            "record_count": int(b["record_count"]),
        }
        for d, b in sorted(daily.items())
    ]
    total = round(sum(x["total_cost"] for x in items), 2)
    return {
        "customer_id": customer_id,
        "customer_name": cust.customer_name,
        "month": month,
        "granularity": "day",
        "total_cost": total,
        "items": items,
    }


@router.get("/by-customer-export", summary="按客户聚合账单 CSV（含订单折扣 + 覆盖）")
@router.get("/export", summary="账单导出（含折前/折后/折扣率/手续费）")
def bills_by_customer_export(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    format: str = Query("csv", pattern=r"^csv$"),  # noqa: A002
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    # 权限过滤
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if not _can_see_all(user):
        q = q.filter(_sales_filter_clause(db, user))
    customers = q.all()

    if not customers:
        logger.warning("bills export: no customers found for user %s", user.sub)

    cust_to_res_ids: Dict[int, List[int]] = defaultdict(list)
    if customers:
        links = db.query(CustomerResource).filter(
            CustomerResource.customer_id.in_([c.id for c in customers]),
        ).all()
        for link in links:
            cust_to_res_ids[link.customer_id].append(link.resource_id)

    all_res_ids = {rid for rids in cust_to_res_ids.values() for rid in rids}
    resources = (
        db.query(Resource).filter(Resource.id.in_(all_res_ids)).all()
        if all_res_ids else []
    )
    res_by_id = {r.id: r for r in resources}
    identifiers = [r.identifier_field for r in resources if r.identifier_field]

    usages_by_id = _fetch_usage_by_identifier(db, identifiers, month)
    pairs = [(cid, rid) for cid, rids in cust_to_res_ids.items() for rid in rids]
    discounts = _fetch_discounts_by_cust_res(db, pairs)
    adjustments = _fetch_adjustments(db, pairs, month)

    def _iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        yield "\ufeff"
        w.writerow([
            "月份", "客户名", "货源代码", "货源厂商", "货源账号",
            "云账号标识(identifier_field)",
            "原价(云管用量)", "订单折扣率%", "覆盖折扣率%", "手续费", "折后金额", "备注",
        ])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for cust in customers:
            res_ids = cust_to_res_ids.get(cust.id, [])
            cust_resources = [res_by_id[rid] for rid in res_ids if rid in res_by_id]
            for r in cust_resources:
                usage = usages_by_id.get(r.identifier_field or "", 0.0)
                pct = discounts.get((cust.id, r.id), 0.0)
                adj = adjustments.get((cust.id, r.id))
                orig, final, _, surcharge = _compute_row(usage, pct, adj)
                if orig == 0 and final == 0 and adj is None:
                    continue
                override_pct = (
                    float(adj.discount_rate_override)
                    if adj is not None and adj.discount_rate_override is not None else ""
                )
                w.writerow([
                    month, cust.customer_name,
                    r.resource_code or "", r.cloud_provider or "",
                    r.account_name or "", r.identifier_field or "",
                    f"{orig:.2f}",
                    f"{pct:.2f}",
                    f"{override_pct:.2f}" if override_pct != "" else "",
                    f"{surcharge:.2f}",
                    f"{final:.2f}",
                    (adj.notes if adj is not None else "") or "",
                ])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fn = f"bills-{month}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        _iter(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
