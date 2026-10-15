"""Match accepted broker tickets to the live terminal.

A ticket that is no longer open is closed on the opportunity. This does not invent a fill or a profit.
When the terminal cannot be read, nothing is closed.
"""
from __future__ import annotations

import json


def accepted_ticket(opportunity: dict) -> str | None:
    evidence = opportunity.get("evidence") or opportunity.get("evidence_json") or {}
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except ValueError:
            evidence = {}
    if not isinstance(evidence, dict):
        return None
    order = evidence.get("broker_order") or {}
    if not isinstance(order, dict):
        return None
    ticket = order.get("ticket")
    return None if ticket in (None, "") else str(ticket)


def close_absent_tickets(conn, tenant: str, account: str, opportunities: list[dict], positions: list[dict], now) -> list[str]:
    """Close ORDER_ACCEPTED rows whose ticket is absent. Returns the closed ids."""
    from ..autonomous.store import AERepository

    open_ids = {str(item.get("ticket")) for item in positions if item.get("ticket") is not None}
    repo = AERepository(conn, (tenant, account))
    stamp = now.isoformat() if hasattr(now, "isoformat") else str(now)
    closed: list[str] = []
    for opportunity in opportunities:
        if str(opportunity.get("status") or "ACTIVE") != "ACTIVE":
            continue
        if str(opportunity.get("state") or "") != "ORDER_ACCEPTED":
            continue
        ticket = accepted_ticket(opportunity)
        if not ticket or ticket in open_ids:
            continue
        evidence = opportunity.get("evidence") or {}
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except ValueError:
                evidence = {}
        if not isinstance(evidence, dict):
            evidence = {}
        evidence = {
            **evidence,
            "terminal_reconcile": {"ticket": ticket, "at": stamp, "reason": "ABSENT_FROM_TERMINAL"},
        }
        note = f"Broker order {ticket} is not open on the terminal."
        opportunity["status"] = "CLOSED"
        opportunity["outcome"] = "EXITED"
        opportunity["stage"] = "LEARNING"
        opportunity["state"] = "COMPLETED"
        opportunity["closed_at"] = stamp
        opportunity["next_condition"] = note
        opportunity["evidence"] = evidence
        repo.update_opportunity(
            opportunity["id"],
            status="CLOSED",
            outcome="EXITED",
            stage="LEARNING",
            state="COMPLETED",
            closed_at=stamp,
            next_condition=note,
            evidence_json=evidence,
            updated_at=stamp,
            reason_code="TERMINAL_FLAT",
        )
        closed.append(str(opportunity["id"]))
    return closed
