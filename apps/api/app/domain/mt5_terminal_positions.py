"""Read open positions from the attached MetaTrader 5 terminal.

This module only calls positions_get. It does not send, modify, or close an order.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_cached_positions: list[dict[str, Any]] | None = None
_cached_basis = "Open positions were last read from the MT5 terminal."


def read_terminal_positions(*, wait: bool = True) -> tuple[list[dict[str, Any]] | None, str]:
    """Return (positions, basis). None means the terminal could not be read.

    ``wait=False`` returns the last book and does not call the terminal, so a
    page load is not stuck inside MetaTrader IPC.
    """
    global _cached_positions, _cached_basis
    if not wait:
        if _cached_positions is not None:
            return _cached_positions, _cached_basis
        return None, "MT5 terminal is busy. Open positions refresh when the current read finishes."
    from ..market.mt5_gateway import run_mt5

    def _read():
        import MetaTrader5 as mt5  # type: ignore

        if mt5.terminal_info() is None:
            return None, "MT5 terminal is not attached. Open positions stay hidden until the terminal is connected."
        try:
            rows = mt5.positions_get()
        except Exception as exc:
            return None, f"MT5 positions could not be read: {exc}"
        return rows, None

    try:
        ok, payload = run_mt5(_read, timeout=None)
    except Exception as exc:
        return None, f"MT5 positions could not be read: {exc}"
    if not ok:
        if _cached_positions is not None:
            return _cached_positions, _cached_basis
        return None, "MT5 terminal is busy. Open positions refresh when the current read finishes."
    rows, early = payload
    if early:
        return None, early
    if rows is None:
        import MetaTrader5 as mt5  # type: ignore
        err = mt5.last_error()
        return None, f"MT5 positions_get failed: {err}"
    import MetaTrader5 as mt5  # type: ignore
    positions = []
    for row in rows:
        ticket = getattr(row, "ticket", None)
        if ticket is None:
            continue
        side = int(getattr(row, "type", -1))
        if side == int(getattr(mt5, "POSITION_TYPE_BUY", 0)):
            direction = "BUY"
        elif side == int(getattr(mt5, "POSITION_TYPE_SELL", 1)):
            direction = "SELL"
        else:
            continue
        opened = getattr(row, "time", None)
        opened_at = datetime.fromtimestamp(int(opened), timezone.utc).isoformat() if opened else None
        positions.append({
            "ticket": str(ticket),
            "symbol": str(getattr(row, "symbol", "") or ""),
            "direction": direction,
            "volume": float(getattr(row, "volume", 0) or 0),
            "priceOpen": float(getattr(row, "price_open", 0) or 0),
            "priceCurrent": float(getattr(row, "price_current", 0) or 0),
            "stopLoss": float(getattr(row, "sl", 0) or 0),
            "takeProfit": float(getattr(row, "tp", 0) or 0),
            "profit": float(getattr(row, "profit", 0) or 0),
            "openedAt": opened_at,
        })
    count = len(positions)
    noun = "position" if count == 1 else "positions"
    basis = f"{count} open {noun} read from the MT5 terminal."
    _cached_positions = positions
    _cached_basis = basis
    return positions, basis
