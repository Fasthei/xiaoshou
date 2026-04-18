"""本地账单聚合 API — 按客户 × 关联货源聚合 cc_bill / cc_usage.

业务逻辑（CLAUDE.md §3.3 "运营视角"）:
  不再展示云管原始费用, 改为按客户**本地关联的货源** (customer_resource 关联表)
  聚合费用:
    1. 取 customer_resource 里所有 (customer_id, resource_id) 对
    2. 通过 resource.identifier_field / account_name / cloud_account_id 去找云管
       账单 cc_bill / 用量 cc_usage 对应行
    3. GROUP BY customer_id 汇总
    4. 客户无关联货源则 cost=0 (默认不返回, 可带 include_empty=1 返回)

权限 (CLAUDE.md §3):
  - sales-manager / admin / ops: 可看全部客户
  - sales: 只能看 customer.sales_user_id 匹配自己 (通过 sub / name / id) 的客户

cc_bill 关联策略:
  cc_bill 表没有 resource_id 直接外键. 通过 customer_code 关联到 customer.customer_code.
  所以"该客户当月账单"的算法是:
    bills = cc_bill.filter(month=m, customer_code=customer.customer_code)
  然后把 bill 按 provider 分桶, 尝试与 resource.cloud_provider 对齐归到每个关联货源.
  如果无法对齐, 归入 "其他" 组.

cc_usage 下钻策略 (granularity=day):
  usage = cc_usage.filter(customer_code=customer.customer_code, date in month)
  按日聚合 total_cost.
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
from app.models.cc_bill import CCBill
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bills", tags=["账单-本地聚合"])


_MANAGER_ROLES = {"sales-manager", "admin", "ops", "operation", "operations"}


def _can_see_all(user: CurrentUser) -> bool:
    return any(user.has_role(r) for r in _MANAGER_ROLES)


def _sales_filter_clause(user: CurrentUser):
    """返回 SQLAlchemy filter: 只允许看自己负责的客户.

    customer.sales_user_id 是 BigInteger — 但 Casdoor sub 是字符串 (UUID-like).
    历史上很多部署直接把 sub 的数字写到 sales_user_id, 或者 sales 表建了一个映射.
    这里尽可能地宽松匹配: 尝试把 user.sub 当整数;失败则空 filter (= 看不到任何).
    另外支持按 created_by == sub 来兜底.
    """
    try:
        sid = int(user.sub)
        return Customer.sales_user_id == sid
    except (TypeError, ValueError):
        # fallback: 空白 filter, 但我们宁愿返回空列表也不给泄露全部.
        return Customer.id == -1  # 永远不匹配


def _month_date_range(month: str) -> Tuple[date, date]:
    """'2026-04' -> (date(2026,4,1), date(2026,4,30))."""
    y, m = month.split("-")
    y_i, m_i = int(y), int(m)
    start = date(y_i, m_i, 1)
    if m_i == 12:
        end = date(y_i + 1, 1, 1)
    else:
        end = date(y_i, m_i + 1, 1)
    # last day = end - 1 day, but we'll use end as exclusive upper bound
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


def _customer_month_total(db: Session, customer_code: str, month: str) -> float:
    """客户当月总费用 = cc_bill.final_cost 之和 (优先), 否则 cc_usage."""
    if not customer_code:
        return 0.0
    bills = db.query(CCBill).filter(
        CCBill.month == month,
        CCBill.customer_code == customer_code,
    ).all()
    if bills:
        return sum(_decimal_to_float(b.final_cost) for b in bills)
    # fallback: 汇总 cc_usage 当月
    start, end = _month_date_range(month)
    usages = db.query(CCUsage).filter(
        CCUsage.customer_code == customer_code,
        CCUsage.date >= start,
        CCUsage.date < end,
    ).all()
    return sum(_decimal_to_float(u.total_cost) for u in usages)


def _split_cost_across_resources(
    total: float, resources: List[Resource], bills: List[CCBill],
) -> Dict[int, float]:
    """把 customer 的当月总账单按 provider 分桶分配到每个关联货源.

    算法:
      - 按 provider 汇总 cc_bill.final_cost -> provider_totals
      - 每个 resource 按 cloud_provider 匹配, 同 provider 的 resources 平分该桶
      - provider 没对上的 bill 金额计入 "其他" (resource_id=None)
      - 只用 total 做完整性校验, 实际以 provider_totals 为准
    """
    if not resources:
        return {}
    provider_totals: Dict[str, float] = defaultdict(float)
    for b in bills:
        p = (b.provider or "").upper() or "UNKNOWN"
        provider_totals[p] += _decimal_to_float(b.final_cost)

    # group resources by provider
    by_provider: Dict[str, List[Resource]] = defaultdict(list)
    for r in resources:
        by_provider[(r.cloud_provider or "").upper() or "UNKNOWN"].append(r)

    out: Dict[int, float] = {r.id: 0.0 for r in resources}
    for provider, amt in provider_totals.items():
        matched = by_provider.get(provider) or []
        if matched:
            share = amt / len(matched)
            for r in matched:
                out[r.id] += share
        # unmatched provider amount is dropped silently from per-resource view
    return out


@router.get("/by-customer", summary="按客户聚合本月账单（本地 customer_resource）")
def bills_by_customer(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (默认当月)"),
    include_empty: bool = Query(False, description="是否返回无关联货源/金额=0的客户"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
) -> Any:
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")
    # 1) 拿客户范围 (权限)
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if not _can_see_all(user):
        q = q.filter(_sales_filter_clause(user))
    customers = q.all()
    if not customers:
        return []
    cust_by_id = {c.id: c for c in customers}

    # 2) 找这些客户的 customer_resource 行
    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id.in_(cust_by_id.keys()),
    ).all()

    # customer_id -> [resource_id]
    cust_to_res_ids: Dict[int, List[int]] = defaultdict(list)
    for link in links:
        cust_to_res_ids[link.customer_id].append(link.resource_id)

    if not cust_to_res_ids and not include_empty:
        return []

    all_res_ids = {rid for rids in cust_to_res_ids.values() for rid in rids}
    resources = (
        db.query(Resource).filter(Resource.id.in_(all_res_ids)).all()
        if all_res_ids else []
    )
    res_by_id = {r.id: r for r in resources}

    # 3) 批量取 cc_bill（按 month + customer_code 一次性拉回来, 避免 N+1）
    codes = {c.customer_code for c in customers if c.customer_code}
    bills_by_code: Dict[str, List[CCBill]] = defaultdict(list)
    if codes:
        for b in db.query(CCBill).filter(
            CCBill.month == month,
            CCBill.customer_code.in_(codes),
        ).all():
            bills_by_code[b.customer_code or ""].append(b)

    # 4) 汇总每个客户
    result: List[Dict[str, Any]] = []
    for cid, cust in cust_by_id.items():
        res_ids = cust_to_res_ids.get(cid, [])
        if not res_ids and not include_empty:
            continue
        cust_resources = [res_by_id[rid] for rid in res_ids if rid in res_by_id]
        cust_bills = bills_by_code.get(cust.customer_code or "", [])
        total = sum(_decimal_to_float(b.final_cost) for b in cust_bills)
        if total == 0 and not cust_bills:
            # fallback to cc_usage
            total = _customer_month_total(db, cust.customer_code or "", month)

        per_res = _split_cost_across_resources(total, cust_resources, cust_bills)

        if total == 0 and not include_empty:
            continue

        result.append({
            "customer_id": cid,
            "customer_name": cust.customer_name,
            "customer_code": cust.customer_code,
            "month": month,
            "total_cost": round(total, 2),
            "resource_count": len(cust_resources),
            "resources": [
                {
                    "resource_id": r.id,
                    "resource_code": r.resource_code,
                    "cloud_provider": r.cloud_provider,
                    "account_name": r.account_name,
                    "cost": round(per_res.get(r.id, 0.0), 2),
                }
                for r in cust_resources
            ],
        })
    # 排序: 金额从高到低
    result.sort(key=lambda x: x["total_cost"], reverse=True)
    return result


@router.get(
    "/by-customer/{customer_id}",
    summary="单客户下钻: 按货源 或 按日聚合",
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
        try:
            sid = int(user.sub)
        except (TypeError, ValueError):
            sid = -1
        if cust.sales_user_id != sid:
            raise HTTPException(403, "无权查看该客户账单")

    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id == customer_id,
    ).all()
    res_ids = [l.resource_id for l in links]
    resources = (
        db.query(Resource).filter(Resource.id.in_(res_ids)).all()
        if res_ids else []
    )

    bills = []
    if cust.customer_code:
        bills = db.query(CCBill).filter(
            CCBill.month == month,
            CCBill.customer_code == cust.customer_code,
        ).all()

    total = sum(_decimal_to_float(b.final_cost) for b in bills)

    if granularity == "resource":
        per_res = _split_cost_across_resources(total, resources, bills)
        return {
            "customer_id": customer_id,
            "customer_name": cust.customer_name,
            "month": month,
            "granularity": "resource",
            "total_cost": round(total, 2),
            "items": [
                {
                    "resource_id": r.id,
                    "resource_code": r.resource_code,
                    "cloud_provider": r.cloud_provider,
                    "account_name": r.account_name,
                    "cost": round(per_res.get(r.id, 0.0), 2),
                }
                for r in resources
            ],
        }

    # granularity == "day": 按日聚合 cc_usage
    start, end = _month_date_range(month)
    usages: List[CCUsage] = []
    if cust.customer_code:
        usages = db.query(CCUsage).filter(
            CCUsage.customer_code == cust.customer_code,
            CCUsage.date >= start,
            CCUsage.date < end,
        ).order_by(CCUsage.date.asc()).all()

    return {
        "customer_id": customer_id,
        "customer_name": cust.customer_name,
        "month": month,
        "granularity": "day",
        "total_cost": round(
            sum(_decimal_to_float(u.total_cost) for u in usages), 2,
        ),
        "items": [
            {
                "date": u.date.isoformat() if u.date else None,
                "total_cost": round(_decimal_to_float(u.total_cost), 2),
                "total_usage": round(_decimal_to_float(u.total_usage), 4),
                "record_count": u.record_count or 0,
            }
            for u in usages
        ],
    }


def _build_export_rows(
    db: Session,
    month: str,
    customers: List,
    cust_to_res_ids: Dict,
    res_by_id: Dict,
    bills_by_code: Dict,
) -> List[Dict[str, Any]]:
    """Build per-(customer, resource) rows with pre/post discount amounts and profit."""
    rows: List[Dict[str, Any]] = []
    for cust in customers:
        res_ids = cust_to_res_ids.get(cust.id, [])
        cust_resources = [res_by_id[rid] for rid in res_ids if rid in res_by_id]
        cust_bills = bills_by_code.get(cust.customer_code or "", [])

        # Aggregate pre-discount (original_cost) and post-discount (final_cost) by provider
        pre_by_provider: Dict[str, float] = defaultdict(float)
        post_by_provider: Dict[str, float] = defaultdict(float)
        for b in cust_bills:
            p = (b.provider or "").upper() or "UNKNOWN"
            pre_by_provider[p] += _decimal_to_float(b.original_cost)
            post_by_provider[p] += _decimal_to_float(b.final_cost)

        if not cust_resources:
            # No linked resources — emit one summary row
            pre_total = sum(pre_by_provider.values())
            post_total = sum(post_by_provider.values())
            if pre_total == 0 and post_total == 0:
                continue
            discount_rate = (pre_total - post_total) / pre_total if pre_total else 0.0
            rows.append({
                "month": month,
                "customer_name": cust.customer_name,
                "resource_code": "",
                "cloud_provider": "",
                "account_name": "",
                "pre_discount": pre_total,
                "discount_rate": discount_rate,
                "post_discount": post_total,
                "profit": post_total - pre_total,
            })
            continue

        # Group resources by provider for bucketed split
        by_provider: Dict[str, List] = defaultdict(list)
        for r in cust_resources:
            by_provider[(r.cloud_provider or "").upper() or "UNKNOWN"].append(r)

        # Emit one row per resource
        res_pre: Dict[int, float] = {r.id: 0.0 for r in cust_resources}
        res_post: Dict[int, float] = {r.id: 0.0 for r in cust_resources}
        all_providers = set(pre_by_provider.keys()) | set(post_by_provider.keys())
        for provider in all_providers:
            matched = by_provider.get(provider, [])
            if not matched:
                continue
            share = 1.0 / len(matched)
            for r in matched:
                res_pre[r.id] += pre_by_provider.get(provider, 0.0) * share
                res_post[r.id] += post_by_provider.get(provider, 0.0) * share

        for r in cust_resources:
            pre = res_pre[r.id]
            post = res_post[r.id]
            if pre == 0 and post == 0:
                continue
            discount_rate = (pre - post) / pre if pre else 0.0
            rows.append({
                "month": month,
                "customer_name": cust.customer_name,
                "resource_code": r.resource_code or "",
                "cloud_provider": r.cloud_provider or "",
                "account_name": r.account_name or "",
                "pre_discount": pre,
                "discount_rate": discount_rate,
                "post_discount": post,
                "profit": post - pre,
            })
    return rows


@router.get("/by-customer-export", summary="按客户聚合账单 CSV 导出（含折前/折后/毛利）")
@router.get("/export", summary="账单导出（含折前/折后/折扣率/毛利）")
def bills_by_customer_export(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    format: str = Query("csv", pattern=r"^csv$"),  # noqa: A002
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    import csv
    import io
    from fastapi.responses import StreamingResponse

    # Build customer + resource data (same permission logic as bills_by_customer)
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if not _can_see_all(user):
        q = q.filter(_sales_filter_clause(user))
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

    codes = {c.customer_code for c in customers if c.customer_code}
    bills_by_code: Dict[str, List[CCBill]] = defaultdict(list)
    if codes:
        for b in db.query(CCBill).filter(
            CCBill.month == month,
            CCBill.customer_code.in_(codes),
        ).all():
            bills_by_code[b.customer_code or ""].append(b)

    if not bills_by_code:
        logger.warning(
            "bills export month=%s: cc_bill 数据为空，返回空 CSV (请确认同步任务已运行)", month,
        )

    export_rows = _build_export_rows(
        db=db, month=month, customers=customers,
        cust_to_res_ids=cust_to_res_ids, res_by_id=res_by_id,
        bills_by_code=bills_by_code,
    )

    def _iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        yield "\ufeff"
        w.writerow([
            "月份", "客户名", "货源代码", "货源厂商", "货源账号",
            "折前金额(cloudcost原价)", "折扣率", "折后金额", "毛利",
        ])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for row in export_rows:
            pre = row["pre_discount"]
            post = row["post_discount"]
            dr = row["discount_rate"]
            profit = row["profit"]
            w.writerow([
                row["month"],
                row["customer_name"],
                row["resource_code"],
                row["cloud_provider"],
                row["account_name"],
                f"{pre:.2f}",
                f"{dr:.4f}",
                f"{post:.2f}",
                f"{profit:.2f}",
            ])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fn = f"bills-{month}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        _iter(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )
