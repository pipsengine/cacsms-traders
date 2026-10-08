"""XAUUSD chart timeframes include M1 through W1, and a chart can be drawn for any of them."""
from datetime import datetime, timedelta, timezone

from apps.api.app.autonomous.read_model import display_channel
from apps.api.app.market.scanner_config import CHART_TIMEFRAMES, EXTRA_INGEST_TIMEFRAMES

INCLUSIVE = ("M1", "M5", "M15", "H1", "H4", "W1")


def test_xauusd_ingestion_includes_every_chart_timeframe():
    for tf in INCLUSIVE:
        assert tf in EXTRA_INGEST_TIMEFRAMES
        assert CHART_TIMEFRAMES[tf] == tf


def test_display_channel_draws_any_inclusive_timeframe():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    candles = []
    px = 4100.0
    for i in range(40):
        o, c = px, px + (1.2 if i % 6 else -2.4)
        candles.append({"t": (start + timedelta(minutes=i)).isoformat(), "o": o, "h": max(o, c) + 0.8, "l": min(o, c) - 0.8, "c": c, "v": 10})
        px = c
    for tf in INCLUSIVE:
        view = display_channel("XAUUSD", tf, candles)
        assert view and view["timeframe"] == tf and view["digits"] == 2
        assert view["lines"]["upper"] and view["lines"]["lower"]
        assert view["quality"] is not None
