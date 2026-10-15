"""Project persisted outlook analyses into read-only campaigns.

The evidence score is alignment of closed-bar evidence. It is not a win probability.
A qualified campaign is a candidate. Broker position counts come only from reconciled order ids.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .policy import budget_open, horizon_slot_cap, reconcile_orders, ui_horizon
from .qualify import OutlookSignal, qualify

_DIRECTION = {"BULLISH": "BUY", "BUY": "BUY", "BEARISH": "SELL", "SELL": "SELL"}
_CLOSED_LIFECYCLE = ("INVALIDATED", "EXPIRED", "COMPLETED")
_ZONE_LIFECYCLE = {
    "APPROACHING_ZONE", "ZONE_REACHED", "REACTION_PENDING", "CONFIRMATION_PENDING", "CONFIRMED",
    "AWAITING_REACTION", "REACTION", "EXHAUSTION", "CHOCH", "BOS", "RETEST", "NEAR_ERZ",
}
_RISK_LIFECYCLE = {"AUTHORIZATION_PENDING", "AUTHORIZED", "RISK_REVIEW", "RISK_APPROVED", "RISK_DEFERRED"}
_STAGE_RANK = {"QUALIFICATION": 1, "CONFIRMATION": 2, "RISK": 3, "EXECUTION": 4, "MANAGEMENT": 5}
_PIPELINE = {
    "CONFIRMATION": "Stage 7 · Confirmation",
    "RISK": "Stage 8 · Risk authorization",
    "EXECUTION": "Stage 9 · Execution",
    "MANAGEMENT": "Stage 10 · Position management",
}


def trading_mode(system_mode: str | None) -> str:
    mode = (system_mode or "").upper()
    return {
        "LIVE_AUTONOMOUS": "LIVE",
        "DEMO_AUTONOMOUS": "DEMO",
        "SHADOW": "SHADOW",
        "ANALYSIS_ONLY": "SHADOW",
        "PAUSED": "PAUSED",
        "EMERGENCY_STOP": "PAUSED",
    }.get(mode, "PAUSED")


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _score(payload: dict) -> float | None:
    raw = payload.get("evidence_score")
    if isinstance(raw, dict):
        return _num(raw.get("value"))
    found = _num(raw)
    if found is not None:
        return found
    confidence = payload.get("confidence")
    if isinstance(confidence, dict):
        return _num(confidence.get("primary"))
    return _num(confidence)


def _direction(payload: dict) -> str:
    raw = str(payload.get("expected_direction") or payload.get("direction") or "").upper()
    return _DIRECTION.get(raw, "NEUTRAL")


def _levels(payload: dict) -> tuple[float | None, float | None, float | None, list[float]]:
    erz = payload.get("erz") or {}
    invalidation = payload.get("invalidation") or {}
    entry = _num(erz.get("mid"))
    stop = _num(invalidation.get("price"))
    targets = []
    for target in payload.get("targets") or []:
        price = _num(target.get("price") if isinstance(target, dict) else target)
        if price is not None:
            targets.append(price)
    return entry, stop, stop, targets


def _stale(payload: dict) -> bool:
    quality = payload.get("data_quality") or {}
    if quality.get("status") not in (None, "", "OK"):
        return True
    checks = quality.get("checks") or []
    return any(not item.get("fresh", True) for item in checks if isinstance(item, dict))


def _scenario_id(payload: dict) -> str:
    primary = payload.get("primary_scenario") or {}
    if isinstance(primary, dict) and primary.get("key"):
        return str(primary["key"])
    return "primary"


def _status_text(payload: dict, lifecycle: str | None) -> tuple[str, str]:
    current = payload.get("current_status")
    if isinstance(current, dict) and current.get("title"):
        return str(current["title"]), str(current.get("detail") or "")
    labels = {
        "WATCHING": "Watching",
        "APPROACHING_ZONE": "Approaching reaction zone",
        "ZONE_REACHED": "Reaction at ERZ",
        "REACTION_PENDING": "Reaction at ERZ",
        "CONFIRMATION_PENDING": "Awaiting confirmation",
        "CONFIRMED": "Confirmed",
        "AUTHORIZATION_PENDING": "Pending authorization",
        "AUTHORIZED": "Risk authorised",
        "AWAITING_REACTION": "Waiting for the reaction zone",
        "REACTION": "Reaction at the zone",
        "EXHAUSTION": "Exhaustion inside the zone",
        "CHOCH": "Structure shift",
        "BOS": "Break of structure",
        "RETEST": "Retest of the zone",
        "NEAR_ERZ": "Approaching reaction zone",
        "ORDER_SUBMITTED": "Order submitted",
        "PUBLISHED": "Published outlook",
        "INVALIDATED": "Invalidated",
        "EXPIRED": "Expired",
        "COMPLETED": "Completed",
        "NO_OPPORTUNITY": "No opportunity",
    }
    return labels.get(lifecycle or "", lifecycle or "Outlook"), ""


def _signal(outlook: dict, horizon: str, lifecycle: str | None, invalidated: bool) -> OutlookSignal:
    payload = outlook.get("payload") or outlook
    entry, stop, _inv, targets = _levels(payload)
    score = _score(payload)
    published = str(payload.get("status") or outlook.get("status") or "") == "PUBLISHED"
    direction = _direction(payload)
    valid = published and direction in ("BUY", "SELL") and entry is not None and stop is not None and bool(targets)
    return OutlookSignal(
        outlook_id=str(outlook.get("outlook_id") or ""),
        scenario_id=_scenario_id(payload),
        version=1,
        symbol=str(payload.get("symbol") or outlook.get("symbol") or ""),
        horizon=ui_horizon(horizon),  # type: ignore[arg-type]
        score=0.0 if score is None else score,
        direction=direction,
        valid=valid and score is not None,
        stale=_stale(payload) or bool(outlook.get("late")),
        invalidated=invalidated,
    )


_PARENT_TF = {"DAILY": "D1", "WEEKLY": "W", "MONTHLY": "MN", "QUARTERLY": "Q", "H8": "H8", "GOLD_H8": "H8"}


def _same_horizon(row: dict, horizon: str) -> bool:
    """An H1 or daily plan must not be presented as the state of another outlook horizon."""
    name = ui_horizon(horizon)
    evidence = row.get("evidence") or {}
    stamped = evidence.get("outlook_horizon")
    if stamped:
        return ui_horizon(str(stamped)) == name
    parent = _PARENT_TF.get(name)
    return bool(parent) and str(row.get("parent_tf") or "") == parent


def _linked_opportunity(outlook: dict, opportunities: list[dict], horizon: str) -> dict | None:
    payload = outlook.get("payload") or outlook
    symbol = str(payload.get("symbol") or outlook.get("symbol") or "")
    direction = _direction(payload)
    want = {"BUY": "BULLISH", "SELL": "BEARISH"}.get(direction)
    if not want:
        return None
    rank = {"MANAGEMENT": 5, "EXECUTION": 4, "RISK": 3, "CONFIRMATION": 2, "OPPORTUNITY": 1}
    matches = [
        row for row in opportunities
        if row.get("symbol") == symbol and row.get("direction") == want and row.get("status") != "CLOSED" and _same_horizon(row, horizon)
    ]
    if not matches:
        return None
    return max(matches, key=lambda row: (rank.get(str(row.get("stage")), 0), str(row.get("updated_at") or "")))


def _opportunity_stage(opportunity: dict) -> str | None:
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
    return None


def _lifecycle_stage(lifecycle: str | None) -> str | None:
    if lifecycle in _RISK_LIFECYCLE or lifecycle == "ORDER_SUBMITTED":
        return "EXECUTION" if lifecycle == "ORDER_SUBMITTED" else "RISK"
    if lifecycle in _ZONE_LIFECYCLE:
        return "CONFIRMATION"
    return None


def campaign_stage(
    decision, *, lifecycle: str | None, invalidated: bool, opportunity: dict | None, orders: dict[str, int],
    execution_ref: str | None = None,
) -> str:
    if decision.stage == "BLOCKED":
        return "BLOCKED"
    if invalidated or lifecycle in _CLOSED_LIFECYCLE:
        return "CLOSED"
    if not decision.qualified:
        return decision.stage
    if orders.get("open", 0):
        return "MANAGEMENT"
    if orders.get("pending", 0) or orders.get("inflight", 0):
        return "EXECUTION"
    reached = []
    if execution_ref:
        reached.append("EXECUTION")
    if opportunity:
        mapped = _opportunity_stage(opportunity)
        if mapped == "CLOSED":
            return "CLOSED"
        if mapped:
            reached.append(mapped)
    mapped_life = _lifecycle_stage(lifecycle)
    if mapped_life:
        reached.append(mapped_life)
    if not reached:
        return "QUALIFICATION"
    return max(reached, key=lambda name: _STAGE_RANK.get(name, 0))


def _next_action(
    stage: str, decision, opportunity: dict | None, *, horizon: str, ceiling: bool, budget_held: bool,
    note: str | None = None, execution_ref: str | None = None,
) -> str:
    if budget_held:
        return "Risk budget unavailable or exhausted — authorisation held."
    if ceiling and stage in ("QUALIFICATION", "CONFIRMATION", "RISK"):
        return "Slot ceiling reached for this symbol and horizon."
    if opportunity and opportunity.get("next_condition") and stage == "CONFIRMATION":
        return str(opportunity["next_condition"])
    if stage == "QUALIFICATION":
        if horizon == "GOLD_H8":
            return "Candidate. A new closed M15 confirmation and remaining risk budget are required before any entry."
        return "Candidate eligible for independent closed-bar confirmation."
    if stage == "CONFIRMATION":
        return note or "Wait for a closed-bar ERZ reaction, BOS/CHoCH, breakout or retest."
    if stage == "RISK":
        if note:
            return note
        if opportunity and str(opportunity.get("state")) == "EXECUTION_BLOCKED_ANALYSIS_ONLY":
            error = (opportunity.get("evidence") or {}).get("broker_error")
            if error:
                return f"Broker did not accept the order: {error}"
            return "Authorised by risk. No broker order is submitted while the operating mode blocks execution."
        return "Awaiting portfolio authorisation. A qualified outlook is not an order."
    if stage == "EXECUTION":
        if execution_ref:
            return f"Broker order {execution_ref} was submitted. The position appears here only after the terminal reports it."
        return "Reconcile the accepted broker order. No fill is assumed."
    if stage == "MANAGEMENT":
        return "Monitor broker-side invalidation, targets and exposure."
    if stage == "MONITORING":
        return decision.reason
    if stage == "BLOCKED":
        return decision.reason
    if stage == "CLOSED":
        return "Scenario closed on persisted lifecycle."
    return decision.reason


def _evidence(payload: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    meaning = (payload.get("evidence_score") or {}) if isinstance(payload.get("evidence_score"), dict) else {}
    if meaning.get("meaning"):
        rows.append({"label": "Evidence score", "value": str(meaning["meaning"])})
    for item in payload.get("evidence_for") or []:
        if isinstance(item, str):
            rows.append({"label": "Supporting", "value": item})
        elif isinstance(item, dict):
            rows.append({
                "label": str(item.get("title") or item.get("id") or "Supporting"),
                "value": str(item.get("detail") or item.get("label") or ""),
            })
    return rows[:12]


def _iso_latest(*stamps: object) -> str | None:
    """Newest ISO timestamp. Same-offset strings sort in time order."""
    best = None
    for stamp in stamps:
        text = str(stamp or "").strip()
        if text and (best is None or text > best):
            best = text
    return best


def _events(revisions: list[dict], published_at: str | None) -> list[dict[str, str]]:
    events = []
    if published_at:
        events.append({"at": published_at, "stage": "QUALIFICATION", "message": "Outlook snapshot published."})
    for revision in revisions:
        events.append({
            "at": str(revision.get("observed_at") or ""),
            "stage": str(revision.get("status") or ""),
            "message": str(revision.get("status") or "Revision"),
        })
    return events


def project_campaign(
    outlook: dict,
    *,
    horizon: str,
    tenant_id: str,
    account_id: str,
    lifecycle: str | None,
    invalidated: bool,
    opportunity: dict | None,
    orders: dict[str, int],
    engine_cap: int,
    account_cap: int | None,
    exposure_percent: float | None,
    max_exposure_percent: float | None,
    updated_at: str,
    revisions: list[dict] | None = None,
    published_at: str | None = None,
    execution_ref: str | None = None,
    handoff_note: str | None = None,
) -> dict:
    payload = outlook.get("payload") or outlook
    signal = _signal(outlook, horizon, lifecycle, invalidated)
    if _score(payload) is None:
        signal = OutlookSignal(
            outlook_id=signal.outlook_id, scenario_id=signal.scenario_id, version=signal.version, symbol=signal.symbol,
            horizon=signal.horizon, score=signal.score, direction=signal.direction, valid=False, stale=signal.stale,
            invalidated=signal.invalidated,
        )
    decision = qualify(signal)
    stage = campaign_stage(
        decision, lifecycle=lifecycle, invalidated=invalidated or signal.invalidated, opportunity=opportunity, orders=orders,
        execution_ref=execution_ref,
    )
    cap = horizon_slot_cap(signal.horizon, engine_cap=engine_cap, account_cap=account_cap)
    used = int(orders.get("open", 0) + orders.get("pending", 0) + orders.get("inflight", 0))
    ceiling = cap is not None and used >= cap
    held = signal.horizon == "GOLD_H8" and stage in ("RISK", "EXECUTION") and not budget_open(exposure_percent, max_exposure_percent)
    if held and stage == "EXECUTION":
        stage = "RISK"
    checked = _iso_latest(updated_at, (opportunity or {}).get("updated_at")) or updated_at
    title, detail = _status_text(payload, lifecycle)
    if stage == "MONITORING" and decision.reason == "Evidence below threshold":
        title = "Below qualification threshold"
    entry, stop, invalidation, targets = _levels(payload)
    pipeline = None
    if opportunity and str(opportunity.get("stage")) in _PIPELINE:
        pipeline = _PIPELINE[str(opportunity["stage"])]
    elif stage in _PIPELINE:
        pipeline = _PIPELINE[stage]
    return {
        "id": signal.outlook_id,
        "tenantId": tenant_id,
        "accountId": account_id,
        "outlookId": signal.outlook_id,
        "scenarioId": signal.scenario_id,
        "analysisVersion": signal.version,
        "symbol": signal.symbol,
        "horizon": signal.horizon,
        "outlookQualified": bool(payload.get("qualified")),
        "direction": signal.direction if signal.direction in ("BUY", "SELL") else "NEUTRAL",
        "evidenceScore": max(0.0, min(100.0, signal.score if _score(payload) is not None else 0.0)),
        "stage": stage,
        "status": title,
        "entry": entry,
        "stopLoss": stop,
        "targets": targets,
        "invalidation": invalidation,
        "positionsOpen": int(orders.get("open", 0)),
        "positionsPending": int(orders.get("pending", 0) + orders.get("inflight", 0)),
        "positionsUsed": used,
        "brokerPositions": [],
        "maxPositions": cap,
        "nextAction": _next_action(
            stage, decision, opportunity, horizon=signal.horizon, ceiling=ceiling, budget_held=held,
            note=handoff_note, execution_ref=execution_ref,
        ),
        "executionRef": execution_ref,
        "updatedAt": checked,
        "publishedAt": published_at,
        "reason": detail or decision.reason,
        "isStale": signal.stale,
        "sourceMode": "OUTLOOK",
        "strategyType": None,
        "conflict": None,
        "linkedIds": [],
        "entryLo": entry,
        "entryHi": entry,
        "pipelineStage": pipeline,
        "evidence": _evidence(payload),
        "events": _events(revisions or [], published_at),
        "risk": {
            "horizon_cap": cap,
            "positions_used": used,
            "exposure_percent": exposure_percent,
            "max_exposure_percent": max_exposure_percent,
            "budget_open": budget_open(exposure_percent, max_exposure_percent),
            "broker_order": None,
            "evidence_meaning": "Alignment of closed-bar evidence. Not a calibrated win probability.",
        },
    }


def build_overview(
    rows: list[dict],
    *,
    generated_at: datetime | None = None,
    system_mode: str | None,
    engine_cap: int,
    account_cap: int | None,
    exposure_percent: float | None,
    max_exposure_percent: float | None,
    market_data_status: str,
    broker_status: str,
    broker_basis: str,
    opportunities: list[dict] | None = None,
    orders: list[dict] | None = None,
    broker_positions: list[dict] | None = None,
) -> dict:
    """rows: outlook, horizon, tenant_id, account_id, lifecycle, invalidated, updated_at, revisions, published_at."""
    when = generated_at or datetime.now(timezone.utc)
    books = reconcile_orders(orders or [])
    opps = opportunities or []
    campaigns = []
    seen: set[str] = set()
    for row in rows:
        outlook = row["outlook"]
        if not outlook.get("outlook_id"):
            continue
        payload = outlook.get("payload") or outlook
        symbol = str(payload.get("symbol") or outlook.get("symbol") or "")
        horizon = ui_horizon(row.get("horizon"))
        bucket = books.get((symbol, horizon), {"open": 0, "pending": 0, "inflight": 0, "rejected": 0})
        campaign = project_campaign(
            outlook,
            horizon=str(row.get("horizon") or horizon),
            tenant_id=str(row.get("tenant_id") or ""),
            account_id=str(row.get("account_id") or ""),
            lifecycle=row.get("lifecycle"),
            invalidated=bool(row.get("invalidated")),
            opportunity=_linked_opportunity(outlook, opps, str(row.get("horizon") or horizon)),
            orders=bucket,
            engine_cap=engine_cap,
            account_cap=account_cap,
            exposure_percent=exposure_percent,
            max_exposure_percent=max_exposure_percent,
            updated_at=str(row.get("updated_at") or when.isoformat()),
            revisions=row.get("revisions") or [],
            published_at=row.get("published_at"),
            execution_ref=row.get("execution_ref"),
            handoff_note=row.get("handoff_note"),
        )
        key = f"{campaign['outlookId']}:{campaign['scenarioId']}:{campaign['analysisVersion']}"
        if key in seen:
            continue
        seen.add(key)
        campaigns.append(campaign)
    campaigns = [item for item in campaigns if item.get("outlookQualified")]
    from .registry import unify

    campaigns = unify(campaigns, opps, account_cap=account_cap)
    if broker_positions is not None:
        _apply_terminal_positions(campaigns, broker_positions, checked_at=when.isoformat())
        _drop_orders_missing_from_terminal(campaigns, broker_positions)
    campaigns.sort(key=lambda item: (
        0 if item["stage"] not in ("MONITORING", "BLOCKED", "CLOSED") else 1,
        0 if item.get("sourceMode") != "STRATEGY" else 1,
        {"DAILY": 0, "WEEKLY": 1, "MONTHLY": 2, "QUARTERLY": 3, "GOLD_H8": 4}.get(item["horizon"], 9),
        -item["evidenceScore"],
        item["symbol"],
    ))
    def count(stage: str) -> int:
        return sum(item["stage"] == stage for item in campaigns)
    qualified = count("QUALIFICATION")
    horizon_counts = {name: sum(item["horizon"] == name and item.get("sourceMode") != "STRATEGY" for item in campaigns) for name in ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "GOLD_H8")}
    open_positions = len(broker_positions) if broker_positions is not None else sum(item["positionsOpen"] for item in campaigns)
    pending_orders = sum(item["positionsPending"] for item in campaigns)
    fx_positions = None
    gold_positions = None
    if broker_positions is not None:
        gold_positions = sum(1 for item in broker_positions if _canon_symbol(item.get("symbol")).startswith("XAU"))
        fx_positions = len(broker_positions) - gold_positions
    remaining = None
    if exposure_percent is not None and max_exposure_percent is not None:
        remaining = round(max_exposure_percent - exposure_percent, 1)
    return {
        "summary": {
            "qualified": qualified,
            "monitoring": count("MONITORING"),
            "awaitingConfirmation": count("CONFIRMATION"),
            "pendingRisk": count("RISK"),
            "executing": count("EXECUTION"),
            "openPositions": open_positions,
            "fxPositions": fx_positions,
            "goldPositions": gold_positions,
            "pendingOrders": pending_orders,
            "rejected": count("BLOCKED") + sum(1 for item in campaigns if item["stage"] == "CLOSED"),
            "confirmed": count("CONFIRMATION"),
            "campaigns": sum(item["stage"] != "CLOSED" for item in campaigns),
            "exposurePercent": exposure_percent,
            "maxExposurePercent": max_exposure_percent,
            "exposureRemainingPercent": remaining,
            "tradingMode": trading_mode(system_mode),
            "marketDataStatus": market_data_status or "UNKNOWN",
            "brokerStatus": broker_status or "UNKNOWN",
            "brokerBasis": broker_basis,
            "horizonCounts": horizon_counts,
            "sourceCounts": {
                "outlook": sum(item.get("sourceMode") == "OUTLOOK" for item in campaigns),
                "strategy": sum(item.get("sourceMode") == "STRATEGY" for item in campaigns),
                "combined": sum(item.get("sourceMode") == "COMBINED" for item in campaigns),
                "conflicts": sum(bool(item.get("conflict")) for item in campaigns),
            },
        },
        "campaigns": campaigns,
        "generatedAt": when.isoformat(),
    }


def _canon_symbol(symbol: object) -> str:
    text = str(symbol or "").upper().replace("/", "").split(".")[0]
    if text.endswith("M") and len(text) > 6:
        text = text[:-1]
    return "".join(ch for ch in text if ch.isalnum())


def qualified_outlook_directions(conn, tenant: str, account: str) -> dict[str, set[str]]:
    """Directions the latest AI Market Outlook marked qualified, per symbol. An empty set means it is not an opportunity."""
    from ..market.outlook.store import OutlookRepository

    store = OutlookRepository(conn, (tenant, account))
    found: dict[str, set[str]] = {}
    for horizon in ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "H8"):
        run = store.latest_published(horizon)
        if not run:
            continue
        for outlook in store.outlooks(run["id"]):
            if not outlook.get("qualified"):
                continue
            symbol = _canon_symbol(outlook.get("symbol"))
            raw = str(outlook.get("expected_direction") or "").upper()
            direction = {"BULLISH": "BULLISH", "BUY": "BULLISH", "BEARISH": "BEARISH", "SELL": "BEARISH"}.get(raw)
            if symbol and direction:
                found.setdefault(symbol, set()).add(direction)
    return found


def outlook_allows(directions: dict[str, set[str]], symbol: str, direction: str) -> bool:
    """A symbol can be traded only when every qualified outlook agrees with this direction."""
    allowed = directions.get(_canon_symbol(symbol))
    return bool(allowed) and allowed == {str(direction or "").upper()}


def outlook_blocks(directions: dict[str, set[str]], symbol: str, direction: str) -> bool:
    """The execution book may trade a symbol the outlook does not mention. It may not trade against a qualified outlook."""
    allowed = directions.get(_canon_symbol(symbol))
    if not allowed:
        return False
    return str(direction or "").upper() not in allowed


def _px(value: object) -> str:
    number = _num(value)
    if number is None or number == 0:
        return "—"
    return f"{number:.5f}".rstrip("0").rstrip(".")


def _position_note(positions: list[dict]) -> str:
    parts = []
    for pos in positions:
        profit = _num(pos.get("profit"))
        floating = "" if profit is None else f", floating {profit:+.2f}"
        parts.append(
            f"MT5 #{pos.get('ticket')} {str(pos.get('direction') or '').lower()} {pos.get('volume')} "
            f"at {_px(pos.get('priceOpen'))}, stop {_px(pos.get('stopLoss'))}, target {_px(pos.get('takeProfit'))}{floating}"
        )
    return "Terminal position open. " + "; ".join(parts) + "."


def _drop_orders_missing_from_terminal(campaigns: list[dict], positions: list[dict]) -> None:
    """A recorded ticket that the terminal does not have is not an executing order."""
    open_ids = {str(item.get("ticket")) for item in positions if item.get("ticket") is not None}
    for item in campaigns:
        if item.get("stage") != "EXECUTION":
            continue
        if int(item.get("positionsOpen") or 0) > 0:
            continue
        ref = item.get("executionRef")
        if ref and str(ref) in open_ids:
            continue
        if ref:
            item["nextAction"] = f"Broker order {ref} is not open on the terminal."
        else:
            item["nextAction"] = "No open broker order matches this campaign."
        item["stage"] = "CLOSED"
        item["positionsPending"] = 0
        item["positionsOpen"] = 0


def _apply_terminal_positions(campaigns: list[dict], positions: list[dict], *, checked_at: str) -> None:
    """Put each live ticket on one same-direction campaign. A ticket is never copied onto every horizon."""
    preference = {"MANAGEMENT": 0, "EXECUTION": 1, "RISK": 2, "CONFIRMATION": 3, "QUALIFICATION": 4, "MONITORING": 5}
    horizon_order = {"DAILY": 0, "WEEKLY": 1, "MONTHLY": 2, "QUARTERLY": 3, "GOLD_H8": 4}
    for pos in positions:
        symbol = _canon_symbol(pos.get("symbol"))
        direction = str(pos.get("direction") or "").upper()
        if not symbol or direction not in ("BUY", "SELL"):
            continue
        pool = [
            item for item in campaigns
            if _canon_symbol(item.get("symbol")) == symbol and item.get("direction") == direction and item.get("stage") not in ("CLOSED", "BLOCKED")
        ]
        if not pool:
            continue
        chosen = min(pool, key=lambda item: (
            preference.get(str(item.get("stage")), 9),
            horizon_order.get(str(item.get("horizon")), 9),
            -float(item.get("evidenceScore") or 0),
        ))
        held = list(chosen.get("brokerPositions") or [])
        if any(str(item.get("ticket")) == str(pos.get("ticket")) for item in held):
            continue
        held.append(pos)
        chosen["brokerPositions"] = held
        chosen["positionsOpen"] = int(chosen.get("positionsOpen") or 0) + 1
        chosen["positionsUsed"] = int(chosen.get("positionsUsed") or 0) + 1
        chosen["stage"] = "MANAGEMENT"
        chosen["nextAction"] = _position_note(held)
        chosen["updatedAt"] = checked_at
