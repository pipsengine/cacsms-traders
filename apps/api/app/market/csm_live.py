"""Live EarnForex CSM inputs read straight from MT5 rates.

Mirrors the MQL5 indicator: for each pair/timeframe the cell compares iClose(pair, tf, BarsDifference)
with iClose(pair, tf, 0) — the current (forming) bar's close, i.e. the latest price. Set
STRENGTH_BAR_BASIS=closed to compare the last two closed bars instead (shift BarsDifference+1 → 1).
"""
from __future__ import annotations

import os
import time
from datetime import datetime

from .constants import FX_PAIRS_28, MATRIX_TIMEFRAMES, SYNTHETIC_MATRIX_TIMEFRAMES
from .csm_indicators import mode_series
from .csm_windows import rolling_quarter_start, window_closes, year_start
from .mt5_contract import MarketDataUnavailable

D1_HISTORY_BARS = 400
# Enough bars for MT5's EMA/RSI recursion to converge to the terminal's values at 4 decimals.
# Oversized requests on short-history timeframes block inside the MT5 library, so W/MN are capped.
INDICATOR_BARS = {"MN": 100, "W": 250}
DEFAULT_INDICATOR_BARS = 300
D1_REFRESH_SECONDS = 60.0


def bar_basis() -> str:
    return "closed" if os.getenv("STRENGTH_BAR_BASIS", "earnforex").strip().lower() == "closed" else "earnforex"


class LiveCsmSource:
    def __init__(self, gateway):
        self.gw = gateway
        self._d1: dict[str, list[tuple[datetime, float]]] = {}
        self._d1_at = 0.0

    def _refresh_d1(self) -> None:
        if self._d1 and time.monotonic() - self._d1_at < D1_REFRESH_SECONDS:
            return
        d1: dict[str, list[tuple[datetime, float]]] = {}
        for pair in FX_PAIRS_28:
            try:
                d1[pair] = self.gw.current_closes(pair, "D1", D1_HISTORY_BARS)
            except MarketDataUnavailable:
                continue
        self._d1 = d1
        self._d1_at = time.monotonic()

    def pair_closes_by_tf(self, as_of: datetime, bars_difference: int = 1) -> dict[str, dict[str, list[float]]]:
        """{timeframe: {pair: [close@start, ..., close@end]}} in compute_matrix's oldest → newest order."""
        return self.inputs_by_mode(as_of, ("CLOSE_CLOSE",), bars_difference)["CLOSE_CLOSE"]

    def inputs_by_mode(
        self, as_of: datetime, modes: tuple[str, ...], bars_difference: int = 1
    ) -> dict[str, dict[str, dict[str, list[float]]]]:
        """{mode: {timeframe: {pair: [value@BarsDifference, ..., value@0]}}} from one MT5 read per pair/tf."""
        closed = bar_basis() == "closed"
        need = bars_difference + 1
        indicator_modes = [m for m in modes if m != "CLOSE_CLOSE"]
        out = {m: {tf: {} for tf in MATRIX_TIMEFRAMES} for m in modes}
        for tf in MATRIX_TIMEFRAMES:
            if tf in SYNTHETIC_MATRIX_TIMEFRAMES:
                continue
            history = INDICATOR_BARS.get(tf, DEFAULT_INDICATOR_BARS) if indicator_modes else need
            count = history + (1 if closed else 0)
            for pair in FX_PAIRS_28:
                try:
                    rows = self.gw.current_closes(pair, tf, count)
                except MarketDataUnavailable:
                    continue
                closes = [c for _, c in rows]
                if closed:
                    closes = closes[:-1]
                if len(closes) < need:
                    continue
                if "CLOSE_CLOSE" in out:
                    out["CLOSE_CLOSE"][tf][pair] = closes[-need:]
                for mode in indicator_modes:
                    tail = mode_series(mode, closes)[-need:]
                    if all(v is not None for v in tail):
                        out[mode][tf][pair] = tail  # type: ignore[assignment]

        if "CLOSE_CLOSE" not in out:
            return out
        out["CLOSE_CLOSE"].update(self._ytd_q(as_of, closed))
        return out

    def _ytd_q(self, as_of: datetime, closed: bool) -> dict[str, dict[str, list[float]]]:
        out: dict[str, dict[str, list[float]]] = {"YTD": {}, "Q": {}}
        self._refresh_d1()
        ys, qs = year_start(as_of), rolling_quarter_start(as_of)
        for pair, rows in self._d1.items():
            series = rows[:-1] if closed else rows
            for tf, start in (("YTD", ys), ("Q", qs)):
                s, e = window_closes(series, start)
                if s is not None and e is not None:
                    out[tf][pair] = [s, e]
        return out
