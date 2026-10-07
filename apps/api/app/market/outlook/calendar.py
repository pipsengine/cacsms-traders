"""FX trading calendar: the trading day closes at 17:00 New York (broker D1 rollover), Monday–Friday."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
ROLLOVER = time(17, 0)
# UTC session windows (hours) used for the next-session plan.
SESSIONS = (
    ("ASIAN", "Asian Session", 0, 9),
    ("LONDON", "London Session", 7, 16),
    ("NEW_YORK", "New York Session", 12, 21),
)


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5


def close_time(d: date) -> datetime:
    """UTC instant the trading day ``d`` closes."""
    return datetime.combine(d, ROLLOVER, tzinfo=NEW_YORK).astimezone(timezone.utc)


def last_closed_day(now: datetime) -> date:
    """Most recent trading day whose close is at or before ``now``."""
    d = now.astimezone(NEW_YORK).date()
    while not is_trading_day(d) or close_time(d) > now:
        d -= timedelta(days=1)
    return d


def next_trading_day(d: date) -> date:
    n = d + timedelta(days=1)
    while not is_trading_day(n):
        n += timedelta(days=1)
    return n


def next_close(now: datetime) -> datetime:
    return close_time(next_trading_day(last_closed_day(now)))


def d1_open_for(d: date) -> datetime:
    """UTC open of the D1 candle that belongs to trading day ``d`` (previous calendar day's rollover)."""
    prev = d - timedelta(days=1)
    while prev.weekday() == 5:
        prev -= timedelta(days=1)
    return datetime.combine(prev, ROLLOVER, tzinfo=NEW_YORK).astimezone(timezone.utc)


def session_windows(after: datetime) -> list[dict]:
    """The next occurrence of each session after ``after`` (the trading day's close)."""
    day = next_trading_day(after.astimezone(NEW_YORK).date())
    out = []
    for key, label, start, end in SESSIONS:
        base = datetime.combine(day, time(0, 0), tzinfo=timezone.utc)
        s, e = base + timedelta(hours=start), base + timedelta(hours=end)
        out.append({"key": key, "label": label, "start": s.isoformat(), "end": e.isoformat()})
    return out


def active_session(now: datetime) -> str | None:
    h = now.astimezone(timezone.utc).hour
    if now.astimezone(NEW_YORK).weekday() >= 5 and now.astimezone(NEW_YORK).time() < ROLLOVER:
        return None
    live = [key for key, _, start, end in SESSIONS if start <= h < end]
    return live[-1] if live else None
