"""Central Structure Overview configuration (multi-timeframe regime, alignment, structural events).

Every group can be overridden with a comma-separated environment variable; invalid overrides fall back to
defaults. Structure Overview is an intelligence surface — it never issues trade direction or BUY/SELL.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scanner_config import _floats

OVERVIEW_TIMEFRAMES = ("W", "D1", "H8", "H1")

REGIMES = {
    "BULLISH": "Bullish",
    "BEARISH": "Bearish",
    "RANGING": "Ranging",
    "TRANSITION": "Transition",
}

# Matrix cell vocabulary (per timeframe).
CELLS = {
    "BULL": "Bull",
    "BEAR": "Bear",
    "RANGE": "Range",
    "NEUTRAL": "Neutral",
    "PULLBACK": "Pullback",
}

STATES = {
    "TRENDING": "Trending",
    "CONTINUATION": "Continuation",
    "REVERSAL": "Reversal",
    "REACTION": "Reaction",
    "ROTATION": "Rotation",
    "BREAKOUT": "Breakout",
    "TRANSITION": "Transition",
    "INSUFFICIENT": "Insufficient data",
}


@dataclass(frozen=True)
class OverviewSettings:
    weights: dict[str, float]
    bullish_min: float
    bearish_max: float
    strong_alignment: float
    event_lookback_hours: float
    regime_change_hours: float
    retest_atr: float
    top_n: int
    fractal_strength: int = 2
    channel_period: int = 50
    atr_period: int = 14


def overview_settings() -> OverviewSettings:
    # STRUCTURE_ALIGNMENT_WEIGHTS="W,D1,H8,H1" (normalised to sum 1)
    ww = _floats("STRUCTURE_ALIGNMENT_WEIGHTS", (0.4, 0.3, 0.2, 0.1))
    total = sum(max(0.0, x) for x in ww) or 1.0
    weights = {tf: max(0.0, x) / total for tf, x in zip(OVERVIEW_TIMEFRAMES, ww)}
    # STRUCTURE_ALIGNMENT_BANDS="bullish_min,bearish_max,strong" (0–100 alignment score)
    bu, be, st = _floats("STRUCTURE_ALIGNMENT_BANDS", (60.0, 40.0, 85.0))
    # STRUCTURE_EVENTS="event_lookback_hours,regime_change_hours,retest_atr,top_n"
    el, rc, ra, tn = _floats("STRUCTURE_EVENTS", (72.0, 24.0, 0.3, 5.0))
    return OverviewSettings(
        weights=weights,
        bullish_min=max(50.0, bu),
        bearish_max=min(50.0, be),
        strong_alignment=max(bu, st),
        event_lookback_hours=max(1.0, el),
        regime_change_hours=max(1.0, rc),
        retest_atr=max(0.0, ra),
        top_n=max(1, int(tn)),
    )


def overview_settings_payload() -> dict:
    s = overview_settings()
    return {
        "weights": s.weights,
        "bullish_min": s.bullish_min,
        "bearish_max": s.bearish_max,
        "strong_alignment": s.strong_alignment,
        "event_lookback_hours": s.event_lookback_hours,
        "regime_change_hours": s.regime_change_hours,
        "retest_atr": s.retest_atr,
        "top_n": s.top_n,
        "fractal_strength": s.fractal_strength,
        "channel_period": s.channel_period,
    }
