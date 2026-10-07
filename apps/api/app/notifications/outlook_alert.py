"""AI Market Outlook → Alert Engine: one "AI Analysis Complete" email per published live analysis day.

Replay / backfill runs never alert, and the deduplication key is the analysis date, so a forced re-run of the same day
cannot send a second email. The alert summarises analysis only — it never authorises or describes a trade.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ..market.channel_events import DomainEvent
from ..market.outlook import calendar as cal
from .engine import AlertEngine

EVENT_TYPE = "AI_OUTLOOK_PUBLISHED"
ALL_SYMBOLS = "ALL"
TOP_OPPORTUNITIES = 5


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
    day = date.fromisoformat(run["analysis_date"])
    cutoff = cal.close_time(day)
    qualified = sorted((o for o in outlooks if o.get("qualified")), key=lambda o: o.get("opportunity_rank") or 10**6)
    metadata = {
        "run_id": run["id"],
        "analysis_date": run["analysis_date"],
        "outlook_for": cal.next_trading_day(day).isoformat(),
        "published_at": published_at,
        "asian_open": cal.session_windows(cutoff)[0]["start"],
        "late": bool(late),
        "counts": {k: int(counts.get(k) or 0) for k in ("published", "qualified", "insufficient", "failed")},
        "total": len(outlooks),
        "opportunities": [opportunity(o) for o in qualified[:TOP_OPPORTUNITIES]],
    }
    return DomainEvent(EVENT_TYPE, ALL_SYMBOLS, "D1", None, provider, cutoff.isoformat(), None, None,
                       structure_id=f"AI_OUTLOOK|{run['analysis_date']}", metadata=metadata)


def publish_outlook_published(conn, run: dict, outlooks: list[dict], counts: dict, published_at: str, late: bool,
                              now: datetime | None = None) -> dict:
    """Hand-off from the outlook orchestrator; the caller contains every failure so analysis never depends on mail."""
    from ..market.market_data import market_context
    from .worker import alert_scope, enabled

    if not enabled():
        return {"skipped": "notifications_disabled"}
    if run.get("origin") != "LIVE":
        return {"skipped": "not_live"}
    try:
        provider = market_context(conn).get("active_provider")
    except Exception:  # noqa: BLE001 - provider label is cosmetic
        provider = None
    tenant, account = alert_scope(conn)
    event = outlook_event(run, outlooks, counts, published_at, late, provider)
    return AlertEngine(conn, tenant, account).process([event], [], now or datetime.now(timezone.utc))
