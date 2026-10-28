"""Shared MetaTrader5 session — avoid re-initialize on every health/market-data call."""
from __future__ import annotations


_cached_info = None


def terminal_info(*, wait: bool = True):
    """Read terminal status.

    ``wait=False`` never enters the MetaTrader DLL. ``terminal_info()`` can sit
    inside IPC for longer than a page load even when the Python lock is free,
    so request threads only return the last status a background read saved.
    """
    global _cached_info
    if not wait:
        return _cached_info
    try:
        from .mt5_gateway import run_mt5

        def _read():
            import MetaTrader5 as mt5  # type: ignore

            return mt5.terminal_info()

        ok, info = run_mt5(_read, timeout=None)
    except Exception:
        return None
    if not ok:
        return _cached_info
    _cached_info = info
    return info


def is_initialized() -> bool:
    return terminal_info() is not None


def connection_state(*, wait: bool = True) -> dict:
    ti = terminal_info(wait=wait)
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


# A missing timeout makes initialize() wait until the terminal answers. Startup and
# login must not sit behind that, especially while the Windows gateway already owns IPC.
_INIT_TIMEOUT_MS = 10_000


def initialize(path: str | None = None) -> bool:
    ok, _ = initialize_first([path] if path else [])
    return ok


def initialize_first(paths: list[str | None]) -> tuple[bool, str]:
    """Try each terminal64.exe until MT5 IPC attaches (broker terminal before generic install).

    The terminal lock is waited on for a few seconds. A page or Connect click must not
    sit behind a candle read, and it must not call the terminal while that read is inside
    the DLL — two overlapping IPC calls are what drops the attached session.
    """
    import MetaTrader5 as mt5  # type: ignore

    from .mt5_gateway import run_mt5

    ordered: list[str] = []
    for raw in paths:
        p = (raw or "").strip()
        if p and p not in ordered:
            ordered.append(p)

    def _init() -> tuple[bool, str]:
        global _cached_info
        info = mt5.terminal_info()
        if info is not None:
            _cached_info = info
            return True, ""
        for p in ordered:
            try:
                mt5.shutdown()
            except Exception:
                pass
            if mt5.initialize(path=p, timeout=_INIT_TIMEOUT_MS):
                _cached_info = mt5.terminal_info()
                return True, p
        if not ordered and mt5.initialize(timeout=_INIT_TIMEOUT_MS):
            _cached_info = mt5.terminal_info()
            return True, ""
        return False, ""

    acquired, result = run_mt5(_init, timeout=8)
    if not acquired or result is None:
        return False, ""
    return result


def shutdown() -> None:
    try:
        import MetaTrader5 as mt5  # type: ignore

        mt5.shutdown()
    except Exception:
        pass
