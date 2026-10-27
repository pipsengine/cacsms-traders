"""Outlook-first execution: defer strategy broker orders while outlook campaigns are active on a symbol."""
from __future__ import annotations

import os

_ACTIVE_OUTLOOK = (
    "WATCHING",
    "APPROACHING_ZONE",
    "ZONE_REACHED",
    "REACTION_PENDING",
    "CONFIRMATION_PENDING",
    "CONFIRMED",
    "AUTHORIZATION_PENDING",
)


def outlook_execution_priority() -> bool:
    return os.getenv("OUTLOOK_EXECUTION_PRIORITY", "1").strip().lower() not in ("0", "false", "no")


def strategy_deferred_for_outlook(conn, tenant: str, account: str, symbol: str) -> bool:
    """True when a qualified outlook on this symbol is still in the intraday pipeline."""
    if not outlook_execution_priority():
        return False
    sym = (symbol or "").upper()
    row = conn.execute(
        """
        SELECT 1 FROM ai_outlook_handoff h
        JOIN ai_outlook_symbol s ON s.id = h.outlook_id
        WHERE h.tenant_id=? AND h.trading_account_id=? AND h.symbol=? AND s.qualified=1
          AND h.lifecycle IN ({})
        LIMIT 1
        """.format(",".join("?" * len(_ACTIVE_OUTLOOK))),
        (tenant, account, sym, *_ACTIVE_OUTLOOK),
    ).fetchone()
    return row is not None
