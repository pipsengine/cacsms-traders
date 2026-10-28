"""Move an authorised AI Market Outlook campaign through risk and, when allowed, one demo or live order.

A qualified outlook stays a candidate until its own confirmation sequence reaches authorisation.
This module does not invent a fill. The campaign shows a position only after the terminal reports one.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..autonomous.config import ae_settings
from ..autonomous import opportunities as opps
from ..market.outlook.store import OutlookRepository
from ..market.provenance import values
import os

from ..market.outlook.config import outlook_settings
from .policy import horizon_slot_cap, ui_horizon
from .project import _direction, _levels, _score

_HOLD_SECONDS = 600


def _min_send_score() -> float:
    raw = os.getenv("OUTLOOK_MIN_SEND_SCORE", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return outlook_settings().min_probability


def decide_outlook_order(
    payload: dict,
    *,
    horizon: str,
    open_symbols: set[str],
    horizon_used: int,
    engine_cap: int,
    account_cap: int | None,
    exposure_percent: float | None,
    max_exposure_percent: float | None,
    slots_remaining: int,
) -> dict:
    """Return send, hold, or skip. send includes the order fields. Nothing here contacts the broker."""
    symbol = str(payload.get("symbol") or "")
    if not payload.get("qualified"):
        return {"action": "skip", "reason": "Outlook is not a qualified opportunity"}
    score = _score(payload)
    floor = _min_send_score()
    if score is None or score < floor:
        return {"action": "skip", "reason": f"Evidence score is below {floor:g}"}
    direction = _direction(payload)
    if direction not in ("BUY", "SELL"):
        return {"action": "skip", "reason": "Outlook has no tradable direction"}
    del open_symbols
    if max_exposure_percent is not None and exposure_percent is not None and exposure_percent >= max_exposure_percent:
        return {"action": "hold", "reason": "The account risk budget is already in use"}
    if slots_remaining is not None and slots_remaining <= 0:
        return {"action": "hold", "reason": "The account risk budget is already in use"}
    entry, stop, _invalidation, targets = _levels(payload)
    if entry is None or stop is None or not targets:
        return {"action": "hold", "reason": "The outlook has no entry, stop and target to size"}
    name = ui_horizon(horizon)
    cap = horizon_slot_cap(name, engine_cap=engine_cap, account_cap=account_cap)
    if cap is not None and horizon_used >= cap:
        return {"action": "hold", "reason": f"The {name.lower()} horizon already has {horizon_used} of {cap} positions"}
    word = "BULLISH" if direction == "BUY" else "BEARISH"
    plan = {
        "symbol": symbol,
        "direction": word,
        "entry_lo": entry,
        "entry_hi": entry,
        "invalidation": stop,
        "target_1": targets[0],
        "confidence": score,
        "evidence": {
            "confirmation": {"close": entry},
            "outlook_horizon": name,
            "horizon_slots_used": horizon_used,
            "exposure_percent": exposure_percent,
            "max_exposure_percent": max_exposure_percent,
        },
    }
    state, _reason, metrics = opps.risk_decision(plan, [], ae_settings(), position_cap=account_cap)
    if state != "RISK_APPROVED":
        rule = metrics.get("rule") or state
        return {"action": "hold", "reason": f"Risk has not authorised this outlook ({rule})"}
    return {
        "action": "send",
        "reason": "Confirmation complete and risk authorised",
        "order": {"symbol": symbol, "direction": word, "stop": stop, "target": targets[0]},
    }


def _recent(stamp: object, now: datetime) -> bool:
    text = str(stamp or "").strip()
    if not text:
        return False
    try:
        attempted = datetime.fromisoformat(text)
    except ValueError:
        return False
    if attempted.tzinfo is None:
        attempted = attempted.replace(tzinfo=timezone.utc)
    return (now - attempted).total_seconds() < _HOLD_SECONDS


def advance_authorised_outlooks(conn, tenant: str, account: str, mode: str, now: datetime | None = None, *, wait: bool = True) -> dict:
    """Submit at most the remaining position slots for outlooks whose confirmation sequence is complete."""
    from ..market.outlook.lifecycle import promote_reaction_handoffs

    promote_reaction_handoffs(conn, tenant, account)
    from .retry import reset_execution_retries

    reset_execution_retries(conn, tenant, account)
    from ..autonomous.portfolio import _account_row, _profile, open_position_cap
    from ..domain.mt5_connection import ensure_gateway_session
    from ..domain.mt5_execution import execution_allowed, open_market_position, terminal_order_context, terminal_trade_mode
    from ..execution.service import execute_candidate, save_spec
    from ..domain.mt5_terminal_account import read_terminal_account
    from ..domain.mt5_terminal_positions import read_terminal_positions

    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT h.outlook_id, h.run_id, h.symbol, h.horizon, h.close_at, h.evidence_json, s.payload_json "
        "FROM ai_outlook_handoff h JOIN ai_outlook_symbol s ON s.id = h.outlook_id "
        "WHERE h.tenant_id=? AND h.trading_account_id=? AND h.lifecycle='AUTHORIZATION_PENDING' "
        "AND (h.execution_ref IS NULL OR h.execution_ref='')",
        (tenant, account),
    ).fetchall()
    if not rows:
        return {"checked": 0, "sent": 0, "held": 0}
    if wait:
        try:
            ensure_gateway_session(conn, tenant)
        except Exception:
            pass
    autonomous = (mode or "").upper() in ("DEMO_AUTONOMOUS", "LIVE_AUTONOMOUS")
    positions = []
    if autonomous:
        positions, _basis = read_terminal_positions(wait=wait)
        positions = positions or []
    open_ids = {str(item.get("ticket")) for item in positions if item.get("ticket") is not None}
    ae = ae_settings()
    cap = open_position_cap(conn, tenant, account)
    allowed = execution_allowed(mode, terminal_trade_mode()) if autonomous else False
    account_row = _account_row(conn, tenant, account)
    if account_row is None:
        try:
            from ..domain.mt5_connection import read_terminal_account_for_tenant

            terminal = read_terminal_account_for_tenant(conn, tenant, force_attach=False, persist_snapshot=True)
            if terminal and terminal.get("available"):
                from ..services.trading_account_sync import sync_trading_account_from_terminal

                sync_trading_account_from_terminal(conn, tenant, terminal)
                account_row = _account_row(conn, tenant, account)
        except Exception:
            pass
    profile = _profile(conn, account_row["id"] if account_row else None)
    risk_pct = 1.0
    max_exposure = None
    if profile:
        if profile.get("max_trade_risk_pct") is not None:
            risk_pct = float(profile["max_trade_risk_pct"])
        if profile.get("max_total_risk_pct") is not None:
            max_exposure = float(profile["max_total_risk_pct"])
    exposure = None
    terminal = read_terminal_account(wait=wait) if autonomous else None
    if terminal and terminal.get("available"):
        equity = float(terminal.get("equity") or 0)
        margin = terminal.get("margin")
        if equity and margin is not None:
            exposure = round(100 * float(margin) / equity, 1)
    store = OutlookRepository(conn, (tenant, account))
    used_rows = conn.execute(
        "SELECT symbol, horizon, execution_ref FROM ai_outlook_handoff WHERE tenant_id=? AND trading_account_id=? "
        "AND execution_ref IS NOT NULL AND execution_ref != ''",
        (tenant, account),
    ).fetchall()
    used: dict[tuple[str, str], int] = {}
    for row in used_rows:
        symbol_name, horizon_name, ticket = values(row)
        if str(ticket) not in open_ids:
            continue
        key = (str(symbol_name or "").upper(), ui_horizon(str(horizon_name)))
        used[key] = used.get(key, 0) + 1
    open_risk = round(len(positions) * risk_pct, 4)
    room = None if max_exposure is None else (1 if open_risk + risk_pct <= max_exposure else 0)
    sent = held = 0
    pending = []
    for row in rows:
        outlook_id, run_id, symbol, horizon, close_at, evidence_json, payload_json = values(row)
        try:
            evidence = json.loads(evidence_json or "{}")
            payload = json.loads(payload_json or "{}")
        except ValueError:
            continue
        if not isinstance(evidence, dict):
            evidence = {}
        last_err = str(evidence.get("broker_error") or "")
        retriable = last_err in (
            "NO_CONTRACT", "NO_QUOTE", "MINIMUM_EXCEEDS_BUDGET", "MARGIN", "PER_TRADE_RISK",
            "MT5 terminal is not attached", "ACCOUNT_UNKNOWN",
        ) or last_err.startswith("Symbol ")
        if _recent(evidence.get("attempted_at"), now) and not retriable:
            held += 1
            continue
        payload = payload if isinstance(payload, dict) else {}
        payload.setdefault("symbol", symbol)
        pending.append((float(_score(payload) or 0), outlook_id, run_id, symbol, horizon, close_at, payload))
    pending.sort(key=lambda item: (str(item[3] or "").upper().startswith("XAU"), item[0]), reverse=True)
    for _score_value, outlook_id, run_id, symbol, horizon, close_at, payload in pending:
        name = ui_horizon(str(horizon))
        decision = decide_outlook_order(
            payload,
            horizon=str(horizon),
            open_symbols=set(),
            horizon_used=used.get((str(symbol or "").upper(), name), 0),
            engine_cap=ae.max_concurrent,
            account_cap=cap,
            exposure_percent=open_risk if max_exposure is not None else exposure,
            max_exposure_percent=max_exposure,
            slots_remaining=room,
        )
        outlook = {"outlook_id": outlook_id, "symbol": symbol}
        run = {"id": run_id, "horizon": horizon, "close_at": close_at}
        if decision["action"] != "send":
            if decision["action"] == "hold":
                store.save_handoff(outlook, run, "AUTHORIZATION_PENDING", {"risk_note": decision["reason"]}, None)
                held += 1
            continue
        if not allowed:
            store.save_handoff(
                outlook, run, "AUTHORIZATION_PENDING",
                {"risk_note": "Confirmation and risk are complete. The operating mode is not sending orders to this terminal."},
                None,
            )
            held += 1
            continue
        order = decision["order"]
        context = terminal_order_context(order["symbol"], order["direction"])
        send = None
        spec = price = None
        count = len(positions)
        if context.get("ok"):
            spec = context["spec"]
            price = context["price"]
            count = max(count, int(context.get("open_positions") or 0))
            broker_symbol = context["broker_symbol"]
            if account_row and spec:
                save_spec(conn, tenant, account_row["id"], spec)

            def send(volume, _order=order, _broker=broker_symbol):
                return open_market_position(
                    symbol=_order["symbol"], direction=_order["direction"], stop=float(_order["stop"]),
                    target=float(_order["target"]), risk_pct=risk_pct, volume=float(volume), broker_symbol=_broker,
                )
        elif context.get("error"):
            result = {"ok": False, "error": context["error"]}
            store.save_handoff(
                outlook, run, "AUTHORIZATION_PENDING",
                {"broker_error": context["error"], "attempted_at": now.isoformat(), "risk_note": None},
                None,
            )
            held += 1
            continue
        result = {"ok": False, "error": "ACCOUNT_UNKNOWN"}
        stamp = now.isoformat()
        if account_row:
            result = execute_candidate(
                conn, tenant_id=tenant, account_id=account_row["id"], mode="MODE_2",
                idempotency_key=f"mode2:{outlook_id}:{horizon}", symbol=order["symbol"], direction=order["direction"],
                stop=float(order["stop"]), target=float(order["target"]), price=price, spec=spec, system_mode=mode,
                terminal_mode=terminal_trade_mode(), open_position_count=count, account=account_row, profile=profile,
                connected=(account_row.get("connection_status") == "CONNECTED") or bool(context.get("ok")),
                outlook_horizon=horizon, outlook_payload=payload, send=send,
            )
        err = str(result.get("error") or "")
        if err.startswith("PRICE_OUTSIDE_ERZ"):
            store.save_handoff(
                outlook, run, "AUTHORIZATION_PENDING",
                {
                    "risk_note": "Waiting for price at the outlook entry zone before sizing a live order.",
                    "broker_error": None,
                    "attempted_at": stamp,
                },
                None,
            )
            held += 1
            continue
        if err == "MINIMUM_EXCEEDS_BUDGET":
            store.save_handoff(
                outlook, run, "AUTHORIZATION_PENDING",
                {
                    "risk_note": (
                        "Minimum broker lot at this stop exceeds the account risk ceiling "
                        f"(₦{int(float(account_row.get('equity') or 0) * 0.13):,} max at 13% on this equity)."
                    ),
                    "broker_error": None,
                    "attempted_at": stamp,
                },
                None,
            )
            held += 1
            continue
        if result.get("ok") and result.get("ticket"):
            store.save_handoff(
                outlook, run, "ORDER_SUBMITTED",
                {"risk_note": None, "broker_error": None, "attempted_at": stamp, "broker_order": result},
                str(result["ticket"]),
            )
            sent += 1
            key = (str(symbol or "").upper(), name)
            used[key] = used.get(key, 0) + 1
            if max_exposure is not None:
                open_risk = round(open_risk + risk_pct, 4)
                room = 1 if open_risk + risk_pct <= max_exposure else 0
        elif err:
            store.save_handoff(
                outlook, run, "AUTHORIZATION_PENDING",
                {"broker_error": err or "Broker did not accept the order", "attempted_at": stamp, "risk_note": None},
                None,
            )
            held += 1
    return {"checked": len(rows), "sent": sent, "held": held}
