"""AI Market Outlook → Alert Engine.

A published live analysis day still sends one "AI Analysis Complete" email. Replay and backfill never alert.

A live outlook strategy also sends two signal emails, once each: when it is confirmed for entry, and when its order
has been placed. Earlier lifecycle steps stay quiet. Each outlook sends its own pair, so both strategies on one symbol
are notified separately.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from ..market.channel_events import DomainEvent
from ..market.outlook import calendar as cal
from .engine import AlertEngine

EVENT_TYPE = "AI_OUTLOOK_PUBLISHED"
LIFECYCLE_EVENT = "AI_OUTLOOK_EVENT"
ALL_SYMBOLS = "ALL"
_SPAN = {"WEEKLY": timedelta(days=7), "MONTHLY": timedelta(days=31), "QUARTERLY": timedelta(days=93), "H8": timedelta(hours=8)}
_TF = {"DAILY": "D1", "WEEKLY": "W1", "MONTHLY": "MN", "QUARTERLY": "Q", "H8": "H8"}
_HORIZON_LABEL = {"DAILY": "Daily", "WEEKLY": "Weekly", "MONTHLY": "Monthly", "QUARTERLY": "Quarterly", "H8": "H8", "GOLD_H8": "H8"}
# Confirmation and a later risk approval share one email. The placed order is the second email.
_SIGNAL = {
    "CONFIRMED": "ENTRY_CONFIRMED",
    "AUTHORIZATION_PENDING": "ENTRY_CONFIRMED",
    "AUTHORIZED": "ENTRY_CONFIRMED",
    "ORDER_SUBMITTED": "ORDER_PLACED",
}
_SIGNAL_SUMMARY = {
    "ENTRY_CONFIRMED": "This AI outlook strategy is confirmed for entry.",
    "ORDER_PLACED": "The order for this AI outlook strategy has been placed.",
}
TOP_OPPORTUNITIES = 5


def close_is_current(close: datetime, latest: datetime | None) -> bool:
    """A recovered older candle is stored, but only the latest close of that horizon notifies."""
    if latest is None:
        return True
    if close.tzinfo is None:
        close = close.replace(tzinfo=timezone.utc)
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return abs((latest - close).total_seconds()) <= 90


def _latest_broker_close(conn, horizon: str) -> datetime | None:
    from ..market.outlook.horizons import CLOCK, TIMEFRAME, recent_closes

    found = recent_closes(conn, TIMEFRAME[horizon], CLOCK[horizon], datetime.now(timezone.utc), 1)
    return found[0] if found else None


def _price(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def opportunity(o: dict) -> dict:
    erz = o.get("erz") or {}
    return {
        "rank": o.get("opportunity_rank"),
        "symbol": o["symbol"],
        "digits": o.get("digits"),
        "direction": o.get("expected_direction"),
        "confidence": (o.get("confidence") or {}).get("primary"),
        "score": o.get("opportunity_score"),
        "next_move": o.get("expected_next_move"),
        "erz": [_price(erz.get("lo")), _price(erz.get("hi"))],
        "targets": [_price(t.get("price")) for t in o.get("targets") or []],
        "invalidation": _price((o.get("invalidation") or {}).get("price")),
    }


def outlook_event(run: dict, outlooks: list[dict], counts: dict, published_at: str, late: bool, provider: str | None) -> DomainEvent:
    horizon = run.get("horizon") or "DAILY"
    if horizon == "DAILY":
        day = date.fromisoformat(run["analysis_date"])
        cutoff = cal.close_time(day)
        outlook_for = cal.next_trading_day(day).isoformat()
        analysis_label = run["analysis_date"]
        structure = f"AI_OUTLOOK|{run['analysis_date']}"
    else:
        cutoff = datetime.fromisoformat(run["close_at"])
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        outlook_for = (cutoff + _SPAN[horizon]).date().isoformat()
        analysis_label = cutoff.date().isoformat()
        structure = f"AI_OUTLOOK|{horizon}|{run['close_at']}"
    qualified = sorted((o for o in outlooks if o.get("qualified")), key=lambda o: o.get("opportunity_rank") or 10**6)
    metadata = {
        "run_id": run["id"],
        "horizon": horizon,
        "analysis_date": analysis_label,
        "outlook_for": outlook_for,
        "published_at": published_at,
        "asian_open": cal.session_windows(cutoff)[0]["start"],
        "late": bool(late),
        "counts": {k: int(counts.get(k) or 0) for k in ("published", "qualified", "insufficient", "failed")},
        "total": len(outlooks),
        "opportunities": [opportunity(o) for o in qualified[:TOP_OPPORTUNITIES]],
    }
    return DomainEvent(EVENT_TYPE, ALL_SYMBOLS, _TF[horizon], None, provider, cutoff.isoformat(), None, None,
                       structure_id=structure, metadata=metadata)


def publish_outlook_published(conn, run: dict, outlooks: list[dict], counts: dict, published_at: str, late: bool,
                              now: datetime | None = None) -> dict:
    """Hand-off from the outlook orchestrator; the caller contains every failure so analysis never depends on mail."""
    from ..market.market_data import market_context
    from .worker import alert_scope, enabled

    if not enabled():
        return {"skipped": "notifications_disabled"}
    if run.get("origin") != "LIVE":
        return {"skipped": "not_live"}
    horizon = run.get("horizon") or "DAILY"
    if horizon != "DAILY" and run.get("close_at"):
        close = datetime.fromisoformat(run["close_at"])
        if not close_is_current(close, _latest_broker_close(conn, horizon)):
            return {"skipped": "historical_catch_up"}
    try:
        provider = market_context(conn).get("active_provider")
    except Exception:  # noqa: BLE001 - provider label is cosmetic
        provider = None
    tenant, account = alert_scope(conn)
    event = outlook_event(run, outlooks, counts, published_at, late, provider)
    return AlertEngine(conn, tenant, account).process([event], [], now or datetime.now(timezone.utc))


def _live(conn, run: dict) -> bool:
    origin = run.get("origin")
    if not origin and run.get("id"):
        from ..market.provenance import values

        row = conn.execute("SELECT origin FROM ai_outlook_run WHERE id=?", (run["id"],)).fetchone()
        origin = values(row)[0] if row else None
    return origin == "LIVE"


def _with_levels(conn, outlook: dict) -> dict:
    """The execution path stores only the id and symbol. The published payload still has the entry plan."""
    if outlook.get("erz") or outlook.get("targets"):
        return outlook
    outlook_id = outlook.get("outlook_id")
    if not outlook_id:
        return outlook
    from ..market.provenance import values

    row = conn.execute("SELECT payload_json FROM ai_outlook_symbol WHERE id=?", (outlook_id,)).fetchone()
    if not row:
        return outlook
    try:
        payload = json.loads(values(row)[0] or "{}")
    except ValueError:
        return outlook
    if not isinstance(payload, dict):
        return outlook
    return {**payload, **outlook}


def _signal_levels(outlook: dict) -> tuple[float | None, float | None, list[float]]:
    erz = outlook.get("erz") or {}
    invalidation = outlook.get("invalidation") or {}
    entry = _price(erz.get("mid") if isinstance(erz, dict) else None)
    if entry is None and isinstance(erz, dict):
        lo, hi = _price(erz.get("lo")), _price(erz.get("hi"))
        if lo is not None and hi is not None:
            entry = (lo + hi) / 2
    stop = _price(invalidation.get("price") if isinstance(invalidation, dict) else None)
    targets = []
    for target in outlook.get("targets") or []:
        price = _price(target.get("price") if isinstance(target, dict) else target)
        if price is not None:
            targets.append(price)
    return entry, stop, targets


def publish_lifecycle(conn, outlook: dict, run: dict, progress: dict, now: datetime | None = None) -> dict:
    """Email when a live outlook strategy is confirmed for entry, and again when its order is placed.

    Approaching the zone, a reaction, and every other in-progress step stay quiet. The same outlook and stage
    cannot send a second email. Replay and backfill never alert.
    """
    from ..market.market_data import market_context
    from .worker import alert_scope, enabled

    if not enabled() or not _live(conn, run):
        return {"skipped": "not_live"}
    life = progress.get("lifecycle")
    kind = _SIGNAL.get(life or "")
    if not kind:
        return {"skipped": "quiet"}
    outlook = _with_levels(conn, outlook)
    horizon = str(run.get("horizon") or outlook.get("horizon") or "DAILY")
    entry, stop, targets = _signal_levels(outlook)
    ticket = progress.get("execution_ref") or progress.get("ticket")
    try:
        provider = market_context(conn).get("active_provider")
    except Exception:
        provider = None
    tenant, account = alert_scope(conn)
    event = DomainEvent(
        LIFECYCLE_EVENT, outlook.get("symbol") or ALL_SYMBOLS, _TF.get(horizon, "H8"),
        outlook.get("expected_direction") or outlook.get("direction"), provider,
        progress.get("observed_at") or (now or datetime.now(timezone.utc)).isoformat(),
        progress.get("price") or entry, entry, structure_id=f"AI_OUTLOOK_EVENT|{outlook.get('outlook_id')}|{kind}",
        identity=kind,
        metadata={
            "horizon": horizon,
            "horizon_label": _HORIZON_LABEL.get(horizon, horizon),
            "lifecycle": life,
            "kind": kind,
            "summary": _SIGNAL_SUMMARY[kind],
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "ticket": None if not ticket else str(ticket),
            "execution_ref": None if not ticket else str(ticket),
            "force_trade": False,
        },
    )
    return AlertEngine(conn, tenant, account).process([event], [], now or datetime.now(timezone.utc))


def publish_handoff(conn, outlook_id: str, lifecycle: str, ticket: str | None = None, now: datetime | None = None) -> dict:
    """Notify from a handoff row when the writer did not pass the outlook payload."""
    from ..market.provenance import values

    row = conn.execute(
        "SELECT h.run_id, h.symbol, h.horizon, h.close_at, r.origin FROM ai_outlook_handoff h "
        "LEFT JOIN ai_outlook_run r ON r.id = h.run_id WHERE h.outlook_id=?",
        (outlook_id,),
    ).fetchone()
    if not row:
        return {"skipped": "no_handoff"}
    run_id, symbol, horizon, close_at, origin = values(row)
    return publish_lifecycle(
        conn,
        {"outlook_id": outlook_id, "symbol": symbol, "horizon": horizon},
        {"id": run_id, "horizon": horizon, "close_at": close_at, "origin": origin},
        {"lifecycle": lifecycle, "execution_ref": ticket, "observed_at": (now or datetime.now(timezone.utc)).isoformat()},
        now,
    )


def flush_outlook_mail() -> dict:
    """Send anything waiting, and queue the latest live publish if it never produced an alert.

    On Vercel nothing runs between HTTP requests, so a queued email is never sent unless a request delivers it.
    """
    import logging

    from ..core.database import db
    from ..market.outlook.store import DONE_STATES, OutlookRepository
    from ..market.strength_intel_store import active_scope
    from .worker import dispatch, enabled

    log = logging.getLogger("cacsms.ai_outlook")
    queue: dict = {"skipped": "notifications_disabled"}
    if enabled():
        try:
            with db() as conn:
                store = OutlookRepository(conn, active_scope(conn))
                run = store.latest_published()
                if run and run.get("origin") == "LIVE" and run.get("state") in DONE_STATES:
                    outs = store.outlooks(run["id"])
                    published_at = run.get("published_at") or ""
                    asian = cal.session_windows(cal.close_time(date.fromisoformat(run["analysis_date"])))[0]["start"]
                    counts = {k: int(run.get(src) or 0) for k, src in (
                        ("published", "symbols_published"), ("qualified", "qualified"),
                        ("insufficient", "symbols_insufficient"), ("failed", "symbols_failed"))}
                    queue = publish_outlook_published(conn, run, outs, counts, published_at, bool(published_at and published_at > asian))
                    conn.commit()
                else:
                    queue = {"skipped": "no_live_publish"}
        except Exception:
            log.warning("AI analysis complete alert could not be queued", exc_info=True)
            queue = {"error": "queue_failed"}
    try:
        report = dispatch()
    except Exception:
        log.warning("Queued alert email could not be sent", exc_info=True)
        report = {"error": "dispatch_failed"}
    return {"queue": queue, "dispatch": report}
