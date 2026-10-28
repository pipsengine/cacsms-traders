"""Load the latest persisted outlook book for the active tenant and account.

Tenant and account come from the server scope. Callers must not pass a client-selected tenant.
"""
from __future__ import annotations

import json

from ..autonomous.config import ae_settings
from ..autonomous.engine import _mode
from ..autonomous.portfolio import _account_row, _profile, open_position_cap
from ..market.outlook.store import OutlookRepository
from ..market.provenance import values
from .project import _iso_latest

HORIZONS = ("DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "H8")
BROKER_BASIS = "No broker-order ledger is stored. Open, pending and in-flight counts stay at zero until an order id is reconciled."


def _evaluation_flags(conn, outlook_ids: list[str], tenant: str, account: str) -> dict[str, bool]:
    if not outlook_ids:
        return {}
    marks = ",".join("?" * len(outlook_ids))
    rows = conn.execute(
        f"SELECT outlook_id, invalidated FROM ai_outlook_evaluation WHERE tenant_id=? AND trading_account_id=? AND outlook_id IN ({marks})",
        (tenant, account, *outlook_ids),
    ).fetchall()
    out = {}
    for row in rows:
        outlook_id, invalidated = values(row)
        out[str(outlook_id)] = bool(invalidated)
    return out


def _handoff_note(evidence: dict) -> str | None:
    if evidence.get("broker_error"):
        return f"Broker did not accept the order: {evidence['broker_error']}"
    if evidence.get("risk_note"):
        return str(evidence["risk_note"])
    done = evidence.get("steps_done") or []
    if done:
        return "Confirmation so far: " + ", ".join(str(step) for step in done) + "."
    return None


def _handoffs(conn, outlook_ids: list[str], tenant: str, account: str) -> dict[str, dict]:
    if not outlook_ids:
        return {}
    marks = ",".join("?" * len(outlook_ids))
    rows = conn.execute(
        f"SELECT outlook_id, lifecycle, execution_ref, evidence_json, updated_at FROM ai_outlook_handoff "
        f"WHERE tenant_id=? AND trading_account_id=? AND outlook_id IN ({marks})",
        (tenant, account, *outlook_ids),
    ).fetchall()
    out = {}
    for row in rows:
        outlook_id, lifecycle, execution_ref, evidence_json, updated_at = values(row)
        try:
            evidence = json.loads(evidence_json or "{}")
        except ValueError:
            evidence = {}
        out[str(outlook_id)] = {
            "lifecycle": str(lifecycle),
            "execution_ref": execution_ref or None,
            "note": _handoff_note(evidence if isinstance(evidence, dict) else {}),
            "updated_at": updated_at,
        }
    return out


def load_campaign_rows(store: OutlookRepository) -> list[dict]:
    rows = []
    for horizon in HORIZONS:
        run = store.latest_published(horizon)
        if not run:
            continue
        outlooks = store.outlooks(run["id"])
        ids = [str(item.get("outlook_id")) for item in outlooks if item.get("outlook_id")]
        revisions = store.latest_revisions(ids)
        invalidated = _evaluation_flags(store.conn, ids, store.tenant, store.account)
        handoffs = _handoffs(store.conn, ids, store.tenant, store.account)
        for outlook in outlooks:
            outlook_id = str(outlook.get("outlook_id") or "")
            revision = revisions.get(outlook_id) or {}
            handoff = handoffs.get(outlook_id) or {}
            lifecycle = handoff.get("lifecycle") or revision.get("status") or (outlook.get("lifecycle"))
            rows.append({
                "outlook": outlook,
                "horizon": horizon,
                "tenant_id": store.tenant,
                "account_id": store.account,
                "lifecycle": lifecycle,
                "execution_ref": handoff.get("execution_ref"),
                "handoff_note": handoff.get("note"),
                "invalidated": bool(invalidated.get(outlook_id)),
                "updated_at": _iso_latest(
                    handoff.get("updated_at"), run.get("monitored_at"), run.get("updated_at"),
                    run.get("published_at"), run.get("created_at"),
                ),
                "published_at": run.get("published_at") or run.get("created_at"),
                "revisions": [],
            })
    return rows


def load_detail_revisions(store: OutlookRepository, outlook_id: str) -> list[dict]:
    return store.revisions(outlook_id)


def exposure_snapshot(conn, tenant: str, account_id: str, now) -> dict:
    """Margin/equity exposure only when the account sync is fresh. Stale data fails closed."""
    from ..autonomous.portfolio import _stale

    account = _account_row(conn, tenant, account_id)
    profile = _profile(conn, account["id"] if account else None)
    stale = _stale(account.get("last_synced_at") if account else None, now)
    max_pct = None if not profile else _num(profile.get("max_total_risk_pct"))
    used = None
    if account and not stale:
        equity = _num(account.get("equity"))
        margin = _num(account.get("margin"))
        if equity and margin is not None:
            used = round(100 * margin / equity, 1)
    broker = "DISCONNECTED"
    if account and account.get("connection_status"):
        broker = "STALE" if stale else str(account["connection_status"])
    return {
        "exposure_percent": used,
        "max_exposure_percent": max_pct,
        "account_cap": open_position_cap(conn, tenant, account_id),
        "broker_status": broker,
        "stale": stale,
    }


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def market_data_status(conn) -> str:
    try:
        from ..market.market_data import market_context

        ctx = market_context(conn) or {}
    except Exception:
        return "UNKNOWN"
    if ctx.get("provider_status"):
        return str(ctx["provider_status"])
    if ctx.get("market_data_ready"):
        return "READY"
    return "UNAVAILABLE"


def _terminal_book(snapshot: dict) -> tuple[list[dict] | None, str, float | None]:
    """Live tickets and margin exposure. A failed read leaves both empty rather than inventing fills."""
    from ..domain.mt5_terminal_account import read_terminal_account
    from ..domain.mt5_terminal_positions import read_terminal_positions

    positions, basis = read_terminal_positions(wait=False)
    exposure = snapshot["exposure_percent"]
    account = read_terminal_account(wait=False)
    if account and account.get("available"):
        equity = _num(account.get("equity"))
        margin = _num(account.get("margin"))
        if equity and margin is not None:
            exposure = round(100 * margin / equity, 1)
    if positions is None:
        return None, f"{BROKER_BASIS} {basis}", exposure
    return positions, basis, exposure


def assemble(conn, store: OutlookRepository, opportunities: list[dict], now) -> dict:
    from .project import build_overview

    snapshot = exposure_snapshot(conn, store.tenant, store.account, now)
    mode = _mode(conn)
    broker_status = snapshot["broker_status"]
    if mode in ("ANALYSIS_ONLY", "PAUSED", "EMERGENCY_STOP"):
        broker_status = "BLOCKED" if broker_status in ("DISCONNECTED", "UNKNOWN") else f"{broker_status} · SUBMISSION BLOCKED"
    positions, basis, exposure = _terminal_book(snapshot)
    if positions is not None:
        from .reconcile import close_absent_tickets

        close_absent_tickets(conn, store.tenant, store.account, opportunities, positions, now)
    book = build_overview(
        load_campaign_rows(store),
        generated_at=now,
        system_mode=mode,
        engine_cap=ae_settings().max_concurrent,
        account_cap=snapshot["account_cap"],
        exposure_percent=exposure,
        max_exposure_percent=snapshot["max_exposure_percent"],
        market_data_status=market_data_status(conn),
        broker_status=broker_status,
        broker_basis=basis,
        opportunities=opportunities,
        orders=[],
        broker_positions=positions,
    )
    try:
        from .registry import performance_counts, sync_registry

        closed = conn.execute(
            "SELECT opp_type, outcome, status FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=? AND status='CLOSED'",
            (store.tenant, store.account),
        ).fetchall()
        book["summary"]["performance"] = performance_counts(
            [{"opp_type": values(row)[0], "outcome": values(row)[1], "status": values(row)[2]} for row in closed]
        )
        sync_registry(conn, store.tenant, store.account, book["campaigns"], now.isoformat())
        conn.commit()
    except Exception:
        conn.rollback()
    return book


def detail_for(conn, store: OutlookRepository, opportunities: list[dict], outlook_id: str, now) -> dict | None:
    book = assemble(conn, store, opportunities, now)
    match = next((row for row in book["campaigns"] if row["id"] == outlook_id), None)
    if match is None:
        return None
    match["events"] = [
        {"at": str(item.get("observed_at") or ""), "stage": str(item.get("status") or ""), "message": _revision_message(item)}
        for item in load_detail_revisions(store, outlook_id)
    ] or match.get("events") or []
    return match


def _revision_message(item: dict) -> str:
    detail = item.get("detail")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except ValueError:
            return detail
    if isinstance(detail, dict):
        action = detail.get("system_action") or detail.get("status")
        if action:
            return str(action)
    return str(item.get("status") or "Revision recorded")
