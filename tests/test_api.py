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


def test_mt5_disconnect_reports_disconnected(client, monkeypatch):
    from apps.api.app.market import mt5_session

    live = {"on": False}

    def fake_initialize(path=None):
        live["on"] = True
        return True

    def fake_shutdown():
        live["on"] = False

    def fake_is_initialized():
        return live["on"]

    def fake_connection_state():
        if live["on"]:
            return {"connected": True, "adapter": "MT5", "message": "MetaTrader 5 Test"}
        return {"connected": False, "adapter": "MT5", "message": "Not connected — use Connect in System Control"}

    def fake_initialize_first(paths):
        live["on"] = True
        used = next((p for p in paths if p), r"C:\Program Files\MetaTrader 5\terminal64.exe")
        return True, used

    monkeypatch.setattr(mt5_session, "initialize", fake_initialize)
    monkeypatch.setattr(mt5_session, "initialize_first", fake_initialize_first)
    monkeypatch.setattr(mt5_session, "shutdown", fake_shutdown)
    monkeypatch.setattr(mt5_session, "is_initialized", fake_is_initialized)
    monkeypatch.setattr(mt5_session, "connection_state", fake_connection_state)
    monkeypatch.setattr(mt5_session, "terminal_info", lambda: object() if live["on"] else None)
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.mt5_python_package_status",
        lambda: {"python_package": "installed", "version": "1.0", "hint": None},
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.auto_detect_terminal_path",
        lambda **kw: (r"C:\Program Files\MetaTrader 5\terminal64.exe", "filesystem"),
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection._terminal_path_from_mt5",
        lambda: r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )

    token, user = _login(client, username="Admin", password="P@882w0rd")
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = user["memberships"][0]["tenant_id"]

    r = client.post(
        f"/tenants/{tenant_id}/connections/gateway/connect",
        headers=h,
        json={"terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["gateway"]["status"] == "CONNECTED"

    r_off = client.post(f"/tenants/{tenant_id}/connections/gateway/disconnect", headers=h, json={})
    assert r_off.status_code == 200, r_off.text
    body = r_off.json()
    assert body["settings"]["session_status"] == "DISCONNECTED"
    assert body["gateway"]["status"] == "DISCONNECTED"

    r_get = client.get(f"/tenants/{tenant_id}/connections", headers=h)
    assert r_get.status_code == 200, r_get.text
    assert r_get.json()["gateway"]["status"] == "DISCONNECTED"
    assert r_get.json()["settings"]["session_status"] == "DISCONNECTED"


def test_mt5_auto_link_terminal(client, monkeypatch):
    from apps.api.app.market import mt5_session

    live = {"on": False}

    def fake_initialize_first(paths):
        live["on"] = True
        used = next((p for p in paths if p), r"C:\Program Files\MetaTrader 5\terminal64.exe")
        return True, used

    monkeypatch.setattr(mt5_session, "initialize", lambda path=None: live.__setitem__("on", True) or True)
    monkeypatch.setattr(mt5_session, "initialize_first", fake_initialize_first)
    monkeypatch.setattr(mt5_session, "shutdown", lambda: live.__setitem__("on", False))
    monkeypatch.setattr(mt5_session, "is_initialized", lambda: live["on"])
    monkeypatch.setattr(
        mt5_session,
        "connection_state",
        lambda: {"connected": live["on"], "adapter": "MT5", "message": "MetaTrader 5 Test"},
    )
    monkeypatch.setattr(mt5_session, "terminal_info", lambda: object() if live["on"] else None)
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.mt5_python_package_status",
        lambda: {"python_package": "installed", "version": "1.0", "hint": None},
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.auto_detect_terminal_path",
        lambda **kw: (r"C:\Program Files\MetaTrader 5\terminal64.exe", "filesystem"),
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection._terminal_path_from_mt5",
        lambda: r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )
    terminal_account = {
        "available": True,
        "login": "99887766",
        "server": "ICMarketsSC-Demo",
        "name": "Verify Demo",
        "company": "IC Markets",
        "currency": "USD",
        "trade_mode": "DEMO",
        "leverage": 500,
    }
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_terminal_account.read_terminal_account",
        lambda: terminal_account,
    )
    monkeypatch.setattr(
        "apps.api.app.routers.tenant_admin.read_terminal_account_for_tenant",
        lambda conn, tenant_id, *, force_attach=False, persist_snapshot=True: terminal_account,
    )

    token, user = _login(client, username="Admin", password="P@882w0rd")
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = user["memberships"][0]["tenant_id"]

    assert (
        client.post(
            f"/tenants/{tenant_id}/connections/gateway/connect",
            headers=h,
            json={"terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe"},
        ).status_code
        == 200
    )

    r = client.post(f"/tenants/{tenant_id}/connections/auto-link-terminal", headers=h, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["terminal_account"]["login"] == "99887766"

    listed = client.get(f"/tenants/{tenant_id}/connections", headers=h).json()
    assert len(listed["connections"]) >= 1
    assert listed["connections"][0]["account_number"] == "99887766"


def test_mt5_registry_sync_backfills_account(client, monkeypatch):
    from apps.api.app.market import mt5_session

    live = {"on": False}

    def fake_initialize_first(paths):
        live["on"] = True
        used = next((p for p in paths if p), r"C:\Program Files\MetaTrader 5\terminal64.exe")
        return True, used

    monkeypatch.setattr(mt5_session, "initialize", lambda path=None: live.__setitem__("on", True) or True)
    monkeypatch.setattr(mt5_session, "initialize_first", fake_initialize_first)
    monkeypatch.setattr(mt5_session, "shutdown", lambda: live.__setitem__("on", False))
    monkeypatch.setattr(mt5_session, "is_initialized", lambda: live["on"])
    monkeypatch.setattr(
        mt5_session,
        "connection_state",
        lambda: {"connected": live["on"], "adapter": "MT5", "message": "MetaTrader 5 Test"},
    )
    monkeypatch.setattr(mt5_session, "terminal_info", lambda: object() if live["on"] else None)
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.mt5_python_package_status",
        lambda: {"python_package": "installed", "version": "1.0", "hint": None},
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.auto_detect_terminal_path",
        lambda **kw: (r"C:\Program Files\MetaTrader 5\terminal64.exe", "filesystem"),
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection._terminal_path_from_mt5",
        lambda: r"C:\Program Files\MetaTrader 5\terminal64.exe",
    )
    terminal_account = {
        "available": True,
        "login": "11223344",
        "server": "ICMarketsSC-Demo",
        "name": "Verify Demo",
        "company": "IC Markets",
        "currency": "USD",
        "trade_mode": "DEMO",
        "leverage": 500,
        "balance": 10000.0,
        "equity": 10050.5,
        "margin": 120.0,
        "free_margin": 9930.5,
    }
    def _read_for_tenant(conn, tenant_id, *, force_attach=False, persist_snapshot=True):
        return terminal_account

    monkeypatch.setattr(
        "apps.api.app.domain.mt5_terminal_account.read_terminal_account",
        lambda: terminal_account,
    )
    monkeypatch.setattr(
        "apps.api.app.domain.mt5_connection.read_terminal_account_for_tenant",
        _read_for_tenant,
    )
    monkeypatch.setattr(
        "apps.api.app.routers.tenant_admin.read_terminal_account_for_tenant",
        _read_for_tenant,
    )

    token, user = _login(client, username="Admin", password="P@882w0rd")
    h = {"Authorization": f"Bearer {token}"}
    tenant_id = user["memberships"][0]["tenant_id"]

    aid = client.post(
        f"/tenants/{tenant_id}/accounts",
        headers=h,
        json={"account_name": "Registry Test Account", "environment": "DEMO"},
    ).json()["id"]

    client.post(
        f"/tenants/{tenant_id}/connections/gateway/connect",
        headers=h,
        json={"terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe"},
    )
    client.post(
        f"/tenants/{tenant_id}/connections",
        headers=h,
        json={"trading_account_id": aid, "adapter_type": "LOCAL_MT5"},
    )

    sync = client.post(f"/tenants/{tenant_id}/connections/sync-registry", headers=h, json={})
    assert sync.status_code == 200, sync.text

    listed = client.get(f"/tenants/{tenant_id}/connections", headers=h).json()
    assert listed["connections"][0]["account_number"] == "11223344"
    assert listed["connections"][0]["server_name"] == "ICMarketsSC-Demo"
    assert listed["connections"][0]["status"] == "CONNECTED"
    accts = client.get(f"/tenants/{tenant_id}/accounts", headers=h).json()
    assert accts[0]["balance"] == 10000.0
    assert accts[0]["equity"] == 10050.5


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
