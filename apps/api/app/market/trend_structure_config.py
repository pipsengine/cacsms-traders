"""Central Trend Structure configuration (Market Structure → Trend Structure).

Every group can be overridden with a comma-separated environment variable; invalid overrides fall back to
defaults. Trend Structure is an analysis surface — it classifies structure and never issues BUY/SELL.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scanner_config import _floats

TREND_TIMEFRAMES = ("W", "D1", "H8", "H1")
BAR_KEYS = {"W": "W1", "D1": "D1", "H8": "H8", "H1": "H1"}

TREND_STATES = {
    "STRONG_UPTREND": "Strong Uptrend",
    "UPTREND_PULLBACK": "Uptrend (Pullback)",
    "UPTREND_EARLY": "Uptrend (Early)",
    "UPTREND": "Uptrend",
    "STRONG_DOWNTREND": "Strong Downtrend",
    "DOWNTREND_PULLBACK": "Downtrend (Pullback)",
    "DOWNTREND_EARLY": "Downtrend (Early)",
    "DOWNTREND": "Downtrend",
    "RANGING": "Ranging",
    "NO_TREND": "No Clear Trend",
}

SETUPS = {
    "CONTINUATION": ("Continuation Setup", "Trend following"),
    "EXTENSION": ("Trend Extension", "Trend following"),
    "REVERSAL_RISK": ("Reversal Risk", "Weakening structure"),
    "DEVELOPING": ("Trend Developing", "Early structure"),
    "NO_TREND": ("No Directional Structure", "Range / transition"),
}

SETUP_STATUS = {
    "MONITORING": "Monitoring",
    "IN_ZONE": "In Zone",
    "EXTENDED": "Extended",
    "INVALIDATED": "Invalidated",
    "NOT_APPLICABLE": "Not applicable",
}


@dataclass(frozen=True)
class TrendSettings:
    analysis_tf: str
    fractal_strength: int
    channel_period: int
    channel_width_sd: float
    efficiency_bars: int
    # Strength composite weights (normalised to 1): alignment, structure, channel, momentum
    weights: tuple[float, float, float, float]
    strong_min: float
    # Pullback / continuation geometry (fractions of the last impulse leg)
    zone_shallow: float
    zone_deep: float
    reversal_depth: float
    objective_extension: float
    early_age_weeks: float
    reversal_event_hours: float
    event_limit: int
    efficiency_full: float
    atr_period: int = 14


def trend_settings() -> TrendSettings:
    # TREND_ANALYSIS="analysis_tf_index(0=W,1=D1,2=H8,3=H1),fractal_strength,channel_period,channel_width_sd,efficiency_bars"
    ti, fs, cp, cw, eb = _floats("TREND_ANALYSIS", (1.0, 2.0, 50.0, 2.0, 20.0))
    # TREND_STRENGTH_WEIGHTS="alignment,structure,channel,momentum"
    ww = _floats("TREND_STRENGTH_WEIGHTS", (0.4, 0.25, 0.15, 0.2))
    total = sum(max(0.0, x) for x in ww) or 1.0
    # TREND_BANDS="strong_min,zone_shallow,zone_deep,reversal_depth,objective_extension,early_age_weeks"
    sm, zs, zd, rd, oe, ea = _floats("TREND_BANDS", (75.0, 0.382, 0.618, 0.786, 1.272, 3.0))
    # TREND_EVENTS="reversal_event_hours,event_limit"
    rh, el = _floats("TREND_EVENTS", (72.0, 14.0))
    # TREND_MOMENTUM="efficiency_full" (efficiency ratio scored as 100% momentum)
    (ef,) = _floats("TREND_MOMENTUM", (0.5,))
    idx = min(max(int(ti), 0), len(TREND_TIMEFRAMES) - 1)
    shallow = min(max(zs, 0.0), 0.95)
    deep = min(max(zd, shallow + 0.01), 0.99)
    return TrendSettings(
        analysis_tf=TREND_TIMEFRAMES[idx],
        fractal_strength=max(1, int(fs)),
        channel_period=max(10, int(cp)),
        channel_width_sd=max(0.5, cw),
        efficiency_bars=max(5, int(eb)),
        weights=tuple(max(0.0, x) / total for x in ww),  # type: ignore[arg-type]
        strong_min=min(max(sm, 50.0), 100.0),
        zone_shallow=shallow,
        zone_deep=deep,
        reversal_depth=min(max(rd, deep), 1.5),
        objective_extension=max(1.0, oe),
        early_age_weeks=max(0.0, ea),
        reversal_event_hours=max(1.0, rh),
        event_limit=max(1, int(el)),
        efficiency_full=min(max(ef, 0.05), 1.0),
    )


def trend_settings_payload() -> dict:
    s = trend_settings()
    return {
        "analysis_tf": s.analysis_tf,
        "fractal_strength": s.fractal_strength,
        "channel_period": s.channel_period,
        "channel_width_sd": s.channel_width_sd,
        "efficiency_bars": s.efficiency_bars,
        "weights": dict(zip(("alignment", "structure", "channel", "momentum"), s.weights)),
        "strong_min": s.strong_min,
        "continuation_zone": [s.zone_shallow, s.zone_deep],
        "reversal_depth": s.reversal_depth,
        "objective_extension": s.objective_extension,
        "early_age_weeks": s.early_age_weeks,
        "reversal_event_hours": s.reversal_event_hours,
        "efficiency_full": s.efficiency_full,
    }
