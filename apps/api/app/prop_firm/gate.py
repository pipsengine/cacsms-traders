"""Block an autonomous order when the attached terminal belongs to a prop account.

A terminal that is not registered here is left to the existing demo and live checks.
Once a login is registered, a failed compliance read blocks the order.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from ..core.database import db
from .compliance import FirmRules, Observation, evaluate
from .store import find_by_login

log = logging.getLogger("cacsms.prop_firm")


def _audit(conn, account: dict, action: str, detail: dict) -> None:
    conn.execute(
        "INSERT INTO pf_audit(id, tenant_id, account_id, firm_id, action, actor, detail_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4()), account["tenant_id"], account["id"], account["firm_id"], action, "execution",
            json.dumps(detail), datetime.now(timezone.utc).isoformat(),
        ),
    )


def block_prop_order(
    *,
    login: str | int | None,
    equity: float,
    balance: float,
    floating_pnl: float,
    symbol: str,
    volume: float,
    risk_pct: float,
    open_positions: int,
    strategy: str | None = None,
) -> str | None:
    if login is None:
        return None
    try:
        with db() as conn:
            account = find_by_login(conn, str(login))
            if account is None:
                return None
            if account.get("ambiguous"):
                return "More than one prop account uses this broker login"
            rule_row = conn.execute("SELECT rules_json FROM pf_rule_version WHERE id=?", (account["rule_version_id"],)).fetchone()
            raw = json.loads(rule_row["rules_json"]) if rule_row else None
            rules = FirmRules.from_dict(raw) if raw else None
            snap = conn.execute(
                "SELECT * FROM pf_snapshot WHERE account_id=? ORDER BY recorded_at DESC LIMIT 1",
                (account["id"],),
            ).fetchone()
            if rules is None or snap is None:
                reason = "Prop firm rules or a fresh account snapshot are missing"
                _audit(conn, account, "ORDER_BLOCKED", {"reason": reason, "symbol": symbol})
                conn.commit()
                return reason
            recorded = datetime.fromisoformat(snap["recorded_at"])
            if recorded.tzinfo is None:
                recorded = recorded.replace(tzinfo=timezone.utc)
            key = f"{symbol}:{volume}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
            duplicate = conn.execute(
                "SELECT 1 FROM pf_order_intent WHERE account_id=? AND idempotency_key=? AND created_at>=?",
                (account["id"], key, (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()),
            ).fetchone()
            decision = evaluate(rules, Observation(
                balance=balance, equity=equity, initial_balance=float(account["account_size"]),
                day_start_balance=float(snap["day_start_balance"]), day_start_equity=float(snap["day_start_equity"]),
                equity_high=max(float(snap["equity_high"]), equity), eod_equity_high=max(float(snap["eod_equity_high"]), equity),
                floating_pnl=floating_pnl, commission=float(snap["commission"] or 0),
                open_positions=open_positions, pending_orders=int(snap["pending_orders"] or 0),
                proposed_lot=volume, proposed_risk_pct=risk_pct, snapshot_age_seconds=(datetime.now(timezone.utc) - recorded).total_seconds(),
                strategy=strategy, duplicate=duplicate is not None,
                automation_confirmed=bool(account["automation_confirmed"]), autonomous=True,
                news_calendar_available=False,
            ))
            conn.execute(
                "INSERT INTO pf_evaluation(id, tenant_id, account_id, snapshot_id, decision, protection, daily_drawdown_pct, "
                "max_drawdown_pct, reasons_json, close_positions, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()), account["tenant_id"], account["id"], snap["id"],
                    "ALLOW" if decision.allow else "REJECT", decision.protection, decision.daily_drawdown_pct,
                    decision.max_drawdown_pct, json.dumps(list(decision.reasons)), 1 if decision.close_positions else 0,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            if decision.allow:
                conn.execute(
                    "INSERT INTO pf_order_intent(id, tenant_id, account_id, idempotency_key, symbol, decision, created_at) "
                    "VALUES(?,?,?,?,?,?,?) ON CONFLICT(account_id, idempotency_key) DO NOTHING",
                    (str(uuid.uuid4()), account["tenant_id"], account["id"], key, symbol, "ALLOW", datetime.now(timezone.utc).isoformat()),
                )
                _audit(conn, account, "ORDER_PERMITTED", {"symbol": symbol, "volume": volume, "protection": decision.protection})
            else:
                _audit(conn, account, "ORDER_BLOCKED", {"symbol": symbol, "reasons": list(decision.reasons)})
            conn.commit()
            if decision.allow:
                return None
            return "; ".join(decision.reasons) or "Prop firm compliance rejected the order"
    except Exception:
        log.exception("Prop firm gate failed for login %s", login)
        try:
            with db() as conn:
                found = find_by_login(conn, str(login))
        except Exception:
            return None
        if not found or found.get("ambiguous"):
            return None
        return "Prop firm compliance could not evaluate this account"
