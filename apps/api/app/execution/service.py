"""Shared entry point for Mode 1 and Mode 2.

The function sizes the order from broker contract data, checks the one account
risk budget, then either sends it or leaves it for the Windows MT5 gateway.
Live and prop accounts stay queued-or-blocked until live trading is enabled.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import replace
from datetime import datetime, timezone

from .baselines import touch_baseline
from .money import D, money, text
from .pipeline import (
    TERMINAL, acquire_lock, claim_queued, classify_broker_result, get_request, open_exposure,
    record_outcome, release_lock, upsert_request, _audit,
)
from .risk import Baselines, RiskPolicy, evaluate_entry, live_submission_allowed
from .sizing import SizeResult, account_tick_value, size_position
from .symbols import canonical_symbol


def _min_lot_max_risk_pct(profile: dict | None) -> float:
    """Ceiling for broker minimum-lot stop risk (Mode 1 and Mode 2, all symbols)."""
    raw = (os.getenv("MIN_LOT_MAX_RISK_PCT", "") or os.getenv("OUTLOOK_MIN_LOT_MAX_RISK_PCT", "")).strip()
    ceiling = float(raw) if raw else 13.0
    if profile and profile.get("max_trade_risk_pct") is not None:
        ceiling = max(ceiling, float(profile["max_trade_risk_pct"]))
    return ceiling


def _apply_min_lot_fallback(sized: SizeResult, *, equity, volume_min, ceiling_pct: float) -> tuple[SizeResult, bool]:
    """Use volume_min when 1% (or profile) sizing is below broker minimum but loss fits the ceiling."""
    if sized.ok or sized.reason != "MINIMUM_EXCEEDS_BUDGET" or sized.projected_loss is None:
        return sized, False
    projected = D(sized.projected_loss)
    cap = money(D(equity) * D(ceiling_pct) / D(100))
    if projected > cap:
        return sized, False
    return SizeResult(True, D(volume_min), sized.risk_amount, money(projected), None), True


# Backward-compatible aliases for scripts and tests
_outlook_min_lot_ceiling_pct = _min_lot_max_risk_pct
_outlook_min_lot_size = _apply_min_lot_fallback


def _row(conn, sql, params=()):
    found = conn.execute(sql, params).fetchone()
    return None if found is None else dict(found)


def _policy(row: dict | None) -> RiskPolicy:
    row = row or {}
    return RiskPolicy(
        per_trade_pct=row.get("max_trade_risk_pct") if row.get("max_trade_risk_pct") is not None else 1,
        max_positions=None if row.get("max_open_positions") is None else int(row["max_open_positions"]),
        max_aggregate_pct=row.get("max_total_risk_pct"),
        max_daily_loss_pct=row.get("max_daily_loss_pct"),
        max_weekly_loss_pct=row.get("max_weekly_loss_pct"),
        max_drawdown_pct=row.get("max_drawdown_pct"),
        max_spread_points=row.get("max_spread_points"),
        margin_floor_pct=row.get("margin_floor_pct"),
        emergency_stop=bool(row.get("emergency_stop") or 0),
        live_trading_enabled=bool(row.get("live_trading_enabled") or 0),
    )


def _baselines(row: dict | None) -> Baselines | None:
    if not row:
        return None
    return Baselines(row["peak_equity"], row["day_start_equity"], row["week_start_equity"])


def load_spec(conn, account_id: str, symbol: str) -> dict | None:
    return _row(
        conn,
        "SELECT * FROM broker_contract_specs WHERE trading_account_id=? AND canonical_symbol=?",
        (account_id, canonical_symbol(symbol)),
    )


def latest_conversion(conn, tenant_id: str, from_currency: str, to_currency: str) -> dict | None:
    return _row(
        conn,
        """SELECT * FROM currency_snapshots WHERE tenant_id=? AND from_currency=? AND to_currency=?
           AND reconciliation_status='VALIDATED' ORDER BY as_of DESC LIMIT 1""",
        (tenant_id, from_currency.upper(), to_currency.upper()),
    )


def save_spec(conn, tenant_id: str, account_id: str, spec: dict, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    symbol = canonical_symbol(spec["symbol"])
    current = load_spec(conn, account_id, symbol)
    values = (
        spec.get("broker_symbol") or symbol, spec.get("currency_profit"), spec.get("currency_margin"), spec.get("digits"),
        text(D(spec["point"])), text(D(spec["tick_size"])), text(D(spec["tick_value"])), spec["tick_value_currency"].upper(),
        text(D(spec["volume_min"])), text(D(spec["volume_max"])), text(D(spec["volume_step"])), int(spec.get("stops_level_points") or 0),
        None if spec.get("spread_points") is None else text(D(spec["spread_points"])),
        None if spec.get("margin_per_lot") is None else text(D(spec["margin_per_lot"])),
        text(D(spec.get("commission_per_lot") or 0)), now.isoformat(),
    )
    if current:
        conn.execute(
            """UPDATE broker_contract_specs SET broker_symbol=?,currency_profit=?,currency_margin=?,digits=?,point=?,tick_size=?,tick_value=?,
               tick_value_currency=?,volume_min=?,volume_max=?,volume_step=?,stops_level_points=?,spread_points=?,margin_per_lot=?,
               commission_per_lot=?,updated_at=? WHERE id=?""",
            (*values, current["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO broker_contract_specs(id,tenant_id,trading_account_id,canonical_symbol,broker_symbol,currency_profit,currency_margin,
               digits,point,tick_size,tick_value,tick_value_currency,volume_min,volume_max,volume_step,stops_level_points,spread_points,
               margin_per_lot,commission_per_lot,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), tenant_id, account_id, symbol, *values),
        )


def _refuse(conn, *, tenant_id, account_id, key, mode, symbol, direction, currency, reason, now, holder) -> dict:
    request = upsert_request(
        conn, tenant_id=tenant_id, account_id=account_id, key=key, mode=mode, symbol=symbol, direction=direction,
        currency=currency, status="PRECHECK_REJECTED", now=now, reason=reason,
    )
    _audit(conn, tenant_id, account_id, request["id"], "BROKER_ORDER_CHECK", {"accepted": False, "reason": reason}, now)
    release_lock(conn, account_id, holder)
    return {"ok": False, "error": reason, "status": "PRECHECK_REJECTED", "uncertain": False, "request_id": request["id"]}


def execute_candidate(conn, *, tenant_id: str, account_id: str, mode: str, idempotency_key: str, symbol: str,
                      direction: str, stop, target=None, price=None, spec: dict | None = None, system_mode: str,
                      terminal_mode: str | None, open_position_count: int = 0, account: dict | None = None,
                      profile: dict | None = None,                       connected: bool = True, stale: bool = False, send=None, dry_run: bool = False,
                      parent_tf: str | None = None, trigger_tf: str | None = None, outlook_horizon: str | None = None,
                      now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    from .holding_profile import holding_profile_for_execution

    holder = f"{mode}:{idempotency_key}"
    symbol = canonical_symbol(symbol)
    holding_profile = holding_profile_for_execution(
        mode=mode, symbol=symbol, parent_tf=parent_tf, trigger_tf=trigger_tf, outlook_horizon=outlook_horizon,
    )
    if not acquire_lock(conn, tenant_id, account_id, holder, now):
        return {"ok": False, "error": "EXECUTION_LOCK", "status": "LOCKED", "uncertain": False}
    existing = get_request(conn, tenant_id, idempotency_key)
    if existing and existing["status"] in TERMINAL | {"QUEUED", "SUBMITTING"}:
        release_lock(conn, account_id, holder)
        outcome = existing["status"]
        return {
            "ok": outcome in {"CONFIRMED", "QUEUED"},
            "queued": outcome == "QUEUED",
            "uncertain": outcome == "UNCERTAIN",
            "error": existing.get("rejection_reason") or ("Reconcile the broker order before retrying" if outcome == "UNCERTAIN" else None),
            "status": outcome,
            "ticket": existing.get("ticket"),
            "request_id": existing["id"],
            "volume": existing.get("volume"),
        }
    account = account if account is not None else _row(conn, "SELECT * FROM trading_accounts WHERE id=? AND tenant_id=?", (account_id, tenant_id))
    if account is None:
        release_lock(conn, account_id, holder)
        return {"ok": False, "error": "ACCOUNT_UNKNOWN", "status": "PRECHECK_REJECTED", "uncertain": False}
    profile = profile if profile is not None else _row(conn, "SELECT * FROM account_risk_profiles WHERE trading_account_id=?", (account_id,))
    policy = _policy(profile)
    currency = (account.get("account_currency") or "USD").upper()
    equity = account.get("equity")
    if equity is None:
        return _refuse(conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol,
                       direction=direction, currency=currency, reason="NO_EQUITY", now=now, holder=holder)
    touch_baseline(conn, tenant_id, account_id, currency, equity, now, "execution")
    baselines = _baselines(_row(conn, "SELECT * FROM equity_baselines WHERE trading_account_id=?", (account_id,)))
    spec = spec or load_spec(conn, account_id, symbol)
    if not spec or price is None:
        return _refuse(conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol,
                       direction=direction, currency=currency, reason="NO_CONTRACT" if not spec else "NO_QUOTE", now=now, holder=holder)
    conversion = None
    profit_currency = spec.get("currency_profit")
    if profit_currency and profit_currency.upper() != currency:
        conversion = latest_conversion(conn, tenant_id, profit_currency, currency)
    tick_value, tick_reason = account_tick_value(
        account_currency=currency,
        tick_value=spec.get("tick_value"),
        tick_value_currency=spec.get("tick_value_currency") or currency,
        profit_tick_value=spec.get("profit_tick_value"),
        profit_currency=profit_currency,
        conversion_rate=None if not conversion else conversion["rate"],
        conversion_from=None if not conversion else conversion["from_currency"],
        conversion_to=None if not conversion else conversion["to_currency"],
    )
    if tick_reason:
        return _refuse(conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol,
                       direction=direction, currency=currency, reason=tick_reason, now=now, holder=holder)
    point = D(spec.get("point") or spec.get("tick_size"))
    spread_points = D(spec.get("spread_points") or 0)
    spread_cost = (spread_points * point / D(spec["tick_size"])) * tick_value if spread_points else 0
    stops = D(spec.get("stops_level_points") or 0) * point
    sized = size_position(
        equity=equity, risk_pct=policy.per_trade_pct, price=price, stop=stop, tick_size=spec["tick_size"],
        tick_value=tick_value, volume_min=spec["volume_min"], volume_max=spec["volume_max"], volume_step=spec["volume_step"],
        commission_per_lot=spec.get("commission_per_lot") or 0, spread_cost_per_lot=spread_cost, stops_distance=stops,
    )
    min_lot_fallback = False
    if not sized.ok:
        ceiling = _min_lot_max_risk_pct(profile)
        sized, min_lot_fallback = _apply_min_lot_fallback(
            sized, equity=equity, volume_min=spec["volume_min"], ceiling_pct=ceiling,
        )
    _audit(
        conn, tenant_id, account_id, None, "RISK_CALCULATED",
        {
            "risk_amount": str(sized.risk_amount),
            "reason": sized.reason,
            "min_lot_fallback": min_lot_fallback,
            "mode": mode,
            "symbol": symbol,
        },
        now,
    )
    if not sized.ok:
        return _refuse(conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol,
                       direction=direction, currency=currency, reason=sized.reason or "VOLUME_REJECTED", now=now, holder=holder)
    _audit(conn, tenant_id, account_id, None, "VOLUME_VALIDATED", {"volume": str(sized.volume), "projected_loss": str(sized.projected_loss)}, now)
    losses, confirmed = open_exposure(conn, tenant_id, account_id)
    margin_per_lot = spec.get("margin_per_lot")
    margin_required = None if margin_per_lot is None else D(margin_per_lot) * sized.volume
    risk_policy = policy
    if min_lot_fallback:
        ceiling = _min_lot_max_risk_pct(profile)
        aggregate = policy.max_aggregate_pct
        aggregate_f = float(aggregate) if aggregate is not None else ceiling
        risk_policy = replace(
            policy,
            per_trade_pct=ceiling,
            max_aggregate_pct=max(ceiling, aggregate_f),
        )
    decision = evaluate_entry(
        policy=risk_policy, equity=equity, free_margin=account.get("free_margin") or 0, projected_loss=sized.projected_loss,
        open_losses=losses, open_positions=max(int(open_position_count), confirmed), baselines=baselines,
        spread_points=spread_points, margin_required=margin_required, connected=connected, stale=stale,
    )
    if not decision.ok:
        return _refuse(conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol,
                       direction=direction, currency=currency, reason=decision.reason or "RISK_REJECTED", now=now, holder=holder)
    if dry_run:
        release_lock(conn, account_id, holder)
        return {
            "ok": True, "status": "DRY_RUN", "submitted": False, "uncertain": False, "error": None,
            "volume": text(sized.volume), "projected_loss": text(sized.projected_loss), "risk_amount": text(sized.risk_amount),
            "currency": currency, "holding_profile": holding_profile,
        }
    allowed, gate = live_submission_allowed(
        environment=account.get("environment") or "", policy=policy, system_mode=system_mode, terminal_mode=terminal_mode,
    )
    request = upsert_request(
        conn, tenant_id=tenant_id, account_id=account_id, key=idempotency_key, mode=mode, symbol=symbol, direction=direction,
        currency=currency, status="READY", now=now, broker_symbol=spec.get("broker_symbol"), entry=D(price), stop=D(stop),
        target=None if target is None else D(target), volume=sized.volume, risk_amount=sized.risk_amount, projected_loss=sized.projected_loss,
    )
    if not allowed:
        conn.execute("UPDATE trade_requests SET status='PRECHECK_REJECTED',rejection_reason=?,updated_at=? WHERE id=?", (gate, now.isoformat(), request["id"]))
        _audit(conn, tenant_id, account_id, request["id"], "BROKER_ORDER_CHECK", {"accepted": False, "reason": gate}, now)
        release_lock(conn, account_id, holder)
        return {"ok": False, "error": gate, "status": "PRECHECK_REJECTED", "uncertain": False, "request_id": request["id"], "volume": text(sized.volume)}
    if send is None:
        conn.execute("UPDATE trade_requests SET status='QUEUED',updated_at=? WHERE id=?", (now.isoformat(), request["id"]))
        _audit(
            conn, tenant_id, account_id, request["id"], "LIVE_ORDER_SUBMISSION",
            {"queued": True, "holding_profile": holding_profile}, now,
        )
        release_lock(conn, account_id, holder)
        return {
            "ok": True, "queued": True, "status": "QUEUED", "uncertain": False, "request_id": request["id"],
            "ticket": request["id"], "volume": text(sized.volume), "projected_loss": text(sized.projected_loss),
            "currency": currency, "holding_profile": holding_profile,
        }
    conn.execute("UPDATE trade_requests SET status='SUBMITTING',updated_at=? WHERE id=?", (now.isoformat(), request["id"]))
    _audit(
        conn, tenant_id, account_id, request["id"], "LIVE_ORDER_SUBMISSION",
        {"queued": False, "volume": text(sized.volume), "holding_profile": holding_profile}, now,
    )
    try:
        result = send(sized.volume)
    except Exception as exc:
        result = {"ok": False, "uncertain": True, "error": str(exc)}
    outcome = classify_broker_result(result if isinstance(result, dict) else None)
    record_outcome(conn, request, outcome, result if isinstance(result, dict) else {"ok": False, "uncertain": True}, now)
    release_lock(conn, account_id, holder)
    failed = outcome != "CONFIRMED"
    return {
        "ok": outcome == "CONFIRMED",
        "uncertain": outcome == "UNCERTAIN",
        "error": None if not failed else (result or {}).get("error") or outcome,
        "status": outcome,
        "ticket": None if not isinstance(result, dict) else result.get("ticket"),
        "request_id": request["id"],
        "volume": text(sized.volume),
        "projected_loss": text(sized.projected_loss),
        "currency": currency,
        "retcode": None if not isinstance(result, dict) else result.get("retcode"),
        "holding_profile": holding_profile,
    }


def pull_gateway_order(conn, tenant_id: str, account_id: str) -> dict | None:
    return claim_queued(conn, tenant_id, account_id)


def _publish_confirmed_ticket(conn, request: dict, result: dict) -> None:
    """Write the broker ticket back onto the Mode 1 plan or Mode 2 outlook that queued this order."""
    ticket = str(result.get("ticket") or "")
    key = str(request.get("idempotency_key") or "")
    if not ticket or ":" not in key:
        return
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        if key.startswith("mode1:"):
            opportunity_id = key.split(":", 1)[1]
            row = conn.execute(
                "SELECT evidence_json FROM ae_opportunity WHERE id=? AND tenant_id=?",
                (opportunity_id, request["tenant_id"]),
            ).fetchone()
            if row is None:
                return
            raw = dict(row).get("evidence_json") or "{}"
            evidence = json.loads(raw)
            if not isinstance(evidence, dict):
                evidence = {}
            broker = dict(evidence.get("broker_order") or {})
            broker["ticket"] = ticket
            broker["status"] = "CONFIRMED"
            evidence["broker_order"] = broker
            conn.execute(
                "UPDATE ae_opportunity SET evidence_json=?,updated_at=? WHERE id=? AND tenant_id=?",
                (json.dumps(evidence), stamp, opportunity_id, request["tenant_id"]),
            )
        elif key.startswith("mode2:"):
            outlook_id = key.split(":")[1]
            conn.execute(
                "UPDATE ai_outlook_handoff SET execution_ref=?,lifecycle='ORDER_SUBMITTED',updated_at=? WHERE outlook_id=? AND tenant_id=?",
                (ticket, stamp, outlook_id, request["tenant_id"]),
            )
    except (sqlite3.OperationalError, json.JSONDecodeError, TypeError, ValueError):
        return


def apply_gateway_result(conn, tenant_id: str, account_id: str, request_id: str, result: dict) -> dict:
    request = _row(conn, "SELECT * FROM trade_requests WHERE id=? AND tenant_id=? AND trading_account_id=?", (request_id, tenant_id, account_id))
    if request is None:
        return {"ok": False, "error": "REQUEST_UNKNOWN"}
    if request["status"] in {"CONFIRMED", "BROKER_REJECTED", "UNCERTAIN", "RECONCILED_CLOSED"}:
        return {"ok": True, "status": request["status"], "replayed": True}
    outcome = classify_broker_result(result)
    saved = record_outcome(conn, request, outcome, result)
    if outcome == "CONFIRMED":
        _publish_confirmed_ticket(conn, saved, result)
    return {"ok": outcome == "CONFIRMED", "status": saved["status"], "uncertain": outcome == "UNCERTAIN"}
