"""Risk & Portfolio read model.

Assembles the synced trading account, the configured risk profile and the autonomous engine's
analysis-only plans and Stage 8 decisions. It does not size lots, invent an equity curve, or
authorise a broker order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import OPP_TYPES, ae_settings
from .opportunities import SIGN, currencies
from .store import AERepository

RISK_STATES = ("RISK_APPROVED", "RISK_DEFERRED", "RISK_REJECTED")
ACCOUNT_STALE_SECONDS = 15 * 60
SIZE_NOTE = "Lot size is not calculated. The risk gate does not read contract size, tick value or account-currency conversion."
CAPACITY_BASIS = "Open analysis-only plans against the concurrent-plan limit. This is not a dollar risk budget and not permission to trade."
OUTCOME_BASIS = "Closed analysis-only plans in the last 30 days. Not broker-account performance."


def net_exposure(plans: list[dict]) -> dict[str, int]:
    """Net shadow-plan count per currency. A bullish plan is +1 base and -1 quote. Not lots."""
    exposure: dict[str, int] = {}
    for plan in plans:
        direction = plan.get("direction")
        symbol = plan.get("symbol") or ""
        if direction not in SIGN or len(symbol) < 6:
            continue
        sign = SIGN[direction]
        base, quote = currencies(symbol)
        exposure[base] = exposure.get(base, 0) + sign
        exposure[quote] = exposure.get(quote, 0) - sign
    return {k: v for k, v in exposure.items() if v}


def slot_capacity(used: int, limit: int) -> dict:
    used = max(0, int(used))
    limit = max(0, int(limit))
    return {
        "used": used,
        "limit": limit,
        "available": max(0, limit - used) if limit else None,
        "used_pct": round(100 * used / limit, 1) if limit else None,
        "basis": CAPACITY_BASIS,
    }


def shadow_outcomes(closed: list[dict]) -> dict:
    outcomes: dict[str, int] = {}
    multiples: list[float] = []
    by_type: dict[str, dict] = {}
    for row in closed:
        outcome = row.get("outcome") or "UNKNOWN"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        raw = ((row.get("evidence") or {}).get("outcome") or {}).get("r_multiple")
        if isinstance(raw, (int, float)):
            multiples.append(float(raw))
        bucket = by_type.setdefault(row.get("opp_type") or "UNKNOWN", {"closed": 0, "target_1": 0, "stopped": 0})
        bucket["closed"] += 1
        bucket["target_1"] += int(outcome == "TARGET_1")
        bucket["stopped"] += int(outcome == "STOPPED")
    resolved = outcomes.get("TARGET_1", 0) + outcomes.get("STOPPED", 0)
    return {
        "closed_30d": len(closed),
        "resolved": resolved,
        "hit_rate": round(100 * outcomes.get("TARGET_1", 0) / resolved, 1) if resolved else None,
        "avg_r": round(sum(multiples) / len(multiples), 2) if multiples else None,
        "counts": outcomes,
        "profit_factor": None,
        "sharpe": None,
        "total_return_pct": None,
        "max_drawdown_pct": None,
        "daily_drawdown_pct": None,
        "basis": OUTCOME_BASIS,
        "by_type": by_type,
    }


def decision_row(transition: dict, opportunity: dict | None) -> dict:
    evidence = transition.get("evidence") or {}
    opp = opportunity or {}
    opp_type = opp.get("opp_type")
    return {
        "id": transition.get("id"),
        "opportunity_id": transition.get("entity_id"),
        "at": transition.get("evidence_at") or transition.get("created_at"),
        "symbol": transition.get("symbol") or opp.get("symbol"),
        "direction": opp.get("direction"),
        "type": opp_type,
        "type_label": OPP_TYPES.get(opp_type, opp_type),
        "tit_level": opp.get("tit_level"),
        "state": transition.get("to_state"),
        "reason_code": transition.get("reason_code"),
        "detail": transition.get("detail"),
        "rule": evidence.get("rule"),
        "reward_risk": evidence.get("reward_risk", opp.get("reward_risk")),
        "confidence": evidence.get("confidence", opp.get("confidence")),
        "currency": evidence.get("currency"),
        "position_size": None,
        "stop_distance": None,
        "position_size_note": SIZE_NOTE,
        "shadow": True,
        "broker_order": None,
    }


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _account_row(conn, tenant_id: str, account_id: str) -> dict | None:
    if not tenant_id:
        return None
    rows = [dict(r) for r in conn.execute(
        "SELECT id, account_name, account_number, broker, server, environment, account_currency, balance, equity, margin, "
        "free_margin, leverage, connection_status, last_synced_at FROM trading_accounts WHERE tenant_id=?",
        (tenant_id,),
    ).fetchall()]
    if not rows:
        return None
    wanted = (account_id or "").strip()
    for row in rows:
        number = str(row.get("account_number") or "")
        if row["id"] == wanted or number == wanted or (number and wanted.endswith("/" + number)):
            return row
    connected = [row for row in rows if row.get("connection_status") == "CONNECTED"]
    return (connected or rows)[0]


def _profile(conn, account_pk: str | None) -> dict | None:
    if not account_pk:
        return None
    row = conn.execute(
        "SELECT max_open_positions, max_total_risk_pct, max_trade_risk_pct, max_daily_loss_pct, max_total_loss_pct, "
        "profit_target_pct, weekend_holding_allowed FROM account_risk_profiles WHERE trading_account_id=?",
        (account_pk,),
    ).fetchone()
    return dict(row) if row else None


def _stale(synced_at: str | None, now: datetime) -> bool:
    if not synced_at:
        return True
    try:
        stamp = datetime.fromisoformat(synced_at)
    except ValueError:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (now - stamp).total_seconds() > ACCOUNT_STALE_SECONDS


def build_portfolio(conn, repo: AERepository, now: datetime) -> dict:
    ae = ae_settings()
    account = _account_row(conn, repo.tenant, repo.account)
    profile = _profile(conn, account["id"] if account else None)
    balance = _num(account.get("balance")) if account else None
    equity = _num(account.get("equity")) if account else None
    margin = _num(account.get("margin")) if account else None
    free_margin = _num(account.get("free_margin")) if account else None
    stale = _stale(account.get("last_synced_at") if account else None, now)
    floating = equity - balance if equity is not None and balance is not None else None

    active = repo.active_opportunities()
    plans = [o for o in active if o.get("stage") == "EXECUTION"]
    by_id = {o["id"]: o for o in repo.opportunities(limit=500)}
    by_id.update({o["id"]: o for o in active})
    exposure = net_exposure(plans)
    capacity = slot_capacity(len(plans), ae.max_concurrent)
    transitions = repo.transitions(entity_type="OPPORTUNITY", limit=200)
    decisions = [
        decision_row(t, by_id.get(t.get("entity_id")))
        for t in transitions
        if t.get("to_state") in RISK_STATES
    ]
    counts = {"RISK_APPROVED": 0, "RISK_DEFERRED": 0, "RISK_REJECTED": 0}
    for row in decisions:
        if row["state"] in counts:
            counts[row["state"]] += 1

    type_counts: dict[str, dict] = {key: {"active": 0, "shadow": 0} for key in OPP_TYPES}
    for opp in active:
        bucket = type_counts.setdefault(opp.get("opp_type") or "UNKNOWN", {"active": 0, "shadow": 0})
        bucket["active"] += 1
        if opp.get("stage") == "EXECUTION":
            bucket["shadow"] += 1
    campaigns = []
    for key, label in OPP_TYPES.items():
        counts_for = type_counts.get(key) or {"active": 0, "shadow": 0}
        campaigns.append({
            "type": key,
            "label": label,
            "active_plans": counts_for["active"],
            "shadow_plans": counts_for["shadow"],
            "slot_share_pct": round(100 * counts_for["shadow"] / ae.max_concurrent, 1) if ae.max_concurrent else None,
            "status": "ACTIVE" if counts_for["shadow"] else "STANDBY" if counts_for["active"] else "IDLE",
            "dollar_allocation": None,
        })
    total_shadow = sum(c["shadow_plans"] for c in campaigns) or 0
    distribution = [
        {"type": c["type"], "label": c["label"], "plans": c["shadow_plans"],
         "share_pct": round(100 * c["shadow_plans"] / total_shadow, 1) if total_shadow else 0}
        for c in campaigns if c["shadow_plans"]
    ]
    abs_exposure = sum(abs(v) for v in exposure.values())
    currencies_out = [
        {"currency": name, "net_plans": value, "share_pct": round(100 * abs(value) / abs_exposure, 1) if abs_exposure else 0}
        for name, value in sorted(exposure.items(), key=lambda item: -abs(item[1]))
    ]
    most = currencies_out[0]["currency"] if currencies_out else None
    floor = min((abs(item["net_plans"]) for item in currencies_out), default=0)
    tied = [item["currency"] for item in currencies_out if abs(item["net_plans"]) == floor]
    least = tied[0] if len(currencies_out) > 1 and len(tied) == 1 else None
    closed = repo.closed_opportunities((now - timedelta(days=30)).isoformat())
    limits = {
        "max_open_positions": profile.get("max_open_positions") if profile else None,
        "max_total_risk_pct": profile.get("max_total_risk_pct") if profile else None,
        "max_trade_risk_pct": profile.get("max_trade_risk_pct") if profile else None,
        "max_daily_loss_pct": profile.get("max_daily_loss_pct") if profile else None,
        "max_total_loss_pct": profile.get("max_total_loss_pct") if profile else None,
        "profit_target_pct": profile.get("profit_target_pct") if profile else None,
        "weekend_holding_allowed": bool(profile.get("weekend_holding_allowed")) if profile else None,
        "max_concurrent": ae.max_concurrent,
        "max_currency_exposure": ae.max_currency_exposure,
        "min_reward_risk": ae.min_reward_risk,
        "min_confidence": ae.min_confidence,
    }
    return {
        "account": None if not account else {
            "id": account["id"],
            "name": account.get("account_name"),
            "number": account.get("account_number"),
            "broker": account.get("broker"),
            "server": account.get("server"),
            "environment": account.get("environment"),
            "currency": account.get("account_currency") or "USD",
            "balance": balance,
            "equity": equity,
            "margin": margin,
            "free_margin": free_margin,
            "leverage": account.get("leverage"),
            "floating_pnl": floating,
            "floating_pnl_basis": "Equity minus balance on the last account sync. Deposits and withdrawals are included in that difference.",
            "margin_used_pct": round(100 * margin / equity, 1) if margin is not None and equity else None,
            "free_margin_pct": round(100 * free_margin / equity, 1) if free_margin is not None and equity else None,
            "last_synced_at": account.get("last_synced_at"),
            "connection_status": account.get("connection_status"),
            "stale": stale,
            "source": "trading_account_sync",
        },
        "limits": limits,
        "capacity": capacity,
        "exposure": {
            "basis": "Net count of analysis-only plans. Not broker lots and not a correlation matrix.",
            "currencies": currencies_out,
            "most_exposed": most,
            "least_exposed": least,
            "plans": len(plans),
        },
        "campaigns": campaigns,
        "distribution": distribution,
        "decisions": decisions[:40],
        "decision_counts": counts,
        "outcomes": shadow_outcomes(closed),
        "equity_history": {
            "points": [{"t": account.get("last_synced_at"), "equity": equity}] if account and equity is not None and account.get("last_synced_at") else [],
            "note": "Only the latest synced equity is stored. Earlier points are not invented.",
        },
        "unavailable": [
            "lot_size",
            "dollar_risk_budget",
            "equity_curve_history",
            "daily_drawdown",
            "profit_factor",
            "sharpe",
            "pair_correlation",
            "broker_positions",
        ],
        "execution": "BLOCKED",
        "execution_note": "SHADOW / analysis-only. Risk decisions are simulated and are not permission to send a broker order.",
    }
