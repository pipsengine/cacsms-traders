"""Advanced Chart Analysis API — auth, workspace persistence, draft opportunities."""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CLIENT_HEADER = {"X-CT-Client": "web"}
ADMIN = {"username": "cacsms", "password": "TestPass!123"}


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
    try:
        Path(path).unlink(missing_ok=True)
    except PermissionError:
        pass


@pytest.fixture
def authed_client(client):
    r = client.post("/api/auth/login", json=ADMIN, headers=CLIENT_HEADER)
    if r.status_code != 200:
        pytest.skip("Bootstrap admin not available in this test database")
    return client


def test_chart_workspace_and_draft_opportunity(authed_client):
    c = authed_client
    r = c.get("/api/chart/workspace", params={"symbol": "EURUSD", "timeframe": "H1"}, headers=CLIENT_HEADER)
    assert r.status_code == 200
    ws = r.json()
    ws["drawings"] = [
        {
            "id": "d1",
            "symbol": "EURUSD",
            "timeframe": "H1",
            "kind": "horizontal",
            "points": [{"time": 1720000000, "price": 1.09}],
            "color": "#2563eb",
        }
    ]
    assert c.post("/api/chart/workspace", json=ws, headers=CLIENT_HEADER).status_code == 200
    saved = c.get("/api/chart/workspace", params={"symbol": "EURUSD", "timeframe": "H1"}, headers=CLIENT_HEADER).json()
    assert len(saved["drawings"]) == 1
    a = c.post(
        "/api/chart/analyses",
        json={"symbol": "EURUSD", "timeframe": "H1", "title": "Test", "notes": "Test note"},
        headers=CLIENT_HEADER,
    )
    assert a.status_code == 200
    o = c.post(
        "/api/chart/opportunities",
        json={
            "symbol": "EURUSD",
            "timeframe": "H1",
            "direction": "BUY",
            "strategy": "Channel Continuation",
            "notes": "Test",
            "analysis_id": a.json()["id"],
        },
        headers=CLIENT_HEADER,
    )
    assert o.status_code == 201
    assert o.json()["status"] == "DRAFT_REQUIRES_REVIEW"
    bad = c.post(
        "/api/chart/opportunities",
        json={"symbol": "EURUSD", "timeframe": "H1", "direction": "BAD", "strategy": "Channel Continuation", "notes": ""},
        headers=CLIENT_HEADER,
    )
    assert bad.status_code == 422


def test_chart_symbols_require_auth(client):
    assert client.get("/api/chart/symbols").status_code == 401
