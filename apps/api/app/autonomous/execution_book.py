"""Stage 9–10 read model.

Shadow plans are opportunities the engine already stopped at EXECUTION_BLOCKED_ANALYSIS_ONLY.
This module does not submit, modify, or close broker orders, and it does not invent fills.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import OPP_TYPES
from .opportunities import SIGN
from .store import AERepository

BLOCKED = "EXECUTION_BLOCKED_ANALYSIS_ONLY"
SHADOW_REASONS = {
    "TARGET_1_REACHED": "SHADOW_TARGET",
    "INVALIDATED_AFTER_CONFIRMATION": "SHADOW_STOP",
    "NO_RESOLUTION": "SHADOW_UNRESOLVED",
}
PRICE_STALE_SECONDS = 6 * 3600
EXECUTION_NOTE = (
    "SHADOW / analysis-only. Plans stop at EXECUTION_BLOCKED_ANALYSIS_ONLY. "
    "No broker order is submitted, modified, or closed."
)
BROKER_BASIS = "The execution ledger has no broker orders. These counts stay at zero while submission is blocked."
SHADOW_BASIS = (
    "Open rows are analysis-only plans. Target, stop and unresolved counts are shadow outcomes "
    "from closed-bar tracking, not broker fills."
)
R_BASIS = (
    "Unrealized R is the stored current price versus the confirmation close and invalidation. "
    "It is not a lot size, a fill, or account-currency P&L."
)


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def entry_reference(opportunity: dict) -> float | None:
    evidence = opportunity.get("evidence") or {}
    confirmed = _num((evidence.get("confirmation") or {}).get("close"))
    if confirmed is not None:
        return confirmed
    lo, hi = _num(opportunity.get("entry_lo")), _num(opportunity.get("entry_hi"))
    if lo is None or hi is None:
        return None
    return (lo + hi) / 2


def unrealized_r(opportunity: dict) -> float | None:
    entry = entry_reference(opportunity)
    invalidation = _num(opportunity.get("invalidation"))
    price = _num(opportunity.get("current_price"))
    sign = SIGN.get(opportunity.get("direction"))
    if entry is None or invalidation is None or price is None or not sign:
        return None
    risk = abs(entry - invalidation)
    if not risk:
        return None
    return round((price - entry) * sign / risk, 2)


def _day(stamp: str | None) -> str | None:
    if not stamp or len(stamp) < 10:
        return None
    return stamp[:10]


def _price_status(opportunity: dict, now: datetime) -> str:
    raw = opportunity.get("price_at")
    if not raw:
        return "STALE"
    try:
        stamp = datetime.fromisoformat(str(raw))
    except ValueError:
        return "STALE"
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    if (now - stamp).total_seconds() > PRICE_STALE_SECONDS:
        return "STALE"
    return "SIMULATED"


def plan_row(opportunity: dict, now: datetime) -> dict:
    opp_type = opportunity.get("opp_type")
    return {
        "id": opportunity.get("id"),
        "symbol": opportunity.get("symbol"),
        "direction": opportunity.get("direction"),
        "type": opp_type,
        "type_label": OPP_TYPES.get(opp_type, opp_type),
        "state": opportunity.get("state"),
        "entry_lo": _num(opportunity.get("entry_lo")),
        "entry_hi": _num(opportunity.get("entry_hi")),
        "entry_reference": entry_reference(opportunity),
        "invalidation": _num(opportunity.get("invalidation")),
        "target_1": _num(opportunity.get("target_1")),
        "target_2": _num(opportunity.get("target_2")),
        "current_price": _num(opportunity.get("current_price")),
        "price_at": opportunity.get("price_at"),
        "price_status": _price_status(opportunity, now),
        "unrealized_r": unrealized_r(opportunity),
        "reward_risk": _num(opportunity.get("reward_risk")),
        "confidence": _num(opportunity.get("confidence")),
        "since": opportunity.get("stage_entered_at") or opportunity.get("updated_at"),
        "volume": None,
        "broker_order_id": None,
        "record_class": "SIMULATED",
        "order_status": "NOT_SUBMITTED",
    }


def event_row(transition: dict, opportunity: dict | None) -> dict | None:
    state = transition.get("to_state")
    reason = transition.get("reason_code")
    if state == BLOCKED:
        result = "NOT_SUBMITTED"
    elif reason in SHADOW_REASONS:
        result = SHADOW_REASONS[reason]
    else:
        return None
    opp = opportunity or {}
    opp_type = opp.get("opp_type")
    return {
        "id": transition.get("id"),
        "at": transition.get("evidence_at") or transition.get("created_at"),
        "symbol": transition.get("symbol") or opp.get("symbol"),
        "direction": opp.get("direction"),
        "type": opp_type,
        "type_label": OPP_TYPES.get(opp_type, opp_type),
        "from_state": transition.get("from_state"),
        "to_state": state,
        "reason_code": reason,
        "detail": transition.get("detail"),
        "reference_price": entry_reference(opp) if opp else None,
        "record_class": "SIMULATED",
        "result": result,
        "broker_order_id": None,
        "volume": None,
        "fill_price": None,
        "slippage": None,
        "latency_ms": None,
    }


def assemble_execution(
    *,
    plans: list[dict],
    closed: list[dict],
    transitions: list[dict],
    blocked_30d: int,
    blocked_today: int,
    provider: str | None,
    last_cycle_at: str | None,
    now: datetime,
    by_id: dict[str, dict] | None = None,
) -> dict:
    lookup = by_id or {}
    events = []
    for transition in transitions:
        row = event_row(transition, lookup.get(transition.get("entity_id")))
        if row:
            events.append(row)
    events.sort(key=lambda row: row.get("at") or "", reverse=True)
    shadow_closed = [row for row in closed if row.get("outcome") in ("TARGET_1", "STOPPED", "NO_RESOLUTION")]
    counts = {"TARGET_1": 0, "STOPPED": 0, "NO_RESOLUTION": 0}
    for row in shadow_closed:
        outcome = row.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
    days = []
    blocked_by_day: dict[str, int] = {}
    resolved_by_day: dict[str, int] = {}
    for event in events:
        day = _day(event.get("at"))
        if not day:
            continue
        if event["result"] == "NOT_SUBMITTED":
            blocked_by_day[day] = blocked_by_day.get(day, 0) + 1
        elif event["result"] in ("SHADOW_TARGET", "SHADOW_STOP"):
            resolved_by_day[day] = resolved_by_day.get(day, 0) + 1
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        days.append({"day": day, "blocked": blocked_by_day.get(day, 0), "resolved": resolved_by_day.get(day, 0)})
    return {
        "mode": "SHADOW",
        "broker_submission": "BLOCKED",
        "execution_note": EXECUTION_NOTE,
        "provider": provider,
        "last_cycle_at": last_cycle_at,
        "broker": {
            "orders_submitted": 0,
            "fills": 0,
            "rejections": 0,
            "pending_orders": 0,
            "open_positions": 0,
            "basis": BROKER_BASIS,
        },
        "shadow": {
            "open_plans": len(plans),
            "blocked_today": int(blocked_today),
            "blocked_30d": int(blocked_30d),
            "target_1": counts["TARGET_1"],
            "stopped": counts["STOPPED"],
            "unresolved": counts["NO_RESOLUTION"],
            "basis": SHADOW_BASIS,
        },
        "plans": [plan_row(plan, now) for plan in plans],
        "events": events[:80],
        "daily": days,
        "unavailable": [
            "broker_order_id",
            "volume",
            "fill_price",
            "slippage",
            "latency",
            "broker_pnl",
            "trailing_stop",
            "break_even",
            "partial_close",
        ],
        "r_basis": R_BASIS,
    }


def build_execution(repo: AERepository, now: datetime) -> dict:
    active = repo.active_opportunities()
    plans = [row for row in active if row.get("stage") == "EXECUTION"]
    since = (now - timedelta(days=30)).isoformat()
    today = now.date().isoformat()
    closed = repo.closed_opportunities(since)
    blocked = repo.transitions(entity_type="OPPORTUNITY", to_state=BLOCKED, since=since, limit=300)
    completed = repo.transitions(entity_type="OPPORTUNITY", to_state="COMPLETED", since=since, limit=300)
    transitions = blocked + completed
    by_id = {row["id"]: row for row in active}
    by_id.update({row["id"]: row for row in closed})
    last = repo.last_cycle("COMPLETED") or {}
    counts_30 = repo.transition_counts("OPPORTUNITY", since)
    counts_today = repo.transition_counts("OPPORTUNITY", today)
    return assemble_execution(
        plans=plans,
        closed=closed,
        transitions=transitions,
        blocked_30d=counts_30.get(BLOCKED, 0),
        blocked_today=counts_today.get(BLOCKED, 0),
        provider=last.get("provider"),
        last_cycle_at=last.get("completed_at"),
        now=now,
        by_id=by_id,
    )
