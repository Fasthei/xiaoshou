"""Contract API — list contracts per customer, create contract."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.contract import Contract
from app.models.customer import Customer


# ---------- Schemas ----------
class ContractBase(BaseModel):
    customer_id: int = Field(..., description="客户ID")
    contract_code: str = Field(..., description="合同编号")
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = Field("active", description="active/expired/terminated")
    notes: Optional[str] = None


class ContractCreate(ContractBase):
    pass


class ContractResponse(ContractBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- Routers ----------
# Customer-scoped: GET /api/customers/{id}/contracts
customer_scoped = APIRouter(prefix="/api/customers", tags=["合同"])

# Top-level: POST /api/contracts
router = APIRouter(prefix="/api/contracts", tags=["合同"])


@customer_scoped.get(
    "/{customer_id}/contracts",
    response_model=list[ContractResponse],
    summary="查询客户合同列表",
)
def list_contracts_of_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (
        db.query(Contract)
        .filter(Contract.customer_id == customer_id)
        .order_by(Contract.created_at.desc())
        .all()
    )
    return rows


@router.post("", response_model=ContractResponse, summary="创建合同")
def create_contract(payload: ContractCreate, db: Session = Depends(get_db)):
    # Verify customer exists
    customer = db.query(Customer).filter(
        Customer.id == payload.customer_id,
        Customer.is_deleted == False,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    # Uniqueness check on contract_code
    existing = db.query(Contract).filter(Contract.contract_code == payload.contract_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="合同编号已存在")

    db_row = Contract(**payload.model_dump())
    db.add(db_row)
    db.commit()
    db.refresh(db_row)
    return db_row
