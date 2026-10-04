"""Central Market Scanner configuration: universe, analysis parameters, score weights and status thresholds.

Every group can be overridden with a comma-separated environment variable; invalid overrides fall back to
defaults. The scanner ranks instruments for inspection — it never issues trade direction or BUY/SELL.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .constants import FX_PAIRS_28

GOLD = "XAUUSD"
SCANNER_UNIVERSE: tuple[str, ...] = (GOLD, *FX_PAIRS_28)
# Timeframes the scanner keeps ingested for instruments outside the strength engine basket (XAUUSD).
EXTRA_INGEST_TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4", "H8", "D1", "W1", "MN")
# Timeframes the scanner ingests for every instrument because the strength engine does not maintain them.
UNIVERSE_INGEST_TIMEFRAMES = ("H4", "M30")
CHART_TIMEFRAMES = {
    "M5": "M5", "M15": "M15", "M30": "M30", "H1": "H1", "H4": "H4", "H8": "H8", "D1": "D1", "W": "W1", "MN": "MN",
}
STRUCTURE_TIMEFRAMES = ("W1", "D1", "H8", "H1")
DISPLAY_TF = {"W1": "W", "D1": "D1", "H8": "H8", "H1": "H1"}

INSTRUMENT_NAMES = {
    "AUD": "Australian Dollar",
    "CAD": "Canadian Dollar",
    "CHF": "Swiss Franc",
    "EUR": "Euro",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "NZD": "New Zealand Dollar",
    "USD": "US Dollar",
    "XAU": "Gold",
}


def _floats(name: str, default: tuple[float, ...]) -> tuple[float, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parts = tuple(float(x) for x in raw.split(","))
    except ValueError:
        return default
    return parts if len(parts) == len(default) and all(p >= 0 for p in parts) else default


@dataclass(frozen=True)
class ScannerSettings:
    high_inspection: float
    watching: float
    w_strength: float
    w_structure: float
    w_channel: float
    w_volatility: float
    w_alignment: float
    strength_full_scale: float
    channel_period: int
    channel_width_sd: float
    swing_strength: int
    atr_period: int
    atr_baseline: int
    vol_low: float
    vol_high: float
    min_d1_bars: int
    analysis_seconds: float
    quote_seconds: float
    persist_seconds: float


def settings() -> ScannerSettings:
    # SCANNER_STATUS_THRESHOLDS="high_inspection,watching" (0–100 score)
    hi, wa = _floats("SCANNER_STATUS_THRESHOLDS", (70.0, 55.0))
    if wa > hi:
        hi, wa = 70.0, 55.0
    # SCANNER_SCORE_WEIGHTS="strength,structure,channel,volatility,alignment"
    ws, wt, wc, wv, wa2 = _floats("SCANNER_SCORE_WEIGHTS", (35.0, 25.0, 20.0, 10.0, 10.0))
    # SCANNER_VOLATILITY_BANDS="low_ratio,high_ratio" (ATR14 / baseline mean true range)
    vl, vh = _floats("SCANNER_VOLATILITY_BANDS", (0.8, 1.25))
    # SCANNER_INTERVALS="analysis_seconds,quote_seconds,persist_seconds"
    an, qu, pe = _floats("SCANNER_INTERVALS", (60.0, 2.0, 300.0))
    return ScannerSettings(
        high_inspection=hi,
        watching=wa,
        w_strength=ws,
        w_structure=wt,
        w_channel=wc,
        w_volatility=wv,
        w_alignment=wa2,
        strength_full_scale=40.0,
        channel_period=50,
        channel_width_sd=2.0,
        swing_strength=2,
        atr_period=14,
        atr_baseline=100,
        vol_low=min(vl, vh),
        vol_high=max(vl, vh),
        min_d1_bars=60,
        analysis_seconds=max(10.0, an),
        quote_seconds=max(1.0, qu),
        persist_seconds=max(60.0, pe),
    )


def settings_payload() -> dict:
    s = settings()
    return {
        "status": [
            {"key": "HIGH_INSPECTION", "label": "High Inspection", "min": s.high_inspection},
            {"key": "WATCHING", "label": "Watching", "min": s.watching},
            {"key": "NEUTRAL", "label": "Neutral", "min": 0.0},
        ],
        "weights": {
            "strength": s.w_strength,
            "structure": s.w_structure,
            "channel": s.w_channel,
            "volatility": s.w_volatility,
            "alignment": s.w_alignment,
        },
        "channel_period": s.channel_period,
        "atr_period": s.atr_period,
        "volatility_bands": [s.vol_low, s.vol_high],
        "analysis_seconds": s.analysis_seconds,
        "quote_seconds": s.quote_seconds,
    }


def instrument_name(symbol: str) -> str:
    b, q = symbol[:3], symbol[3:6]
    return f"{INSTRUMENT_NAMES.get(b, b)} vs {INSTRUMENT_NAMES.get(q, q)}"
