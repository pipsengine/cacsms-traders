"""AI Market Outlook (Daily) API — published immutable outlooks, monitoring, history, performance and the scheduler job."""
import hmac
import logging
import os
import threading
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from ..core.audit import write_audit
from ..core.database import db
from ..deps import current_user
from ..market.outlook import calendar as cal
from ..market.outlook.config import ENGINE_VERSION, outlook_settings, settings_payload
from ..market.outlook.service import get_outlook_service, performance_payload, run_summary, schedule_payload, utcnow
from ..market.outlook.store import DONE_STATES, OutlookRepository
from ..market.scanner_engine import SCANNER_UNIVERSE, chart_candles
from ..market.strength_intel_store import active_scope

router = APIRouter(prefix="/api/ai-outlook", tags=["AI Market Outlook"])
log = logging.getLogger("cacsms.ai_outlook")
ROW_FIELDS = ("symbol", "status", "qualified", "opportunity_rank", "opportunity_score", "expected_direction", "regime", "confidence", "reason",
              "system_action", "price", "digits", "late")
MTF_CHART = ("Y", "YTD", "HY", "Q", "MN", "W", "D1", "H8", "H1", "M30")
_catchup_lock = threading.Lock()


def _catch_up() -> dict:
    """Serverless has no background thread, so the open page asks for a pass in its own request (reads never wait on it).

    Locally the scheduler thread owns the cycle."""
    if os.getenv("VERCEL", "").strip() != "1":
        return {"ran": False, "reason": "scheduler_thread"}
    reason = get_outlook_service().due()
    if reason is None:
        return {"ran": False, "reason": None}
    if not _catchup_lock.acquire(blocking=False):
        return {"ran": False, "reason": "busy"}
    try:
        report = get_outlook_service().tick(replay=False)
    finally:
        _catchup_lock.release()
    return {"ran": "skipped" not in report, "reason": reason}


def _store(conn) -> OutlookRepository:
    return OutlookRepository(conn, active_scope(conn))


def _run_for(store: OutlookRepository, analysis_date: str | None) -> dict | None:
    if analysis_date:
        for origin in ("LIVE", "REPLAY"):
            r = store.run(analysis_date, origin)
            if r and r["state"] in DONE_STATES:
                return r
        return None
    return store.latest_published()


def _summaries(store: OutlookRepository, run_id: str, timing: dict | None = None) -> tuple[list[dict], dict[str, dict]]:
    timing = {} if timing is None else timing
    try:
        t = time.perf_counter()
        rows = store.summaries(run_id)
        timing["summaries"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        revs = store.latest_revisions([o["outlook_id"] for o in rows if o["status"] == "PUBLISHED"])
        timing["revisions"] = (time.perf_counter() - t) * 1000
        return rows, revs
    except Exception:  # noqa: BLE001 - dialect-specific JSON SQL; the full-payload read is slower but always works
        log.warning("Outlook summary query failed; falling back to full payloads", exc_info=True)
        store.conn.rollback()
        timing["fallback"] = 0.0
    rows = []
    for o in store.outlooks(run_id):
        rows.append({**o, "confidence": (o.get("confidence") or {}).get("primary"), "regime": (o.get("regime") or {}).get("label")})
    revs = {o["outlook_id"]: store.latest_revision(o["outlook_id"]) or {} for o in rows if o["status"] == "PUBLISHED"}
    return rows, revs


def _with_monitoring(store: OutlookRepository, o: dict) -> dict:
    rev = store.latest_revision(o["outlook_id"])
    return {**o, "monitoring": rev, "system_action_live": (rev or {}).get("system_action") or o.get("system_action")}


def _symbol(symbol: str) -> str:
    sym = symbol.upper()
    if sym not in SCANNER_UNIVERSE:
        raise HTTPException(400, f"Unknown instrument: {symbol}")
    return sym


def _outlook(symbol: str, analysis_date: str | None) -> tuple[dict, dict]:
    sym = _symbol(symbol)
    with db() as conn:
        store = _store(conn)
        run = _run_for(store, analysis_date)
        if not run:
            raise HTTPException(404, "No published outlook yet")
        o = store.outlook(run["id"], sym)
        if not o:
            raise HTTPException(404, f"No outlook for {sym} on {run['analysis_date']}")
        return run, _with_monitoring(store, o)


@router.get("/status")
def status():
    with db() as conn:
        store = _store(conn)
        latest = store.latest_published()
        live = store.run(get_outlook_service().target_day(utcnow(), outlook_settings()).isoformat(), "LIVE")
    return {"schedule": schedule_payload(), "latest": run_summary(latest), "current": run_summary(live), "engine_version": ENGINE_VERSION,
            "settings": settings_payload(), "last_tick": get_outlook_service().last_tick, "analysis_only": True}


@router.get("/latest")
def latest(response: Response, analysis_date: str | None = Query(None)):
    """Latest published daily outlook: every instrument's status plus the ranked qualified opportunities."""
    timing: dict[str, float] = {}
    data = _latest(analysis_date, timing)
    response.headers["Server-Timing"] = ", ".join(f"{k};dur={v:.0f}" for k, v in timing.items())
    return data


def _latest(analysis_date: str | None, timing: dict[str, float]) -> dict:
    t = time.perf_counter()
    with db() as conn:
        timing["connect"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        store = _store(conn)
        run = _run_for(store, analysis_date)
        live = store.run(get_outlook_service().target_day(utcnow(), outlook_settings()).isoformat(), "LIVE")
        timing["runs"] = (time.perf_counter() - t) * 1000
        rows = []
        if run:
            summaries, revs = _summaries(store, run["id"], timing)
            for o in summaries:
                rev = revs.get(o["outlook_id"]) or {}
                r = {k: o.get(k) for k in ROW_FIELDS}
                r["system_action"] = rev.get("system_action") or o.get("system_action")
                r["monitor_status"] = rev.get("status")
                rows.append(r)
    rows.sort(key=lambda r: (r["opportunity_rank"] is None, r["opportunity_rank"] or 0, r["symbol"]))
    stale = bool(run) and run["analysis_date"] < schedule_payload()["analysis_date"]
    return {"schedule": schedule_payload(), "run": run_summary(run), "current": run_summary(live), "stale": stale, "rows": rows,
            "opportunities": [r for r in rows if r["qualified"]], "engine_version": ENGINE_VERSION, "analysis_only": True}


@router.get("/opportunities")
def opportunities(analysis_date: str | None = Query(None)):
    data = _latest(analysis_date, {})
    return {"run": data["run"], "stale": data["stale"], "opportunities": data["opportunities"],
            "message": None if data["opportunities"] else "No qualified opportunities today"}


@router.get("/symbol/{symbol}")
def symbol_outlook(symbol: str, analysis_date: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    return {"run": run_summary(run), "schedule": schedule_payload(), "outlook": o}


@router.get("/symbol/{symbol}/scenarios")
def scenarios(symbol: str, analysis_date: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    keys = ("symbol", "analysis_date", "status", "price", "digits", "anchor", "regime", "htf_bias", "expected_direction", "primary_scenario",
            "alternative_scenario", "range_scenario", "scenario_conditions", "hypotheses", "confidence", "uncertainty", "evidence", "key_drivers",
            "erz", "targets", "invalidation", "expected_path", "chart_annotations", "monitoring", "reason", "data_quality")
    return {"run": run_summary(run), "outlook": {k: o.get(k) for k in keys}}


@router.get("/symbol/{symbol}/key-levels")
def key_levels(symbol: str, analysis_date: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    keys = ("symbol", "analysis_date", "status", "price", "digits", "anchor", "expected_direction", "key_levels", "key_zones", "supports",
            "resistances", "liquidity", "erz", "targets", "invalidation", "chart_annotations", "fractals", "channels", "reason", "data_quality", "confidence")
    return {"run": run_summary(run), "outlook": {k: o.get(k) for k in keys}}


@router.get("/symbol/{symbol}/annotations")
def annotations(symbol: str, analysis_date: str | None = Query(None), tf: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    items = o.get("chart_annotations") or []
    if tf:
        items = [a for a in items if a.get("tf") in (tf.upper(), None) or tf.upper() in (a.get("tfs") or [])]
    return {"run": run_summary(run), "symbol": o["symbol"], "annotations": items, "evidence": o.get("evidence") or []}


@router.get("/symbol/{symbol}/mtf")
def mtf(symbol: str, analysis_date: str | None = Query(None), limit: int = Query(60, ge=10, le=200)):
    """Multi-timeframe matrix: channel state per timeframe from the outlook plus closed candles per timeframe."""
    run, o = _outlook(symbol, analysis_date)
    candles = {}
    for tf in MTF_CHART:
        try:
            candles[tf] = chart_candles(o["symbol"], tf, limit)["candles"]
        except ValueError:
            candles[tf] = []
    return {"run": run_summary(run), "symbol": o["symbol"], "channels": o.get("channels") or [], "candles": candles,
            "annotations": o.get("chart_annotations") or []}


@router.get("/symbol/{symbol}/session-plan")
def session_plan(symbol: str, analysis_date: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    return {"run": run_summary(run), "symbol": o["symbol"], "session_plan": o.get("session_plan") or [], "active_session": cal.active_session(utcnow()),
            "confirmation_sequence": o.get("confirmation_sequence") or [], "monitoring": o.get("monitoring")}


@router.get("/symbol/{symbol}/monitoring")
def monitoring(symbol: str, analysis_date: str | None = Query(None)):
    run, o = _outlook(symbol, analysis_date)
    with db() as conn:
        revisions = _store(conn).revisions(o["outlook_id"])
    return {"run": run_summary(run), "symbol": o["symbol"], "original": {k: o.get(k) for k in ("expected_direction", "confidence", "erz", "targets", "invalidation",
                                                                                                "confirmation_sequence", "system_action", "published_at")},
            "latest": o.get("monitoring"), "revisions": revisions}


@router.get("/history")
def history(symbol: str = Query(...), days: int = Query(30, ge=5, le=365)):
    """Immutable published outlooks for one instrument with their next-day evaluation (audit trail)."""
    sym = _symbol(symbol)
    since = (utcnow() - timedelta(days=days)).date().isoformat()
    with db() as conn:
        store = _store(conn)
        rows = store.history(sym, since)
        perf = performance_payload(store, days, sym)
    out = []
    for r in rows:
        p = r.pop("payload")
        r.update({"price": p.get("price"), "digits": p.get("digits"), "regime_label": (p.get("regime") or {}).get("label"),
                  "primary": {k: (p.get("primary_scenario") or {}).get(k) for k in ("label", "direction", "probability")},
                  "alternative": {k: (p.get("alternative_scenario") or {}).get(k) for k in ("label", "direction", "probability")},
                  "range": {k: (p.get("range_scenario") or {}).get(k) for k in ("label", "probability")},
                  "erz": p.get("erz"), "targets": p.get("targets"), "invalidation": p.get("invalidation"), "expected_next_move": p.get("expected_next_move"),
                  "snapshot_id": p.get("snapshot_id"), "published_at": p.get("published_at"), "reason": p.get("reason"),
                  "opportunity_score": p.get("opportunity_score"), "late": p.get("late")})
        out.append(r)
    return {"symbol": sym, "days": days, "rows": out, "performance": perf}


@router.get("/performance")
def performance(days: int = Query(30, ge=5, le=365), symbol: str | None = Query(None)):
    with db() as conn:
        return performance_payload(_store(conn), days, _symbol(symbol) if symbol else None)


@router.get("/runs")
def runs(limit: int = Query(40, ge=1, le=200)):
    with db() as conn:
        return {"runs": [run_summary(r) for r in _store(conn).runs(limit=limit)]}


def _cron_authorized(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET", "").strip()
    if secret and not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "Invalid cron credentials")


@router.get("/jobs/daily")
def daily_job(authorization: str | None = Header(default=None)):
    """Scheduler entry point (Vercel Cron after the D1 close; idempotent — safe to call repeatedly)."""
    _cron_authorized(authorization)
    return get_outlook_service().tick()


@router.post("/jobs/catch-up")
def catch_up(user=Depends(current_user)):
    """Called by the open page alongside its reads: advances the serverless scheduler only when something is due."""
    return _catch_up()


@router.post("/jobs/run")
def run_job(analysis_date: str | None = Query(None), user=Depends(current_user)):
    """Operator trigger for a LIVE run that has not published yet (never regenerates a published outlook)."""
    day = date.fromisoformat(analysis_date) if analysis_date else None
    if day and (not cal.is_trading_day(day) or cal.close_time(day) > utcnow()):
        raise HTTPException(400, "That trading day has not closed yet")
    result = get_outlook_service().run_now(day)
    with db() as conn:
        store = _store(conn)
        write_audit(conn, store.tenant or None, user["id"], "AI_OUTLOOK_MANUAL_RUN", "ai_outlook_run", (result.get("run") or {}).get("id"),
                    None, {"analysis_date": analysis_date, "result": result.get("skipped") or (result.get("run") or {}).get("state")}, "Operator trigger")
    run = result.get("run")
    return {"run": run_summary(run) if run else None, "skipped": result.get("skipped")}
