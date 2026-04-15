from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timedelta, date
from decimal import Decimal
from app.database import get_db
from app.models.usage import UsageRecord
from app.models.customer import Customer
from app.schemas.usage import (
    UsageRecordResponse,
    UsageListResponse,
    UsageSummaryResponse,
    UsageTrendResponse
)

router = APIRouter(prefix="/api/usage", tags=["用量查询"])


@router.get("/customer/{customer_id}", response_model=UsageListResponse, summary="查询客户用量")
def get_customer_usage(
    customer_id: int,
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """查询客户的用量记录"""
    # 验证客户存在
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    query = db.query(UsageRecord).filter(UsageRecord.customer_id == customer_id)

    if start_date:
        query = query.filter(UsageRecord.usage_date >= start_date)
    if end_date:
        query = query.filter(UsageRecord.usage_date <= end_date)

    query = query.order_by(UsageRecord.usage_date.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "items": items}


@router.get("/resource/{resource_id}", response_model=UsageListResponse, summary="查询货源用量")
def get_resource_usage(
    resource_id: int,
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db)
):
    """查询货源的用量记录"""
    query = db.query(UsageRecord).filter(UsageRecord.resource_id == resource_id)

    if start_date:
        query = query.filter(UsageRecord.usage_date >= start_date)
    if end_date:
        query = query.filter(UsageRecord.usage_date <= end_date)

    query = query.order_by(UsageRecord.usage_date.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "items": items}


@router.get("/customer/{customer_id}/summary", response_model=UsageSummaryResponse, summary="客户用量汇总")
def get_customer_usage_summary(
    customer_id: int,
    start_date: Optional[date] = Query(None, description="开始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    db: Session = Depends(get_db)
):
    """查询客户用量汇总信息"""
    # 验证客户存在
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    # 默认查询最近30天
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).date()
    if not end_date:
        end_date = datetime.now().date()

    result = db.query(
        func.sum(UsageRecord.usage_amount).label("total_usage"),
        func.sum(UsageRecord.usage_cost).label("total_cost"),
        func.count(UsageRecord.id).label("record_count")
    ).filter(
        UsageRecord.customer_id == customer_id,
        UsageRecord.usage_date >= start_date,
        UsageRecord.usage_date <= end_date
    ).first()

    return {
        "customer_id": customer_id,
        "total_usage": result.total_usage or Decimal(0),
        "total_cost": result.total_cost or Decimal(0),
        "record_count": result.record_count or 0,
        "start_date": start_date,
        "end_date": end_date
    }


@router.get("/customer/{customer_id}/trend", response_model=list[UsageTrendResponse], summary="客户用量趋势")
def get_customer_usage_trend(
    customer_id: int,
    days: int = Query(30, ge=1, le=365, description="查询天数"),
    db: Session = Depends(get_db)
):
    """查询客户用量趋势"""
    # 验证客户存在
    customer = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.is_deleted == False
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="客户不存在")

    start_date = (datetime.now() - timedelta(days=days)).date()

    results = db.query(
        func.date(UsageRecord.usage_date).label("date"),
        func.sum(UsageRecord.usage_amount).label("usage_amount"),
        func.sum(UsageRecord.usage_cost).label("usage_cost")
    ).filter(
        UsageRecord.customer_id == customer_id,
        UsageRecord.usage_date >= start_date
    ).group_by(
        func.date(UsageRecord.usage_date)
    ).order_by(
        func.date(UsageRecord.usage_date)
    ).all()

    return [
        {
            "date": result.date,
            "usage_amount": result.usage_amount or Decimal(0),
            "usage_cost": result.usage_cost or Decimal(0)
        }
        for result in results
    ]
