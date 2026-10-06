from dataclasses import replace

from .quality import assess
from .normalized_provider import candle_close


def missing_between(previous, current, timeframe):
    missing = 0
    expected = candle_close(previous, timeframe)
    while expected < current:
        if timeframe.upper() in ('MN','MN1','W','W1') or expected.weekday() < 5:
            missing += 1
        expected = candle_close(expected, timeframe)
    return missing


def missing_candles(candles):
    """Count observed gaps; weekends are scheduled closures, never filled."""
    ordered = sorted(candles, key=lambda c: c.open_time)
    return sum(missing_between(previous.open_time,current.open_time,previous.timeframe) for previous,current in zip(ordered,ordered[1:]))


class CandleIngestionService:
    def __init__(self, gateway, repo):
        self.gateway = gateway
        self.repo = repo

    def sync(self, symbol, timeframe, count=400, *, store_as: str | None = None, start=None, end=None):
        store = (store_as or symbol).upper().replace("/", "")
        previous = self.repo.candles(store, timeframe, 1)
        candles = self.gateway.get_closed_candles(symbol, timeframe, count=count, start=start, end=end) if start is not None or end is not None else self.gateway.closed_candles(symbol, timeframe, count)
        candles = sorted(candles, key=lambda c:c.open_time)
        accepted = 0
        rejected = 0
        for c in candles:
            row = replace(c, symbol=store) if store != c.symbol else c
            if c.is_closed and c.high >= max(c.open, c.close, c.low) and c.low <= min(c.open, c.close, c.high):
                accepted += int(bool(self.repo.upsert_candle(row)))
            else:
                rejected += 1
        self.repo.conn.commit()
        last = candles[-1].close_time if candles else None
        bridge_missing = 0
        ordered = candles
        if previous and ordered:
            from datetime import datetime, timezone
            last_open = datetime.fromisoformat(previous[-1][0])
            last_open = last_open.replace(tzinfo=timezone.utc) if last_open.tzinfo is None else last_open
            if last_open < ordered[0].open_time:
                # An incremental window cannot silently jump across an outage.
                bridge_missing = missing_between(last_open,ordered[0].open_time,timeframe)
        missing = missing_candles(ordered) + bridge_missing
        quality = assess(store, timeframe, last, missing_bars=missing)
        return {
            "symbol": store,
            "timeframe": timeframe,
            "accepted": accepted,
            "rejected": rejected,
            "quality": quality.__dict__,
            **({'error': 'invalid_candles'} if rejected else {'error': 'missing_candles'} if missing else {'error': 'stale_candles'} if quality.state == 'STALE' else {}),
        }
