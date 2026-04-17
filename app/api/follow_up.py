"""Customer follow-up log + completeness score + CSV import/export."""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Response
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.customer import Customer, CustomerContact
from app.models.follow_up import CustomerFollowUp
from app.models.sales import SalesUser
from app.schemas.follow_up import (
    CompletenessOut, FollowUpCreate, FollowUpOut, FOLLOW_UP_KINDS, OUTCOMES,
)
from app.api.customer_stage import auto_advance_stage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/customers", tags=["客户档案 / 跟进日志"])
global_router = APIRouter(prefix="/api", tags=["客户档案 / 跟进日志"])


# ---------- global follow-up list ----------

def _sales_name_map(db: Session) -> dict[int, str]:
    """Return {sales_user.id: sales_user.name} for all active sales users."""
    rows = db.query(SalesUser.id, SalesUser.name).filter(SalesUser.is_active == True).all()  # noqa: E712
    return {r.id: r.name for r in rows}


@global_router.get("/follow-ups", summary="全局跟进列表")
def list_all_follow_ups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365, description="近 N 天"),
    sales_user_id: Optional[int] = Query(None),
    customer_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    q = (
        db.query(CustomerFollowUp, Customer.customer_code, Customer.customer_name)
        .join(Customer, CustomerFollowUp.customer_id == Customer.id)
        .filter(Customer.is_deleted == False)  # noqa: E712
    )
    if days:
        cutoff = datetime.utcnow() - timedelta(days=days)
        q = q.filter(CustomerFollowUp.created_at >= cutoff)
    if sales_user_id:
        q = q.filter(Customer.sales_user_id == sales_user_id)
    if customer_id:
        q = q.filter(CustomerFollowUp.customer_id == customer_id)
    q = q.order_by(CustomerFollowUp.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    name_map = _sales_name_map(db)
    items = [
        {
            "id": f.id,
            "customer_id": f.customer_id,
            "customer_code": code,
            "customer_name": name,
            "follow_type": f.kind,
            "content": f.content,
            "title": f.title,
            "outcome": f.outcome,
            "next_action_date": f.next_action_at.isoformat() if f.next_action_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "operator_casdoor_id": f.operator_casdoor_id,
            "to_sales_user_id": f.to_sales_user_id,
            "parent_follow_up_id": f.parent_follow_up_id,
            "from_sales_name": None,  # resolved below via casdoor_map
            "to_sales_name": name_map.get(f.to_sales_user_id),
        }
        for (f, code, name) in rows
    ]
    # resolve from_sales_name via operator_casdoor_id matching sales_user.casdoor_user_id
    casdoor_map = {
        su.casdoor_user_id: su.name
        for su in db.query(SalesUser).filter(SalesUser.casdoor_user_id.isnot(None)).all()
    }
    for item, (f, _code, _name) in zip(items, rows):
        item["from_sales_name"] = casdoor_map.get(f.operator_casdoor_id)
    return {"total": total, "items": items}


@global_router.get("/follow-ups/inbox", summary="收件箱: 定向发给我的留言")
def follow_ups_inbox(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    """返回 to_sales_user_id = 当前登录用户对应 sales_user 的所有 comment 留言（不做已读过滤）。"""
    # Find current user's sales_user by casdoor_user_id
    my_sales = db.query(SalesUser).filter(SalesUser.casdoor_user_id == user.sub).first()
    if not my_sales:
        return {"total": 0, "items": []}

    q = (
        db.query(CustomerFollowUp, Customer.customer_code, Customer.customer_name)
        .join(Customer, CustomerFollowUp.customer_id == Customer.id)
        .filter(
            CustomerFollowUp.to_sales_user_id == my_sales.id,
            Customer.is_deleted == False,  # noqa: E712
        )
        .order_by(CustomerFollowUp.created_at.desc())
    )
    rows = q.all()
    name_map = _sales_name_map(db)
    casdoor_map = {
        su.casdoor_user_id: su.name
        for su in db.query(SalesUser).filter(SalesUser.casdoor_user_id.isnot(None)).all()
    }
    items = [
        {
            "id": f.id,
            "customer_id": f.customer_id,
            "customer_code": code,
            "customer_name": name,
            "follow_type": f.kind,
            "content": f.content,
            "title": f.title,
            "outcome": f.outcome,
            "next_action_date": f.next_action_at.isoformat() if f.next_action_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "operator_casdoor_id": f.operator_casdoor_id,
            "to_sales_user_id": f.to_sales_user_id,
            "parent_follow_up_id": f.parent_follow_up_id,
            "from_sales_name": casdoor_map.get(f.operator_casdoor_id),
            "to_sales_name": name_map.get(f.to_sales_user_id),
        }
        for (f, code, name) in rows
    ]
    return {"total": len(items), "items": items}


# ---------- follow-up log ----------

@router.get("/{customer_id}/follow-ups", response_model=List[FollowUpOut],
            summary="客户跟进日志 (倒序)")
def list_follow_ups(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    return (
        db.query(CustomerFollowUp)
        .filter(CustomerFollowUp.customer_id == customer_id)
        .order_by(CustomerFollowUp.id.desc())
        .all()
    )


@router.post("/{customer_id}/follow-ups", response_model=FollowUpOut,
             summary="记录新跟进 + 更新 last_follow_time")
def create_follow_up(
    customer_id: int,
    body: FollowUpCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")

    if body.kind not in FOLLOW_UP_KINDS:
        raise HTTPException(400, f"kind 必须是 {FOLLOW_UP_KINDS}")
    if body.outcome and body.outcome not in OUTCOMES:
        raise HTTPException(400, f"outcome 必须是 {OUTCOMES}")

    fu = CustomerFollowUp(
        customer_id=customer_id,
        kind=body.kind, title=body.title, content=body.content,
        outcome=body.outcome, next_action_at=body.next_action_at,
        operator_casdoor_id=getattr(user, "sub", None) if user else None,
        to_sales_user_id=body.to_sales_user_id,
        parent_follow_up_id=body.parent_follow_up_id,
    )
    # Bump customer.last_follow_time so 过期回收引擎能正确判断
    customer.last_follow_time = datetime.now()
    if body.kind == "meeting":
        customer.last_meeting_at = datetime.now()
    # Auto lifecycle: lead -> contacting on first follow-up
    auto_advance_stage(
        db, customer, "contacting",
        reason="首次跟进, 自动从 lead 升至 contacting",
        only_if_in=("lead",),
    )
    db.add(fu); db.add(customer); db.commit(); db.refresh(fu)
    return fu


@router.delete("/{customer_id}/follow-ups/{fu_id}", summary="删除跟进记录 (硬删)")
def delete_follow_up(
    customer_id: int, fu_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    fu = db.query(CustomerFollowUp).filter(
        CustomerFollowUp.id == fu_id,
        CustomerFollowUp.customer_id == customer_id,
    ).first()
    if not fu:
        raise HTTPException(404, "跟进记录不存在")
    db.delete(fu); db.commit()
    return {"ok": True}


# ---------- completeness score ----------

# Each key maps to a (display_label, weight) tuple. Weights sum to 100.
# A field is considered "present" when truthy (non-empty string, non-null, > 0).
_COMPLETENESS_WEIGHTS = {
    "customer_name":   ("客户名称",  10),
    "industry":        ("行业",      10),
    "region":          ("地区",      10),
    "customer_level":  ("客户级别",  10),
    "sales_user_id":   ("所属销售",  10),
    "primary_contact": ("主联系人",  15),
    "employee_size":   ("员工规模",  10),
    "annual_revenue":  ("年营收",    10),
    "last_follow_time": ("最近跟进",  8),
    "website":         ("公司官网",  7),
}


def _compute_completeness(db: Session, customer: Customer) -> CompletenessOut:
    present: list[str] = []
    missing: list[str] = []
    score = 0

    has_primary_contact = db.query(CustomerContact).filter(
        CustomerContact.customer_id == customer.id,
        CustomerContact.is_primary == True,  # noqa: E712
        CustomerContact.is_deleted == False,  # noqa: E712
    ).first() is not None

    field_values = {
        "customer_name": customer.customer_name,
        "industry": customer.industry,
        "region": customer.region,
        "customer_level": customer.customer_level,
        "sales_user_id": customer.sales_user_id,
        "primary_contact": has_primary_contact,
        "employee_size": customer.employee_size,
        "annual_revenue": customer.annual_revenue,
        "last_follow_time": customer.last_follow_time,
        "website": customer.website,
    }

    for key, (label, weight) in _COMPLETENESS_WEIGHTS.items():
        v = field_values.get(key)
        if v:
            score += weight
            present.append(label)
        else:
            missing.append(label)

    tier = "green" if score >= 80 else "yellow" if score >= 50 else "red"
    return CompletenessOut(
        customer_id=customer.id, score=score, tier=tier,
        missing=missing, present=present,
    )


@router.get("/{customer_id}/completeness", response_model=CompletenessOut,
            summary="客户档案完整度评分")
def completeness(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customer = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not customer:
        raise HTTPException(404, "客户不存在")
    return _compute_completeness(db, customer)


# ---------- CSV import/export ----------

_EXPORT_COLUMNS = [
    "id", "customer_code", "customer_name", "customer_short_name", "industry",
    "region", "customer_level", "customer_status", "sales_user_id",
    "employee_size", "annual_revenue", "website", "linkedin_url",
    "current_resource_count", "current_month_consumption",
    "last_follow_time", "last_meeting_at", "first_deal_time",
    "source_system", "source_id", "note",
    "created_at", "updated_at",
]


@router.get("/bulk/export.csv", summary="导出全部客户为 CSV")
def export_customers_csv(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    customers = db.query(Customer).filter(Customer.is_deleted == False).all()  # noqa: E712
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for c in customers:
        row = []
        for col in _EXPORT_COLUMNS:
            val = getattr(c, col, None)
            if val is None:
                row.append("")
            elif hasattr(val, "isoformat"):
                row.append(val.isoformat())
            else:
                row.append(str(val))
        writer.writerow(row)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="customers-{datetime.now().strftime("%Y%m%d")}.csv"',
        },
    )


class _ImportResult:
    __slots__ = ("created", "updated", "skipped", "errors")

    def __init__(self):
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors: list[dict] = []


@router.post("/bulk/import.csv", summary="从 CSV 批量导入/更新客户")
async def import_customers_csv(
    file: UploadFile = File(..., description="UTF-8 CSV, 需含 customer_code + customer_name 列"),
    dry_run: bool = False,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    result = _ImportResult()

    fields_we_can_upsert = {
        "customer_short_name", "industry", "region", "customer_level",
        "customer_status", "employee_size", "annual_revenue", "website",
        "linkedin_url", "note", "source_system", "source_id",
    }

    for idx, row in enumerate(reader, start=2):
        code = (row.get("customer_code") or "").strip()
        name = (row.get("customer_name") or "").strip()
        if not code or not name:
            result.skipped += 1
            result.errors.append({"row": idx, "reason": "缺 customer_code 或 customer_name"})
            continue

        existing = db.query(Customer).filter(
            Customer.customer_code == code, Customer.is_deleted == False,  # noqa: E712
        ).first()
        patch = {
            k: (int(row[k]) if k == "employee_size" and row.get(k) else row[k])
            for k in fields_we_can_upsert if row.get(k)
        }
        try:
            if existing:
                if not dry_run:
                    existing.customer_name = name
                    for k, v in patch.items():
                        setattr(existing, k, v)
                    db.add(existing)
                result.updated += 1
            else:
                if not dry_run:
                    db.add(Customer(
                        customer_code=code, customer_name=name,
                        customer_status=row.get("customer_status") or "prospect",
                        **patch,
                    ))
                result.created += 1
        except Exception as e:  # noqa: BLE001
            result.skipped += 1
            result.errors.append({"row": idx, "reason": str(e)})

    if not dry_run:
        db.commit()

    return {
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors[:50],
        "dry_run": dry_run,
    }
