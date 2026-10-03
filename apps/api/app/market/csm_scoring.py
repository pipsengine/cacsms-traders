"""Map raw CSM deltas (EarnForex % change sums) to 0–100 strength scores.

Per timeframe column the raw value is scaled by the column's RMS and squashed with tanh around 0,
so the score keeps the EarnForex sign: raw > 0 → score > 50 (green), raw < 0 → score < 50 (red),
and ordering within a column is identical to the raw values. AVG is the mean of a currency's
available timeframe scores.
"""
from __future__ import annotations

import math

from .constants import CSM_CURRENCIES

SCORABLE = ("FRESH", "PARTIAL")
TANH_SPREAD = 1.5


def normalize_column_scores(
    values: dict[str, dict[str, float]],
    quality: dict[str, dict[str, str]],
    timeframe: str,
) -> dict[str, float]:
    present = [
        c for c in CSM_CURRENCIES if quality.get(c, {}).get(timeframe, "MISSING") in SCORABLE
    ]
    if not present:
        return {}
    nums = [float(values[c].get(timeframe, 0.0)) for c in present]
    rms = math.sqrt(sum(v * v for v in nums) / len(nums))
    out: dict[str, float] = {}
    for c, v in zip(present, nums):
        out[c] = 50.0 if rms == 0 else round(50.0 + 50.0 * math.tanh(v / (rms * TANH_SPREAD)), 1)
    return out


def normalize_all_scores(
    values: dict[str, dict[str, float]],
    timeframes: tuple[str, ...],
    quality: dict[str, dict[str, str]],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {c: {} for c in CSM_CURRENCIES}
    native = [tf for tf in timeframes if tf != "AVG"]
    for tf in native:
        for c, s in normalize_column_scores(values, quality, tf).items():
            scores[c][tf] = s
    if "AVG" in timeframes:
        for c in CSM_CURRENCIES:
            parts = [scores[c][tf] for tf in native if tf in scores[c]]
            if parts:
                scores[c]["AVG"] = round(sum(parts) / len(parts), 1)
    return scores
