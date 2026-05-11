"""手工录入过往账单 API (customer_manual_bill).

区别于 cc_bill (云管同步) — 这里是销售/运营手工补录的账单,
所有字段都可空, 附件可选 (单文件, 支持 PDF/Word/图片)。
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.integrations import azure_blob
from app.models.customer import Customer
from app.models.customer_manual_bill import CustomerManualBill

logger = logging.getLogger(__name__)

# 上传上限与白名单, 与合同附件一致
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}


class ManualBillCreate(BaseModel):
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    bill_date: Optional[date] = None
    notes: Optional[str] = None


class ManualBillUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    bill_date: Optional[date] = None
    notes: Optional[str] = None


class ManualBillResponse(BaseModel):
    id: int
    customer_id: int
    title: Optional[str] = None
    amount: Optional[Decimal] = None
    bill_date: Optional[date] = None
    notes: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 客户作用域 endpoints
customer_scoped = APIRouter(prefix="/api/customers", tags=["手工账单"])
# 单条作用域 endpoints
router = APIRouter(prefix="/api/manual-bills", tags=["手工账单"])


def _get_customer_or_404(customer_id: int, db: Session) -> Customer:
    c = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not c:
        raise HTTPException(404, "客户不存在")
    return c


def _get_bill_or_404(bill_id: int, db: Session) -> CustomerManualBill:
    b = db.query(CustomerManualBill).filter(CustomerManualBill.id == bill_id).first()
    if not b:
        raise HTTPException(404, "账单不存在")
    return b


def _infer_ext(filename: str) -> str:
    import os as _os
    _, ext = _os.path.splitext(filename or "")
    return ext.lower()


@customer_scoped.get(
    "/{customer_id}/manual-bills",
    response_model=list[ManualBillResponse],
    summary="客户手工录入过往账单列表",
)
def list_manual_bills(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    _get_customer_or_404(customer_id, db)
    rows = (
        db.query(CustomerManualBill)
        .filter(CustomerManualBill.customer_id == customer_id)
        .order_by(CustomerManualBill.bill_date.desc().nullslast(),
                  CustomerManualBill.created_at.desc())
        .all()
    )
    return rows


@customer_scoped.post(
    "/{customer_id}/manual-bills",
    response_model=ManualBillResponse,
    summary="新建手工过往账单 (字段全部可空)",
)
def create_manual_bill(
    customer_id: int,
    payload: ManualBillCreate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    _get_customer_or_404(customer_id, db)
    row = CustomerManualBill(customer_id=customer_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch(
    "/{bill_id}",
    response_model=ManualBillResponse,
    summary="编辑手工账单元数据 (标题/金额/日期/备注)",
)
def update_manual_bill(
    bill_id: int,
    payload: ManualBillUpdate,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = _get_bill_or_404(bill_id, db)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete(
    "/{bill_id}",
    status_code=204,
    summary="删除手工账单 (附带清除 Blob)",
)
def delete_manual_bill(
    bill_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = _get_bill_or_404(bill_id, db)
    if row.file_url and azure_blob.is_configured():
        azure_blob.delete_blob(row.file_url)
    db.delete(row)
    db.commit()
    return None


@router.post(
    "/{bill_id}/upload",
    response_model=ManualBillResponse,
    summary="上传手工账单附件 (单文件 ≤100MB, 替换已有附件)",
)
async def upload_manual_bill_file(
    bill_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = _get_bill_or_404(bill_id, db)

    mime = (file.content_type or "").lower()
    ext = _infer_ext(file.filename or "")
    if mime not in ALLOWED_MIME and ext not in ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {mime or ext or '未知'}，仅支持 PDF/Word/JPG/PNG",
        )

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
            filename=file.filename or f"bill-{bill_id}{ext or '.bin'}",
            content_type=mime or "application/octet-stream",
            prefix=f"manual-bill/{row.id}",
        )
    except Exception as e:
        logger.exception("manual_bill upload: blob upload failed: %s", e)
        raise HTTPException(status_code=502, detail=f"上传 Blob 失败: {e}")

    # 单附件: 新的覆盖旧的
    if row.file_url:
        azure_blob.delete_blob(row.file_url)

    row.file_url = blob_url
    row.file_name = file.filename
    row.file_size = size
    row.mime_type = mime or None
    db.commit()
    db.refresh(row)
    return row


@router.get(
    "/{bill_id}/download",
    summary="生成账单附件下载 URL (10 分钟 SAS)",
)
def download_manual_bill_file(
    bill_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    row = _get_bill_or_404(bill_id, db)
    if not row.file_url:
        raise HTTPException(404, "该账单暂无附件")
    if not azure_blob.is_configured():
        raise HTTPException(503, "Azure Blob Storage 未配置")
    try:
        url = azure_blob.sas_url(row.file_url)
    except Exception as e:
        logger.exception("manual_bill download SAS failed: %s", e)
        raise HTTPException(502, f"生成下载链接失败: {e}")
    return {"url": url, "expires_in": azure_blob.SAS_TTL_MINUTES * 60}
