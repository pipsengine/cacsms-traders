"""Equity baselines taken from broker equity, never from a fixed deposit."""
from __future__ import annotations

from datetime import datetime, timezone

from .money import D, text


def _row(conn, sql, params=()):
    found = conn.execute(sql, params).fetchone()
    return None if found is None else dict(found)


def touch_baseline(conn, tenant_id: str, account_id: str, currency: str, equity, now: datetime | None = None, source: str = "broker") -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    amount = D(equity)
    day_key = now.date().isoformat()
    week = now.isocalendar()
    week_key = f"{week.year}-W{week.week:02d}"
    stamp = now.isoformat()
    current = _row(conn, "SELECT * FROM equity_baselines WHERE trading_account_id=?", (account_id,))
    if current is None:
        stored = text(amount)
        conn.execute(
            "INSERT INTO equity_baselines(trading_account_id,tenant_id,currency,peak_equity,day_start_equity,week_start_equity,day_key,week_key,source,recorded_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (account_id, tenant_id, currency, stored, stored, stored, day_key, week_key, source, stamp),
        )
    else:
        peak = max(D(current["peak_equity"]), amount)
        day_start = amount if current["day_key"] != day_key else D(current["day_start_equity"])
        week_start = amount if current["week_key"] != week_key else D(current["week_start_equity"])
        conn.execute(
            "UPDATE equity_baselines SET currency=?,peak_equity=?,day_start_equity=?,week_start_equity=?,day_key=?,week_key=?,source=?,recorded_at=? WHERE trading_account_id=?",
            (currency, text(peak), text(day_start), text(week_start), day_key, week_key, source, stamp, account_id),
        )
    return _row(conn, "SELECT * FROM equity_baselines WHERE trading_account_id=?", (account_id,))
