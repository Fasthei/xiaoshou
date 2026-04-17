"""客户 ↔ 货源 关联 CRUD.

正式客户（lifecycle_stage=active）通过本地 customer_resource 表勾选关联多个货源。
货源本身通过云管 (cloudcost) 同步进入本地 resource 表。本 API 只做关联表的 CRUD。
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.customer import Customer
from app.models.customer_resource import CustomerResource
from app.models.resource import Resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


class LinkCreate(BaseModel):
    resource_ids: List[int] = Field(default_factory=list)
    end_user_label: Optional[str] = None  # 渠道客户终端用户备忘（可选，暂未使用）


def _get_customer_or_404(db: Session, customer_id: int) -> Customer:
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")
    return customer


@router.get("/{customer_id}/resources", summary="该客户已关联的货源列表")
def list_customer_resources(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    _get_customer_or_404(db, customer_id)
    rows = (
        db.query(CustomerResource, Resource)
        .join(Resource, Resource.id == CustomerResource.resource_id)
        .filter(CustomerResource.customer_id == customer_id)
        .order_by(CustomerResource.id.desc())
        .all()
    )
    return [
        {
            "id": link.id,
            "resource_id": res.id,
            "resource_code": res.resource_code,
            "cloud_provider": res.cloud_provider,
            "account_name": res.account_name,
            "identifier_field": res.identifier_field,
            "end_user_label": getattr(link, "end_user_label", None)
            or getattr(link, "note", None),
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
        for link, res in rows
    ]


@router.post("/{customer_id}/resources", summary="批量关联货源（自动去重）")
def add_customer_resources(
    customer_id: int,
    body: LinkCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
) -> Any:
    _get_customer_or_404(db, customer_id)

    if not body.resource_ids:
        return {"created": 0, "skipped": 0}

    # 校验 resource 存在
    existing_resources = {
        r.id for r in db.query(Resource.id).filter(
            Resource.id.in_(body.resource_ids),
            Resource.is_deleted == False,  # noqa: E712
        ).all()
    }
    # 已关联的 resource_id
    already_linked = {
        cr.resource_id for cr in db.query(CustomerResource.resource_id).filter(
            CustomerResource.customer_id == customer_id,
            CustomerResource.resource_id.in_(body.resource_ids),
        ).all()
    }

    created = 0
    skipped = 0
    created_by = str(getattr(user, "sub", None) or getattr(user, "id", "") or "")[:200] or None
    for rid in body.resource_ids:
        if rid not in existing_resources or rid in already_linked:
            skipped += 1
            continue
        link = CustomerResource(
            customer_id=customer_id,
            resource_id=rid,
            created_by=created_by,
        )
        # end_user_label 写入 note 字段（现有模型字段名为 note）
        if body.end_user_label:
            if hasattr(link, "end_user_label"):
                link.end_user_label = body.end_user_label
            elif hasattr(link, "note"):
                link.note = body.end_user_label
        db.add(link)
        created += 1

    if created:
        db.commit()
    return {"created": created, "skipped": skipped}


@router.delete("/{customer_id}/resources/{link_id}", summary="取消关联")
def delete_customer_resource(
    customer_id: int,
    link_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
) -> Any:
    link = db.query(CustomerResource).filter(
        CustomerResource.id == link_id,
        CustomerResource.customer_id == customer_id,
    ).first()
    if not link:
        raise HTTPException(404, "关联记录不存在")
    db.delete(link)
    db.commit()
    return {"ok": True}
