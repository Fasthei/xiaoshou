import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    allocation, auth, customer, resource, usage, sync, customer_resources,
    internal, enrich, bridge, briefing, health_score, customer_timeline, trend,
    customer_insight_agent, sales, external, follow_up, contract, ticket,
    alert_rule, payment, cc_sync, bills_export, bills_local, bill_adjustment,
    manager, orders, customer_stage, manager_metrics, reports,
)
from app.auth.dependencies import require_auth
from app.config import get_settings
from app.database import Base, engine
from app import models  # noqa: F401  — registers all tables on Base.metadata

settings = get_settings()
logger = logging.getLogger("xiaoshou")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用启动/关闭生命周期。

    1. Base.metadata.create_all — 创建缺失的表 (如新加的 bill_adjustment)
    2. _ensure_columns — 对已存在的表补齐新列 (IF NOT EXISTS, idempotent)
       Best effort：alembic entrypoint 跑成功时这一步没事做；
       alembic 失败 (如 sync_log 主键类型问题等) 时作为兜底。
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("DB tables ensured via metadata.create_all")
    except Exception as e:
        logger.error("DB init failed: %s", e)
    try:
        _ensure_columns()
    except Exception as e:
        logger.error("DB column patch failed: %s", e)
    yield


# 议题 A/B 新列的兜底 —— 对应 alembic 006 / 007。
# 如果生产 alembic 已经跑过，这些 ALTER 会因 IF NOT EXISTS 直接空跑。
_STARTUP_COLUMN_PATCHES = [
    # alembic 006: bill_adjustment 已经在 ORM metadata 里，create_all 会处理
    # alembic 007: customer / resource 的两级删除策略列
    "ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS demoted_at TIMESTAMP",
    "ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS demoted_reason VARCHAR(200)",
    "ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(200)",
    "ALTER TABLE IF EXISTS customer ADD COLUMN IF NOT EXISTS deletion_reason VARCHAR(200)",
    "ALTER TABLE IF EXISTS resource ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
]


def _ensure_columns() -> None:
    """补齐 ORM 预期存在但生产库可能缺的列；幂等。"""
    from sqlalchemy import text
    with engine.begin() as conn:
        for stmt in _STARTUP_COLUMN_PATCHES:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                logger.warning("column patch skipped (%s): %s", stmt, e)
    logger.info("column patches applied (idempotent)")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="销售系统 API",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public routes
app.include_router(auth.router)

# Internal M2M routes: its own auth (see app.api.internal._auth) — not behind user JWT
app.include_router(internal.router)

# External routes for 超级运营中心: own auth via X-Api-Key — not behind user JWT
app.include_router(external.router)

# Protected business routes — all /api/* require a valid Casdoor JWT
protected_deps = [Depends(require_auth)]
app.include_router(customer.router, dependencies=protected_deps)
app.include_router(customer_resources.router, dependencies=protected_deps)
app.include_router(resource.router, dependencies=protected_deps)
app.include_router(allocation.router, dependencies=protected_deps)
app.include_router(usage.router, dependencies=protected_deps)
app.include_router(sync.router, dependencies=protected_deps)
app.include_router(enrich.router, dependencies=protected_deps)
app.include_router(bridge.router, dependencies=protected_deps)
app.include_router(briefing.router, dependencies=protected_deps)
app.include_router(health_score.router, dependencies=protected_deps)
app.include_router(customer_timeline.router, dependencies=protected_deps)
app.include_router(trend.router, dependencies=protected_deps)
app.include_router(customer_insight_agent.router, dependencies=protected_deps)
app.include_router(sales.router, dependencies=protected_deps)
app.include_router(sales.customer_scoped, dependencies=protected_deps)
app.include_router(follow_up.router, dependencies=protected_deps)
app.include_router(follow_up.global_router, dependencies=protected_deps)
app.include_router(contract.router, dependencies=protected_deps)
app.include_router(contract.customer_scoped, dependencies=protected_deps)
app.include_router(ticket.sync_router, dependencies=protected_deps)
app.include_router(ticket.customer_scoped, dependencies=protected_deps)
app.include_router(alert_rule.router, dependencies=protected_deps)
app.include_router(payment.router, dependencies=protected_deps)
app.include_router(cc_sync.sync_router, dependencies=protected_deps)
app.include_router(cc_sync.local_router, dependencies=protected_deps)
app.include_router(bills_export.router, dependencies=protected_deps)
app.include_router(bills_local.router, dependencies=protected_deps)
app.include_router(bill_adjustment.router, dependencies=protected_deps)
app.include_router(manager.router, dependencies=protected_deps)
app.include_router(orders.router, dependencies=protected_deps)
app.include_router(customer_stage.customer_router, dependencies=protected_deps)
app.include_router(customer_stage.request_router, dependencies=protected_deps)
app.include_router(manager_metrics.router, dependencies=protected_deps)
app.include_router(reports.router, dependencies=protected_deps)


@app.get("/")
def root():
    return {
        "message": "欢迎使用销售系统 API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "auth": "/api/auth/login",
    }


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
