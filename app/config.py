from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "销售系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库：优先用完整 DATABASE_URL，否则用 PG_* 各部分组装
    # (Azure Container Apps 不支持 env 值里插值 secretRef，所以在 sales-rg 模式下
    #  我们传的是 PG_USER / PG_PASSWORD / PG_HOST / PG_DB 四件套。)
    DATABASE_URL: str = ""
    PG_USER: str = ""
    PG_PASSWORD: str = ""
    PG_HOST: str = ""
    PG_DB: str = ""
    PG_PORT: int = 5432
    PG_SSLMODE: str = "require"

    # Redis：优先用完整 REDIS_URL，否则用 REDIS_* 组装
    REDIS_HOST: str = ""
    REDIS_PASSWORD: str = ""
    REDIS_PORT: int = 6380
    REDIS_DB: int = 0
    REDIS_TLS: bool = True

    REDIS_URL: str = ""

    # 本地 JWT（开发/退化）
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Casdoor
    AUTH_ENABLED: bool = True
    CASDOOR_ENDPOINT: str = ""
    CASDOOR_CLIENT_ID: str = ""
    CASDOOR_CLIENT_SECRET: str = ""
    CASDOOR_ORG: str = "built-in"
    CASDOOR_APP_NAME: str = "xiaoshou"
    CASDOOR_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"
    CASDOOR_CERT: str = ""

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # 工单 (gongdan) 集成
    GONGDAN_ENDPOINT: str = ""
    GONGDAN_API_KEY: str = ""

    # 云管 (cloudcost) 集成
    CLOUDCOST_ENDPOINT: str = ""
    # Which service-account field matches xiaoshou customer_code.
    # Options commonly seen: external_project_id | supplier_name | name
    CLOUDCOST_MATCH_FIELD: str = "external_project_id"

    # Internal API auth — Casdoor M2M audiences allowed to pull /api/internal/*
    CASDOOR_INTERNAL_ALLOWED_CLIENTS: str = ""
    # Fallback static key for cloudcost before it joins Casdoor
    XIAOSHOU_INTERNAL_API_KEY: str = ""

    # Jina (search + reader) — 商机/客户补全
    JINA_API_KEY: str = ""

    # LinkedIn via RapidAPI — 深度企业数据
    RAPIDAPI_KEY: str = ""
    LINKEDIN_API_HOST: str = "fresh-linkedin-profile-data.p.rapidapi.com"

    # Azure OpenAI — 用于客户洞察 agent (gpt-5.4 + function calling)
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_VERSION: str = "2025-04-01-preview"
    AZURE_OPENAI_DEPLOYMENT: str = "gpt-5.4"

    # 超级运营中心访问专用 API key (只读, /api/external/*)
    SUPER_OPS_API_KEY: str = ""

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if self.PG_HOST and self.PG_USER and self.PG_DB:
            from urllib.parse import quote_plus
            pw = quote_plus(self.PG_PASSWORD)
            return (
                f"postgresql://{self.PG_USER}:{pw}@{self.PG_HOST}:{self.PG_PORT}"
                f"/{self.PG_DB}?sslmode={self.PG_SSLMODE}"
            )
        raise RuntimeError("No DATABASE_URL and no PG_* parts configured")

    @property
    def effective_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_HOST:
            scheme = "rediss" if self.REDIS_TLS else "redis"
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
            return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        raise RuntimeError("No REDIS_URL and no REDIS_* parts configured")

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings():
    return Settings()
