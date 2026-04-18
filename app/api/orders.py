"""POST /api/orders — 多货源订单 + 合同一体化创建 endpoint.

前端客户管理"新建客户 + 新建订单"wizard 提交到此. 单次 multipart/form-data 请求
原子创建:
  - Customer (如 customer_id 为空则新建)
  - N 个 Allocation (approval_status='pending', 包含 end_user_label)
  - 1 个 Contract (文件如有则上传 Azure Blob, 否则只落 metadata)

产品规则: CLAUDE.md 3.1 (订单需审批 + 入口在客户管理 + 多货源 + 必须上传合同)
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.resource import Resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["订单管理"])


@router.get("", summary="订单列表 (allocations 的别名)")
def list_orders(
    page: int = 1,
    page_size: int = 20,
    approval_status: Optional[str] = None,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    """前端 /orders 调用此端点；语义同 GET /api/allocations，仅返回订单列表视图。"""
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    q = db.query(Allocation).filter(Allocation.is_deleted == False)  # noqa: E712
    if approval_status:
        q = q.filter(Allocation.approval_status == approval_status)
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": items}


def _gen_allocation_code() -> str:
    return f"ALLOC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(2).upper()}"


def _gen_contract_code() -> str:
    return f"CN-{datetime.now().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


@router.post("", summary="新建订单 (可选新建客户 + 多货源 + 合同一体化)")
async def create_order(
    customer_id: Optional[int] = Form(None),
    customer_json: Optional[str] = Form(None, description="新建客户的 JSON 文本"),
    resources_json: str = Form(..., description="货源数组 JSON: [{resource_id, quantity, end_user_label?}]"),
    contract_code: Optional[str] = Form(None),
    contract_title: Optional[str] = Form(None),
    contract_amount: Optional[str] = Form(None),
    contract_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """原子性创建: Customer (可选) + N 个 Allocation + 1 个 Contract."""

    # ------- 1. 解析 body -------
    if not customer_id and not customer_json:
        raise HTTPException(400, "customer_id 与 customer_json 至少传一个")
    try:
        resources = json.loads(resources_json)
    except Exception:
        raise HTTPException(400, "resources_json 不是合法 JSON")
    if not isinstance(resources, list) or len(resources) == 0:
        raise HTTPException(400, "resources 至少一条")

    # ------- 2. 准备客户 -------
    try:
        if customer_id:
            customer = db.query(Customer).filter(
                Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
            ).first()
            if not customer:
                raise HTTPException(404, f"客户 {customer_id} 不存在")
        else:
            cdata = json.loads(customer_json) if customer_json else {}
            # customer_code 改可选 (手工建客户可不填, gongdan 同步后回填)
            if not cdata.get("customer_name"):
                raise HTTPException(400, "新建客户至少需要 customer_name")
            # 仅在提供了 customer_code 时去重 (None 时 IS NULL 会匹配所有 NULL)
            if cdata.get("customer_code"):
                dup = db.query(Customer).filter(
                    Customer.customer_code == cdata["customer_code"],
                    Customer.is_deleted == False,  # noqa: E712
                ).first()
                if dup:
                    raise HTTPException(400, f"客户编号 {cdata['customer_code']} 已存在")
            customer = Customer(
                customer_code=cdata.get("customer_code"),
                customer_name=cdata["customer_name"],
                customer_status=cdata.get("customer_status") or "potential",
                customer_type=cdata.get("customer_type") or "direct",
                referrer=cdata.get("referrer"),
                channel_notes=cdata.get("channel_notes"),
                industry=cdata.get("industry"),
                region=cdata.get("region"),
                customer_short_name=cdata.get("customer_short_name"),
            )
            db.add(customer)
            db.flush()  # 拿 customer.id 但不提交

        # ------- 3. 逐条建 Allocation -------
        allocation_ids: list[int] = []
        for idx, line in enumerate(resources):
            rid = line.get("resource_id")
            qty = int(line.get("quantity") or 1)
            if not rid:
                raise HTTPException(400, f"resources[{idx}].resource_id 缺失")
            res = db.query(Resource).filter(
                Resource.id == rid, Resource.is_deleted == False,  # noqa: E712
            ).first()
            if not res:
                raise HTTPException(404, f"货源 {rid} 不存在")

            unit_price = Decimal(str(line.get("unit_price") or 0))
            unit_cost = res.unit_cost or Decimal(0)
            total_cost = unit_cost * qty
            total_price = unit_price * qty
            profit_amount = total_price - total_cost
            profit_rate = (
                (profit_amount / total_price * 100) if total_price > 0 else Decimal(0)
            )

            alloc = Allocation(
                allocation_code=_gen_allocation_code(),
                customer_id=customer.id,
                resource_id=rid,
                allocated_quantity=qty,
                unit_cost=unit_cost,
                unit_price=unit_price,
                total_cost=total_cost,
                total_price=total_price,
                profit_amount=profit_amount,
                profit_rate=profit_rate,
                allocation_status="PENDING",
                allocated_by=getattr(user, "id", None),
                allocated_at=datetime.utcnow(),
                remark=line.get("remark"),
                end_user_label=line.get("end_user_label"),
                # 订单审批: 新建默认 pending
                approval_status="pending",
            )
            db.add(alloc)
            db.flush()
            allocation_ids.append(alloc.id)

        # ------- 4. 合同 -------
        contract_id: Optional[int] = None
        if contract_code or contract_title or contract_file:
            file_url = None
            file_name = None
            file_size = None
            mime_type = None
            if contract_file:
                file_name = contract_file.filename
                mime_type = contract_file.content_type
                content = await contract_file.read()
                file_size = len(content)
                # Azure Blob 上传 (best-effort, 如果未配则只落 metadata)
                try:
                    from app.integrations.azure_blob import upload_bytes
                    _, file_url = upload_bytes(
                        content,
                        filename=file_name or "contract.bin",
                        content_type=mime_type or "application/octet-stream",
                        prefix=f"customer-{customer.id}",
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "Azure Blob 上传失败, 只落 metadata (customer=%s, file=%s): %s",
                        customer.id, file_name, e,
                    )

            amount_dec = None
            if contract_amount:
                try:
                    amount_dec = Decimal(contract_amount)
                except Exception:
                    amount_dec = None

            ct = Contract(
                customer_id=customer.id,
                contract_code=contract_code or _gen_contract_code(),
                title=contract_title,
                amount=amount_dec,
                status="active",
                file_url=file_url,
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
            )
            db.add(ct)
            db.flush()
            contract_id = ct.id

        db.commit()
        return {
            "customer_id": customer.id,
            "customer_code": customer.customer_code,
            "customer_name": customer.customer_name,
            "order_id": allocation_ids[0] if allocation_ids else None,
            "allocation_ids": allocation_ids,
            "contract_id": contract_id,
            "approval_status": "pending",
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.exception("create_order failed")
        raise HTTPException(500, f"订单创建失败: {e}")
