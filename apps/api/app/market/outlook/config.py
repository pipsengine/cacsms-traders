from __future__ import annotations

import os
from dataclasses import dataclass, fields

ENGINE_VERSION = "ai-outlook-1.1.0"
OUTLOOK_TIMEFRAMES = ("Y", "YTD", "HY", "Q", "MN", "W", "D1", "H8", "H1", "M30")
REQUIRED_TIMEFRAMES = ("MN", "W1", "D1", "H8", "H1")
FRESHNESS_TIMEFRAMES = ("D1", "H8", "H1")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class OutlookSettings:
    close_grace_minutes: float
    min_probability: float
    min_margin: float
    min_reward_risk: float
    min_data_quality: float
    softmax_temperature: float
    calibration_strength: float
    near_level_atr: float
    erz_max_atr: float
    target_min_atr: float
    invalidation_max_atr: float
    replay_days: float
    replay_budget_seconds: float
    monitor_seconds: float
    lock_seconds: float
    max_attempts: float


def outlook_settings() -> OutlookSettings:
    """Thresholds are explicit and overridable (OUTLOOK_<FIELD>) — no hidden constants drive conclusions."""
    defaults = {
        "close_grace_minutes": 5.0,
        "min_probability": 55.0,
        "min_margin": 12.0,
        "min_reward_risk": 1.2,
        "min_data_quality": 70.0,
        "softmax_temperature": 1.25,
        "calibration_strength": 25.0,
        "near_level_atr": 1.6,
        "erz_max_atr": 0.6,
        "target_min_atr": 0.35,
        "invalidation_max_atr": 2.5,
        "replay_days": 30.0,
        "replay_budget_seconds": 8.0 if os.getenv("VERCEL", "").strip() == "1" else 25.0,
        "monitor_seconds": 60.0,
        "lock_seconds": 600.0,
        "max_attempts": 3.0,
    }
    return OutlookSettings(**{k: _float(f"OUTLOOK_{k.upper()}", v) for k, v in defaults.items()})


def settings_payload() -> dict:
    s = outlook_settings()
    return {f.name: getattr(s, f.name) for f in fields(s)}
