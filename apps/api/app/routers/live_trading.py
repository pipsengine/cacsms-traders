"""Account-currency risk report and the audited live-trading switch.

Live order submission stays off until the account owner turns it on. These
routes do not place a broker order by themselves.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..core.audit import write_audit
from ..core.config import SESSION_COOKIE
from ..core.database import db
from ..core.security import iso, token_hash
from ..deps import current_user
from ..execution.money import money
from ..execution.service import execute_candidate
from ..services.access import require_permission

router = APIRouter(prefix="/tenants/{tenant_id}/accounts/{account_id}", tags=["Live trading"])


class Toggle(BaseModel):
    enabled: bool


class EvaluateIn(BaseModel):
    mode: str = Field(pattern=r"^MODE_[12]$")
    symbol: str
    direction: str = Field(pattern=r"^(BULLISH|BEARISH)$")
    price: Decimal
    stop: Decimal
    target: Decimal | None = None
    system_mode: str = "ANALYSIS_ONLY"


def _account(conn, tenant_id: str, account_id: str) -> dict:
    row = conn.execute("SELECT * FROM trading_accounts WHERE id=? AND tenant_id=?", (account_id, tenant_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Account not found")
    return dict(row)


def _report(conn, tenant_id: str, account_id: str) -> dict:
    account = _account(conn, tenant_id, account_id)
    profile = conn.execute("SELECT * FROM account_risk_profiles WHERE trading_account_id=?", (account_id,)).fetchone()
    profile = dict(profile) if profile else {}
    baseline = conn.execute("SELECT * FROM equity_baselines WHERE trading_account_id=?", (account_id,)).fetchone()
    events = [
        dict(row) for row in conn.execute(
            "SELECT stage, detail_json, created_at FROM execution_audit WHERE tenant_id=? AND trading_account_id=? ORDER BY created_at DESC LIMIT 30",
            (tenant_id, account_id),
        ).fetchall()
    ]
    equity = account.get("equity")
    per_trade = profile.get("max_trade_risk_pct")
    available = None if equity is None or per_trade is None else str(money(Decimal(str(equity)) * Decimal(str(per_trade)) / Decimal(100)))
    environment = account.get("environment") or ""
    link = "DISCONNECTED" if (account.get("connection_status") or "").upper() != "CONNECTED" else "CONNECTED"
    execution = "EMERGENCY_STOP" if profile.get("emergency_stop") else "LIVE_EXECUTION" if profile.get("live_trading_enabled") and environment in ("LIVE", "PROP_FIRM") else "SIMULATION"
    return {
        "account_id": account_id,
        "currency": account.get("account_currency"),
        "environment": environment,
        "balance": account.get("balance"),
        "equity": equity,
        "free_margin": account.get("free_margin"),
        "margin": account.get("margin"),
        "margin_level": account.get("margin_level"),
        "floating_pnl": account.get("floating_pnl"),
        "leverage": account.get("leverage"),
        "link_state": link,
        "execution_state": execution,
        "live_trading_enabled": bool(profile.get("live_trading_enabled")),
        "emergency_stop": bool(profile.get("emergency_stop")),
        "available_risk": available,
        "baseline": None if baseline is None else dict(baseline),
        "events": events,
    }


@router.get("/report")
def report(tenant_id: str, account_id: str, user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "accounts.read")
        return _report(conn, tenant_id, account_id)


@router.post("/live-trading")
def set_live_trading(tenant_id: str, account_id: str, body: Toggle, user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "accounts.enable_live")
        account = _account(conn, tenant_id, account_id)
        before = conn.execute("SELECT live_trading_enabled FROM account_risk_profiles WHERE trading_account_id=?", (account_id,)).fetchone()
        conn.execute(
            "UPDATE account_risk_profiles SET live_trading_enabled=?, updated_at=? WHERE trading_account_id=? AND tenant_id=?",
            (1 if body.enabled else 0, iso(), account_id, tenant_id),
        )
        write_audit(
            conn, tenant_id, user["id"], "LIVE_TRADING_ENABLED" if body.enabled else "LIVE_TRADING_DISABLED",
            "TradingAccount", account_id, before={"live_trading_enabled": None if before is None else before["live_trading_enabled"]},
            after={"live_trading_enabled": body.enabled, "environment": account.get("environment")},
        )
        return _report(conn, tenant_id, account_id)


@router.post("/emergency-stop")
def set_emergency_stop(tenant_id: str, account_id: str, body: Toggle, user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "accounts.manage")
        _account(conn, tenant_id, account_id)
        conn.execute(
            "UPDATE account_risk_profiles SET emergency_stop=?, updated_at=? WHERE trading_account_id=? AND tenant_id=?",
            (1 if body.enabled else 0, iso(), account_id, tenant_id),
        )
        write_audit(
            conn, tenant_id, user["id"], "EMERGENCY_STOP" if body.enabled else "EMERGENCY_STOP_CLEARED",
            "TradingAccount", account_id, after={"emergency_stop": body.enabled},
        )
        return _report(conn, tenant_id, account_id)


@router.post("/risk/evaluate")
def evaluate(tenant_id: str, account_id: str, body: EvaluateIn, user=Depends(current_user)):
    """Size and risk-check one candidate. This does not submit an order."""
    with db() as conn:
        require_permission(conn, user, tenant_id, "accounts.read")
        _account(conn, tenant_id, account_id)
        result = execute_candidate(
            conn, tenant_id=tenant_id, account_id=account_id, mode=body.mode,
            idempotency_key=f"evaluate:{body.mode}:{body.symbol}:{body.direction}:{body.stop}",
            symbol=body.symbol, direction=body.direction, stop=body.stop, target=body.target, price=body.price,
            system_mode="ANALYSIS_ONLY", terminal_mode=None, send=None, dry_run=True,
        )
        result["submitted"] = False
        return result


@router.websocket("/stream")
async def stream(websocket: WebSocket, tenant_id: str, account_id: str):
    await websocket.accept()
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        await websocket.close(code=4401)
        return
    with db() as conn:
        user = conn.execute(
            """SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.status='ACTIVE'""",
            (token_hash(token), iso()),
        ).fetchone()
        if user is None:
            await websocket.close(code=4401)
            return
        try:
            require_permission(conn, dict(user), tenant_id, "accounts.read")
            _account(conn, tenant_id, account_id)
        except HTTPException:
            await websocket.close(code=4403)
            return
    try:
        while True:
            with db() as conn:
                payload = _report(conn, tenant_id, account_id)
            await websocket.send_json(payload)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
