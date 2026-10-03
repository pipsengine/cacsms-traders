"""Shared MT5 / market-data context (same source as /health + tenant gateway)."""
from __future__ import annotations

import sqlite3

from ..domain.gateway import LocalMT5Gateway
from ..domain.mt5_connection import _active_tenant_id
from ..domain.mt5_terminal_account import read_terminal_account
from ..market import mt5_session


def get_mt5_market_context(conn: sqlite3.Connection) -> dict:
    active = _active_tenant_id(conn)
    gw = LocalMT5Gateway(active) if active else LocalMT5Gateway()
    # Read persisted session only — do not block on MT5 re-init during analysis requests.
    mt5 = gw.health(conn=conn, allow_reconnect=False)
    status = (mt5.get("status") or "").upper()
    session = (mt5.get("session_status") or "").upper()
    ipc = mt5_session.is_initialized()
    connected = status == "CONNECTED" or session == "CONNECTED" or ipc
    terminal = read_terminal_account()
    server = ""
    if terminal and terminal.get("available"):
        server = (terminal.get("server") or "").strip()
    if not server:
        server = (mt5.get("message") or "").strip()
    return {
        "mt5_connected": connected and ipc,
        "mt5_session_persisted": session == "CONNECTED",
        "mt5_ipc": ipc,
        "mt5_server": server or "MetaTrader 5",
        "market_data_ready": ipc,
    }
