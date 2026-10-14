"""Read open positions from the attached MetaTrader 5 terminal.

This module only calls positions_get. It does not send, modify, or close an order.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..market import mt5_session


def read_terminal_positions() -> tuple[list[dict[str, Any]] | None, str]:
    """Return (positions, basis). None means the terminal could not be read."""
    if not mt5_session.is_initialized() and not mt5_session.initialize():
        return None, "MT5 terminal is not attached. Open positions stay hidden until the terminal is connected."
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        return None, f"MT5 positions could not be read: {exc}"
    try:
        rows = mt5.positions_get()
    except Exception as exc:
        return None, f"MT5 positions could not be read: {exc}"
    if rows is None:
        err = mt5.last_error()
        return None, f"MT5 positions_get failed: {err}"
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
    return positions, f"{count} open {noun} read from the MT5 terminal."
