"""H8 BOS & BTL Intelligence — closed-bar structural break analysis.

W  : confirmed fractals + SCH oscillator (0–100, separate from price).
H8 : BOS = closed H8 close beyond a confirmed swing (wicks never count);
     BTL = closed H8 close beyond a validated swing trend line by the ATR tolerance.
     Both are replayed bar by bar so each break is attributable to one closed bar.
H1 : post-break LH→LL / HH→HL validation.
M30: retest entry, reaction, failed reclaim and LTF confirmation inside the retest zone.

Analysis only — nothing here issues trade direction or BUY/SELL.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .h8_bos_btl_config import H8BosBtlSettings
from .scanner_analytics import Bar, market_structure, pivots, true_ranges, wilder_atr

TF_DELTA = {"W": timedelta(days=7), "H8": timedelta(hours=8), "H1": timedelta(hours=1), "M30": timedelta(minutes=30)}
BEAR, BULL, NEUTRAL = "Bearish", "Bullish", "Neutral"
MIN_H8_BARS = 40
MIN_W_BARS = 20

RETEST = {
    "AWAITING": "Awaiting retest",
    "IN_ZONE": "Retesting now",
    "RETESTED": "Retested — holding",
    "RECLAIMED": "Level reclaimed",
    "FAILED": "Invalidated",
}
H1_STATUS = {
    "CONFIRMED": "Validated",
    "FORMING": "Forming",
    "PENDING": "Awaiting swing",
    "CONTRADICTED": "Contradicted",
    "NO_EVENT": "No H8 event",
    "INSUFFICIENT": "Insufficient data",
}
M30_STATUS = {
    "LTF_CONFIRMED": "LTF confirmation",
    "FAILED_RECLAIM": "Failed reclaim",
    "REACTION": "Reaction",
    "RECLAIMING": "Reclaim attempt",
    "IN_RETEST": "Retest entry",
    "AWAITING": "Awaiting retest",
    "INVALID": "Invalidated",
    "NO_EVENT": "No H8 event",
    "INSUFFICIENT": "Insufficient data",
}


def _kl(key: str, table: dict[str, str]) -> dict:
    return {"key": key, "label": table[key]}


def _close_t(b: Bar, tf: str) -> datetime:
    return b.t + TF_DELTA[tf]


def atr_series(bars: list[Bar], period: int) -> list[float | None]:
    """Wilder ATR aligned to ``bars`` (None until enough history)."""
    atr = wilder_atr(true_ranges(bars), period)
    return [None] * period + atr if atr else [None] * len(bars)


def _ema(xs: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n:
        return out
    k = 2.0 / (n + 1)
    v = sum(xs[:n]) / n
    out[n - 1] = v
    for i in range(n, len(xs)):
        v = xs[i] * k + v * (1 - k)
        out[i] = v
    return out


def _stoch_smooth(xs: list[float | None], window: int) -> list[float | None]:
    """Schaff stage: stochastic of ``xs`` over ``window`` followed by a 0.5 factor smoothing."""
    out: list[float | None] = [None] * len(xs)
    prev_raw = prev = None
    for i, x in enumerate(xs):
        win = [v for v in xs[max(0, i - window + 1) : i + 1] if v is not None]
        if x is None or len(win) < window:
            continue
        lo, hi = min(win), max(win)
        raw = (x - lo) / (hi - lo) * 100.0 if hi > lo else (prev_raw if prev_raw is not None else 50.0)
        prev_raw = raw
        prev = raw if prev is None else prev + 0.5 * (raw - prev)
        out[i] = prev
    return out


def sch_series(bars: list[Bar], s: H8BosBtlSettings) -> list[tuple[float, float] | None]:
    """SCH oscillator (fast, signal) on closed bars, 0–100. Schaff Trend Cycle by default."""
    closes = [b.c for b in bars]
    if s.sch_method == "STOCHASTIC":
        raw: list[float | None] = []
        for i in range(len(bars)):
            if i + 1 < s.sch_cycle:
                raw.append(None)
                continue
            win = bars[i + 1 - s.sch_cycle : i + 1]
            lo, hi = min(b.l for b in win), max(b.h for b in win)
            raw.append((bars[i].c - lo) / (hi - lo) * 100.0 if hi > lo else 50.0)
        fast = _sma_opt(raw, s.sch_signal)
    else:
        ef, es = _ema(closes, s.sch_fast), _ema(closes, s.sch_slow)
        macd = [None if a is None or b is None else a - b for a, b in zip(ef, es)]
        fast = _stoch_smooth(_stoch_smooth(macd, s.sch_cycle), s.sch_cycle)
    signal = _sma_opt(fast, s.sch_signal)
    return [None if f is None or g is None else (max(0.0, min(100.0, f)), max(0.0, min(100.0, g))) for f, g in zip(fast, signal)]


def _sma_opt(xs: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        win = xs[i - n + 1 : i + 1]
        if all(v is not None for v in win):
            out[i] = sum(win) / n  # type: ignore[arg-type]
    return out


# ---------------------------------------------------------------- Weekly ----


def weekly_core(w: list[Bar], s: H8BosBtlSettings) -> dict:
    if len(w) < MIN_W_BARS:
        return {"available": False, "reason": f"Insufficient closed weekly history ({len(w)}/{MIN_W_BARS})"}
    highs, lows = pivots(w, s.w_fractal_strength)
    sch = sch_series(w, s)
    fractals = [{"t": w[i].t.isoformat(), "price": p, "kind": "HIGH", "confirmed": True} for i, p in highs]
    fractals += [{"t": w[i].t.isoformat(), "price": p, "kind": "LOW", "confirmed": True} for i, p in lows]
    fractals.sort(key=lambda f: f["t"])
    valid = [(i, v) for i, v in enumerate(sch) if v is not None]
    if not valid:
        return {"available": False, "reason": "Insufficient weekly history for SCH"}
    i_last, (fast, signal) = valid[-1]
    prev = valid[-2][1] if len(valid) > 1 else (fast, signal)
    direction = BULL if fast > signal else BEAR if fast < signal else NEUTRAL
    cross_ago = None
    for k in range(len(valid) - 1, 0, -1):
        (f1, g1), (f0, g0) = valid[k][1], valid[k - 1][1]
        if (f1 > g1) != (f0 > g0):
            cross_ago = len(valid) - 1 - k
            break
    if fast >= 75:
        state = "Overbought"
    elif fast <= 25:
        state = "Oversold"
    elif cross_ago is not None and cross_ago <= 2:
        state = f"{direction} cross"
    else:
        state = "Rising" if fast > prev[0] else "Falling" if fast < prev[0] else "Flat"
    return {
        "available": True,
        "last_closed": w[-1].t.isoformat(),
        "fast": round(fast, 2),
        "signal": round(signal, 2),
        "direction": direction,
        "state": state,
        "cross_bars_ago": cross_ago,
        "active_high": highs[-1][1] if highs else None,
        "active_high_at": w[highs[-1][0]].t.isoformat() if highs else None,
        "active_low": lows[-1][1] if lows else None,
        "active_low_at": w[lows[-1][0]].t.isoformat() if lows else None,
        "fractals": fractals,
        "sch": [{"t": w[i].t.isoformat(), "fast": round(v[0], 2), "signal": round(v[1], 2)} for i, v in valid],
    }


def weekly_live(core: dict, price: float | None) -> dict:
    """Price position inside the active weekly fractal range plus the backend interpretation text."""
    if not core.get("available"):
        return core
    hi, lo = core["active_high"], core["active_low"]
    pos = label = fractal_state = None
    if hi is not None and lo is not None and hi > lo and price is not None:
        pos = (price - lo) / (hi - lo) * 100.0
        if pos > 100:
            label, fractal_state = "Above fractal high", "Above active fractal high"
        elif pos < 0:
            label, fractal_state = "Below fractal low", "Below active fractal low"
        else:
            label = "Upper half" if pos >= 50 else "Lower half"
            fractal_state = "Inside active fractal range"
    d = core["direction"]
    where = {
        None: "the weekly fractal range is not defined",
        "Above active fractal high": "price trades above the last confirmed weekly fractal high",
        "Below active fractal low": "price trades below the last confirmed weekly fractal low",
        "Inside active fractal range": "price remains inside the active weekly fractal range",
    }[fractal_state]
    return {
        **core,
        "position_pct": None if pos is None else round(pos, 1),
        "position_label": label,
        "fractal_state": fractal_state,
        "interpretation": f"Weekly SCH is {d.lower()} ({core['state'].lower()}) while {where}.",
    }


# -------------------------------------------------------------------- H8 ----


def _line_at(a: tuple[int, float], b: tuple[int, float], i: float) -> float:
    (ia, pa), (ib, pb) = a, b
    return pa + (pb - pa) * (i - ia) / (ib - ia)


def _line_respected(bars: list[Bar], atr: list[float | None], a, b, tol: float, below: bool) -> bool:
    """No close between the two anchors crossed the line (support: close below; resistance: close above)."""
    for j in range(a[0] + 1, b[0]):
        x = atr[j] or 0.0
        y = _line_at(a, b, j)
        if (below and bars[j].c < y - tol * x) or (not below and bars[j].c > y + tol * x):
            return False
    return True


def _confirmed_by(pivs: list[tuple[int, float]], i: int, k: int) -> list[tuple[int, float]]:
    """Pivots whose ``k`` right-side bars had all closed before bar ``i``."""
    return [p for p in pivs if p[0] + k < i]


def _replay(h8: list[Bar], atr: list[float | None], highs, lows, s: H8BosBtlSettings) -> tuple[list[dict], list[dict], dict]:
    """Bar-by-bar replay of BOS and BTL breaks. Returns (bos events, btl events, still-pending levels)."""
    k = s.h8_swing_strength
    bos: list[dict] = []
    btl: list[dict] = []
    used_hi: set[int] = set()
    used_lo: set[int] = set()
    used_sup: set[tuple[int, int]] = set()
    used_res: set[tuple[int, int]] = set()
    n = len(h8)
    for i in range(n + 1):
        ch, cl = _confirmed_by(highs, i, k), _confirmed_by(lows, i, k)
        sup = res = None
        if len(cl) >= 2 and cl[-1][1] > cl[-2][1] and (cl[-2][0], cl[-1][0]) not in used_sup:
            if _line_respected(h8, atr, cl[-2], cl[-1], s.btl_tolerance_atr, True):
                sup = (cl[-2], cl[-1])
        if len(ch) >= 2 and ch[-1][1] < ch[-2][1] and (ch[-2][0], ch[-1][0]) not in used_res:
            if _line_respected(h8, atr, ch[-2], ch[-1], s.btl_tolerance_atr, False):
                res = (ch[-2], ch[-1])
        last_hi = ch[-1] if ch and ch[-1][0] not in used_hi else None
        last_lo = cl[-1] if cl and cl[-1][0] not in used_lo else None
        if i == n:
            return bos, btl, {"swing_high": last_hi, "swing_low": last_lo, "support": sup, "resistance": res, "atr": atr[-1]}
        a = atr[i]
        if a is None:
            continue
        b = h8[i]
        if last_lo and b.c < last_lo[1] - s.bos_tolerance_atr * a:
            used_lo.add(last_lo[0])
            bos.append(_event("BOS", BEAR, i, last_lo[1], a, ch, cl, h8, swing=last_lo))
        if last_hi and b.c > last_hi[1] + s.bos_tolerance_atr * a:
            used_hi.add(last_hi[0])
            bos.append(_event("BOS", BULL, i, last_hi[1], a, ch, cl, h8, swing=last_hi))
        if sup and b.c < _line_at(*sup, i) - s.btl_tolerance_atr * a:
            used_sup.add((sup[0][0], sup[1][0]))
            btl.append(_event("BTL", BEAR, i, _line_at(*sup, i), a, ch, cl, h8, line=sup))
        if res and b.c > _line_at(*res, i) + s.btl_tolerance_atr * a:
            used_res.add((res[0][0], res[1][0]))
            btl.append(_event("BTL", BULL, i, _line_at(*res, i), a, ch, cl, h8, line=res))
    return bos, btl, {}


def _event(kind: str, direction: str, i: int, level: float, atr: float, ch, cl, h8: list[Bar], *, swing=None, line=None) -> dict:
    b = h8[i]
    if direction == BEAR:
        inv = ch[-1][1] if ch else max(x.h for x in h8[max(0, i - 10) : i])
    else:
        inv = cl[-1][1] if cl else min(x.l for x in h8[max(0, i - 10) : i])
    side = "<" if direction == BEAR else ">"
    what = "swing low" if (kind == "BOS" and direction == BEAR) else "swing high" if kind == "BOS" else "trend line"
    return {
        "kind": kind,
        "direction": direction,
        "i": i,
        "bar_open": b.t.isoformat(),
        "at": _close_t(b, "H8").isoformat(),
        "close": b.c,
        "level": level,
        "atr": atr,
        "strength_atr": round(abs(b.c - level) / atr, 2) if atr else None,
        "invalidation": inv,
        "swing": None if swing is None else {"t": h8[swing[0]].t.isoformat(), "price": swing[1]},
        "line": None if line is None else [[h8[p[0]].t.isoformat(), p[1]] for p in line],
        "_line": line,
        "proof": f"Closed H8 bar opened {b.t:%Y-%m-%d %H:%M} UTC closed {b.c} {side} {what} {level:.6g}",
    }


def _retest_eval(h8: list[Bar], parts: list[dict], direction: str, pad: float, inv: float) -> str:
    """Post-break closed-bar retest status (FAILED / RECLAIMED / RETESTED / AWAITING) against the broken levels."""
    j = max(p["i"] for p in parts)
    lv = [p["level"] for p in parts]
    lo, hi = min(lv) - pad, max(lv) + pad
    touched = False
    for m in range(j + 1, len(h8)):
        b = h8[m]
        if direction == BEAR:
            if b.c > inv:
                return "FAILED"
            if b.c > hi:
                return "RECLAIMED"
            touched = touched or b.h >= lo
        else:
            if b.c < inv:
                return "FAILED"
            if b.c < lo:
                return "RECLAIMED"
            touched = touched or b.l <= hi
    return "RETESTED" if touched else "AWAITING"


def _structure_label(ch, cl, broken: bool) -> str:
    if len(ch) < 2 or len(cl) < 2:
        return "Insufficient swings"
    up_hi, up_lo = ch[-1][1] > ch[-2][1], cl[-1][1] > cl[-2][1]
    label = (
        "Ascending Channel" if up_hi and up_lo
        else "Descending Channel" if not up_hi and not up_lo
        else "Contracting Range" if not up_hi and up_lo
        else "Expanding Range"
    )
    return f"{label} (Broken)" if broken else label


def h8_core(h8: list[Bar], s: H8BosBtlSettings) -> dict:
    if len(h8) < MIN_H8_BARS:
        return {"available": False, "reason": f"Insufficient closed H8 history ({len(h8)}/{MIN_H8_BARS})"}
    n = len(h8)
    atr = atr_series(h8, s.atr_period)
    highs, lows = pivots(h8, s.h8_swing_strength)
    bos_events, btl_events, pending = _replay(h8, atr, highs, lows, s)
    cutoff = n - s.active_bars

    def evaluated(e: dict | None) -> dict | None:
        if e is None:
            return None
        pad = s.retest_pad_atr * e["atr"]
        status = _retest_eval(h8, [e], e["direction"], pad, e["invalidation"])
        return {**e, "retest_key": status, "active": e["i"] >= cutoff and status not in ("FAILED", "RECLAIMED")}

    last_bos = evaluated(bos_events[-1] if bos_events else None)
    last_btl = evaluated(btl_events[-1] if btl_events else None)
    event = None
    act = [e for e in (last_bos, last_btl) if e and e["active"]]
    if (
        len(act) == 2
        and act[0]["direction"] == act[1]["direction"]
        and abs(act[0]["i"] - act[1]["i"]) <= s.composite_bars
    ):
        parts, kind = act, "BOS + BTL"
    elif act:
        latest = max(act, key=lambda e: (e["i"], e["kind"] == "BOS"))
        parts, kind = [latest], latest["kind"]
    else:
        parts, kind = [], None
    if parts:
        d = parts[0]["direction"]
        later = max(parts, key=lambda e: e["i"])
        inv = max(p["invalidation"] for p in parts) if d == BEAR else min(p["invalidation"] for p in parts)
        pad = s.retest_pad_atr * later["atr"]
        lv = [p["level"] for p in parts]
        status = _retest_eval(h8, parts, d, pad, inv)
        event = {
            "kind": kind,
            "direction": d,
            "at": later["at"],
            "bar_open": later["bar_open"],
            "close": later["close"],
            "break_strength_atr": max(p["strength_atr"] or 0 for p in parts),
            "retest": [min(lv) - pad, max(lv) + pad],
            "invalidation": inv,
            "retest_key": status,
            "bos": next((_public_part(p) for p in parts if p["kind"] == "BOS"), None),
            "btl": next((_public_part(p, n - 1, h8) for p in parts if p["kind"] == "BTL"), None),
            "analysis_id": f"H8BB-{later['bar_open'][:16]}-{kind.replace(' + ', '')}-{d[:4].upper()}",
        }
        if status in ("FAILED", "RECLAIMED"):
            event = None
    ch, cl = _confirmed_by(highs, n, s.h8_swing_strength), _confirmed_by(lows, n, s.h8_swing_strength)
    ms = market_structure(h8, s.h8_swing_strength)
    direction = event["direction"] if event else {"BULLISH": BULL, "BEARISH": BEAR}.get(ms["key"], NEUTRAL)
    broken = bool(event and event["btl"])
    channel = None
    if len(ch) >= 2 and len(cl) >= 2:
        upper = (ch[-2], ch[-1])
        lower = (cl[-2], cl[-1])
        if broken:
            btl = next(p for p in parts if p["kind"] == "BTL")
            if btl["direction"] == BEAR:
                lower = btl["_line"]
                prior = [p for p in ch if p[0] < btl["i"]]
                upper = (prior[-2], prior[-1]) if len(prior) >= 2 else upper
            else:
                upper = btl["_line"]
                prior = [p for p in cl if p[0] < btl["i"]]
                lower = (prior[-2], prior[-1]) if len(prior) >= 2 else lower
        channel = {
            "upper": _line_points(upper, h8),
            "lower": _line_points(lower, h8),
            "broken": broken,
        }
    swings = [{"t": h8[i].t.isoformat(), "price": p, "kind": "HIGH"} for i, p in ch[-6:]]
    swings += [{"t": h8[i].t.isoformat(), "price": p, "kind": "LOW"} for i, p in cl[-6:]]
    return {
        "available": True,
        "last_closed": h8[-1].t.isoformat(),
        "last_close": h8[-1].c,
        "atr": atr[-1],
        "direction": direction,
        "structure": _structure_label(ch, cl, broken),
        "event": event,
        "history": {
            "bos": [_public_part(e) for e in bos_events[-6:]],
            "btl": [_public_part(e, None, h8) for e in btl_events[-6:]],
        },
        "channel": channel,
        "swings": sorted(swings, key=lambda x: x["t"]),
        "pending": _pending_public(pending, h8, n),
    }


def _line_points(line, h8: list[Bar]) -> list[list]:
    """Two anchor points plus the projection to the last closed bar (times are bar open times)."""
    a, b = line
    last = len(h8) - 1
    return [[h8[a[0]].t.isoformat(), a[1]], [h8[b[0]].t.isoformat(), b[1]], [h8[last].t.isoformat(), _line_at(a, b, last)]]


def _public_part(e: dict, at_i: int | None = None, h8: list[Bar] | None = None) -> dict:
    out = {k: v for k, v in e.items() if not k.startswith("_") and k not in ("i", "atr", "active", "retest_key")}
    if e.get("_line") and at_i is not None:
        out["level_now"] = _line_at(*e["_line"], at_i)
    return out


def _pending_public(p: dict, h8: list[Bar], n: int) -> dict:
    """Unbroken levels the live price can develop through (projected to the forming bar)."""
    def line(l):
        return None if l is None else {"anchors": [[h8[x[0]].t.isoformat(), x[1]] for x in l], "level": _line_at(*l, n)}

    return {
        "swing_high": None if not p.get("swing_high") else p["swing_high"][1],
        "swing_low": None if not p.get("swing_low") else p["swing_low"][1],
        "support": line(p.get("support")),
        "resistance": line(p.get("resistance")),
    }


def h8_live(core: dict, last_bar: Bar | None, price: float | None, s: H8BosBtlSettings) -> dict:
    """Alert kind with live price: confirmed events come only from closed bars; live price can only add DEVELOPING."""
    if not core.get("available"):
        return {"kind": "MONITORING", "retest_status": None, "developing": None}
    ev = core["event"]
    if ev:
        key = ev["retest_key"]
        lo, hi = ev["retest"]
        if price is not None and lo <= price <= hi and key in ("AWAITING", "RETESTED"):
            key = "IN_ZONE"
        return {"kind": ev["kind"], "retest_status": _kl(key, RETEST), "developing": None}
    p, atr = core["pending"], core["atr"] or 0.0
    tol = s.btl_tolerance_atr * atr
    checks = []
    if p["swing_low"] is not None:
        checks.append(("BOS", BEAR, p["swing_low"], "swing low"))
    if p["swing_high"] is not None:
        checks.append(("BOS", BULL, p["swing_high"], "swing high"))
    if p["support"]:
        checks.append(("BTL", BEAR, p["support"]["level"] - tol, "trend line"))
    if p["resistance"]:
        checks.append(("BTL", BULL, p["resistance"]["level"] + tol, "trend line"))
    for kind, d, level, what in checks:
        live = price is not None and (price < level if d == BEAR else price > level)
        wick = last_bar is not None and (last_bar.l < level if d == BEAR else last_bar.h > level)
        if live or wick:
            basis = "Live price" if live else "Last closed H8 wick"
            return {
                "kind": "DEVELOPING",
                "retest_status": None,
                "developing": {
                    "event": kind,
                    "direction": d,
                    "level": level,
                    "basis": basis,
                    "detail": f"{basis} beyond {what} {level:.6g} — awaiting H8 close",
                },
            }
    return {"kind": "MONITORING", "retest_status": None, "developing": None}


# ------------------------------------------------------------- H1 / M30 ----


def _post(bars: list[Bar], at: datetime) -> int:
    return next((i for i, b in enumerate(bars) if b.t >= at), len(bars))


def _dir_of(ms: dict) -> str:
    return {"BULLISH": BULL, "BEARISH": BEAR}.get(ms.get("key"), NEUTRAL)


def h1_validation(h1: list[Bar], event: dict | None, s: H8BosBtlSettings) -> dict:
    if len(h1) < 20:
        return {"direction": NEUTRAL, "structure": "—", "status": _kl("INSUFFICIENT", H1_STATUS), "labels": []}
    ms = market_structure(h1, s.h1_swing_strength)
    labels = _swing_labels(h1, s.h1_swing_strength)
    if not event:
        return {"direction": _dir_of(ms), "structure": ms["label"], "status": _kl("NO_EVENT", H1_STATUS), "labels": labels}
    d, inv = event["direction"], event["invalidation"]
    start = _post(h1, datetime.fromisoformat(event["at"]))
    post = h1[start:]
    if any((b.c > inv) if d == BEAR else (b.c < inv) for b in post):
        return {"direction": _dir_of(ms), "structure": "Close beyond invalidation", "status": _kl("CONTRADICTED", H1_STATUS), "labels": labels}
    k = s.h1_swing_strength
    highs, lows = pivots(h1, k)
    first, second = ("LH", "LL") if d == BEAR else ("HL", "HH")
    pivs = [p for p in (highs if d == BEAR else lows) if p[0] >= start and p[0] + k < len(h1)]
    if not pivs:
        return {"direction": _dir_of(ms), "structure": "No post-break swing", "status": _kl("PENDING", H1_STATUS), "labels": labels}
    pi, pp = pivs[0]
    ext = min(b.l for b in h1[start : pi + 1]) if d == BEAR else max(b.h for b in h1[start : pi + 1])
    done = next((m for m in range(pi + 1, len(h1)) if (h1[m].c < ext if d == BEAR else h1[m].c > ext)), None)
    seq = [{"t": h1[pi].t.isoformat(), "price": pp, "label": first}]
    if done is None:
        return {"direction": d, "structure": f"{first} formed", "status": _kl("FORMING", H1_STATUS), "labels": labels, "sequence": seq}
    seq.append({"t": h1[done].t.isoformat(), "price": h1[done].c, "label": second})
    return {"direction": d, "structure": f"{first} → {second}", "status": _kl("CONFIRMED", H1_STATUS), "labels": labels, "sequence": seq}


def _swing_labels(bars: list[Bar], k: int, keep: int = 8) -> list[dict]:
    """HH/LH and HL/LL labels for the most recent confirmed swings."""
    highs, lows = pivots(bars, k)
    out = []
    for pivs, up, down, kind in ((highs, "HH", "LH", "HIGH"), (lows, "HL", "LL", "LOW")):
        for (_, prev), (i, p) in zip(pivs, pivs[1:]):
            out.append({"t": bars[i].t.isoformat(), "price": p, "label": up if p > prev else down, "kind": kind})
    out.sort(key=lambda x: x["t"])
    return out[-keep:]


def m30_confirmation(m30: list[Bar], event: dict | None, s: H8BosBtlSettings) -> dict:
    if len(m30) < 20:
        return {"direction": NEUTRAL, "structure": "—", "status": _kl("INSUFFICIENT", M30_STATUS), "markers": []}
    ms = market_structure(m30, s.m30_swing_strength)
    if not event:
        return {"direction": _dir_of(ms), "structure": ms["label"], "status": _kl("NO_EVENT", M30_STATUS), "markers": []}
    d, inv = event["direction"], event["invalidation"]
    lo, hi = event["retest"]
    start = _post(m30, datetime.fromisoformat(event["at"]))
    post = m30[start:]
    bear = d == BEAR
    if any((b.c > inv) if bear else (b.c < inv) for b in post):
        return {"direction": _dir_of(ms), "structure": "Close beyond invalidation", "status": _kl("INVALID", M30_STATUS), "markers": []}
    entry = next((i for i, b in enumerate(post) if (b.h >= lo if bear else b.l <= hi)), None)
    if entry is None:
        return {"direction": d, "structure": "Away from retest zone", "status": _kl("AWAITING", M30_STATUS), "markers": []}
    markers = [{"t": post[entry].t.isoformat(), "price": post[entry].h if bear else post[entry].l, "label": "Retest"}]
    pre_ext = (min(b.l for b in post[: entry + 1]) if bear else max(b.h for b in post[: entry + 1]))
    state = "IN_RETEST"
    reclaim_at = None
    for m in range(entry + 1, len(post)):
        b = post[m]
        beyond = b.c > hi if bear else b.c < lo
        back = b.c < lo if bear else b.c > hi
        if beyond:
            reclaim_at = m
            state = "RECLAIMING"
        elif back:
            if reclaim_at is not None:
                state = "FAILED_RECLAIM"
                markers.append({"t": b.t.isoformat(), "price": b.c, "label": "Failed reclaim"})
                reclaim_at = None
            elif state == "IN_RETEST":
                state = "REACTION"
                markers.append({"t": b.t.isoformat(), "price": b.c, "label": "Reaction"})
        if state in ("REACTION", "FAILED_RECLAIM") and (b.c < pre_ext if bear else b.c > pre_ext):
            state = "LTF_CONFIRMED"
            markers.append({"t": b.t.isoformat(), "price": b.c, "label": "LTF BOS"})
            break
    structure = {
        "IN_RETEST": "Inside retest zone",
        "RECLAIMING": "Closed back through zone",
        "REACTION": "Rejected from zone",
        "FAILED_RECLAIM": "Reclaim failed",
        "LTF_CONFIRMED": "LTF break in event direction",
    }[state]
    return {"direction": d, "structure": structure, "status": _kl(state, M30_STATUS), "markers": markers}
