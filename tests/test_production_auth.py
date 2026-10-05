"""Production API path: /api routing, cookie sessions, health, DB guard, proxy secret and cTrader callback."""
from urllib.parse import parse_qs, urlparse
from contextlib import contextmanager
from threading import Event

import pytest
from fastapi.testclient import TestClient

ADMIN = {"username": "Admin", "password": "P@882w0rd"}
CLIENT_HEADER = {"X-CT-Client": "web"}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    for name in ("APP_ENV", "API_PROXY_SECRET", "CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_REDIRECT_URI"):
        monkeypatch.delenv(name, raising=False)
    from apps.api.app.main import app
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    with TestClient(app) as c:
        yield c


def test_public_health_reports_only_safe_fields(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["api"] == "reachable"
    assert body["database"] == "reachable"
    assert body["auth"] == "ready"
    assert body["environment"] == "development"
    assert set(body) == {"status", "api", "database", "bootstrap", "auth", "environment", "autonomous_services", "time"}
    assert set(body["autonomous_services"]) == {"strength_engine", "market_scanner", "intelligence_worker"}
    assert all(v in ("running", "stopped", "disabled") for v in body["autonomous_services"].values())


def test_vercel_liveness_survives_database_bootstrap_failure(monkeypatch, caplog):
    from fastapi.testclient import TestClient

    from apps.api.app import main as main_module
    from apps.api.app.routers import platform as platform_module

    database_url = "postgresql://user:secret@example.invalid/traders"
    bootstrap_started = Event()

    def fail_bootstrap():
        bootstrap_started.set()
        raise RuntimeError(f"migration failed for {database_url}")

    @contextmanager
    def unavailable_database():
        raise RuntimeError("database unavailable")
        yield

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(main_module, "bootstrap", fail_bootstrap)
    monkeypatch.setattr(platform_module, "db", unavailable_database)

    with TestClient(main_module.app) as client:
        assert bootstrap_started.wait(timeout=5)
        live = client.get("/api/health/live")
        ready = client.get("/api/health/ready")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 503
    assert ready.json()["database"] == "unavailable"
    assert database_url not in live.text + ready.text + caplog.text


def test_invalid_login_is_401_not_404(client):
    r = client.post("/api/auth/login", json={"username": "Admin", "password": "wrong-password"})
    assert r.status_code == 401


def test_cors_allows_configured_vercel_origin_with_credentials(monkeypatch):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from apps.api.app.core.config import cors_origins

    monkeypatch.setenv("WEB_ORIGINS", "https://cacsms-traders.vercel.app")
    probe = FastAPI()
    probe.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @probe.post("/api/auth/login")
    def _login():
        return {}

    r = TestClient(probe).options(
        "/api/auth/login",
        headers={
            "Origin": "https://cacsms-traders.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-ct-client",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://cacsms-traders.vercel.app"
    assert r.headers["access-control-allow-credentials"] == "true"


def test_routes_live_only_under_api_prefix(client):
    assert client.post("/auth/login", json=ADMIN).status_code == 404
    assert client.get("/health").status_code == 404
    assert client.post("/api/auth/login", json=ADMIN).status_code == 200


def test_cookie_session_login_me_logout(client):
    r = client.post("/api/auth/login", json=ADMIN)
    assert r.status_code == 200, r.text
    set_cookie = r.headers["set-cookie"]
    assert "ct_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/api" in set_cookie
    assert "samesite=lax" in set_cookie.lower()

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "Admin"

    assert client.post("/api/auth/logout").status_code == 403, "cookie writes require the client header"
    assert client.post("/api/auth/logout", headers=CLIENT_HEADER).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_protected_routes_reject_unauthenticated(client):
    for path in ("/api/auth/me", "/api/tenants", "/api/system/health", "/api/dashboard/summary"):
        assert client.get(path).status_code == 401, path
    assert client.get("/api/connections/ctrader/status", params={"tenant_id": "tenant-cacsms"}).status_code == 401


def test_production_cookie_is_secure(client, monkeypatch):
    from apps.api.app.core.config import session_cookie_secure

    monkeypatch.setenv("APP_ENV", "production")
    assert session_cookie_secure(False) is True
    monkeypatch.setenv("APP_ENV", "development")
    r = client.post("/api/auth/login", json=ADMIN, headers={"x-forwarded-proto": "https"})
    assert r.status_code == 200
    assert "Secure" in r.headers["set-cookie"]
    assert client.get("/api/health").json()["environment"] == "development"


def test_production_refuses_to_create_missing_database(monkeypatch, tmp_path):
    from apps.api.app.core.database import DatabaseUnavailable, connect

    missing = tmp_path / "missing" / "prod.db"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_PATH", str(missing))
    monkeypatch.delenv("DATABASE_ALLOW_CREATE", raising=False)
    with pytest.raises(DatabaseUnavailable):
        connect()
    assert not missing.exists()


def test_proxy_secret_enforced_for_forwarded_traffic(client, monkeypatch):
    monkeypatch.setenv("API_PROXY_SECRET", "s3cret-value")
    forwarded = {"X-Forwarded-For": "203.0.113.7"}
    assert client.get("/api/health", headers=forwarded).status_code == 403
    assert client.get("/api/health", headers={**forwarded, "x-ct-proxy-secret": "wrong"}).status_code == 403
    assert client.get("/api/health", headers={**forwarded, "x-ct-proxy-secret": "s3cret-value"}).status_code == 200
    assert client.get("/api/health").status_code == 200, "direct local calls stay allowed"


def _ctrader_env(monkeypatch):
    monkeypatch.setenv("CTRADER_CLIENT_ID", "client-id-test")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "client-secret-test")
    monkeypatch.setenv("CTRADER_REDIRECT_URI", "https://cacsms-traders.vercel.app/api/connections/ctrader/callback")
    monkeypatch.setenv("CTRADER_ENVIRONMENT", "demo")


def test_ctrader_callback_route_exists_and_rejects_bad_requests(client, monkeypatch):
    r = client.get("/api/connections/ctrader/callback", params={"code": "x", "state": "y"}, follow_redirects=False)
    assert r.status_code == 303
    assert "ctrader=not_configured" in r.headers["location"]

    _ctrader_env(monkeypatch)
    r = client.get("/api/connections/ctrader/callback", params={"code": "x", "state": "forged"}, follow_redirects=False)
    assert r.status_code == 303
    assert "ctrader=invalid_state" in r.headers["location"]

    r = client.get("/api/connections/ctrader/callback", follow_redirects=False)
    assert "ctrader=invalid_request" in r.headers["location"]


def test_ctrader_authorize_and_callback_store_tokens_server_side(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.routers import ctrader

    seen = {}

    def fake_exchange(cfg, code):
        seen["code"] = code
        return {"accessToken": "ACCESS-TOKEN-XYZ", "refreshToken": "REFRESH-TOKEN-XYZ", "tokenType": "bearer", "expiresIn": 2628000}

    monkeypatch.setattr(ctrader, "_exchange", fake_exchange)
    user = client.post("/api/auth/login", json=ADMIN).json()["user"]
    tenant_id = user["memberships"][0]["tenant_id"]

    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id})
    assert status.json()["configured"] is True
    assert status.json()["connected"] is False

    auth = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    assert auth.status_code == 200, auth.text
    url = auth.json()["authorize_url"]
    assert "client-secret-test" not in url
    state = parse_qs(urlparse(url).query)["state"][0]

    cb = client.get("/api/connections/ctrader/callback", params={"code": "AUTH-CODE", "state": state}, follow_redirects=False)
    assert cb.status_code == 303
    assert "ctrader=connected" in cb.headers["location"]
    assert seen["code"] == "AUTH-CODE"

    replay = client.get("/api/connections/ctrader/callback", params={"code": "AUTH-CODE", "state": state}, follow_redirects=False)
    assert "ctrader=invalid_state" in replay.headers["location"]

    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id})
    body = status.text
    assert status.json()["connected"] is True
    assert "ACCESS-TOKEN-XYZ" not in body and "REFRESH-TOKEN-XYZ" not in body and "client-secret-test" not in body
