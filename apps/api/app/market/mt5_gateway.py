"""MetaTrader 5 market data adapter (closed bars only)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from .models import Candle
from .mt5_contract import MarketDataUnavailable

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
        out: list[Candle] = []
        for r in rates:
            open_time = datetime.fromtimestamp(int(r["time"]), tz=timezone.utc)
            # MT5 time is open time; approximate close as next bar open for storage consistency.
            close_time = open_time
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
                    spread=int(r["spread"]) if "spread" in r.dtype.names else 0,
                    source="MT5",
                    is_closed=True,
                )
            )
        return out

    def latest_closed_open_time(self, symbol: str, timeframe: str) -> int | None:
        """Open time (epoch s) of the most recent closed bar — cheap change probe."""
        mt5 = self._mt5
        sym = symbol if len(symbol) > 6 else _select_symbol(mt5, symbol)
        rates = mt5.copy_rates_from_pos(sym, self._tf_const(timeframe), 1, 1)
        if rates is None or len(rates) == 0:
            return None
        return int(rates[0]["time"])

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

    def latest_tick(self, symbol: str) -> dict:
        sym = symbol if len(symbol) > 6 else _broker_symbol(symbol)
        tick = self._mt5.symbol_info_tick(sym)
        if tick is None:
            raise MarketDataUnavailable(f"No tick for {sym}")
        return {"symbol": sym, "bid": tick.bid, "ask": tick.ask, "time": tick.time}


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
