"""SQLite access for Strength Intelligence history: reference snapshots, differential history and
tenant/account-scoped pair intelligence snapshots in ``db_cacsms-traders.db``."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from ..core.database import execute_retry
from ..domain.mt5_connection import _active_tenant_id
from .constants import normalize_matrix_timeframe
from .pair_relationships import Scores, split_pair
from .relationship_analysis import Point, diff_series
from .strength_history import load_score_series
from .strength_intel_config import ANALYSIS_TIMEFRAMES


def active_scope(conn: sqlite3.Connection) -> tuple[str, str]:
    """(tenant_id, trading_account_id) of the shared MT5 session; '' when not configured."""
    tenant = _active_tenant_id(conn) or ""
    if not tenant:
        return "", ""
    row = conn.execute(
        "SELECT trading_account_id FROM trading_connections WHERE tenant_id=? ORDER BY updated_at DESC LIMIT 1",
        (tenant,),
    ).fetchone()
    return tenant, str(row[0]) if row and row[0] else ""


def reference_scores(conn: sqlite3.Connection, at_or_before: datetime) -> tuple[datetime, Scores] | None:
    """Most recent persisted score snapshot at or before ``at_or_before`` (None if history is shorter)."""
    row = conn.execute(
        "SELECT MAX(as_of) FROM mi_strength_snapshot WHERE timeframe='AVG' AND score IS NOT NULL AND as_of <= ?",
        (at_or_before.isoformat(),),
    ).fetchone()
    if not row or not row[0]:
        return None
    as_of = str(row[0])
    scores: Scores = {}
    for currency, tf, score in conn.execute(
        "SELECT currency, timeframe, score FROM mi_strength_snapshot WHERE as_of=? AND score IS NOT NULL", (as_of,)
    ).fetchall():
        scores.setdefault(str(currency), {})[normalize_matrix_timeframe(str(tf))] = float(score)
    at = datetime.fromisoformat(as_of)
    return (at if at.tzinfo else at.replace(tzinfo=timezone.utc)), scores


def differential_history(conn: sqlite3.Connection, pair: str, start: datetime) -> dict[str, list[Point]]:
    base, quote = split_pair(pair)
    out: dict[str, list[Point]] = {}
    for tf in ("AVG", *ANALYSIS_TIMEFRAMES):
        series = load_score_series(conn, tf, start, (base, quote))
        out[tf] = diff_series(series[base], series[quote])
    return out


def save_pair_snapshot(conn: sqlite3.Connection, scope: tuple[str, str], as_of: datetime, rows: list[dict]) -> int:
    tenant, account = scope
    stamp = as_of.isoformat()
    for r in rows:
        base, quote = split_pair(r["pair"])
        execute_retry(
            conn,
            """INSERT INTO mi_pair_intel_snapshot(tenant_id,trading_account_id,pair,base_currency,quote_currency,as_of,
                 base_strength,quote_strength,differential,abs_differential,relationship,dynamics,alignment,
                 aligned_count,timeframe_count,tf_differentials_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id,trading_account_id,pair,as_of) DO UPDATE SET
                 base_strength=excluded.base_strength,quote_strength=excluded.quote_strength,
                 differential=excluded.differential,abs_differential=excluded.abs_differential,
                 relationship=excluded.relationship,dynamics=excluded.dynamics,alignment=excluded.alignment,
                 aligned_count=excluded.aligned_count,timeframe_count=excluded.timeframe_count,
                 tf_differentials_json=excluded.tf_differentials_json""",
            (
                tenant,
                account,
                r["pair"],
                base,
                quote,
                stamp,
                r["base_strength"],
                r["quote_strength"],
                r["differential"],
                r["abs_differential"],
                r["relationship"]["key"],
                r["dynamics"]["key"],
                r["alignment"]["key"],
                r["alignment"]["aligned"],
                r["alignment"]["total"],
                json.dumps(r["timeframes"]),
            ),
        )
    conn.commit()
    return len(rows)


def latest_pair_snapshot(conn: sqlite3.Connection, scope: tuple[str, str]) -> list[dict]:
    """Latest persisted pair intelligence for one tenant/account (for Market Scanner / pipeline consumers)."""
    tenant, account = scope
    rows = conn.execute(
        """SELECT * FROM mi_pair_intel_snapshot WHERE tenant_id=? AND trading_account_id=? AND as_of=(
             SELECT MAX(as_of) FROM mi_pair_intel_snapshot WHERE tenant_id=? AND trading_account_id=?)
           ORDER BY abs_differential DESC""",
        (tenant, account, tenant, account),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["timeframes"] = json.loads(d.pop("tf_differentials_json") or "{}")
        out.append(d)
    return out
