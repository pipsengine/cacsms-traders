"""Historical Strength: persisted 0–100 strength snapshots → trends, momentum, extremes and events.

Series come only from ``mi_strength_snapshot`` rows written by the Strength Engine (plus the engine's
current calculation as the latest point). Gaps are reported as incomplete coverage, never filled.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from itertools import combinations

from .constants import CSM_CURRENCIES
from .provenance import scoped_query, values
from .csm_windows import year_start
from .strength_classification import classify
from .strength_intel_config import HistoryThresholds, history_thresholds

PERIODS: dict[str, timedelta | None] = {
    "24H": timedelta(hours=24),
    "7D": timedelta(days=7),
    "1M": timedelta(days=30),
    "3M": timedelta(days=91),
    "6M": timedelta(days=182),
    "YTD": None,
}
MAX_CHART_POINTS = 360
MAX_EVENTS = 40
TIMEFRAME_STORAGE = {"W": ("W", "W1")}

Point = tuple[datetime, float]


def parse_period(period: str) -> str:
    p = period.upper()
    if p not in PERIODS:
        raise ValueError(f"Unknown period: {period}")
    return p


def period_start(period: str, now: datetime) -> datetime:
    span = PERIODS[parse_period(period)]
    return year_start(now) if span is None else now - span


def _dt(raw: str) -> datetime:
    d = datetime.fromisoformat(raw)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def load_score_series(
    conn: sqlite3.Connection, timeframe: str, start: datetime, currencies: tuple[str, ...] = CSM_CURRENCIES
) -> dict[str, list[Point]]:
    names = TIMEFRAME_STORAGE.get(timeframe, (timeframe,))
    marks = ",".join("?" * len(names))
    cmarks = ",".join("?" * len(currencies))
    rows = scoped_query(conn,
        f"""SELECT currency, as_of, score FROM mi_strength_snapshot
            WHERE timeframe IN ({marks}) AND currency IN ({cmarks}) AND as_of >= ? AND score IS NOT NULL
            ORDER BY as_of""",
        (*names, *currencies, start.isoformat()),
    ).fetchall()
    out: dict[str, list[Point]] = {c: [] for c in currencies}
    for row in rows:
        currency, as_of, score = values(row)
        series = out[str(currency)]
        at = _dt(str(as_of))
        if series and series[-1][0] == at:
            series[-1] = (at, float(score))
        else:
            series.append((at, float(score)))
    return out


def first_snapshot_at(conn: sqlite3.Connection, timeframe: str = "AVG") -> datetime | None:
    names = TIMEFRAME_STORAGE.get(timeframe, (timeframe,))
    marks = ",".join("?" * len(names))
    row = scoped_query(conn,
        f"SELECT MIN(as_of) FROM mi_strength_snapshot WHERE timeframe IN ({marks}) AND score IS NOT NULL", names
    ).fetchone()
    return _dt(str(values(row)[0])) if row and values(row)[0] else None


def append_live(series: dict[str, list[Point]], live: dict[str, float], as_of: datetime | None) -> None:
    """Add the engine's current calculation as the latest point when newer than the last snapshot."""
    if as_of is None:
        return
    for c, v in live.items():
        s = series.setdefault(c, [])
        if not s or as_of > s[-1][0]:
            s.append((as_of, v))


def coverage(start: datetime, end: datetime, first: datetime | None, interval_s: float) -> dict:
    span = (end - start).total_seconds()
    if first is None or span <= 0:
        return {"complete": False, "pct": 0.0, "first_available": None}
    effective = max(start, first)
    pct = max(0.0, min(100.0, (end - effective).total_seconds() / span * 100.0))
    complete = (first - start).total_seconds() <= interval_s * 2
    return {"complete": complete, "pct": round(100.0 if complete else pct, 1), "first_available": first.isoformat()}


def value_at(series: list[Point], t: datetime) -> float | None:
    """Last persisted value at or before t (no interpolation)."""
    out = None
    for at, v in series:
        if at > t:
            break
        out = v
    return out


def trend(change: float, t: HistoryThresholds) -> dict:
    if change >= t.trend_band:
        return {"key": "STRENGTHENING", "label": "Strengthening"}
    if change <= -t.trend_band:
        return {"key": "WEAKENING", "label": "Weakening"}
    return {"key": "STABLE", "label": "Stable"}


def momentum(series: list[Point], t: HistoryThresholds) -> dict:
    """Compare the score change over the latest third of the covered window with the third before it."""
    if len(series) < 6:
        return {"key": "INSUFFICIENT", "label": "Insufficient history", "recent": None, "prior": None}
    start, end = series[0][0], series[-1][0]
    w = (end - start) / 3
    a, b, c = value_at(series, end - 2 * w), value_at(series, end - w), series[-1][1]
    if a is None or b is None:
        return {"key": "INSUFFICIENT", "label": "Insufficient history", "recent": None, "prior": None}
    recent, prior = c - b, b - a
    if abs(recent) - abs(prior) >= t.momentum_epsilon:
        key, label = "ACCELERATING", "Accelerating"
    elif abs(prior) - abs(recent) >= t.momentum_epsilon:
        key, label = "DECELERATING", "Decelerating"
    else:
        key, label = "STABLE", "Stable"
    return {"key": key, "label": label, "recent": round(recent, 1), "prior": round(prior, 1)}


def currency_stats(currency: str, series: list[Point], t: HistoryThresholds) -> dict:
    if not series:
        return {"currency": currency, "available": False}
    values = [v for _, v in series]
    current, start = values[-1], values[0]
    hi_i = max(range(len(values)), key=values.__getitem__)
    lo_i = min(range(len(values)), key=values.__getitem__)
    change = round(current - start, 1)
    return {
        "currency": currency,
        "available": True,
        "points": len(series),
        "current": round(current, 1),
        "classification": classify(current),
        "start": round(start, 1),
        "start_at": series[0][0].isoformat(),
        "change": change,
        "change_pct": round(change / start * 100.0, 1) if start else None,
        "trend": trend(change, t),
        "momentum": momentum(series, t),
        "high": round(values[hi_i], 1),
        "high_at": series[hi_i][0].isoformat(),
        "low": round(values[lo_i], 1),
        "low_at": series[lo_i][0].isoformat(),
        "average": round(sum(values) / len(values), 1),
    }


def reversal_events(currency: str, series: list[Point], amplitude: float) -> list[dict]:
    """Zig-zag pivots: a swing is confirmed once price-of-strength retraces ``amplitude`` points."""
    events: list[dict] = []
    if len(series) < 3:
        return events
    direction = 0
    ext_t, ext_v = series[0]
    for at, v in series[1:]:
        if direction >= 0 and v > ext_v or direction <= 0 and v < ext_v:
            if direction == 0:
                direction = 1 if v > ext_v else -1
            ext_t, ext_v = at, v
            continue
        if abs(v - ext_v) >= amplitude and direction != 0:
            events.append(
                {
                    "type": "REVERSAL",
                    "at": ext_t.isoformat(),
                    "confirmed_at": at.isoformat(),
                    "currency": currency,
                    "direction": "TURNED_DOWN" if direction > 0 else "TURNED_UP",
                    "score": round(ext_v, 1),
                    "detail": f"{currency} {'peaked' if direction > 0 else 'bottomed'} at {ext_v:.1f} and "
                    f"{'weakened' if direction > 0 else 'strengthened'} by {abs(v - ext_v):.1f} points",
                }
            )
            direction = -direction
            ext_t, ext_v = at, v
    return events


def _aligned(series: dict[str, list[Point]], a: str, b: str) -> list[tuple[datetime, float, float]]:
    sb = dict(series.get(b, []))
    return [(at, va, sb[at]) for at, va in series.get(a, []) if at in sb]


def crossover_events(series: dict[str, list[Point]], min_gap: float) -> list[dict]:
    """Rank crossovers between currencies, with a hysteresis gap so noise around equality is ignored."""
    events: list[dict] = []
    for a, b in combinations(sorted(series), 2):
        state = 0
        for at, va, vb in _aligned(series, a, b):
            d = va - vb
            s = 1 if d >= min_gap else -1 if d <= -min_gap else 0
            if s == 0:
                continue
            if state and s != state:
                leader, laggard = (a, b) if s > 0 else (b, a)
                events.append(
                    {
                        "type": "CROSSOVER",
                        "at": at.isoformat(),
                        "leader": leader,
                        "laggard": laggard,
                        "currencies": [leader, laggard],
                        "detail": f"{leader} moved above {laggard} ({max(va, vb):.1f} vs {min(va, vb):.1f})",
                    }
                )
            state = s
    return events


def midline_events(currency: str, series: list[Point], min_gap: float) -> list[dict]:
    events: list[dict] = []
    state = 0
    for at, v in series:
        s = 1 if v >= 50 + min_gap else -1 if v <= 50 - min_gap else 0
        if s == 0:
            continue
        if state and s != state:
            events.append(
                {
                    "type": "MIDLINE",
                    "at": at.isoformat(),
                    "currency": currency,
                    "direction": "ABOVE" if s > 0 else "BELOW",
                    "score": round(v, 1),
                    "detail": f"{currency} crossed {'above' if s > 0 else 'below'} the 50 neutral line",
                }
            )
        state = s
    return events


def downsample(times: list[datetime], limit: int = MAX_CHART_POINTS) -> list[datetime]:
    if len(times) <= limit:
        return times
    step = len(times) / (limit - 1)
    picked = [times[int(i * step)] for i in range(limit - 1)]
    return picked + [times[-1]]


def chart_series(series: dict[str, list[Point]]) -> dict:
    """Common time axis of real snapshot times; a currency without a row at a time is null (not filled)."""
    times = downsample(sorted({at for s in series.values() for at, _ in s}))
    lookup = {c: dict(s) for c, s in series.items()}
    return {
        "times": [t.isoformat() for t in times],
        "values": {c: [lookup[c].get(t) for t in times] for c in series},
    }


def build_history(
    series: dict[str, list[Point]],
    *,
    period: str,
    start: datetime,
    end: datetime,
    first_available: datetime | None,
    snapshot_interval_s: float,
) -> dict:
    t = history_thresholds()
    stats = [currency_stats(c, series.get(c, []), t) for c in CSM_CURRENCIES]
    ranked = sorted((s for s in stats if s["available"]), key=lambda s: -s["current"])
    for i, s in enumerate(ranked):
        s["rank"] = i + 1
    events: list[dict] = crossover_events(series, t.crossover_min_gap)
    for c in CSM_CURRENCIES:
        events += reversal_events(c, series.get(c, []), t.reversal_amplitude)
        events += midline_events(c, series.get(c, []), t.crossover_min_gap)
    events.sort(key=lambda e: e["at"], reverse=True)
    points = max((len(s) for s in series.values()), default=0)
    return {
        "period": period,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "points": points,
        "coverage": coverage(start, end, first_available, snapshot_interval_s),
        "currencies": stats,
        "chart": chart_series(series),
        "events": events[:MAX_EVENTS],
        "event_count": len(events),
    }
