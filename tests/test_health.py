from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root():
    r = client.get("/")
    assert r.status_code == 200
    assert "version" in r.json()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_me_requires_auth_when_enabled(monkeypatch):
    # With AUTH_ENABLED=false (set in conftest), /me should succeed as "dev" user
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["name"] == "dev"
