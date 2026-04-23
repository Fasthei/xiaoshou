"""客户 → 货源 关联解析器.

账单中心 + 用量查看 两个视图共用的"一个客户对应哪些货源"查询.

- **手工关联**（customer_resource）始终生效 — 销售在客户详情里勾选的真源
- **自然匹配**（resource.identifier_field == customer.customer_code）只对销售主管
  / admin / ops 启用，作为"销售没手工勾选也能看到全部用量"的兜底. 销售角色仍只
  看手工勾选的，不会因为自然匹配越权看到别人负责的客户.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource


def resolve_customer_resources(
    db: Session, customers: List[Customer], *, include_auto_match: bool,
) -> Dict[int, List[Resource]]:
    """返回 customer_id → [Resource]；手工关联 ∪（可选）自然匹配, 去重.

    调用方负责决定 `include_auto_match`：
        - 账单中心 / 用量查看给销售主管用 True
        - 给销售 / 未授权角色 用 False（只看手工关联）
    """
    if not customers:
        return {}

    cust_ids = [c.id for c in customers]
    links = db.query(CustomerResource).filter(
        CustomerResource.customer_id.in_(cust_ids),
    ).all()

    manual_by_cid: Dict[int, Set[int]] = defaultdict(set)
    for link in links:
        manual_by_cid[link.customer_id].add(link.resource_id)

    auto_by_cid: Dict[int, Set[int]] = defaultdict(set)
    if include_auto_match:
        code_to_cid: Dict[str, int] = {}
        for c in customers:
            if c.customer_code:
                code_to_cid.setdefault(c.customer_code, c.id)
        if code_to_cid:
            auto_resources = db.query(Resource).filter(
                Resource.identifier_field.in_(list(code_to_cid.keys())),
            ).all()
            for r in auto_resources:
                cid = code_to_cid.get(r.identifier_field or "")
                if cid is not None:
                    auto_by_cid[cid].add(r.id)

    all_ids: Set[int] = set()
    for cid in cust_ids:
        all_ids |= manual_by_cid.get(cid, set())
        all_ids |= auto_by_cid.get(cid, set())
    if not all_ids:
        return {}
    res_by_id = {
        r.id: r for r in db.query(Resource).filter(Resource.id.in_(all_ids)).all()
    }
    out: Dict[int, List[Resource]] = {}
    for cid in cust_ids:
        ids = manual_by_cid.get(cid, set()) | auto_by_cid.get(cid, set())
        rows = [res_by_id[rid] for rid in ids if rid in res_by_id]
        if rows:
            out[cid] = rows
    return out
