"""Idempotent order queue shared by both autonomous modes.

An uncertain broker result is stored and is not submitted again. The next step
is reconciliation against the tickets the broker still reports.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from .money import text

UNCERTAIN_RETCODES = {10012, 10032}
TERMINAL = {"CONFIRMED", "UNCERTAIN", "BROKER_REJECTED", "RECONCILED_CLOSED"}
LOCK_SECONDS = 30


def _now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current if current.tzinfo else current.replace(tzinfo=timezone.utc)


def _row(conn, sql, params=()):
    found = conn.execute(sql, params).fetchone()
    return None if found is None else dict(found)


def _audit(conn, tenant_id, account_id, request_id, stage, detail, now: datetime):
    conn.execute(
        "INSERT INTO execution_audit(id,tenant_id,trading_account_id,trade_request_id,stage,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), tenant_id, account_id, request_id, stage, json.dumps(detail, default=str), now.isoformat()),
    )


def acquire_lock(conn, tenant_id: str, account_id: str, holder: str, now: datetime | None = None) -> bool:
    now = _now(now)
    expires = (now + timedelta(seconds=LOCK_SECONDS)).isoformat()
    stamp = now.isoformat()
    current = _row(conn, "SELECT holder, expires_at FROM execution_locks WHERE trading_account_id=?", (account_id,))
    if current and current["expires_at"] > stamp and current["holder"] != holder:
        return False
    if current:
        conn.execute(
            "UPDATE execution_locks SET tenant_id=?,holder=?,acquired_at=?,expires_at=? WHERE trading_account_id=?",
            (tenant_id, holder, stamp, expires, account_id),
        )
    else:
        conn.execute(
            "INSERT INTO execution_locks(trading_account_id,tenant_id,holder,acquired_at,expires_at) VALUES(?,?,?,?,?)",
            (account_id, tenant_id, holder, stamp, expires),
        )
    return True


def release_lock(conn, account_id: str, holder: str) -> None:
    conn.execute("DELETE FROM execution_locks WHERE trading_account_id=? AND holder=?", (account_id, holder))


def classify_broker_result(result: dict | None) -> str:
    if not result or result.get("uncertain"):
        return "UNCERTAIN"
    retcode = result.get("retcode")
    if result.get("ok"):
        return "CONFIRMED"
    if retcode in UNCERTAIN_RETCODES or (retcode is None and not result.get("error")):
        return "UNCERTAIN"
    return "BROKER_REJECTED"


def open_exposure(conn, tenant_id: str, account_id: str) -> tuple[list[str], int]:
    rows = conn.execute(
        "SELECT projected_loss FROM trade_requests WHERE tenant_id=? AND trading_account_id=? AND status='CONFIRMED'",
        (tenant_id, account_id),
    ).fetchall()
    losses = [dict(row)["projected_loss"] for row in rows if dict(row).get("projected_loss")]
    return losses, len(rows)


def get_request(conn, tenant_id: str, key: str):
    return _row(conn, "SELECT * FROM trade_requests WHERE tenant_id=? AND idempotency_key=?", (tenant_id, key))


def _save_result(conn, tenant_id, request_id, outcome, result, now: datetime):
    conn.execute(
        "INSERT INTO execution_results(id,tenant_id,trade_request_id,retcode,ticket,deal,outcome,broker_comment,payload_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()), tenant_id, request_id, None if not result else result.get("retcode"),
            None if not result else result.get("ticket"), None if not result else result.get("deal"),
            outcome, None if not result else result.get("error"), json.dumps(result or {}, default=str), now.isoformat(),
        ),
    )


def upsert_request(conn, *, tenant_id, account_id, key, mode, symbol, direction, currency, status, now,
                   action="PLACE", broker_symbol=None, entry=None, stop=None, target=None, volume=None,
                   risk_amount=None, projected_loss=None, reason=None, ticket=None) -> dict:
    current = get_request(conn, tenant_id, key)
    stamp = now.isoformat()
    values = (
        mode, action, symbol, broker_symbol, direction,
        None if entry is None else text(entry), None if stop is None else text(stop), None if target is None else text(target),
        None if volume is None else text(volume), None if risk_amount is None else text(risk_amount),
        None if projected_loss is None else text(projected_loss), currency, status, reason, ticket, stamp,
    )
    if current is None:
        request_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO trade_requests(id,tenant_id,trading_account_id,idempotency_key,mode,action,symbol,broker_symbol,direction,
               entry_price,stop_price,target_price,volume,risk_amount,projected_loss,currency,status,rejection_reason,ticket,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (request_id, tenant_id, account_id, key, *values, stamp),
        )
    else:
        request_id = current["id"]
        conn.execute(
            """UPDATE trade_requests SET mode=?,action=?,symbol=?,broker_symbol=?,direction=?,entry_price=?,stop_price=?,target_price=?,
               volume=?,risk_amount=?,projected_loss=?,currency=?,status=?,rejection_reason=?,ticket=?,updated_at=? WHERE id=?""",
            (*values, request_id),
        )
    return get_request(conn, tenant_id, key)


def record_outcome(conn, request: dict, outcome: str, result: dict | None, now: datetime | None = None) -> dict:
    now = _now(now)
    ticket = request.get("ticket")
    if result and result.get("ticket"):
        ticket = str(result["ticket"])
    status = {"CONFIRMED": "CONFIRMED", "UNCERTAIN": "UNCERTAIN", "BROKER_REJECTED": "BROKER_REJECTED"}.get(outcome, outcome)
    conn.execute(
        "UPDATE trade_requests SET status=?,ticket=?,rejection_reason=?,updated_at=? WHERE id=?",
        (status, ticket, None if outcome == "CONFIRMED" else (result or {}).get("error"), now.isoformat(), request["id"]),
    )
    _save_result(conn, request["tenant_id"], request["id"], outcome, result, now)
    _audit(conn, request["tenant_id"], request["trading_account_id"], request["id"], "BROKER_CONFIRMATION", {"outcome": outcome, "result": result}, now)
    if outcome == "UNCERTAIN":
        _audit(conn, request["tenant_id"], request["trading_account_id"], request["id"], "TRADE_RECONCILIATION",
               {"required": True, "reason": "Broker response did not confirm the order"}, now)
    return get_request(conn, request["tenant_id"], request["idempotency_key"])


def reconcile_account(conn, tenant_id: str, account_id: str, open_tickets: set[str], now: datetime | None = None) -> dict:
    """Match stored requests to tickets the broker still has open. Uncertain rows are not sent again."""
    now = _now(now)
    confirmed = closed = 0
    rows = conn.execute(
        "SELECT * FROM trade_requests WHERE tenant_id=? AND trading_account_id=? AND status IN ('UNCERTAIN','CONFIRMED','SUBMITTING')",
        (tenant_id, account_id),
    ).fetchall()
    for raw in rows:
        row = dict(raw)
        ticket = str(row.get("ticket") or "")
        age = now - datetime.fromisoformat(row["updated_at"])
        if row["status"] == "UNCERTAIN" and ticket and ticket in open_tickets:
            conn.execute("UPDATE trade_requests SET status='CONFIRMED',updated_at=? WHERE id=?", (now.isoformat(), row["id"]))
            _audit(conn, tenant_id, account_id, row["id"], "TRADE_RECONCILIATION", {"ticket": ticket, "found": True}, now)
            confirmed += 1
        elif row["status"] == "CONFIRMED" and ticket and ticket not in open_tickets and age.total_seconds() > 15:
            conn.execute("UPDATE trade_requests SET status='RECONCILED_CLOSED',updated_at=? WHERE id=?", (now.isoformat(), row["id"]))
            _audit(conn, tenant_id, account_id, row["id"], "POSITION_MONITORING", {"ticket": ticket, "open": False}, now)
            closed += 1
        elif row["status"] == "SUBMITTING" and age.total_seconds() > LOCK_SECONDS:
            conn.execute(
                "UPDATE trade_requests SET status='UNCERTAIN',rejection_reason=?,updated_at=? WHERE id=?",
                ("Gateway did not report the broker result", now.isoformat(), row["id"]),
            )
            _audit(conn, tenant_id, account_id, row["id"], "TRADE_RECONCILIATION", {"expired_submission": True}, now)
    return {"confirmed": confirmed, "closed": closed}


def claim_queued(conn, tenant_id: str, account_id: str, now: datetime | None = None):
    """One queued order for this account. A claimed order is not returned again."""
    now = _now(now)
    pending = conn.execute(
        "SELECT id, updated_at FROM trade_requests WHERE tenant_id=? AND trading_account_id=? AND status='SUBMITTING'",
        (tenant_id, account_id),
    ).fetchall()
    for raw in pending:
        row = dict(raw)
        age = now - datetime.fromisoformat(row["updated_at"])
        if age.total_seconds() > LOCK_SECONDS:
            conn.execute(
                "UPDATE trade_requests SET status='UNCERTAIN',rejection_reason=?,updated_at=? WHERE id=?",
                ("Gateway did not report the broker result", now.isoformat(), row["id"]),
            )
            _audit(conn, tenant_id, account_id, row["id"], "TRADE_RECONCILIATION", {"expired_submission": True}, now)
    row = _row(
        conn,
        """SELECT * FROM trade_requests WHERE tenant_id=? AND trading_account_id=? AND status='QUEUED'
           ORDER BY created_at LIMIT 1""",
        (tenant_id, account_id),
    )
    if row is None:
        return None
    conn.execute("UPDATE trade_requests SET status='SUBMITTING',updated_at=? WHERE id=? AND status='QUEUED'", (now.isoformat(), row["id"]))
    claimed = _row(conn, "SELECT * FROM trade_requests WHERE id=? AND status='SUBMITTING'", (row["id"],))
    if claimed:
        _audit(conn, tenant_id, account_id, claimed["id"], "LIVE_ORDER_SUBMISSION", {"gateway": True}, now)
    return claimed
