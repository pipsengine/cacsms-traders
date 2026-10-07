"""Channel Intelligence on closed candles: regression channels across Y…H1, breakout & retest, trend-in-trend.

Y / HY / Q bars are calendar aggregates of closed MN bars; YTD is the D1 window since 1 January. Channels are
linear-regression channels on closes (±width σ), fitted with prefix sums so rolling (walk-forward) fits stay
O(1) per bar. A breakout is a close beyond the channel projected from the bars *before* it — the fit never
looks ahead. Outputs describe structure only; scenario weights are structural scores, not trade signals.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .scanner_analytics import Bar, pivots, true_ranges, wilder_atr
from .scanner_config import _floats

CHANNEL_TIMEFRAMES = ("Y", "YTD", "HY", "Q", "MN", "W", "D1", "H8", "H1")
EVENT_TIMEFRAMES = ("W", "D1", "H8", "H1")
LAYERS = (("L1", "W"), ("L2", "D1"), ("L3", "H8"), ("L4", "H1"))
PARENT = {"YTD": "Y", "HY": "Y", "Q": "HY", "MN": "Q", "W": "MN", "D1": "W", "H8": "D1", "H1": "H8"}
TF_NAMES = {
    "Y": "Yearly (Y)", "YTD": "YTD", "HY": "Half-Year (HY)", "Q": "Quarterly (Q)", "MN": "Monthly (MN)",
    "W": "Weekly (W)", "D1": "Daily (D1)", "H8": "H8", "H1": "H1",
}
UNITS = {"Y": "years", "YTD": "days", "HY": "half-years", "Q": "quarters", "MN": "months", "W": "weeks", "D1": "days",
         "H8": "H8 bars", "H1": "hours"}
DELTA = {"W": timedelta(days=7), "D1": timedelta(days=1), "YTD": timedelta(days=1), "H8": timedelta(hours=8),
         "H1": timedelta(hours=1)}
DIRECTIONS = {"ASCENDING": "UPTREND", "DESCENDING": "DOWNTREND", "FLAT": "RANGING"}
STATES = {
    "ACTIVE": "Active",
    "TESTING_UPPER": "Testing Upper",
    "TESTING_LOWER": "Testing Lower",
    "BREAKOUT_UP": "Breakout ↑",
    "BREAKOUT_DOWN": "Breakout ↓",
}
BREAKOUT_STATUS = {"CONFIRMED": "Confirmed", "DEVELOPING": "Developing", "RETESTING": "Retesting", "FAILED": "Failed",
                   "TESTING": "Testing", "INSIDE": "Back Inside"}
RETEST_STATUS = {"PENDING": "Pending", "TESTING": "Testing", "COMPLETED": "Completed", "NONE": "—"}


@dataclass(frozen=True)
class ChannelSettings:
    periods: dict[str, int]
    width_sd: float
    flat_ratio: float
    touch_atr: float
    touch_gap: int
    inside_valid: float
    confirm_closes: int
    retest_atr: float
    scan_bars: int
    stat_windows: int
    test_pct: float
    approach_pct: float
    near_setup_atr: float
    mature_pct: float
    min_bars: int = 8
    atr_period: int = 14
    fail_bars: int = 10
    break_atr: float = 0.1


def channel_settings() -> ChannelSettings:
    # CHANNEL_PERIODS="Y,HY,Q,MN,W,D1,H8,H1" (bars per fit; YTD always uses every D1 bar since 1 January)
    per = _floats("CHANNEL_PERIODS", (12.0, 16.0, 20.0, 36.0, 52.0, 60.0, 60.0, 60.0))
    # CHANNEL_GEOMETRY="width_sd,flat_ratio,touch_atr,touch_gap,inside_valid"
    wsd, fr, ta, tg, iv = _floats("CHANNEL_GEOMETRY", (2.0, 0.35, 0.25, 2.0, 0.9))
    # CHANNEL_BREAKOUTS="confirm_closes,retest_atr,scan_bars,stat_windows"
    cc, ra, sb, sw = _floats("CHANNEL_BREAKOUTS", (2.0, 0.3, 120.0, 60.0))
    # CHANNEL_SETUPS="test_pct,approach_pct,near_setup_atr,mature_pct"
    tp, ap, ns, mp = _floats("CHANNEL_SETUPS", (5.0, 15.0, 1.5, 60.0))
    keys = ("Y", "HY", "Q", "MN", "W", "D1", "H8", "H1")
    return ChannelSettings(
        periods={k: max(5, int(v)) for k, v in zip(keys, per)},
        width_sd=max(0.5, wsd), flat_ratio=fr, touch_atr=ta, touch_gap=max(1, int(tg)), inside_valid=min(1.0, iv),
        confirm_closes=max(1, int(cc)), retest_atr=ra, scan_bars=max(20, int(sb)), stat_windows=max(5, int(sw)),
        test_pct=min(tp, ap), approach_pct=min(45.0, ap), near_setup_atr=ns, mature_pct=min(100.0, mp),
    )


def channel_settings_payload() -> dict:
    s = channel_settings()
    return {k: getattr(s, k) for k in s.__dataclass_fields__}


# ----- bars -----


def aggregate(mn: list[Bar], months: int) -> list[Bar]:
    """Calendar-aligned aggregate of closed monthly bars (3 = quarter, 6 = half-year, 12 = year)."""
    out: list[Bar] = []
    key = None
    for b in mn:
        k = (b.t.year, (b.t.month - 1) // months)
        if k != key:
            start = datetime(b.t.year, k[1] * months + 1, 1, tzinfo=b.t.tzinfo or timezone.utc)
            out.append(Bar(start, b.o, b.h, b.l, b.c, b.v))
            key = k
        else:
            p = out[-1]
            out[-1] = Bar(p.t, p.o, max(p.h, b.h), min(p.l, b.l), b.c, p.v + b.v)
    return out


def ytd_bars(d1: list[Bar]) -> list[Bar]:
    if not d1:
        return []
    year = d1[-1].t.year
    return [b for b in d1 if b.t.year == year]


def channel_bars(bars: dict[str, list[Bar]]) -> dict[str, list[Bar]]:
    mn = bars.get("MN", [])
    return {
        "Y": aggregate(mn, 12), "YTD": ytd_bars(bars.get("D1", [])), "HY": aggregate(mn, 6), "Q": aggregate(mn, 3),
        "MN": mn, "W": bars.get("W1", []), "D1": bars.get("D1", []), "H8": bars.get("H8", []), "H1": bars.get("H1", []),
    }


# ----- regression fits -----


class _Fits:
    """Prefix sums over closes so any window's regression line and residual σ costs O(1)."""

    def __init__(self, ys: list[float]):
        self.s = [0.0]
        self.s2 = [0.0]
        self.si = [0.0]
        for i, y in enumerate(ys):
            self.s.append(self.s[-1] + y)
            self.s2.append(self.s2[-1] + y * y)
            self.si.append(self.si[-1] + i * y)

    def fit(self, a: int, b: int) -> tuple[float, float, float]:
        """(slope per bar, fitted value at bar b-1, residual σ) for closes[a:b]."""
        n = b - a
        sy = self.s[b] - self.s[a]
        syy = self.s2[b] - self.s2[a]
        sxy = (self.si[b] - self.si[a]) - a * sy
        sx = n * (n - 1) / 2
        sxx = (n - 1) * n * (2 * n - 1) / 6
        den = n * sxx - sx * sx
        slope = (n * sxy - sx * sy) / den if den else 0.0
        icpt = (sy - slope * sx) / n
        sse = syy - icpt * sy - slope * sxy
        return slope, icpt + slope * (n - 1), math.sqrt(max(sse, 0.0) / n)


def _closed_at(b: Bar, tf: str) -> str:
    return (b.t + DELTA[tf]).isoformat() if tf in DELTA else b.t.isoformat()


def _direction(slope: float, period: int, width: float, s: ChannelSettings) -> str:
    drift = abs(slope) * (period - 1)
    if width <= 0 or drift < s.flat_ratio * width:
        return "FLAT"
    return "ASCENDING" if slope > 0 else "DESCENDING"


def _touch_groups(flags: list[bool], gap: int) -> list[int]:
    """Indices starting each run of touches (touches closer than ``gap`` bars are one test)."""
    out, last = [], -10**9
    for i, f in enumerate(flags):
        if f:
            if i - last > gap:
                out.append(i)
            last = i
    return out


def _breakouts(bars: list[Bar], fits: _Fits, p: int, atr: float, tf: str, s: ChannelSettings) -> list[dict]:
    """Walk-forward breakouts: close beyond the channel fitted on the p bars before it, tracked on the frozen line."""
    size = len(bars)
    out: list[dict] = []
    tol = s.retest_atr * atr
    prev_dir = 0
    gap = max(3, p // 6)
    for k in range(max(p, size - s.scan_bars), size):
        slope, mid_end, sd = fits.fit(k - p, k)
        mid_k = mid_end + slope
        half = s.width_sd * sd
        c = bars[k].c
        d = 1 if c > mid_k + half + s.break_atr * atr else -1 if c < mid_k - half - s.break_atr * atr else 0
        same_move = bool(out) and out[-1]["dir"] == d and k - out[-1]["k"] <= gap
        if d and d != prev_dir and not same_move:
            level = mid_k + d * half
            out.append({"k": k, "dir": d, "level": level, "slope": slope, "half": half, "mid": mid_k,
                        "fit_start": k - p})
        prev_dir = d
    events = []
    for e in out:
        k, d = e["k"], e["dir"]
        line = lambda j: e["level"] + e["slope"] * (j - k)  # noqa: E731
        closes_beyond = 0
        for j in range(k, size):
            if (bars[j].c - line(j)) * d > 0:
                closes_beyond += 1
            else:
                break
        retest_k = next((j for j in range(k + 1, size) if ((bars[j].l <= line(j) + tol) if d == 1 else (bars[j].h >= line(j) - tol))), None)
        completed_k = None
        if retest_k is not None:
            completed_k = next((j for j in range(retest_k + 1, size)
                                if ((bars[j].c > bars[retest_k].h) if d == 1 else (bars[j].c < bars[retest_k].l))), None)
        # A breakout fails if it closes back inside before its retest completes (or within the failure window).
        fail_end = completed_k if completed_k is not None else min(size, k + 1 + s.fail_bars)
        failed_k = next((j for j in range(k + 1, fail_end) if (bars[j].c - (line(j) - d * tol)) * d < 0), None)
        if failed_k is not None and completed_k is not None and completed_k > failed_k:
            completed_k = None
        after = bars[k + 1 :]
        mfe = max(((x.h - e["level"]) if d == 1 else (e["level"] - x.l) for x in after), default=0.0)
        mfe_k = None
        if after:
            mfe_k = k + 1 + max(range(len(after)), key=lambda i: (after[i].h if d == 1 else -after[i].l))
        events.append({
            "tf": tf,
            "direction": "UP" if d == 1 else "DOWN",
            "at": _closed_at(bars[k], tf),
            "bar_at": bars[k].t.isoformat(),
            "level": e["level"],
            "close": bars[k].c,
            "slope": e["slope"],
            "half": e["half"],
            "fit_start_at": bars[e["fit_start"]].t.isoformat(),
            "fit_start_mid": e["mid"] - e["slope"] * (k - e["fit_start"]),
            "mid_break": e["mid"],
            "closes_beyond": closes_beyond,
            "confirmed": closes_beyond >= s.confirm_closes,
            "failed": failed_k is not None,
            "failed_at": _closed_at(bars[failed_k], tf) if failed_k is not None else None,
            "retest_at": _closed_at(bars[retest_k], tf) if retest_k is not None else None,
            "retest_bar_at": bars[retest_k].t.isoformat() if retest_k is not None else None,
            "retest_level": line(retest_k) if retest_k is not None else None,
            "completed_at": _closed_at(bars[completed_k], tf) if completed_k is not None else None,
            "mfe": mfe,
            "mfe_atr": round(mfe / atr, 2) if atr else None,
            "mfe_at": bars[mfe_k].t.isoformat() if mfe_k is not None else None,
            "mfe_price": (after[mfe_k - k - 1].h if d == 1 else after[mfe_k - k - 1].l) if mfe_k is not None else None,
            "bars_after": size - 1 - k,
            "body_beyond_atr": round(((bars[k].c - e["level"]) * d) / atr, 2) if atr else None,
            "_line_now": line(size),
        })
    return events


def tf_core(bars: list[Bar], tf: str, s: ChannelSettings) -> dict:
    """Price-independent channel geometry, touches, statistics, events and breakouts for one timeframe."""
    size = len(bars)
    if size < s.min_bars:
        return {"available": False, "bars": size}
    p = size if tf == "YTD" else min(s.periods.get(tf, 60), size)
    fits = _Fits([b.c for b in bars])
    slope, mid, sd = fits.fit(size - p, size)
    half = s.width_sd * sd
    upper, lower = mid + half, mid - half
    atr_list = wilder_atr(true_ranges(bars), min(s.atr_period, max(2, size - 2)))
    atr = atr_list[-1] if atr_list else (max(b.h for b in bars) - min(b.l for b in bars)) / max(1, size)
    a = size - p
    mid_at = lambda i: mid - slope * (size - 1 - i)  # noqa: E731
    tol = s.touch_atr * atr
    up_flags = [bars[i].h >= mid_at(i) + half - tol for i in range(a, size)]
    lo_flags = [bars[i].l <= mid_at(i) - half + tol for i in range(a, size)]
    up_touch = [a + i for i in _touch_groups(up_flags, s.touch_gap)]
    lo_touch = [a + i for i in _touch_groups(lo_flags, s.touch_gap)]
    inside = sum(1 for i in range(a, size) if mid_at(i) - half <= bars[i].c <= mid_at(i) + half) / p
    # Persistence: walk back while closes stay inside the channel extended to the left (with touch tolerance).
    age = p
    for i in range(a - 1, -1, -1):
        if mid_at(i) - half - tol <= bars[i].c <= mid_at(i) + half + tol:
            age += 1
        else:
            break
    if p >= 8:
        q = max(2, p // 4)
        _, _, sd_prev = fits.fit(max(0, size - p - q), size - q)
        ratio = sd / sd_prev if sd_prev else 1.0
        width_trend = "EXPANDING" if ratio > 1.1 else "CONTRACTING" if ratio < 0.9 else "STABLE"
    else:
        width_trend = "STABLE"
    widths, slopes = [], []
    for end in range(max(p, size - s.stat_windows), size + 1):
        sl, _, sdw = fits.fit(end - p, end)
        widths.append(2 * s.width_sd * sdw)
        slopes.append(sl)
    direction = _direction(slope, p, upper - lower, s)
    if inside >= s.inside_valid and len(up_touch) >= 2 and len(lo_touch) >= 2:
        validity = {"key": "VALID", "label": "Valid (Respecting Channel)"}
    elif inside >= s.inside_valid:
        validity = {"key": "FORMING", "label": "Forming (Few Touches)"}
    else:
        validity = {"key": "LOOSE", "label": "Loose (Closes Outside)"}
    breakouts = _breakouts(bars, fits, p, atr, tf, s) if tf in EVENT_TIMEFRAMES and size > p + 1 else []

    events = []
    for i in up_touch[-4:]:
        nxt = bars[i + 1 : i + 3]
        respected = bool(nxt) and all(x.c < mid_at(i) + half for x in nxt)
        events.append({"at": _closed_at(bars[i], tf), "event": "Test Upper", "level": mid_at(i) + half,
                       "result": "Respect" if respected else "Testing" if not nxt else "Pressing"})
    for i in lo_touch[-4:]:
        nxt = bars[i + 1 : i + 3]
        respected = bool(nxt) and all(x.c > mid_at(i) - half for x in nxt)
        events.append({"at": _closed_at(bars[i], tf), "event": "Channel Touch" if direction == "ASCENDING" else "Test Lower",
                       "level": mid_at(i) - half, "result": "Rebound" if respected else "Testing" if not nxt else "Pressing"})
    for i in up_touch[-3:]:
        j = next((j for j in range(i + 1, size) if bars[j].c <= mid_at(j)), None)
        if j is not None:
            events.append({"at": _closed_at(bars[j], tf), "event": "Pullback to Mid", "level": mid_at(j), "result": "Completed"})
    if p >= 7:
        hs, ls = pivots(bars[a:], 2)
        prev: dict[str, float] = {}
        for i, price, side in sorted([(i, v, "H") for i, v in hs] + [(i, v, "L") for i, v in ls]):
            if side in prev:
                name = ("Higher High" if price > prev[side] else "Lower High") if side == "H" else ("Higher Low" if price > prev[side] else "Lower Low")
                events.append({"at": _closed_at(bars[a + i], tf), "event": name, "level": price, "result": "Confirmed"})
            prev[side] = price
    for b in breakouts[-4:]:
        events.append({"at": b["at"], "event": "Breakout Attempt" if not b["confirmed"] else f"Breakout {'↑' if b['direction'] == 'UP' else '↓'}",
                       "level": b["level"], "result": "Failed" if b["failed"] else "Confirmed" if b["confirmed"] else "Developing"})
    for e in events:
        e["tf"] = tf
    events.sort(key=lambda e: e["at"], reverse=True)

    spark_n = min(40, size)
    sa = size - spark_n
    la = max(sa, a)
    return {
        "available": True,
        "bars": size,
        "period": p,
        "slope": slope,
        "slope_pct": slope / mid * 100 if mid else 0.0,
        "upper": upper,
        "mid": mid,
        "lower": lower,
        "half": half,
        "width": upper - lower,
        "atr": atr,
        "width_atr": (upper - lower) / atr if atr else None,
        "width_trend": width_trend,
        "direction": direction,
        "touches_upper": len(up_touch),
        "touches_lower": len(lo_touch),
        "inside_ratio": round(inside, 3),
        "validity": validity,
        "age": age,
        "fit_start": bars[a].t.isoformat(),
        "last_at": bars[-1].t.isoformat(),
        "closed_at": _closed_at(bars[-1], tf),
        "last_close": bars[-1].c,
        "lines": {
            "upper": [[bars[a].t.isoformat(), mid_at(a) + half], [bars[-1].t.isoformat(), upper]],
            "mid": [[bars[a].t.isoformat(), mid_at(a)], [bars[-1].t.isoformat(), mid]],
            "lower": [[bars[a].t.isoformat(), mid_at(a) - half], [bars[-1].t.isoformat(), lower]],
        },
        "stats": {
            "avg_width": sum(widths) / len(widths),
            "min_width": min(widths),
            "max_width": max(widths),
            "avg_slope": sum(slopes) / len(slopes),
            "touches": len(up_touch) + len(lo_touch),
            "touches_upper": len(up_touch),
            "touches_lower": len(lo_touch),
            "breakout_attempts": len(breakouts),
            "successful_breakouts": sum(1 for b in breakouts if b["confirmed"] and not b["failed"]),
            "false_breakouts": sum(1 for b in breakouts if b["failed"]),
        },
        "spark": {
            "candles": [{"t": b.t.isoformat(), "o": b.o, "h": b.h, "l": b.l, "c": b.c} for b in bars[sa:]],
            "upper": [mid_at(la) + half, upper],
            "lower": [mid_at(la) - half, lower],
            "from": la - sa,
        },
        "events": events[:12],
        "breakouts": breakouts,
    }


def channel_core(bars: dict[str, list[Bar]], s: ChannelSettings) -> dict:
    cb = channel_bars(bars)
    return {tf: tf_core(cb[tf], tf, s) for tf in CHANNEL_TIMEFRAMES}


# ----- live views -----


def _pos(c: dict, price: float) -> float | None:
    if not c.get("available") or c["upper"] == c["lower"]:
        return None
    return (price - c["lower"]) / (c["upper"] - c["lower"])


def _state(c: dict, pos: float | None, s: ChannelSettings) -> str:
    if pos is None:
        return "ACTIVE"
    if pos > 1.0:
        return "BREAKOUT_UP"
    if pos < 0.0:
        return "BREAKOUT_DOWN"
    if pos >= 1 - s.test_pct / 100 * 2:
        return "TESTING_UPPER"
    if pos <= s.test_pct / 100 * 2:
        return "TESTING_LOWER"
    return "ACTIVE"


def _slope_strength(c: dict) -> str:
    drift = abs(c["slope"]) * (c["period"] - 1)
    r = drift / c["width"] if c["width"] else 0
    return "Strong" if r >= 1.5 else "Moderate" if r >= 0.5 else "Weak"


def _sign(direction: str | None) -> int:
    return 1 if direction == "ASCENDING" else -1 if direction == "DESCENDING" else 0


def tf_view(core: dict, tf: str, price: float | None, s: ChannelSettings) -> dict:
    c = core.get(tf) or {}
    if not c.get("available"):
        return {"tf": tf, "available": False}
    px = price if price is not None else c["last_close"]
    pos = _pos(c, px)
    state = _state(c, pos, s)
    atr = c["atr"] or 0
    return {
        "tf": tf,
        "available": True,
        "direction": {"key": DIRECTIONS[c["direction"]], "label": DIRECTIONS[c["direction"]].title()},
        "slope": c["slope"],
        "slope_strength": _slope_strength(c),
        "upper": c["upper"],
        "mid": c["mid"],
        "lower": c["lower"],
        "width": c["width"],
        "width_atr": c["width_atr"],
        "width_trend": c["width_trend"],
        "position": None if pos is None else round(pos * 100, 1),
        "half": None if pos is None else "Upper Half" if pos >= 0.5 else "Lower Half",
        "state": {"key": state, "label": STATES[state]},
        "validity": c["validity"],
        "distance_upper": c["upper"] - px,
        "distance_lower": px - c["lower"],
        "distance_upper_atr": round((c["upper"] - px) / atr, 2) if atr else None,
        "distance_lower_atr": round((px - c["lower"]) / atr, 2) if atr else None,
        "touches_upper": c["touches_upper"],
        "touches_lower": c["touches_lower"],
        "age": c["age"],
        "age_unit": UNITS[tf],
        "period": c["period"],
        "atr": c["atr"],
        "closed_at": c["closed_at"],
    }


def alignment(views: dict[str, dict], direction_key: str | None) -> dict:
    avail = [v for v in views.values() if v.get("available")]
    agree = [v for v in avail if direction_key and v["direction"]["key"] == direction_key]
    return {"aligned": len(agree), "total": len(avail), "direction": direction_key}


def scenarios(v: dict, parent: dict | None, c: dict) -> dict:
    """Structural scenario weights (sum 100) — continuation, breakout or reversal of the channel."""
    pos = (v["position"] or 50) / 100
    d = _sign({"UPTREND": "ASCENDING", "DOWNTREND": "DESCENDING"}.get(v["direction"]["key"]))
    pd = _sign({"UPTREND": "ASCENDING", "DOWNTREND": "DESCENDING"}.get((parent or {}).get("direction", {}).get("key")))
    valid = v["validity"]["key"] == "VALID"
    edge = pos >= 0.85 or pos <= 0.15
    cont = 30 + 25 * valid + 20 * (d != 0 and pd == d) + 15 * (1 - min(1.0, abs(pos - 0.5) * 2))
    brk = 10 + 25 * edge + 15 * (c["width_trend"] == "CONTRACTING") + 10 * (max(v["touches_upper"], v["touches_lower"]) >= 3) + 10 * (not valid)
    against = (d == 1 and pos >= 0.85) or (d == -1 and pos <= 0.15)
    rev = 8 + 20 * (d != 0 and pd == -d) + 12 * against + 10 * (d == 0)
    total = cont + brk + rev
    a, b = round(100 * cont / total), round(100 * brk / total)
    return {"continue": a, "breakout": b, "reversal": 100 - a - b}


def channel_detail(core: dict, price: float | None, tf: str, s: ChannelSettings) -> dict:
    views = {t: tf_view(core, t, price, s) for t in CHANNEL_TIMEFRAMES}
    v = views.get(tf) or {}
    c = core.get(tf) or {}
    if not v.get("available"):
        return {"available": False, "reason": f"Insufficient closed {tf} history ({c.get('bars', 0)} bars)", "views": views}
    px = price if price is not None else c["last_close"]
    parent_tf = PARENT.get(tf)
    parent = views.get(parent_tf) if parent_tf else None
    parent = parent if parent and parent.get("available") else None
    al = alignment(views, v["direction"]["key"])
    up = v["direction"]["key"] == "UPTREND"
    down = v["direction"]["key"] == "DOWNTREND"
    pos = v["position"] or 0
    if v["state"]["key"].startswith("BREAKOUT"):
        nxt_event = "Retest of Broken Boundary"
    elif up:
        nxt_event = "Test Upper Boundary" if pos >= 50 else "Rotation to Upper Boundary" if pos >= 20 else "Rebound from Lower Boundary"
    elif down:
        nxt_event = "Test Lower Boundary" if pos <= 50 else "Rotation to Lower Boundary" if pos <= 80 else "Rejection at Upper Boundary"
    else:
        nxt_event = "Test Upper Boundary" if pos >= 50 else "Test Lower Boundary"
    next_level = c["upper"] if (up or (not down and pos >= 50)) else c["lower"]
    invalidation = c["lower"] if up else c["upper"] if down else None
    w = c["width"]
    key_levels = {
        "upper": c["upper"], "upper_ext_1": c["upper"] + 0.5 * w, "upper_ext_2": c["upper"] + w, "mid": c["mid"],
        "lower": c["lower"], "lower_ext_1": c["lower"] - 0.5 * w, "lower_ext_2": c["lower"] - w,
        "invalidation": invalidation, "atr": c["atr"],
        "to_upper": c["upper"] - px, "to_lower": c["lower"] - px,
        "to_upper_atr": round((c["upper"] - px) / c["atr"], 2) if c["atr"] else None,
        "to_lower_atr": round((c["lower"] - px) / c["atr"], 2) if c["atr"] else None,
    }
    events = []
    for t in (tf, *(x for x in ("W", "D1", "H8") if x != tf)):
        events += (core.get(t) or {}).get("events", [])
    events.sort(key=lambda e: e["at"], reverse=True)
    return {
        "available": True,
        "tf": tf,
        "price": px,
        "view": v,
        "views": views,
        "alignment": al,
        "context": {
            "parent_tf": parent_tf,
            "parent": parent,
            "position_in_parent": None if not parent else parent["position"],
            "next_level": next_level,
            "next_level_role": "Resistance" if next_level == c["upper"] else "Support",
            "next_event": nxt_event,
            "invalidation": invalidation,
        },
        "scenarios": scenarios(v, parent, c),
        "stats": {**c["stats"], "atr": c["atr"]},
        "key_levels": key_levels,
        "lines": c["lines"],
        "events": events[:12],
        "sparks": {t: (core.get(t) or {}).get("spark") for t in CHANNEL_TIMEFRAMES},
    }


# ----- breakout & retest -----


def breakout_status(b: dict, price: float | None, atr: float | None, s: ChannelSettings) -> tuple[str, str]:
    tol = s.retest_atr * (atr or 0)
    d = 1 if b["direction"] == "UP" else -1
    retest = "COMPLETED" if b.get("completed_at") else "TESTING" if b.get("retest_at") else "NONE"
    if b["failed"]:
        return "FAILED", retest
    line_now = b["_line_now"]
    # Live price back inside the frozen channel beyond the retest tolerance: no longer a retest.
    if price is not None and (price - line_now) * d < -tol:
        return "INSIDE", retest
    near = price is not None and (price - line_now) * d <= tol
    if not b["confirmed"]:
        return ("TESTING" if near else "DEVELOPING"), ("TESTING" if near else "PENDING")
    if near:
        return "RETESTING", "TESTING"
    if b.get("completed_at"):
        return "CONFIRMED", "COMPLETED"
    if b.get("retest_at"):
        return "RETESTING", "TESTING"
    return "CONFIRMED", "PENDING"


def pip_size(symbol: str) -> float:
    if symbol.startswith("XAU"):
        return 0.1
    return 0.01 if symbol.endswith("JPY") else 0.0001


def live_breakouts(symbol: str, core: dict, price: float | None, s: ChannelSettings) -> list[dict]:
    out = []
    pip = pip_size(symbol)
    for tf in EVENT_TIMEFRAMES:
        c = core.get(tf) or {}
        for b in c.get("breakouts", []):
            st, rt = breakout_status(b, price, c.get("atr"), s)
            d = 1 if b["direction"] == "UP" else -1
            result = None if price is None else (price - b["close"]) * d / pip
            out.append({
                **{k: v for k, v in b.items() if not k.startswith("_")},
                "symbol": symbol,
                "label": f"{'Bullish' if d == 1 else 'Bearish'} Breakout",
                "status": {"key": st, "label": BREAKOUT_STATUS[st]},
                "retest": {"key": rt, "label": RETEST_STATUS[rt]},
                "retest_now": b["_line_now"],
                "result_pips": None if result is None else round(result, 1),
                "distance_pips": None if price is None else round((price - b["_line_now"]) / pip, 1),
                "distance_atr": None if price is None or not c.get("atr") else round((price - b["_line_now"]) * d / c["atr"], 2),
            })
    out.sort(key=lambda e: e["at"], reverse=True)
    return out


def setup_candidates(symbol: str, core: dict, price: float | None, s: ChannelSettings) -> list[dict]:
    """Channels whose boundary price is approaching (not yet broken)."""
    if price is None:
        return []
    out = []
    for tf in EVENT_TIMEFRAMES:
        v = tf_view(core, tf, price, s)
        if not v.get("available") or v["position"] is None:
            continue
        pos = v["position"]
        if not (pos >= 100 - s.approach_pct or pos <= s.approach_pct) or pos > 100 or pos < 0:
            continue
        upper = pos >= 50
        dist_atr = abs(v["distance_upper_atr"] if upper else v["distance_lower_atr"]) if v["atr"] else None
        parent = tf_view(core, PARENT[tf], price, s)
        pdir = (parent.get("direction") or {}).get("key") if parent.get("available") else None
        with_parent = (upper and pdir == "UPTREND") or (not upper and pdir == "DOWNTREND")
        score = 40 * (v["validity"]["key"] == "VALID") + 30 * with_parent + 30 * (dist_atr is not None and dist_atr <= 0.5)
        out.append({
            "symbol": symbol, "tf": tf,
            "state": "Testing" if (pos >= 100 - s.test_pct or pos <= s.test_pct) else "Approaching",
            "boundary": "UPPER" if upper else "LOWER",
            "position": pos,
            "distance_atr": dist_atr,
            "quality": {"key": "HIGH", "label": "High"} if score >= 70 else {"key": "MEDIUM", "label": "Medium"} if score >= 40
            else {"key": "LOW", "label": "Low"},
            "score": score,
            "expected": "Breakout" if with_parent else "Rejection",
        })
    return out


def breakout_detail(symbol: str, core: dict, price: float | None, tf: str, s: ChannelSettings) -> dict:
    events = [e for e in live_breakouts(symbol, core, price, s) if e["tf"] == tf]
    c = core.get(tf) or {}
    related = []
    for t in EVENT_TIMEFRAMES:
        v = tf_view(core, t, price, s)
        if v.get("available"):
            related.append({"tf": t, "state": v["state"], "direction": v["direction"]})
    if not events:
        return {"available": False, "tf": tf, "related": related,
                "reason": f"No {tf} channel breakout in the last {s.scan_bars} closed bars"}
    e = events[0]
    d = 1 if e["direction"] == "UP" else -1
    pip = pip_size(symbol)
    w = 2 * e["half"]
    next_obj = e["level"] + d * w
    mid_last = e["mid_break"] + e["slope"] * e["bars_after"]
    lines = {
        name: [[e["fit_start_at"], e["fit_start_mid"] + off], [c.get("last_at"), mid_last + off]]
        for name, off in (("upper", e["half"]), ("mid", 0.0), ("lower", -e["half"]))
    }
    rt = e["retest"]["key"]
    lifecycle = [
        {"label": "Channel Identified", "done": True, "at": e["fit_start_at"]},
        {"label": "Price Approaching Boundary", "done": True, "at": None},
        {"label": "Breakout Detected", "done": True, "at": e["at"]},
        {"label": "Close Validation", "done": e["confirmed"], "at": e["at"] if e["confirmed"] else None},
        {"label": "Retest In Progress", "done": bool(e.get("retest_at")),
         "current": rt == "TESTING" and e["status"]["key"] in ("RETESTING", "TESTING"), "at": e.get("retest_at")},
        {"label": "Retest Confirmed", "done": bool(e.get("completed_at")), "at": e.get("completed_at")},
        {"label": "Continuation Active", "done": bool(e.get("completed_at")) and not e["failed"], "at": None},
    ]
    higher = [r for r in related if EVENT_TIMEFRAMES.index(r["tf"]) < EVENT_TIMEFRAMES.index(tf)]
    want = "UPTREND" if d == 1 else "DOWNTREND"
    valid = bool(higher) and all(r["direction"]["key"] == want for r in higher[-1:])
    word = "bullish" if d == 1 else "bearish"
    if e["failed"]:
        takeaway = f"{tf} {word} breakout failed — price closed back inside the channel. Structure reverts to the channel range."
    elif e["status"]["key"] == "INSIDE":
        takeaway = (f"{tf} {word} breakout has been given back — live price is back inside the frozen channel "
                    f"({e['retest_now']:,.{_dp(symbol)}f}). The break stays unconfirmed until price clears the boundary again.")
    elif rt == "COMPLETED":
        takeaway = (f"{tf} breakout and retest confirmed{' within higher timeframe ' + word + ' channel' if valid else ''}. "
                    f"Next channel objective {next_obj:,.{_dp(symbol)}f} (+{e['mfe_atr'] or 0:.2f} ATR so far). Invalid below {e['level']:,.{_dp(symbol)}f}."
                    if d == 1 else
                    f"{tf} breakdown and retest confirmed{' within higher timeframe ' + word + ' channel' if valid else ''}. "
                    f"Next channel objective {next_obj:,.{_dp(symbol)}f}. Invalid above {e['level']:,.{_dp(symbol)}f}.")
    elif rt == "TESTING":
        takeaway = f"{tf} {word} breakout is retesting the broken boundary ({e['retest_now']:,.{_dp(symbol)}f}). Waiting for the retest to hold."
    else:
        takeaway = f"{tf} {word} breakout {'confirmed' if e['confirmed'] else 'developing'}; retest of {e['retest_now']:,.{_dp(symbol)}f} still pending."
    return {
        "available": True,
        "tf": tf,
        "event": e,
        "lines": lines,
        "marks": {
            "breakout": {"at": e["bar_at"], "price": e["close"]},
            "retest": {"at": e["retest_bar_at"], "price": e["retest_level"]} if e.get("retest_bar_at") else None,
            "continuation": {"at": e["mfe_at"], "price": e["mfe_price"]} if e.get("mfe_at") and e.get("completed_at") else None,
            "boundary": {"at": e["bar_at"], "price": e["level"]},
        },
        "details": {
            "type": e["label"],
            "level": e["level"],
            "break_candle": e["bar_at"],
            "close_side": "Above" if d == 1 else "Below",
            "body_acceptance": (e.get("body_beyond_atr") or 0) >= 0.1,
            "retest_level": e["retest_now"] if not e.get("retest_level") else e["retest_level"],
            "retest": e["retest"],
            "retest_candle": e.get("retest_bar_at"),
            "follow_through_atr": e.get("mfe_atr"),
            "follow_through_pips": round(e["mfe"] / pip, 1),
            "valid_structure": valid,
            "valid_note": f"{tf} > {higher[-1]['tf']} {'breakout' if d == 1 else 'breakdown'}" if higher else tf,
            "next_objective": next_obj,
            "invalidation": e["level"] - d * s.retest_atr * (c.get("atr") or 0),
        },
        "lifecycle": lifecycle,
        "related": related,
        "takeaway": takeaway,
    }


def _dp(symbol: str) -> int:
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


# ----- trend-in-trend -----


def tit_view(symbol: str, core: dict, price: float | None, s: ChannelSettings) -> dict:
    views = {tf: tf_view(core, tf, price, s) for _, tf in LAYERS}
    layers = []
    parent_dir = None
    for lid, tf in LAYERS:
        v = views[tf]
        if v.get("available") and v["direction"]["key"] != "RANGING":
            parent_dir = v["direction"]["key"]
            parent_layer = lid
            break
    if parent_dir is None:
        return {"available": False, "reason": "No trending parent channel on W or D1", "layers": _layers(views, None)}
    sign = 1 if parent_dir == "UPTREND" else -1
    layers = _layers(views, parent_dir)
    ct = next((l for l in layers if l["id"] != parent_layer and l["layer_dir"] == -sign and l["id"] > parent_layer), None)
    parent_tf = dict(LAYERS)[parent_layer]
    pv = views[parent_tf]
    px = price if price is not None else (core.get("H1") or {}).get("last_close")
    word = "Bullish" if sign == 1 else "Bearish"
    base = {
        "available": True,
        "parent": {"layer": parent_layer, "tf": parent_tf, "direction": parent_dir, "position": pv["position"],
                   "state": pv["state"], "validity": pv["validity"]},
        "layers": layers,
        "price": px,
    }
    if ct is None:
        return {**base, "state": {"key": "ALIGNED", "label": "Aligned"}, "countertrend": None,
                "summary": f"{word} parent trend with no countertrend channel — layers aligned.", "setup": None,
                "lifecycle": _tit_lifecycle(True, False, False, False, False), "quality": None,
                "takeaways": [f"{TF_NAMES[parent_tf]} channel is {word.lower()} and active.",
                              "No lower-timeframe countertrend channel — no trend-in-trend pullback to track."]}
    ct_tf = ct["tf"]
    cv = views[ct_tf]
    cc = core[ct_tf]
    k = [l for _, l in LAYERS].index(ct_tf)
    exec_tf = LAYERS[min(k + 1, len(LAYERS) - 1)][1]
    ev = views[exec_tf]
    above_tf = LAYERS[max(k - 1, 0)][1]
    av = views[above_tf]
    ppos = (pv["position"] or 50) / 100
    depth = min(1.0, max(0.0, (1 - ppos) if sign == 1 else ppos))
    touches = min(1.0, (cc["touches_upper"] + cc["touches_lower"]) / 4)
    agef = min(1.0, cc["age"] / max(1, cc["period"]))
    maturity = round(100 * (0.5 * depth + 0.3 * touches + 0.2 * agef))
    phase = "Early" if maturity < 40 else "Mid" if maturity < 70 else "Late"
    rejoin = cv["upper"] if sign == 1 else cv["lower"]
    dist = (rejoin - px) * sign
    atr = cc["atr"] or 0
    est = max(1, math.ceil(abs(dist) / atr)) if atr else None
    exec_with = ev.get("available") and ev["direction"]["key"] == parent_dir
    rejoin_score = round(0.4 * maturity + 30 * (1.0 if exec_with else 0.3) + 30 * (1.0 if pv["validity"]["key"] == "VALID" else 0.5))
    l2_with = av.get("available") and av["direction"]["key"] == parent_dir
    quality = round((100 * (1 if l2_with or above_tf == parent_tf else 0) + maturity + rejoin_score + (100 if pv["validity"]["key"] == "VALID" else 50)) / 4)
    zone = sorted((cv["lower"], cv["lower"] + 0.2 * cv["width"])) if sign == 1 else sorted((cv["upper"] - 0.2 * cv["width"], cv["upper"]))
    obj1 = rejoin
    obj2 = av["upper"] if sign == 1 else av["lower"]
    invalid = (av["lower"] if sign == 1 else av["upper"]) if above_tf != ct_tf else (pv["lower"] if sign == 1 else pv["upper"])
    zmid = (zone[0] + zone[1]) / 2
    risk = abs(zmid - invalid)
    reward = abs(obj2 - zmid)
    in_zone = zone[0] <= px <= zone[1]
    rejoined = (px - rejoin) * sign > 0
    status = "ACTIVE" if in_zone or (maturity >= s.mature_pct and abs(dist) <= s.near_setup_atr * atr) else "DEVELOPING" if maturity < 50 else "MONITORING"
    setup = {
        "type": "Channel Rejoin (Trend Continuation)" if maturity >= 50 else "Pullback Continuation",
        "direction": parent_dir,
        "direction_label": f"{word} (with parent trend)",
        "zone": zone,
        "objective_1": obj1,
        "objective_1_label": f"{ct['id']} {'Upper' if sign == 1 else 'Lower'}",
        "objective_2": obj2,
        "objective_2_label": f"{LAYERS[max(k - 1, 0)][0]} {'Upper' if sign == 1 else 'Lower'}",
        "invalidation": invalid,
        "invalidation_label": f"{'below' if sign == 1 else 'above'} {LAYERS[max(k - 1, 0)][0]} channel",
        "ratio": round(reward / risk, 2) if risk else None,
        "quality": quality,
        "status": {"key": status, "label": status.title()},
    }
    countertrend = {
        "layer": ct["id"],
        "tf": ct_tf,
        "type": "Pullback Channel" if sign == 1 else "Rally Channel",
        "direction": cv["direction"],
        "phase": f"{phase} {'Pullback' if sign == 1 else 'Rally'}",
        "maturity": maturity,
        "position": cv["position"],
        "half": cv["half"],
        "distance_lower": cv["distance_lower"],
        "distance_upper": cv["distance_upper"],
        "distance_lower_atr": cv["distance_lower_atr"],
        "distance_upper_atr": cv["distance_upper_atr"],
        "rejoin_level": rejoin,
        "expected_bars": None if est is None else [max(1, est - 1), est + 1],
        "rejoin_score": rejoin_score,
        "invalidation": invalid,
        "exec_tf": exec_tf,
        "exec_layer": LAYERS[min(k + 1, len(LAYERS) - 1)][0],
    }
    dp = _dp(symbol)
    takeaways = [
        f"Higher timeframe ({parent_tf}) trend is {word.lower()} and {pv['state']['label'].lower()}.",
        f"Price is in {ct_tf} countertrend channel ({'pullback' if sign == 1 else 'rally'}).",
        f"Currently {round(cv['position'] or 0)}% into the {ct_tf} channel ({(cv['half'] or '').lower()}).",
        f"Rejoin score {rejoin_score}% — {'channel rejoin likely' if rejoin_score >= 60 else 'rejoin not yet supported'}.",
        f"Continuation zone: {zone[0]:,.{dp}f} – {zone[1]:,.{dp}f}.",
        f"Invalidation: {'close below' if sign == 1 else 'close above'} {invalid:,.{dp}f}.",
        f"Objectives: {obj1:,.{dp}f} then {obj2:,.{dp}f}.",
    ]
    return {
        **base,
        "state": {"key": "ACTIVE" if status == "ACTIVE" else "FORMING", "label": "Active" if status == "ACTIVE" else "Forming"},
        "tit_layer": ct["id"],
        "summary": f"{word} continuation setup",
        "countertrend": countertrend,
        "setup": setup,
        "quality": {"score": quality, "label": "High probability" if quality >= 70 else "Moderate" if quality >= 50 else "Low"},
        "next_event": {"label": "Channel Rejoin" if maturity >= 50 else "Countertrend Extension",
                       "bars": countertrend["expected_bars"]},
        "lifecycle": _tit_lifecycle(True, True, maturity >= s.mature_pct, in_zone or abs(dist) <= s.near_setup_atr * atr,
                                    bool(exec_with or rejoined)),
        "takeaways": takeaways,
        "charts": {"L1": parent_tf, "CT": ct_tf, "EXEC": exec_tf},
    }


def _layers(views: dict, parent_dir: str | None) -> list[dict]:
    out = []
    for lid, tf in LAYERS:
        v = views[tf]
        if not v.get("available"):
            out.append({"id": lid, "tf": tf, "available": False, "layer_dir": 0})
            continue
        d = v["direction"]["key"]
        layer_dir = 1 if d == "UPTREND" else -1 if d == "DOWNTREND" else 0
        psign = 1 if parent_dir == "UPTREND" else -1 if parent_dir == "DOWNTREND" else 0
        if lid == "L1":
            align = "—"
        elif layer_dir and layer_dir == psign:
            align = "With L1"
        elif layer_dir and layer_dir == -psign:
            align = "Countertrend"
        else:
            align = "Neutral"
        state = v["state"]
        if layer_dir and layer_dir == -psign and not state["key"].startswith("BREAKOUT"):
            state = {"key": "PULLBACK", "label": "Pullback"}
        out.append({
            "id": lid, "tf": tf, "available": True, "layer_dir": layer_dir,
            "trend": {"key": d, "label": {"UPTREND": "Bullish", "DOWNTREND": "Bearish"}.get(d, "Ranging")},
            "state": state, "position": v["position"], "half": v["half"], "alignment": align,
        })
    return out


def _tit_lifecycle(parent: bool, ct: bool, mature: bool, near: bool, trigger: bool) -> list[dict]:
    steps = [
        ("Parent Trend Identified (L1)", parent),
        ("Countertrend Channel Forming", ct),
        ("Countertrend Mature", mature),
        ("Price Near Rejoin Zone", near),
        ("Trigger / Confirmation", trigger),
        ("Handoff to Opportunity Engine", False),
        ("Objective: Parent Trend Continuation", False),
    ]
    out, chain = [], True
    for label, done in steps:
        chain = chain and done
        out.append({"label": label, "done": chain})
    cur = next((i for i, x in enumerate(out) if not x["done"]), None)
    if cur is not None:
        out[cur]["current"] = True
    return out
