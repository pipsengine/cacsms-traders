from fastapi import APIRouter, Depends, Query

from ..deps import get_db
from ..market.constants import CSM_CURRENCIES
from ..market.csm_engine import CalculationMode
from ..market.csm_service import CurrencyStrengthMatrixService
from ..market.ingestion_runner import MarketIngestionRunner
from ..market.intelligence_cycle import run_intelligence_cycle
from ..market.mt5_gateway import create_market_data_gateway, mt5_is_connected
from ..market.repository import MarketRepository

router = APIRouter(prefix="/api/market-intelligence", tags=["Market Intelligence"])


def _csm(db) -> CurrencyStrengthMatrixService:
    return CurrencyStrengthMatrixService(MarketRepository(db))


@router.get("/health")
def health():
    return {"status": "ready", "layer": "strength-relationship", "tradingSignals": False}


@router.get("/matrix")
def matrix(
    sort_by: str = Query("AVG"),
    calculation_mode: str = Query("CLOSE_CLOSE"),
    db=Depends(get_db),
):
    svc = _csm(db)
    payload = svc.latest_from_db(sort_by=sort_by.upper())
    if payload:
        payload["meta"]["calculation_mode"] = calculation_mode
        payload["meta"]["sort_by"] = sort_by.upper()
        payload["meta"]["mt5_connected"] = mt5_is_connected()
        return payload
    return {
        "meta": {
            "as_of": None,
            "last_calculated_at": None,
            "calculation_mode": calculation_mode,
            "bars_difference": 1,
            "sort_by": sort_by.upper(),
            "closed_bar_only": True,
            "data_source": "MT5",
            "mt5_connected": False,
            "historical_ok": False,
            "missing_history": [],
            "stale": False,
            "currency_order": list(CSM_CURRENCIES),
        },
        "matrix": [],
        "avg_ranking": [],
        "rows": [],
    }


@router.post("/matrix/compute")
def matrix_compute(
    sort_by: str = Query("AVG"),
    calculation_mode: str = Query("CLOSE_CLOSE"),
    bars_difference: int = Query(1, ge=1, le=10),
    db=Depends(get_db),
):
    svc = _csm(db)
    mode = CalculationMode(calculation_mode.upper())
    result = svc.calculate(calculation_mode=mode, bars_difference=bars_difference)
    svc.persist(result)
    return svc.to_api_payload(
        result,
        calculation_mode=mode,
        sort_by=sort_by.upper(),
        bars_difference=bars_difference,
        mt5_connected=mt5_is_connected(),
    )


@router.get("/status")
def mi_status():
    gw = create_market_data_gateway()
    return {"market_data": gw.connection_state(), "worker_hint": "Set MI_WORKER_ENABLED=1 to run scheduled cycles"}


@router.post("/ingest")
def ingest_market_data(
    candle_count: int = Query(400, ge=50, le=2000),
    db=Depends(get_db),
):
    gw = create_market_data_gateway()
    repo = MarketRepository(db)
    summary = MarketIngestionRunner(gw, repo, candle_count=candle_count).sync_universe()
    return {"market_data": gw.connection_state(), "ingest": summary}


@router.post("/cycle")
def run_cycle(
    ingest: bool = Query(True),
    candle_count: int = Query(400, ge=50, le=2000),
):
    return run_intelligence_cycle(ingest=ingest, candle_count=candle_count)


@router.get("/strength/{currency}/history")
def strength_history(
    currency: str,
    timeframe: str = Query("H1"),
    limit: int = Query(96, ge=2, le=2000),
    db=Depends(get_db),
):
    return [
        dict(r)
        for r in db.execute(
            "SELECT * FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",
            (currency.upper(), timeframe.upper(), limit),
        ).fetchall()
    ][::-1]


@router.get("/relationships")
def relationships(timeframe: str | None = None, state: str | None = None, db=Depends(get_db)):
    sql = """SELECT r.* FROM mi_relationship_snapshot r
             JOIN (SELECT pair,timeframe,MAX(as_of) a FROM mi_relationship_snapshot GROUP BY pair,timeframe) x
             ON x.pair=r.pair AND x.timeframe=r.timeframe AND x.a=r.as_of WHERE 1=1"""
    args = []
    if timeframe:
        sql += " AND r.timeframe=?"
        args.append(timeframe.upper())
    if state:
        sql += " AND r.state=?"
        args.append(state.upper())
    sql += " ORDER BY CASE r.inspection_priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 ELSE 4 END,r.abs_gap DESC"
    return [dict(r) for r in db.execute(sql, args).fetchall()]


@router.get("/relationships/{pair}/history")
def relationship_history(
    pair: str,
    timeframe: str = Query("H1"),
    limit: int = Query(96, ge=2, le=2000),
    db=Depends(get_db),
):
    return [
        dict(r)
        for r in db.execute(
            "SELECT * FROM mi_relationship_snapshot WHERE pair=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",
            (pair.upper(), timeframe.upper(), limit),
        ).fetchall()
    ][::-1]


@router.get("/data-quality")
def quality(db=Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM mi_data_quality ORDER BY symbol,timeframe").fetchall()]
