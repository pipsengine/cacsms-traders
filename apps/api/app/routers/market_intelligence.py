import os
import time

from fastapi import APIRouter, HTTPException, Query

from ..core.database import db
from ..market.constants import CSM_CURRENCIES
from ..market.csm_engine import CalculationMode
from ..market.csm_service import CurrencyStrengthMatrixService, collect_forming_bids, collect_live_endpoints
from ..market.ingestion_runner import MarketIngestionRunner
from ..market.live import live_snapshot
from ..market.intelligence_cycle import run_intelligence_cycle
from ..market.market_data import create_market_data_gateway, market_context
from ..market.repository import MarketRepository
from ..market.scanner_engine import MarketScannerEngine, chart_candles, get_scanner_engine, scanner_enabled
from ..market.strength_engine import StrengthEngine, get_strength_engine
from ..market.strength_intel_service import analysis_payload, historical_payload, pairs_payload
from ..market.strength_intel_store import active_scope, latest_pair_snapshot

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence"])


def _on_demand(engine: StrengthEngine) -> bool:
    return not engine.running and os.getenv("STRENGTH_ENGINE_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def _refresh(engine: StrengthEngine) -> None:
    """Serverless deployments have no background worker, so reads advance the engine (throttled).

    The tick re-reads provider context itself, so the diagnostics seed is only needed without it."""
    if _on_demand(engine):
        engine.tick_on_demand()
    else:
        engine.seed_from_db()


def _ready_engine() -> StrengthEngine:
    engine = get_strength_engine()
    if not engine.running:
        _refresh(engine)
    return engine


def _or_503(payload: dict | None) -> dict:
    if payload is None:
        raise HTTPException(503, "Strength engine has not produced a calculation yet")
    return payload


def _require_close_close(calculation_mode: str) -> CalculationMode:
    try:
        mode = CalculationMode(calculation_mode.upper())
    except ValueError as exc:
        raise HTTPException(400, f"Unknown calculation mode: {calculation_mode}") from exc
    if mode != CalculationMode.CLOSE_CLOSE:
        raise HTTPException(400, f"Calculation mode {mode.value} is reserved for a future release")
    return mode


@router.get("/health")
def health():
    return {"status": "ready", "layer": "strength-relationship", "tradingSignals": False}


@router.get("/matrix")
def matrix(
    sort_by: str = Query("AVG"),
    calculation_mode: str = Query("CLOSE_CLOSE"),
):
    """Latest strength matrix produced by the background engine (no recalculation per request)."""
    try:
        mode = CalculationMode(calculation_mode.upper())
    except ValueError as exc:
        raise HTTPException(400, f"Unknown calculation mode: {calculation_mode}") from exc
    started = time.monotonic()
    engine = get_strength_engine()
    _refresh(engine)
    refreshed = time.monotonic()
    payload = engine.payload(sort_by, mode)
    if isinstance(payload.get("meta"), dict):
        payload["meta"]["request_profile"] = {"refresh": round(refreshed - started, 3), "payload": round(time.monotonic() - refreshed, 3)}
    return payload


@router.post("/matrix/compute")
def matrix_compute(
    sort_by: str = Query("AVG"),
    calculation_mode: str = Query("CLOSE_CLOSE"),
    bars_difference: int = Query(1, ge=1, le=10),
):
    """Persist a snapshot from stored candles (operational/admin use)."""
    mode = _require_close_close(calculation_mode)
    with db() as conn:
        ctx = market_context(conn)
        if not ctx["market_data_ready"]:
            return {"market_data": ctx, "matrix": [], "analysis_only": True}
        gw = create_market_data_gateway(conn, context=ctx)
        svc = CurrencyStrengthMatrixService(MarketRepository(conn, provider=gw.provider_id, snapshot_id=gw.snapshot_id))
        endpoints = collect_live_endpoints(gw, bars_difference)
        result = svc.calculate(
            calculation_mode=mode,
            bars_difference=bars_difference,
            forming_bids=None if endpoints else collect_forming_bids(gw),
            live_endpoints=endpoints,
        )
        svc.persist(result)
        return svc.to_api_payload(
            result,
            calculation_mode=mode,
            sort_by=sort_by.upper(),
            bars_difference=bars_difference,

            histories=svc.score_histories(),
        )


@router.get("/status")
def mi_status():
    with db() as conn:
        context = market_context(conn)
    engine = get_strength_engine()
    if not engine.running:
        if _on_demand(engine):
            engine.allow_on_demand()
        engine.seed_from_db()
    meta = engine.engine_meta() or {}
    return {"market_data": {**context, **(meta if meta.get('active_provider') == context.get('active_provider') else {})}}


@router.post("/ingest")
def ingest_market_data(candle_count: int = Query(400, ge=50, le=2000)):
    with db() as conn:
        ctx = market_context(conn)
        if not ctx["market_data_ready"]:
            return {"market_data": ctx, "ingest": None, "analysis_only": True}
        gw = create_market_data_gateway(conn)
        summary = MarketIngestionRunner(gw, MarketRepository(conn), candle_count=candle_count).sync_universe()
    return {"market_data": ctx, "ingest": summary}


@router.post("/cycle")
def run_cycle(
    ingest: bool = Query(True),
    candle_count: int = Query(400, ge=50, le=2000),
):
    return run_intelligence_cycle(ingest=ingest, candle_count=candle_count)


@router.get("/strength/sparklines")
def strength_sparklines(
    timeframe: str = Query("AVG"),
    limit: int = Query(32, ge=4, le=200),
):
    with db() as conn:
        repo = MarketRepository(conn)
        return {
            c: [{"as_of": a, "score": s} for a, s in repo.score_history(c, timeframe.upper(), limit)]
            for c in CSM_CURRENCIES
        }


@router.get("/strength/historical")
def strength_historical(period: str = Query("24H"), timeframe: str = Query("AVG")):
    """Historical Strength tab: persisted 0–100 scores, trends, momentum, extremes and events."""
    try:
        return _or_503(historical_payload(_ready_engine(), period, timeframe))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/relationships/pairs")
def pair_relationships_live():
    """Pair Relationships tab: 28-pair strength differentials from the engine's current scores."""
    return _or_503(pairs_payload(_ready_engine()))


@router.get("/relationships/pairs/snapshot")
def pair_relationships_snapshot():
    """Latest persisted pair intelligence for the active tenant/account (downstream consumers)."""
    with db() as conn:
        scope = active_scope(conn)
        rows = latest_pair_snapshot(conn, scope)
    return {
        "scope": {"tenant_id": scope[0] or None, "trading_account_id": scope[1] or None},
        "as_of": rows[0]["as_of"] if rows else None,
        "analysis_only": True,
        "rows": rows,
    }


@router.get("/relationships/pairs/{pair}/analysis")
def pair_relationship_analysis(pair: str, period: str = Query("24H")):
    """Relationship Analysis tab: multi-timeframe structural interpretation for one pair."""
    try:
        return _or_503(analysis_payload(_ready_engine(), pair, period))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _scanner() -> MarketScannerEngine:
    engine = get_scanner_engine()
    if engine.running or not scanner_enabled():
        return engine
    if os.getenv("VERCEL", "").strip() == "1":
        # Threads are frozen between serverless invocations; the scanner also merges strength intelligence.
        strength = get_strength_engine()
        if _on_demand(strength):
            strength.tick_on_demand()
        engine.tick_on_demand()
    else:
        engine.start()
    return engine


@router.get("/scanner")
def market_scanner():
    """Market Scanner: inspection-priority classification for XAUUSD + 28 FX pairs (analysis only)."""
    return _scanner().payload()


@router.get("/scanner/{symbol}")
def market_scanner_instrument(symbol: str):
    detail = _scanner().detail(symbol)
    if detail is None:
        raise HTTPException(404, f"{symbol.upper()} is not in the scanner universe or has not been scanned yet")
    return detail


@router.get("/scanner/{symbol}/candles")
def market_scanner_candles(symbol: str, timeframe: str = Query("D1"), limit: int = Query(120, ge=10, le=500)):
    """Closed candles from the persisted market data store for the scanner detail chart."""
    try:
        return chart_candles(symbol, timeframe, limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/scanner/{symbol}/live")
def market_scanner_live(symbol: str, timeframes: str = Query("D1", max_length=120)):
    """Latest tick and the forming bar per chart timeframe (display only; never stored or analysed)."""
    try:
        return live_snapshot(symbol, timeframes.split(","))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/structure/overview")
def structure_overview():
    """Market Structure → Structure Overview: multi-timeframe regimes, alignment and structural events."""
    return _scanner().structure_overview_payload()


@router.get("/h8-bos-btl")
def h8_bos_btl():
    """H8 BOS & BTL Intelligence: summary counts and the priority-sorted alert strip (closed-bar analysis only)."""
    return _scanner().h8_bos_btl_payload()


@router.get("/h8-bos-btl/latest")
def h8_bos_btl_latest(symbol: str = Query(...)):
    """Latest W / H8 / H1 / M30 analysis snapshot for one instrument (observer of the scanner engine)."""
    detail = _scanner().h8_bos_btl_detail(symbol)
    if detail is None:
        raise HTTPException(404, f"{symbol.upper()} is not in the scanner universe")
    return detail


@router.get("/structure/trend")
def trend_structure():
    """Market Structure → Trend Structure: W/D1/H8/H1 trend matrix, strength, age and setup counts (closed bars)."""
    return _scanner().trend_structure_payload()


@router.get("/structure/trend/{symbol}")
def trend_structure_instrument(symbol: str):
    detail = _scanner().trend_structure_detail(symbol)
    if detail is None:
        raise HTTPException(404, f"{symbol.upper()} is not in the scanner universe")
    return detail


def _found(detail: dict | None, symbol: str) -> dict:
    if detail is None:
        raise HTTPException(404, f"{symbol.upper()} is not in the scanner universe")
    return detail


@router.get("/structure/fractals")
def fractal_structure():
    """Market Structure → Fractals: per-timeframe fractal lifecycle, weekly clusters and counts (closed bars)."""
    return _scanner().fractal_payload()


@router.get("/structure/fractals/{symbol}")
def fractal_structure_instrument(symbol: str, timeframe: str = Query("W")):
    return _found(_scanner().fractal_detail(symbol, timeframe), symbol)


@router.get("/structure/bos")
def bos_choch():
    """Market Structure → BOS / CHoCH: confirmed and developing structure breaks with retest status."""
    return _scanner().bos_payload()


@router.get("/structure/bos/{symbol}")
def bos_choch_instrument(symbol: str, timeframe: str = Query("H1")):
    return _found(_scanner().bos_detail(symbol, timeframe), symbol)


@router.get("/channels")
def channel_intelligence():
    """Channel Intelligence: channel states, breakout & retest events and trend-in-trend candidates (all symbols)."""
    return _scanner().channel_payload()


@router.get("/channels/{symbol}")
def channel_intelligence_instrument(symbol: str, timeframe: str = Query("W"), breakout_timeframe: str = Query("H1")):
    return _found(_scanner().channel_detail(symbol, timeframe, breakout_timeframe), symbol)


@router.get("/structure/range")
def range_structure():
    """Market Structure → Range Structure: weekly range intelligence for every scanner instrument."""
    return _scanner().range_payload()


@router.get("/structure/range/{symbol}")
def range_structure_instrument(symbol: str):
    detail = _scanner().range_detail(symbol)
    if detail is None:
        raise HTTPException(404, f"{symbol.upper()} is not in the scanner universe")
    return detail


@router.get("/strength/{currency}/history")
def strength_history(
    currency: str,
    timeframe: str = Query("H1"),
    limit: int = Query(96, ge=2, le=2000),
):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",
            (currency.upper(), timeframe.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows][::-1]


@router.get("/relationships")
def relationships(timeframe: str | None = None, state: str | None = None):
    sql = """SELECT r.* FROM mi_relationship_snapshot r
             JOIN (SELECT pair,timeframe,MAX(as_of) a FROM mi_relationship_snapshot GROUP BY pair,timeframe) x
             ON x.pair=r.pair AND x.timeframe=r.timeframe AND x.a=r.as_of WHERE 1=1"""
    args = []
    if timeframe and timeframe.upper() != "ALL":
        sql += " AND r.timeframe=?"
        args.append(timeframe.upper())
    if state:
        sql += " AND r.state=?"
        args.append(state.upper())
    sql += " ORDER BY CASE r.inspection_priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 ELSE 4 END,r.abs_gap DESC"
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]


@router.get("/relationships/{pair}/history")
def relationship_history(
    pair: str,
    timeframe: str = Query("H1"),
    limit: int = Query(96, ge=2, le=2000),
):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM mi_relationship_snapshot WHERE pair=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",
            (pair.upper(), timeframe.upper(), limit),
        ).fetchall()
        return [dict(r) for r in rows][::-1]


@router.get("/data-quality")
def quality():
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM mi_data_quality ORDER BY symbol,timeframe").fetchall()]
