"""Validate provider-persisted candles (Windows bridge uploads) with bulk reads instead of per-series gateway calls."""
from __future__ import annotations

from datetime import datetime, timezone

from .constants import FX_PAIRS_28
from .ingestion import RECENT_GAP_BARS, recent_gaps
from .normalized_provider import candle_close
from .provider_contract import MarketDataUnavailable
from .quality import assess
from .repository import MarketRepository


def store_failures(repo: MarketRepository, timeframes, broker_utc_offset_seconds: int = 0, now: datetime | None = None) -> list[dict]:
    """One query per timeframe covering all 28 pairs; same error codes as per-series ingestion."""
    now = now or datetime.now(timezone.utc)
    failures = []
    for tf in timeframes:
        series = repo.recent_candles(tf, RECENT_GAP_BARS)
        for pair in FX_PAIRS_28:
            bars = series.get(pair, [])
            error = None
            if not bars:
                error = "no_closed_bars"
            # H8 buckets straddle the weekend; their continuity is checked on the H1 bars they are built from.
            elif tf != "H8" and recent_gaps(bars, broker_utc_offset_seconds):
                error = "missing_candles"
            elif assess(pair, tf, bars[-1].close_time, now=now).state == "STALE":
                error = "stale_candles"
            if error:
                failures.append({"symbol": pair, "timeframe": tf, "error_code": error})
    return failures


def probe_open_times(repo: MarketRepository, symbol: str, broker_utc_offset_seconds: int = 0, now: datetime | None = None) -> dict[str, int]:
    """Latest closed-bar open time per timeframe for the probe symbol, omitting missing or stale timeframes."""
    now = now or datetime.now(timezone.utc)
    out = {}
    for tf, opened in repo.latest_open_times(symbol).items():
        try:
            closed = candle_close(opened, tf, broker_utc_offset_seconds)
        except MarketDataUnavailable:
            continue
        if assess(symbol, tf, closed, now=now).state != "STALE":
            out[tf] = int(opened.timestamp())
    return out
