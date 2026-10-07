"""Autonomous engine settings and the 11-stage catalogue (AE_* environment overrides)."""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from datetime import timedelta

ENGINE_VERSION = "ae-1.0.0"
LOCK_NAME = "autonomous-engine"

# key, number, label, colour (the UI colour-codes each stage card by this key)
STAGES = (
    ("MARKET_DATA", 1, "Market Data", "#2563eb"),
    ("INTELLIGENCE", 2, "Market Intelligence", "#7c3aed"),
    ("SCANNER", 3, "Scanner", "#0891b2"),
    ("STRUCTURE", 4, "Structure", "#4f46e5"),
    ("CHANNEL", 5, "Channel Intelligence", "#0d9488"),
    ("OPPORTUNITY", 6, "Opportunity", "#d97706"),
    ("CONFIRMATION", 7, "Confirmation", "#ca8a04"),
    ("RISK", 8, "Risk & Portfolio", "#dc2626"),
    ("EXECUTION", 9, "Execution", "#475569"),
    ("MANAGEMENT", 10, "Position Management", "#0f766e"),
    ("LEARNING", 11, "Performance & Learning", "#9333ea"),
)
STAGE_KEYS = tuple(s[0] for s in STAGES)

OPP_TYPES = {
    "P1_RETRACEMENT": "P1 Retracement",
    "P2_BREAKOUT_RETEST": "P2 Breakout Retest",
    "CONTINUATION": "Continuation",
    "TIT": "Trend-in-Trend",
}
# Opportunity states per stage (the vocabulary the transition audit trail uses).
OPP_STATES = {
    "OPPORTUNITY": ("WAITING_FOR_ZONE",),
    "CONFIRMATION": ("AWAITING_REACTION", "REACTION_CONFIRMED"),
    "RISK": ("RISK_REVIEW", "RISK_DEFERRED"),
    "EXECUTION": ("EXECUTION_BLOCKED_ANALYSIS_ONLY",),
    "LEARNING": ("INVALIDATED", "EXPIRED", "RISK_REJECTED", "COMPLETED"),
}
CHANNEL_STATES = ("FORMING", "ACTIVE", "MATURE", "TOUCHED", "BREAKING", "BROKEN", "RETESTING", "CONTINUING",
                  "INVALIDATED", "EXPIRED")
CHANNEL_TERMINAL = ("INVALIDATED", "EXPIRED")
TF_DELTA = {"W": timedelta(days=7), "D1": timedelta(days=1), "H8": timedelta(hours=8), "H1": timedelta(hours=1)}
WORKERS = {
    "autonomous-engine": "Autonomous Engine",
    "market-scanner": "Market Scanner",
    "strength-engine": "Strength Engine",
    "notification-worker": "Notification Worker",
}


@dataclass(frozen=True)
class AESettings:
    cycle_seconds: float = 30.0          # worker cadence (each cycle is cheap when no new closed bar arrived)
    lock_seconds: float = 180.0          # lease length; a crashed worker's lease expires and another resumes
    on_demand_seconds: float = 45.0      # serverless: minimum spacing between request-driven cycles
    recovery_after_seconds: float = 600.0  # gap since the last completed cycle that marks a RECOVERY replay
    stale_cycle_seconds: float = 300.0   # scanner analysis older than this (market open) is stale
    worker_stale_seconds: float = 180.0  # heartbeat age that marks a worker offline
    zone_wait_bars: int = 48             # trigger-TF bars an opportunity may wait for its entry zone
    confirm_bars: int = 24               # H1 bars allowed from zone entry to confirmation
    risk_defer_bars: int = 24            # H1 bars a confirmed opportunity may stay deferred by portfolio limits
    shadow_bars: int = 240               # H1 bars an analysis-only (blocked) plan is tracked for its outcome
    rearm_bars: int = 12                 # trigger-TF bars before a closed family may produce a new opportunity
    max_breakout_age_bars: int = 30      # P2: breakouts older than this are history, not opportunities
    min_reward_risk: float = 1.5
    min_confidence: float = 50.0
    max_concurrent: int = 6
    max_currency_exposure: int = 2
    max_replay_bars: int = 720           # bound one recovery pass (the next cycle continues from the watermark)


def _env(name: str, default):
    raw = os.getenv(f"AE_{name.upper()}", "").strip()
    if not raw:
        return default
    try:
        return type(default)(float(raw)) if isinstance(default, int) else float(raw)
    except ValueError:
        return default


def ae_settings() -> AESettings:
    return AESettings(**{f.name: _env(f.name, f.default) for f in fields(AESettings)})


def settings_payload() -> dict:
    s = ae_settings()
    return {f.name: getattr(s, f.name) for f in fields(AESettings)}


def enabled() -> bool:
    return os.getenv("AUTONOMOUS_ENGINE_ENABLED", "1").strip().lower() not in ("0", "false", "no")
