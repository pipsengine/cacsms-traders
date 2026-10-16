"""One registry for strategy setups and AI Market Outlook campaigns.

Same symbol, same direction and an overlapping entry become one executable row.
Opposite directions are both kept and marked. Neither mode is allowed to erase the other.
"""
from __future__ import annotations

import json

from .policy import STRATEGY_LIMIT

_STRATEGY = {
    "TIT": "Trend-in-Trend",
    "CONTINUATION": "Channel Continuation",
    "P2_BREAKOUT_RETEST": "Breakout-Retest",
    "P1_RETRACEMENT": "Trend Continuation",
}
_RANK = {"QUALIFICATION": 1, "CONFIRMATION": 2, "RISK": 3, "EXECUTION": 4, "MANAGEMENT": 5, "MONITORING": 0, "BLOCKED": 0, "CLOSED": 0}
_BUY = {"BULLISH": "BUY", "BUY": "BUY", "BEARISH": "SELL", "SELL": "SELL"}
_PARENT = {"DAILY": "D1", "WEEKLY": "W", "MONTHLY": "MN", "QUARTERLY": "Q", "GOLD_H8": "H8", "H8": "H8"}


def _side(value: object) -> str:
    return _BUY.get(str(value or "").upper(), "NEUTRAL")


def _stage(opportunity: dict) -> str:
    if str(opportunity.get("status") or "") == "CLOSED":
        return "CLOSED"
    stage = str(opportunity.get("stage") or "")
    state = str(opportunity.get("state") or "")
    if stage == "LEARNING":
        return "CLOSED"
    if stage == "MANAGEMENT":
        return "MANAGEMENT"
    if stage == "EXECUTION" and state == "ORDER_ACCEPTED":
        return "EXECUTION"
    if stage == "EXECUTION" or state == "EXECUTION_BLOCKED_ANALYSIS_ONLY":
        return "RISK"
    if stage == "RISK":
        return "RISK"
    if stage in ("CONFIRMATION", "OPPORTUNITY"):
        return "CONFIRMATION"
    return "QUALIFICATION"


def _num(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _bounds(row: dict) -> tuple[float, float] | None:
    lo = _num(row.get("entryLo"))
    hi = _num(row.get("entryHi"))
    if lo is None or hi is None:
        point = _num(row.get("entry"))
        if point is None:
            return None
        lo = hi = point
    return min(lo, hi), max(lo, hi)


def _same_book(opportunity: dict, row: dict) -> bool:
    """A strategy plan belongs to an outlook only when it names that outlook horizon."""
    evidence = opportunity.get("evidence") or {}
    if isinstance(evidence, str):
        evidence = {}
    stamped = str(evidence.get("outlook_horizon") or "").upper()
    horizon = str(row.get("horizon") or "").upper()
    if stamped:
        return stamped in (horizon, "H8" if horizon == "GOLD_H8" else "")
    parent = str(opportunity.get("parent_tf") or "")
    return bool(parent) and _PARENT.get(horizon) == parent


def zones_overlap(left: dict, right: dict) -> bool:
    a = _bounds(left)
    b = _bounds(right)
    if a is None or b is None:
        return False
    return a[0] <= b[1] and b[0] <= a[1]


def strategy_campaign(opportunity: dict, *, account_cap: int | None) -> dict | None:
    """A strategy setup keeps its own qualification. The outlook score of 70 is not applied."""
    direction = _side(opportunity.get("direction"))
    symbol = str(opportunity.get("symbol") or "")
    if not symbol or direction not in ("BUY", "SELL") or str(opportunity.get("status") or "ACTIVE") != "ACTIVE":
        return None
    kind = str(opportunity.get("opp_type") or "")
    lo = _num(opportunity.get("entry_lo"))
    hi = _num(opportunity.get("entry_hi"))
    entry = None if lo is None or hi is None else (lo + hi) / 2
    target = _num(opportunity.get("target_1"))
    targets = [price for price in (target, _num(opportunity.get("target_2"))) if price is not None]
    score = _num(opportunity.get("confidence"))
    evidence = opportunity.get("evidence") or {}
    order = evidence.get("broker_order") if isinstance(evidence, dict) else None
    ticket = order.get("ticket") if isinstance(order, dict) else None
    return {
        "id": str(opportunity.get("id")),
        "tenantId": str(opportunity.get("tenant_id") or ""),
        "accountId": str(opportunity.get("trading_account_id") or ""),
        "outlookId": str(opportunity.get("id")),
        "scenarioId": str(opportunity.get("family_key") or kind or "strategy"),
        "analysisVersion": 1,
        "symbol": symbol,
        "horizon": "DAILY",
        "sourceMode": "STRATEGY",
        "strategyType": _STRATEGY.get(kind, kind or "Strategy"),
        "outlookQualified": False,
        "direction": direction,
        "evidenceScore": 0.0 if score is None else max(0.0, min(100.0, score)),
        "stage": _stage(opportunity),
        "status": _STRATEGY.get(kind, kind or "Strategy setup"),
        "entry": entry,
        "entryLo": lo,
        "entryHi": hi,
        "stopLoss": _num(opportunity.get("invalidation")),
        "targets": targets,
        "invalidation": _num(opportunity.get("invalidation")),
        "positionsOpen": 0,
        "positionsPending": 0,
        "positionsUsed": 0,
        "brokerPositions": [],
        "maxPositions": STRATEGY_LIMIT,
        "nextAction": str(opportunity.get("next_condition") or "Waiting for the strategy confirmation on a closed bar."),
        "updatedAt": str(opportunity.get("updated_at") or ""),
        "publishedAt": opportunity.get("origin_at"),
        "reason": "Strategy qualification uses its own structural rules. The AI outlook score of 70 is not applied.",
        "isStale": False,
        "pipelineStage": None,
        "conflict": None,
        "linkedIds": [],
        "executionRef": None if not ticket else str(ticket),
        "events": [],
    }


def unify(outlook_rows: list[dict], opportunities: list[dict], *, account_cap: int | None) -> list[dict]:
    """Return one executable list. Overlapping same-direction entries collapse. Conflicts stay visible."""
    book = []
    for row in outlook_rows:
        item = dict(row)
        item["sourceMode"] = item.get("sourceMode") or "OUTLOOK"
        item["strategyType"] = item.get("strategyType")
        item["conflict"] = None
        item["linkedIds"] = list(item.get("linkedIds") or [])
        book.append(item)
    for opportunity in opportunities:
        campaign = strategy_campaign(opportunity, account_cap=account_cap)
        if campaign is None:
            continue
        same = [
            row for row in book
            if row.get("symbol") == campaign["symbol"] and row.get("direction") == campaign["direction"] and row.get("stage") != "CLOSED"
        ]
        overlap = next((row for row in same if zones_overlap(row, campaign) or _same_book(opportunity, row)), None)
        if overlap is not None:
            primary, secondary = (overlap, campaign) if _RANK.get(str(overlap.get("stage")), 0) >= _RANK.get(campaign["stage"], 0) else (campaign, overlap)
            if primary is campaign:
                book.remove(overlap)
                book.append(primary)
            links = list(primary.get("linkedIds") or [])
            if secondary["id"] not in links:
                links.append(secondary["id"])
            primary["linkedIds"] = links
            outlook = overlap if str(overlap.get("sourceMode") or "") != "STRATEGY" else None
            if outlook is None:
                primary["sourceMode"] = "STRATEGY"
                continue
            primary["sourceMode"] = "COMBINED"
            primary["evidenceScore"] = outlook["evidenceScore"]
            primary["horizon"] = outlook.get("horizon") or primary.get("horizon")
            primary["outlookQualified"] = outlook.get("outlookQualified", True)
            if campaign.get("strategyType"):
                primary["strategyType"] = campaign["strategyType"]
            note = "A strategy setup and an AI outlook share this entry. One order and one risk reservation are used."
            if note not in str(primary.get("nextAction") or ""):
                primary["nextAction"] = f"{note} {primary.get('nextAction') or ''}".strip()
            continue
        book.append(campaign)
    by_symbol: dict[str, list[dict]] = {}
    for row in book:
        if row.get("stage") == "CLOSED":
            continue
        by_symbol.setdefault(str(row.get("symbol")), []).append(row)
    for rows in by_symbol.values():
        directions = {row.get("direction") for row in rows}
        if "BUY" in directions and "SELL" in directions:
            for row in rows:
                row["conflict"] = "OPPOSITE_DIRECTION"
                note = "The other mode has the opposite direction. Both analyses stay. A second position on this symbol is not reserved."
                if note not in str(row.get("nextAction") or ""):
                    row["nextAction"] = f"{note} {row.get('nextAction') or ''}".strip()
        if str(rows[0].get("symbol") or "").startswith("XAU") and len(rows) > 1:
            for row in rows:
                note = "Gold strategy trades and the H8 outlook share one XAUUSD risk budget."
                if note not in str(row.get("nextAction") or ""):
                    row["nextAction"] = f"{note} {row.get('nextAction') or ''}".strip()
    return book


def performance_counts(rows: list[dict]) -> dict:
    """Lifecycle outcomes already stored on strategy rows. Shadow plans are not reported as broker profit."""
    grouped: dict[str, dict[str, int]] = {}
    for row in rows:
        if str(row.get("status") or "") != "CLOSED":
            continue
        kind = _STRATEGY.get(str(row.get("opp_type") or ""), str(row.get("opp_type") or "Strategy"))
        bucket = grouped.setdefault(kind, {"closed": 0, "targets": 0, "stopped": 0})
        bucket["closed"] += 1
        outcome = str(row.get("outcome") or "")
        if outcome in ("TARGET_1", "TARGET_2"):
            bucket["targets"] += 1
        elif outcome in ("STOPPED", "INVALIDATED"):
            bucket["stopped"] += 1
    return {
        "basis": "Closed strategy outcomes stored by the engine. Shadow tracking is not broker profit.",
        "strategy": grouped,
    }


def sync_registry(conn, tenant: str, account: str, campaigns: list[dict], now: str) -> None:
    """Replace this scope's registry with the current executable book. The id is stable across restarts."""
    conn.execute("DELETE FROM ce_opportunity WHERE tenant_id=? AND trading_account_id=?", (tenant, account))
    for row in campaigns:
        conn.execute(
            "INSERT INTO ce_opportunity(id, tenant_id, trading_account_id, symbol, source_mode, strategy_type, outlook_horizon, "
            "analysis_id, scenario_id, direction, evidence_score, entry_zone, stop_loss, targets_json, invalidation, "
            "confirmation_requirements, lifecycle_status, stage, conflict, linked_json, campaign_id, next_action, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(row.get("id")), tenant, account, row.get("symbol"), row.get("sourceMode") or "OUTLOOK",
                row.get("strategyType"), None if row.get("sourceMode") == "STRATEGY" else row.get("horizon"),
                row.get("outlookId") or row.get("id"), row.get("scenarioId"), row.get("direction"), row.get("evidenceScore"),
                row.get("entry"), row.get("stopLoss"), json.dumps(row.get("targets") or []), row.get("invalidation"),
                row.get("reason"), row.get("status"), row.get("stage"), row.get("conflict"), json.dumps(row.get("linkedIds") or []),
                row.get("id"), row.get("nextAction"), now, row.get("updatedAt") or now,
            ),
        )
