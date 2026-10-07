"""SQLite access for Strength Intelligence history: reference snapshots, differential history and
tenant/account-scoped pair intelligence snapshots in ``db_cacsms-traders.db``."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from ..core.database import execute_values
from .market_data import configuration
from .provenance import scoped_query, values
from .constants import normalize_matrix_timeframe
from .pair_relationships import Scores, split_pair
from .relationship_analysis import Point, diff_series
from .strength_history import load_score_series
from .strength_intel_config import ANALYSIS_TIMEFRAMES


def active_scope(conn: sqlite3.Connection) -> tuple[str, str]:
    """Explicit scope of the active market-data configuration."""
    cfg = configuration(conn)
    return cfg["tenant_id"], cfg["account_id"]


def reference_scores(conn: sqlite3.Connection, at_or_before: datetime, snapshot_id=None) -> tuple[datetime, Scores] | None:
    """Most recent persisted score snapshot at or before ``at_or_before`` (None if history is shorter)."""
    row = scoped_query(conn,
        "SELECT MAX(as_of) FROM mi_strength_snapshot WHERE timeframe='AVG' AND score IS NOT NULL AND as_of <= ?",
        (at_or_before.isoformat(),), snapshot_id=snapshot_id,
    ).fetchone()
    if not row or not values(row)[0]:
        return None
    as_of = str(values(row)[0])
    scores: Scores = {}
    for record in scoped_query(conn,
        "SELECT currency, timeframe, score FROM mi_strength_snapshot WHERE as_of=? AND score IS NOT NULL", (as_of,), snapshot_id=snapshot_id
    ).fetchall():
        currency, tf, score = values(record)
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
    execute_values(
        conn,
        """INSERT INTO mi_pair_intel_snapshot(tenant_id,trading_account_id,pair,base_currency,quote_currency,as_of,
             base_strength,quote_strength,differential,abs_differential,relationship,dynamics,alignment,
             aligned_count,timeframe_count,tf_differentials_json)""",
        [
            (
                tenant,
                account,
                r["pair"],
                *split_pair(r["pair"]),
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
            )
            for r in rows
        ],
        """ON CONFLICT(tenant_id,trading_account_id,pair,as_of) DO UPDATE SET
             base_strength=excluded.base_strength,quote_strength=excluded.quote_strength,
             differential=excluded.differential,abs_differential=excluded.abs_differential,
             relationship=excluded.relationship,dynamics=excluded.dynamics,alignment=excluded.alignment,
             aligned_count=excluded.aligned_count,timeframe_count=excluded.timeframe_count,
             tf_differentials_json=excluded.tf_differentials_json""",
        key=lambda r: r[2],
    )
    conn.commit()
    return len(rows)


def latest_pair_snapshot(conn: sqlite3.Connection, scope: tuple[str, str]) -> list[dict]:
    """Latest persisted pair intelligence for one tenant/account (for Market Scanner / pipeline consumers)."""
    tenant, account = scope
    rows = scoped_query(conn,
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
