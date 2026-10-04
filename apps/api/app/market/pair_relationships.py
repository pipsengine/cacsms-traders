"""Pair Relationship engine: currency strength scores → 28-pair strength differentials.

Pure functions over the same 0–100 scores the Strength Matrix shows (``normalize_all_scores``).
Describes relationships only; it never produces trade direction or BUY/SELL output.
"""
from __future__ import annotations

from .constants import FX_PAIRS_28
from .strength_classification import classify
from .strength_intel_config import ANALYSIS_TIMEFRAMES, RelationshipThresholds, relationship_thresholds

Scores = dict[str, dict[str, float]]

RELATIONSHIP_LABELS = {
    "STRONG_DIVERGENCE": "Strong Divergence",
    "DIVERGENCE": "Divergence",
    "MODERATE": "Moderate",
    "BALANCED": "Balanced / Equilibrium",
}
DYNAMICS_LABELS = {
    "EXPANDING": "Expanding",
    "CONTRACTING": "Contracting",
    "REVERSING": "Reversing",
    "STABLE": "Stable",
    "NO_HISTORY": "Awaiting history",
}
ALIGNMENT_LABELS = {
    "ALIGNED": "Aligned",
    "PARTIAL": "Partially aligned",
    "CONFLICTED": "Conflicted",
    "NEUTRAL": "No clear direction",
}


def _sign(v: float, eps: float = 0.0) -> int:
    return 1 if v > eps else -1 if v < -eps else 0


def split_pair(pair: str) -> tuple[str, str]:
    p = pair.upper()
    return p[:3], p[3:6]


def differential(scores: Scores, base: str, quote: str, tf: str) -> float | None:
    b, q = scores.get(base, {}).get(tf), scores.get(quote, {}).get(tf)
    if b is None or q is None:
        return None
    return round(b - q, 1)


def classify_relationship(abs_diff: float, t: RelationshipThresholds | None = None) -> dict:
    t = t or relationship_thresholds()
    if abs_diff >= t.strong_divergence:
        key = "STRONG_DIVERGENCE"
    elif abs_diff >= t.divergence:
        key = "DIVERGENCE"
    elif abs_diff >= t.moderate:
        key = "MODERATE"
    else:
        key = "BALANCED"
    return {"key": key, "label": RELATIONSHIP_LABELS[key]}


def classify_dynamics(diff: float, prev: float | None, t: RelationshipThresholds | None = None) -> dict:
    t = t or relationship_thresholds()
    if prev is None:
        key = "NO_HISTORY"
    elif prev * diff < 0 and max(abs(prev), abs(diff)) >= t.moderate:
        key = "REVERSING"
    elif abs(diff) - abs(prev) >= t.dynamics_epsilon:
        key = "EXPANDING"
    elif abs(prev) - abs(diff) >= t.dynamics_epsilon:
        key = "CONTRACTING"
    else:
        key = "STABLE"
    change = None if prev is None else round(diff - prev, 1)
    return {"key": key, "label": DYNAMICS_LABELS[key], "change": change, "previous": prev}


def timeframe_differentials(scores: Scores, base: str, quote: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for tf in ANALYSIS_TIMEFRAMES:
        d = differential(scores, base, quote, tf)
        if d is not None:
            out[tf] = d
    return out


def alignment(composite: float, by_tf: dict[str, float], t: RelationshipThresholds | None = None) -> dict:
    """How many timeframes point the same way as the composite (AVG) differential."""
    t = t or relationship_thresholds()
    direction = _sign(composite, t.alignment_epsilon)
    total = len(by_tf)
    aligned = sum(1 for d in by_tf.values() if direction and _sign(d, t.alignment_epsilon) == direction)
    pct = round(aligned / total * 100.0, 1) if total else 0.0
    if not total or direction == 0:
        key = "NEUTRAL"
    elif aligned / total >= t.aligned_ratio:
        key = "ALIGNED"
    elif aligned / total >= 0.5:
        key = "PARTIAL"
    else:
        key = "CONFLICTED"
    return {
        "key": key,
        "label": ALIGNMENT_LABELS[key],
        "aligned": aligned,
        "total": total,
        "pct": pct,
        "direction": {1: "BASE", -1: "QUOTE", 0: "NONE"}[direction],
    }


def pair_relationship(
    pair: str,
    scores: Scores,
    reference: Scores | None = None,
    t: RelationshipThresholds | None = None,
) -> dict | None:
    t = t or relationship_thresholds()
    base, quote = split_pair(pair)
    diff = differential(scores, base, quote, "AVG")
    if diff is None:
        return None
    b, q = scores[base]["AVG"], scores[quote]["AVG"]
    prev = differential(reference, base, quote, "AVG") if reference else None
    by_tf = timeframe_differentials(scores, base, quote)
    return {
        "pair": pair,
        "base": base,
        "quote": quote,
        "base_strength": b,
        "quote_strength": q,
        "base_class": classify(b),
        "quote_class": classify(q),
        "differential": diff,
        "abs_differential": abs(diff),
        "dominant": {1: "BASE", -1: "QUOTE", 0: "NONE"}[_sign(diff, t.alignment_epsilon)],
        "relationship": classify_relationship(abs(diff), t),
        "dynamics": classify_dynamics(diff, prev, t),
        "alignment": alignment(diff, by_tf, t),
        "timeframes": by_tf,
    }


def pair_relationships(scores: Scores, reference: Scores | None = None) -> list[dict]:
    """All 28 pairs ranked by absolute differential (strongest-versus-weakest first)."""
    t = relationship_thresholds()
    rows = [r for p in FX_PAIRS_28 if (r := pair_relationship(p, scores, reference, t)) is not None]
    rows.sort(key=lambda r: (-r["abs_differential"], r["pair"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows
