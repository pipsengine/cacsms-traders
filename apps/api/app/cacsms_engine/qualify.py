"""Pure qualification for an outlook scenario.

A qualified result is a candidate for the existing confirmation and risk gates.
This module does not submit, modify, or close a broker order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Horizon = Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "GOLD_H8"]
LIMITS = {"DAILY": 5, "WEEKLY": 2, "MONTHLY": 1, "QUARTERLY": 1}


@dataclass(frozen=True)
class OutlookSignal:
    outlook_id: str
    scenario_id: str
    version: int
    symbol: str
    horizon: Horizon
    score: float
    direction: str
    valid: bool
    stale: bool
    invalidated: bool


@dataclass(frozen=True)
class Decision:
    qualified: bool
    stage: str
    reason: str
    max_positions: int | None
    dedupe_key: str


def qualify(signal: OutlookSignal, *, min_score: float = 70) -> Decision:
    key = f"{signal.outlook_id}:{signal.scenario_id}:{signal.version}"
    cap = LIMITS.get(signal.horizon)  # GOLD_H8 uses the portfolio risk budget, not a count
    if signal.horizon == "GOLD_H8" and signal.symbol != "XAUUSD":
        return Decision(False, "BLOCKED", "H8 special strategy is XAUUSD-only", cap, key)
    if not 0 <= signal.score <= 100:
        return Decision(False, "BLOCKED", "Invalid evidence score", cap, key)
    if signal.stale or not signal.valid or signal.invalidated:
        return Decision(False, "MONITORING", "Stale, invalid or invalidated outlook", cap, key)
    if signal.direction not in ("BUY", "SELL"):
        return Decision(False, "MONITORING", "No tradable directional scenario", cap, key)
    if signal.score < min_score:
        return Decision(False, "MONITORING", "Evidence below threshold", cap, key)
    return Decision(True, "QUALIFICATION", "Candidate eligible for independent confirmation", cap, key)
