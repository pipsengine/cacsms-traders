"""Derived holding style and duration hints from timeframes and outlook horizons.

Live orders are not tagged in the broker ticket; these fields are computed for UI and
risk/evaluate responses from existing setup metadata (parent/trigger TF, Mode 2 horizon).
"""
from __future__ import annotations

from ..autonomous.config import TF_DELTA, ae_settings

STYLE_INTRADAY = "INTRADAY"
STYLE_SWING = "SWING"
STYLE_POSITION = "POSITION"

STYLE_LABELS = {
    STYLE_INTRADAY: "Intraday",
    STYLE_SWING: "Swing",
    STYLE_POSITION: "Position",
}

_EXIT = "STOP_AND_TARGET"


def _norm_tf(timeframe: str | None) -> str:
    raw = (timeframe or "").strip().upper()
    if raw in ("W", "W1"):
        return "W1"
    if raw == "D":
        return "D1"
    return raw or "H1"


def _tf_hours(timeframe: str | None) -> float:
    name = _norm_tf(timeframe)
    delta = TF_DELTA.get(name)
    if delta is not None:
        return delta.total_seconds() / 3600
    aliases = {
        "M1": 1 / 60,
        "M5": 5 / 60,
        "M15": 0.25,
        "M30": 0.5,
        "H4": 4,
        "MN": 24 * 31,
    }
    return aliases.get(name, 1.0)


def _is_gold(symbol: str | None) -> bool:
    sym = (symbol or "").upper()
    return sym.startswith("XAU") or "GOLD" in sym


def _style_from_timeframes(*, parent_tf: str | None, trigger_tf: str | None, symbol: str | None) -> str:
    parent_h = _tf_hours(parent_tf)
    trigger_h = _tf_hours(trigger_tf)
    peak = max(parent_h, trigger_h)
    if _is_gold(symbol):
        if peak <= 8:
            return STYLE_INTRADAY
        if peak <= 24 * 7:
            return STYLE_SWING
        return STYLE_POSITION
    if peak <= 0.5:
        return STYLE_INTRADAY
    if peak <= 8:
        return STYLE_SWING
    if peak <= 24 * 7:
        return STYLE_SWING
    return STYLE_POSITION


def _style_from_horizon(horizon: str | None) -> str:
    name = (horizon or "").upper()
    if name in ("H8", "GOLD_H8"):
        return STYLE_INTRADAY
    if name == "DAILY":
        return STYLE_SWING
    if name == "WEEKLY":
        return STYLE_SWING
    if name in ("MONTHLY", "QUARTERLY"):
        return STYLE_POSITION
    return STYLE_SWING


def _setup_window(*, trigger_tf: str | None) -> str:
    ae = ae_settings()
    trigger = _norm_tf(trigger_tf)
    trig_h = _tf_hours(trigger)
    zone_h = ae.zone_wait_bars * trig_h
    confirm_h = ae.confirm_bars * _tf_hours("H1")
    total = zone_h + confirm_h
    if total < 48:
        return f"Pre-entry window up to ~{int(total)}h ({ae.zone_wait_bars} {trigger} bars zone wait + {ae.confirm_bars} H1 confirm bars)."
    days = round(total / 24, 1)
    return (
        f"Pre-entry window up to ~{days} days ({ae.zone_wait_bars} {trigger} bars zone wait + "
        f"{ae.confirm_bars} H1 confirm bars)."
    )


def _typical_hold(*, style: str, parent_tf: str | None, trigger_tf: str | None) -> str:
    ae = ae_settings()
    parent = _norm_tf(parent_tf)
    trigger = _norm_tf(trigger_tf)
    shadow_days = max(1, round(ae.shadow_bars / 24))
    if style == STYLE_INTRADAY:
        return (
            f"Exit at stop or target (no time stop). {parent}/{trigger} context — often hours to one session."
        )
    if style == STYLE_POSITION:
        return (
            f"Exit at stop or target (no time stop). {parent}/{trigger} macro context — may run multiple weeks."
        )
    return (
        f"Exit at stop or target (no time stop). {parent}/{trigger} context — often several sessions, "
        f"tracked up to ~{shadow_days} days while the plan is active."
    )


def holding_profile_for_opportunity(opportunity: dict) -> dict:
    """Mode 1 autonomous opportunity row."""
    parent = opportunity.get("parent_tf")
    trigger = opportunity.get("trigger_tf")
    symbol = opportunity.get("symbol")
    style = _style_from_timeframes(parent_tf=parent, trigger_tf=trigger, symbol=symbol)
    return {
        "style": style,
        "style_label": STYLE_LABELS[style],
        "setup_window": _setup_window(trigger_tf=trigger),
        "typical_hold": _typical_hold(style=style, parent_tf=parent, trigger_tf=trigger),
        "exit_mechanism": _EXIT,
        "derived_from": "mode_1_timeframes",
        "parent_tf": parent,
        "trigger_tf": trigger,
    }


def holding_profile_for_execution(
    *,
    mode: str,
    symbol: str,
    parent_tf: str | None = None,
    trigger_tf: str | None = None,
    outlook_horizon: str | None = None,
) -> dict:
    """Size/evaluate/live order path when full opportunity context may be missing."""
    mode_u = (mode or "").upper()
    if mode_u == "MODE_2" or outlook_horizon:
        style = _style_from_horizon(outlook_horizon)
        horizon = (outlook_horizon or "DAILY").upper()
        return {
            "style": style,
            "style_label": STYLE_LABELS[style],
            "setup_window": None,
            "typical_hold": (
                f"Exit at stop or target (no time stop). AI outlook {horizon} horizon — "
                + (
                    "often one to several sessions."
                    if style == STYLE_INTRADAY
                    else "often days to weeks."
                    if style == STYLE_SWING
                    else "may run weeks to months."
                )
            ),
            "exit_mechanism": _EXIT,
            "derived_from": "mode_2_horizon",
            "outlook_horizon": horizon,
        }
    parent = parent_tf or ("H8" if not _is_gold(symbol) else "H8")
    trigger = trigger_tf or "H1"
    style = _style_from_timeframes(parent_tf=parent, trigger_tf=trigger, symbol=symbol)
    return {
        "style": style,
        "style_label": STYLE_LABELS[style],
        "setup_window": _setup_window(trigger_tf=trigger),
        "typical_hold": _typical_hold(style=style, parent_tf=parent, trigger_tf=trigger),
        "exit_mechanism": _EXIT,
        "derived_from": "mode_1_timeframes",
        "parent_tf": parent,
        "trigger_tf": trigger,
    }
