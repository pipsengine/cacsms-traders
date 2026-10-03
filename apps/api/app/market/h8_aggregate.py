"""Build closed H8 candles from closed H1 series (MT5 has no native H8)."""
from __future__ import annotations

from datetime import datetime, timezone

from .models import Candle


def _epoch_seconds(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def aggregate_h8_from_h1(h1: list[Candle]) -> list[Candle]:
    """Group H1 bars into 8-hour buckets (UTC epoch aligned)."""
    if not h1:
        return []
    bucket_sec = 8 * 3600
    buckets: dict[int, list[Candle]] = {}
    for c in h1:
        if not c.is_closed:
            continue
        key = int(_epoch_seconds(c.open_time) // bucket_sec)
        buckets.setdefault(key, []).append(c)
    out: list[Candle] = []
    for key in sorted(buckets):
        bars = sorted(buckets[key], key=lambda x: x.open_time)
        if len(bars) < 8:
            continue
        bars = bars[-8:]
        out.append(
            Candle(
                symbol=bars[0].symbol,
                timeframe="H8",
                open_time=bars[0].open_time,
                close_time=bars[-1].close_time,
                open=bars[0].open,
                high=max(b.high for b in bars),
                low=min(b.low for b in bars),
                close=bars[-1].close,
                tick_volume=sum(b.tick_volume for b in bars),
                spread=bars[-1].spread,
                source=bars[0].source,
                is_closed=True,
            )
        )
    return out
