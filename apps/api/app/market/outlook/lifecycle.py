"""Scenario lifecycle for a published outlook.

The original analysis stays immutable. These states describe what closed bars have done since that close.
AUTHORIZED is never produced here — Stage 8 risk approval stays with the autonomous engine.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


def _send_on_reaction() -> bool:
    """When enabled, ERZ reaction alone may hand off to execution (default on for autonomous outlook trading)."""
    return os.getenv("OUTLOOK_SEND_ON_REACTION", "1").strip().lower() not in ("0", "false", "no")

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


def promote_reaction_handoffs(conn, tenant: str, account: str) -> int:
    """Upgrade stale REACTION_PENDING rows when ERZ reaction is already confirmed (e.g. after rule or weekend monitor gap)."""
    if not _send_on_reaction():
        return 0
    import json

    from ..provenance import values

    rows = conn.execute(
        "SELECT outlook_id, evidence_json FROM ai_outlook_handoff "
        "WHERE tenant_id=? AND trading_account_id=? AND lifecycle='REACTION_PENDING' "
        "AND (execution_ref IS NULL OR execution_ref='')",
        (tenant, account),
    ).fetchall()
    stamp = datetime.now(timezone.utc).isoformat()
    n = 0
    for row in rows:
        outlook_id, evidence_json = values(row)
        try:
            evidence = json.loads(evidence_json or "{}")
        except ValueError:
            continue
        steps = evidence.get("steps_done") or []
        if "REACTION" not in steps:
            continue
        conn.execute(
            "UPDATE ai_outlook_handoff SET lifecycle='AUTHORIZATION_PENDING', updated_at=? WHERE outlook_id=?",
            (stamp, outlook_id),
        )
        try:
            from ...notifications.outlook_alert import publish_handoff

            publish_handoff(conn, outlook_id, "AUTHORIZATION_PENDING")
        except Exception:
            import logging

            logging.getLogger("cacsms.ai_outlook").warning("Outlook entry alert could not be queued", exc_info=True)
        n += 1
    return n


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
    if _send_on_reaction() and "REACTION" in keys and horizon != "H8":
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
