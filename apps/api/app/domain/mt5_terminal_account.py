"""Read the account currently logged into the attached MetaTrader 5 terminal."""
from __future__ import annotations

from typing import Any


def _trade_mode_label(trade_mode: int) -> str:
    try:
        import MetaTrader5 as mt5  # type: ignore

        if trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO:
            return "DEMO"
        if trade_mode == mt5.ACCOUNT_TRADE_MODE_CONTEST:
            return "CONTEST"
        if trade_mode == mt5.ACCOUNT_TRADE_MODE_REAL:
            return "LIVE"
    except Exception:
        pass
    return str(trade_mode)


_cached_account: dict[str, Any] | None = None


def read_terminal_account(*, wait: bool = True) -> dict[str, Any] | None:
    """Read the logged-in account.

    ``wait=False`` returns the last read and does not call the terminal.
    ``account_info()`` blocks inside MetaTrader IPC even when the Python lock is free.
    """
    global _cached_account
    if not wait:
        return _cached_account
    from ..market.mt5_gateway import run_mt5

    def _read():
        import MetaTrader5 as mt5  # type: ignore

        if mt5.terminal_info() is None:
            return None
        ai = mt5.account_info()
        if ai is None:
            err = mt5.last_error()
            return {
                "available": False,
                "error": str(err) if err else "account_info() returned no data — log into MT5 and retry.",
            }
        login = getattr(ai, "login", None)
        info = mt5.terminal_info()
        return {
            "available": True,
            "terminal_connected": bool(info and getattr(info, "connected", False)),
            "login": str(login) if login is not None else "",
            "server": (getattr(ai, "server", None) or "").strip(),
            "name": (getattr(ai, "name", None) or "").strip(),
            "company": (getattr(ai, "company", None) or "").strip(),
            "currency": (getattr(ai, "currency", None) or "").strip(),
            "trade_mode": _trade_mode_label(int(getattr(ai, "trade_mode", 0) or 0)),
            "leverage": int(getattr(ai, "leverage", 0) or 0),
            "balance": float(getattr(ai, "balance", 0) or 0),
            "equity": float(getattr(ai, "equity", 0) or 0),
            "profit": float(getattr(ai, "profit", 0) or 0),
            "margin": float(getattr(ai, "margin", 0) or 0),
            "free_margin": float(getattr(ai, "margin_free", 0) or 0),
        }

    try:
        ok, account = run_mt5(_read, timeout=None)
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if not ok:
        return _cached_account
    if account and account.get("available"):
        _cached_account = account
    elif account is None:
        _cached_account = None
    return account


def environment_from_terminal(trade_mode: str) -> str:
    if trade_mode == "LIVE":
        return "LIVE"
    if trade_mode == "CONTEST":
        return "PROP_FIRM"
    return "DEMO"
