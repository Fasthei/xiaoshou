"""本地账单聚合 API — 按客户 × **销售分配的货源** 聚合 cc_bill / cc_usage.

业务口径（产品硬口径，勿改）:
  1. 云管提供原始数据（per-account，不是 per-customer）。
  2. 云管里的货源（ServiceAccount / external_project_id）不天然对应客户。
  3. 只有销售系统在客户详情里把货源分配给客户（customer_resource 行）之后，
     本地才按该分配关系把对应货源的原始账单/用量归到该客户名下。
  4. 客户侧账单 = 云管原始数据（cc_bill / cc_usage）×
     销售分配关系（customer_resource）→ 本地聚合。
  → 绝不能用 `cc_bill.customer_code == customer.customer_code` 直接做等值聚合，
    因为 cc_bill.customer_code 其实是云管的 external_project_id（per-account），
    它碰到客户维度完全是巧合。

Join key（硬事实）:
  resource.identifier_field = 云管 service_account.external_project_id
                            = cc_bill.customer_code
                            = cc_usage.customer_code
  （见 app/api/sync.py: identifier_field=a.external_project_id）
  所以正确的关联链是：
    customer → customer_resource → resource.identifier_field → cc_bill/cc_usage

权限（CLAUDE.md §3）:
  - sales-manager / admin / ops: 可看全部客户
  - sales: 只能看 customer.sales_user_id == int(user.sub) 的客户
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


def _fetch_bills_by_identifier(
    db: Session, identifiers: List[str], month: str,
) -> Dict[str, List[CCBill]]:
    """批量拉一批 identifier_field 对应的当月 cc_bill，分桶返回。"""
    out: Dict[str, List[CCBill]] = defaultdict(list)
    if not identifiers:
        return out
    for b in db.query(CCBill).filter(
        CCBill.month == month,
        CCBill.customer_code.in_(identifiers),
    ).all():
        if b.customer_code:
            out[b.customer_code].append(b)
    return out


def _fetch_usage_by_identifier(
    db: Session, identifiers: List[str], month: str,
) -> Dict[str, float]:
    """批量拉 identifier_field 当月 cc_usage.total_cost，按 identifier 汇总。"""
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


def _cost_for_identifier(
    identifier: Optional[str],
    bills_by_id: Dict[str, List[CCBill]],
    usages_by_id: Dict[str, float],
) -> Tuple[float, float, float]:
    """单货源当月口径统一三元组: (original_cost, final_cost, discount_rate).

    - 有 cc_bill: original_cost / final_cost 分别合计, discount_rate = (orig - final)/orig
    - 没 cc_bill 则 fallback cc_usage.total_cost: 原价 = 折后价 = usage, discount_rate=0
      (usage 不区分折前折后, 只有一口价)
    """
    if not identifier:
        return 0.0, 0.0, 0.0
    if identifier in bills_by_id and bills_by_id[identifier]:
        orig = sum(_decimal_to_float(b.original_cost) for b in bills_by_id[identifier])
        final = sum(_decimal_to_float(b.final_cost) for b in bills_by_id[identifier])
        dr = ((orig - final) / orig) if orig else 0.0
        return orig, final, dr
    usage = usages_by_id.get(identifier, 0.0)
    return usage, usage, 0.0


@router.get("/by-customer", summary="按客户聚合本月账单（销售分配关系 × 云管原始数据）")
def bills_by_customer(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM (默认当月)"),
    include_empty: bool = Query(False, description="是否返回无关联货源/金额=0的客户"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
) -> Any:
    """聚合口径（严格按产品规则）:
      customer → customer_resource → resource.identifier_field → cc_bill/cc_usage
    未被销售分配的货源 (no customer_resource 行) 的云管原始费用**不计**到任何客户名下。
    """
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")

    # 1) 授权客户集
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    if not _can_see_all(user):
        q = q.filter(_sales_filter_clause(user))
    customers = q.all()
    if not customers:
        return []
    cust_by_id = {c.id: c for c in customers}

    # 2) 销售分配关系: customer_id -> [resource_id]
    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id.in_(cust_by_id.keys()),
    ).all()
    cust_to_res_ids: Dict[int, List[int]] = defaultdict(list)
    for link in links:
        cust_to_res_ids[link.customer_id].append(link.resource_id)

    if not cust_to_res_ids and not include_empty:
        return []

    # 3) 货源 → identifier_field（= 云管 external_project_id = cc_bill.customer_code）
    all_res_ids = {rid for rids in cust_to_res_ids.values() for rid in rids}
    resources = (
        db.query(Resource).filter(Resource.id.in_(all_res_ids)).all()
        if all_res_ids else []
    )
    res_by_id = {r.id: r for r in resources}
    all_identifiers = [r.identifier_field for r in resources if r.identifier_field]

    # 4) 批量拉 cc_bill + fallback cc_usage，按 identifier_field 分桶
    bills_by_id = _fetch_bills_by_identifier(db, all_identifiers, month)
    missing = [i for i in all_identifiers if i not in bills_by_id]
    usages_by_id = _fetch_usage_by_identifier(db, missing, month)

    # 5) 每个客户 = 其分配货源的费用直接相加（无 provider 近似分摊）
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
            orig, final, dr = _cost_for_identifier(r.identifier_field, bills_by_id, usages_by_id)
            orig_sum += orig
            final_sum += final
            resource_rows.append({
                "resource_id": r.id,
                "resource_code": r.resource_code,
                "cloud_provider": r.cloud_provider,
                "account_name": r.account_name,
                "identifier_field": r.identifier_field,
                "original_cost": round(orig, 2),
                "discount_rate": round(dr, 4),
                "final_cost": round(final, 2),
                "cost": round(final, 2),  # backwards compat alias = final_cost
            })

        if orig_sum == 0 and final_sum == 0 and not include_empty:
            continue

        total_discount_rate = ((orig_sum - final_sum) / orig_sum) if orig_sum else 0.0
        result.append({
            "customer_id": cid,
            "customer_name": cust.customer_name,
            "customer_code": cust.customer_code,
            "month": month,
            "total_original_cost": round(orig_sum, 2),
            "total_discount_rate": round(total_discount_rate, 4),
            "total_final_cost": round(final_sum, 2),
            # alias (老前端字段): total_cost = final（折后价合计）
            "total_cost": round(final_sum, 2),
            "resource_count": len(cust_resources),
            "resources": resource_rows,
        })
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

    # 销售分配关系: 只有分配给该客户的货源才计入
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
        bills_by_id = _fetch_bills_by_identifier(db, identifiers, month)
        missing = [i for i in identifiers if i not in bills_by_id]
        usages_by_id = _fetch_usage_by_identifier(db, missing, month)

        items = []
        orig_sum = 0.0
        final_sum = 0.0
        for r in resources:
            orig, final, dr = _cost_for_identifier(r.identifier_field, bills_by_id, usages_by_id)
            orig_sum += orig
            final_sum += final
            items.append({
                "resource_id": r.id,
                "resource_code": r.resource_code,
                "cloud_provider": r.cloud_provider,
                "account_name": r.account_name,
                "identifier_field": r.identifier_field,
                "original_cost": round(orig, 2),
                "discount_rate": round(dr, 4),
                "final_cost": round(final, 2),
                "cost": round(final, 2),  # 旧别名
            })
        total_discount_rate = ((orig_sum - final_sum) / orig_sum) if orig_sum else 0.0
        return {
            "customer_id": customer_id,
            "customer_name": cust.customer_name,
            "month": month,
            "granularity": "resource",
            "total_original_cost": round(orig_sum, 2),
            "total_discount_rate": round(total_discount_rate, 4),
            "total_final_cost": round(final_sum, 2),
            "total_cost": round(final_sum, 2),  # 旧别名 = total_final_cost
            "items": items,
        }

    # granularity == "day": 跨该客户所有分配货源的 cc_usage 按日合并
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


def _build_export_rows(
    month: str,
    customers: List,
    cust_to_res_ids: Dict,
    res_by_id: Dict,
    bills_by_identifier: Dict[str, List[CCBill]],
) -> List[Dict[str, Any]]:
    """逐 (customer × 分配货源) 出一行。pre/post 直接取 cc_bill 对应 identifier 的原值，
    不再做 provider 近似分摊 —— 保证和"按客户聚合"接口金额对齐。"""
    rows: List[Dict[str, Any]] = []
    for cust in customers:
        res_ids = cust_to_res_ids.get(cust.id, [])
        cust_resources = [res_by_id[rid] for rid in res_ids if rid in res_by_id]
        for r in cust_resources:
            iden = r.identifier_field
            if not iden:
                # 销售分配了货源但该货源没 identifier_field (云管 external_project_id 缺失)
                # -> 没法对齐 cc_bill, 仍输出 0 行供对账
                rows.append({
                    "month": month,
                    "customer_name": cust.customer_name,
                    "resource_code": r.resource_code or "",
                    "cloud_provider": r.cloud_provider or "",
                    "account_name": r.account_name or "",
                    "identifier_field": "",
                    "pre_discount": 0.0,
                    "discount_rate": 0.0,
                    "post_discount": 0.0,
                    "profit": 0.0,
                })
                continue
            bills = bills_by_identifier.get(iden, [])
            pre = sum(_decimal_to_float(b.original_cost) for b in bills)
            post = sum(_decimal_to_float(b.final_cost) for b in bills)
            if pre == 0 and post == 0:
                continue
            discount_rate = (pre - post) / pre if pre else 0.0
            rows.append({
                "month": month,
                "customer_name": cust.customer_name,
                "resource_code": r.resource_code or "",
                "cloud_provider": r.cloud_provider or "",
                "account_name": r.account_name or "",
                "identifier_field": iden,
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

    # 只按销售分配给客户的货源聚合 cc_bill — identifier_field 是云管 external_project_id
    identifiers = [r.identifier_field for r in resources if r.identifier_field]
    bills_by_identifier = _fetch_bills_by_identifier(db, identifiers, month)

    if not bills_by_identifier:
        logger.warning(
            "bills export month=%s: 分配给客户的货源在 cc_bill 无命中 (identifiers=%d)",
            month, len(identifiers),
        )

    export_rows = _build_export_rows(
        month=month, customers=customers,
        cust_to_res_ids=cust_to_res_ids, res_by_id=res_by_id,
        bills_by_identifier=bills_by_identifier,
    )

    def _iter():
        buf = io.StringIO()
        w = csv.writer(buf)
        yield "\ufeff"
        w.writerow([
            "月份", "客户名", "货源代码", "货源厂商", "货源账号", "云账号标识(identifier_field)",
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
                row.get("identifier_field", ""),
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
