"""Outlook (Mode 2) entry zone and sizing reference.

Broker minimum-lot risk must be measured from the outlook entry zone, not from a live quote
that is still far from the ERZ. Orders are only sent when price is inside or near the zone.
"""
from __future__ import annotations

from .money import D, money
from .service import _apply_min_lot_fallback, _min_lot_max_risk_pct
from .sizing import size_position


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def outlook_size_reference(payload: dict, direction: str) -> float | None:
    """Conservative fill price inside the ERZ for sizing (nearest edge toward the stop)."""
    erz = payload.get("erz") or {}
    lo, hi = _num(erz.get("lo")), _num(erz.get("hi"))
    if lo is not None and hi is not None:
        word = str(direction or "").upper()
        if word in ("BEARISH", "SELL"):
            return hi
        if word in ("BULLISH", "BUY"):
            return lo
    invalidation = payload.get("invalidation") or {}
    entry = _num((payload.get("erz") or {}).get("mid"))
    return entry or _num(invalidation.get("price"))


def outlook_price_ready(payload: dict, live_price: float | None, *, near_atr: float = 0.5) -> tuple[bool, str]:
    if live_price is None:
        return False, "NO_QUOTE"
    erz = payload.get("erz") or {}
    lo, hi = _num(erz.get("lo")), _num(erz.get("hi"))
    if lo is None or hi is None:
        return True, "NO_ERZ"
    if lo <= live_price <= hi:
        return True, "IN_ERZ"
    distance = erz.get("distance_atr")
    if distance is not None and float(distance) <= near_atr:
        return True, "NEAR_ERZ"
    label = erz.get("label") or f"{lo:g} – {hi:g}"
    return False, f"PRICE_OUTSIDE_ERZ ({label})"


def _loss_per_lot(*, price, stop, tick_size, tick_value, commission_per_lot=0, spread_cost_per_lot=0) -> object | None:
    distance = abs(D(price) - D(stop))
    tick = D(tick_size)
    value = D(tick_value)
    if distance <= 0 or tick <= 0 or value <= 0:
        return None
    cost = D(commission_per_lot) + D(spread_cost_per_lot)
    loss = (distance / tick) * value + cost
    return loss if loss > 0 else None


def outlook_volume_plan(
    *,
    payload: dict,
    direction: str,
    live_price: float,
    stop,
    equity,
    risk_pct: float,
    spec: dict,
    tick_value,
    profile: dict | None,
    spread_cost_per_lot=0,
) -> tuple[bool, object | None, str | None]:
    """Size at the ERZ reference, then confirm the same volume is within budget at the live quote."""
    ready, reason = outlook_price_ready(payload, live_price)
    if not ready:
        return False, None, reason
    reference = outlook_size_reference(payload, direction)
    if reference is None:
        reference = live_price
    ceiling = _min_lot_max_risk_pct(profile)
    cap = money(D(equity) * D(ceiling) / D(100))
    commission = spec.get("commission_per_lot") or 0
    stops = D(spec.get("stops_level_points") or 0) * D(spec.get("point") or spec.get("tick_size"))
    sized = size_position(
        equity=equity,
        risk_pct=risk_pct,
        price=reference,
        stop=stop,
        tick_size=spec["tick_size"],
        tick_value=tick_value,
        volume_min=spec["volume_min"],
        volume_max=spec["volume_max"],
        volume_step=spec["volume_step"],
        commission_per_lot=commission,
        spread_cost_per_lot=spread_cost_per_lot,
        stops_distance=stops,
    )
    if not sized.ok:
        sized, _ = _apply_min_lot_fallback(
            sized, equity=equity, volume_min=spec["volume_min"], ceiling_pct=ceiling,
        )
    if not sized.ok or sized.volume is None:
        return False, None, sized.reason or "MINIMUM_EXCEEDS_BUDGET"
    live_loss = _loss_per_lot(
        price=live_price, stop=stop, tick_size=spec["tick_size"], tick_value=tick_value,
        commission_per_lot=commission, spread_cost_per_lot=spread_cost_per_lot,
    )
    if live_loss is None:
        return False, None, "CONTRACT_SPEC_INCOMPLETE"
    projected_live = money(D(sized.volume) * D(live_loss))
    if projected_live > cap:
        return False, None, "MINIMUM_EXCEEDS_BUDGET"
    return True, sized.volume, None
