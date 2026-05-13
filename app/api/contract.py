"""Contract API — list contracts per customer, create contract, upload/list/delete
multiple file attachments per contract."""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.integrations import azure_blob
from app.models.contract import Contract
from app.models.contract_attachment import ContractAttachment
from app.models.customer import Customer

logger = logging.getLogger(__name__)

# Upload limits / whitelist
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB / 单文件
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}


# ---------- Schemas ----------
class AttachmentResponse(BaseModel):
    id: int
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


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


class ContractUpdate(BaseModel):
    """合同元数据局部更新 — contract_code 不可改 (业务唯一标识)。"""
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ContractResponse(ContractBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    attachments: List[AttachmentResponse] = []

    class Config:
        from_attributes = True


class ContractListResponse(BaseModel):
    total: int
    items: list[ContractResponse]


class DownloadResponse(BaseModel):
    url: str
    expires_in: int = 600


class UploadUrlResponse(BaseModel):
    sas_url: str
    blob_name: str
    expires_at: str  # ISO-8601 UTC


class UploadConfirmRequest(BaseModel):
    blob_name: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    file_name: Optional[str] = None


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


@router.get("", response_model=ContractListResponse, summary="合同列表 (全局, 分页+过滤)")
def list_contracts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="合同号/标题模糊搜索"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    """全局合同列表 —— 没有该端点前端会 405。customer-scoped
    `/api/customers/{id}/contracts` 仍然保留。"""
    q = db.query(Contract)
    if customer_id is not None:
        q = q.filter(Contract.customer_id == customer_id)
    if status:
        q = q.filter(Contract.status == status)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(or_(Contract.contract_code.ilike(kw), Contract.title.ilike(kw)))
    total = q.count()
    items = (
        q.order_by(Contract.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": items}


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


@router.delete(
    "/{contract_id}",
    status_code=204,
    summary="删除合同 (清除全部附件 Blob + 级联删除 attachment 行)",
)
def delete_contract(
    contract_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    # 清 Blob (best-effort), DB 关系 cascade='all, delete-orphan' 自动删 attachment 行
    if azure_blob.is_configured():
        for att in list(contract.attachments or []):
            if att.file_url:
                azure_blob.delete_blob(att.file_url)
    db.delete(contract)
    db.commit()
    return None


@router.patch(
    "/{contract_id}",
    response_model=ContractResponse,
    summary="更新合同元数据 (标题/金额/起止/状态/备注)",
)
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="合同不存在")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(contract, k, v)
    db.commit()
    db.refresh(contract)
    return contract


# ---------- File upload / download / delete ----------
def _get_contract_or_404(contract_id: int, db: Session) -> Contract:
    c = db.query(Contract).filter(Contract.id == contract_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="合同不存在")
    return c


def _get_attachment_or_404(contract_id: int, att_id: int, db: Session) -> ContractAttachment:
    a = db.query(ContractAttachment).filter(
        ContractAttachment.id == att_id,
        ContractAttachment.contract_id == contract_id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="附件不存在")
    return a


def _infer_ext(filename: str) -> str:
    import os as _os
    _, ext = _os.path.splitext(filename or "")
    return ext.lower()


def _validate_type(mime: str, ext: str) -> None:
    if mime not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {mime or ext or '未知'}，仅支持 PDF/Word/JPG/PNG",
        )


@router.post(
    "/{contract_id}/upload",
    response_model=AttachmentResponse,
    summary="上传单个合同附件 (PDF/Word/图片, ≤100MB), 追加而非替换",
)
async def upload_contract_file(
    contract_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    contract = _get_contract_or_404(contract_id, db)

    mime = (file.content_type or "").lower()
    ext = _infer_ext(file.filename or "")
    _validate_type(mime, ext)

    data = await file.read()
    size = len(data)
    if size == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    if size > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 上限",
        )

    if not azure_blob.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage 未配置 (AZURE_STORAGE_CONNECTION_STRING)",
        )

    try:
        _, blob_url = azure_blob.upload_bytes(
            data,
            filename=file.filename or f"contract-{contract_id}{ext or '.bin'}",
            content_type=mime or "application/octet-stream",
            prefix=f"contract/{contract.id}",
        )
    except Exception as e:
        logger.exception("contract upload: blob upload failed: %s", e)
        raise HTTPException(status_code=502, detail=f"上传 Blob 失败: {e}")

    att = ContractAttachment(
        contract_id=contract.id,
        file_url=blob_url,
        file_name=file.filename,
        file_size=size,
        mime_type=mime or None,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.post(
    "/{contract_id}/uploads",
    response_model=List[AttachmentResponse],
    summary="批量上传合同附件 (单文件 ≤100MB)",
)
async def upload_contract_files(
    contract_id: int,
    files: List[UploadFile] = File(..., description="多文件 multipart, 字段名 files"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    contract = _get_contract_or_404(contract_id, db)

    if not azure_blob.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage 未配置 (AZURE_STORAGE_CONNECTION_STRING)",
        )

    created: list[ContractAttachment] = []
    for f in files:
        mime = (f.content_type or "").lower()
        ext = _infer_ext(f.filename or "")
        _validate_type(mime, ext)

        data = await f.read()
        size = len(data)
        if size == 0:
            raise HTTPException(status_code=400, detail=f"文件为空: {f.filename}")
        if size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"文件 {f.filename} 超过 {MAX_UPLOAD_SIZE // (1024 * 1024)}MB 上限",
            )

        try:
            _, blob_url = azure_blob.upload_bytes(
                data,
                filename=f.filename or f"contract-{contract_id}{ext or '.bin'}",
                content_type=mime or "application/octet-stream",
                prefix=f"contract/{contract.id}",
            )
        except Exception as e:
            logger.exception("contract upload: blob upload failed: %s", e)
            raise HTTPException(status_code=502, detail=f"上传 Blob 失败: {e}")

        att = ContractAttachment(
            contract_id=contract.id,
            file_url=blob_url,
            file_name=f.filename,
            file_size=size,
            mime_type=mime or None,
        )
        db.add(att)
        created.append(att)

    db.commit()
    for a in created:
        db.refresh(a)
    return created


UPLOAD_SAS_TTL_MINUTES = 15


@router.get(
    "/{contract_id}/upload-url",
    response_model=UploadUrlResponse,
    summary="获取合同附件 SAS 直传 URL (15 分钟有效, write+create)",
)
def get_contract_upload_url(
    contract_id: int,
    filename: str = Query(..., description="原始文件名, 用于生成 blob 路径"),
    content_type: str = Query("application/octet-stream", description="MIME 类型"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    _get_contract_or_404(contract_id, db)

    ext = _infer_ext(filename)
    mime = content_type.lower()
    _validate_type(mime, ext)

    if not azure_blob.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage 未配置 (AZURE_STORAGE_CONNECTION_STRING)",
        )

    import os as _os
    safe_name = _os.path.basename(filename).replace("/", "_")
    import uuid as _uuid
    blob_name = f"contract/{contract_id}/{_uuid.uuid4().hex}-{safe_name}"

    try:
        sas_url, expires_at = azure_blob.generate_upload_sas(
            blob_name,
            content_type=mime,
            ttl_minutes=UPLOAD_SAS_TTL_MINUTES,
        )
    except Exception as e:
        logger.exception("contract upload-url: SAS generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"生成上传链接失败: {e}")

    return UploadUrlResponse(
        sas_url=sas_url,
        blob_name=blob_name,
        expires_at=expires_at.isoformat(),
    )


@router.post(
    "/{contract_id}/upload-confirm",
    response_model=AttachmentResponse,
    summary="确认 SAS 直传完成 → 追加为该合同的一条 attachment",
)
def confirm_contract_upload(
    contract_id: int,
    payload: UploadConfirmRequest,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    contract = _get_contract_or_404(contract_id, db)

    if not azure_blob.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Azure Blob Storage 未配置 (AZURE_STORAGE_CONNECTION_STRING)",
        )

    if not azure_blob.head_blob(payload.blob_name):
        raise HTTPException(
            status_code=422,
            detail=f"Blob '{payload.blob_name}' 尚不存在，请确认上传已完成",
        )

    file_url = azure_blob.blob_url(payload.blob_name)

    att = ContractAttachment(
        contract_id=contract.id,
        file_url=file_url,
        file_name=payload.file_name or payload.blob_name.split("/")[-1],
        file_size=payload.file_size,
        mime_type=(payload.content_type or None),
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


@router.get(
    "/{contract_id}/attachments",
    response_model=List[AttachmentResponse],
    summary="列出合同的全部附件",
)
def list_contract_attachments(
    contract_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    _get_contract_or_404(contract_id, db)
    return (
        db.query(ContractAttachment)
        .filter(ContractAttachment.contract_id == contract_id)
        .order_by(ContractAttachment.created_at.asc())
        .all()
    )


@router.get(
    "/{contract_id}/attachments/{attachment_id}/download",
    response_model=DownloadResponse,
    summary="生成附件下载 URL (10 分钟 SAS)",
)
def download_attachment(
    contract_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    att = _get_attachment_or_404(contract_id, attachment_id, db)
    if not azure_blob.is_configured():
        raise HTTPException(status_code=503, detail="Azure Blob Storage 未配置")
    try:
        url = azure_blob.sas_url(att.file_url, download_filename=att.file_name)
    except Exception as e:
        logger.exception("contract attachment download SAS failed: %s", e)
        raise HTTPException(status_code=502, detail=f"生成下载链接失败: {e}")
    return DownloadResponse(url=url, expires_in=azure_blob.SAS_TTL_MINUTES * 60)


@router.delete(
    "/{contract_id}/attachments/{attachment_id}",
    status_code=204,
    summary="删除单个附件 (移除 Blob + 删除 attachment 行)",
)
def delete_attachment(
    contract_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    att = _get_attachment_or_404(contract_id, attachment_id, db)
    if att.file_url and azure_blob.is_configured():
        azure_blob.delete_blob(att.file_url)
    db.delete(att)
    db.commit()
    return None
