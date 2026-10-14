"""Horizon ceilings, broker reconciliation and M15 entry allocation.

The stricter of the horizon ceiling and the existing account/engine cap wins.
Gold H8 has no position-count ceiling; a missing or exhausted risk budget fails closed.
Nothing here submits an order.
"""
from __future__ import annotations

HORIZON_LIMITS = {"DAILY": 5, "WEEKLY": 2, "MONTHLY": 1, "QUARTERLY": 1}
UI_HORIZON = {
    "DAILY": "DAILY",
    "WEEKLY": "WEEKLY",
    "MONTHLY": "MONTHLY",
    "QUARTERLY": "QUARTERLY",
    "H8": "GOLD_H8",
    "GOLD_H8": "GOLD_H8",
}
TERMINAL_LIFECYCLE = ("INVALIDATED", "EXPIRED", "COMPLETED", "NO_OPPORTUNITY")


def ui_horizon(horizon: str | None) -> str:
    return UI_HORIZON.get((horizon or "").upper(), (horizon or "").upper())


def global_position_limit(engine_cap: int, account_cap: int | None) -> tuple[int, str]:
    """Return the tighter concurrent-position cap and the rule that set it."""
    if account_cap is None:
        return engine_cap, "MAX_CONCURRENT"
    if account_cap < engine_cap:
        return account_cap, "ACCOUNT_POSITION_CAP"
    return engine_cap, "MAX_CONCURRENT"


def horizon_slot_cap(horizon: str | None, *, engine_cap: int, account_cap: int | None) -> int | None:
    """Count ceiling for one symbol and horizon. Gold H8 returns None."""
    name = ui_horizon(horizon)
    global_cap, _rule = global_position_limit(engine_cap, account_cap)
    if name == "GOLD_H8":
        return None
    per_horizon = HORIZON_LIMITS.get(name)
    if per_horizon is None:
        return global_cap
    return min(per_horizon, global_cap)


def budget_open(used_pct: float | None, max_pct: float | None) -> bool:
    """Fail closed when either side of the risk budget is missing."""
    if used_pct is None or max_pct is None:
        return False
    return used_pct < max_pct


def reconcile_orders(orders: list[dict]) -> dict[tuple[str, str], dict[str, int]]:
    """Count each broker id once. Rejected orders take no slot. A partial fill is one open position."""
    seen: set[str] = set()
    out: dict[tuple[str, str], dict[str, int]] = {}
    for order in orders:
        broker_id = str(order.get("broker_order_id") or "").strip()
        if not broker_id or broker_id in seen:
            continue
        seen.add(broker_id)
        symbol = str(order.get("symbol") or "")
        horizon = ui_horizon(str(order.get("horizon") or ""))
        bucket = out.setdefault((symbol, horizon), {"open": 0, "pending": 0, "inflight": 0, "rejected": 0})
        state = str(order.get("state") or "").upper()
        if state == "REJECTED":
            bucket["rejected"] += 1
        elif state == "PENDING":
            bucket["pending"] += 1
        elif state == "INFLIGHT":
            bucket["inflight"] += 1
        elif state in ("OPEN", "PARTIAL"):
            bucket["open"] += 1
    return out


def confirmed_entry_keys(events: list[dict]) -> list[str]:
    """One confirmed closed bar produces one key. Repeats and unconfirmed bars add nothing."""
    seen: set[str] = set()
    keys: list[str] = []
    for event in events:
        if not event.get("confirmed") or not event.get("closed"):
            continue
        key = str(event.get("event_id") or event.get("bar_time") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def authorise_entries(events: list[dict], *, budget_is_open: bool, slots_remaining: int | None) -> int:
    """How many new entries the policy can accept. Zero when risk is exhausted."""
    if not budget_is_open:
        return 0
    count = len(confirmed_entry_keys(events))
    if slots_remaining is None:
        return count
    return min(count, max(0, slots_remaining))
