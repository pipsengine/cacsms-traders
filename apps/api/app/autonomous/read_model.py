"""Read models for the Autonomous Engine page. Everything comes from persisted engine state — nothing is computed here
that could change a trading decision; the page only visualizes what the backend state machine recorded."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .channels import erz
from .config import CHANNEL_STATES, ENGINE_VERSION, OPP_TYPES, STAGES, ae_settings
from .engine import serverless
from .store import AERepository

STAGE_INFO = {k: {"number": n, "label": label, "color": color} for k, n, label, color in STAGES}
ALERT_TYPES = ("CHANNEL_TOUCH", "CHANNEL_BREAK", "BREAK_RETEST_CONTINUATION", "TIT_DETECTED")
ON_DEMAND_FRESH_SECONDS = 900


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def digits(symbol: str) -> int:
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


def _stale_after() -> float:
    ae = ae_settings()
    return ON_DEMAND_FRESH_SECONDS if serverless() else max(3 * ae.cycle_seconds, ae.worker_stale_seconds)


def workers(repo: AERepository, now: datetime) -> dict:
    ae = ae_settings()
    out = []
    for w in repo.workers():
        hb = _dt(w.get("heartbeat_at"))
        age = (now - hb).total_seconds() if hb else None
        limit = ON_DEMAND_FRESH_SECONDS if w["state"] == "ON_DEMAND" else ae.worker_stale_seconds
        online = w["state"] in ("RUNNING", "ON_DEMAND") and age is not None and age <= limit
        out.append({"worker": w["worker"], "label": w["label"], "state": w["state"], "online": online, "heartbeat_at": w.get("heartbeat_at"),
                    "last_success_at": w.get("last_success_at"), "last_error": w.get("last_error"), "age_seconds": None if age is None else round(age)})
    return {"online": sum(1 for w in out if w["online"]), "total": len(out), "items": out}


def _system_status(last: dict | None, last_ok: dict | None, ws: dict, now: datetime) -> str:
    if last is None:
        return "STARTING"
    if last["status"] == "FAILED":
        return "ERROR"
    engine = next((w for w in ws["items"] if w["worker"] == "autonomous-engine"), None)
    if engine is not None and not engine["online"]:
        return "STALLED"
    if last.get("safety_status") == "HALTED":
        return "HALTED"
    return "RUNNING"


def overview(repo: AERepository, now: datetime, ctx: dict, mode: str, engine_running: bool) -> dict:
    from ..market.unified_status import compute_platform_status

    ae = ae_settings()
    last = repo.last_cycle()
    last_ok = repo.last_cycle("COMPLETED")
    ws = workers(repo, now)
    safety = (last_ok or {}).get("safety") or {}
    platform = compute_platform_status(repo.conn)
    ctx = {**ctx, **platform}
    stages_db = repo.stages()
    stale_after = _stale_after()
    stages = []
    for key, n, label, color in STAGES:
        s = stages_db.get(key)
        if s is None:
            stages.append({"key": key, "number": n, "label": label, "color": color, "status": "PENDING", "current_operation": None,
                           "next_operation": None, "processed": 0, "active": 0, "waiting": 0, "errors": 0, "blockers": [], "metrics": {},
                           "last_update": None, "last_success_at": None, "stale": False})
            continue
        updated = _dt(s.get("last_update"))
        stages.append({
            "key": key, "number": n, "label": label, "color": color, "status": s["status"], "current_operation": s.get("current_operation"),
            "next_operation": s.get("next_operation"), "processed": s["processed"], "active": s["active"], "waiting": s["waiting"],
            "errors": s["errors"], "blockers": s.get("blockers") or [], "metrics": s.get("metrics") or {}, "provider": s.get("provider"),
            "last_update": s.get("last_update"), "last_success_at": s.get("last_success_at"),
            "stale": bool(updated and (now - updated).total_seconds() > stale_after),
        })
    completed = _dt((last_ok or {}).get("completed_at"))
    interval = ae.on_demand_seconds if serverless() else ae.cycle_seconds
    active_provider = ctx.get("active_provider")
    providers = ctx.get("providers") or {}
    active_state = providers.get(active_provider or "", {})
    return {
        "ribbon": {
            "system_status": _system_status(last, last_ok, ws, now),
            "safety_status": safety.get("status") or "UNKNOWN",
            "operating_mode": mode,
            "execution": "EXECUTION_BLOCKED_ANALYSIS_ONLY",
            "provider": active_provider,
            "provider_label": {"mt5": "MT5", "ctrader": "cTrader"}.get(active_provider or "", active_provider),
            "provider_connection": platform.get("provider_phase") or ("CONNECTED" if ctx.get("market_data_ready") else "OFFLINE"),
            "data_readiness": platform.get("data_phase"),
            "connections_label": platform.get("connections_label"),
            "strength_pairs_loaded": platform.get("strength_pairs_loaded"),
            "strength_engine_state": platform.get("strength_engine_state"),
            "provider_heartbeat": active_state.get("last_heartbeat"),
            "account_id": (ctx.get("market_data_scope") or {}).get("account_id"),
            "workers_online": ws["online"], "workers_total": ws["total"],
            "server_time": now.isoformat(),
            "last_successful_cycle": (last_ok or {}).get("completed_at"),
            "last_cycle_status": (last or {}).get("status"),
            "last_cycle_origin": (last or {}).get("origin"),
            "next_cycle_at": (completed + timedelta(seconds=interval)).isoformat() if completed else None,
            "cadence": "ON_DEMAND" if serverless() else "WORKER",
            "engine_running": engine_running,
            "data_as_of": (last_ok or {}).get("data_as_of"),
            "engine_version": ENGINE_VERSION,
        },
        "stages": stages,
        "safety": {"status": safety.get("status") or "UNKNOWN", "checks": safety.get("checks") or [], "blockers": safety.get("blockers") or [],
                   "warnings": safety.get("warnings") or [], "market_open": safety.get("market_open")},
        "workers": ws,
        "cycle": _cycle_public(last) if last else None,
        "platform_status": platform,
    }


def _cycle_public(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "origin", "status", "operating_mode", "safety_status", "provider", "snapshot_id", "scanner_cycle_id",
                                  "data_as_of", "started_at", "completed_at", "duration_ms", "error")} | {"counts": c.get("counts") or {}}


def transition_public(t: dict) -> dict:
    return {k: t.get(k) for k in ("id", "entity_type", "entity_id", "symbol", "timeframe", "from_stage", "from_state", "to_stage", "to_state",
                                  "reason_code", "detail", "provider", "evidence_at", "cycle_id", "created_at")} | {"evidence": t.get("evidence") or {}}


def opportunity_public(o: dict) -> dict:
    info = STAGE_INFO.get(o["stage"], {})
    return {
        "id": o["id"], "symbol": o["symbol"], "digits": digits(o["symbol"]), "direction": o["direction"], "type": o["opp_type"],
        "type_label": OPP_TYPES.get(o["opp_type"], o["opp_type"]), "tit_level": o.get("tit_level"), "stage": o["stage"],
        "stage_label": info.get("label"), "stage_number": info.get("number"), "stage_color": info.get("color"), "state": o["state"],
        "status": o["status"], "outcome": o.get("outcome"), "parent_tf": o.get("parent_tf"), "trigger_tf": o.get("trigger_tf"),
        "entry_lo": o.get("entry_lo"), "entry_hi": o.get("entry_hi"), "invalidation": o.get("invalidation"), "target_1": o.get("target_1"),
        "target_2": o.get("target_2"), "current_price": o.get("current_price"), "price_at": o.get("price_at"), "confidence": o.get("confidence"),
        "quality": o.get("quality"), "reward_risk": o.get("reward_risk"), "next_condition": o.get("next_condition"),
        "reason_code": o.get("reason_code"), "provider": o.get("provider"), "blockers": o.get("blockers") or [], "origin_at": o.get("origin_at"),
        "stage_entered_at": o.get("stage_entered_at"), "evaluated_through": o.get("evaluated_through"), "created_at": o.get("created_at"),
        "updated_at": o.get("updated_at"), "closed_at": o.get("closed_at"),
    }


def _erz_band(lines: dict | None, direction: str | None) -> dict | None:
    """The ERZ along the sloped channel: the engine's ERZ rule applied at both regression-line endpoints."""
    if not lines or not lines.get("upper") or not lines.get("lower"):
        return None
    lo_pts, hi_pts = [], []
    for (t, up), (_, low) in zip(lines["upper"], lines["lower"]):
        lo, hi = erz({"upper": up, "lower": low, "direction": direction})
        if lo is None:
            return None
        lo_pts.append([t, lo])
        hi_pts.append([t, hi])
    return {"lower": lo_pts, "upper": hi_pts}


def channel_public(c: dict) -> dict:
    lines = (c.get("lines") or {}).get("lines")
    return {k: c.get(k) for k in ("id", "symbol", "timeframe", "status", "state", "direction", "validity", "upper", "mid", "lower", "width",
                                  "width_atr", "atr", "position", "touches_upper", "touches_lower", "quality", "age_bars", "erz_lo", "erz_hi",
                                  "break_direction", "break_level", "break_at", "retest_at", "continuation_at", "last_touch_at",
                                  "last_touch_side", "state_entered_at", "started_at", "last_bar_at", "closed_at", "provider", "updated_at")} \
        | {"digits": digits(c["symbol"]), "lines": lines, "erz_band": _erz_band(lines, c.get("direction")),
           "ref": (c.get("lines") or {}).get("ref")}


def opportunities(repo: AERepository, *, status: str | None, symbol: str | None, stage: str | None, opp_type: str | None,
                  limit: int) -> dict:
    rows = repo.opportunities(status=status, symbol=symbol, stage=stage, opp_type=opp_type, limit=limit)
    active = repo.opportunities(status="ACTIVE", limit=1000)
    counts = {"active": len(active), "by_stage": {}, "by_type": {}}
    for o in active:
        counts["by_stage"][o["stage"]] = counts["by_stage"].get(o["stage"], 0) + 1
        counts["by_type"][o["opp_type"]] = counts["by_type"].get(o["opp_type"], 0) + 1
    return {"rows": [opportunity_public(o) for o in rows], "counts": counts, "types": OPP_TYPES}


def history(repo: AERepository, opp_id: str) -> dict | None:
    o = repo.opportunity(opp_id)
    if not o:
        return None
    return {"opportunity": {**opportunity_public(o), "evidence": o.get("evidence") or {}},
            "transitions": [transition_public(t) for t in repo.transitions(entity_id=opp_id, limit=500)]}


def _alerts(conn, now: datetime, symbol: str | None) -> dict:
    from ..notifications.worker import alert_scope

    tenant, _ = alert_scope(conn)
    marks = ",".join("?" * len(ALERT_TYPES))
    sql = (f"SELECT id, event_type, symbol, timeframe, direction, status, status_reason, event_time, detected_at, sent_at, level "
           f"FROM alert_events WHERE tenant_id=? AND event_type IN ({marks})")
    params: list = [tenant, *ALERT_TYPES]
    if symbol:
        sql += " AND symbol=?"
        params.append(symbol)
    cols = ("id", "event_type", "symbol", "timeframe", "direction", "status", "status_reason", "event_time", "detected_at", "sent_at", "level")
    rows = [dict(r) if hasattr(r, "keys") else dict(zip(cols, tuple(r)))
            for r in conn.execute(sql + " ORDER BY detected_at DESC LIMIT 12", params).fetchall()]
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    stat_rows = conn.execute(f"SELECT status, COUNT(*) AS n FROM alert_events WHERE tenant_id=? AND event_type IN ({marks}) AND detected_at>=? "
                             "GROUP BY status", (tenant, *ALERT_TYPES, since)).fetchall()
    stats = {}
    for r in stat_rows:
        d = dict(r) if hasattr(r, "keys") else dict(zip(("status", "n"), tuple(r)))
        stats[d["status"]] = int(d["n"] or 0)
    return {"items": rows, "today": stats}


def stage_detail(conn, repo: AERepository, key: str, now: datetime, *, symbol: str | None, timeframe: str | None,
                 provider: str | None) -> dict | None:
    if key not in STAGE_INFO:
        return None
    s = repo.stages().get(key)
    info = STAGE_INFO[key]
    last_ok = repo.last_cycle("COMPLETED")
    ae = ae_settings()
    completed = _dt((last_ok or {}).get("completed_at"))
    interval = ae.on_demand_seconds if serverless() else ae.cycle_seconds
    base = {
        "key": key, **info, "available": s is not None,
        "status": (s or {}).get("status", "PENDING"), "current_operation": (s or {}).get("current_operation"),
        "next_operation": (s or {}).get("next_operation"), "processed": (s or {}).get("processed", 0), "active": (s or {}).get("active", 0),
        "waiting": (s or {}).get("waiting", 0), "errors": (s or {}).get("errors", 0), "metrics": (s or {}).get("metrics") or {},
        "blockers": (s or {}).get("blockers") or [], "detail": (s or {}).get("detail") or {}, "provider": (s or {}).get("provider"),
        "last_update": (s or {}).get("last_update"), "last_success_at": (s or {}).get("last_success_at"),
        "last_successful_cycle": (last_ok or {}).get("completed_at"),
        "next_cycle_at": (completed + timedelta(seconds=interval)).isoformat() if completed else None,
        "filters": {"symbol": symbol, "timeframe": timeframe, "provider": provider},
    }
    if provider and base["provider"] and provider != base["provider"]:
        base["detail"] = {}
        base["provider_mismatch"] = True
    since = (now - timedelta(days=2)).isoformat()
    opp_stage_states = {"OPPORTUNITY": ("WAITING_FOR_ZONE",), "CONFIRMATION": ("AWAITING_REACTION", "REACTION_CONFIRMED", "RISK_REVIEW"),
                        "RISK": ("RISK_APPROVED", "RISK_DEFERRED", "RISK_REJECTED"), "EXECUTION": ("EXECUTION_BLOCKED_ANALYSIS_ONLY",),
                        "LEARNING": ("COMPLETED", "INVALIDATED", "EXPIRED", "RISK_REJECTED")}
    if key == "CHANNEL":
        lineages = [c for c in repo.active_channels() if (not symbol or c["symbol"] == symbol) and (not timeframe or c["timeframe"] == timeframe)]
        base["channels"] = [channel_public(c) for c in lineages]
        base["detections"] = [transition_public(t) for t in repo.transitions(entity_type="CHANNEL", symbol=symbol, timeframe=timeframe,
                                                                             since=since, limit=25)]
        base["alerts"] = _alerts(conn, now, symbol)
        base["lifecycle_states"] = list(CHANNEL_STATES)
        if symbol or timeframe:
            q = base["detail"].get("queue") or []
            base["detail"] = {**base["detail"], "queue": [x for x in q if (not symbol or x["symbol"] == symbol)
                                                          and (not timeframe or x["timeframe"] == timeframe)]}
    elif key in opp_stage_states:
        stage_filter = None if key == "LEARNING" else key
        status = "CLOSED" if key == "LEARNING" else "ACTIVE"
        rows = repo.opportunities(status=status, stage=stage_filter, symbol=symbol, limit=100)
        if timeframe:
            rows = [o for o in rows if timeframe in (o.get("trigger_tf"), o.get("parent_tf"))]
        base["opportunities"] = [opportunity_public(o) for o in rows]
        wanted = set(opp_stage_states[key])
        base["detections"] = [transition_public(t) for t in repo.transitions(entity_type="OPPORTUNITY", symbol=symbol, since=since, limit=200)
                              if t["to_state"] in wanted][:25]
    else:
        base["detections"] = []
        if symbol:
            for list_key in ("instruments", "symbols", "top", "events", "currencies"):
                items = base["detail"].get(list_key)
                if isinstance(items, list):
                    base["detail"][list_key] = [x for x in items if x.get("symbol", symbol) == symbol]
        if timeframe and isinstance(base["detail"].get("events"), list):
            base["detail"]["events"] = [x for x in base["detail"]["events"] if x.get("tf") == timeframe]
    base["symbols"] = [x["symbol"] for x in repo.symbols()]
    return base


def display_channel(symbol: str, timeframe: str, candles: list[dict]) -> dict | None:
    """Channel geometry for a chart timeframe. Display only — not a stored lineage and not an order."""
    from datetime import datetime

    from ..market.channel_intelligence import channel_settings, tf_core
    from ..market.scanner_analytics import Bar
    from .channels import quality

    bars = []
    for c in candles:
        try:
            t = datetime.fromisoformat(str(c["t"]))
            bars.append(Bar(t, float(c["o"]), float(c["h"]), float(c["l"]), float(c["c"]), float(c.get("v") or 0)))
        except (TypeError, ValueError, KeyError):
            continue
    core = tf_core(bars, "W" if timeframe in ("W", "W1") else timeframe, channel_settings())
    if not core.get("available"):
        return None
    width = core["upper"] - core["lower"]
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "state": "ACTIVE" if core["validity"]["key"] == "VALID" else "FORMING",
        "direction": core["direction"],
        "validity": core["validity"]["key"],
        "upper": core["upper"],
        "mid": core["mid"],
        "lower": core["lower"],
        "width": width,
        "width_atr": core["width_atr"],
        "touches_upper": core["touches_upper"],
        "touches_lower": core["touches_lower"],
        "age_bars": core["age"],
        "quality": quality(core),
        "digits": digits(symbol),
        "lines": core["lines"],
    }


def symbol_chart(repo: AERepository, symbol: str, timeframe: str, limit: int) -> dict:
    from ..market.scanner_engine import chart_candles

    candle_name = "W" if timeframe in ("W", "W1") else timeframe
    candles = chart_candles(symbol, candle_name, limit)["candles"]
    view = display_channel(symbol, timeframe, candles)
    stored_tf = "W" if timeframe in ("W", "W1") else timeframe
    stored = next((c for c in repo.active_channels() if c["symbol"] == symbol and c["timeframe"] == stored_tf), None)
    if view and stored:
        view["state"] = stored.get("state") or view["state"]
        if stored.get("quality") is not None:
            view["quality"] = stored["quality"]
    elif stored and not view:
        view = channel_public(stored)
        view["timeframe"] = timeframe
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles, "channel": view}


def channel_chart(repo: AERepository, channel_id: str, limit: int) -> dict | None:
    from ..market.scanner_engine import chart_candles

    c = repo.channel(channel_id)
    if not c:
        return None
    candles = chart_candles(c["symbol"], c["timeframe"], limit)["candles"]
    events = [transition_public(t) for t in repo.transitions(entity_id=channel_id, limit=200)]
    return {"channel": channel_public(c), "candles": candles, "events": events}
