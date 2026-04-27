"""GET /api/customers/{id}/timeline — chronological events for a customer.

Sources (产品规则 §3.4 — 真实业务动作):
  * Customer.created_at / updated_at — 仅直客显示, gongdan 同步来源隐藏
  * Allocation                       — 分配/订单
  * CustomerFollowUp                 — 跟进留言 + 回复
  * Contract                         — 合同
  * CustomerInsightRun               — AI 洞察运行记录
  * CustomerStageRequest             — 阶段审批申请 + 决议

System-level gongdan sync 痕迹（客户建档/资料更新对 gongdan 来源客户）依旧吞掉，
但跟进 / 合同 / AI 洞察 / 审批都是真实业务动作, 与来源无关, 全部展示。
"""
from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import CurrentUser, require_auth
from app.database import get_db
from app.models.allocation import Allocation
from app.models.contract import Contract
from app.models.customer import Customer
from app.models.customer_insight import CustomerInsightRun
from app.models.customer_stage_request import CustomerStageRequest
from app.models.follow_up import CustomerFollowUp

router = APIRouter(prefix="/api/customers", tags=["客户管理"])


class TimelineEvent(BaseModel):
    at: str
    # created | updated | allocation | follow_up | follow_up_reply
    # | contract | insight | stage_request | stage_decision
    kind: str
    title: str
    detail: str = ""
    color: str = "blue"


_STAGE_STATUS_COLOR = {
    "pending": "orange",
    "approved": "green",
    "rejected": "red",
}


@router.get("/{customer_id}/timeline", response_model=List[TimelineEvent],
            summary="客户相关事件时间线")
def customer_timeline(
    customer_id: int,
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(require_auth),
):
    c = db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()  # noqa: E712
    if not c:
        raise HTTPException(404, "客户不存在")

    events: List[TimelineEvent] = []

    # 产品规则 §3.4: 时间线只展示真实业务动作，不展示 gongdan 等系统同步痕迹。
    # 对于来源=gongdan 的客户，客户建档和"资料更新"本身就是同步事件产物，整体隐藏。
    source = (c.source_system or "").strip().lower()
    is_sync_origin = source in {"gongdan", "gongdan_sync", "system"}

    if c.created_at and not is_sync_origin:
        events.append(TimelineEvent(
            at=c.created_at.isoformat(), kind="created",
            title=f"客户建档：{c.customer_code}",
            detail=f"来源 {c.source_system or '手工'}",
            color="green",
        ))
    if c.updated_at and c.updated_at != c.created_at and not is_sync_origin:
        stage_display = c.lifecycle_stage or c.customer_status or "-"
        events.append(TimelineEvent(
            at=c.updated_at.isoformat(), kind="updated",
            title="客户资料更新",
            detail=f"阶段 {stage_display} · 行业 {c.industry or '-'}",
            color="blue",
        ))

    # --- Allocation (分配 / 订单) ---
    allocs = db.query(Allocation).filter(
        Allocation.customer_id == c.id, Allocation.is_deleted == False,  # noqa: E712
    ).order_by(Allocation.created_at.desc()).limit(50).all()
    for a in allocs:
        events.append(TimelineEvent(
            at=(a.created_at or datetime.utcnow()).isoformat(),
            kind="allocation",
            title=f"新增分配 {a.allocation_code}",
            detail=f"数量 {a.allocated_quantity} · 毛利 ¥{a.profit_amount or 0} · 状态 {a.allocation_status}",
            color="purple",
        ))

    # --- Follow-up (跟进 / 留言 / 回复) ---
    # 真实业务动作, 与 is_sync_origin 无关, 始终展示。
    follow_ups = db.query(CustomerFollowUp).filter(
        CustomerFollowUp.customer_id == c.id,
    ).order_by(CustomerFollowUp.created_at.desc()).limit(50).all()
    for f in follow_ups:
        is_reply = f.parent_follow_up_id is not None
        kind = "follow_up_reply" if is_reply else "follow_up"
        title_prefix = "跟进回复" if is_reply else f"跟进 · {f.kind or 'note'}"
        snippet = (f.content or "").strip().replace("\n", " ")
        if len(snippet) > 80:
            snippet = snippet[:80] + "…"
        detail_parts = []
        if f.title:
            detail_parts.append(f.title)
        if snippet:
            detail_parts.append(snippet)
        if f.outcome:
            detail_parts.append(f"结果 {f.outcome}")
        events.append(TimelineEvent(
            at=(f.created_at or datetime.utcnow()).isoformat(),
            kind=kind,
            title=title_prefix,
            detail=" · ".join(detail_parts) or "-",
            color="cyan",
        ))

    # --- Contract (合同) ---
    contracts = db.query(Contract).filter(
        Contract.customer_id == c.id,
    ).order_by(Contract.created_at.desc()).limit(50).all()
    for ct in contracts:
        bits = []
        if ct.title:
            bits.append(ct.title)
        if ct.amount is not None:
            bits.append(f"金额 ¥{ct.amount}")
        if ct.status:
            bits.append(f"状态 {ct.status}")
        if ct.file_name:
            bits.append(f"附件 {ct.file_name}")
        events.append(TimelineEvent(
            at=(ct.created_at or datetime.utcnow()).isoformat(),
            kind="contract",
            title=f"合同 {ct.contract_code}",
            detail=" · ".join(bits) or "-",
            color="gold",
        ))

    # --- AI Insight Run (AI 洞察运行) ---
    runs = db.query(CustomerInsightRun).filter(
        CustomerInsightRun.customer_id == c.id,
    ).order_by(CustomerInsightRun.started_at.desc()).limit(20).all()
    for r in runs:
        # fact_count 取关系长度（已有 lazy='select'）；无 duration_ms 字段, 用
        # completed_at - started_at 算一份毫秒数, 只在 completed_at 存在时展示。
        fact_count = len(r.facts) if r.facts is not None else 0
        duration_ms = None
        if r.completed_at and r.started_at:
            duration_ms = int((r.completed_at - r.started_at).total_seconds() * 1000)
        bits = [f"状态 {r.status}", f"事实 {fact_count} 条"]
        if duration_ms is not None:
            bits.append(f"耗时 {duration_ms}ms")
        events.append(TimelineEvent(
            at=(r.started_at or datetime.utcnow()).isoformat(),
            kind="insight",
            title="AI 洞察运行",
            detail=" · ".join(bits),
            color="magenta",
        ))

    # --- Stage Request (阶段审批) ---
    stage_reqs = db.query(CustomerStageRequest).filter(
        CustomerStageRequest.customer_id == c.id,
    ).order_by(CustomerStageRequest.created_at.desc()).limit(50).all()
    for sr in stage_reqs:
        # 提交事件: 永远以 created_at 落点, 颜色按当前 status
        submit_color = _STAGE_STATUS_COLOR.get(sr.status, "blue")
        submit_bits = [f"{sr.from_stage} → {sr.to_stage}", f"状态 {sr.status}"]
        if sr.requested_by:
            submit_bits.append(f"申请人 {sr.requested_by}")
        if sr.reason:
            reason = sr.reason.strip().replace("\n", " ")
            if len(reason) > 80:
                reason = reason[:80] + "…"
            submit_bits.append(f"理由 {reason}")
        events.append(TimelineEvent(
            at=(sr.created_at or datetime.utcnow()).isoformat(),
            kind="stage_request",
            title=f"阶段审批申请 {sr.from_stage} → {sr.to_stage}",
            detail=" · ".join(submit_bits),
            color=submit_color,
        ))
        # 决议事件: 仅 status != pending && decided_at 存在时落点
        if sr.status != "pending" and sr.decided_at:
            decision_color = _STAGE_STATUS_COLOR.get(sr.status, "blue")
            decision_bits = [f"{sr.from_stage} → {sr.to_stage}", f"结果 {sr.status}"]
            if sr.decided_by:
                decision_bits.append(f"审批人 {sr.decided_by}")
            if sr.decision_comment:
                cmt = sr.decision_comment.strip().replace("\n", " ")
                if len(cmt) > 80:
                    cmt = cmt[:80] + "…"
                decision_bits.append(f"意见 {cmt}")
            events.append(TimelineEvent(
                at=sr.decided_at.isoformat(),
                kind="stage_decision",
                title=f"阶段审批 {sr.status}",
                detail=" · ".join(decision_bits),
                color=decision_color,
            ))

    # System-level sync events (e.g. "从 gongdan 同步客户") are deliberately
    # omitted — users only want to see real business actions on the timeline.

    events.sort(key=lambda e: e.at, reverse=True)
    return events
