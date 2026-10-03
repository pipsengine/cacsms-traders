"""Read the account currently logged into the attached MetaTrader 5 terminal."""
from __future__ import annotations

from typing import Any

from ..market import mt5_session


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


def read_terminal_account() -> dict[str, Any] | None:
    if not mt5_session.is_initialized():
        return None
    try:
        import MetaTrader5 as mt5  # type: ignore

        ai = mt5.account_info()
        if ai is None:
            err = mt5.last_error()
            return {
                "available": False,
                "error": str(err) if err else "account_info() returned no data — log into MT5 and retry.",
            }
        login = getattr(ai, "login", None)
        return {
            "available": True,
            "login": str(login) if login is not None else "",
            "server": (getattr(ai, "server", None) or "").strip(),
            "name": (getattr(ai, "name", None) or "").strip(),
            "company": (getattr(ai, "company", None) or "").strip(),
            "currency": (getattr(ai, "currency", None) or "").strip(),
            "trade_mode": _trade_mode_label(int(getattr(ai, "trade_mode", 0) or 0)),
            "leverage": int(getattr(ai, "leverage", 0) or 0),
            "balance": float(getattr(ai, "balance", 0) or 0),
            "equity": float(getattr(ai, "equity", 0) or 0),
            "margin": float(getattr(ai, "margin", 0) or 0),
            "free_margin": float(getattr(ai, "margin_free", 0) or 0),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def environment_from_terminal(trade_mode: str) -> str:
    if trade_mode == "LIVE":
        return "LIVE"
    if trade_mode == "CONTEST":
        return "PROP_FIRM"
    return "DEMO"
