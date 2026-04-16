"""账单 CSV 导出 endpoint.

从本地 cc_bill 表按月导出, join customer 补 customer_name.
列: 月份 / 客户名称 / 客户编号 / 货源编号 / 原始成本 / 调价 / 最终金额 / 状态 / 创建时间
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.cc_bill import CCBill
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bills", tags=["账单导出"])


_CSV_HEADER = [
    "月份", "客户名称", "客户编号", "货源编号",
    "原始成本", "调价", "最终金额", "状态", "创建时间",
]


def _fmt_num(v) -> str:
    if v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _fmt_dt(v) -> str:
    if not v:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _iter_rows(
    db: Session,
    month: str,
    status: Optional[str],
    customer_code: Optional[str],
) -> Iterable[str]:
    """Stream CSV rows — yields a header row then one row per bill."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # write UTF-8 BOM so Excel opens the file correctly
    yield "\ufeff"

    writer.writerow(_CSV_HEADER)
    yield buf.getvalue()
    buf.seek(0); buf.truncate(0)

    q = db.query(CCBill).filter(CCBill.month == month)
    if status:
        q = q.filter(CCBill.status == status)
    if customer_code:
        q = q.filter(CCBill.customer_code == customer_code)
    bills = q.order_by(CCBill.id.asc()).all()

    # Build customer_code -> customer_name map in one shot
    codes = {b.customer_code for b in bills if b.customer_code}
    name_map: dict[str, str] = {}
    if codes:
        rows = db.query(Customer.customer_code, Customer.customer_name).filter(
            Customer.customer_code.in_(codes),
            Customer.is_deleted == False,  # noqa: E712
        ).all()
        name_map = {code: name for code, name in rows}

    for b in bills:
        writer.writerow([
            b.month or "",
            name_map.get(b.customer_code or "", ""),
            b.customer_code or "",
            "",  # 货源编号 — 预留, 当前 cc_bill 无此字段
            _fmt_num(b.original_cost),
            _fmt_num(b.adjustment),
            _fmt_num(b.final_cost),
            b.status or "",
            _fmt_dt(b.sync_at),
        ])
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)


@router.get("/export", summary="账单 CSV 导出 (按月)")
def export_bills_csv(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    status: Optional[str] = Query(None, description="账单状态过滤, e.g. draft/confirmed/paid"),
    customer_code: Optional[str] = Query(None, description="按客户编号过滤"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    filename = f"bills-{month}-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        _iter_rows(db, month, status, customer_code),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
