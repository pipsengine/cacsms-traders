"""Weekly Range Structure intelligence (pure functions over closed candles).

Weekly range detection from a close envelope bounded in ATR, boundary zones from weekly fractal clusters,
developing (unconfirmed) weekly fractals with weighted lower-timeframe evidence, multi-timeframe alignment,
reversal-vs-breakout hypotheses and the autonomous workflow stage. Analysis only — never trade direction.
"""
from __future__ import annotations

from .range_structure_config import FRACTAL_EVIDENCE_WEIGHTS, RANGE_POSITION_BANDS, RangeSettings
from .scanner_analytics import Bar, market_structure, pivots, regression_channel, true_ranges, volatility, wilder_atr

REGIME_LABELS = {
    "RANGING": "Ranging",
    "BULLISH": "Bullish",
    "BEARISH": "Bearish",
    "TRANSITIONAL": "Transitional",
    "INSUFFICIENT": "Insufficient data",
}
STATE_LABELS = {
    "FORMING": "Forming",
    "VALIDATED": "Validated",
    "MATURE": "Mature",
    "BREAKOUT_THREAT": "Breakout Threat",
}
DIRECTION_LABELS = {"ASCENDING": "Ascending", "DESCENDING": "Descending", "FLAT": "Sideways"}


def _kl(key: str | None, labels: dict[str, str]) -> dict | None:
    return None if key is None else {"key": key, "label": labels.get(key, key)}


def _cluster(points: list[tuple[int, float]], tol: float, prefer_high: bool) -> list[tuple[int, float]]:
    """Densest group of fractal prices within ±tol (ties → the more extreme level)."""
    best_key, best = None, []
    for _, p in points:
        members = [(i, q) for i, q in points if abs(q - p) <= tol]
        key = (len(members), p if prefer_high else -p)
        if best_key is None or key > best_key:
            best_key, best = key, members
    return best


def developing_fractals(bars: list[Bar], n: int) -> list[dict]:
    """Weekly fractal candidates that still lack ``n`` confirming closed bars on the right."""
    out: list[dict] = []
    size = len(bars)
    for c in range(max(n, size - n), size):
        b, left, right = bars[c], bars[c - n : c], bars[c + 1 :]
        pending = n - len(right)
        if all(x.l > b.l for x in left) and all(x.l > b.l for x in right):
            out.append({"kind": "WFL", "price": b.l, "at": b.t.isoformat(), "bars_to_confirm": pending})
        if all(x.h < b.h for x in left) and all(x.h < b.h for x in right):
            out.append({"kind": "WFH", "price": b.h, "at": b.t.isoformat(), "bars_to_confirm": pending})
    return out


def weekly_range(w: list[Bar], s: RangeSettings) -> dict:
    """Price-independent weekly range core from closed weekly bars."""
    n = s.fractal_strength
    if len(w) < s.atr_period + s.min_weeks + 2 * n:
        return {"regime": _kl("INSUFFICIENT", REGIME_LABELS), "weeks_available": len(w)}
    atr = wilder_atr(true_ranges(w), s.atr_period)[-1]
    size = len(w)
    tol = s.zone_tolerance_atr * atr
    highs, lows = pivots(w, n)

    def candidate(start: int) -> dict:
        win = w[start:]
        fh = [(i, p) for i, p in highs if i >= start]
        fl = [(i, p) for i, p in lows if i >= start]
        mid_env = (max(b.h for b in win) + min(b.l for b in win)) / 2
        hc = _cluster([x for x in fh if x[1] >= mid_env], tol, True)
        lc = _cluster([x for x in fl if x[1] <= mid_env], tol, False)
        hi = max(p for _, p in hc) if hc else max(b.h for b in win)
        lo = min(p for _, p in lc) if lc else min(b.l for b in win)
        flags = [b.c > hi or b.c < lo for b in win]
        trailing = 0
        for f in reversed(flags):
            if not f:
                break
            trailing += 1
        # Closes outside that later returned inside are false breakouts; a trailing run of 2+ is a broken range.
        outside = sum(flags[: len(flags) - trailing])
        valid = (
            len(hc) >= s.min_touches
            and len(lc) >= s.min_touches
            and hi - lo <= s.max_width_atr * atr
            and trailing <= 1
            and outside <= max(1, round(s.max_outside_ratio * len(win)))
        )
        return {
            "start": start, "fh": fh, "fl": fl, "hc": hc, "lc": lc, "hi": hi, "lo": lo,
            "outside": outside, "trailing": trailing, "valid": valid,
        }

    # Longest recent window whose fractal-cluster boundaries contain (almost) every weekly close.
    best = None
    for start in range(max(0, size - s.lookback_weeks), size - s.min_weeks + 1):
        c = candidate(start)
        if c["valid"]:
            best = c
            break
    ranging = best is not None
    if best is None:
        best = candidate(max(0, size - s.recent_swing_weeks))
    start, hc, lc, fh, fl = best["start"], best["hc"], best["lc"], best["fh"], best["fl"]
    win = w[start:]
    age = len(win)
    high_zone = (min(p for _, p in hc), max(p for _, p in hc)) if hc else None
    low_zone = (min(p for _, p in lc), max(p for _, p in lc)) if lc else None
    range_high, range_low = best["hi"], best["lo"]
    th, tl = len(hc), len(lc)
    false_breakouts = best["outside"]
    last_outside = win[-1].c > range_high or win[-1].c < range_low
    if ranging:
        regime = "RANGING"
        if last_outside:
            state = "BREAKOUT_THREAT"
        elif age >= s.mature_weeks and th + tl >= 2 * s.min_touches + 2:
            state = "MATURE"
        else:
            state = "VALIDATED"
    else:
        st = market_structure(w[-80:], n)["key"]
        regime = st if st in ("BULLISH", "BEARISH") else "TRANSITIONAL"
        state = "FORMING" if th >= 1 and tl >= 1 and age >= max(3, s.min_weeks // 2) else None
    width = range_high - range_low
    balance = min(th, tl) / max(th, tl) if max(th, tl) else 0.0
    quality = round(
        35 * min(1.0, (th + tl) / 8)
        + 25 * min(1.0, age / 40)
        + 20 * balance
        + 20 * max(0.0, 1 - false_breakouts / 4)
    )
    major_highs, major_lows = pivots(w, s.major_fractal_strength)
    major_h, major_l = {i for i, _ in major_highs}, {i for i, _ in major_lows}
    last = w[-1]
    bar_range = last.h - last.l
    channel = regression_channel(w, min(26, len(w)), 2.0)
    vol = volatility(w, s.atr_period, min(52, len(w) - 1), 0.8, 1.25)
    return {
        "regime": _kl(regime, REGIME_LABELS),
        "state": _kl(state, STATE_LABELS),
        "ranging": ranging,
        "basis": "VALIDATED_RANGE" if ranging else "RECENT_SWINGS",
        "start": win[0].t.isoformat(),
        "age_weeks": age,
        "atr": atr,
        "tolerance": tol,
        "range_high": range_high,
        "range_low": range_low,
        "midpoint": (range_high + range_low) / 2,
        "width": width,
        "width_atr": width / atr if atr else None,
        "high_zone": list(high_zone) if high_zone else None,
        "low_zone": list(low_zone) if low_zone else None,
        "touches_high": th,
        "touches_low": tl,
        "last_touch_high": w[max(i for i, _ in hc)].t.isoformat() if hc else None,
        "last_touch_low": w[max(i for i, _ in lc)].t.isoformat() if lc else None,
        "false_breakouts": false_breakouts,
        "last_close_outside": last_outside,
        "quality": quality if ranging else None,
        "reliability": None if not ranging else "HIGH" if quality >= 75 else "MEDIUM" if quality >= 55 else "LOW",
        "fractals": [
            {"kind": "WFH", "at": w[i].t.isoformat(), "price": p, "in_cluster": (i, p) in hc, "major": i in major_h}
            for i, p in highs
        ]
        + [
            {"kind": "WFL", "at": w[i].t.isoformat(), "price": p, "in_cluster": (i, p) in lc, "major": i in major_l}
            for i, p in lows
        ],
        "developing": developing_fractals(w, n),
        "last_week": {
            "at": last.t.isoformat(),
            "close_location": (last.c - last.l) / bar_range if bar_range else 0.5,
        },
        "channel_direction": channel.get("direction"),
        "volatility_trend": vol.get("trend"),
    }


def ltf_context(d1: list[Bar], h8: list[Bar], h1: list[Bar], s: RangeSettings) -> dict:
    n = s.fractal_strength
    out: dict = {}
    for tf, bars in (("D1", d1), ("H8", h8), ("H1", h1)):
        ch = regression_channel(bars, s.channel_period, 2.0)
        out[tf] = {
            "structure": market_structure(bars, n),
            "channel": ch,
            "last_close": bars[-1].c if bars else None,
        }
    reaction = None
    if len(d1) >= 4:
        last = d1[-1]
        if last.c > last.o and last.c > d1[-4].c:
            reaction = "UP"
        elif last.c < last.o and last.c < d1[-4].c:
            reaction = "DOWN"
    out["d1_reaction"] = reaction
    return out


def position_band(pos: float) -> dict:
    if pos > 100:
        return {"key": "ABOVE_RANGE", "label": "Above Range"}
    if pos < 0:
        return {"key": "BELOW_RANGE", "label": "Below Range"}
    for lower, key, label in RANGE_POSITION_BANDS:
        if pos >= lower:
            return {"key": key, "label": label}
    return {"key": "LOWER_EXTREME", "label": "Lower Extreme"}


def _dir(structure_key: str | None) -> str | None:
    return {"BULLISH": "UP", "BEARISH": "DOWN"}.get(structure_key or "")


def _band(score: float, s: RangeSettings) -> dict:
    if score >= s.strong:
        return {"key": "STRONG", "label": "Strong"}
    if score >= s.moderate:
        return {"key": "MODERATE", "label": "Moderate"}
    return {"key": "WEAK", "label": "Weak"}


def _signal(tf_ctx: dict, rev_dir: str | None) -> dict:
    st = tf_ctx["structure"]
    ev = (st.get("event") or {}).get("key")
    if ev == "BREAK_UP":
        return {"key": "BREAK_UP", "label": "Bullish break", "tone": "up"}
    if ev == "BREAK_DOWN":
        return {"key": "BREAK_DOWN", "label": "Bearish break", "tone": "down"}
    if ev == "PULLBACK":
        return {"key": "PULLBACK", "label": "Pullback", "tone": "amber"}
    if rev_dir and _dir(st["key"]) == rev_dir:
        return {"key": "REACTION", "label": "Reaction", "tone": "up" if rev_dir == "UP" else "down"}
    return {"key": "WATCHING", "label": "Watching", "tone": "muted"}


def range_view(core: dict, ltf: dict, price: float, s: RangeSettings) -> dict:
    """Live (price-dependent) range intelligence: position, fractal evidence, MTF, hypotheses, workflow."""
    if core["regime"]["key"] == "INSUFFICIENT":
        return {"available": False}
    hi, lo = core["range_high"], core["range_low"]
    pos = (price - lo) / (hi - lo) * 100 if hi > lo else 50.0
    band = position_band(pos)
    lower_half = pos < 50
    rev_dir = "UP" if lower_half else "DOWN"
    brk_dir = "DOWN" if lower_half else "UP"
    want = "WFL" if lower_half else "WFH"
    dev = next(
        (
            f
            for f in core["developing"]
            if f["kind"] == want and (price >= f["price"] if want == "WFL" else price <= f["price"])
        ),
        None,
    )
    zone = core["low_zone"] if lower_half else core["high_zone"]
    tol = core["tolerance"]
    d1s, h8s, h1s = (ltf[tf]["structure"] for tf in ("D1", "H8", "H1"))
    close_loc = core["last_week"]["close_location"]
    side = "low" if lower_half else "high"
    bull = rev_dir == "UP"
    h1_bos = (h1s.get("event") or {}).get("key") == ("BREAK_UP" if bull else "BREAK_DOWN")
    near = pos <= s.extreme_pct if lower_half else pos >= 100 - s.extreme_pct
    evidence_items = [
        ("near_boundary", f"Near weekly range {side}", near),
        (
            "cluster",
            f"Historical {want} cluster",
            bool(dev and zone and zone[0] - tol <= dev["price"] <= zone[1] + tol),
        ),
        ("weekly_rejection", "Weekly rejection developing", close_loc >= 0.5 if bull else close_loc <= 0.5),
        ("d1_reaction", f"D1 {'bullish' if bull else 'bearish'} reaction", ltf["d1_reaction"] == rev_dir),
        ("h8_structure", f"H8 {'bullish' if bull else 'bearish'} structure", _dir(h8s["key"]) == rev_dir),
        ("h1_bos", "H1 BOS confirmed" if h1_bos else "H1 BOS pending", h1_bos),
        ("weekly_confirmation", "Weekly confirmation pending", False),
    ]
    evidence = [
        {"key": k, "label": label, "met": met, "weight": FRACTAL_EVIDENCE_WEIGHTS[k]} for k, label, met in evidence_items
    ]
    score = sum(e["weight"] for e in evidence if e["met"])
    quality = core["quality"] or 0
    ext = pos <= s.extreme_pct or pos >= 100 - s.extreme_pct
    beyond = pos < 0 or pos > 100 or core["last_close_outside"]
    at_edge = pos <= s.breakout_pct or pos >= 100 - s.breakout_pct
    rev_score = round(
        25 * ext + 0.35 * score + 0.20 * quality + 10 * (_dir(d1s["key"]) == rev_dir) + 10 * (_dir(h8s["key"]) == rev_dir)
    )
    brk_score = round(
        30 * beyond
        + 15 * at_edge
        + 15 * (core["volatility_trend"] == "EXPANDING")
        + 10 * (_dir(d1s["key"]) == brk_dir)
        + 10 * (_dir(h8s["key"]) == brk_dir)
        + 20 * (1 - quality / 100)
    )
    ranging = core["ranging"]
    arrow = {"UP": "↑", "DOWN": "↓"}
    if not ranging:
        summary = {"key": "NOT_APPLICABLE", "label": "—", "direction": None}
    elif rev_score >= s.hypothesis_min and rev_score > brk_score:
        summary = {"key": "REVERSAL", "label": f"Reversal {arrow[rev_dir]}", "direction": rev_dir}
    elif brk_score >= s.hypothesis_min and brk_score > rev_score:
        summary = {"key": "BREAKOUT", "label": f"Breakout {arrow[brk_dir]}", "direction": brk_dir}
    else:
        summary = {"key": "NEUTRAL", "label": "Neutral", "direction": None}

    ltf_reaction = ltf["d1_reaction"] == rev_dir or _dir(h8s["key"]) == rev_dir
    conditions = [
        ("Range Detected", ranging),
        ("Boundary Approach", ext),
        ("Fractal Developing", dev is not None and score >= 50),
        ("LTF Reaction", ltf_reaction),
        ("Structure Confirmation", h1_bos),
        ("Opportunity", False),
        ("Execution", False),
    ]
    workflow, chain = [], True
    for label, cond in conditions:
        chain = chain and cond
        workflow.append({"label": label, "done": chain})
    stage = sum(1 for x in workflow if x["done"])
    word = "BULLISH" if bull else "BEARISH"
    if not ranging:
        decision = {"key": "NO_RANGE", "title": "NO ACTIVE RANGE", "subtitle": f"W REGIME {core['regime']['label'].upper()}"}
        narrative = (
            f"No validated weekly range: the weekly regime is {core['regime']['label'].lower()} "
            f"({core['touches_high']} upper / {core['touches_low']} lower fractal touches in {core['age_weeks']} weeks)."
        )
    elif core["state"] and core["state"]["key"] == "BREAKOUT_THREAT" or beyond:
        decision = {"key": "ALERT", "title": "ALERT", "subtitle": "RANGE BREAKOUT THREAT"}
        narrative = (
            f"Price is outside the {core['state']['label'].lower() if core['state'] else ''} weekly range "
            f"({pos:.0f}% position). Monitoring whether the boundary is reclaimed or the breakout is accepted."
        )
    elif stage >= 5:
        decision = {"key": "CONFIRMING", "title": "STRUCTURE CONFIRMED", "subtitle": f"{word} RANGE REACTION"}
        narrative = (
            f"Weekly {want} evidence with H1 break of structure at the range {side}. "
            "Awaiting the Opportunity engine; this screen never initiates execution."
        )
    elif stage >= 4:
        decision = {"key": "MONITORING", "title": "MONITORING", "subtitle": f"{word} RANGE REACTION"}
        narrative = (
            f"Price is at the {band['label'].lower()} of a {core['state']['label'].lower()} weekly range with a "
            f"developing {want} and {word.lower()} lower-TF reaction. Monitoring for H1 confirmation."
        )
    elif stage >= 2:
        decision = {"key": "WATCHING", "title": "WATCHING", "subtitle": "BOUNDARY APPROACH"}
        narrative = (
            f"Price is approaching the weekly range {side} ({pos:.0f}% position). "
            f"Waiting for a developing {want} and lower-TF reaction."
        )
    else:
        decision = {"key": "IDLE", "title": "IDLE", "subtitle": "PRICE INSIDE RANGE"}
        narrative = f"Price is in the {band['label'].lower()} of the weekly range ({pos:.0f}%); no boundary interaction."
    decision["direction"] = rev_dir if decision["key"] in ("MONITORING", "CONFIRMING", "WATCHING") else None

    w_struct = core["regime"]
    mtf = [
        {
            "timeframe": "W",
            "structure": w_struct,
            "channel": DIRECTION_LABELS.get(core["channel_direction"] or "", "—"),
            "signal": {"key": band["key"], "label": band["label"], "tone": "up" if lower_half else "down"}
            if ranging
            else {"key": "TREND", "label": w_struct["label"], "tone": "muted"},
        }
    ]
    for tf in ("D1", "H8", "H1"):
        st = ltf[tf]["structure"]
        ch = ltf[tf]["channel"]
        mtf.append(
            {
                "timeframe": tf,
                "structure": {"key": st["key"], "label": "Neutral" if st["key"] in ("RANGE", "INSUFFICIENT") else st["label"]},
                "channel": DIRECTION_LABELS.get(ch.get("direction") or "", "—") if ch.get("key") != "INSUFFICIENT" else "—",
                "signal": _signal(ltf[tf], rev_dir if ranging else None),
            }
        )
    return {
        "available": True,
        "position": round(pos, 1),
        "position_band": band,
        "developing_fractal": None
        if dev is None
        else {**dev, "label": f"{dev['kind']} (Developing)", "location": f"{band['label']} ({pos:.0f}%)"},
        "fractal_kind": want,
        "evidence": evidence,
        "evidence_score": score,
        "mtf": mtf,
        "hypotheses": None
        if not ranging
        else {
            "reversal": {"direction": rev_dir, "score": rev_score, "band": _band(rev_score, s)},
            "breakout": {"direction": brk_dir, "score": brk_score, "band": _band(brk_score, s)},
        },
        "summary_hypothesis": summary,
        "workflow": workflow,
        "stage": stage,
        "decision": {**decision, "narrative": narrative},
    }
