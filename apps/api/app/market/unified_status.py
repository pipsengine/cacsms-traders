"""Single source of truth for provider + market-data + strength readiness (UI + autonomous engine)."""
from __future__ import annotations

from typing import Any


def compute_platform_status(conn) -> dict[str, Any]:
    from .market_data import configuration, ensure_active_provider_snapshot, market_context
    from .strength_engine import get_strength_engine
    from .basket_status import repository_basket_status

    ensure_active_provider_snapshot(conn)
    ctx = market_context(conn)
    cfg = configuration(conn)
    meta = get_strength_engine().engine_meta() or {}
    active = ctx.get("active_provider")
    md_ready = bool(ctx.get("market_data_ready"))
    scope = ctx.get("market_data_scope") or {}
    account_id = scope.get("account_id") or cfg.get("account_id") or ""

    pairs = int(meta.get("pairs_loaded") or meta.get("repository_pairs_loaded") or 0)
    if pairs == 0 and md_ready and active:
        try:
            snap_row = conn.execute(
                "SELECT id FROM mi_provider_snapshot WHERE finalized_at IS NULL ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            sid = snap_row["id"] if snap_row else None
            basket = repository_basket_status(conn, provider=active, snapshot_id=sid, account_id=account_id)
            pairs = int(basket.get("pairs_loaded") or 0)
        except Exception:
            pass

    engine_state = str(meta.get("engine_state") or "STARTING")
    if not active:
        provider_phase = "OFFLINE"
    elif not md_ready:
        provider_phase = "SYNCHRONIZING"
    else:
        provider_phase = "CONNECTED"

    if provider_phase == "OFFLINE":
        data_phase = "BLOCKED"
    elif pairs >= 28 and meta.get("historical_ok"):
        data_phase = "DATA_READY"
    elif pairs >= 1:
        data_phase = "SYNCHRONIZING" if pairs < 28 else "DEGRADED"
    elif md_ready:
        data_phase = "SYNCHRONIZING"
    else:
        data_phase = "BLOCKED"

    connections_label = {
        "OFFLINE": "Offline",
        "SYNCHRONIZING": "Syncing",
        "CONNECTED": "Healthy",
    }.get(provider_phase, "Unknown")

    analysis_allowed = provider_phase != "OFFLINE" and data_phase != "BLOCKED"
    authorization_allowed = analysis_allowed and pairs >= 20 and engine_state in ("READY", "INCOMPLETE_BASKET", "DEGRADED")

    return {
        "provider_phase": provider_phase,
        "data_phase": data_phase,
        "connections_label": connections_label,
        "provider_connected": provider_phase in ("CONNECTED", "SYNCHRONIZING"),
        "market_data_ready": md_ready,
        "strength_pairs_loaded": pairs,
        "strength_pairs_total": int(meta.get("pairs_total") or 28),
        "strength_engine_state": engine_state,
        "strength_live": bool(meta.get("live_data")),
        "analysis_allowed": analysis_allowed,
        "authorization_allowed": authorization_allowed,
        "active_provider": active,
        "account_id": account_id,
    }
