"""Central thresholds for Historical Strength, Pair Relationships and Relationship Analysis.

All values are on the 0–100 strength score scale (differentials are score points). Each group can be
overridden with a comma-separated environment variable; invalid overrides fall back to defaults.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .strength_classification import thresholds_payload as classification_thresholds

HTF = ("YTD", "Q", "MN", "W", "D1")
LTF = ("H8", "H1", "M15", "M5", "M1")
ANALYSIS_TIMEFRAMES = HTF + LTF


def _floats(name: str, default: tuple[float, ...], *, descending: bool = False) -> tuple[float, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parts = tuple(float(x) for x in raw.split(","))
    except ValueError:
        return default
    if len(parts) != len(default) or any(p < 0 for p in parts):
        return default
    if descending and list(parts) != sorted(parts, reverse=True):
        return default
    return parts


@dataclass(frozen=True)
class RelationshipThresholds:
    strong_divergence: float
    divergence: float
    moderate: float
    dynamics_epsilon: float
    alignment_epsilon: float
    aligned_ratio: float
    persistent_ratio: float
    developing_ratio: float


@dataclass(frozen=True)
class HistoryThresholds:
    trend_band: float
    momentum_epsilon: float
    reversal_amplitude: float
    crossover_min_gap: float


def relationship_thresholds() -> RelationshipThresholds:
    # PAIR_RELATIONSHIP_THRESHOLDS="strong_divergence,divergence,moderate" (descending score points)
    sd, dv, md = _floats("PAIR_RELATIONSHIP_THRESHOLDS", (30.0, 18.0, 8.0), descending=True)
    # PAIR_DYNAMICS_THRESHOLDS="dynamics_epsilon,alignment_epsilon"
    dyn, align = _floats("PAIR_DYNAMICS_THRESHOLDS", (1.0, 2.0))
    # PAIR_PERSISTENCE_RATIOS="aligned,persistent,developing" (0–1)
    ar, pr, dr = _floats("PAIR_PERSISTENCE_RATIOS", (0.7, 0.8, 0.5))
    return RelationshipThresholds(sd, dv, md, dyn, align, min(ar, 1.0), min(pr, 1.0), min(dr, 1.0))


def history_thresholds() -> HistoryThresholds:
    # STRENGTH_HISTORY_THRESHOLDS="trend_band,momentum_epsilon,reversal_amplitude,crossover_min_gap"
    tb, me, ra, cg = _floats("STRENGTH_HISTORY_THRESHOLDS", (2.0, 0.5, 5.0, 1.0))
    return HistoryThresholds(tb, me, ra, cg)


def dynamics_lookback_minutes() -> float:
    try:
        return max(5.0, float(os.getenv("PAIR_DYNAMICS_LOOKBACK_MINUTES", "60")))
    except ValueError:
        return 60.0


def thresholds_payload() -> dict:
    r = relationship_thresholds()
    h = history_thresholds()
    return {
        "relationship": [
            {"key": "STRONG_DIVERGENCE", "label": "Strong Divergence", "min": r.strong_divergence},
            {"key": "DIVERGENCE", "label": "Divergence", "min": r.divergence},
            {"key": "MODERATE", "label": "Moderate", "min": r.moderate},
            {"key": "BALANCED", "label": "Balanced", "min": 0.0},
        ],
        "dynamics_epsilon": r.dynamics_epsilon,
        "alignment_epsilon": r.alignment_epsilon,
        "aligned_ratio": r.aligned_ratio,
        "persistent_ratio": r.persistent_ratio,
        "developing_ratio": r.developing_ratio,
        "trend_band": h.trend_band,
        "momentum_epsilon": h.momentum_epsilon,
        "reversal_amplitude": h.reversal_amplitude,
        "crossover_min_gap": h.crossover_min_gap,
        "dynamics_lookback_minutes": dynamics_lookback_minutes(),
        "htf": list(HTF),
        "ltf": list(LTF),
        "classification": classification_thresholds(),
    }
