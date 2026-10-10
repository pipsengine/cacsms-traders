"""Overview command centre. Assembles persisted engine, outlook, scanner and account facts.

It does not invent a bias, a confidence, a progress percentage, a broker position, or a P/L figure.
"""
from __future__ import annotations

from datetime import datetime

from .config import OPP_TYPES, ae_settings
from .read_model import opportunity_public

MAJORS = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"}
WORKFLOW = (
    ("scan", "Scan", ("MARKET_DATA", "SCANNER")),
    ("analyze", "Analyze", ("INTELLIGENCE", "STRUCTURE", "CHANNEL")),
    ("setups", "Identify Setups", ("OPPORTUNITY",)),
    ("validate", "Validate", ("CONFIRMATION", "RISK")),
    ("execute", "Execute", ("EXECUTION",)),
    ("manage", "Manage", ("MANAGEMENT", "LEARNING")),
)
LIVE_STAGE = {"RUNNING", "DEGRADED", "STALE", "SYNCHRONIZING", "ERROR"}
def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _bucket(symbol: str) -> str:
    if symbol == "XAUUSD":
        return "commodities"
    if symbol.endswith("JPY") and symbol not in MAJORS:
        return "jpy"
    if symbol in MAJORS:
        return "majors"
    return "minors"


def _outlook(raw: dict | None) -> dict:
    rows = list((raw or {}).get("rows") or [])
    qualified = [r for r in rows if r.get("qualified")]
    bull = sum(1 for r in qualified if r.get("expected_direction") == "BULLISH")
    bear = sum(1 for r in qualified if r.get("expected_direction") == "BEARISH")
    if bull > bear:
        bias = "BULLISH"
    elif bear > bull:
        bias = "BEARISH"
    elif bull or bear:
        bias = "MIXED"
    else:
        bias = None
    scores = [n for n in (_num(r.get("confidence")) for r in qualified) if n is not None]
    ranked = sorted(qualified, key=lambda r: (-(_num(r.get("confidence")) or -1), r.get("symbol") or ""))
    if any(r.get("symbol") == "XAUUSD" for r in ranked):
        ranked.sort(key=lambda r: (r.get("symbol") != "XAUUSD", -(_num(r.get("confidence")) or -1), r.get("symbol") or ""))
    reason = next((str(r.get("reason")).strip() for r in ranked if r.get("reason")), "")
    return {
        "analysis_date": (raw or {}).get("analysis_date"),
        "published_at": (raw or {}).get("published_at"),
        "state": (raw or {}).get("state"),
        "qualified": len(qualified),
        "published": (raw or {}).get("symbols_published"),
        "bias": bias,
        "confidence": round(sum(scores) / len(scores), 1) if scores else None,
        "confidence_basis": "Mean evidence score of the qualified daily outlooks. Not a win probability.",
        "narrative": reason or None,
        "symbols": [{"symbol": r.get("symbol"), "direction": r.get("expected_direction"), "confidence": _num(r.get("confidence"))} for r in ranked[:6]],
    }


def _workflow(stages: list[dict]) -> dict:
    by = {s.get("key"): s for s in stages}

    def group_of(index: int) -> list[dict]:
        return [by[m] for m in WORKFLOW[index][2] if by.get(m)]

    def is_open(index: int) -> bool:
        return any(g.get("status") in LIVE_STAGE for g in group_of(index))

    # Earlier groups stay RUNNING after the pipeline has moved on. The current step is the
    # furthest of Scan → Validate that is still working. Execute counts only when it is not
    # the standing analysis-only block, and Manage counts when nothing ahead of it is open.
    current = 0
    for index in range(4):
        if is_open(index):
            current = index
    if not any(is_open(index) for index in range(4)):
        execute = group_of(4)
        if is_open(4) and not any(g.get("status") == "BLOCKED" for g in execute):
            current = 4
        elif is_open(5):
            current = 5
    steps = []
    for index, (key, label, _members) in enumerate(WORKFLOW):
        group = group_of(index)
        steps.append({
            "key": key,
            "label": label,
            "state": "current" if index == current else "done" if index < current else "pending",
            "statuses": [g.get("status") or "PENDING" for g in group],
            "errors": sum(int(g.get("errors") or 0) for g in group),
            "blockers": [b for g in group for b in (g.get("blockers") or [])][:4],
        })
    focus = None
    operation = None
    nxt = None
    for key in WORKFLOW[current][2]:
        stage = by.get(key) or {}
        operation = operation or stage.get("current_operation")
        nxt = nxt or stage.get("next_operation")
        focus = focus or (stage.get("metrics") or {}).get("focus")
    done = current
    return {
        "steps": steps,
        "current_index": current,
        "current_label": WORKFLOW[current][1],
        "step_of": current + 1,
        "step_count": len(WORKFLOW),
        "position_pct": round(100 * (current + 1) / len(WORKFLOW)),
        "position_basis": "Share of the six workflow groups reached by the latest persisted stage status. Not a task-completion percentage.",
        "operation": operation,
        "next_action": nxt,
        "focus_symbol": focus,
        "completed_groups": done,
        "errors": steps[current]["errors"] if steps else 0,
        "blockers": steps[current]["blockers"] if steps else [],
    }


def _scanner(raw: dict | None) -> dict:
    rows = list((raw or {}).get("rows") or [])
    counts = {"HIGH_INSPECTION": 0, "WATCHING": 0, "NEUTRAL": 0, "EXCLUDED": 0}
    groups = {k: {"HIGH_INSPECTION": 0, "WATCHING": 0, "NEUTRAL": 0, "EXCLUDED": 0} for k in ("majors", "minors", "jpy", "commodities")}
    excluded = []
    for row in rows:
        status = ((row.get("status") or {}).get("key")) or "EXCLUDED"
        if status not in counts:
            status = "EXCLUDED"
        counts[status] += 1
        groups[_bucket(row.get("symbol") or "")][status] += 1
        if status == "EXCLUDED" and len(excluded) < 4:
            reason = row.get("excluded_reason") or (row.get("reasons") or [None])[0]
            if reason:
                excluded.append({"symbol": row.get("symbol"), "reason": reason})
    return {
        "total": len(rows),
        "actionable": counts["HIGH_INSPECTION"],
        "watchlist": counts["WATCHING"],
        "no_setup": counts["NEUTRAL"],
        "excluded": counts["EXCLUDED"],
        "groups": groups,
        "excluded_reasons": excluded,
    }


def _opportunities(rows: list[dict]) -> list[dict]:
    ranked = sorted(rows, key=lambda o: (o.get("symbol") != "XAUUSD", -(_num(o.get("confidence")) or -1), o.get("symbol") or ""))
    out = []
    for o in ranked[:6]:
        out.append({
            "id": o.get("id"),
            "symbol": o.get("symbol"),
            "direction": o.get("direction"),
            "type": o.get("type"),
            "type_label": o.get("type_label") or OPP_TYPES.get(o.get("type"), o.get("type")),
            "tit_level": o.get("tit_level"),
            "timeframe": o.get("trigger_tf"),
            "stage": o.get("stage"),
            "state": o.get("state"),
            "confidence": _num(o.get("confidence")),
            "next_condition": o.get("next_condition"),
            "reason_code": o.get("reason_code"),
        })
    return out


def _tit(rows: list[dict]) -> dict:
    levels: dict[str, int] = {}
    for row in rows:
        if row.get("type") != "TIT" and row.get("opp_type") != "TIT":
            continue
        level = row.get("tit_level") or "UNSET"
        levels[level] = levels.get(level, 0) + 1
    return {"count": sum(levels.values()), "levels": levels}


def assemble(*, now: datetime, mode: str, market_open: bool | None, safety: dict, ribbon: dict, stages: list[dict],
             outlook: dict | None, scanner: dict | None, strength: list[dict], opportunities: list[dict],
             portfolio: dict | None, execution: dict | None, alerts: list[dict]) -> dict:
    ae = ae_settings()
    port = portfolio or {}
    exe = execution or {}
    limits = port.get("limits") or {}
    account = port.get("account") or {}
    broker = (exe.get("broker") or {})
    shadow = exe.get("shadow") or {}
    outcomes = port.get("outcomes") or {}
    safety_blockers = list(safety.get("blockers") or [])
    flow = _workflow(stages)
    flow["blockers"] = (safety_blockers + flow["blockers"])[:6]
    return {
        "as_of": now.isoformat(),
        "mode": mode,
        "market_open": market_open,
        "safety_status": safety.get("status") or ribbon.get("safety_status") or "UNKNOWN",
        "system_status": ribbon.get("system_status"),
        "execution": "BLOCKED",
        "execution_note": (exe.get("execution_note") or "Broker execution is disabled. No order is submitted."),
        "provider": ribbon.get("provider_label") or ribbon.get("provider"),
        "provider_connection": ribbon.get("provider_connection"),
        "data_as_of": ribbon.get("data_as_of"),
        "workers_online": ribbon.get("workers_online"),
        "workers_total": ribbon.get("workers_total"),
        "warnings": list(safety.get("warnings") or [])[:4],
        "limits": {
            "max_open_positions": limits.get("max_open_positions"),
            "max_concurrent": limits.get("max_concurrent") if limits else ae.max_concurrent,
            "max_trade_risk_pct": limits.get("max_trade_risk_pct"),
            "max_total_risk_pct": limits.get("max_total_risk_pct"),
            "source": "account_risk_profiles" if limits.get("max_open_positions") is not None else "engine_concurrent_limit",
        },
        "positions": {
            "broker_open": int(broker.get("open_positions") or 0),
            "shadow_open": int(shadow.get("open_plans") or 0),
            "orders_submitted": int(broker.get("orders_submitted") or 0),
        },
        "account": {
            "currency": account.get("currency"),
            "environment": account.get("environment"),
            "balance": account.get("balance"),
            "equity": account.get("equity"),
            "floating_pnl": account.get("floating_pnl"),
            "floating_pnl_basis": account.get("floating_pnl_basis"),
            "margin_used_pct": account.get("margin_used_pct"),
            "stale": account.get("stale"),
            "connection_status": account.get("connection_status"),
        },
        "outlook": _outlook(outlook),
        "strength": strength,
        "scanner": _scanner(scanner),
        "tit": _tit(opportunities),
        "opportunities": _opportunities(opportunities),
        "workflow": flow,
        "shadow_plans": [
            {
                "symbol": p.get("symbol"),
                "direction": p.get("direction"),
                "type_label": p.get("type_label"),
                "unrealized_r": p.get("unrealized_r"),
                "entry_reference": p.get("entry_reference"),
                "price_status": p.get("price_status"),
                "order_status": p.get("order_status"),
            }
            for p in (exe.get("plans") or [])[:6]
        ],
        "performance": {
            "basis": outcomes.get("basis"),
            "closed_30d": outcomes.get("closed_30d"),
            "hit_rate": outcomes.get("hit_rate"),
            "avg_r": outcomes.get("avg_r"),
            "profit_factor": outcomes.get("profit_factor"),
            "max_drawdown_pct": outcomes.get("max_drawdown_pct"),
            "daily": list(exe.get("daily") or [])[-14:],
        },
        "alerts": alerts[:6],
    }


def build_command_centre(conn, repo, now: datetime, mode: str, engine_running: bool) -> dict:
    from ..market.outlook.store import OutlookRepository
    from ..market.scanner_engine import get_scanner_engine
    from ..market.strength_classification import classify
    from ..market.strength_engine import get_strength_engine
    from ..notifications.store import NotificationStore
    from .execution_book import build_execution
    from .portfolio import build_portfolio
    from .read_model import overview

    board = overview(repo, now, {}, mode, engine_running)
    outlook_repo = OutlookRepository(conn, (repo.tenant, repo.account))
    run = outlook_repo.latest_published("DAILY")
    outlook = None
    if run:
        outlook = {
            "analysis_date": run.get("analysis_date"),
            "published_at": run.get("published_at"),
            "state": run.get("state"),
            "symbols_published": run.get("symbols_published"),
            "rows": outlook_repo.summaries(run["id"]),
        }
    try:
        scan = get_scanner_engine().payload()
    except Exception:
        scan = None
    strength = []
    intel = get_strength_engine().intelligence() or {}
    for currency, values in (intel.get("scores") or {}).items():
        score = _num((values or {}).get("AVG"))
        if score is None:
            continue
        klass = classify(score)
        strength.append({"currency": currency, "score": round(score, 1), "label": klass["label"], "tone": klass["tone"]})
    strength.sort(key=lambda r: -r["score"])
    active = [opportunity_public(o) for o in repo.active_opportunities()]
    alerts = []
    try:
        from .read_model import transition_public

        for item in (transition_public(t) for t in repo.transitions(limit=8)):
            alerts.append({
                "at": item.get("created_at") or item.get("evidence_at"),
                "symbol": item.get("symbol"),
                "timeframe": item.get("timeframe"),
                "label": str(item.get("reason_code") or item.get("to_state") or "Transition").replace("_", " ").title(),
                "direction": None,
                "level": item.get("to_state"),
                "source": "engine",
            })
    except Exception:
        pass
    try:
        for event in NotificationStore(conn, repo.tenant).events(limit=8):
            alerts.append({
                "at": event.get("event_time") or event.get("detected_at"),
                "symbol": event.get("symbol"),
                "timeframe": event.get("timeframe"),
                "label": str(event.get("event_type") or "").replace("_", " ").title(),
                "direction": event.get("direction"),
                "level": event.get("status"),
                "source": "notification",
            })
    except Exception:
        pass
    alerts.sort(key=lambda a: a.get("at") or "", reverse=True)
    return assemble(
        now=now,
        mode=mode,
        market_open=(board.get("safety") or {}).get("market_open"),
        safety=board.get("safety") or {},
        ribbon=board.get("ribbon") or {},
        stages=board.get("stages") or [],
        outlook=outlook,
        scanner=scan,
        strength=strength,
        opportunities=active,
        portfolio=build_portfolio(conn, repo, now),
        execution=build_execution(repo, now),
        alerts=alerts,
    )
