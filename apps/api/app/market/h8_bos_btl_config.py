"""Central H8 BOS & BTL Intelligence configuration.

Every group can be overridden with a comma-separated environment variable; invalid overrides fall back to
defaults. The page is an analysis surface — it never issues trade direction or BUY/SELL.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .scanner_config import _floats

ALERT_KINDS = ("BOS + BTL", "BOS", "BTL", "DEVELOPING", "MONITORING")
ALERT_PRIORITY = {k: i for i, k in enumerate(ALERT_KINDS)}
SCH_METHODS = ("SCHAFF", "STOCHASTIC")


@dataclass(frozen=True)
class H8BosBtlSettings:
    # Weekly context
    w_fractal_strength: int
    sch_method: str
    sch_fast: int
    sch_slow: int
    sch_cycle: int
    sch_signal: int
    # H8 structure
    h8_swing_strength: int
    btl_tolerance_atr: float
    bos_tolerance_atr: float
    active_bars: int
    composite_bars: int
    retest_pad_atr: float
    # Downstream confirmation
    h1_swing_strength: int
    m30_swing_strength: int
    atr_period: int = 14


def h8_bos_btl_settings() -> H8BosBtlSettings:
    # H8BB_WEEKLY="fractal_strength,sch_fast,sch_slow,sch_cycle,sch_signal"
    wf, sf, ss, sc, sg = _floats("H8BB_WEEKLY", (2.0, 23.0, 50.0, 10.0, 3.0))
    # H8BB_H8="swing_strength,btl_tolerance_atr,bos_tolerance_atr,active_bars,composite_bars,retest_pad_atr"
    hs, bt, bo, ab, cb, rp = _floats("H8BB_H8", (3.0, 0.1, 0.0, 12.0, 6.0, 0.15))
    # H8BB_LTF="h1_swing_strength,m30_swing_strength"
    h1s, m30s = _floats("H8BB_LTF", (2.0, 2.0))
    # H8BB_SCH_METHOD=SCHAFF|STOCHASTIC (STOCHASTIC uses sch_cycle as %K length, sch_signal as %D)
    method = os.getenv("H8BB_SCH_METHOD", "SCHAFF").strip().upper()
    return H8BosBtlSettings(
        w_fractal_strength=max(1, int(wf)),
        sch_method=method if method in SCH_METHODS else "SCHAFF",
        sch_fast=max(2, int(sf)),
        sch_slow=max(int(sf) + 1, int(ss)),
        sch_cycle=max(2, int(sc)),
        sch_signal=max(1, int(sg)),
        h8_swing_strength=max(1, int(hs)),
        btl_tolerance_atr=max(0.0, bt),
        bos_tolerance_atr=max(0.0, bo),
        active_bars=max(1, int(ab)),
        composite_bars=max(0, int(cb)),
        retest_pad_atr=max(0.0, rp),
        h1_swing_strength=max(1, int(h1s)),
        m30_swing_strength=max(1, int(m30s)),
    )


def h8_bos_btl_settings_payload() -> dict:
    s = h8_bos_btl_settings()
    return {
        "w_fractal_strength": s.w_fractal_strength,
        "sch_method": s.sch_method,
        "sch": {"fast": s.sch_fast, "slow": s.sch_slow, "cycle": s.sch_cycle, "signal": s.sch_signal},
        "h8_swing_strength": s.h8_swing_strength,
        "btl_tolerance_atr": s.btl_tolerance_atr,
        "bos_tolerance_atr": s.bos_tolerance_atr,
        "active_bars": s.active_bars,
        "composite_bars": s.composite_bars,
        "retest_pad_atr": s.retest_pad_atr,
        "h1_swing_strength": s.h1_swing_strength,
        "m30_swing_strength": s.m30_swing_strength,
        "atr_period": s.atr_period,
    }
