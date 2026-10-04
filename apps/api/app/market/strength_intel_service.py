"""Payload assembly for Historical Strength, Pair Relationships and Relationship Analysis.

Current values come from the Strength Engine cache (the same scores as the Strength Matrix);
persisted history is read from SQLite through a short TTL cache so polling never re-runs the
28-pair calculation or re-reads full history on every request.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from ..core.database import db
from .constants import FX_PAIRS_28
from .pair_relationships import RELATIONSHIP_LABELS, differential, split_pair
from .relationship_analysis import analyze_pair
from .strength_engine import StrengthEngine
from .strength_history import (
    append_live,
    build_history,
    coverage,
    first_snapshot_at,
    load_score_series,
    parse_period,
    period_start,
)
from .strength_intel_config import ANALYSIS_TIMEFRAMES, dynamics_lookback_minutes, thresholds_payload
from .strength_intel_store import active_scope, differential_history

HISTORY_CACHE_SECONDS = 30.0
HISTORY_TIMEFRAMES = ("AVG", *ANALYSIS_TIMEFRAMES)


class _TTLCache:
    def __init__(self, ttl: float, max_items: int = 64) -> None:
        self.ttl, self.max_items = ttl, max_items
        self._items: dict[tuple, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, build: Callable[[], Any]) -> Any:
        now = time.monotonic()
        with self._lock:
            hit = self._items.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = build()
        with self._lock:
            if len(self._items) >= self.max_items:
                self._items.pop(min(self._items, key=lambda k: self._items[k][0]))
            self._items[key] = (now, value)
        return value


_history_cache = _TTLCache(HISTORY_CACHE_SECONDS)


def _marker(intel: dict) -> str | None:
    at = intel.get("last_persisted_at")
    return at.isoformat() if at else None


def _age_minutes(now: datetime, ref_at: datetime | None) -> float | None:
    return round((now - ref_at).total_seconds() / 60.0, 1) if ref_at else None


def _copy(series: dict[str, list]) -> dict[str, list]:
    return {k: list(v) for k, v in series.items()}


def historical_payload(engine: StrengthEngine, period: str, timeframe: str = "AVG") -> dict | None:
    meta, intel = engine.engine_meta(), engine.intelligence()
    if meta is None or intel is None:
        return None
    period = parse_period(period)
    tf = timeframe.upper()
    if tf not in HISTORY_TIMEFRAMES:
        raise ValueError(f"Unknown timeframe: {timeframe}")
    now = datetime.now(timezone.utc)
    start = period_start(period, now)

    def load():
        with db() as conn:
            return load_score_series(conn, tf, start), first_snapshot_at(conn, tf)

    stored, first = _history_cache.get(("hist", period, tf, _marker(intel)), load)
    series = _copy(stored)
    live = {c: by_tf[tf] for c, by_tf in intel["scores"].items() if tf in by_tf}
    append_live(series, live, intel["as_of"])
    body = build_history(
        series,
        period=period,
        start=start,
        end=now,
        first_available=first,
        snapshot_interval_s=float(meta["snapshot_interval_seconds"]),
    )
    return {"meta": {**meta, "timeframe": tf}, "thresholds": thresholds_payload(), **body}


def pairs_payload(engine: StrengthEngine) -> dict | None:
    meta, intel = engine.engine_meta(), engine.intelligence()
    if meta is None or intel is None:
        return None
    engine.ensure_reference()
    rows = intel["pairs"]
    with db() as conn:
        tenant, account = active_scope(conn)
    ref_at = intel["reference_as_of"]
    counts = {k: sum(1 for r in rows if r["relationship"]["key"] == k) for k in RELATIONSHIP_LABELS}
    return {
        "meta": {
            **meta,
            "reference_as_of": ref_at.isoformat() if ref_at else None,
            "reference_age_minutes": _age_minutes(intel["as_of"], ref_at),
            "lookback_minutes": dynamics_lookback_minutes(),
            "pairs_available": len(rows),
            "scope": {"tenant_id": tenant or None, "trading_account_id": account or None},
            "analysis_only": True,
        },
        "thresholds": thresholds_payload(),
        "summary": {"relationship_counts": counts},
        "rows": rows,
    }


def analysis_payload(engine: StrengthEngine, pair: str, period: str = "24H") -> dict | None:
    pair = pair.upper()
    if pair not in FX_PAIRS_28:
        raise ValueError(f"Unknown pair: {pair}")
    meta, intel = engine.engine_meta(), engine.intelligence()
    if meta is None or intel is None:
        return None
    engine.ensure_reference()
    period = parse_period(period)
    now = datetime.now(timezone.utc)
    start = period_start(period, now)

    def load():
        with db() as conn:
            return differential_history(conn, pair, start), first_snapshot_at(conn, "AVG")

    stored, first = _history_cache.get(("pair", pair, period, _marker(intel)), load)
    history = _copy(stored)
    base, quote = split_pair(pair)
    scores = intel["scores"]
    for tf, series in history.items():
        d = differential(scores, base, quote, tf)
        if d is not None and (not series or intel["as_of"] > series[-1][0]):
            series.append((intel["as_of"], d))
    ref_at = intel["reference_as_of"]
    out = analyze_pair(
        pair,
        scores,
        intel["reference"],
        history,
        lookback_minutes=dynamics_lookback_minutes(),
        reference_age_minutes=_age_minutes(intel["as_of"], ref_at),
    )
    if out is None:
        return None
    out["meta"] = {
        **meta,
        **out["meta"],
        "pair": pair,
        "period": period,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "reference_as_of": ref_at.isoformat() if ref_at else None,
        "coverage": coverage(start, now, first, float(meta["snapshot_interval_seconds"])),
        "history_points": len(history.get("AVG", [])),
        "analysis_only": True,
    }
    out["thresholds"] = thresholds_payload()
    return out
