"""Passive MT5 status: never initialize IPC, discover terminals, or reconnect on reads."""
from __future__ import annotations
import importlib.util
import os
from ..domain.mt5_terminal_account import read_terminal_account


def get_mt5_market_context(conn):
    from ..domain.mt5_connection import LocalMT5Gateway
    from ..market.market_data import configuration

    cfg = configuration(conn)
    tenant_id = (cfg.get('tenant_id') or cfg.get('mt5_tenant_id') or '').strip()
    if not tenant_id:
        from ..domain.mt5_connection import _active_tenant_id

        tenant_id = (_active_tenant_id(conn) or '').strip()
    persisted = False
    if tenant_id:
        settings = LocalMT5Gateway(tenant_id)._load_settings(conn)
        persisted = settings.get('session_status') == 'CONNECTED'
    # Reconnect stays on the session keeper. Doing it inside a page read blocks the overview.
    conn.commit()
    terminal = read_terminal_account(wait=False) or {}
    ipc = bool(terminal.get("available") or terminal.get("terminal_connected"))
    connected = bool(terminal.get("terminal_connected") or terminal.get("available"))
    authorized = bool(terminal.get('available'))
    return {
        'configured': importlib.util.find_spec('MetaTrader5') is not None and os.getenv('MT5_MODE', 'local').lower() not in ('off','disabled','null'),
        'mt5_connected': connected,
        'mt5_session_persisted': persisted,
        'mt5_ipc': ipc,
        'mt5_server': terminal.get('server') or 'MetaTrader 5',
        'authorized': authorized,
        'account_id': f"{terminal.get('server')}/{terminal.get('login')}" if authorized else None,
        'environment': terminal.get('trade_mode', 'UNKNOWN'),
        'market_data_ready': connected and authorized,
    }
