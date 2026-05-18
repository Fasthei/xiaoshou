from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func as sa_func
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

router = APIRouter(prefix="/api/resources", tags=["货源看板"])


@router.get("/summary", summary="货源聚合看板数据")
def get_resource_summary(db: Session = Depends(get_db)):
    """货源看板聚合数据: 总数 / 按状态 / 按云厂商 / Top 10 可用货源。

    Note: This static route MUST be registered before /{resource_id}
    so FastAPI does not try to parse 'summary' as an int resource_id.
    """
    base = db.query(Resource).filter(Resource.is_deleted == False)
    all_items = base.all()

    total = len(all_items)

    by_status: dict[str, int] = {}
    for it in all_items:
        key = it.resource_status or "UNKNOWN"
        by_status[key] = by_status.get(key, 0) + 1

    # 以云管 (cloudcost) 的 ServiceAccount 为准 —— 云管那边每个云账号就是一个资源单元,
    # 没有配额/数量字段 (total_quantity / allocated_quantity / available_quantity 在
    # xiaoshou 本地都是 NULL, 不能拿来乱加乘). 看板只按 status 维度聚合账号数.

    # by provider aggregation: total 数 + 按 status 桶分
    # 口径统一: 顶部 KPI "可用" 和 by_provider[*].available 都取
    # resource_status == "AVAILABLE" 的 account 行数 (is_deleted=False), 跟
    # by_status["AVAILABLE"] 一致, 不从本地 available_quantity 再算一遍, 否则
    # 前端会出现 "顶部可用 8, 分厂商 available 全是 0" 这种对不上的情况。
    prov_map: dict[str, dict] = {}
    for it in all_items:
        p = it.cloud_provider or "UNKNOWN"
        row = prov_map.setdefault(p, {
            "provider": p, "total": 0, "available": 0, "by_status": {},
        })
        st = it.resource_status or "UNKNOWN"
        row["by_status"][st] = row["by_status"].get(st, 0) + 1
        row["total"] = row["total"] + 1
        if st == "AVAILABLE":
            row["available"] = row["available"] + 1

    by_provider = sorted(prov_map.values(), key=lambda r: r["total"], reverse=True)

    # Top 10 最新同步的 AVAILABLE 账号 (仅作下拉/参考用途, 不返回 available_quantity
    # 因为云管没这个字段, 本地凑的值没意义).
    top_items = sorted(
        [it for it in all_items if it.resource_status == "AVAILABLE"],
        key=lambda it: it.last_sync_time or it.created_at, reverse=True,
    )[:10]
    top_available = [{
        "id": it.id,
        "resource_code": it.resource_code,
        "account_name": it.account_name,
        "provider": it.cloud_provider,
    } for it in top_items]

    # CLAUDE.md §3.2: 只展示 status 维度聚合，不暴露本地凑的 quantity 列
    # (total_quantity/allocated_quantity/available_quantity). 顶层 `total` /
    # `available` 与 by_provider[*].total / .available 是**账号数**计数
    # (= len of ServiceAccount 行)，不是凑出来的数量，仍符合 §3.2 的
    # "只按 status 维度聚合账号数"口径。口径不变量:
    #   data["available"] == data["by_status"]["AVAILABLE"]
    #                    == sum(p["available"] for p in data["by_provider"])
    return {
        "total": total,
        "available": by_status.get("AVAILABLE", 0),
        "by_status": by_status,
        "by_provider": by_provider,
        "top_available": top_available,
    }


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
    # 计算可分配数量 (allocated_quantity 的 default=0 只在 flush 时生效, Python
    # 侧新建对象时为 None, 先显式归零再减)
    if db_resource.allocated_quantity is None:
        db_resource.allocated_quantity = 0
    if db_resource.total_quantity is not None:
        db_resource.available_quantity = db_resource.total_quantity - db_resource.allocated_quantity

    db.add(db_resource)
    db.commit()
    db.refresh(db_resource)
    return db_resource


@router.get("/available", response_model=ResourceListResponse, summary="查询可分配货源")
def _get_available_resources_early(
    resource_type: Optional[str] = Query(None, description="货源类型"),
    cloud_provider: Optional[str] = Query(None, description="云厂商"),
    min_quantity: int = Query(1, description="最小可分配数量"),
    db: Session = Depends(get_db),
):
    """Must be registered BEFORE /{resource_id} so FastAPI does not try to
    parse 'available' as an int resource_id. (Old duplicate at bottom of file
    was unreachable for this reason — kept there as dead code for diff clarity.)
    """
    query = db.query(Resource).filter(
        Resource.is_deleted == False,
        Resource.resource_status == "AVAILABLE",
        Resource.available_quantity >= min_quantity,
    )
    if resource_type:
        query = query.filter(Resource.resource_type == resource_type)
    if cloud_provider:
        query = query.filter(Resource.cloud_provider == cloud_provider)
    items = query.all()
    return {"total": len(items), "items": items}


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
