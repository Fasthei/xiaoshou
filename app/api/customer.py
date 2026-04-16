from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.customer import Customer, CustomerContact
from app.models.sales import SalesUser
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
    CustomerContactCreate,
    CustomerContactResponse
)


def _attach_sales_user_name(customer: Customer, db: Session) -> Customer:
    """Attach sales_user_name onto customer object (non-persistent attr)."""
    if customer is None:
        return customer
    if getattr(customer, "sales_user_id", None):
        su = db.query(SalesUser).filter(SalesUser.id == customer.sales_user_id).first()
        customer.sales_user_name = su.name if su else None
    else:
        customer.sales_user_name = None
    return customer

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


@router.post("", response_model=CustomerResponse, summary="创建客户")
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    """创建新客户"""
    # 检查客户编号是否已存在
    existing = db.query(Customer).filter(
        Customer.customer_code == customer.customer_code,
        Customer.is_deleted == False
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="客户编号已存在")

    db_customer = Customer(**customer.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


@router.get("/{customer_id}", response_model=CustomerResponse, summary="查询客户详情")
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    """根据ID查询客户详情"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    return _attach_sales_user_name(customer, db)


@router.put("/{customer_id}", response_model=CustomerResponse, summary="更新客户信息")
def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    db: Session = Depends(get_db)
):
    """更新客户信息"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    update_data = customer_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer


@router.get("", response_model=CustomerListResponse, summary="客户列表查询")
def list_customers(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    customer_status: Optional[str] = Query(None, description="客户状态"),
    industry: Optional[str] = Query(None, description="所属行业"),
    sales_user_id: Optional[int] = Query(None, description="所属销售"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    db: Session = Depends(get_db)
):
    """分页查询客户列表，支持筛选"""
    query = db.query(Customer).filter(Customer.is_deleted == False)

    if customer_status:
        query = query.filter(Customer.customer_status == customer_status)
    if industry:
        query = query.filter(Customer.industry == industry)
    if sales_user_id:
        query = query.filter(Customer.sales_user_id == sales_user_id)
    if keyword:
        query = query.filter(
            (Customer.customer_name.ilike(f"%{keyword}%")) |
            (Customer.customer_code.ilike(f"%{keyword}%"))
        )

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    # Batch attach sales_user_name to avoid N+1
    sales_ids = {c.sales_user_id for c in items if c.sales_user_id}
    sales_map = {}
    if sales_ids:
        sales_rows = db.query(SalesUser).filter(SalesUser.id.in_(sales_ids)).all()
        sales_map = {s.id: s.name for s in sales_rows}
    for c in items:
        c.sales_user_name = sales_map.get(c.sales_user_id) if c.sales_user_id else None

    return {"total": total, "items": items}


@router.post("/{customer_id}/contacts", response_model=CustomerContactResponse, summary="添加客户联系人")
def add_customer_contact(
    customer_id: int,
    contact: CustomerContactCreate,
    db: Session = Depends(get_db)
):
    """为客户添加联系人"""
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    db_contact = CustomerContact(**contact.model_dump(), customer_id=customer_id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return db_contact
