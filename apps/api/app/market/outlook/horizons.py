"""Candle-close scheduling for weekly, monthly and XAUUSD H8 outlooks.

Closes come from stored broker bars (`is_closed=1`, `close_time`), not from the browser and not from a fixed local clock.
Daily keeps its New York 17:00 trading-day identity so existing published outlooks stay addressable.
When several horizons close together, the caller freezes one snapshot and processes Monthly → Weekly → Daily → H8.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from ..h8_bos_btl import weekly_core, weekly_live
from ..h8_bos_btl_config import h8_bos_btl_settings
from ..provenance import values
from ..scanner_analytics import Bar
from ..scanner_config import GOLD
from .lifecycle import lifecycle_for
from .store import DONE_STATES, now_iso

HORIZON_ORDER = ("MONTHLY", "WEEKLY", "DAILY", "H8")
PREFIX = {"WEEKLY": "W1", "MONTHLY": "MN", "H8": "H8"}
TIMEFRAME = {"MONTHLY": "MN", "WEEKLY": "W1", "DAILY": "D1", "H8": "H8"}
SPAN = {"MONTHLY": timedelta(days=31), "WEEKLY": timedelta(days=7), "DAILY": timedelta(days=1), "H8": timedelta(hours=8)}
CLOCK = {"MONTHLY": "EURUSD", "WEEKLY": "EURUSD", "DAILY": "EURUSD", "H8": GOLD}
LOOKBACK = {"MONTHLY": 6, "WEEKLY": 12, "H8": 48}
CATCHUP = {"MONTHLY": 2, "WEEKLY": 2, "H8": 3}


def ordered(names: list[str] | tuple[str, ...]) -> list[str]:
    rank = {name: i for i, name in enumerate(HORIZON_ORDER)}
    return sorted(names, key=lambda name: rank[name])


def _add_months(stamp: datetime, months: int) -> datetime:
    month = stamp.month - 1 + months
    year = stamp.year + month // 12
    month = month % 12 + 1
    return stamp.replace(year=year, month=month)


def project_next_close(closes: list[datetime], horizon: str, now: datetime) -> datetime | None:
    """Next broker close after ``now``, using the cadence of the stored closes.

    H8 only lands on a weekday and hour that those closes actually use, so a weekend gap is not filled with bars the broker does not print.
    """
    if horizon not in PREFIX or not closes:
        return None
    latest = max(closes)
    if horizon == "MONTHLY":
        nxt = _add_months(latest, 1)
        for _ in range(18):
            if nxt > now:
                return nxt
            nxt = _add_months(nxt, 1)
        return nxt
    if horizon == "WEEKLY":
        nxt = latest + timedelta(days=7)
        for _ in range(12):
            if nxt > now:
                return nxt
            nxt += timedelta(days=7)
        return nxt
    slots = {(c.weekday(), c.hour, c.minute) for c in closes}
    nxt = latest
    for _ in range(64):
        nxt += timedelta(hours=8)
        if nxt > now and (nxt.weekday(), nxt.hour, nxt.minute) in slots:
            return nxt
    return None


def run_key(horizon: str, close: datetime) -> str:
    """Idempotency key for one finalized candle. Daily is not prefixed — it stays the trading date."""
    stamp = close.astimezone(timezone.utc).isoformat()
    return f"{PREFIX[horizon]}|{stamp}"


def coincident(closes: dict[str, datetime], grace: timedelta) -> bool:
    if len(closes) < 2:
        return False
    stamps = list(closes.values())
    return max(stamps) - min(stamps) <= grace


def trim_bars(bars: dict[str, dict[str, list[Bar]]], cutoff: datetime) -> dict[str, dict[str, list[Bar]]]:
    """Drop any bar that opened at or after the horizon's own close (no look-ahead when a snapshot is shared)."""
    return {sym: {tf: [b for b in hist if b.t < cutoff] for tf, hist in tfs.items()} for sym, tfs in bars.items()}


def _as_utc(raw: str) -> datetime:
    t = datetime.fromisoformat(str(raw))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def recent_closes(conn, timeframe: str, symbol: str, until: datetime, limit: int) -> list[datetime]:
    """Finalized broker close timestamps, newest first. Empty when the candle table cannot be read."""
    try:
        from ..repository import MarketRepository
        from .service import _scope_sql

        repo = MarketRepository(conn)
        if repo is None or not getattr(repo, "conn", None):
            return []
        table, scope, sp = _scope_sql(repo)
        sql = (
            f"SELECT close_time FROM {table} WHERE {scope}symbol=? AND timeframe=? AND is_closed=1 AND close_time<=? "
            "ORDER BY close_time DESC LIMIT ?"
        )
        rows = repo.conn.execute(sql, (*sp, symbol, timeframe, until.isoformat(), limit)).fetchall()
    except Exception:
        return []
    out = []
    for row in rows:
        try:
            out.append(_as_utc(values(row)[0]))
        except (TypeError, ValueError):
            continue
    return out


def pending_closes(conn, store, horizon: str, now: datetime, grace_minutes: float) -> list[datetime]:
    """Missed finalized closes, newest first, bounded so a restart cannot replay the whole history.

    The newest close is the one the operator sees. Older missed closes are recovered after it.
    """
    if horizon not in PREFIX:
        return []
    until = now - timedelta(minutes=grace_minutes)
    found = recent_closes(conn, TIMEFRAME[horizon], CLOCK[horizon], until, LOOKBACK[horizon])
    pending = []
    for close in found:
        key = run_key(horizon, close)
        run = store.run(key, "LIVE", horizon)
        deadline = close + SPAN[horizon]
        if run and run["state"] in DONE_STATES + ("MISSED",):
            continue
        if run and now >= deadline and run["state"] not in DONE_STATES:
            store.update_run(run["id"], state="MISSED", error="Next candle closed before this outlook was published",
                             log={"at": now_iso(), "state": "MISSED", "message": f"{horizon} close {close.isoformat()} missed"})
            continue
        if run and run["state"] == "FAILED" and int(run["attempts"] or 0) >= 3 and now >= deadline:
            continue
        pending.append(close)
    return pending[: CATCHUP[horizon]]


def due_closes(conn, store, now: datetime, grace_minutes: float) -> dict[str, datetime]:
    """The newest outstanding close per non-daily horizon."""
    out = {}
    for horizon in ("MONTHLY", "WEEKLY", "H8"):
        pending = pending_closes(conn, store, horizon, now, grace_minutes)
        if pending:
            out[horizon] = pending[0]
    return out


def freeze_at(conn, cutoff: datetime, origin: str, symbols, horizon: str, key: str) -> tuple[dict, dict]:
    """Closed-bar snapshot as of one broker candle close. The id is a content hash."""
    from ..repository import MarketRepository
    from ..scanner_engine import BARS
    from .service import candles_until

    repo = MarketRepository(conn)
    by_tf = {tf: candles_until(repo, tf, n, symbols, cutoff) for tf, n in BARS.items()}
    bars = {sym: {tf: by_tf[tf].get(sym, []) for tf in BARS} for sym in symbols}
    return _pack(bars, cutoff, origin, horizon, key, getattr(repo, "provider", None), getattr(repo, "account_id", None), getattr(repo, "snapshot_id", None)), bars


def repack(bars: dict, cutoff: datetime, origin: str, horizon: str, key: str, provider: str | None, account: str | None) -> tuple[dict, dict]:
    trimmed = trim_bars(bars, cutoff)
    return _pack(trimmed, cutoff, origin, horizon, key, provider, account, None), trimmed


def _pack(bars: dict, cutoff: datetime, origin: str, horizon: str, key: str, provider, account, market_snapshot_id) -> dict:
    symbols = {}
    for sym, tfs in bars.items():
        symbols[sym] = {
            tf: {"bars": len(hist), "first": hist[0].t.isoformat() if hist else None, "last": hist[-1].t.isoformat() if hist else None,
                 "last_close": hist[-1].c if hist else None}
            for tf, hist in tfs.items()
        }
    digest = hashlib.sha256(json.dumps(
        {"key": key, "horizon": horizon, "cutoff": cutoff.isoformat(), "origin": origin, "provider": provider, "account": account, "symbols": symbols},
        sort_keys=True).encode()).hexdigest()
    return {
        "snapshot_id": f"snap-{horizon.lower()}-{digest[:12]}",
        "analysis_date": key,
        "horizon": horizon,
        "origin": origin,
        "cutoff": cutoff.isoformat(),
        "frozen_at": now_iso(),
        "provider": provider,
        "account_id": account,
        "market_snapshot_id": market_snapshot_id,
        "symbols": symbols,
    }


def evidence_balance(outlook: dict) -> dict:
    missing = [c["note"] for c in (outlook.get("data_quality") or {}).get("checks") or [] if not (c.get("complete") and c.get("fresh"))]
    return {
        "supporting": len(outlook.get("evidence_for") or []),
        "conflicting": len(outlook.get("evidence_against") or []),
        "missing": missing,
    }


def decorate(outlook: dict, horizon: str, bars: dict[str, list[Bar]]) -> dict:
    """Attach horizon-specific structure. Weekly SCH stays off the price pane."""
    outlook["horizon"] = horizon
    if horizon == "WEEKLY":
        _attach_weekly(outlook, bars.get("W1") or [])
    elif horizon == "MONTHLY":
        outlook["timeframe_focus"] = ["YTD", "Q", "MN", "W"]
        outlook["strategic"] = {
            "overrides_shorter": False,
            "role": "Strategic context for the next trading month. A valid shorter-term counter-trend opportunity is not cancelled by this reading.",
        }
        outlook["conclusion"] = (outlook.get("conclusion") or "").rstrip() + " Monthly structure sets context only and does not override a valid shorter-term opportunity."
    elif horizon == "H8":
        outlook["timeframe_focus"] = ["MN", "W", "D1", "H8", "H1", "M15"]
        outlook["gold_session"] = {
            "symbol": GOLD,
            "operational_tf": "H8",
            "validation_tf": "H1",
            "execution_tf": "M15",
            "refinement_tf": "M5",
            "chain": ["MN/W/D1 context", "H8 direction, BOS, BTL and channel", "H1 structure", "M15 closed-bar confirmation", "P1/P2", "Stage 7", "Stage 8 risk authorization", "existing execution adapter"],
            "force_trade": False,
        }
        outlook["handoff"] = (
            "M15 confirmation hands the setup to the existing opportunity pipeline. "
            "It does not bypass P1/P2, H1 Stage 7 confirmation, or Stage 8 risk authorization, and it never forces a trade."
        )
    outlook["evidence_balance"] = evidence_balance(outlook)
    return outlook


def _attach_weekly(outlook: dict, weekly: list[Bar]) -> None:
    core = weekly_live(weekly_core(weekly, h8_bos_btl_settings()), outlook.get("price"))
    fractal_state = core.get("fractal_state")
    outlook["weekly"] = {
        "available": bool(core.get("available")),
        "direction": core.get("direction"),
        "state": core.get("state"),
        "fast": core.get("fast"),
        "signal": core.get("signal"),
        "fractal_state": fractal_state,
        "intact_range": fractal_state == "Inside active fractal range",
        "structural_breakout": fractal_state in ("Above active fractal high", "Below active fractal low"),
        "active_high": core.get("active_high"),
        "active_low": core.get("active_low"),
        "position_label": core.get("position_label"),
        "interpretation": core.get("interpretation"),
        "reason": core.get("reason"),
    }
    outlook["sch"] = {"pane": "below_price", "timeframe": "W", "only": "W", "series": (core.get("sch") or [])[-160:]}
    seen = {(a.get("at"), a.get("price"), a.get("side")) for a in outlook.get("chart_annotations") or [] if a.get("type") == "fractal"}
    for mark in core.get("fractals") or []:
        ident = (mark["t"], mark["price"], mark["kind"])
        if ident in seen:
            continue
        outlook.setdefault("chart_annotations", []).append({
            "id": f"wf-{mark['t']}-{mark['kind']}",
            "type": "fractal",
            "group": "fractal",
            "tf": "W",
            "label": f"W {mark['kind'].title()}",
            "tone": "red" if mark["kind"] == "HIGH" else "green",
            "source": "Weekly fractals",
            "evidence_key": None,
            "detail": "Confirmed weekly fractal on a closed W candle",
            "price": mark["price"],
            "at": mark["t"],
            "side": mark["kind"],
            "status": "CONFIRMED",
        })
    outlook["timeframe_focus"] = ["MN", "W", "D1", "H8"]


def m15_confirmation(outlook: dict, m15: list[Bar]) -> dict:
    """Closed M15 rejection inside the published ERZ. M5 is not required."""
    from .evaluation import DIR, _t, _touch

    direction = DIR.get(outlook.get("expected_direction") or "", 0)
    erz = outlook.get("erz") or {}
    if not direction or "lo" not in erz:
        return {"confirmed": False, "reason": "No directional ERZ to confirm on M15"}
    try:
        anchor = _t(outlook["anchor"])
    except (KeyError, ValueError):
        return {"confirmed": False, "reason": "Outlook has no frozen anchor"}
    bars = [b for b in m15 if b.t >= anchor]
    for bar in bars:
        touched = _touch(bar, erz["lo"], erz["hi"])
        with_direction = (bar.c > bar.o and bar.c >= erz["lo"]) if direction == 1 else (bar.c < bar.o and bar.c <= erz["hi"])
        if touched and with_direction:
            return {"confirmed": True, "at": bar.t.isoformat(), "close": bar.c, "bars": len(bars)}
    return {"confirmed": False, "reason": "No M15 rejection close inside the ERZ yet", "bars": len(bars)}


def gold_progress(outlook: dict, h1: list[Bar], m15: list[Bar], now: datetime, expires_at: datetime) -> dict:
    """H1 structure and M15 confirmation between H8 closes. Never marks the setup authorised."""
    from .evaluation import monitor

    watched = dict(outlook, horizon="H8")
    base = monitor(watched, h1, [], None, now, m15=m15)
    m15_state = m15_confirmation(watched, m15)
    life = lifecycle_for(watched, base, now, expires_at, m15_confirmed=bool(m15_state.get("confirmed")))
    if life == "AUTHORIZED":
        life = "AUTHORIZATION_PENDING"
    base["lifecycle"] = life
    base["m15"] = m15_state
    base["execution_ref"] = None
    base["force_trade"] = False
    return base


def risk_approval_id(conn, symbol: str) -> str | None:
    """Existing Stage 8 approval, if the autonomous engine already recorded one. This does not create it."""
    try:
        row = conn.execute(
            "SELECT id FROM ae_opportunity WHERE symbol=? AND reason_code='RISK_APPROVED' ORDER BY updated_at DESC LIMIT 1",
            (symbol,),
        ).fetchone()
    except Exception:
        return None
    return None if row is None else str(values(row)[0])


def gold_position_active(conn) -> bool | None:
    try:
        row = conn.execute("SELECT 1 FROM ae_opportunity WHERE symbol=? AND status='ACTIVE' LIMIT 1", (GOLD,)).fetchone()
    except Exception:
        return None
    return row is not None
