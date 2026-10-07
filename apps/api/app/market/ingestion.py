from dataclasses import replace
from datetime import timedelta

from .quality import assess
from .normalized_provider import candle_close


RECENT_GAP_BARS = 12
TICKLESS_TIMEFRAMES = ('M1', 'M5', 'M15')
MARKET_HOLIDAYS = ((12, 25), (1, 1))


def missing_between(previous, current, timeframe, broker_utc_offset_seconds=0):
    # Weekends and holidays follow the broker's session clock, not UTC (e.g. a UTC+3 week ends Friday 21:00 UTC).
    offset = timedelta(seconds=broker_utc_offset_seconds)
    missing = 0
    expected = candle_close(previous, timeframe, broker_utc_offset_seconds)
    while expected < current:
        local = expected + offset
        if timeframe.upper() in ('MN','MN1','W','W1') or (local.weekday() < 5 and (local.month, local.day) not in MARKET_HOLIDAYS):
            missing += 1
        expected = candle_close(expected, timeframe, broker_utc_offset_seconds)
    return missing


def missing_candles(candles, broker_utc_offset_seconds=0):
    """Count observed gaps; weekends are scheduled closures, never filled."""
    ordered = sorted(candles, key=lambda c: c.open_time)
    return sum(missing_between(previous.open_time,current.open_time,previous.timeframe,broker_utc_offset_seconds) for previous,current in zip(ordered,ordered[1:]))


def recent_gaps(candles, broker_utc_offset_seconds=0, window=RECENT_GAP_BARS):
    """Gaps that invalidate current analysis: only recent bars matter, and a lone intraday bar may be tick-less."""
    ordered = sorted(candles, key=lambda c: c.open_time)[-window:]
    gaps = [missing_between(a.open_time, b.open_time, a.timeframe, broker_utc_offset_seconds) for a, b in zip(ordered, ordered[1:])]
    tolerance = 1 if ordered and ordered[0].timeframe.upper() in TICKLESS_TIMEFRAMES else 0
    return sum(n for n in gaps if n > tolerance)


def broker_offset(gateway):
    context = gateway.get_account_context() if hasattr(gateway, 'get_account_context') else None
    value = context.get('broker_utc_offset_seconds') if isinstance(context, dict) else 0
    return value if isinstance(value, int) else 0


class CandleIngestionService:
    def __init__(self, gateway, repo):
        self.gateway = gateway
        self.repo = repo

    def sync(self, symbol, timeframe, count=400, *, store_as: str | None = None, start=None, end=None):
        store = (store_as or symbol).upper().replace("/", "")
        previous = self.repo.candles(store, timeframe, 1)
        candles = self.gateway.get_closed_candles(symbol, timeframe, count=count, start=start, end=end) if start is not None or end is not None else self.gateway.closed_candles(symbol, timeframe, count)
        candles = sorted(candles, key=lambda c:c.open_time)
        offset = broker_offset(self.gateway)
        # Bridge uploads already live in the provider candle store; re-upserting them row by row is pure overhead.
        persisted = store == symbol.upper().replace("/", "") and getattr(getattr(self.gateway, 'adapter', None), 'candles_persisted', False) is True
        accepted = 0
        rejected = 0
        for c in candles:
            row = replace(c, symbol=store) if store != c.symbol else c
            if c.is_closed and c.high >= max(c.open, c.close, c.low) and c.low <= min(c.open, c.close, c.high):
                accepted += 1 if persisted else int(bool(self.repo.upsert_candle(row)))
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
                bridge_missing = missing_between(last_open,ordered[0].open_time,timeframe,offset)
        missing = missing_candles(ordered, offset) + bridge_missing
        blocking = recent_gaps(ordered, offset) + bridge_missing
        quality = assess(store, timeframe, last, missing_bars=missing)
        return {
            "symbol": store,
            "timeframe": timeframe,
            "accepted": accepted,
            "rejected": rejected,
            "quality": quality.__dict__,
            **({'error': 'invalid_candles'} if rejected else {'error': 'missing_candles'} if blocking else {'error': 'stale_candles'} if quality.state == 'STALE' else {}),
        }
