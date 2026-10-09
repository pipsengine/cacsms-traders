"""Shared normalization at the adapter boundary, including legacy method aliases."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math
from .models import Candle
from .provider_contract import MarketDataUnavailable


def candle_close(opened, timeframe, broker_utc_offset_seconds=0):
    tf = timeframe.upper()
    if tf in ('MN', 'MN1'):
        local = opened + timedelta(seconds=broker_utc_offset_seconds)
        return datetime(local.year + (local.month == 12), 1 if local.month == 12 else local.month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=broker_utc_offset_seconds)
    seconds = {'M1': 60, 'M5': 300, 'M15': 900, 'M30': 1800, 'H1': 3600, 'H4': 14400, 'H8': 28800, 'D1': 86400, 'W': 604800, 'W1': 604800}
    if tf not in seconds:
        raise MarketDataUnavailable('unsupported_timeframe')
    return opened + timedelta(seconds=seconds[tf])


class NormalizedProvider:
    def __init__(self, adapter, provider_id, account_context=None, observer=None):
        self.adapter = adapter
        self.provider_id = provider_id
        self.account_context = account_context
        self.observer = observer
        self._health = dict(provider=provider_id, configured=True, authorized=bool(account_context),
                            connected=False, healthy=False, market_data_available=False, execution_available=False,
                            last_heartbeat=None, last_market_data=None, last_error=None,
                            environment=(account_context or {}).get('environment', 'UNKNOWN'))

    def _check_account(self):
        if self.account_context:
            current = self.adapter.get_account_context() or {}
            if current.get('account_id') != self.account_context.get('account_id') or current.get('environment') != self.account_context.get('environment'):
                raise MarketDataUnavailable('provider_account_changed')

    def _request(self, callback, *args, **kwargs):
        try:
            self._check_account()
            value = callback(*args, **kwargs)
            self._check_account()
        except Exception:
            self._health.update(connected=False, healthy=False, market_data_available=False, last_error='provider_request_failed')
            if self.observer:
                self.observer(success=False, error='provider_request_failed')
            raise
        if self.observer:
            self.observer(success=True)
        self._health.update(connected=True, last_heartbeat=datetime.now(timezone.utc).isoformat())
        return value

    def get_symbols(self):
        return [{**row, 'provider': self.provider_id, 'account_id': (self.get_account_context() or {}).get('account_id', '')} for row in self._request(self.adapter.get_symbols)]

    def get_symbol(self, symbol):
        canonical = symbol.upper().replace('/', '')
        return next((s for s in self.get_symbols() if s.get('canonical_symbol') == canonical), None)

    def get_latest_price(self, symbol):
        return self._request(self.adapter.get_latest_price, symbol.upper().replace('/', ''))

    def get_candles(self, symbol, timeframe, *, start=None, end=None, count=400):
        # Read-only contract intentionally returns closed history; live quotes are separate.
        return self.get_closed_candles(symbol, timeframe, start=start, end=end, count=count)

    def get_closed_candles(self, symbol, timeframe, *, start=None, end=None, count=400):
        tf = {'W': 'W1', 'MN1': 'MN'}.get(timeframe.upper(), timeframe.upper())
        symbol = symbol.upper().replace('/', '')
        start = (start.replace(tzinfo=timezone.utc) if start.tzinfo is None else start.astimezone(timezone.utc)) if start else None
        end = (end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end.astimezone(timezone.utc)) if end else None
        if tf == 'H8':
            from .h8_aggregate import aggregate_h8_from_h1
            rows = aggregate_h8_from_h1(self.get_closed_candles(symbol, 'H1', start=start, end=end, count=count * 8 + 16))
        elif start is not None or end is not None:
            rows = self._request(self.adapter.get_closed_candles, symbol, tf, start=start, end=end, count=count)
        else:
            rows = self._request(self.adapter.closed_candles, symbol, tf, count)
        now = datetime.now(timezone.utc)
        normalized = {}
        for c in rows:
            opened = c.open_time.astimezone(timezone.utc) if c.open_time.tzinfo else c.open_time.replace(tzinfo=timezone.utc)
            closed = candle_close(opened, tf, (self.account_context or {}).get('broker_utc_offset_seconds', 0))
            if not c.is_closed or closed > now:
                continue
            if not all(math.isfinite(v) and v > 0 for v in (c.open, c.high, c.low, c.close)):
                continue
            if c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high):
                continue
            if (start is None or opened >= start) and (end is None or closed <= end):
                normalized[opened] = replace(c, symbol=symbol.upper().replace('/', ''), timeframe=tf, open_time=opened, close_time=closed, source=self.provider_id, account_id=(self.get_account_context() or {}).get('account_id', ''))
        result = [normalized[t] for t in sorted(normalized)][-count:]
        from .quality import assess
        fresh = bool(result and assess(symbol, tf, result[-1].close_time).state != 'STALE')
        # Historical backfills need not be fresh; they do not determine live availability.
        if end is None:
            self._health.update(healthy=fresh, market_data_available=fresh, last_error=None if fresh else 'stale_or_missing_candles')
            if fresh:
                self._health['last_market_data'] = datetime.now(timezone.utc).isoformat()
        # One stale series must not mark the whole provider unavailable; provider liveness has its own probes.
        if self.observer and end is None and fresh:
            self.observer(success=True, data_available=True, error=None)
        return result

    def closed_candles(self, symbol, timeframe, count=400):
        return self.get_closed_candles(symbol, timeframe, count=count)

    def latest_closed_open_time(self, symbol, timeframe):
        rows = self.get_closed_candles(symbol, timeframe, count=1)
        from .quality import assess
        if not rows or assess(symbol,timeframe,rows[-1].close_time).state == 'STALE':
            raise MarketDataUnavailable('stale_or_missing_candles')
        return int(rows[-1].open_time.timestamp())

    def current_closes(self, symbol, timeframe, count=400):
        return [(c.open_time, c.close) for c in self.closed_candles(symbol, timeframe, count)]

    def symbol_snapshot(self, symbol):
        return self._request(self.adapter.symbol_snapshot, symbol)

    def get_provider_health(self):
        return dict(self._health)

    def get_account_context(self):
        return self.account_context or self.adapter.get_account_context()
