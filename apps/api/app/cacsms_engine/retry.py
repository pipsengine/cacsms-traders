"""Clear stale execution errors so sizing and broker paths can run again after policy fixes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..market.provenance import values

_RETRIABLE = frozenset(
    {
        "NO_CONTRACT",
        "NO_QUOTE",
        "MINIMUM_EXCEEDS_BUDGET",
        "MARGIN",
        "PER_TRADE_RISK",
        "ACCOUNT_UNKNOWN",
        "PROFIT_CURRENCY_UNCONVERTED",
        "LIVE_TRADING_DISABLED",
        "Trade disabled",
    }
)


def _retriable_error(code: str) -> bool:
    text = (code or "").strip()
    if not text:
        return False
    if text in _RETRIABLE:
        return True
    return text.startswith("Symbol ") or "MT5 terminal" in text


def reset_execution_retries(conn, tenant: str, account: str) -> dict:
    """Drop retriable handoff errors and rejected trade requests so the next cycle can resend."""
    stamp = datetime.now(timezone.utc).isoformat()
    handoffs = 0
    requests = 0
    opportunities = 0

    rows = conn.execute(
        "SELECT outlook_id, horizon, evidence_json FROM ai_outlook_handoff "
        "WHERE tenant_id=? AND trading_account_id=? AND lifecycle='AUTHORIZATION_PENDING' "
        "AND (execution_ref IS NULL OR execution_ref='')",
        (tenant, account),
    ).fetchall()
    for outlook_id, horizon, evidence_json in rows:
        try:
            evidence = json.loads(evidence_json or "{}")
        except ValueError:
            continue
        if not isinstance(evidence, dict):
            continue
        err = str(evidence.get("broker_error") or "")
        if not _retriable_error(err):
            continue
        evidence.pop("broker_error", None)
        evidence.pop("attempted_at", None)
        evidence["retry_reset_at"] = stamp
        conn.execute(
            "UPDATE ai_outlook_handoff SET evidence_json=?, updated_at=? WHERE outlook_id=?",
            (json.dumps(evidence), stamp, outlook_id),
        )
        handoffs += 1
        key = f"mode2:{outlook_id}:{horizon}"
        cur = conn.execute(
            "DELETE FROM trade_requests WHERE tenant_id=? AND idempotency_key=? AND status='PRECHECK_REJECTED'",
            (tenant, key),
        )
        requests += int(cur.rowcount or 0)

    opp_rows = conn.execute(
        "SELECT id, evidence_json FROM ae_opportunity WHERE tenant_id=? AND trading_account_id=? "
        "AND status='ACTIVE' AND stage IN ('EXECUTION','RISK')",
        (tenant, account),
    ).fetchall()
    for oid, evidence_json in opp_rows:
        try:
            evidence = json.loads(evidence_json or "{}")
        except ValueError:
            continue
        if not isinstance(evidence, dict):
            continue
        err = str(evidence.get("broker_error") or "")
        if not _retriable_error(err):
            continue
        evidence.pop("broker_error", None)
        evidence["retry_reset_at"] = stamp
        conn.execute(
            "UPDATE ae_opportunity SET evidence_json=?, updated_at=? WHERE id=?",
            (json.dumps(evidence), stamp, oid),
        )
        opportunities += 1

    return {"handoffs": handoffs, "trade_requests_cleared": requests, "opportunities": opportunities, "at": stamp}
