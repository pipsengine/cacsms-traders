"""Tenant-scoped prop firm persistence. Credentials stay encrypted and are never selected for the UI."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .compliance import FirmRules, Observation, evaluate

LIFECYCLE = (
    "REGISTERED", "CONNECTED", "EVALUATION_PHASE_1", "EVALUATION_PHASE_2",
    "EVALUATION_PASSED", "FUNDED", "ACTIVE", "SUSPENDED", "FAILED", "RESET", "CLOSED",
)
TRANSITIONS = {
    "REGISTERED": {"CONNECTED", "CLOSED"},
    "CONNECTED": {"EVALUATION_PHASE_1", "FUNDED", "ACTIVE", "CLOSED"},
    "EVALUATION_PHASE_1": {"EVALUATION_PHASE_2", "EVALUATION_PASSED", "FAILED", "RESET", "SUSPENDED", "CLOSED"},
    "EVALUATION_PHASE_2": {"EVALUATION_PASSED", "FAILED", "RESET", "SUSPENDED", "CLOSED"},
    "EVALUATION_PASSED": {"FUNDED", "SUSPENDED", "CLOSED"},
    "FUNDED": {"ACTIVE", "SUSPENDED", "CLOSED"},
    "ACTIVE": {"SUSPENDED", "CLOSED"},
    "SUSPENDED": {"ACTIVE", "EVALUATION_PHASE_1", "CLOSED"},
    "FAILED": {"RESET", "CLOSED"},
    "RESET": {"EVALUATION_PHASE_1", "CONNECTED", "CLOSED"},
    "CLOSED": set(),
}
CONFIRMED = {"EVALUATION_PASSED", "FUNDED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _row(row) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _scalar(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


class PropRepository:
    def __init__(self, conn, tenant_id: str):
        self.conn = conn
        self.tenant = tenant_id

    def audit(self, action: str, actor: str, detail: dict, *, account_id: str | None = None, firm_id: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO pf_audit(id, tenant_id, account_id, firm_id, action, actor, detail_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (_id(), self.tenant, account_id, firm_id, action, actor, json.dumps(detail), _now()),
        )

    def create_firm(self, name: str, rules: dict, actor: str) -> dict:
        FirmRules.from_dict(rules)
        now = _now()
        firm_id, rule_id = _id(), _id()
        slug = "-".join(name.lower().split()) or firm_id[:8]
        self.conn.execute(
            "INSERT INTO pf_firm(id, tenant_id, name, slug, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (firm_id, self.tenant, name.strip(), slug, "ACTIVE", now, now),
        )
        self.conn.execute(
            "INSERT INTO pf_rule_version(id, tenant_id, firm_id, version, rules_json, created_at) VALUES(?,?,?,?,?,?)",
            (rule_id, self.tenant, firm_id, 1, json.dumps(rules), now),
        )
        self.audit("FIRM_REGISTERED", actor, {"name": name, "rule_version": 1}, firm_id=firm_id)
        return {"id": firm_id, "name": name.strip(), "rule_version_id": rule_id, "version": 1}

    def add_rules(self, firm_id: str, rules: dict, actor: str) -> dict:
        FirmRules.from_dict(rules)
        firm = self.conn.execute("SELECT id FROM pf_firm WHERE id=? AND tenant_id=?", (firm_id, self.tenant)).fetchone()
        if firm is None:
            raise KeyError(firm_id)
        current = self.conn.execute("SELECT COALESCE(MAX(version), 0) AS version FROM pf_rule_version WHERE firm_id=?", (firm_id,)).fetchone()
        version = int(_scalar(current) or 0) + 1
        rule_id = _id()
        now = _now()
        self.conn.execute(
            "INSERT INTO pf_rule_version(id, tenant_id, firm_id, version, rules_json, created_at) VALUES(?,?,?,?,?,?)",
            (rule_id, self.tenant, firm_id, version, json.dumps(rules), now),
        )
        self.audit("RULES_VERSIONED", actor, {"version": version}, firm_id=firm_id)
        return {"id": rule_id, "version": version}

    def create_account(self, payload: dict, actor: str) -> dict:
        firm = self.conn.execute(
            "SELECT id FROM pf_firm WHERE id=? AND tenant_id=?", (payload["firm_id"], self.tenant)
        ).fetchone()
        if firm is None:
            raise KeyError("firm")
        rule = None
        if payload.get("rule_version_id"):
            rule = self.conn.execute(
                "SELECT id, rules_json FROM pf_rule_version WHERE id=? AND firm_id=? AND tenant_id=?",
                (payload["rule_version_id"], payload["firm_id"], self.tenant),
            ).fetchone()
        if rule is None:
            latest = self.conn.execute(
                "SELECT id, rules_json FROM pf_rule_version WHERE firm_id=? AND tenant_id=? ORDER BY version DESC LIMIT 1",
                (payload["firm_id"], self.tenant),
            ).fetchone()
            if latest is None:
                raise KeyError("rules")
            rule = latest
        lifecycle = payload.get("lifecycle") or "REGISTERED"
        if lifecycle not in LIFECYCLE:
            raise ValueError("Lifecycle is not supported")
        now = _now()
        account_id = _id()
        self.conn.execute(
            "INSERT INTO pf_account(id, tenant_id, firm_id, rule_version_id, trading_account_id, display_name, external_id, "
            "broker, broker_login, broker_server, credential_cipher, environment, lifecycle, phase_label, account_size, "
            "currency, firm_confirmed, automation_confirmed, phase_ends_at, status_note, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                account_id, self.tenant, payload["firm_id"], rule["id"], payload.get("trading_account_id"),
                payload["display_name"].strip(), payload.get("external_id") or account_id[:8].upper(),
                payload.get("broker") or "MT5", payload.get("broker_login"), payload.get("broker_server"),
                payload.get("credential_cipher"), payload.get("environment") or "DEMO", lifecycle,
                payload.get("phase_label") or "Registration", float(payload["account_size"]),
                payload.get("currency") or "USD", 1 if payload.get("firm_confirmed") else 0,
                1 if payload.get("automation_confirmed") else 0, payload.get("phase_ends_at"),
                payload.get("status_note"), now, now,
            ),
        )
        self.audit("ACCOUNT_REGISTERED", actor, {"lifecycle": lifecycle, "broker": payload.get("broker")}, account_id=account_id, firm_id=payload["firm_id"])
        return self.account(account_id)

    def transition(self, account_id: str, lifecycle: str, actor: str, *, firm_confirmed: bool = False) -> dict:
        account = self._owned(account_id)
        current = account["lifecycle"]
        if lifecycle not in TRANSITIONS.get(current, set()):
            raise ValueError(f"{current} cannot move to {lifecycle}")
        if lifecycle in CONFIRMED and not firm_confirmed:
            raise ValueError("Firm confirmation is required before this status")
        now = _now()
        self.conn.execute(
            "UPDATE pf_account SET lifecycle=?, firm_confirmed=?, updated_at=? WHERE id=? AND tenant_id=?",
            (lifecycle, 1 if firm_confirmed else account["firm_confirmed"], now, account_id, self.tenant),
        )
        self.audit("LIFECYCLE", actor, {"from": current, "to": lifecycle, "firm_confirmed": firm_confirmed}, account_id=account_id, firm_id=account["firm_id"])
        return self.account(account_id)

    def record_snapshot(self, account_id: str, reading: dict, source: str) -> dict:
        account = self._owned(account_id)
        rules = self.rules_for(account)
        previous = self.latest_snapshot(account_id)
        now = datetime.now(timezone.utc)
        balance = float(reading["balance"])
        equity = float(reading["equity"])
        day_balance, day_equity = balance, equity
        equity_high = equity
        eod_high = equity
        if previous:
            equity_high = max(float(previous["equity_high"]), equity)
            eod_high = max(float(previous["eod_equity_high"]), equity)
            tz = ZoneInfo(rules.reset_timezone)
            prev_at = datetime.fromisoformat(previous["recorded_at"])
            if prev_at.tzinfo is None:
                prev_at = prev_at.replace(tzinfo=timezone.utc)
            if prev_at.astimezone(tz).date() == now.astimezone(tz).date():
                day_balance = float(previous["day_start_balance"])
                day_equity = float(previous["day_start_equity"])
            else:
                eod_high = max(eod_high, float(previous["equity"]))
        snapshot_id = _id()
        stamp = now.isoformat()
        self.conn.execute(
            "INSERT INTO pf_snapshot(id, tenant_id, account_id, balance, equity, floating_pnl, commission, open_positions, "
            "pending_orders, equity_high, eod_equity_high, day_start_balance, day_start_equity, recorded_at, source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                snapshot_id, self.tenant, account_id, balance, equity, float(reading.get("floating_pnl") or equity - balance),
                float(reading.get("commission") or 0), int(reading.get("open_positions") or 0), int(reading.get("pending_orders") or 0),
                equity_high, eod_high, day_balance, day_equity, stamp, source,
            ),
        )
        return _row(self.conn.execute("SELECT * FROM pf_snapshot WHERE id=?", (snapshot_id,)).fetchone())

    def evaluate_account(self, account_id: str, proposal: dict | None = None) -> dict:
        account = self._owned(account_id)
        rules = FirmRules.from_dict(self.rules_for(account).raw)
        snap = self.latest_snapshot(account_id)
        if snap is None:
            decision = evaluate(rules, None)
        else:
            recorded = datetime.fromisoformat(snap["recorded_at"])
            if recorded.tzinfo is None:
                recorded = recorded.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - recorded).total_seconds()
            proposal = proposal or {}
            decision = evaluate(rules, Observation(
                balance=float(snap["balance"]), equity=float(snap["equity"]), initial_balance=float(account["account_size"]),
                day_start_balance=float(snap["day_start_balance"]), day_start_equity=float(snap["day_start_equity"]),
                equity_high=float(snap["equity_high"]), eod_equity_high=float(snap["eod_equity_high"]),
                floating_pnl=float(snap["floating_pnl"]), commission=float(snap["commission"]),
                open_positions=int(snap["open_positions"]), pending_orders=int(snap["pending_orders"]),
                open_risk_pct=float(proposal.get("open_risk_pct") or 0), proposed_lot=float(proposal.get("proposed_lot") or 0),
                proposed_risk_pct=float(proposal.get("proposed_risk_pct") or 0), snapshot_age_seconds=age,
                news_blackout=bool(proposal.get("news_blackout")), news_calendar_available=bool(proposal.get("news_calendar_available")),
                strategy=proposal.get("strategy"), duplicate=bool(proposal.get("duplicate")),
                automation_confirmed=bool(account["automation_confirmed"]), autonomous=bool(proposal.get("autonomous", True)),
            ))
        evaluation_id = _id()
        self.conn.execute(
            "INSERT INTO pf_evaluation(id, tenant_id, account_id, snapshot_id, decision, protection, daily_drawdown_pct, "
            "max_drawdown_pct, reasons_json, close_positions, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                evaluation_id, self.tenant, account_id, None if snap is None else snap["id"],
                "ALLOW" if decision.allow else "REJECT", decision.protection, decision.daily_drawdown_pct,
                decision.max_drawdown_pct, json.dumps(list(decision.reasons)), 1 if decision.close_positions else 0, _now(),
            ),
        )
        if not decision.allow:
            self.audit("ORDER_BLOCKED", "compliance", decision.as_dict(), account_id=account_id, firm_id=account["firm_id"])
        return decision.as_dict()

    def firms(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT f.id, f.name, f.slug, f.status, r.version, r.id AS rule_version_id, r.rules_json "
            "FROM pf_firm f LEFT JOIN pf_rule_version r ON r.firm_id=f.id "
            "AND r.version=(SELECT MAX(version) FROM pf_rule_version WHERE firm_id=f.id) "
            "WHERE f.tenant_id=? ORDER BY f.name",
            (self.tenant,),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["rules"] = json.loads(item.pop("rules_json") or "{}")
            out.append(item)
        return out

    def accounts(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT a.id, a.firm_id, a.display_name, a.external_id, a.broker, a.broker_login, a.broker_server, "
            "a.environment, a.lifecycle, a.phase_label, a.account_size, a.currency, a.firm_confirmed, a.automation_confirmed, "
            "a.phase_ends_at, a.credential_cipher IS NOT NULL AS credential_configured, f.name AS firm_name "
            "FROM pf_account a JOIN pf_firm f ON f.id=a.firm_id WHERE a.tenant_id=? ORDER BY a.updated_at DESC",
            (self.tenant,),
        ).fetchall()
        return [dict(row) for row in rows]

    def account(self, account_id: str) -> dict:
        row = self.conn.execute(
            "SELECT a.id, a.firm_id, a.rule_version_id, a.display_name, a.external_id, a.broker, a.broker_login, a.broker_server, "
            "a.environment, a.lifecycle, a.phase_label, a.account_size, a.currency, a.firm_confirmed, a.automation_confirmed, "
            "a.phase_ends_at, a.status_note, a.credential_cipher IS NOT NULL AS credential_configured, f.name AS firm_name "
            "FROM pf_account a JOIN pf_firm f ON f.id=a.firm_id WHERE a.id=? AND a.tenant_id=?",
            (account_id, self.tenant),
        ).fetchone()
        if row is None:
            raise KeyError(account_id)
        return dict(row)

    def snapshots(self, account_id: str, limit: int = 180) -> list[dict]:
        self._owned(account_id)
        rows = self.conn.execute(
            "SELECT recorded_at, balance, equity, floating_pnl FROM pf_snapshot WHERE account_id=? AND tenant_id=? ORDER BY recorded_at",
            (account_id, self.tenant),
        ).fetchall()
        return [dict(row) for row in rows][-limit:]

    def deals(self, account_id: str) -> list[dict]:
        self._owned(account_id)
        rows = self.conn.execute(
            "SELECT symbol, direction, volume, profit, commission, strategy, closed_at FROM pf_deal WHERE account_id=? AND tenant_id=? ORDER BY closed_at DESC",
            (account_id, self.tenant),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_deal(self, account_id: str, deal: dict) -> None:
        self._owned(account_id)
        self.conn.execute(
            "INSERT INTO pf_deal(id, tenant_id, account_id, broker_deal_id, symbol, direction, volume, profit, commission, strategy, closed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id, broker_deal_id) DO NOTHING",
            (
                _id(), self.tenant, account_id, str(deal["broker_deal_id"]), deal["symbol"], deal["direction"],
                float(deal["volume"]), float(deal["profit"]), float(deal.get("commission") or 0), deal.get("strategy"), deal["closed_at"],
            ),
        )

    def audit_rows(self, account_id: str | None = None, limit: int = 100) -> list[dict]:
        if account_id:
            rows = self.conn.execute(
                "SELECT action, actor, detail_json, created_at, account_id FROM pf_audit WHERE tenant_id=? AND account_id=? ORDER BY created_at DESC LIMIT ?",
                (self.tenant, account_id, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT action, actor, detail_json, created_at, account_id FROM pf_audit WHERE tenant_id=? ORDER BY created_at DESC LIMIT ?",
                (self.tenant, limit),
            ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["detail"] = json.loads(item.pop("detail_json") or "{}")
            out.append(item)
        return out

    def violations(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT e.decision, e.protection, e.reasons_json, e.created_at, e.account_id, a.display_name, a.external_id "
            "FROM pf_evaluation e JOIN pf_account a ON a.id=e.account_id "
            "WHERE e.tenant_id=? AND e.decision='REJECT' ORDER BY e.created_at DESC LIMIT ?",
            (self.tenant, limit),
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
            out.append(item)
        return out

    def latest_snapshot(self, account_id: str) -> dict | None:
        return _row(self.conn.execute(
            "SELECT * FROM pf_snapshot WHERE account_id=? AND tenant_id=? ORDER BY recorded_at DESC LIMIT 1",
            (account_id, self.tenant),
        ).fetchone())

    def latest_evaluation(self, account_id: str) -> dict | None:
        row = _row(self.conn.execute(
            "SELECT decision, protection, daily_drawdown_pct, max_drawdown_pct, reasons_json, close_positions, created_at "
            "FROM pf_evaluation WHERE account_id=? AND tenant_id=? ORDER BY created_at DESC LIMIT 1",
            (account_id, self.tenant),
        ).fetchone())
        if row:
            row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
        return row

    def rules_for(self, account: dict):
        row = self.conn.execute("SELECT rules_json FROM pf_rule_version WHERE id=?", (account["rule_version_id"],)).fetchone()
        raw = json.loads(row["rules_json"]) if row else {}

        class _Rules:
            pass

        holder = _Rules()
        holder.raw = raw
        holder.reset_timezone = str(raw.get("reset_timezone") or "UTC")
        return holder

    def _owned(self, account_id: str) -> dict:
        row = _row(self.conn.execute("SELECT * FROM pf_account WHERE id=? AND tenant_id=?", (account_id, self.tenant)).fetchone())
        if row is None:
            raise KeyError(account_id)
        return row


def find_by_login(conn, login: str) -> dict | None:
    rows = conn.execute(
        "SELECT * FROM pf_account WHERE broker_login=? AND lifecycle NOT IN ('CLOSED', 'FAILED')",
        (str(login),),
    ).fetchall()
    if len(rows) != 1:
        return {"ambiguous": True} if len(rows) > 1 else None
    return dict(rows[0])
