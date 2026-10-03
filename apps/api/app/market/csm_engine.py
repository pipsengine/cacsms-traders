"""Currency Strength Matrix — EarnForex close-to-close methodology (ported from MQL5 CSM)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping, Sequence

from .constants import CSM_CURRENCIES, FX_PAIRS_28


class CalculationMode(str, Enum):
    CLOSE_CLOSE = "CLOSE_CLOSE"
    MA = "MA"
    RSI = "RSI"
    RSI_MA = "RSI_MA"
    STOCH_MAIN = "STOCH_MAIN"
    STOCH_SIGNAL = "STOCH_SIGNAL"


@dataclass(frozen=True)
class MissingHistory:
    symbol: str
    timeframe: str


@dataclass
class CsmMatrixResult:
    values: dict[str, dict[str, float]]
    quality: dict[str, dict[str, str]]
    sample_counts: dict[str, dict[str, int]]
    missing: list[MissingHistory]
    historical_ok: bool
    as_of: datetime


def split_pair(pair: str) -> tuple[str, str]:
    s = pair.upper().replace("/", "")
    if len(s) >= 6:
        return s[:3], s[3:6]
    raise ValueError(f"Not a supported FX pair: {pair}")


def is_base_currency(currency: str, pair: str) -> bool:
    base, quote = split_pair(pair)
    return currency.upper() == base


def pct_change(start: float, end: float) -> float | None:
    if start == 0 or end == 0:
        return None
    return (end - start) * 100.0 / start


def _closed_endpoints(
    closes: Sequence[float], bars_difference: int
) -> tuple[float | None, float | None]:
    """Latest closed bar is the last element; never use an in-progress bar (caller must exclude it)."""
    need = bars_difference + 1
    if len(closes) < need:
        return None, None
    end = closes[-1]
    start = closes[-1 - bars_difference]
    return start, end


def pair_contribution(
    currency: str,
    pair: str,
    start: float,
    end: float,
) -> float | None:
    diff = pct_change(start, end)
    if diff is None:
        return None
    if not is_base_currency(currency, pair):
        diff = -diff
    return round(diff, 4)


def populate_matrix_cell(
    currency: str,
    pair_closes: Mapping[str, Sequence[float]],
    bars_difference: int = 1,
) -> tuple[float, int, list[MissingHistory]]:
    total = 0.0
    used = 0
    missing: list[MissingHistory] = []
    for pair in FX_PAIRS_28:
        if currency not in pair:
            continue
        closes = pair_closes.get(pair)
        if not closes:
            missing.append(MissingHistory(pair, "UNKNOWN"))
            continue
        start, end = _closed_endpoints(closes, bars_difference)
        if start is None or end is None:
            missing.append(MissingHistory(pair, "UNKNOWN"))
            continue
        contrib = pair_contribution(currency, pair, start, end)
        if contrib is None:
            missing.append(MissingHistory(pair, "UNKNOWN"))
            continue
        total += contrib
        used += 1
    return round(total, 4), used, missing


def populate_matrix_row_consensus(values: Mapping[str, float], timeframes: Sequence[str]) -> int:
    """MQL consensus column: +1 all positive, -1 all negative, else 0."""
    score = 0
    count = 0
    for tf in timeframes:
        if tf == "AVG":
            continue
        v = values.get(tf)
        if v is None:
            continue
        count += 1
        if v > 0:
            score += 1
        elif v < 0:
            score -= 1
    if count and score == count:
        return 1
    if count and score == -count:
        return -1
    return 0


def compute_avg(values: Mapping[str, float], timeframes: Sequence[str]) -> float:
    nums = [values[tf] for tf in timeframes if tf != "AVG" and tf in values]
    return round(sum(nums) / len(nums), 4) if nums else 0.0


def compute_matrix(
    timeframes: Sequence[str],
    pair_closes_by_tf: Mapping[str, Mapping[str, Sequence[float]]],
    *,
    bars_difference: int = 1,
    as_of: datetime,
) -> CsmMatrixResult:
    values: dict[str, dict[str, float]] = {c: {} for c in CSM_CURRENCIES}
    quality: dict[str, dict[str, str]] = {c: {} for c in CSM_CURRENCIES}
    sample_counts: dict[str, dict[str, int]] = {c: {} for c in CSM_CURRENCIES}
    all_missing: list[MissingHistory] = []
    historical_ok = True

    native_tfs = [t for t in timeframes if t not in ("AVG",)]

    for tf in native_tfs:
        tf_pairs = pair_closes_by_tf.get(tf, {})
        for currency in CSM_CURRENCIES:
            cell, used, missing = populate_matrix_cell(currency, tf_pairs, bars_difference)
            values[currency][tf] = cell
            sample_counts[currency][tf] = used
            if used < 7:
                quality[currency][tf] = "MISSING"
                historical_ok = False
                all_missing.extend(missing)
            else:
                quality[currency][tf] = "FRESH"

    for currency in CSM_CURRENCIES:
        avg = compute_avg(values[currency], native_tfs)
        values[currency]["AVG"] = avg
        qcells = [quality[currency].get(tf, "MISSING") for tf in native_tfs]
        quality[currency]["AVG"] = "FRESH" if qcells and all(q == "FRESH" for q in qcells) else "MISSING"

    return CsmMatrixResult(values, quality, sample_counts, all_missing, historical_ok, as_of)


def sort_currencies_by(values: dict[str, dict[str, float]], sort_by: str) -> list[str]:
    key = sort_by if sort_by != "CURRENT" else "AVG"
    scored = [(c, values.get(c, {}).get(key, float("-inf"))) for c in CSM_CURRENCIES]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]
