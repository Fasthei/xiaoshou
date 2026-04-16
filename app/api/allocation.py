import secrets
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from decimal import Decimal
from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.allocation_history import AllocationHistory
from app.models.customer import Customer
from app.models.resource import Resource
from app.schemas.allocation import (
    AllocationCreate,
    AllocationUpdate,
    AllocationResponse,
    AllocationListResponse,
    AllocationProfitResponse,
    AllocationApprovalRequest,
)
from app.schemas.allocation_history import AllocationHistoryOut, CancelAllocationBody
from app.models.sales import SalesUser
from typing import List as _List

router = APIRouter(prefix="/api/allocations", tags=["分配管理"])


def generate_allocation_code() -> str:
    """生成分配编号 (秒级时间戳 + 4 位随机后缀, 避免同秒并发碰撞)"""
    suffix = secrets.token_hex(2).upper()  # 4 hex chars
    return f"ALLOC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{suffix}"


def calculate_profit(unit_cost: Decimal, unit_price: Decimal, quantity: int):
    """计算毛利"""
    total_cost = unit_cost * quantity
    total_price = unit_price * quantity
    profit_amount = total_price - total_cost
    profit_rate = (profit_amount / total_cost * 100) if total_cost > 0 else Decimal(0)
    return {
        "total_cost": total_cost,
        "total_price": total_price,
        "profit_amount": profit_amount,
        "profit_rate": profit_rate
    }


@router.post("", response_model=AllocationResponse, summary="创建分配")
def create_allocation(allocation: AllocationCreate, db: Session = Depends(get_db)):
    """创建货源分配"""
    # 验证客户存在
    customer = db.query(Customer).filter(
        Customer.id == allocation.customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 验证货源存在且可分配
    resource = db.query(Resource).filter(
        Resource.id == allocation.resource_id,
        Resource.is_deleted == False
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="货源不存在")

    if resource.available_quantity is None or resource.available_quantity < allocation.allocated_quantity:
        raise HTTPException(status_code=400, detail="货源可分配数量不足")

    # 创建分配记录
    allocation_code = generate_allocation_code()
    unit_cost = resource.unit_cost or Decimal(0)

    # 计算毛利
    profit_data = calculate_profit(unit_cost, allocation.unit_price, allocation.allocated_quantity)

    db_allocation = Allocation(
        allocation_code=allocation_code,
        customer_id=allocation.customer_id,
        resource_id=allocation.resource_id,
        allocated_quantity=allocation.allocated_quantity,
        unit_cost=unit_cost,
        unit_price=allocation.unit_price,
        total_cost=profit_data["total_cost"],
        total_price=profit_data["total_price"],
        profit_amount=profit_data["profit_amount"],
        profit_rate=profit_data["profit_rate"],
        allocation_status="PENDING",
        allocated_at=datetime.now(),
        remark=allocation.remark,
        approval_status="pending",
    )

    # 更新货源已分配数量
    resource.allocated_quantity += allocation.allocated_quantity
    resource.available_quantity = resource.total_quantity - resource.allocated_quantity

    # 更新客户资源数量
    customer.current_resource_count += 1

    db.add(db_allocation)
    db.commit()
    db.refresh(db_allocation)
    return db_allocation


@router.get("/{allocation_id}", response_model=AllocationResponse, summary="查询分配详情")
def get_allocation(allocation_id: int, db: Session = Depends(get_db)):
    """根据ID查询分配详情"""
    allocation = db.query(Allocation).filter(
        Allocation.id == allocation_id,
        Allocation.is_deleted == False
    ).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="分配记录不存在")
    return allocation


@router.put("/{allocation_id}", response_model=AllocationResponse, summary="更新分配信息")
def update_allocation(
    allocation_id: int,
    allocation_update: AllocationUpdate,
    db: Session = Depends(get_db)
):
    """更新分配信息"""
    allocation = db.query(Allocation).filter(
        Allocation.id == allocation_id,
        Allocation.is_deleted == False
    ).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="分配记录不存在")

    update_data = allocation_update.model_dump(exclude_unset=True)

    # 如果更新了数量或价格，重新计算毛利
    if "allocated_quantity" in update_data or "unit_price" in update_data:
        quantity = update_data.get("allocated_quantity", allocation.allocated_quantity)
        unit_price = update_data.get("unit_price", allocation.unit_price)
        profit_data = calculate_profit(allocation.unit_cost, unit_price, quantity)
        update_data.update(profit_data)

    # Log each changed field to allocation_history
    for field, value in update_data.items():
        old_val = getattr(allocation, field, None)
        if old_val != value:
            db.add(AllocationHistory(
                allocation_id=allocation.id, field=field,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(value) if value is not None else None,
            ))
        setattr(allocation, field, value)

    db.commit()
    db.refresh(allocation)
    return allocation


@router.post("/{allocation_id}/cancel", response_model=AllocationResponse, summary="取消分配 (软)")
def cancel_allocation(
    allocation_id: int,
    body: CancelAllocationBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    allocation = db.query(Allocation).filter(
        Allocation.id == allocation_id, Allocation.is_deleted == False,  # noqa: E712
    ).first()
    if not allocation:
        raise HTTPException(404, "分配记录不存在")
    if allocation.allocation_status == "CANCELLED":
        raise HTTPException(400, "该分配已取消")

    old_status = allocation.allocation_status
    allocation.allocation_status = "CANCELLED"
    # Return resource back to the pool
    resource = db.query(Resource).filter(Resource.id == allocation.resource_id).first()
    if resource:
        resource.allocated_quantity = max(0, (resource.allocated_quantity or 0) - allocation.allocated_quantity)
        if resource.total_quantity is not None:
            resource.available_quantity = resource.total_quantity - resource.allocated_quantity
        db.add(resource)
    db.add(AllocationHistory(
        allocation_id=allocation.id, field="cancel",
        old_value=old_status, new_value="CANCELLED",
        reason=body.reason,
        operator_casdoor_id=getattr(user, "sub", None) if user else None,
    ))
    db.commit()
    db.refresh(allocation)
    return allocation


@router.get("/{allocation_id}/history", response_model=_List[AllocationHistoryOut],
            summary="单个分配的变更流水")
def get_allocation_history(
    allocation_id: int,
    db: Session = Depends(get_db),
):
    return (
        db.query(AllocationHistory)
        .filter(AllocationHistory.allocation_id == allocation_id)
        .order_by(AllocationHistory.id.desc())
        .all()
    )


@router.get("", response_model=AllocationListResponse, summary="分配列表查询")
def list_allocations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    customer_id: Optional[int] = Query(None, description="客户ID"),
    resource_id: Optional[int] = Query(None, description="货源ID"),
    allocation_status: Optional[str] = Query(None, description="分配状态"),
    approval_status: Optional[str] = Query(None, description="审批状态: pending/approved/rejected"),
    db: Session = Depends(get_db)
):
    """分页查询分配列表"""
    query = db.query(Allocation).filter(Allocation.is_deleted == False)

    if customer_id:
        query = query.filter(Allocation.customer_id == customer_id)
    if resource_id:
        query = query.filter(Allocation.resource_id == resource_id)
    if allocation_status:
        query = query.filter(Allocation.allocation_status == allocation_status)
    if approval_status:
        query = query.filter(Allocation.approval_status == approval_status)

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "items": items}


@router.patch("/{allocation_id}/approval", response_model=AllocationResponse, summary="审批分配")
def approve_allocation(
    allocation_id: int,
    body: AllocationApprovalRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """审批或拒绝一个分配。写入 approver_id / approved_at / approval_note / approval_status。"""
    if body.approval_status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="approval_status 必须是 approved 或 rejected")

    allocation = db.query(Allocation).filter(
        Allocation.id == allocation_id,
        Allocation.is_deleted == False,  # noqa: E712
    ).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="分配记录不存在")

    # 通过 casdoor_user_id 映射到本地 sales_user.id（软外键，找不到则写 None）
    approver_id: Optional[int] = None
    sub = getattr(user, "sub", None) if user else None
    if sub:
        su = db.query(SalesUser).filter(SalesUser.casdoor_user_id == sub).first()
        if su:
            approver_id = int(su.id)

    allocation.approval_status = body.approval_status
    allocation.approver_id = approver_id
    allocation.approved_at = datetime.utcnow()
    allocation.approval_note = body.approval_note

    db.commit()
    db.refresh(allocation)
    return allocation


@router.get("/{allocation_id}/profit", response_model=AllocationProfitResponse, summary="查询分配毛利")
def get_allocation_profit(allocation_id: int, db: Session = Depends(get_db)):
    """查询分配的毛利信息"""
    allocation = db.query(Allocation).filter(
        Allocation.id == allocation_id,
        Allocation.is_deleted == False
    ).first()
    if not allocation:
        raise HTTPException(status_code=404, detail="分配记录不存在")

    return {
        "allocation_id": allocation.id,
        "total_cost": allocation.total_cost,
        "total_price": allocation.total_price,
        "profit_amount": allocation.profit_amount,
        "profit_rate": allocation.profit_rate
    }
