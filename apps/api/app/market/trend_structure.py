"""Trend Structure analytics on closed candles (Market Structure → Trend Structure).

Pure functions over ``Bar`` tuples, testable without MT5. Per-timeframe regimes and BOS/CHoCH events come from the
Structure Overview core so both tabs agree; this module adds swing sequences, trend strength, pullback geometry,
trend age and a structural setup classification. ``price=None`` evaluates the last closed bar only (used for
persistence); a live price yields the live view. Outputs describe structure only — never BUY/SELL.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from .scanner_analytics import Bar, market_structure, pivots, regression_channel, true_ranges, wilder_atr
from .structure_overview import TF_DELTA, alignment, cells_for, live_events
from .structure_overview_config import OverviewSettings
from .trend_structure_config import BAR_KEYS, SETUP_STATUS, SETUPS, TREND_STATES, TREND_TIMEFRAMES, TrendSettings

_SIGN = {"BULLISH": 1, "BEARISH": -1}
_WITH_TREND = {1: ("HH", "HL"), -1: ("LH", "LL")}
_CHANNEL_WITH = {1: "ASCENDING", -1: "DESCENDING"}
_SWING_NAMES = {"HH": "Higher High", "HL": "Higher Low", "LH": "Lower High", "LL": "Lower Low"}


def _kl(key: str, table: dict[str, str]) -> dict:
    return {"key": key, "label": table[key]}


def swing_sequence(bars: list[Bar], n: int, tf: str) -> list[dict]:
    """Confirmed fractal swings in time order, each labelled against the previous swing of the same side."""
    highs, lows = pivots(bars, n)
    merged = sorted([(i, p, "HIGH") for i, p in highs] + [(i, p, "LOW") for i, p in lows])
    prev: dict[str, float] = {}
    out: list[dict] = []
    for i, p, side in merged:
        label = None
        if side in prev:
            label = ("HH" if p > prev[side] else "LH") if side == "HIGH" else ("HL" if p > prev[side] else "LL")
        prev[side] = p
        out.append({"side": side, "label": label, "price": p, "index": i, "at": bars[i].t.isoformat(),
                    "confirmed_at": (bars[min(i + n, len(bars) - 1)].t + TF_DELTA[tf]).isoformat()})
    return out


def efficiency_ratio(bars: list[Bar], k: int) -> float | None:
    """Kaufman efficiency of the last ``k`` closes, signed by net direction (−1…1)."""
    if len(bars) <= k:
        return None
    closes = [b.c for b in bars[-(k + 1):]]
    path = sum(abs(b - a) for a, b in zip(closes, closes[1:]))
    return (closes[-1] - closes[0]) / path if path else 0.0


def tf_core(bars: list[Bar], tf: str, s: TrendSettings) -> dict:
    """Price-independent structure for one timeframe."""
    if len(bars) < 2 * s.fractal_strength + 5:
        return {"available": False}
    channel = regression_channel(bars, s.channel_period, s.channel_width_sd) if len(bars) >= s.channel_period else {"key": "INSUFFICIENT"}
    atr = wilder_atr(true_ranges(bars), s.atr_period)
    return {
        "available": True,
        "structure": market_structure(bars, s.fractal_strength)["key"],
        "swings": swing_sequence(bars, s.fractal_strength, tf)[-12:],
        "channel": {k: channel.get(k) for k in ("key", "upper", "mid", "lower", "slope_pct_per_bar", "direction", "period")},
        "atr": atr[-1] if atr else None,
        "efficiency": efficiency_ratio(bars, s.efficiency_bars),
        "last_close": bars[-1].c,
        "closed_at": (bars[-1].t + TF_DELTA[tf]).isoformat(),
    }


def trend_core(bars: dict[str, list[Bar]], s: TrendSettings) -> dict:
    return {tf: tf_core(bars[BAR_KEYS[tf]], tf, s) for tf in TREND_TIMEFRAMES}


# ----- live view -----


def _leg(swings: list[dict], sign: int) -> tuple[dict, dict] | None:
    """Last impulse leg in the trend direction: (start swing, extreme swing)."""
    ext_side, start_side = ("HIGH", "LOW") if sign == 1 else ("LOW", "HIGH")
    for k in range(len(swings) - 1, -1, -1):
        if swings[k]["side"] == ext_side:
            start = next((x for x in reversed(swings[:k]) if x["side"] == start_side), None)
            return (start, swings[k]) if start else None
    return None


def _trend_start(events: list[dict], sign: int) -> str | None:
    """Start of the latest run of same-direction structural breaks (ignoring a trailing counter-trend pullback)."""
    want = "UP" if sign == 1 else "DOWN"
    k = len(events) - 1
    while k >= 0 and events[k]["direction"] != want:
        k -= 1
    if k < 0:
        return None
    start = events[k]["at"]
    while k >= 0 and events[k]["direction"] == want:
        start = events[k]["at"]
        k -= 1
    return start


def _channel_at(ch: dict, price: float) -> float | None:
    up, lo = ch.get("upper"), ch.get("lower")
    if ch.get("key") == "INSUFFICIENT" or up is None or lo is None or up == lo:
        return None
    return (price - lo) / (up - lo)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def trend_view(core: dict, overview: dict, price: float | None, now: datetime, s: TrendSettings, ovs: OverviewSettings) -> dict:
    a = core.get(s.analysis_tf) or {}
    if not a.get("available"):
        return {"available": False, "reason": f"Insufficient closed {s.analysis_tf} history"}
    regimes = overview["regimes"]
    cells = cells_for(regimes)
    align = alignment(regimes, ovs)
    direction = align["key"] if align["key"] in _SIGN else None
    sign = _SIGN.get(direction or "", 0) or (1 if align["score"] > 50 else -1 if align["score"] < 50 else 0)
    live = price is not None
    px = price if live else a["last_close"]

    # Strength components (0–100 each)
    align_c = abs(align["score"] - 50) * 2
    run = 0
    for sw in reversed([x for x in a["swings"] if x["label"]]):
        if sign and sw["label"] in _WITH_TREND[sign]:
            run += 1
        else:
            break
    structure_c = min(run, 4) * 25
    ch_dir = a["channel"].get("direction")
    channel_c = 0 if not sign or ch_dir is None else 100 if ch_dir == _CHANNEL_WITH[sign] else 50 if ch_dir == "FLAT" else 0
    er = a["efficiency"]
    momentum_c = 0 if er is None or not sign else _clamp(er * sign / s.efficiency_full * 100)
    w = s.weights
    strength = round(w[0] * align_c + w[1] * structure_c + w[2] * channel_c + w[3] * momentum_c)
    agree = [tf for tf in TREND_TIMEFRAMES if sign and (core.get(tf) or {}).get("channel", {}).get("direction") == _CHANNEL_WITH[sign]]
    momentum_alignment = round(100 * len(agree) / len(TREND_TIMEFRAMES))

    # Pullback geometry on the analysis timeframe
    leg = _leg(a["swings"], sign) if direction else None
    geo = None
    if leg:
        start, ext = leg
        size = abs(ext["price"] - start["price"])
        if size > 0:
            depth = (ext["price"] - px) / size if sign == 1 else (px - ext["price"]) / size
            last = a["swings"][-1]
            retracing = last["index"] == ext["index"]
            if depth <= 0:
                pb_key, pb_label = "EXTENDING", "Extending beyond swing extreme"
            elif depth >= s.reversal_depth:
                pb_key, pb_label = "BEYOND_REVERSAL", "Retraced beyond reversal depth"
            elif depth > s.zone_deep:
                pb_key, pb_label = "DEEP", "Deep pullback"
            elif retracing:
                pb_key, pb_label = "IN_PULLBACK", "In pullback"
            else:
                pb_key, pb_label = "RESUMING", "Resuming after confirmed swing"
            z = sorted((ext["price"] - sign * s.zone_shallow * size, ext["price"] - sign * s.zone_deep * size))
            invalidation = start["price"]
            obj1 = ext["price"]
            obj2 = start["price"] + sign * s.objective_extension * size
            risk = abs(px - invalidation)
            reward = abs(obj1 - px)
            if (px - invalidation) * sign <= 0:
                status = "INVALIDATED"
            elif (px - obj1) * sign > 0:
                status = "EXTENDED"
            elif z[0] <= px <= z[1]:
                status = "IN_ZONE"
            else:
                status = "MONITORING"
            geo = {
                "leg_start": start["price"], "leg_extreme": ext["price"], "leg_size": size,
                "depth_pct": round(depth * 100, 1), "pullback": {"key": pb_key, "label": pb_label},
                "zone": z, "invalidation": invalidation, "objective_1": obj1, "objective_2": obj2,
                "ratio": round(reward / risk, 2) if risk > 0 and status not in ("INVALIDATED", "EXTENDED") else None,
                "status": _kl(status, SETUP_STATUS),
            }

    # Trend age from the analysis timeframe's run of same-direction breaks
    tf_events = overview["events"].get(s.analysis_tf, {}).get("events", [])
    started = _trend_start(tf_events, sign) if direction else None
    anchor = datetime.fromisoformat(a["closed_at"])
    age_weeks = round((anchor - datetime.fromisoformat(started)).total_seconds() / 604800, 1) if started else None

    # Reversal risk: deep retracement, broken leg or a fresh confirmed CHoCH against the trend
    against = "DOWN" if sign == 1 else "UP"
    since = anchor - timedelta(hours=s.reversal_event_hours)
    choch = [
        {**e, "tf": tf}
        for tf in ("D1", "H8")
        for e in overview["events"].get(tf, {}).get("events", [])
        if e["kind"] == "CHOCH" and e["direction"] == against and not e["failed"] and datetime.fromisoformat(e["at"]) >= since
    ]
    reversal_reasons = []
    if direction and geo:
        if geo["status"]["key"] == "INVALIDATED":
            reversal_reasons.append(f"Price beyond the {s.analysis_tf} leg origin")
        elif geo["pullback"]["key"] == "BEYOND_REVERSAL":
            reversal_reasons.append(f"Retracement {geo['depth_pct']:.0f}% ≥ {s.reversal_depth * 100:.1f}%")
    if direction and choch:
        reversal_reasons.append(f"Counter-trend CHoCH on {', '.join(sorted({c['tf'] for c in choch}))}")

    pullback_cells = [tf for tf in ("D1", "H8", "H1") if (cells.get(tf) or {}).get("key") == "PULLBACK"]
    in_pullback = bool(direction) and (bool(pullback_cells) or (geo is not None and geo["pullback"]["key"] in ("IN_PULLBACK", "DEEP", "RESUMING")))
    w_cell = (cells.get("W") or {}).get("key")
    early = bool(direction) and ((age_weeks is not None and age_weeks < s.early_age_weeks) or w_cell != ("BULL" if sign == 1 else "BEAR"))

    up = sign == 1
    if not direction:
        state = "RANGING" if regimes.get("W") == "RANGING" else "NO_TREND"
    elif in_pullback:
        state = "UPTREND_PULLBACK" if up else "DOWNTREND_PULLBACK"
    elif early:
        state = "UPTREND_EARLY" if up else "DOWNTREND_EARLY"
    elif strength >= s.strong_min:
        state = "STRONG_UPTREND" if up else "STRONG_DOWNTREND"
    else:
        state = "UPTREND" if up else "DOWNTREND"

    if not direction:
        setup = "NO_TREND"
    elif reversal_reasons:
        setup = "REVERSAL_RISK"
    elif in_pullback and geo and geo["status"]["key"] != "INVALIDATED":
        setup = "CONTINUATION"
    elif early:
        setup = "DEVELOPING"
    else:
        setup = "EXTENSION"

    depth = geo["depth_pct"] / 100 if geo else None
    if depth is None:
        pullback_health = 0.0
    elif depth <= s.zone_deep:
        pullback_health = 100.0
    else:
        pullback_health = _clamp(100 * (s.reversal_depth - depth) / (s.reversal_depth - s.zone_deep))
    confidence = round((structure_c + momentum_alignment + pullback_health + align_c) / 4) if direction else 0
    pos = _channel_at(a["channel"], px)

    labels = [x["label"] for x in a["swings"] if x["label"]][-4:]
    title, subtitle = SETUPS[setup]
    return {
        "available": True,
        "closed_bar_only": not live,
        "price": px,
        "direction": direction,
        "cells": cells,
        "regimes": regimes,
        "alignment": align,
        "state": _kl(state, TREND_STATES),
        "strength": strength,
        "components": {"alignment": round(align_c), "structure": structure_c, "channel": channel_c, "momentum": round(momentum_c)},
        "age_weeks": age_weeks,
        "trend_started_at": started,
        "structure_sequence": labels,
        "pullback_cells": pullback_cells,
        "geometry": geo,
        "reversal_reasons": reversal_reasons,
        "setup": {"key": setup, "title": title, "subtitle": subtitle},
        "confidence": confidence,
        "health": {
            "structure_strength": structure_c,
            "channel_position": None if pos is None else round(_clamp(pos * 100)),
            "momentum_alignment": momentum_alignment if direction else 0,
            "pullback_depth": None if depth is None else round(_clamp(depth * 100)),
            "trend_continuation": confidence,
        },
        "key_levels": {
            "support": a["channel"].get("lower"),
            "resistance": a["channel"].get("upper"),
            "basis": f"{s.analysis_tf} regression channel",
        },
        "analysis_tf": s.analysis_tf,
        "anchor": a["closed_at"],
    }


def mtf_rows(core: dict, view: dict) -> list[dict]:
    out = []
    for tf in TREND_TIMEFRAMES:
        c = core.get(tf) or {}
        cell = view["cells"].get(tf)
        last = [x["label"] for x in c.get("swings", []) if x["label"]]
        hi = next((x for x in reversed(last) if x in ("HH", "LH")), None)
        lo = next((x for x in reversed(last) if x in ("HL", "LL")), None)
        out.append({
            "tf": tf,
            "cell": cell,
            "swings": " / ".join(x for x in (hi, lo) if x) or "—",
            "channel": (c.get("channel") or {}).get("direction"),
        })
    return out


def trend_events(core: dict, overview: dict, price: float | None, now: datetime, s: TrendSettings, ovs: OverviewSettings) -> list[dict]:
    """Confirmed swing labels and BOS/CHoCH (with live status) on D1/H8/H1, newest first."""
    out = []
    for tf in ("D1", "H8", "H1"):
        for sw in (core.get(tf) or {}).get("swings", [])[-4:]:
            if sw["label"]:
                out.append({"tf": tf, "at": sw["confirmed_at"], "event": _SWING_NAMES[sw["label"]], "kind": "SWING",
                            "direction": "UP" if sw["label"] in ("HH", "HL") else "DOWN", "level": sw["price"],
                            "status": {"key": "CONFIRMED", "label": "Confirmed"}})
    window = replace(ovs, event_lookback_hours=24 * 7 * 8)
    events = {tf: overview["events"][tf] for tf in ("D1", "H8", "H1") if tf in overview["events"]}
    for e in live_events({**overview, "events": events}, price, now, window):
        if price is None and e["status"]["key"] == "DEVELOPING":
            continue
        out.append({"tf": e["tf"], "at": e["at"], "event": e["label"], "kind": e["kind"], "direction": e["direction"],
                    "level": e["level"], "status": e["status"]})
    out.sort(key=lambda e: e["at"], reverse=True)
    return out[: s.event_limit]
