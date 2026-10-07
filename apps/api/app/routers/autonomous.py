"""Autonomous Trading Engine API — read-only visibility into the backend state machine plus the scheduler entry points.

There is deliberately no endpoint that advances, creates or edits an opportunity or stage: the engine is autonomous.
"""
import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..autonomous import read_model
from ..autonomous.config import STAGE_KEYS, enabled, settings_payload
from ..autonomous.engine import _mode, get_autonomous_engine
from ..autonomous.store import AERepository
from ..core.database import db
from ..deps import current_user
from ..market.scanner_engine import SCANNER_UNIVERSE
from ..market.strength_intel_store import active_scope
from ..services.access import require_permission

router = APIRouter(prefix="/api/autonomous", tags=["Autonomous Engine"])
TIMEFRAMES = ("W", "D1", "H8", "H1")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _repo(conn, user) -> AERepository:
    scope = active_scope(conn)
    if not user["is_platform_admin"]:
        if not scope[0]:
            raise HTTPException(403, "No market-data tenant configured")
        require_permission(conn, user, scope[0], "system.read")
    return AERepository(conn, scope)


def _symbol(symbol: str | None) -> str | None:
    if not symbol:
        return None
    sym = symbol.upper()
    if sym not in SCANNER_UNIVERSE:
        raise HTTPException(400, f"Unknown instrument: {symbol}")
    return sym


def _timeframe(tf: str | None) -> str | None:
    if not tf:
        return None
    if tf.upper() not in TIMEFRAMES:
        raise HTTPException(400, f"Unsupported timeframe: {tf}")
    return tf.upper()


@router.get("/overview")
def overview(user=Depends(current_user)):
    from ..market.market_data import market_context

    with db() as conn:
        repo = _repo(conn, user)
        out = read_model.overview(repo, _now(), market_context(conn), _mode(conn), get_autonomous_engine().running)
    out["enabled"] = enabled()
    out["settings"] = settings_payload()
    return out


@router.get("/stages/{stage}")
def stage(stage: str, symbol: str | None = Query(None), timeframe: str | None = Query(None), provider: str | None = Query(None),
          user=Depends(current_user)):
    key = stage.upper()
    if key not in STAGE_KEYS:
        raise HTTPException(404, "Unknown stage")
    if provider and provider not in ("mt5", "ctrader"):
        raise HTTPException(400, "Unknown provider")
    with db() as conn:
        out = read_model.stage_detail(conn, _repo(conn, user), key, _now(), symbol=_symbol(symbol), timeframe=_timeframe(timeframe),
                                      provider=provider)
    return out


@router.get("/opportunities")
def opportunities(status: str = Query("ACTIVE"), symbol: str | None = Query(None), stage: str | None = Query(None),
                  type: str | None = Query(None), limit: int = Query(100, ge=1, le=500), user=Depends(current_user)):
    st = status.upper()
    if st not in ("ACTIVE", "CLOSED", "ALL"):
        raise HTTPException(400, "status must be ACTIVE, CLOSED or ALL")
    if stage and stage.upper() not in STAGE_KEYS:
        raise HTTPException(400, "Unknown stage")
    with db() as conn:
        return read_model.opportunities(_repo(conn, user), status=None if st == "ALL" else st, symbol=_symbol(symbol),
                                        stage=stage.upper() if stage else None, opp_type=type.upper() if type else None, limit=limit)


@router.get("/opportunities/{opp_id}/history")
def opportunity_history(opp_id: str, user=Depends(current_user)):
    with db() as conn:
        out = read_model.history(_repo(conn, user), opp_id)
    if out is None:
        raise HTTPException(404, "Opportunity not found")
    return out


@router.get("/channels/{channel_id}/chart")
def channel_chart(channel_id: str, limit: int = Query(160, ge=40, le=400), user=Depends(current_user)):
    with db() as conn:
        out = read_model.channel_chart(_repo(conn, user), channel_id, limit)
    if out is None:
        raise HTTPException(404, "Channel not found")
    return out


@router.get("/transitions")
def transitions(entity_type: str | None = Query(None), symbol: str | None = Query(None), limit: int = Query(100, ge=1, le=500),
                user=Depends(current_user)):
    with db() as conn:
        rows = _repo(conn, user).transitions(entity_type=entity_type.upper() if entity_type else None, symbol=_symbol(symbol), limit=limit)
    return {"rows": [read_model.transition_public(t) for t in rows]}


@router.get("/cycles")
def cycles(limit: int = Query(20, ge=1, le=200), user=Depends(current_user)):
    with db() as conn:
        rows = _repo(conn, user).cycles(limit)
    return {"rows": [read_model._cycle_public(c) for c in rows]}


@router.post("/jobs/catch-up")
def catch_up(user=Depends(current_user)):
    """Called by the open page alongside its reads: on serverless, advances the engine when a pass is due (throttled)."""
    with db() as conn:
        _repo(conn, user)
    if not enabled():
        return {"ran": False, "reason": "disabled"}
    return get_autonomous_engine().tick_on_demand()


def _cron_authorized(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET", "").strip()
    if secret and not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "Invalid cron credentials")


@router.get("/jobs/cycle")
def cron_cycle(authorization: str | None = Header(default=None)):
    """Scheduler entry point (cron / external pinger). Idempotent: replays only closed bars newer than each watermark."""
    _cron_authorized(authorization)
    if not enabled():
        return {"ran": False, "reason": "disabled"}
    return get_autonomous_engine().safe_cycle("CRON")
