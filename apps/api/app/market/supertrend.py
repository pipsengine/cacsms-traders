"""Supertrend sensor (ATR trailing band) on closed bars — direction, active line and last flip."""
from __future__ import annotations

from .scanner_analytics import Bar, true_ranges, wilder_atr

SUPERTREND_TIMEFRAMES = ("W", "D1", "H8", "H1")
BAR_KEYS = {"W": "W1", "D1": "D1", "H8": "H8", "H1": "H1"}


def supertrend(bars: list[Bar], period: int = 10, multiplier: float = 3.0) -> dict:
    """Classic Supertrend: the final band trails price and flips when a close crosses it."""
    if len(bars) < period + 2:
        return {"available": False}
    atr = wilder_atr(true_ranges(bars), period)
    offset = len(bars) - len(atr)
    upper_f = lower_f = None
    direction = 1
    flip_at = None
    line = None
    for k, a in enumerate(atr):
        b = bars[k + offset]
        prev_c = bars[k + offset - 1].c
        hl2 = (b.h + b.l) / 2
        ub, lb = hl2 + multiplier * a, hl2 - multiplier * a
        upper_f = ub if upper_f is None or ub < upper_f or prev_c > upper_f else upper_f
        lower_f = lb if lower_f is None or lb > lower_f or prev_c < lower_f else lower_f
        if direction == 1 and b.c < lower_f:
            direction, flip_at = -1, b.t.isoformat()
        elif direction == -1 and b.c > upper_f:
            direction, flip_at = 1, b.t.isoformat()
        line = lower_f if direction == 1 else upper_f
    return {
        "available": True,
        "direction": direction,
        "line": line,
        "atr": atr[-1],
        "flip_at": flip_at,
        "distance_atr": round((bars[-1].c - line) / atr[-1], 2) if atr[-1] else None,
        "period": period,
        "multiplier": multiplier,
    }


def supertrend_core(bars: dict[str, list[Bar]]) -> dict:
    return {tf: supertrend(bars[BAR_KEYS[tf]]) for tf in SUPERTREND_TIMEFRAMES}
