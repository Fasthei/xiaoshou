"""Verify URL composition from PG_*/REDIS_* parts (Plan Y env shape)."""
import importlib
import os


def _reload_settings():
    from app import config
    config.get_settings.cache_clear()
    importlib.reload(config)
    return config.get_settings()


def test_database_url_from_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PG_USER", "sales_admin")
    monkeypatch.setenv("PG_PASSWORD", "p@ss/word")  # chars that must be url-encoded
    monkeypatch.setenv("PG_HOST", "dataope.postgres.database.azure.com")
    monkeypatch.setenv("PG_DB", "sales_system")
    s = _reload_settings()
    url = s.effective_database_url
    assert url.startswith("postgresql://sales_admin:")
    assert "%40" in url and "%2F" in url  # @ and / encoded
    assert "dataope.postgres.database.azure.com:5432/sales_system" in url
    assert "sslmode=require" in url


def test_redis_url_from_parts(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "oper.redis.cache.windows.net")
    monkeypatch.setenv("REDIS_PASSWORD", "k" * 32)
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "1")
    monkeypatch.setenv("REDIS_TLS", "true")
    s = _reload_settings()
    url = s.effective_redis_url
    assert url.startswith("rediss://:")
    assert "oper.redis.cache.windows.net:6380/1" in url


def test_database_url_override_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    monkeypatch.setenv("PG_HOST", "should-be-ignored")
    s = _reload_settings()
    assert s.effective_database_url == "postgresql://u:p@h:5432/d"


def test_cors_origin_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.com, http://b.com ,  ")
    s = _reload_settings()
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]
