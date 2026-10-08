"""Chart image for a channel alert email (touch, break, retest, TiT).

Best-effort. Missing candles or a drawing failure omits the image and never blocks the email.
"""
from __future__ import annotations

import logging

from .chart_image import render_outlook_chart
from .outlook_charts import _candles

log = logging.getLogger("cacsms.notifications")
_CACHE: dict[str, tuple[str, bytes, str, str]] = {}
ALERT_CHART_TYPES = {"CHANNEL_TOUCH", "CHANNEL_BREAK", "BREAK_RETEST_CONTINUATION", "TIT_DETECTED"}
_STORED_TF = {"W": "W1", "W1": "W1"}


def _digits(symbol: str) -> int:
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


def _build(symbol: str, timeframe: str, direction: str | None) -> bytes:
    from ..autonomous.read_model import display_channel
    from ..core.database import db
    from ..market.repository import MarketRepository

    stored = _STORED_TF.get(timeframe, timeframe)
    with db() as conn:
        candles = _candles(MarketRepository(conn).candles(symbol, stored, 120))
    if len(candles) < 8:
        raise ValueError("not enough candles")
    channel = None
    try:
        view = display_channel(symbol, timeframe, candles)
        channel = (view or {}).get("lines")
    except Exception:
        log.warning("Channel lines for %s %s were left off the alert chart", symbol, timeframe, exc_info=True)
    return render_outlook_chart(symbol, candles, digits=_digits(symbol), direction=direction, channel=channel, timeframe=timeframe)


def alert_chart(event: dict) -> tuple[str, bytes, str, str] | None:
    """`(content-id, png, symbol, caption)` for one channel alert, or None when it cannot be drawn."""
    if event.get("event_type") not in ALERT_CHART_TYPES:
        return None
    symbol = (event.get("symbol") or "").upper()
    timeframe = (event.get("timeframe") or "H1").upper()
    if not symbol:
        return None
    key = str(event.get("id") or "")
    if key and key in _CACHE:
        return _CACHE[key]
    try:
        png = _build(symbol, timeframe, event.get("direction"))
    except Exception:
        log.warning("Chart for %s %s was left out of the alert email", symbol, timeframe, exc_info=True)
        return None
    caption = f"{timeframe} chart · channel"
    shot = (f"chart-{symbol}-{timeframe}", png, symbol, caption)
    if key:
        if len(_CACHE) > 32:
            _CACHE.clear()
        _CACHE[key] = shot
    return shot
