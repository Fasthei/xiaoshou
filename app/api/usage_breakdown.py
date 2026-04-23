"""用量查看：客户 → 货源 → 具体服务（虚拟机 / AI / 存储 / …）三层下钻.

数据源：
    本地 cc_usage.raw.accounts[]（metering/detail 同步落下的明细快照）
    - 每行包含 account_id / service / cost / usage / date / source
    - 我们按 (customer, resource, service) 三层聚合回前端

客户 → 货源路由优先级（沿用 bills_local 口径）：
    1) customer_resource 手工关联
    2) sales-manager / admin / ops 额外兜底：resource.identifier_field == customer.customer_code 自然匹配
       （销售主管不会手工关联客户，仍应能看到所有客户用量）
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.cc_usage import CCUsage
from app.models.customer import Customer
from app.services.customer_resource_resolver import resolve_customer_resources

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/usage", tags=["用量查看"])


_MANAGER_ROLES = {"sales-manager", "admin", "ops", "operation", "operations"}


def _can_see_all(user: CurrentUser) -> bool:
    return any(user.has_role(r) for r in _MANAGER_ROLES)


def _sales_filter_clause(user: CurrentUser):
    try:
        sid = int(user.sub)
        return Customer.sales_user_id == sid
    except (TypeError, ValueError):
        return Customer.id == -1


# ---------- service → 类别 分类 ----------
#
# 关键词按 "compute → ai → database → storage → network → other" 的
# 优先顺序匹配，第一个命中即返回。顺序影响：比如 "AI 虚拟机" 会被归 compute —
# 这里选择优先看底层资源形态，避免把"AI 优先"策略绑死在字符串里。
#
# 如需精调可以直接加关键词；想加新类目在 _CATEGORIES 注册即可.

_CATEGORIES: List[Tuple[str, re.Pattern[str]]] = [
    ("compute",  re.compile(r"(vm|instance|ec2|compute|k8s|aks|eks|gke|container|ecs|fargate|lambda|function|app service|cloud run|serverless|cpu|gpu)", re.I)),
    ("ai",       re.compile(r"(gpt|llm|openai|aoai|claude|anthropic|cognitive|bedrock|sagemaker|vision|speech|nlp|\bai\b|\bml\b|tokens?)", re.I)),
    ("database", re.compile(r"(sql|database|mysql|postgres|redis|cosmos|dynamodb|mongo|memcache|rds|elasticsearch|opensearch)", re.I)),
    ("storage",  re.compile(r"(storage|blob|s3|oss|cos|disk|ebs|volume|efs|file|archive|bucket)", re.I)),
    ("network",  re.compile(r"(cdn|dns|vpn|vpc|load balancer|elb|nat|bandwidth|data transfer|\bnetwork\b|gateway|traffic)", re.I)),
]

_CATEGORY_LABELS = {
    "compute":  "计算",
    "ai":       "AI",
    "database": "数据库",
    "storage":  "存储",
    "network":  "网络",
    "other":    "其他",
}


def _service_category(name: Optional[str]) -> str:
    if not name:
        return "other"
    for cat, pattern in _CATEGORIES:
        if pattern.search(name):
            return cat
    return "other"


# ---------- helpers ----------

def _month_range(month: str) -> Tuple[date, date]:
    y, m = month.split("-")
    yi, mi = int(y), int(m)
    start = date(yi, mi, 1)
    end = date(yi + 1, 1, 1) if mi == 12 else date(yi, mi + 1, 1)
    return start, end


def _usage_rows_by_identifier(
    db: Session, identifiers: List[str], month: str,
) -> Dict[str, List[CCUsage]]:
    """批量拉 cc_usage 当月数据，按 customer_code (=identifier_field) 分桶."""
    out: Dict[str, List[CCUsage]] = defaultdict(list)
    if not identifiers:
        return out
    start, end = _month_range(month)
    rows = db.query(CCUsage).filter(
        CCUsage.customer_code.in_(identifiers),
        CCUsage.date >= start,
        CCUsage.date < end,
    ).all()
    for r in rows:
        if r.customer_code:
            out[r.customer_code].append(r)
    return out


def _aggregate_skus_for_resource(
    usage_rows: List[CCUsage],
) -> List[Dict[str, Any]]:
    """把一个 identifier 对应的 cc_usage 行里的 raw.accounts[] 按 SKU 聚合.

    聚合 key = (provider, product, sku, region, usage_unit) — SKU 是 cloudcost
    metering/detail 里的 `usage_type`，是产品下的计费规格粒度（如 "P0v3 App" /
    "USE1-MP:USE1_OutputTokenCount-Units"）。

    兼容老数据：同步器旧版本只存 `service` 不存 `product/sku`，此处退回用
    service 作为 product + sku（此时 product==sku，前端仍能画图，只是 SKU 粒度
    退化成 service 粒度）。新数据同步后自动升级.
    """
    # key = (provider, product, sku, region, unit) → {cost, usage, records}
    buckets: Dict[tuple, Dict[str, Any]] = {}
    for u in usage_rows:
        raw = u.raw if isinstance(u.raw, dict) else {}
        accounts = raw.get("accounts") if isinstance(raw, dict) else None
        if not isinstance(accounts, list):
            continue
        for entry in accounts:
            if not isinstance(entry, dict):
                continue
            product = (
                entry.get("product")
                or entry.get("service")
                or entry.get("service_name")
                or "云服务"
            )
            sku = entry.get("sku") or entry.get("usage_type") or product
            provider = entry.get("provider") or None
            region = entry.get("region") or None
            unit = entry.get("usage_unit") or entry.get("unit") or None
            key = (provider, product, sku, region, unit)
            slot = buckets.setdefault(key, {"cost": 0.0, "usage": 0.0, "records": 0})
            try:
                slot["cost"] += float(entry.get("cost") or 0)
            except (TypeError, ValueError):
                pass
            try:
                slot["usage"] += float(entry.get("usage") or 0)
            except (TypeError, ValueError):
                pass
            slot["records"] += 1

    skus: List[Dict[str, Any]] = []
    for (provider, product, sku, region, unit), vals in buckets.items():
        cat = _service_category(product)
        skus.append({
            "provider": provider,
            "product": product,
            "sku": sku,
            "region": region,
            "usage_unit": unit,
            "category": cat,
            "category_label": _CATEGORY_LABELS.get(cat, "其他"),
            "cost": round(vals["cost"], 2),
            "usage": round(vals["usage"], 4),
            "record_count": int(vals["records"]),
        })
    skus.sort(key=lambda s: s["cost"], reverse=True)
    return skus


# ---------- endpoint ----------

@router.get(
    "/breakdown",
    summary="用量三层下钻：客户 → 货源 → 具体服务",
)
def usage_breakdown(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM，默认当月"),
    include_empty: bool = Query(False, description="是否包含用量=0 的客户/货源"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    m = month or datetime.utcnow().strftime("%Y-%m")

    # 1) 授权客户集
    q = db.query(Customer).filter(Customer.is_deleted == False)  # noqa: E712
    see_all = _can_see_all(user)
    if not see_all:
        q = q.filter(_sales_filter_clause(user))
    customers = q.all()
    if not customers:
        return {
            "month": m, "total_cost": 0.0, "total_usage": 0.0,
            "customer_count": 0, "customers": [],
            "categories": list(_CATEGORY_LABELS.keys()),
            "category_labels": _CATEGORY_LABELS,
        }

    # 2) 客户 → 货源（手工 + 可选自然匹配）
    cust_to_resources = resolve_customer_resources(
        db, customers, include_auto_match=see_all,
    )

    # 3) 所有 identifier_field 批量拉 cc_usage 当月数据
    all_identifiers: Set[str] = set()
    for rows in cust_to_resources.values():
        for r in rows:
            if r.identifier_field:
                all_identifiers.add(r.identifier_field)
    usage_by_id = _usage_rows_by_identifier(db, list(all_identifiers), m)

    # 4) 组装三层结构
    result_customers: List[Dict[str, Any]] = []
    grand_cost = 0.0
    grand_usage = 0.0
    for c in customers:
        resources = cust_to_resources.get(c.id, [])
        resource_rows: List[Dict[str, Any]] = []
        cust_cost = 0.0
        cust_usage = 0.0
        for r in resources:
            rid = r.identifier_field
            usage_rows = usage_by_id.get(rid or "", [])
            skus = _aggregate_skus_for_resource(usage_rows)
            r_cost = sum(s["cost"] for s in skus)
            r_usage = sum(s["usage"] for s in skus)
            if r_cost == 0 and r_usage == 0 and not include_empty:
                continue
            cust_cost += r_cost
            cust_usage += r_usage
            resource_rows.append({
                "resource_id": r.id,
                "resource_code": r.resource_code,
                "account_name": r.account_name,
                "cloud_provider": r.cloud_provider,
                "identifier_field": r.identifier_field,
                "total_cost": round(r_cost, 2),
                "total_usage": round(r_usage, 4),
                "sku_count": len(skus),
                "skus": skus,
            })
        if not resource_rows and not include_empty:
            continue
        grand_cost += cust_cost
        grand_usage += cust_usage
        result_customers.append({
            "customer_id": c.id,
            "customer_name": c.customer_name,
            "customer_code": c.customer_code,
            "customer_type": getattr(c, "customer_type", None),
            "total_cost": round(cust_cost, 2),
            "total_usage": round(cust_usage, 4),
            "resource_count": len(resource_rows),
            "resources": resource_rows,
        })

    result_customers.sort(key=lambda x: x["total_cost"], reverse=True)
    return {
        "month": m,
        "total_cost": round(grand_cost, 2),
        "total_usage": round(grand_usage, 4),
        "customer_count": len(result_customers),
        "categories": list(_CATEGORY_LABELS.keys()),
        "category_labels": _CATEGORY_LABELS,
        "customers": result_customers,
    }
