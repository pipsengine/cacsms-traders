"""Global Safety Supervisor: one verdict over every stage, recomputed each cycle from backend facts.

NORMAL → DEGRADED (warnings; analysis continues) → CRITICAL (untrustworthy data/scope: no state advancement) →
HALTED (operator mode PAUSED / EMERGENCY_STOP: opportunities frozen). Execution is blocked in every status.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from ..market.outlook import calendar as cal
from .config import AESettings

LEVEL = {"OK": 0, "WARN": 1, "CRITICAL": 2, "HALT": 3}
STATUS = {0: "NORMAL", 1: "DEGRADED", 2: "CRITICAL", 3: "HALTED"}
PROVIDER_LABELS = {"mt5": "MT5", "ctrader": "cTrader"}


def market_open(now: datetime) -> bool:
    """FX week: Sunday 17:00 to Friday 17:00 New York."""
    ny = now.astimezone(cal.NEW_YORK)
    wd, t = ny.weekday(), ny.time()
    if wd == 5:
        return False
    if wd == 6:
        return t >= cal.ROLLOVER
    if wd == 4:
        return t < cal.ROLLOVER
    return True


def last_market_close(now: datetime) -> datetime:
    """Most recent Friday 17:00 New York at or before ``now`` (used while the market is closed)."""
    ny = now.astimezone(cal.NEW_YORK)
    d = ny.date()
    while d.weekday() != 4:
        d -= timedelta(days=1)
    close = datetime.combine(d, time(17, 0), tzinfo=cal.NEW_YORK)
    if close > ny:
        close -= timedelta(days=7)
    return close


def assess(*, now: datetime, mode: str, ctx: dict, analysis: dict, scanner_meta: dict, scanner_state: dict,
           strength_meta: dict, db_ok: bool, db_ms: float | None, snapshot: dict | None, smtp_ready: bool | None,
           threads: dict[str, bool] | None, serverless: bool, ae: AESettings) -> dict:
    checks: list[dict] = []

    def check(key: str, label: str, level: str, detail: str) -> None:
        checks.append({"key": key, "label": label, "status": level, "detail": detail})

    # Operating mode
    if mode in ("PAUSED", "EMERGENCY_STOP"):
        check("OPERATING_MODE", "Operating mode", "HALT", f"{mode.replace('_', ' ').title()} — autonomous progression halted")
    elif mode == "ANALYSIS_ONLY":
        check("OPERATING_MODE", "Operating mode", "OK", "Analysis only — stages 1–8 run, execution blocked")
    elif mode == "SHADOW":
        check("OPERATING_MODE", "Operating mode", "OK", "Shadow — stages run and broker execution stays blocked")
    else:
        check("OPERATING_MODE", "Operating mode", "WARN", f"{mode.replace('_', ' ').title()} still blocks broker execution")

    # Database
    if not db_ok:
        check("DATABASE", "Database", "CRITICAL", "Database round-trip failed")
    elif db_ms is not None and db_ms > 2000:
        check("DATABASE", "Database", "WARN", f"Slow database round-trip ({db_ms:.0f} ms)")
    else:
        check("DATABASE", "Database", "OK", f"Round-trip {db_ms or 0:.0f} ms")

    # Provider
    active = ctx.get("active_provider")
    providers = ctx.get("providers") or {}
    live = providers.get(active or "", {})
    pairs_loaded = int(strength_meta.get("pairs_loaded") or strength_meta.get("repository_pairs_loaded") or 0)
    if not active:
        check("PROVIDER", "Market-data provider", "CRITICAL", "No market-data provider is selected")
    elif not ctx.get("market_data_ready"):
        if live.get("connected") or live.get("healthy") or ctx.get("provider_phase") == "SYNCHRONIZING":
            detail = f"{PROVIDER_LABELS.get(active, active)} connected — synchronizing closed-bar basket ({pairs_loaded}/28 pairs)"
            level = "OK" if pairs_loaded >= 28 else "WARN"
            check("PROVIDER", "Market-data provider", level, detail)
        else:
            check("PROVIDER", "Market-data provider", "CRITICAL", "No market-data provider is ready")
    else:
        check("PROVIDER", "Market-data provider", "OK", f"{PROVIDER_LABELS.get(active, active)} ready ({pairs_loaded}/28 pairs)")

    # Account / scope consistency
    scope_account = (ctx.get("market_data_scope") or {}).get("account_id") or ""
    if active and snapshot and (snapshot.get("provider") != active or (snapshot.get("account_id") or "") != scope_account):
        check("ACCOUNT_SCOPE", "Account scope", "CRITICAL",
              f"Open data snapshot ({snapshot.get('provider')}/{snapshot.get('account_id') or '—'}) does not match the active scope "
              f"({active}/{scope_account or '—'})")
    elif analysis and snapshot and scanner_state.get("snapshot_id") and scanner_state.get("snapshot_id") != snapshot.get("id"):
        check("ACCOUNT_SCOPE", "Account scope", "CRITICAL", "Analysis was produced from a previous provider scope")
    elif analysis and active and scanner_state.get("provider") and scanner_state.get("provider") != active:
        check("ACCOUNT_SCOPE", "Account scope", "CRITICAL", "Analysis provider differs from the active provider")
    elif ctx.get("execution_account") and scope_account and str(ctx.get("execution_account")) != str(scope_account):
        check("ACCOUNT_SCOPE", "Account scope", "WARN", "Execution binding differs from the market-data account (execution disabled)")
    else:
        check("ACCOUNT_SCOPE", "Account scope", "OK", "Data, analysis and scope agree")

    # Closed-bar data freshness
    ok = {s: a for s, a in analysis.items() if a and "excluded" not in a}
    latest = max((a["last_close"][0] for a in ok.values()), default=None)
    is_open = market_open(now)
    if not ok:
        level = "WARN" if ctx.get("market_data_ready") else "CRITICAL"
        check("DATA_FRESHNESS", "Closed-bar data", level, "No closed-bar analysis yet — awaiting the first scanner cycle")
    else:
        friday_close = last_market_close(now)
        if not is_open:
            age_h = (friday_close - latest).total_seconds() / 3600
        else:
            # Right after the Sunday open the newest bar is Friday's: measure from the reopen, not across the weekend.
            week_open = friday_close + timedelta(days=2)
            age_h = (now - (week_open if latest <= friday_close else latest)).total_seconds() / 3600
        excluded = len(analysis) - len(ok)
        if age_h > 2.5:
            check("DATA_FRESHNESS", "Closed-bar data", "CRITICAL", f"Latest closed H1 bar is {age_h:.1f} h old")
        elif excluded > len(analysis) / 2:
            check("DATA_FRESHNESS", "Closed-bar data", "WARN", f"{excluded} of {len(analysis)} instruments excluded")
        else:
            note = "" if is_open else " (market closed)"
            check("DATA_FRESHNESS", "Closed-bar data", "OK", f"Latest close {latest.isoformat()}{note}")

    # Scanner / analysis worker
    cycle_at = scanner_state.get("cycle_at")
    if scanner_meta.get("engine_state") == "ERROR":
        check("SCANNER", "Scanner engine", "CRITICAL", f"Scanner error: {scanner_meta.get('engine_error') or 'unknown'}")
    elif cycle_at is None:
        check("SCANNER", "Scanner engine", "WARN", "Scanner has not completed a cycle")
    elif (now - cycle_at).total_seconds() > ae.stale_cycle_seconds:
        check("SCANNER", "Scanner engine", "CRITICAL", f"Scanner analysis is {(now - cycle_at).total_seconds() / 60:.0f} min old")
    else:
        check("SCANNER", "Scanner engine", "OK", f"Cycle {scanner_state.get('cycle_id')} at {cycle_at.isoformat()}")

    # Strength engine (degrades confidence only)
    if not strength_meta.get("live_data"):
        reason = strength_meta.get("stale_reason") or strength_meta.get("engine_state") or "not live"
        check("STRENGTH", "Strength engine", "WARN", f"Strength not live ({reason}); confidence uses neutral strength")
    else:
        check("STRENGTH", "Strength engine", "OK", f"{strength_meta.get('pairs_loaded')}/28 pairs live")

    # Workers
    if serverless:
        check("WORKERS", "Workers", "OK", "Serverless: engines advance on demand and by the secured cron job")
    else:
        down = [k for k, v in (threads or {}).items() if not v]
        if down:
            check("WORKERS", "Workers", "WARN", f"Not running: {', '.join(down)}")
        else:
            check("WORKERS", "Workers", "OK", "All background workers running")

    # Email alerts (never blocks analysis)
    if smtp_ready is False:
        check("SMTP", "Email alerts", "WARN", "SMTP not ready — alerts queue; analysis continues")
    elif smtp_ready:
        check("SMTP", "Email alerts", "OK", "SMTP ready")

    check("EXECUTION_LOCK", "Execution lock", "OK", "Broker execution disabled — EXECUTION_BLOCKED_ANALYSIS_ONLY")

    worst = max(LEVEL[c["status"]] for c in checks)
    status = STATUS[worst]
    critical = [c for c in checks if c["status"] in ("CRITICAL", "HALT")]
    return {
        "status": status,
        "checks": checks,
        "blockers": [f"{c['label']}: {c['detail']}" for c in critical],
        "warnings": [f"{c['label']}: {c['detail']}" for c in checks if c["status"] == "WARN"],
        "progress_analysis": worst < LEVEL["CRITICAL"] or (worst == LEVEL["HALT"] and not any(c["status"] == "CRITICAL" for c in checks)),
        "progress_opportunities": worst < LEVEL["CRITICAL"],
        "market_open": is_open,
        "data_as_of": latest.isoformat() if latest else None,
        "execution": "BLOCKED",
    }
