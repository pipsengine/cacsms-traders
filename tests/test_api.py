import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    from apps.api.app.main import app

    with TestClient(app) as c:
        yield c
    Path(path).unlink(missing_ok=True)


def _login(client: TestClient, username="cacsms", password="TestPass!123"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    token = body["access_token"]
    return token, body["user"]


def test_health_and_reference_universe(client):
    assert client.get("/health").json()["database"] == "HEALTHY"
    token, _ = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    instruments = client.get("/reference/instruments", headers=h).json()
    currencies = client.get("/reference/currencies", headers=h).json()
    assert len(instruments) == 29
    assert any(c["code"] == "NGN" for c in currencies)
    assert any(c["code"] == "USD" for c in currencies)


def test_tenant_isolation_on_accounts(client):
    admin_token, _ = _login(client)
    ah = {"Authorization": f"Bearer {admin_token}"}
    other = client.post(
        "/tenants",
        headers=ah,
        json={"name": "Other Org", "slug": "other-org", "reporting_currency": "NGN"},
    ).json()["id"]
    client.post(
        f"/tenants/{other}/users",
        headers=ah,
        json={
            "username": "otheruser",
            "email": "other@example.com",
            "first_name": "Other",
            "last_name": "User",
            "password": "OtherPass!99",
        },
    )
    token, user = _login(client, username="otheruser", password="OtherPass!99")
    h = {"Authorization": f"Bearer {token}"}
    home = user["memberships"][0]["tenant_id"]
    assert home == other
    r = client.get("/tenants/tenant-cacsms/accounts", headers=h)
    assert r.status_code == 403


def test_trading_account_lifecycle(client):
    token, user = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = user["memberships"][0]["tenant_id"]
    created = client.post(
        f"/tenants/{tenant_id}/accounts",
        headers=h,
        json={
            "account_name": "Demo Primary",
            "environment": "DEMO",
            "account_currency": "USD",
        },
    ).json()
    accounts = client.get(f"/tenants/{tenant_id}/accounts", headers=h).json()
    assert any(a["id"] == created["id"] for a in accounts)
    audit = client.get(f"/tenants/{tenant_id}/audit", headers=h).json()
    assert any(e["action"] == "TRADING_ACCOUNT_CREATED" for e in audit)


def test_logout_revokes_session(client):
    token, _ = _login(client)
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=h).status_code == 200
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_super_admin_login(client):
    r = client.post("/auth/login", json={"username": "Admin", "password": "P@882w0rd"})
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert user["is_platform_admin"] is True
    assert user["is_system_protected"] is True
    assert user["username"] == "Admin"


def test_mt5_settings_persist(client):
    token, user = _login(client, username="Admin", password="P@882w0rd")
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = user["memberships"][0]["tenant_id"]
    path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    r = client.patch(
        f"/tenants/{tenant_id}/connections/settings",
        headers=h,
        json={"terminal_path": path, "auto_reconnect": True, "heartbeat_interval_seconds": 30},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["settings"]["terminal_path"] == path
    assert body["gateway"]["terminal_configured"] is True
    r2 = client.get(f"/tenants/{tenant_id}/connections", headers=h)
    assert r2.json()["settings"]["terminal_path"] == path


def test_super_admin_platform_access(client):
    token = client.post("/auth/login", json={"username": "Admin", "password": "P@882w0rd"}).json()[
        "access_token"
    ]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/tenants", headers=h).status_code == 200
