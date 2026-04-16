import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    allocation, auth, customer, resource, usage, sync, customer_resources,
    internal, enrich, bridge, briefing, health_score, customer_timeline, trend,
    customer_insight_agent, sales, external, follow_up, contract, ticket,
)
from app.auth.dependencies import require_auth
from app.config import get_settings
from app.database import Base, engine
from app import models  # noqa: F401  — registers all tables on Base.metadata

settings = get_settings()
logger = logging.getLogger("xiaoshou")


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("DB tables ensured via metadata.create_all")
    except Exception as e:
        logger.error("DB init failed: %s", e)
    yield


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
app.include_router(contract.router, dependencies=protected_deps)
app.include_router(contract.customer_scoped, dependencies=protected_deps)
app.include_router(ticket.sync_router, dependencies=protected_deps)
app.include_router(ticket.customer_scoped, dependencies=protected_deps)


@app.get("/")
def root():
    return {
        "message": "欢迎使用销售系统 API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "auth": "/api/auth/login",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
