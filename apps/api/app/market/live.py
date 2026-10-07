"""Live quote and forming (unclosed) bars for charts — display only, never stored or used by any analysis engine.

A forming bar is rebuilt on every request from the finest stored closed bars since the bar opened, then extended
with the latest provider tick, so it matches the bar the terminal is drawing without persisting anything.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from . import channel_intelligence as chan
from .provenance import values
from .repository import MarketRepository
from .scanner_config import CHART_TIMEFRAMES, SCANNER_UNIVERSE

AGGREGATE_MONTHS = {"Y": 12, "HY": 6, "Q": 3}
FIXED = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "H8": 28800, "D1": 86400, "W1": 604800}
# Finer stored timeframes that tile each bar exactly (MN ↔ W1 and H8 ↔ H4 boundaries do not align).
LADDER = {
    "MN": ("D1", "H1", "M30", "M15", "M5", "M1"),
    "W1": ("D1", "H1", "M30", "M15", "M5", "M1"),
    "D1": ("H1", "M30", "M15", "M5", "M1"),
    "H8": ("H1", "M30", "M15", "M5", "M1"),
    "H4": ("H1", "M30", "M15", "M5", "M1"),
    "H1": ("M30", "M15", "M5", "M1"),
    "M30": ("M15", "M5", "M1"),
    "M15": ("M5", "M1"),
    "M5": ("M1",),
    "M1": (),
}
FETCH = {"MN": 14, "W1": 3, "D1": 40, "H8": 3, "H4": 3, "H1": 60, "M30": 8, "M15": 8, "M5": 16, "M1": 20}
MAX_TIMEFRAMES = 12
QUOTE_STALE_SECONDS = 120
CACHE_SECONDS = 0.5

_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def base_timeframe(name: str) -> str:
    if name in AGGREGATE_MONTHS:
        return "MN"
    if name == "YTD":
        return "D1"
    tf = CHART_TIMEFRAMES.get(name)
    if tf is None:
        raise ValueError(f"Unsupported chart timeframe: {name}")
    return tf


def _utc(v) -> datetime:
    t = v if isinstance(v, datetime) else datetime.fromisoformat(str(v))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


class _Rows:
    """Recent closed rows per stored timeframe, fetched at most once per request."""

    def __init__(self, repo: MarketRepository, symbol: str):
        self.repo, self.symbol, self._rows = repo, symbol, {}

    def __call__(self, tf: str) -> list[tuple]:
        if tf not in self._rows:
            out = []
            for r in self.repo.candles(self.symbol, tf, FETCH.get(tf, 20)):
                ot, ct, o, h, l, c, v = values(r)[:7]
                out.append((_utc(ot), _utc(ct), float(o), float(h), float(l), float(c), int(v or 0)))
            self._rows[tf] = out
        return self._rows[tf]


def _period_start(tf: str, last_close: datetime, now: datetime) -> datetime:
    """Open of the bar containing ``now``: whole bar lengths after the last stored close keep the broker alignment."""
    step = FIXED.get(tf)
    if not step or now < last_close:
        return last_close
    return last_close + timedelta(seconds=step * int((now - last_close).total_seconds() // step))


def forming_bar(rows: _Rows, tf: str, price: float | None, tick_at: datetime | None, now: datetime) -> dict | None:
    """The unclosed ``tf`` bar from finer closed bars plus the latest tick, or None when nothing traded since it opened."""
    own = rows(tf)
    if not own:
        return None
    start = _period_start(tf, own[-1][1], now)
    end = start + timedelta(seconds=FIXED[tf]) if tf in FIXED else None
    o = h = l = c = None
    v = 0
    cursor = start
    for child in LADDER.get(tf, ()):
        for ot, ct, bo, bh, bl, bc, bv in rows(child):
            if ot < cursor or (end and ot >= end):
                continue
            o = bo if o is None else o
            h = bh if h is None else max(h, bh)
            l = bl if l is None else min(l, bl)
            c, v, cursor = bc, v + bv, ct
    if price is not None and tick_at is not None and tick_at >= start and (end is None or tick_at < end):
        o = price if o is None else o
        h = price if h is None else max(h, price)
        l = price if l is None else min(l, price)
        c = price
    if o is None:
        return None
    return {"t": start, "o": o, "h": h, "l": l, "c": c, "v": v}


def chart_forming(rows: _Rows, name: str, price: float | None, tick_at: datetime | None, now: datetime) -> dict | None:
    """Forming bar in the chart's own timeframe (Y/HY/Q merge the forming month into the calendar aggregate)."""
    base = base_timeframe(name)
    bar = forming_bar(rows, base, price, tick_at, now)
    if bar is None:
        return None
    if name in AGGREGATE_MONTHS:
        months = [chan.Bar(ot, o, h, l, c, v) for ot, _, o, h, l, c, v in rows("MN")]
        merged = chan.aggregate([*months, chan.Bar(bar["t"], bar["o"], bar["h"], bar["l"], bar["c"], bar["v"])], AGGREGATE_MONTHS[name])
        b = merged[-1]
        bar = {"t": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v}
    elif name == "YTD":
        own = rows("D1")
        if own and own[-1][0].year != bar["t"].year:
            return None
    return {**bar, "t": bar["t"].isoformat()}


def _quote(conn) -> tuple[object, dict | None, str | None]:
    from .market_data import create_market_data_gateway, market_context

    ctx = market_context(conn)
    if not ctx.get("market_data_ready"):
        return ctx, None, ctx.get("error_code") or "market_data_unavailable"
    try:
        gateway = create_market_data_gateway(conn, context=ctx, verify_scope=False)
    except Exception as exc:  # noqa: BLE001 - display path: report, never raise
        return ctx, None, str(exc) or type(exc).__name__
    # A per-second display read must never write provider health: one stale quote would degrade every engine for 60 s.
    gateway.observer = None
    return ctx, gateway, None


def live_snapshot(symbol: str, timeframes: list[str], now: datetime | None = None) -> dict:
    sym = symbol.upper()
    if sym not in SCANNER_UNIVERSE:
        raise ValueError(f"Unknown instrument: {symbol}")
    names = list(dict.fromkeys(t.strip().upper() for t in timeframes if t.strip()))[:MAX_TIMEFRAMES]
    for name in names:
        base_timeframe(name)
    key = (sym, tuple(names))
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS and now is None:
            return hit[1]
    from ..core.database import db

    now = now or datetime.now(timezone.utc)
    quote = None
    with db() as conn:
        ctx, gw, error = _quote(conn)
        if gw is not None:
            try:
                q = gw.get_latest_price(sym)
                tick_at = _utc(q.get("timestamp")) if q.get("timestamp") else datetime.fromtimestamp(int(q["time"]), timezone.utc)
                bid, ask = float(q["bid"]), float(q["ask"])
                age = max(0.0, (now - tick_at).total_seconds())
                quote = {"bid": bid, "ask": ask, "price": bid, "spread": ask - bid, "time": tick_at.isoformat(),
                         "age_seconds": round(age, 1), "stale": age > QUOTE_STALE_SECONDS}
            except Exception as exc:  # noqa: BLE001
                error = str(exc) or type(exc).__name__
        rows = _Rows(MarketRepository(conn), sym)
        price = quote["price"] if quote and not quote["stale"] else None
        tick = _utc(quote["time"]) if price is not None else None
        forming = {name: chart_forming(rows, name, price, tick, now) for name in names}
    out = {"symbol": sym, "provider": ctx.get("active_provider"), "server_time": now.isoformat(), "quote": quote,
           "forming": forming, "error": None if quote else error, "display_only": True}
    with _cache_lock:
        _cache[key] = (time.monotonic(), out)
        if len(_cache) > 256:
            _cache.clear()
    return out
