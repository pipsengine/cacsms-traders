from fastapi import APIRouter, HTTPException, Query

from ..core.database import db
from ..market.constants import CSM_CURRENCIES
from ..market.csm_engine import CalculationMode
from ..market.csm_service import CurrencyStrengthMatrixService
from ..market.ingestion_runner import MarketIngestionRunner
from ..market.intelligence_cycle import run_intelligence_cycle
from ..market.mt5_gateway import create_market_data_gateway
from ..market.mt5_platform_status import get_mt5_market_context
from ..market.repository import MarketRepository
from ..market.strength_engine import get_strength_engine

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence"])


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
    engine = get_strength_engine()
    payload = engine.payload(sort_by, mode)
    if payload is None or not engine.running:
        engine.seed_from_db()
        payload = engine.payload(sort_by, mode)
    if payload is None:
        raise HTTPException(503, "Strength engine has not produced a calculation yet")
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
        ctx = get_mt5_market_context(conn)
        svc = CurrencyStrengthMatrixService(MarketRepository(conn))
        result = svc.calculate(calculation_mode=mode, bars_difference=bars_difference)
        svc.persist(result)
        return svc.to_api_payload(
            result,
            calculation_mode=mode,
            sort_by=sort_by.upper(),
            bars_difference=bars_difference,
            mt5_connected=bool(ctx["mt5_connected"]),
            mt5_server=str(ctx["mt5_server"]),
            histories=svc.score_histories(),
        )


@router.get("/status")
def mi_status():
    gw = create_market_data_gateway()
    return {"market_data": gw.connection_state(), "worker_hint": "Set MI_WORKER_ENABLED=1 to run scheduled cycles"}


@router.post("/ingest")
def ingest_market_data(candle_count: int = Query(400, ge=50, le=2000)):
    gw = create_market_data_gateway()
    with db() as conn:
        ctx = get_mt5_market_context(conn)
        summary = MarketIngestionRunner(gw, MarketRepository(conn), candle_count=candle_count).sync_universe()
    return {"market_data": gw.connection_state(), "mt5": ctx, "ingest": summary}


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
