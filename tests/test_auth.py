"""Auth dependency behaviour — no real Casdoor, use monkeypatched verifier."""
import os

from fastapi.testclient import TestClient

from app.auth import casdoor as casdoor_mod
from main import app

client = TestClient(app)


def _enable_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    # Clear cached settings
    from app import config
    config.get_settings.cache_clear()


def test_protected_route_401_without_token(monkeypatch):
    _enable_auth(monkeypatch)
    # hit a protected list endpoint — don't need DB because auth fails first
    r = client.get("/api/customers")
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"].lower() or "missing" in r.json()["detail"].lower()


def test_me_with_mocked_verify(monkeypatch):
    _enable_auth(monkeypatch)

    def fake_verify(token):
        assert token == "good-token"
        return {
            "sub": "u-1",
            "name": "Alice",
            "email": "a@example.com",
            "owner": "xingyun",
            "roles": [{"name": "sales"}, {"name": "admin"}],
        }

    monkeypatch.setattr(casdoor_mod, "verify_jwt", fake_verify)

    r = client.get("/api/auth/me", headers={"Authorization": "Bearer good-token"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Alice"
    assert "sales" in body["roles"] and "admin" in body["roles"]


def test_bad_token_returns_401(monkeypatch):
    _enable_auth(monkeypatch)

    def fake_verify(token):
        from app.auth.casdoor import CasdoorAuthError
        raise CasdoorAuthError("expired")

    monkeypatch.setattr(casdoor_mod, "verify_jwt", fake_verify)
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer bad"})
    assert r.status_code == 401


def test_auth_disabled_dev_mode():
    # conftest sets AUTH_ENABLED=false at import time
    os.environ["AUTH_ENABLED"] = "false"
    from app import config
    config.get_settings.cache_clear()
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["name"] == "dev"
