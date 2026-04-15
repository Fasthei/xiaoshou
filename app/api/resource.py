from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.resource import Resource
from app.schemas.resource import (
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceListResponse
)

router = APIRouter(prefix="/api/resources", tags=["货源管理"])


@router.post("", response_model=ResourceResponse, summary="创建货源")
def create_resource(resource: ResourceCreate, db: Session = Depends(get_db)):
    """创建新货源"""
    # 检查货源编号是否已存在
    existing = db.query(Resource).filter(
        Resource.resource_code == resource.resource_code,
        Resource.is_deleted == False
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="货源编号已存在")

    db_resource = Resource(**resource.model_dump())
    # 计算可分配数量
    if db_resource.total_quantity:
        db_resource.available_quantity = db_resource.total_quantity - db_resource.allocated_quantity

    db.add(db_resource)
    db.commit()
    db.refresh(db_resource)
    return db_resource


@router.get("/{resource_id}", response_model=ResourceResponse, summary="查询货源详情")
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    """根据ID查询货源详情"""
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.is_deleted == False
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="货源不存在")
    return resource


@router.put("/{resource_id}", response_model=ResourceResponse, summary="更新货源信息")
def update_resource(
    resource_id: int,
    resource_update: ResourceUpdate,
    db: Session = Depends(get_db)
):
    """更新货源信息"""
    resource = db.query(Resource).filter(
        Resource.id == resource_id,
        Resource.is_deleted == False
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="货源不存在")

    update_data = resource_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(resource, field, value)

    # 重新计算可分配数量
    if resource.total_quantity:
        resource.available_quantity = resource.total_quantity - resource.allocated_quantity

    db.commit()
    db.refresh(resource)
    return resource


@router.get("", response_model=ResourceListResponse, summary="货源列表查询")
def list_resources(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    resource_type: Optional[str] = Query(None, description="货源类型"),
    cloud_provider: Optional[str] = Query(None, description="云厂商"),
    resource_status: Optional[str] = Query(None, description="状态"),
    available_only: bool = Query(False, description="仅显示可分配货源"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    db: Session = Depends(get_db)
):
    """分页查询货源列表，支持筛选"""
    query = db.query(Resource).filter(Resource.is_deleted == False)

    if resource_type:
        query = query.filter(Resource.resource_type == resource_type)
    if cloud_provider:
        query = query.filter(Resource.cloud_provider == cloud_provider)
    if resource_status:
        query = query.filter(Resource.resource_status == resource_status)
    if available_only:
        query = query.filter(Resource.available_quantity > 0)
    if keyword:
        query = query.filter(
            (Resource.resource_code.ilike(f"%{keyword}%")) |
            (Resource.account_name.ilike(f"%{keyword}%"))
        )

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return {"total": total, "items": items}


@router.get("/available", response_model=ResourceListResponse, summary="查询可分配货源")
def get_available_resources(
    resource_type: Optional[str] = Query(None, description="货源类型"),
    cloud_provider: Optional[str] = Query(None, description="云厂商"),
    min_quantity: int = Query(1, description="最小可分配数量"),
    db: Session = Depends(get_db)
):
    """查询可分配的货源"""
    query = db.query(Resource).filter(
        Resource.is_deleted == False,
        Resource.resource_status == "AVAILABLE",
        Resource.available_quantity >= min_quantity
    )

    if resource_type:
        query = query.filter(Resource.resource_type == resource_type)
    if cloud_provider:
        query = query.filter(Resource.cloud_provider == cloud_provider)

    items = query.all()
    return {"total": len(items), "items": items}
