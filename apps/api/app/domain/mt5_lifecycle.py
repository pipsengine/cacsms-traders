"""Unified MT5 gateway + Strength Intelligence lifecycle (read-only aggregation)."""
from __future__ import annotations

from typing import Any


def compute_connection_lifecycle(
    gateway: dict[str, Any],
    settings: dict[str, Any],
    intelligence: dict[str, Any] | None,
    *,
    connect_in_progress: bool = False,
) -> dict[str, str]:
    """Map persisted session, live IPC, and engine meta into explicit phases."""
    session = str(settings.get("session_status") or "DISCONNECTED").upper()
    path = (settings.get("terminal_path") or "").strip()
    gw_status = str(gateway.get("status") or "DISCONNECTED").upper()
    last_error = settings.get("last_error")

    if connect_in_progress:
        gateway_phase = "CONNECTING"
    elif session == "DISCONNECTED" and not path:
        gateway_phase = "NOT_CONFIGURED"
    elif session == "DISCONNECTED":
        gateway_phase = "ERROR" if last_error else "DISCONNECTED"
    elif gw_status == "CONNECTING":
        gateway_phase = "RECONNECTING"
    elif gw_status == "CONNECTED":
        gateway_phase = "CONNECTED"
    else:
        gateway_phase = "DISCONNECTED"

    market_sync_phase = "IDLE"
    if intelligence:
        ready = bool(intelligence.get("market_data_ready"))
        engine = str(intelligence.get("engine_state") or intelligence.get("strength_engine_status") or "").upper()
        if not ready or gateway_phase in ("NOT_CONFIGURED", "DISCONNECTED", "ERROR"):
            market_sync_phase = "WAITING_PROVIDER"
        elif engine in (
            "SYNCING",
            "STARTING",
            "DISCOVERING_SYMBOLS",
            "BACKFILLING",
            "VALIDATING",
            "CALCULATING",
        ):
            market_sync_phase = "SYNCHRONIZING"
        elif engine == "INCOMPLETE_BASKET":
            market_sync_phase = "SYNCHRONIZING"
        elif engine == "READY":
            market_sync_phase = "READY"
        elif engine == "ERROR":
            market_sync_phase = "ERROR"
        elif engine in ("DEGRADED", "WORKER_UNAVAILABLE"):
            market_sync_phase = "DEGRADED"
        elif engine == "WAITING_PROVIDER":
            market_sync_phase = "WAITING_PROVIDER"
        else:
            market_sync_phase = "SYNCHRONIZING" if gateway_phase == "CONNECTED" else "WAITING_PROVIDER"

    if gateway_phase in ("NOT_CONFIGURED", "DISCONNECTED", "ERROR", "CONNECTING", "RECONNECTING"):
        overall = gateway_phase
    elif market_sync_phase == "READY":
        overall = "READY"
    elif market_sync_phase in ("SYNCHRONIZING", "DEGRADED", "WAITING_PROVIDER"):
        overall = "SYNCHRONIZING" if gateway_phase == "CONNECTED" else gateway_phase
    else:
        overall = gateway_phase

    return {
        "gateway_phase": gateway_phase,
        "market_sync_phase": market_sync_phase,
        "overall_phase": overall,
    }
