"""Authoritative OHLC from persisted store + live quote/forming bar (no synthetic history)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from ..core.database import db
from ..market.live import live_snapshot
from ..market.scanner_config import CHART_TIMEFRAMES, SCANNER_UNIVERSE
from ..market.scanner_engine import chart_candles


def _unix(t: str) -> int:
    dt = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _norm_tf(timeframe: str) -> str:
    tf = timeframe.strip().upper()
    if tf == "W":
        return "W"
    return tf


def list_symbols() -> list[str]:
    return list(SCANNER_UNIVERSE)


def _store_timeframe(chart_tf: str) -> str | None:
    name = chart_tf.strip().upper()
    if name in ("Y", "HY", "Q"):
        return "MN"
    if name == "YTD":
        return "D1"
    return CHART_TIMEFRAMES.get(name)


def _hydrate_candles_from_provider(symbol: str, chart_tf: str, limit: int) -> bool:
    """Pull closed bars from the active market-data adapter when the store is empty (e.g. scanner worker off)."""
    store_tf = _store_timeframe(chart_tf)
    if not store_tf:
        return False
    from ..market.ingestion_runner import MarketIngestionRunner
    from ..market.market_data import create_market_data_gateway, market_context
    from ..market.repository import MarketRepository

    sym = symbol.upper()
    with db() as conn:
        ctx = market_context(conn)
        if not ctx.get("market_data_ready"):
            return False
        gw = create_market_data_gateway(conn, context=ctx, verify_scope=False)
        if gw is None:
            return False
        repo = MarketRepository(
            conn,
            provider=ctx.get("active_provider") or "__unavailable__",
            snapshot_id=getattr(gw, "snapshot_id", None),
        )
        try:
            have = len(repo.candles(sym, store_tf, 3))
        except Exception:
            have = 0
        count = min(400, max(limit, 80)) if have < 3 else min(32, max(limit, 12))
        result = MarketIngestionRunner(gw, repo, candle_count=count).sync_pair_timeframe(sym, store_tf)
        conn.commit()
        if result.get("error"):
            return False
        return int(result.get("accepted") or 0) > 0


def fetch_candles(symbol: str, timeframe: str, limit: int) -> tuple[list[dict], dict]:
    sym = symbol.upper()
    if sym not in SCANNER_UNIVERSE:
        raise HTTPException(403, "Symbol not authorized for this tenant scope")
    tf = _norm_tf(timeframe)
    try:
        payload = chart_candles(sym, tf, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    raw = payload.get("candles") or []
    if not raw and _hydrate_candles_from_provider(sym, tf, limit):
        try:
            payload = chart_candles(sym, tf, limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        raw = payload.get("candles") or []
    if not raw:
        return [], {
            "stale": True,
            "message": "No closed candles in store for this symbol/timeframe — ensure MT5 is connected and the symbol is visible in Market Watch",
            "closed_only": True,
        }
    rows: list[dict] = []
    for c in raw:
        rows.append(
            {
                "time": _unix(c["t"]),
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": int(c.get("v") or 0),
                "closed": True,
            }
        )
    meta = {"stale": False, "closed_only": bool(payload.get("closed_only")), "count": len(rows)}
    try:
        live = live_snapshot(sym, [tf])
        forming = (live.get("forming") or {}).get(tf) or (live.get("forming") or {}).get(tf.upper())
        if forming and forming.get("t"):
            ft = _unix(forming["t"]) if isinstance(forming["t"], str) else int(forming["t"])
            bar = {
                "time": ft,
                "open": float(forming["o"]),
                "high": float(forming["h"]),
                "low": float(forming["l"]),
                "close": float(forming["c"]),
                "volume": int(forming.get("v") or 0),
                "closed": False,
            }
            if rows and rows[-1]["time"] == ft:
                rows[-1] = bar
            elif not rows or rows[-1]["time"] < ft:
                rows.append(bar)
            meta["forming"] = True
    except ValueError:
        meta["forming"] = False
    except Exception:
        meta["forming"] = False
    rows.sort(key=lambda r: r["time"])
    return rows, meta


def fetch_quote(symbol: str) -> dict:
    sym = symbol.upper()
    if sym not in SCANNER_UNIVERSE:
        raise HTTPException(403, "Symbol not authorized for this tenant scope")
    try:
        snap = live_snapshot(sym, ["M1"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    q = snap.get("quote")
    if not q:
        with db() as conn:
            from ..market.market_data import market_context

            ctx = market_context(conn)
            if not ctx.get("market_data_ready"):
                raise HTTPException(503, ctx.get("error_code") or "Market-data adapter not connected")
        raise HTTPException(503, snap.get("error") or "Quote adapter not connected")
    return {
        "symbol": sym,
        "bid": q.get("bid"),
        "ask": q.get("ask"),
        "updated_at": q.get("time"),
        "stale": bool(q.get("stale")),
    }


def _change_pct_h1(sym: str) -> float | None:
    try:
        rows, _ = fetch_candles(sym, "H1", 3)
        if len(rows) < 2:
            return None
        prev, last = rows[-2], rows[-1]
        if not prev["close"]:
            return None
        return ((last["close"] - prev["close"]) / prev["close"]) * 100.0
    except HTTPException:
        return None


def fetch_quote_enriched(symbol: str) -> dict:
    sym = symbol.upper()
    base = {
        "symbol": sym,
        "bid": None,
        "ask": None,
        "updated_at": None,
        "stale": True,
        "change_pct": _change_pct_h1(sym),
    }
    try:
        q = fetch_quote(sym)
        base.update(q)
        base["change_pct"] = _change_pct_h1(sym)
    except HTTPException:
        pass
    return base


def fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for raw in symbols:
        sym = raw.strip().upper()
        if not sym or sym in out:
            continue
        if sym not in SCANNER_UNIVERSE:
            continue
        out[sym] = fetch_quote_enriched(sym)
        if len(out) >= 40:
            break
    return out
