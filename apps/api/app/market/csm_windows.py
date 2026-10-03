"""Custom YTD and quarter windows from closed D1 candles."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence


def quarter_start(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    q = (dt.month - 1) // 3
    return datetime(dt.year, q * 3 + 1, 1, tzinfo=timezone.utc)


def year_start(dt: datetime) -> datetime:
    dt = dt.astimezone(timezone.utc)
    return datetime(dt.year, 1, 1, tzinfo=timezone.utc)


def window_closes(
    rows: Sequence[tuple[datetime, float]],
    window_start: datetime,
) -> tuple[float | None, float | None]:
    """rows: (open_time, close) ascending; use first bar on/after window_start through last bar."""
    filtered = [(t, c) for t, c in rows if t >= window_start and c > 0]
    if len(filtered) < 2:
        return None, None
    return filtered[0][1], filtered[-1][1]
