"""Production API path: /api routing, cookie sessions, health, DB guard, proxy secret and cTrader callback."""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from contextlib import contextmanager
from threading import Event

import pytest
from fastapi.testclient import TestClient

ADMIN = {"username": "Admin", "password": "P@882w0rd"}
CLIENT_HEADER = {"X-CT-Client": "web"}


def test_ctrader_inactive_callback_and_manual_activation_recovery(client, monkeypatch):
    _ctrader_env(monkeypatch)
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'ctrader')
    from apps.api.app.routers import ctrader
    from apps.api.app.core.database import db
    from apps.api.app.services.ctrader_application_state import APP_INACTIVE, application_state
    tenant = client.post('/api/auth/login', json=ADMIN).json()['user']['memberships'][0]['tenant_id']

    def start():
        r = client.post('/api/connections/ctrader/authorize', headers=CLIENT_HEADER, json={'tenant_id': tenant})
        assert r.status_code == 200
        query = parse_qs(urlparse(r.json()['authorize_url']).query)
        assert query['client_id'] == [os.environ['CTRADER_CLIENT_ID']]
        assert query['scope'] == ['accounts']
        assert 'client_secret' not in query
        return query['state'][0]

    def inactive_exchange(cfg, code):
        raise ctrader.CTraderProviderError('Application authentication failed: OA client is not in active state.')

    monkeypatch.setattr(ctrader, '_exchange', inactive_exchange)
    discovery = __import__('unittest.mock', fromlist=['Mock']).Mock()
    monkeypatch.setattr(ctrader, '_discover_accounts', discovery)
    state = start()
    r = client.get('/api/connections/ctrader/callback', params={'state': state, 'code': 'test-only-code'}, follow_redirects=False)
    assert 'ctrader=app_inactive' in r.headers['location']
    discovery.assert_not_called()
    with db() as c:
        assert application_state(c) == 'APP_INACTIVE'
        assert c.execute('SELECT COUNT(*) FROM ctrader_connections').fetchone()[0] == 0
    for _ in range(2):
        status = client.get('/api/connections/ctrader/status', params={'tenant_id': tenant}).json()
        assert status['provider_status'] == 'APP_INACTIVE'
        assert status['last_error_code'] == APP_INACTIVE
        assert status['authorization_status'] == 'PENDING_PROVIDER_ACTIVATION'
        assert status['connection_status'] == 'DISCONNECTED'
        assert not status['connected']
    from apps.api.app.routers import market_intelligence
    from apps.api.app.market.strength_engine import StrengthEngine
    engine = StrengthEngine()
    monkeypatch.setattr(market_intelligence, 'get_strength_engine', lambda: engine)
    matrix = client.get('/api/market-intelligence/matrix').json()
    assert matrix['meta']['error_code'] == APP_INACTIVE
    assert matrix['meta']['pairs_loaded'] == 0
    assert matrix['matrix'] == []

    # A manual retry after activation uses the normal state/token/account flow.
    state = start()
    monkeypatch.setattr(ctrader, '_exchange', lambda cfg, code: {'accessToken': 'test-access', 'refreshToken': 'test-refresh', 'expiresIn': 3600})
    monkeypatch.setattr(ctrader, '_discover_accounts', lambda token: [{'ctid_trader_account_id': 'test-account', 'environment': 'demo'}])
    r = client.get('/api/connections/ctrader/callback', params={'state': state, 'code': 'test-only-code'}, follow_redirects=False)
    assert 'ctrader=connected' in r.headers['location']
    status = client.get('/api/connections/ctrader/status', params={'tenant_id': tenant}).json()
    assert status['provider_status'] == 'CONNECTED'
    assert status['application_status'] == 'APPLICATION_ACTIVE'
    assert status['connected']


def test_ctrader_worker_decodes_inactive_error_without_proceeding():
    from types import SimpleNamespace
    from apps.api.app.services.ctrader_discovery_worker import decode_response
    response = SimpleNamespace(errorCode='CH_CLIENT_AUTH_FAILURE', description='OA client is not in active state')
    with pytest.raises(RuntimeError, match='^CTRADER_APP_INACTIVE$'):
        decode_response(object(), lambda message: response)
    success = SimpleNamespace()
    assert decode_response(object(), lambda message: success) is success


def test_ctrader_inactive_does_not_retry_token_refresh(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db
    from apps.api.app.routers import ctrader
    from apps.api.app.services.ctrader_application_state import record_application_state
    with db() as c:
        record_application_state(c, 'APP_INACTIVE')
    monkeypatch.setattr(ctrader, '_refresh', lambda *args: pytest.fail('Inactive application must not auto-refresh'))
    row = ctrader._refresh_if_needed({'authorization_status': 'AUTHORIZED', 'access_token': 'test-only'}, ctrader.ctrader_config())
    assert row['authorization_status'] == 'PENDING_PROVIDER_ACTIVATION'
    assert row['connection_status'] == 'DISCONNECTED'


def test_main_imports_under_vercel_without_database_url():
    env = os.environ.copy()
    env["VERCEL"] = "1"
    env["APP_ENV"] = "production"
    env.pop("DATABASE_URL", None)
    command = (
        "from apps.api.app.main import app; "
        "assert any(getattr(route, 'path', None) == '/api/health/live' for route in app.routes); "
        "from apps.api.app.services.bootstrap import _migration_dir; "
        "assert list(_migration_dir().glob('*.sql')); "
        "from apps.api.app.routers.ctrader import ctrader_discovery_worker; "
        "assert ctrader_discovery_worker.__file__.endswith('ctrader_discovery_worker.py')"
    )
    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


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
        live = client.get("/api/health/live")
        assert not bootstrap_started.is_set()
        ready = client.get("/api/health/ready")
        me = client.get("/api/auth/me")
        login = client.post("/api/auth/login", json={"username": "missing", "password": "wrong"})

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 503
    assert ready.json()["database"] == "unavailable"
    assert bootstrap_started.is_set()
    assert me.status_code == 401
    assert login.status_code == 503
    assert login.json()["detail"] == "Database unavailable"
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

def test_vercel_service_ingress_does_not_require_external_proxy_secret(client, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("API_PROXY_SECRET", "configured-secret")
    forwarded = {"x-forwarded-for": "203.0.113.7"}

    me = client.get("/api/auth/me", headers=forwarded)
    login = client.post("/api/auth/login", json={"username": "missing", "password": "wrong"}, headers=forwarded)

    assert me.status_code == 401
    assert login.status_code == 401


def _ctrader_env(monkeypatch):
    monkeypatch.setenv("CTRADER_CLIENT_ID", "client-id-test")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "client-secret-test")
    monkeypatch.setenv("CTRADER_REDIRECT_URI", "https://cacsms-traders.vercel.app/api/connections/ctrader/callback")
    monkeypatch.setenv("CTRADER_ENVIRONMENT", "demo")


def test_ctrader_token_encryption_uses_server_secret(monkeypatch):
    from apps.api.app.core.security import decrypt_ctrader_token, encrypt_ctrader_token, is_encrypted_ctrader_token

    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "server-only-test-secret")
    encrypted = encrypt_ctrader_token("token-value-that-must-not-be-stored-plaintext")

    assert is_encrypted_ctrader_token(encrypted)
    assert "token-value-that-must-not-be-stored-plaintext" not in encrypted
    assert decrypt_ctrader_token(encrypted) == "token-value-that-must-not-be-stored-plaintext"

    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "rotated-server-secret")
    with pytest.raises(ValueError, match="cannot be decrypted"):
        decrypt_ctrader_token(encrypted)


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
    monkeypatch.setattr(
        ctrader,
        "_discover_accounts",
        lambda access: [
            {
                "ctid_trader_account_id": "123456789",
                "trader_login": "7654321",
                "broker_name": "IC Markets",
                "account_type": "HEDGED",
                "currency_code": "USD",
                "environment": "demo",
            }
        ] if access == "ACCESS-TOKEN-XYZ" else [],
    )
    login = client.post("/api/auth/login", json=ADMIN).json()
    user = login["user"]
    tenant_id = user["memberships"][0]["tenant_id"]

    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id})
    assert status.json()["configured"] is True
    assert status.json()["connected"] is False

    auth = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    assert auth.status_code == 200, auth.text
    url = auth.json()["authorize_url"]
    assert "client-secret-test" not in url
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["accounts"]
    assert query["redirect_uri"] == ["https://cacsms-traders.vercel.app/api/connections/ctrader/callback"]
    state = query["state"][0]

    cb = client.get("/api/connections/ctrader/callback", params={"code": "AUTH-CODE", "state": state}, follow_redirects=False)
    assert cb.status_code == 303
    assert "ctrader=connected" in cb.headers["location"]
    assert "#/system-control/mt5" in cb.headers["location"]
    assert seen["code"] == "AUTH-CODE"

    replay = client.get("/api/connections/ctrader/callback", params={"code": "AUTH-CODE", "state": state}, follow_redirects=False)
    assert "ctrader=invalid_state" in replay.headers["location"]

    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id})
    body = status.text
    assert status.json()["connected"] is True
    assert status.json()["accounts"] == [
        {
            "account": "****4321",
            "broker": "IC Markets",
            "account_type": "HEDGED",
            "environment": "demo",
            "currency": "USD",
            "authorization": "AUTHORIZED",
            "last_sync_at": status.json()["accounts"][0]["last_sync_at"],
        }
    ]
    assert "ACCESS-TOKEN-XYZ" not in body and "REFRESH-TOKEN-XYZ" not in body and "client-secret-test" not in body
    from apps.api.app.core.database import db

    with db() as conn:
        stored = conn.execute("SELECT access_token,refresh_token,token_key_version FROM ctrader_connections WHERE tenant_id=?", (tenant_id,)).fetchone()
        audit_actions = {row["action"] for row in conn.execute("SELECT action FROM audit_events WHERE tenant_id=?", (tenant_id,)).fetchall()}
        audit_payloads = " ".join(row["new_json"] or "" for row in conn.execute("SELECT new_json FROM audit_events WHERE tenant_id=?", (tenant_id,)).fetchall())
        account = conn.execute("SELECT broker_name,environment,authorization_status FROM ctrader_accounts WHERE tenant_id=?", (tenant_id,)).fetchone()
    assert stored["access_token"].startswith("fernet:v1:")
    assert stored["refresh_token"].startswith("fernet:v1:")
    assert stored["token_key_version"] == 1
    assert {"CTRADER_OAUTH_STARTED", "CTRADER_OAUTH_COMPLETED", "CTRADER_ACCOUNT_DISCOVERED"} <= audit_actions
    assert "ACCESS-TOKEN-XYZ" not in audit_payloads and "REFRESH-TOKEN-XYZ" not in audit_payloads
    assert dict(account) == {"broker_name": "IC Markets", "environment": "demo", "authorization_status": "AUTHORIZED"}

    logout = client.post("/api/auth/logout", headers=CLIENT_HEADER)
    assert logout.status_code == 200
    relogin = client.post("/api/auth/login", json=ADMIN)
    assert relogin.status_code == 200
    persistent_status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id})
    assert persistent_status.status_code == 200
    assert persistent_status.json()["connected"] is True
    assert persistent_status.json()["accounts"][0]["broker"] == "IC Markets"


def test_ctrader_refresh_and_disconnect_preserve_account_audit(client, monkeypatch):
    from datetime import timedelta

    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db
    from apps.api.app.core.security import decrypt_ctrader_token, iso, now
    from apps.api.app.routers import ctrader

    monkeypatch.setattr(
        ctrader,
        "_exchange",
        lambda cfg, code: {"accessToken": "OLD-ACCESS", "refreshToken": "OLD-REFRESH", "tokenType": "bearer", "expiresIn": 2628000},
    )
    monkeypatch.setattr(
        ctrader,
        "_discover_accounts",
        lambda access: [{
            "ctid_trader_account_id": "987654321",
            "trader_login": "11223344",
            "broker_name": "IC Markets",
            "account_type": "HEDGED",
            "currency_code": "USD",
            "environment": "demo",
        }],
    )
    refreshed = {}

    def fake_refresh(cfg, token):
        refreshed["token"] = token
        return {"accessToken": "NEW-ACCESS", "refreshToken": "NEW-REFRESH", "tokenType": "bearer", "expiresIn": 2628000}

    monkeypatch.setattr(ctrader, "_refresh", fake_refresh)
    login = client.post("/api/auth/login", json=ADMIN).json()
    headers = {**CLIENT_HEADER, "Authorization": f"Bearer {login['access_token']}"}
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    start = client.post("/api/connections/ctrader/authorize", headers=headers, json={"tenant_id": tenant_id})
    state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
    callback = client.get("/api/connections/ctrader/callback", params={"code": "test-code", "state": state}, follow_redirects=False)
    assert "ctrader=connected" in callback.headers["location"]

    with db() as conn:
        conn.execute("UPDATE ctrader_connections SET expires_at=? WHERE tenant_id=?", (iso(now() - timedelta(seconds=1)), tenant_id))
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}, headers=headers).json()

    assert refreshed["token"] == "OLD-REFRESH"
    assert status["connected"] is True
    disconnected = client.post("/api/connections/ctrader/disconnect", headers=headers, json={"tenant_id": tenant_id})
    assert disconnected.status_code == 200
    status_after = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}, headers=headers).json()
    assert status_after["connected"] is False
    assert status_after["authorization_status"] == "REVOKED"
    assert status_after["accounts"][0]["authorization"] == "REVOKED"

    with db() as conn:
        token_row = conn.execute("SELECT access_token,refresh_token FROM ctrader_connections WHERE tenant_id=?", (tenant_id,)).fetchone()
        account_count = conn.execute("SELECT count(*) n FROM ctrader_accounts WHERE tenant_id=?", (tenant_id,)).fetchone()["n"]
        audit_actions = {row["action"] for row in conn.execute("SELECT action FROM audit_events WHERE tenant_id=?", (tenant_id,)).fetchall()}
    assert token_row["access_token"] == ""
    assert token_row["refresh_token"] is None
    assert account_count == 1
    assert "CTRADER_TOKEN_REFRESHED" in audit_actions
    assert "CTRADER_DISCONNECTED" in audit_actions


def test_ctrader_status_does_not_cross_tenant(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db

    login = client.post("/api/auth/login", json=ADMIN).json()
    headers = {"Authorization": f"Bearer {login['access_token']}"}
    with db() as conn:
        conn.execute(
            "INSERT INTO tenants(id,name,slug,status,reporting_currency,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            ("tenant-isolated", "Isolated", "isolated", "ACTIVE", "USD", "2026-01-01", "2026-01-01"),
        )
        conn.execute(
            """INSERT INTO ctrader_connections(id,tenant_id,environment,access_token,refresh_token,token_type,expires_at,created_at,updated_at,
                 authorization_status,connection_status,token_key_version,permission_scope)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("connection-other", "tenant-cacsms", "demo", "", None, None, None, "2026-01-01", "2026-01-01", "REVOKED", "DISCONNECTED", 0, "accounts"),
        )
        conn.execute(
            """INSERT INTO ctrader_accounts(tenant_id,ctid_trader_account_id,broker_name,environment,authorization_status,last_synced_at,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            ("tenant-cacsms", "sensitive-id", "IC Markets", "demo", "AUTHORIZED", "2026-01-01", "2026-01-01", "2026-01-01"),
        )

    status = client.get("/api/connections/ctrader/status", params={"tenant_id": "tenant-isolated"}, headers=headers)
    assert status.status_code == 200
    assert status.json()["accounts"] == []
    assert status.json()["connected"] is False


def test_ctrader_configuration_rejects_live_and_callback_mismatch(monkeypatch):
    from apps.api.app.routers.ctrader import ctrader_config

    _ctrader_env(monkeypatch)
    monkeypatch.setenv("CTRADER_ENVIRONMENT", "live")
    assert ctrader_config() is None
    monkeypatch.setenv("CTRADER_ENVIRONMENT", "demo")
    monkeypatch.setenv("CTRADER_REDIRECT_URI", "https://example.invalid/api/connections/ctrader/callback")
    assert ctrader_config() is None


def test_ctrader_discovery_failure_never_reports_connected(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db
    from apps.api.app.routers import ctrader

    monkeypatch.setattr(
        ctrader,
        "_exchange",
        lambda cfg, code: {"accessToken": "ACCESS-FAILURE", "refreshToken": "REFRESH-FAILURE", "tokenType": "bearer", "expiresIn": 3600},
    )

    def fail_discovery(_access):
        raise ctrader.CTraderProviderError("provider_unavailable")

    monkeypatch.setattr(ctrader, "_discover_accounts", fail_discovery)
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    auth = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    state = parse_qs(urlparse(auth.json()["authorize_url"]).query)["state"][0]

    callback = client.get("/api/connections/ctrader/callback", params={"code": "test-code", "state": state}, follow_redirects=False)
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()

    assert "ctrader=discovery_failed" in callback.headers["location"]
    assert status["connected"] is False
    assert status["connection_status"] == "DISCOVERY_FAILED"
    assert status["authorization_status"] == "AUTHORIZED"
    assert status["accounts"] == []
    with db() as conn:
        row = conn.execute("SELECT access_token,refresh_token FROM ctrader_connections WHERE tenant_id=?", (tenant_id,)).fetchone()
    assert row["access_token"].startswith("fernet:v1:")
    assert "ACCESS-FAILURE" not in row["access_token"]


def test_ctrader_expired_oauth_state_is_rejected(client, monkeypatch):
    from apps.api.app.core.database import db

    _ctrader_env(monkeypatch)
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    authorize = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    state = parse_qs(urlparse(authorize.json()["authorize_url"]).query)["state"][0]
    with db() as conn:
        conn.execute("UPDATE ctrader_oauth_states SET expires_at=? WHERE state_hash=?", ("2000-01-01T00:00:00+00:00", __import__("hashlib").sha256(state.encode()).hexdigest()))

    callback = client.get("/api/connections/ctrader/callback", params={"code": "unused", "state": state}, follow_redirects=False)
    assert "ctrader=invalid_state" in callback.headers["location"]


def test_ctrader_status_fails_closed_after_encryption_key_rotation(client, monkeypatch):
    from datetime import timedelta

    _ctrader_env(monkeypatch)
    from apps.api.app.core.security import encrypt_ctrader_token, iso, now
    from apps.api.app.core.database import db

    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    with db() as conn:
        conn.execute(
            """INSERT INTO ctrader_connections(id,tenant_id,environment,access_token,refresh_token,token_type,expires_at,connected_by,created_at,updated_at,
                 authorization_status,connection_status,token_key_version,permission_scope,last_successful_connection_at,last_sync_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "rotation-test", tenant_id, "demo", encrypt_ctrader_token("access-before-rotation"),
                encrypt_ctrader_token("refresh-before-rotation"), "bearer", iso(now() + timedelta(days=1)),
                login["user"]["id"], iso(), iso(), "AUTHORIZED", "CONNECTED", 1, "accounts", iso(), iso(),
            ),
        )
        conn.execute(
            """INSERT INTO ctrader_accounts(tenant_id,ctid_trader_account_id,trader_login,broker_name,environment,currency_code,
                 authorization_status,last_synced_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, "rotation-account", "99887766", "IC Markets", "demo", "USD", "AUTHORIZED", iso(), iso(), iso()),
        )

    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "rotated-test-secret")
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()

    assert status["connected"] is False
    assert status["authorization_status"] == "REAUTH_REQUIRED"
    assert status["accounts"][0]["authorization"] == "REAUTH_REQUIRED"


def test_ctrader_management_is_tenant_scoped(client):
    from apps.api.app.core.database import db
    from apps.api.app.core.security import hash_password, iso

    admin = client.post("/api/auth/login", json=ADMIN).json()
    admin_headers = {"Authorization": f"Bearer {admin['access_token']}"}
    tenant_response = client.post(
        "/api/tenants",
        headers=admin_headers,
        json={"name": "cTrader Tenant B", "slug": "ctrader-tenant-b", "reporting_currency": "USD"},
    )
    other_tenant = tenant_response.json()["id"]
    timestamp = iso()
    user_id = "ctrader-tenant-b-user"
    role_id = "ctrader-tenant-b-role"
    with db() as conn:
        conn.execute(
            "INSERT INTO roles(id,tenant_id,name,description,created_at) VALUES(?,?,?,?,?)",
            (role_id, other_tenant, "Connection Manager", "Tenant cTrader manager", timestamp),
        )
        for code in ("connections.read", "connections.manage"):
            conn.execute(
                "INSERT INTO role_permissions(role_id,permission_id) VALUES(?,?)",
                (role_id, f"perm-{code}"),
            )
        conn.execute(
            """INSERT INTO users(id,username,email,password_hash,first_name,last_name,display_name,status,is_platform_admin,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, "tenantb-ctrader", "tenantb@example.test", hash_password("TenantBPass!123"), "Tenant", "B", "Tenant B", "ACTIVE", 0, timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO tenant_memberships(id,tenant_id,user_id,role_id,status,created_at) VALUES(?,?,?,?,?,?)",
            ("tenant-b-membership", other_tenant, user_id, role_id, "ACTIVE", timestamp),
        )
        conn.execute(
            """INSERT INTO ctrader_connections(id,tenant_id,environment,access_token,refresh_token,token_type,created_at,updated_at,
                 authorization_status,connection_status,token_key_version,permission_scope)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("tenant-a-connection", "tenant-cacsms", "demo", "", None, None, timestamp, timestamp, "REVOKED", "DISCONNECTED", 0, "accounts"),
        )

    tenant_b = client.post("/api/auth/login", json={"username": "tenantb-ctrader", "password": "TenantBPass!123"}).json()
    headers = {"Authorization": f"Bearer {tenant_b['access_token']}"}
    own_status = client.get("/api/connections/ctrader/status", params={"tenant_id": other_tenant}, headers=headers)
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": "tenant-cacsms"}, headers=headers)
    disconnect = client.post("/api/connections/ctrader/disconnect", headers=headers, json={"tenant_id": "tenant-cacsms"})

    assert own_status.status_code == 200
    assert own_status.json()["can_manage"] is True
    assert status.status_code == 403
    assert disconnect.status_code == 403


def test_environment_observation_does_not_force_inactive(client, monkeypatch):
    _ctrader_env(monkeypatch)
    monkeypatch.setenv("CTRADER_APPLICATION_OBSERVATION", "CTRADER_APP_INACTIVE")
    from apps.api.app.routers import ctrader

    monkeypatch.setattr(ctrader, "probe_application", lambda: "UNVERIFIED")
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()
    assert status["provider_status"] == "APPLICATION_UNVERIFIED"
    assert status["application_status"] == "UNVERIFIED"
    assert status["connected"] is False
    assert status["execution_available"] is False
    assert any(item["code"] == "application" and item["status"] == "UNVERIFIED" for item in status["diagnostics"])


def test_stale_inactive_is_replaced_only_by_a_provider_result(client, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone

    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db
    from apps.api.app.routers import ctrader
    from apps.api.app.services.ctrader_application_state import application_state, record_application_state

    with db() as conn:
        record_application_state(conn, "APP_INACTIVE")
        row = conn.execute("SELECT value_json FROM system_settings WHERE key='ctrader.application_state'").fetchone()
        observation = json.loads(row["value_json"])
        observation["observed_at"] = (datetime.now(timezone.utc) - timedelta(seconds=901)).isoformat()
        conn.execute(
            "UPDATE system_settings SET value_json=? WHERE key='ctrader.application_state'",
            (json.dumps(observation),),
        )
        assert application_state(conn) == "UNKNOWN"

    monkeypatch.setattr(ctrader, "probe_application", lambda: "ACTIVE")
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()
    assert status["application_status"] == "APPLICATION_ACTIVE"
    assert status["provider_status"] == "OAUTH_NOT_AUTHORIZED"
    assert status["connected"] is False
    assert "Select Connect cTrader" in status["message"]


def test_fresh_provider_rejection_stays_inactive(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.routers import ctrader

    monkeypatch.setattr(ctrader, "probe_application", lambda: "APP_INACTIVE")
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()
    assert status["provider_status"] == "APP_INACTIVE"
    assert status["authorization_status"] == "PENDING_PROVIDER_ACTIVATION"
    assert status["connected"] is False
    started = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    assert started.status_code == 200
    assert "grantingaccess" in started.json()["authorize_url"]


def test_discovered_live_account_is_stored(client, monkeypatch):
    _ctrader_env(monkeypatch)
    from apps.api.app.core.database import db
    from apps.api.app.routers import ctrader

    monkeypatch.setattr(ctrader, "probe_application", lambda: "ACTIVE")
    monkeypatch.setattr(
        ctrader,
        "_exchange",
        lambda cfg, code: {"accessToken": "LIVE-ACCESS", "refreshToken": "LIVE-REFRESH", "expiresIn": 3600},
    )
    monkeypatch.setattr(
        ctrader,
        "_discover_accounts",
        lambda token: [
            {"ctid_trader_account_id": "demo-1", "trader_login": "100", "broker_name": "Broker", "environment": "demo"},
            {"ctid_trader_account_id": "live-1", "trader_login": "200", "broker_name": "Broker", "environment": "live"},
        ],
    )
    login = client.post("/api/auth/login", json=ADMIN).json()
    tenant_id = login["user"]["memberships"][0]["tenant_id"]
    started = client.post("/api/connections/ctrader/authorize", headers=CLIENT_HEADER, json={"tenant_id": tenant_id})
    state = parse_qs(urlparse(started.json()["authorize_url"]).query)["state"][0]
    callback = client.get("/api/connections/ctrader/callback", params={"code": "code", "state": state}, follow_redirects=False)
    assert "ctrader=connected" in callback.headers["location"]
    status = client.get("/api/connections/ctrader/status", params={"tenant_id": tenant_id}).json()
    assert status["connected"] is True
    assert status["execution_available"] is False
    assert {account["environment"] for account in status["accounts"]} == {"demo", "live"}
    with db() as conn:
        stored = {row["environment"] for row in conn.execute("SELECT environment FROM ctrader_accounts WHERE tenant_id=?", (tenant_id,)).fetchall()}
    assert stored == {"demo", "live"}
