"""Customer enrichment + 商机 search — powered by Jina."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations.jina import JinaClient, extract_description, guess_industry
from app.integrations.linkedin import LinkedInClient
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enrich", tags=["商机 / 补全"])


def _jina() -> JinaClient:
    s = get_settings()
    if not s.JINA_API_KEY:
        raise HTTPException(400, "JINA_API_KEY not configured")
    return JinaClient(api_key=s.JINA_API_KEY)


def _linkedin() -> LinkedInClient:
    s = get_settings()
    if not s.RAPIDAPI_KEY:
        raise HTTPException(400, "RAPIDAPI_KEY not configured")
    return LinkedInClient(api_key=s.RAPIDAPI_KEY, host=s.LINKEDIN_API_HOST)


class EnrichResult(BaseModel):
    customer_code: str
    customer_name: str
    official_url: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    candidates: List[dict] = []
    applied: bool = False


@router.post("/customer/{customer_id}", response_model=EnrichResult,
             summary="一键补全：搜公司官网、抓简介、猜行业")
def enrich_customer(
    customer_id: int,
    apply: bool = Query(False, description="True 时把猜测结果写回客户"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    cust = db.query(Customer).filter(
        Customer.id == customer_id, Customer.is_deleted == False,  # noqa: E712
    ).first()
    if not cust:
        raise HTTPException(404, "客户不存在")

    jina = _jina()
    q = f"{cust.customer_name} 公司 官网 介绍"
    try:
        results = jina.search(q, num=5)
    except Exception as e:
        raise HTTPException(502, f"Jina search failed: {e}")

    candidates = [
        {"title": r.title, "url": r.url, "description": r.description[:200]}
        for r in results
    ]

    top = results[0] if results else None
    official_url = top.url if top else None
    markdown = ""
    if top:
        try:
            markdown = jina.read(top.url, max_chars=15000)
        except Exception as e:
            logger.warning("jina read failed for %s: %s", top.url, e)

    description = extract_description(markdown or (top.description if top else ""))
    industry_guess = guess_industry((markdown or "") + " " + (top.description if top else ""))

    if apply:
        changed = False
        if industry_guess and not cust.industry:
            cust.industry = industry_guess; changed = True
        if changed:
            db.add(cust); db.commit()

    return EnrichResult(
        customer_code=cust.customer_code,
        customer_name=cust.customer_name,
        official_url=official_url,
        description=description,
        industry=industry_guess,
        candidates=candidates,
        applied=bool(apply),
    )


class LocalProspectItem(BaseModel):
    id: int
    customer_code: str
    customer_name: str
    industry: Optional[str] = None
    region: Optional[str] = None
    source_system: Optional[str] = None
    source_label: Optional[str] = None
    source_id: Optional[str] = None
    note: Optional[str] = None
    website: Optional[str] = None
    created_at: Optional[str] = None
    last_follow_time: Optional[str] = None


@router.get("/leads/local-prospects", response_model=List[LocalProspectItem],
            summary="列出本地潜在客户 (lifecycle_stage=lead) - 商机池客户")
def list_local_prospects(
    keyword: Optional[str] = Query(None, description="名称 / 编号搜索"),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    q = db.query(Customer).filter(
        Customer.is_deleted == False,  # noqa: E712
        Customer.lifecycle_stage == "lead",
    )
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (Customer.customer_name.ilike(like)) |
            (Customer.customer_code.ilike(like))
        )
    items = q.order_by(Customer.created_at.desc()).limit(200).all()
    return [
        LocalProspectItem(
            id=c.id,
            customer_code=c.customer_code,
            customer_name=c.customer_name,
            industry=c.industry,
            region=c.region,
            source_system=c.source_system,
            source_label=c.source_label,
            source_id=c.source_id,
            note=c.note,
            website=c.website,
            created_at=c.created_at.isoformat() if c.created_at else None,
            last_follow_time=c.last_follow_time.isoformat() if c.last_follow_time else None,
        )
        for c in items
    ]


class LeadSearchItem(BaseModel):
    title: str
    url: str
    description: str = ""
    inferred_industry: Optional[str] = None


@router.get("/leads", response_model=List[LeadSearchItem], summary="潜在客户搜索（基于关键词）")
def search_leads(
    q: str = Query(..., description="行业 / 关键词，例如 '新能源 储能 上海'"),
    num: int = Query(8, ge=1, le=20),
    _: CurrentUser = Depends(require_auth),
):
    jina = _jina()
    try:
        results = jina.search(q, num=num)
    except Exception as e:
        raise HTTPException(502, f"Jina search failed: {e}")
    return [
        LeadSearchItem(
            title=r.title, url=r.url, description=r.description[:300],
            inferred_industry=guess_industry((r.title + " " + r.description)),
        )
        for r in results
    ]


class PromoteLeadBody(BaseModel):
    customer_code: str
    customer_name: str
    industry: Optional[str] = None
    source_url: Optional[str] = None


@router.post("/leads/promote", summary="把一个搜索结果转化为客户")
def promote_lead(
    body: PromoteLeadBody,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_auth),
):
    existing = db.query(Customer).filter(Customer.customer_code == body.customer_code).first()
    if existing:
        raise HTTPException(400, "客户编号已存在")
    cust = Customer(
        customer_code=body.customer_code,
        customer_name=body.customer_name,
        industry=body.industry,
        customer_status="potential",   # kept for backward compat
        lifecycle_stage="lead",        # new read path
        source_system="jina-lead",
        source_id=body.source_url,
    )
    db.add(cust); db.commit(); db.refresh(cust)
    return {"id": cust.id, "customer_code": cust.customer_code}


# ---------- LinkedIn deep enrichment ----------

class LinkedInCompanyOut(BaseModel):
    name: str
    linkedin_url: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    headquarters: Optional[str] = None
    employee_count: Optional[int] = None
    description: Optional[str] = None


@router.get("/linkedin/search", response_model=List[LinkedInCompanyOut],
            summary="LinkedIn 搜公司（需 RapidAPI 订阅 fresh-linkedin-profile-data）")
def linkedin_search(
    q: str = Query(..., description="公司名 / 行业 关键词"),
    page: int = Query(1, ge=1, le=20),
    _: CurrentUser = Depends(require_auth),
):
    try:
        items = _linkedin().search_companies(q, page=page)
    except Exception as e:
        raise HTTPException(502, str(e))
    return [LinkedInCompanyOut(**{k: getattr(i, k) for k in LinkedInCompanyOut.model_fields}) for i in items]


@router.get("/linkedin/company", response_model=LinkedInCompanyOut, summary="LinkedIn 公司详情")
def linkedin_company_detail(
    linkedin_url: str = Query(..., description="https://www.linkedin.com/company/<slug>/"),
    _: CurrentUser = Depends(require_auth),
):
    try:
        c = _linkedin().get_company(linkedin_url)
    except Exception as e:
        raise HTTPException(502, str(e))
    return LinkedInCompanyOut(**{k: getattr(c, k) for k in LinkedInCompanyOut.model_fields})
