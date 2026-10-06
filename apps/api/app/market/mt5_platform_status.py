"""Passive MT5 status: never initialize IPC, discover terminals, or reconnect on reads."""
from __future__ import annotations
import importlib.util
import os
from ..domain.mt5_terminal_account import read_terminal_account
from . import mt5_session


def get_mt5_market_context(conn):
    info = mt5_session.terminal_info()
    terminal = read_terminal_account() or {}
    ipc = info is not None
    connected = bool(info and getattr(info, 'connected', False))
    authorized = bool(terminal.get('available'))
    return {
        'configured': importlib.util.find_spec('MetaTrader5') is not None and os.getenv('MT5_MODE', 'local').lower() not in ('off','disabled','null'),
        'mt5_connected': connected,
        'mt5_session_persisted': False,
        'mt5_ipc': ipc,
        'mt5_server': terminal.get('server') or 'MetaTrader 5',
        'authorized': authorized,
        'account_id': f"{terminal.get('server')}/{terminal.get('login')}" if authorized else None,
        'environment': terminal.get('trade_mode', 'UNKNOWN'),
        'market_data_ready': connected and authorized,
    }
