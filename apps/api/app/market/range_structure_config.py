"""Central Range Structure configuration (weekly range detection, fractal evidence, hypothesis bands).

Every group can be overridden with a comma-separated environment variable; invalid overrides fall back to
defaults. Range Structure is an intelligence surface — it never issues trade direction or BUY/SELL.
"""
from __future__ import annotations

from dataclasses import dataclass

from .scanner_config import _floats

RANGE_POSITION_BANDS = (
    (80.0, "UPPER_EXTREME", "Upper Extreme"),
    (60.0, "UPPER_VALUE", "Upper Value"),
    (40.0, "MID_RANGE", "Mid Range"),
    (20.0, "LOWER_VALUE", "Lower Value"),
    (0.0, "LOWER_EXTREME", "Lower Extreme"),
)

# Weighted evidence for a developing weekly fractal (sum = 100).
FRACTAL_EVIDENCE_WEIGHTS = {
    "near_boundary": 20,
    "cluster": 15,
    "weekly_rejection": 20,
    "d1_reaction": 15,
    "h8_structure": 15,
    "h1_bos": 10,
    "weekly_confirmation": 5,
}


@dataclass(frozen=True)
class RangeSettings:
    lookback_weeks: int
    max_width_atr: float
    min_weeks: int
    mature_weeks: int
    zone_tolerance_atr: float
    min_touches: int
    max_outside_ratio: float
    recent_swing_weeks: int
    extreme_pct: float
    breakout_pct: float
    strong: float
    moderate: float
    hypothesis_min: float
    fractal_strength: int
    atr_period: int
    channel_period: int
    major_fractal_strength: int = 8


def range_settings() -> RangeSettings:
    # RANGE_DETECTION="lookback_weeks,max_width_atr,min_weeks,mature_weeks,zone_tolerance_atr,min_touches,max_outside_ratio"
    lb, mw, mn, ma, zt, mt, mo_ = _floats("RANGE_DETECTION", (156.0, 7.0, 8.0, 26.0, 0.5, 2.0, 0.1))
    # RANGE_POSITION="extreme_pct,breakout_pct" (distance from a boundary, % of range width)
    ex, bo = _floats("RANGE_POSITION", (20.0, 5.0))
    # RANGE_HYPOTHESIS_BANDS="strong,moderate,label_min" (0–100 evidence score)
    st, mo, hm = _floats("RANGE_HYPOTHESIS_BANDS", (65.0, 40.0, 55.0))
    return RangeSettings(
        lookback_weeks=max(26, int(lb)),
        max_width_atr=max(1.0, mw),
        min_weeks=max(3, int(mn)),
        mature_weeks=max(int(mn), int(ma)),
        zone_tolerance_atr=zt,
        min_touches=max(1, int(mt)),
        max_outside_ratio=min(0.5, mo_),
        recent_swing_weeks=26,
        extreme_pct=min(45.0, ex),
        breakout_pct=min(ex, bo),
        strong=max(st, mo),
        moderate=min(st, mo),
        hypothesis_min=hm,
        fractal_strength=2,
        atr_period=14,
        channel_period=50,
    )


def range_settings_payload() -> dict:
    s = range_settings()
    return {
        "lookback_weeks": s.lookback_weeks,
        "max_width_atr": s.max_width_atr,
        "min_weeks": s.min_weeks,
        "mature_weeks": s.mature_weeks,
        "zone_tolerance_atr": s.zone_tolerance_atr,
        "min_touches": s.min_touches,
        "max_outside_ratio": s.max_outside_ratio,
        "extreme_pct": s.extreme_pct,
        "breakout_pct": s.breakout_pct,
        "hypothesis_bands": {"strong": s.strong, "moderate": s.moderate, "label_min": s.hypothesis_min},
        "fractal_evidence_weights": FRACTAL_EVIDENCE_WEIGHTS,
        "fractal_strength": s.fractal_strength,
        "major_fractal_strength": s.major_fractal_strength,
        "channel_period": s.channel_period,
    }
