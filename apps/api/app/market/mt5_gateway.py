"""MetaTrader 5 market data adapter (closed bars only)."""
from __future__ import annotations

import functools
import os
import threading
from datetime import datetime, timezone

from .models import Candle
from .mt5_contract import MarketDataUnavailable

# One MetaTrader5 IPC session is shared by the strength engine and the market scanner threads.
MT5_LOCK = threading.RLock()


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with MT5_LOCK:
            return fn(*args, **kwargs)

    return wrapper

_TF_MAP = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "M30": "M30",
    "H1": "H1",
    "H4": "H4",
    "D1": "D1",
    "W1": "W1",
    "MN": "MN1",
}

_LIVE_TF_MAP = {**_TF_MAP, "H8": "H8", "W": "W1", "MN1": "MN1"}


def _broker_symbol(pair: str) -> str:
    prefix = os.getenv("MT5_SYMBOL_PREFIX", "")
    suffix = os.getenv("MT5_SYMBOL_SUFFIX", "")
    return f"{prefix}{pair.upper().replace('/', '')}{suffix}"


def symbol_candidates(pair: str) -> list[str]:
    """Try broker decoration and common IC Markets / MT5 suffix variants."""
    p = pair.upper().replace("/", "")
    prefix = os.getenv("MT5_SYMBOL_PREFIX", "")
    suffix = os.getenv("MT5_SYMBOL_SUFFIX", "")
    out: list[str] = []
    for s in (suffix, "", ".a", ".A", ".m", "m", ".raw", ".pro"):
        cand = f"{prefix}{p}{s}"
        if cand not in out:
            out.append(cand)
    if p not in out:
        out.append(p)
    return out


def _select_symbol(mt5, pair: str) -> str:
    for sym in symbol_candidates(pair):
        if mt5.symbol_select(sym, True):
            return sym
    return symbol_candidates(pair)[0]


class NullMarketDataGateway:
    """Fallback when MT5 is unavailable — never fabricates candles."""

    def connection_state(self) -> dict:
        return {
            "connected": False,
            "adapter": "NULL",
            "message": "MetaTrader5 package or terminal not available",
        }

    def closed_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        raise MarketDataUnavailable("MT5 market data is not connected")

    def latest_tick(self, symbol: str) -> dict:
        raise MarketDataUnavailable("MT5 market data is not connected")


class Mt5MarketDataGateway:
    provider_id = 'mt5'

    def get_symbols(self):
        from .constants import FX_PAIRS_28
        rows = []
        for symbol in (*FX_PAIRS_28, 'XAUUSD'):
            item = self.get_symbol(symbol)
            if item:
                rows.append(item)
        return rows

    @_locked
    def get_symbol(self, symbol):
        name = _select_symbol(self._mt5, symbol)
        info = self._mt5.symbol_info(name)
        if info is None:
            return None
        tick = float(info.point)
        return dict(canonical_symbol=symbol.upper().replace('/', ''), provider_symbol=name,
                    digits=int(info.digits), tick_size=float(getattr(info, 'trade_tick_size', tick)),
                    pip_size=tick * (10 if info.digits in (3, 5) else 1), spread=float(info.spread) * tick, provider='mt5')

    def get_latest_price(self, symbol):
        row = self.latest_tick(symbol)
        metadata=self.get_symbol(symbol) or {}
        row.update(digits=metadata.get('digits'), tick_size=metadata.get('tick_size'), pip_size=metadata.get('pip_size'), provider='mt5', timestamp=datetime.fromtimestamp(row['time'], timezone.utc).isoformat(), spread=row['ask']-row['bid'])
        return row

    def get_provider_health(self):
        info = self._mt5.terminal_info()
        account = self._mt5.account_info()
        connected = bool(info and getattr(info, 'connected', False))
        return dict(configured=True, authorized=bool(account), connected=connected, healthy=connected,
                    market_data_available=connected, execution_available=False)

    def get_account_context(self):
        account = self._mt5.account_info()
        if account is None:
            return None
        return dict(provider='mt5', account_id=f'{account.server}/{account.login}', account_number=str(account.login), server=account.server,
                    environment='demo' if account.trade_mode == 0 else 'live', currency=account.currency)

    def get_candles(self, symbol, timeframe, *, start=None, end=None, count=400):
        return self.get_closed_candles(symbol, timeframe, start=start, end=end, count=count)

    @_locked
    def get_closed_candles(self, symbol, timeframe, *, start=None, end=None, count=400):
        if start is None and end is None:
            return self.closed_candles(symbol, timeframe, count)
        sym = _select_symbol(self._mt5, symbol)
        rates = self._mt5.copy_rates_range(sym, self._tf_const(timeframe), start or datetime(1970, 1, 1, tzinfo=timezone.utc), end or datetime.now(timezone.utc))
        if rates is None:
            raise MarketDataUnavailable('mt5_history_unavailable')
        from .normalized_provider import candle_close
        now = datetime.now(timezone.utc)
        info=self._mt5.symbol_info(sym)
        point=float(info.point) if info is not None else None
        result = []
        for rate in rates:
            opened = datetime.fromtimestamp(int(rate['time']), timezone.utc)
            closed = candle_close(opened, timeframe)
            if closed <= now:
                result.append(Candle(symbol, timeframe, opened, closed, float(rate['open']), float(rate['high']), float(rate['low']), float(rate['close']), int(rate['tick_volume']), spread=float(rate['spread'])*point if point is not None and 'spread' in rate.dtype.names else None, source='mt5'))
        return result[-count:]
    def __init__(self):
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError as e:
            raise MarketDataUnavailable("MetaTrader5 Python package is not installed") from e
        self._mt5 = mt5
        self._resolved: dict[str, str] = {}
        from .mt5_session import is_initialized, initialize

        if not is_initialized() and not initialize():
            err = mt5.last_error()
            raise MarketDataUnavailable(f"MT5 initialize failed: {err}")

    def connection_state(self) -> dict:
        ti = self._mt5.terminal_info()
        return {
            "connected": bool(ti),
            "adapter": "MT5",
            "message": getattr(ti, "name", "MetaTrader 5") if ti else "Terminal not connected",
        }

    def _tf_const(self, timeframe: str):
        tf = timeframe.upper()
        if tf == "H8":
            raise MarketDataUnavailable("Use H1 ingestion and H8 aggregation for H8 timeframe")
        name = _TF_MAP.get(tf)
        if not name:
            raise MarketDataUnavailable(f"Unsupported timeframe for MT5: {timeframe}")
        const = getattr(self._mt5, f"TIMEFRAME_{name}", None)
        if const is None:
            raise MarketDataUnavailable(f"MT5 timeframe constant missing: {name}")
        return const

    @_locked
    def closed_candles(self, symbol: str, timeframe: str, count: int) -> list[Candle]:
        mt5 = self._mt5
        sym = symbol if len(symbol) > 6 else _select_symbol(mt5, symbol)
        if not mt5.symbol_select(sym, True):
            raise MarketDataUnavailable(f"Symbol not available in MT5: {sym}")
        tf = self._tf_const(timeframe)
        # Bar 0 is the forming candle — fetch from shift 1 onward.
        rates = mt5.copy_rates_from_pos(sym, tf, 1, count)
        # Brokers with short monthly/weekly history reject oversized requests outright.
        for smaller in (120, 36, 12):
            if rates is not None and len(rates) > 0:
                break
            if smaller < count:
                rates = mt5.copy_rates_from_pos(sym, tf, 1, smaller)
        if rates is None or len(rates) == 0:
            raise MarketDataUnavailable(f"No rates for {sym} {timeframe}")
        info = mt5.symbol_info(sym)
        point = float(info.point) if info is not None else None
        out: list[Candle] = []
        for r in rates:
            open_time = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            # MT5 time is open time; approximate close as next bar open for storage consistency.
            from .normalized_provider import candle_close
            close_time = candle_close(open_time, timeframe)
            out.append(
                Candle(
                    symbol=sym,
                    timeframe=timeframe.upper(),
                    open_time=open_time,
                    close_time=close_time,
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    tick_volume=int(r["tick_volume"]),
                    spread=float(r["spread"]) * point if point is not None and "spread" in r.dtype.names else None,
                    source="MT5",
                    is_closed=True,
                )
            )
        return out

    @_locked
    def latest_closed_open_time(self, symbol: str, timeframe: str) -> int | None:
        """Open time (epoch s) of the most recent closed bar — cheap change probe."""
        mt5 = self._mt5
        sym = symbol if len(symbol) > 6 else _select_symbol(mt5, symbol)
        rates = mt5.copy_rates_from_pos(sym, self._tf_const(timeframe), 1, 1)
        if rates is None or len(rates) == 0:
            return None
        return int(rates[0]["time"])

    @_locked
    def current_closes(self, symbol: str, timeframe: str, count: int) -> list[tuple[datetime, float]]:
        """(open_time, close) oldest → newest starting at bar 0, i.e. iClose(symbol, tf, 0..count-1)."""
        mt5 = self._mt5
        sym = self._resolved.get(symbol)
        if sym is None:
            sym = symbol if len(symbol) > 6 else _select_symbol(mt5, symbol)
            self._resolved[symbol] = sym
        name = _LIVE_TF_MAP.get(timeframe.upper())
        const = getattr(mt5, f"TIMEFRAME_{name}", None) if name else None
        if const is None:
            raise MarketDataUnavailable(f"Unsupported timeframe for MT5: {timeframe}")
        rates = mt5.copy_rates_from_pos(sym, const, 0, count)
        for smaller in (100, 36, 12):
            if rates is not None and len(rates) > 0:
                break
            if smaller < count:
                rates = mt5.copy_rates_from_pos(sym, const, 0, smaller)
        if rates is None or len(rates) == 0:
            raise MarketDataUnavailable(f"No rates for {sym} {timeframe}")
        return [(datetime.fromtimestamp(int(r["time"]), tz=timezone.utc), float(r["close"])) for r in rates]

    @_locked
    def latest_tick(self, symbol: str) -> dict:
        sym = symbol if len(symbol) > 6 else _select_symbol(self._mt5, symbol)
        tick = self._mt5.symbol_info_tick(sym)
        if tick is None:
            raise MarketDataUnavailable(f"No tick for {sym}")
        return {"symbol": sym, "bid": tick.bid, "ask": tick.ask, "time": tick.time}

    @_locked
    def symbol_snapshot(self, symbol: str) -> dict:
        """Current quote, spread and forming D1 bar for one symbol (bar 0 — display only, never stored)."""
        mt5 = self._mt5
        sym = self._resolved.get(symbol)
        if sym is None:
            sym = symbol if len(symbol) > 6 else _select_symbol(mt5, symbol)
            self._resolved[symbol] = sym
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None or not tick.bid:
            raise MarketDataUnavailable(f"No quote for {sym}")
        day = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 1)
        out = {
            "symbol": symbol.upper(),
            "broker_symbol": sym,
            "description": getattr(info, "description", "") or "",
            "bid": float(tick.bid),
            "ask": float(tick.ask),
            "spread_points": int(getattr(info, "spread", 0) or 0),
            "point": float(getattr(info, "point", 0.0) or 0.0),
            "digits": int(getattr(info, "digits", 5) or 5),
            "tick_time": datetime.fromtimestamp(int(tick.time), tz=timezone.utc),
            "day_high": None,
            "day_low": None,
        }
        if day is not None and len(day):
            out["day_high"] = float(day[0]["high"])
            out["day_low"] = float(day[0]["low"])
        return out


def create_market_data_gateway():
    mode = os.getenv("MT5_MODE", "local").lower()
    if mode in ("off", "disabled", "null"):
        return NullMarketDataGateway()
    try:
        return Mt5MarketDataGateway()
    except (MarketDataUnavailable, OSError, RuntimeError):
        return NullMarketDataGateway()


def mt5_is_connected() -> bool:
    from .mt5_session import connection_state

    return bool(connection_state().get("connected"))
