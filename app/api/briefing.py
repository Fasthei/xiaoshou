"""Morning briefing — aggregate signals from local + cloudcost into a tight report."""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.config import get_settings
from app.database import get_db
from app.integrations import CloudCostClient
from app.models.customer import Customer
from app.models.allocation import Allocation

router = APIRouter(prefix="/api/briefing", tags=["每日 briefing"])


class BriefingItem(BaseModel):
    kind: str           # alert / lead / expire / sync
    severity: str       # info / warn / crit
    title: str
    detail: str = ""


class BriefingOut(BaseModel):
    date: str
    items: List[BriefingItem]
    counts: dict


@router.get("", response_model=BriefingOut, summary="一页纸概要（供首页条幅用）")
def briefing(db: Session = Depends(get_db), _: CurrentUser = Depends(require_auth)):
    items: List[BriefingItem] = []
    s = get_settings()

    # 1) cloudcost 预警
    if s.CLOUDCOST_ENDPOINT:
        try:
            rules = CloudCostClient(s.CLOUDCOST_ENDPOINT).alerts_rule_status() or []
            for r in rules:
                if r.get("triggered"):
                    items.append(BriefingItem(
                        kind="alert", severity="crit",
                        title=f"预警触发：{r.get('rule_name')}",
                        detail=f"当前 {r.get('actual')} / 阈值 {r.get('threshold_value')} · 账号 {r.get('account_name') or '-'}",
                    ))
                elif (r.get("pct") or 0) >= 80:
                    items.append(BriefingItem(
                        kind="alert", severity="warn",
                        title=f"接近阈值：{r.get('rule_name')}",
                        detail=f"已达 {r.get('pct')}%（{r.get('actual')} / {r.get('threshold_value')}）",
                    ))
        except Exception:
            pass

    # 2) 商机池客户（lifecycle_stage=lead，原 prospect/potential 状态）
    prospects = db.query(Customer).filter(
        Customer.lifecycle_stage == "lead", Customer.is_deleted == False,  # noqa: E712
    ).count()
    if prospects:
        items.append(BriefingItem(
            kind="lead", severity="info",
            title=f"{prospects} 个商机池客户待跟进",
            detail="处于 lead 阶段，可进入「客户管理」筛选 lead 状态",
        ))

    # 3) 最近 14 天新分配
    recent_allocs = db.query(Allocation).filter(Allocation.is_deleted == False).count()  # noqa: E712
    if recent_allocs:
        items.append(BriefingItem(
            kind="expire", severity="info",
            title=f"进行中分配 {recent_allocs} 笔",
            detail="毛利汇总在「分配管理」可见",
        ))

    # 4) 云管同步新鲜度
    if s.CLOUDCOST_ENDPOINT:
        last = CloudCostClient(s.CLOUDCOST_ENDPOINT).sync_last()
        if last:
            items.append(BriefingItem(
                kind="sync", severity="info",
                title="云管数据最近同步",
                detail=last,
            ))

    counts = {
        "alerts": sum(1 for i in items if i.kind == "alert"),
        "leads": prospects,
        "allocations": recent_allocs,
    }
    return BriefingOut(date=datetime.utcnow().strftime("%Y-%m-%d"), items=items, counts=counts)
