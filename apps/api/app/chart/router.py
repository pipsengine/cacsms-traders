"""Advanced Chart Analysis routes under /api/chart."""
from __future__ import annotations

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from ..core.database import db
from ..core.security import iso
from ..deps import current_user
from ..market.strength_intel_store import active_scope
from ..services.access import require_permission
from . import intelligence, market, opportunities
from .schemas import CHART_TFS, AnalysisIn, OpportunityIn, Workspace

router = APIRouter(prefix="/api/chart", tags=["Advanced Chart Analysis"])
SYMBOL = re.compile(r"^[A-Z0-9._-]{3,16}$")


def _check(symbol: str, timeframe: str) -> None:
    if not SYMBOL.fullmatch(symbol.upper()):
        raise HTTPException(422, "Invalid symbol")
    if timeframe.upper() not in CHART_TFS:
        raise HTTPException(422, "Invalid timeframe")


def _chart_scope(conn, user) -> tuple[str, str, str]:
    tenant_id, account_id = active_scope(conn)
    if not tenant_id:
        row = conn.execute(
            "SELECT tenant_id FROM tenant_memberships WHERE user_id=? AND status='ACTIVE' ORDER BY created_at LIMIT 1",
            (user["id"],),
        ).fetchone()
        if not row:
            raise HTTPException(503, "No tenant scope available for chart workspace")
        tenant_id = row[0] if isinstance(row, tuple) else row["tenant_id"]
        account_id = account_id or ""
    require_permission(conn, user, tenant_id, "system.read")
    return tenant_id, user["id"], account_id


@router.get("/symbols")
def chart_symbols(user=Depends(current_user)):
    with db() as conn:
        _chart_scope(conn, user)
    return market.list_symbols()


@router.get("/candles")
def chart_candles_route(
    symbol: str,
    timeframe: str,
    limit: int = Query(700, ge=30, le=3000),
    user=Depends(current_user),
):
    _check(symbol, timeframe)
    with db() as conn:
        _chart_scope(conn, user)
    rows, meta = market.fetch_candles(symbol, timeframe, limit)
    if not rows:
        raise HTTPException(503, meta.get("message") or "Market-data adapter returned no candles")
    return rows


@router.get("/quote")
def chart_quote(symbol: str, user=Depends(current_user)):
    if not SYMBOL.fullmatch(symbol.upper()):
        raise HTTPException(422, "Invalid symbol")
    with db() as conn:
        _chart_scope(conn, user)
    return market.fetch_quote_enriched(symbol)


@router.get("/quotes")
def chart_quotes(symbols: str = Query(..., min_length=3, max_length=600), user=Depends(current_user)):
    parts = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not parts:
        raise HTTPException(422, "No symbols requested")
    for sym in parts[:40]:
        if not SYMBOL.fullmatch(sym):
            raise HTTPException(422, f"Invalid symbol: {sym}")
    with db() as conn:
        _chart_scope(conn, user)
    return market.fetch_quotes(parts)


@router.get("/overlays")
def chart_overlays(symbol: str, timeframe: str, user=Depends(current_user)):
    _check(symbol, timeframe)
    with db() as conn:
        _chart_scope(conn, user)
        return intelligence.overlays_for(conn, symbol, timeframe)


@router.get("/workspace")
def get_workspace(symbol: str, timeframe: str, user=Depends(current_user)):
    _check(symbol, timeframe)
    with db() as conn:
        tenant_id, user_id, _ = _chart_scope(conn, user)
        r = conn.execute(
            "SELECT indicators, layers, drawings, updated_at FROM chart_workspaces WHERE tenant_id=? AND user_id=? AND symbol=? AND timeframe=?",
            (tenant_id, user_id, symbol.upper(), timeframe.upper()),
        ).fetchone()
    if not r:
        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "indicators": ["EMA", "Volume"],
            "layers": ["My Drawings", "AI Market Outlook", "Market Structure", "Channel Intelligence", "Key Levels"],
            "drawings": [],
            "updated_at": None,
        }
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe.upper(),
        "indicators": json.loads(r[0]),
        "layers": json.loads(r[1]),
        "drawings": json.loads(r[2]),
        "updated_at": r[3],
    }


@router.post("/workspace")
def save_workspace(payload: Workspace, user=Depends(current_user)):
    _check(payload.symbol, payload.timeframe)
    if any(d.symbol.upper() != payload.symbol.upper() or d.timeframe.upper() != payload.timeframe.upper() for d in payload.drawings):
        raise HTTPException(422, "Drawing symbol/timeframe mismatch")
    stamp = iso()
    with db() as conn:
        tenant_id, user_id, _ = _chart_scope(conn, user)
        cur = conn.execute(
            "SELECT updated_at FROM chart_workspaces WHERE tenant_id=? AND user_id=? AND symbol=? AND timeframe=?",
            (tenant_id, user_id, payload.symbol.upper(), payload.timeframe.upper()),
        ).fetchone()
        if payload.expected_updated_at and cur and cur[0] != payload.expected_updated_at:
            raise HTTPException(409, "Workspace was updated elsewhere; reload before saving")
        conn.execute(
            "INSERT INTO chart_workspaces(tenant_id, user_id, symbol, timeframe, indicators, layers, drawings, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(tenant_id, user_id, symbol, timeframe) DO UPDATE SET "
            "indicators=excluded.indicators, layers=excluded.layers, drawings=excluded.drawings, updated_at=excluded.updated_at",
            (
                tenant_id,
                user_id,
                payload.symbol.upper(),
                payload.timeframe.upper(),
                json.dumps(payload.indicators),
                json.dumps(payload.layers),
                json.dumps([d.model_dump() for d in payload.drawings]),
                stamp,
            ),
        )
    return {**payload.model_dump(exclude={"expected_updated_at"}), "updated_at": stamp}


@router.get("/analyses")
def list_analyses(symbol: str, user=Depends(current_user)):
    if not SYMBOL.fullmatch(symbol.upper()):
        raise HTTPException(422, "Invalid symbol")
    with db() as conn:
        tenant_id, user_id, _ = _chart_scope(conn, user)
        rows = conn.execute(
            "SELECT id, symbol, timeframe, title, notes, created_at FROM chart_analyses WHERE tenant_id=? AND user_id=? AND symbol=? ORDER BY created_at DESC LIMIT 100",
            (tenant_id, user_id, symbol.upper()),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/analyses")
def save_analysis(payload: AnalysisIn, user=Depends(current_user)):
    _check(payload.symbol, payload.timeframe)
    aid = str(uuid.uuid4())
    created = iso()
    with db() as conn:
        tenant_id, user_id, _ = _chart_scope(conn, user)
        conn.execute(
            "INSERT INTO chart_analyses(id, tenant_id, user_id, symbol, timeframe, title, notes, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (aid, tenant_id, user_id, payload.symbol.upper(), payload.timeframe.upper(), payload.title, payload.notes, created),
        )
    return {"id": aid, **payload.model_dump(), "created_at": created}


@router.post("/opportunities", status_code=201)
def create_opportunity(payload: OpportunityIn, user=Depends(current_user)):
    _check(payload.symbol, payload.timeframe)
    if payload.direction not in {"BUY", "SELL"}:
        raise HTTPException(422, "Invalid direction")
    if payload.strategy not in {"Trend-in-Trend", "Channel Continuation", "Breakout–Retest", "Breakout-Retest"}:
        raise HTTPException(422, "Invalid strategy")
    with db() as conn:
        tenant_id, user_id, account_id = _chart_scope(conn, user)
        if payload.analysis_id:
            ok = conn.execute(
                "SELECT id FROM chart_analyses WHERE id=? AND tenant_id=? AND user_id=? AND symbol=?",
                (payload.analysis_id, tenant_id, user_id, payload.symbol.upper()),
            ).fetchone()
            if not ok:
                raise HTTPException(404, "Analysis not found")
        return opportunities.create_draft(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            account_id=account_id,
            symbol=payload.symbol.upper(),
            timeframe=payload.timeframe.upper(),
            direction=payload.direction,
            strategy=payload.strategy,
            notes=payload.notes,
            analysis_id=payload.analysis_id,
        )
