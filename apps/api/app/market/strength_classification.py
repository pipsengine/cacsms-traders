"""Central strength classification thresholds (0–100 score scale).

Override with STRENGTH_CLASS_THRESHOLDS="strong,moderate,neutral,weak" (lower bounds, descending).
"""
from __future__ import annotations

import os

_DEFAULT_BOUNDS = (60.0, 52.0, 48.0, 40.0)
_CLASSES = (
    ("STRONG", "Strong", "positive"),
    ("MODERATE", "Moderate", "positive"),
    ("NEUTRAL", "Neutral", "neutral"),
    ("WEAK", "Weak", "negative"),
    ("VERY_WEAK", "Very Weak", "negative"),
)


def thresholds() -> tuple[float, float, float, float]:
    raw = os.getenv("STRENGTH_CLASS_THRESHOLDS", "").strip()
    if raw:
        try:
            parts = tuple(float(x) for x in raw.split(","))
            if len(parts) == 4 and list(parts) == sorted(parts, reverse=True):
                return parts  # type: ignore[return-value]
        except ValueError:
            pass
    return _DEFAULT_BOUNDS


def classify(score: float) -> dict:
    bounds = thresholds()
    for i, lower in enumerate(bounds):
        if score >= lower:
            key, label, tone = _CLASSES[i]
            return {"key": key, "label": label, "tone": tone}
    key, label, tone = _CLASSES[-1]
    return {"key": key, "label": label, "tone": tone}


def thresholds_payload() -> list[dict]:
    bounds = thresholds()
    out = []
    for i, (key, label, tone) in enumerate(_CLASSES):
        out.append({"key": key, "label": label, "tone": tone, "min": bounds[i] if i < len(bounds) else 0.0})
    return out
