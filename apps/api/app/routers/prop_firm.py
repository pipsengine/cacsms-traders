"""Prop firm registry, compliance preview and dashboard read model.

Figures come from stored firms, accounts, snapshots and evaluations. This router
does not invent balances and does not return broker passwords.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.database import db
from ..deps import current_user
from ..market.strength_intel_store import active_scope
from ..prop_firm.compliance import ComplianceError, FirmRules
from ..prop_firm.store import PropRepository
from ..services.access import require_permission

router = APIRouter(prefix="/api/prop-firm", tags=["Prop Firm"])
log = logging.getLogger("cacsms.prop_firm")


class FirmIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    rules: dict


class RulesIn(BaseModel):
    rules: dict


class AccountIn(BaseModel):
    firm_id: str
    rule_version_id: str | None = None
    display_name: str = Field(min_length=2, max_length=80)
    external_id: str | None = None
    broker: str = "MT5"
    broker_login: str | None = None
    broker_server: str | None = None
    password: str | None = None
    environment: str = "DEMO"
    lifecycle: str = "REGISTERED"
    phase_label: str = "Registration"
    account_size: float = Field(gt=0)
    currency: str = "USD"
    automation_confirmed: bool = False
    phase_ends_at: str | None = None


class TransitionIn(BaseModel):
    lifecycle: str
    firm_confirmed: bool = False


class SnapshotIn(BaseModel):
    balance: float
    equity: float
    floating_pnl: float | None = None
    commission: float = 0
    open_positions: int = 0
    pending_orders: int = 0


class DealIn(BaseModel):
    broker_deal_id: str
    symbol: str
    direction: str
    volume: float
    profit: float
    commission: float = 0
    strategy: str | None = None
    closed_at: str


def _scope(conn, user, permission: str) -> str:
    tenant, _account = active_scope(conn)
    if not tenant:
        raise HTTPException(503, "No tenant is configured")
    if not user["is_platform_admin"]:
        require_permission(conn, user, tenant, permission)
    return tenant


def _cipher(password: str) -> str:
    secret = os.getenv("PROP_FIRM_SECRET") or os.getenv("SMTP_ENCRYPTION_KEY") or ""
    if not secret:
        raise HTTPException(400, "PROP_FIRM_SECRET is not configured, so a broker password cannot be stored")
    from cryptography.fernet import Fernet

    key = hashlib.sha256(b"cacsms-prop-firm:v1\0" + secret.encode()).digest()
    token = Fernet(base64.urlsafe_b64encode(key)).encrypt(password.encode()).decode("ascii")
    return f"fernet:v1:{token}"


def _actor(user) -> str:
    return str(user.get("username") or user.get("id") or "user")


def _days_left(stamp: str | None) -> int | None:
    if not stamp:
        return None
    try:
        end = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, (end - datetime.now(timezone.utc)).days)


def _status(account: dict, evaluation: dict | None) -> str:
    if account["lifecycle"] in ("SUSPENDED", "FAILED", "CLOSED"):
        return "Suspended"
    if evaluation and evaluation["protection"] in ("SUSPENDED", "EMERGENCY", "REDUCED"):
        return "At Risk"
    if account["lifecycle"] in ("FUNDED", "ACTIVE"):
        return "Trading"
    return "On Track"


def overview_payload(repo: PropRepository) -> dict:
    firms = repo.firms()
    accounts = repo.accounts()
    rows = []
    equity = floating = 0.0
    in_profit = 0
    violations = 0
    for account in accounts:
        full = repo.account(account["id"])
        snap = repo.latest_snapshot(account["id"])
        evaluation = repo.latest_evaluation(account["id"])
        rules = {}
        try:
            rules = FirmRules.from_dict(repo.rules_for(full).raw).__dict__
        except ComplianceError:
            rules = {}
        balance = float(snap["balance"]) if snap else None
        mark = float(snap["equity"]) if snap else None
        pnl = None if snap is None else round(float(snap["floating_pnl"]), 2)
        if mark is not None:
            equity += mark
            floating += pnl or 0
            if (pnl or 0) > 0:
                in_profit += 1
        if evaluation and evaluation["decision"] == "REJECT":
            violations += 1
        target = float(rules.get("profit_target_pct") or 0)
        progress = None
        if snap and account["account_size"]:
            progress = round(100 * (float(snap["equity"]) - float(account["account_size"])) / float(account["account_size"]), 2)
        rows.append({
            "id": account["id"],
            "firm": account["firm_name"],
            "external_id": account["external_id"],
            "environment": account["environment"],
            "lifecycle": account["lifecycle"],
            "phase": account["phase_label"],
            "balance": balance,
            "equity": mark,
            "daily_pnl": pnl,
            "daily_drawdown_pct": None if not evaluation else evaluation["daily_drawdown_pct"],
            "max_drawdown_pct": None if not evaluation else evaluation["max_drawdown_pct"],
            "daily_loss_pct": rules.get("daily_loss_pct"),
            "max_loss_pct": rules.get("max_loss_pct"),
            "profit_target_pct": target or None,
            "progress_pct": progress,
            "days_left": _days_left(account["phase_ends_at"]),
            "status": _status(account, evaluation),
            "protection": None if not evaluation else evaluation["protection"],
            "automation_confirmed": bool(account["automation_confirmed"]),
            "credential_configured": bool(account["credential_configured"]),
        })
    safe = violations == 0 and all(row["status"] != "At Risk" for row in rows)
    return {
        "summary": {
            "accounts": len(accounts),
            "firms": len(firms),
            "evaluation": sum(1 for row in rows if str(row["lifecycle"]).startswith("EVALUATION")),
            "funded": sum(1 for row in rows if row["lifecycle"] in ("FUNDED", "ACTIVE")),
            "equity": round(equity, 2) if accounts else None,
            "open_pnl": round(floating, 2) if accounts else None,
            "in_profit": in_profit,
            "compliant": safe if accounts else None,
        },
        "accounts": rows,
        "firms": firms,
    }


@router.get("/overview")
def overview(user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.read"))
        return overview_payload(repo)


@router.get("/firms")
def firms(user=Depends(current_user)):
    with db() as conn:
        return {"firms": PropRepository(conn, _scope(conn, user, "accounts.read")).firms()}


@router.post("/firms")
def create_firm(body: FirmIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        try:
            created = repo.create_firm(body.name, body.rules, _actor(user))
            conn.commit()
        except ComplianceError as exc:
            raise HTTPException(400, str(exc)) from exc
        return created


@router.post("/firms/{firm_id}/rules")
def version_rules(firm_id: str, body: RulesIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        try:
            created = repo.add_rules(firm_id, body.rules, _actor(user))
            conn.commit()
        except KeyError:
            raise HTTPException(404, "Firm not found") from None
        except ComplianceError as exc:
            raise HTTPException(400, str(exc)) from exc
        return created


@router.get("/accounts")
def accounts(user=Depends(current_user)):
    with db() as conn:
        return {"accounts": PropRepository(conn, _scope(conn, user, "accounts.read")).accounts()}


@router.post("/accounts")
def create_account(body: AccountIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        payload = body.model_dump()
        if body.password:
            payload["credential_cipher"] = _cipher(body.password)
        payload.pop("password", None)
        try:
            created = repo.create_account(payload, _actor(user))
            conn.commit()
        except KeyError:
            raise HTTPException(404, "Firm or rule version not found") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return created


@router.post("/accounts/{account_id}/transition")
def transition(account_id: str, body: TransitionIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        try:
            updated = repo.transition(account_id, body.lifecycle, _actor(user), firm_confirmed=body.firm_confirmed)
            conn.commit()
        except KeyError:
            raise HTTPException(404, "Account not found") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return updated


@router.post("/accounts/{account_id}/snapshots")
def snapshot(account_id: str, body: SnapshotIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        try:
            saved = repo.record_snapshot(account_id, body.model_dump(), "manual")
            decision = repo.evaluate_account(account_id, {"autonomous": False})
            conn.commit()
        except KeyError:
            raise HTTPException(404, "Account not found") from None
        return {"snapshot": saved, "compliance": decision}


@router.get("/accounts/{account_id}/performance")
def performance(account_id: str, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.read"))
        try:
            deals = repo.deals(account_id)
            snaps = repo.snapshots(account_id)
        except KeyError:
            raise HTTPException(404, "Account not found") from None
        wins = [deal for deal in deals if deal["profit"] > 0]
        losses = [deal for deal in deals if deal["profit"] < 0]
        gross_win = sum(deal["profit"] for deal in wins)
        gross_loss = abs(sum(deal["profit"] for deal in losses))
        return {
            "snapshots": snaps,
            "deals": deals,
            "win_rate": None if not deals else round(100 * len(wins) / len(deals), 1),
            "profit_factor": None if not gross_loss else round(gross_win / gross_loss, 2),
            "realized_pnl": round(sum(deal["profit"] for deal in deals), 2) if deals else None,
        }


@router.post("/accounts/{account_id}/deals")
def record_deal(account_id: str, body: DealIn, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "accounts.manage"))
        try:
            repo.record_deal(account_id, body.model_dump())
            conn.commit()
        except KeyError:
            raise HTTPException(404, "Account not found") from None
        return {"ok": True}


@router.get("/accounts/{account_id}/audit")
def account_audit(account_id: str, user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "audit.read"))
        return {"events": repo.audit_rows(account_id)}


@router.get("/violations")
def violations(user=Depends(current_user)):
    with db() as conn:
        repo = PropRepository(conn, _scope(conn, user, "audit.read"))
        return {"violations": repo.violations(), "events": repo.audit_rows()}
