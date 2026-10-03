"""Shared MetaTrader5 session — avoid re-initialize on every health/market-data call."""
from __future__ import annotations


def terminal_info():
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5.terminal_info()
    except Exception:
        return None


def is_initialized() -> bool:
    return terminal_info() is not None


def connection_state() -> dict:
    ti = terminal_info()
    if ti is None:
        return {
            "connected": False,
            "adapter": "MT5",
            "message": "Not connected — use Connect in System Control",
        }
    return {
        "connected": True,
        "adapter": "MT5",
        "message": getattr(ti, "name", None) or "MetaTrader 5",
    }


def initialize(path: str | None = None) -> bool:
    ok, _ = initialize_first([path] if path else [])
    return ok


def initialize_first(paths: list[str | None]) -> tuple[bool, str]:
    """Try each terminal64.exe until MT5 IPC attaches (broker terminal before generic install)."""
    import MetaTrader5 as mt5  # type: ignore

    if terminal_info() is not None:
        return True, ""
    ordered: list[str] = []
    for raw in paths:
        p = (raw or "").strip()
        if p and p not in ordered:
            ordered.append(p)
    for p in ordered:
        try:
            mt5.shutdown()
        except Exception:
            pass
        if mt5.initialize(path=p):
            return True, p
    if not ordered:
        if mt5.initialize():
            return True, ""
    return False, ""


def shutdown() -> None:
    try:
        import MetaTrader5 as mt5  # type: ignore

        mt5.shutdown()
    except Exception:
        pass
