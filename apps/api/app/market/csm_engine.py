"""Currency Strength Matrix — EarnForex close-to-close methodology (ported from MQL5 CSM)."""
from __future__ import annotations

from dataclasses import dataclass, field
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
    pairs_loaded: int = 0
    missing_pairs: list[str] = field(default_factory=list)
    # True when the newest close is iClose(shift 0), the current bid, not the last closed bar.
    forming_close: bool = False


def split_pair(pair: str) -> tuple[str, str]:
    s = pair.upper().replace("/", "")
    if len(s) >= 6:
        return s[:3], s[3:6]
    raise ValueError(f"Not a supported FX pair: {pair}")


def is_base_currency(currency: str, pair: str) -> bool:
    base, quote = split_pair(pair)
    return currency.upper() == base


def pct_change(start: float, end: float) -> float | None:
    """EarnForex: (end - start) * 100 / start, or the plain difference when start is 0."""
    if start == 0:
        return end - start
    return (end - start) * 100.0 / start


def _closed_endpoints(
    closes: Sequence[float], bars_difference: int
) -> tuple[float | None, float | None]:
    """EarnForex iClose indexing: last element is shift 0, the element `bars_difference` before it is the start.

    Shift 0 is the current bid when the caller has appended a forming close. Without that append the
    last element is the latest stored bar, which is one bar behind the indicator.
    """
    need = bars_difference + 1
    if len(closes) < need:
        return None, None
    end = closes[-1]
    start = closes[-1 - bars_difference]
    return start, end


def stamp_forming_bids(
    anchors: Mapping[str, Mapping[str, Sequence[float]]],
    bids: Mapping[str, float],
) -> dict[str, dict[str, list[float]]]:
    """Previous-bar closes plus the current bid as iClose(shift 0)."""
    out: dict[str, dict[str, list[float]]] = {}
    for tf, pairs in anchors.items():
        framed: dict[str, list[float]] = {}
        for pair, hist in pairs.items():
            bid = bids.get(pair)
            if not hist or bid is None or float(bid) <= 0:
                continue
            framed[pair] = [float(c) for c in hist] + [float(bid)]
        if framed:
            out[tf] = framed
    return out


def apply_live_endpoints(
    pair_closes_by_tf: Mapping[str, Mapping[str, Sequence[float]]],
    endpoints: Mapping[str, Mapping[str, Sequence[float]]],
) -> dict[str, dict[str, list[float]]]:
    """Replace a timeframe's closes with broker bars that already include iClose(shift 0)."""
    out: dict[str, dict[str, list[float]]] = {tf: {p: list(c) for p, c in pairs.items()} for tf, pairs in pair_closes_by_tf.items()}
    for tf, pairs in endpoints.items():
        bucket = out.setdefault(tf, {})
        for pair, closes in pairs.items():
            series = [float(c) for c in closes if c and float(c) > 0]
            if len(series) >= 2:
                bucket[pair] = series
    return out


def overlay_forming_closes(
    pair_closes_by_tf: Mapping[str, Mapping[str, Sequence[float]]],
    bids: Mapping[str, float],
    *,
    synthetic: frozenset[str] = frozenset({"YTD", "Q"}),
) -> dict[str, dict[str, list[float]]]:
    """Match PopulateMatrixCell: EndValue = iClose(shift 0) = current bid, StartValue = iClose(BarsDifference).

    Native series are closed bars oldest → newest, so appending the bid makes shift 0 the live price and
    shift 1 the previous close. YTD/Q stay a window from the anchor close to that same live price.
    """
    out: dict[str, dict[str, list[float]]] = {}
    for tf, pairs in pair_closes_by_tf.items():
        framed: dict[str, list[float]] = {}
        for pair, closes in pairs.items():
            series = [float(c) for c in closes]
            bid = bids.get(pair)
            if bid is None or bid <= 0 or not series:
                framed[pair] = series
                continue
            if tf in synthetic:
                framed[pair] = [series[0], float(bid)]
            else:
                framed[pair] = [*series, float(bid)]
        out[tf] = framed
    return out


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
    # EarnForex sums unrounded contributions and only NormalizeDouble(Total, 4)s the cell.
    return round(diff, 10)


def populate_matrix_cell(
    currency: str,
    pair_closes: Mapping[str, Sequence[float]],
    bars_difference: int = 1,
    *,
    timeframe: str = "UNKNOWN",
) -> tuple[float, int, list[MissingHistory]]:
    total = 0.0
    used = 0
    missing: list[MissingHistory] = []
    for pair in FX_PAIRS_28:
        if currency not in pair:
            continue
        closes = pair_closes.get(pair)
        if not closes:
            missing.append(MissingHistory(pair, timeframe))
            continue
        start, end = _closed_endpoints(closes, bars_difference)
        if start is None or end is None:
            missing.append(MissingHistory(pair, timeframe))
            continue
        contrib = pair_contribution(currency, pair, start, end)
        if contrib is None:
            missing.append(MissingHistory(pair, timeframe))
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


def compute_avg(
    values: Mapping[str, float],
    quality: Mapping[str, str],
    timeframes: Sequence[str],
) -> float:
    nums: list[float] = []
    for tf in timeframes:
        if tf == "AVG":
            continue
        q = quality.get(tf, "MISSING")
        if q not in ("FRESH", "PARTIAL"):
            continue
        if tf in values:
            nums.append(float(values[tf]))
    return round(sum(nums) / len(nums), 4) if nums else 0.0


def avg_quality(quality: Mapping[str, str], timeframes: Sequence[str]) -> str:
    good = [quality.get(tf, "MISSING") for tf in timeframes if tf != "AVG"]
    fresh = sum(1 for q in good if q == "FRESH")
    partial = sum(1 for q in good if q == "PARTIAL")
    if fresh >= 7:
        return "FRESH"
    if fresh + partial >= 5:
        return "PARTIAL"
    if fresh + partial > 0:
        return "PARTIAL"
    return "MISSING"


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
            cell, used, missing = populate_matrix_cell(currency, tf_pairs, bars_difference, timeframe=tf)
            values[currency][tf] = cell
            sample_counts[currency][tf] = used
            if used >= 7:
                quality[currency][tf] = "FRESH"
            elif used > 0:
                quality[currency][tf] = "PARTIAL"
                historical_ok = False
                all_missing.extend(missing)
            else:
                quality[currency][tf] = "MISSING"
                historical_ok = False
                all_missing.extend(missing)

    for currency in CSM_CURRENCIES:
        avg = compute_avg(values[currency], quality[currency], native_tfs)
        values[currency]["AVG"] = avg
        quality[currency]["AVG"] = avg_quality(quality[currency], native_tfs)

    return CsmMatrixResult(values, quality, sample_counts, all_missing, historical_ok, as_of)


def sort_currencies_by(values: dict[str, dict[str, float]], sort_by: str) -> list[str]:
    from .constants import normalize_matrix_timeframe

    key = normalize_matrix_timeframe(sort_by if sort_by != "CURRENT" else "AVG")
    scored = [(c, values.get(c, {}).get(key, float("-inf"))) for c in CSM_CURRENCIES]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored]


def consensus_action(consensus: int) -> str:
    if consensus == 1:
        return "B"
    if consensus == -1:
        return "S"
    return "W"


def _pair_base_quote(pair: str) -> tuple[str, str]:
    base, quote = split_pair(pair)
    return base, quote


def possible_setup(
    values: dict[str, dict[str, float]],
    sorted_currencies: Sequence[str],
    matrix_timeframes: Sequence[str],
) -> dict[str, str | None]:
    """EarnForex PossibleSetup — ideal pair hint for the matrix footer."""
    from .constants import FX_PAIRS_28

    ideal_buy_ccy = ""
    ideal_sell_ccy = ""
    for c in sorted_currencies:
        if populate_matrix_row_consensus(values[c], matrix_timeframes) == 1:
            ideal_buy_ccy = c
            break
    for c in reversed(sorted_currencies):
        if populate_matrix_row_consensus(values[c], matrix_timeframes) == -1:
            ideal_sell_ccy = c
            break
    if not ideal_buy_ccy or not ideal_sell_ccy:
        return {"ideal_action": "WAIT A BETTER SETUP", "ideal_pair": None, "direction": None}

    pair = ""
    for p in FX_PAIRS_28:
        if ideal_buy_ccy in p and ideal_sell_ccy in p:
            pair = p
            break
    if not pair:
        return {"ideal_action": "WAIT A BETTER SETUP", "ideal_pair": None, "direction": None}

    base, quote = _pair_base_quote(pair)
    direction = None
    label = "WAIT A BETTER SETUP"
    if base == ideal_buy_ccy and quote == ideal_sell_ccy:
        direction = "LONG"
        label = f"POSSIBLE BUY {pair}"
    elif base == ideal_sell_ccy and quote == ideal_buy_ccy:
        direction = "SHORT"
        label = f"POSSIBLE SELL {pair}"
    return {"ideal_action": label, "ideal_pair": pair or None, "direction": direction}
