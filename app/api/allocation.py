from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from decimal import Decimal
from app.database import get_db
from app.models.allocation import Allocation
from app.models.customer import Customer
from app.models.resource import Resource
from app.schemas.allocation import (
    AllocationCreate,
    AllocationUpdate,
    AllocationResponse,
    AllocationListResponse,
    AllocationProfitResponse
)

router = APIRouter(prefix="/api/allocations", tags=["分配管理"])


def generate_allocation_code() -> str:
    """生成分配编号"""
    return f"ALLOC-{datetime.now().strftime('%Y%m%d%H%M%S')}"


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
        remark=allocation.remark
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

    for field, value in update_data.items():
        setattr(allocation, field, value)

    db.commit()
    db.refresh(allocation)
    return allocation


@router.get("", response_model=AllocationListResponse, summary="分配列表查询")
def list_allocations(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    customer_id: Optional[int] = Query(None, description="客户ID"),
    resource_id: Optional[int] = Query(None, description="货源ID"),
    allocation_status: Optional[str] = Query(None, description="分配状态"),
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

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "items": items}


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
