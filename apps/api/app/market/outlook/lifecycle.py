"""Scenario lifecycle for a published outlook.

The original analysis stays immutable. These states describe what closed bars have done since that close.
AUTHORIZED is never produced here — Stage 8 risk approval stays with the autonomous engine.
"""
from __future__ import annotations

from datetime import datetime

PROGRESS = (
    "PUBLISHED",
    "WATCHING",
    "APPROACHING_ZONE",
    "ZONE_REACHED",
    "REACTION_PENDING",
    "CONFIRMATION_PENDING",
    "CONFIRMED",
    "AUTHORIZATION_PENDING",
    "AUTHORIZED",
)
TERMINAL = ("INVALIDATED", "EXPIRED", "COMPLETED", "NO_OPPORTUNITY")


def lifecycle_for(outlook: dict, monitor_result: dict, now: datetime, expires_at: datetime | None = None, *, m15_confirmed: bool = False) -> str:
    """Map closed-bar monitoring onto the scenario lifecycle. Does not authorise a trade."""
    if not outlook.get("qualified"):
        return "NO_OPPORTUNITY"
    status = monitor_result.get("status")
    steps = monitor_result.get("steps") or []
    keys = {s["key"] for s in steps if s.get("done")}
    action = (monitor_result.get("system_action") or {}).get("key")
    if status == "INVALIDATED":
        return "INVALIDATED"
    if {"T1", "T2"} & keys:
        return "COMPLETED"
    horizon = outlook.get("horizon") or "DAILY"
    h1_ready = action == "AUTHORIZE"
    if horizon == "H8":
        if h1_ready and m15_confirmed:
            return "AUTHORIZATION_PENDING"
        if m15_confirmed or "BOS" in keys:
            return "CONFIRMATION_PENDING"
    elif h1_ready:
        return "AUTHORIZATION_PENDING"
    if expires_at is not None and now >= expires_at:
        return "EXPIRED"
    if "BOS" in keys:
        return "CONFIRMATION_PENDING"
    if {"REACTION", "EXHAUSTION"} & keys:
        return "REACTION_PENDING"
    erz = outlook.get("erz") or {}
    if erz.get("price_inside"):
        return "ZONE_REACHED"
    distance = erz.get("distance_atr")
    if distance is not None and distance <= 0.6:
        return "APPROACHING_ZONE"
    return "WATCHING"
