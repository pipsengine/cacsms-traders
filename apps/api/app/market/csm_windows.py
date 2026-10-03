"""Custom YTD and quarter windows from closed D1 candles."""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Sequence


def rolling_quarter_start(dt: datetime) -> datetime:
    """Same calendar day three months earlier (day clamped to month length), at 00:00 UTC."""
    dt = dt.astimezone(timezone.utc)
    month_index = dt.year * 12 + (dt.month - 1) - 3
    year, month = divmod(month_index, 12)
    month += 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return datetime(year, month, day, tzinfo=timezone.utc)


def year_start(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return datetime(dt.year, 1, 1, tzinfo=timezone.utc)


def rolling_year_start(dt: datetime) -> datetime:
    """Trailing 12-month window (EarnForex-style custom Y column)."""
    return dt.astimezone(timezone.utc) - timedelta(days=365)


def window_closes(
    rows: Sequence[tuple[datetime, float]],
    window_start: datetime,
) -> tuple[float | None, float | None]:
    """Close-to-close from last D1 before window_start through latest closed D1."""
    if not rows:
        return None, None
    ws = window_start.astimezone(timezone.utc)
    normalized: list[tuple[datetime, float]] = []
    for t, c in rows:
        if c <= 0:
            continue
        ot = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
        normalized.append((ot, c))
    if not normalized:
        return None, None
    end_close = normalized[-1][1]
    before = [c for t, c in normalized if t < ws]
    on_or_after = [c for t, c in normalized if t >= ws]
    if before:
        start_close = before[-1]
    elif on_or_after:
        start_close = on_or_after[0]
    else:
        return None, None
    if start_close <= 0 or end_close <= 0:
        return None, None
    return start_close, end_close
