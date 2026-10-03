"""MT5 built-in indicator ports used by the EarnForex CSM non-close modes.

Defaults mirror the MQL5 indicator inputs: MA(2, EMA, close), RSI(14, close), RSI MA = EMA(2) over RSI,
Stochastic(5, 3, 3, EMA, close/close). Series are oldest → newest; None where not yet defined.
"""
from __future__ import annotations

from typing import Sequence

MA_PERIOD = 2
RSI_PERIOD = 14
STOCH_K = 5
STOCH_D = 3
STOCH_SLOWING = 3

Series = list[float | None]


def ema(values: Sequence[float | None], period: int) -> Series:
    """MT5 EMA: seeded with the first defined value, then price*k + prev*(1-k)."""
    k = 2.0 / (period + 1.0)
    out: Series = []
    prev: float | None = None
    for v in values:
        if v is None:
            out.append(None)
            continue
        prev = v if prev is None else v * k + prev * (1.0 - k)
        out.append(prev)
    return out


def rsi(closes: Sequence[float], period: int = RSI_PERIOD) -> Series:
    """MT5 iRSI: simple average of the first `period` moves, then Wilder smoothing."""
    out: Series = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    pos, neg = gains / period, losses / period

    def value(p: float, n: float) -> float:
        return 100.0 if n == 0 else 100.0 - 100.0 / (1.0 + p / n)

    out[period] = value(pos, neg)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        pos = (pos * (period - 1) + max(d, 0.0)) / period
        neg = (neg * (period - 1) + max(-d, 0.0)) / period
        out[i] = value(pos, neg)
    return out


def stochastic_close(
    closes: Sequence[float], k: int = STOCH_K, d: int = STOCH_D, slowing: int = STOCH_SLOWING
) -> tuple[Series, Series]:
    """MT5 iStochastic with STO_CLOSECLOSE: %K uses close highs/lows, slowing is a ratio of sums,
    the signal line is an EMA(d) of the main line."""
    n = len(closes)
    lows: Series = [None] * n
    highs: Series = [None] * n
    for i in range(k - 1, n):
        window = closes[i - k + 1 : i + 1]
        lows[i], highs[i] = min(window), max(window)
    main: Series = [None] * n
    for i in range(k - 1 + slowing - 1, n):
        num = den = 0.0
        for j in range(i - slowing + 1, i + 1):
            num += closes[j] - lows[j]  # type: ignore[operator]
            den += highs[j] - lows[j]  # type: ignore[operator]
        main[i] = 100.0 if den == 0 else num / den * 100.0
    return main, ema(main, d)


def mode_series(mode: str, closes: Sequence[float]) -> Series:
    if mode == "MA":
        return ema(closes, MA_PERIOD)
    if mode == "RSI":
        return rsi(closes)
    if mode == "RSI_MA":
        return ema(rsi(closes), MA_PERIOD)
    if mode == "STOCH_MAIN":
        return stochastic_close(closes)[0]
    if mode == "STOCH_SIGNAL":
        return stochastic_close(closes)[1]
    return list(closes)
