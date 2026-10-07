"""Channel Intelligence domain events: CHANNEL_BREAK, CHANNEL_TOUCH, BREAK_RETEST_CONTINUATION, TIT_DETECTED.

Derived only from the engine's own closed-candle outputs — confirmed / failed breakouts, completed retests, the channel
touch tolerance and the Trend-in-Trend state — so no trading rule is defined here. Each event names the closed bar that
satisfied the rule (deterministic deduplication). Edge-triggered conditions (touch, TiT) also carry a re-arm key, and
``observations`` report when those conditions have reset so a consumer can re-arm them.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from . import channel_intelligence as chan

MAX_AGE_BARS = 6
PROVIDER_LABELS = {"mt5": "MT5", "ctrader": "cTrader"}


@dataclass
class DomainEvent:
    event_type: str
    symbol: str
    timeframe: str | None
    direction: str | None
    provider: str | None
    event_time: str
    price: float | None
    level: float | None
    channel_id: str | None = None
    structure_id: str | None = None
    tit_level: str | None = None
    confidence: float | None = None
    identity: str | None = None
    age_bars: int = 0
    rearm_key: str | None = None
    inactive_before: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Observation:
    """Edge-triggered condition state: ``inactive_bars`` closed bars since the condition last held (0 = holding)."""
    rearm_key: str
    inactive_bars: int
    prefix: bool = False


def provider_label(provider: str | None) -> str:
    return PROVIDER_LABELS.get((provider or "").lower(), provider or "Unknown")


def channel_id(symbol: str, tf: str, fit_start: str) -> str:
    return "CH-" + hashlib.sha1(f"{symbol}|{tf}|{fit_start}".encode()).hexdigest()[:10].upper()


def _word(d: int) -> str:
    return "BULLISH" if d > 0 else "BEARISH"


def _trend_word(direction_key: str | None) -> str:
    return {"UPTREND": "BULLISH", "DOWNTREND": "BEARISH"}.get(direction_key or "", "NEUTRAL")


def _closes(core_tf: dict, tf: str) -> list[str]:
    """Close times of the recent closed bars (oldest → newest)."""
    return [(datetime.fromisoformat(c["t"]) + chan.DELTA[tf]).isoformat() for c in (core_tf.get("spark") or {}).get("candles", [])]


def _age(closes: list[str], closed_at: str | None) -> int | None:
    if not closed_at or closed_at not in closes:
        return None
    return len(closes) - 1 - closes.index(closed_at)


def _context(core: dict, tf: str, s) -> dict:
    v = chan.tf_view(core, tf, None, s)
    ptf = chan.PARENT.get(tf)
    pv = chan.tf_view(core, ptf, None, s) if ptf else {"available": False}
    out = {"tf": tf, "parent_tf": ptf}
    if v.get("available"):
        out.update(channel_direction=v["direction"]["key"], channel_state=v["state"]["label"], validity=v["validity"]["label"])
    if pv.get("available"):
        out.update(parent_direction=pv["direction"]["key"], parent_state=pv["state"]["label"], parent_position=pv["position"])
    parts = []
    if v.get("available"):
        parts.append(f"{tf} channel {v['direction']['label'].lower()} ({v['validity']['label'].split(' (')[0].lower()})")
    if pv.get("available"):
        parts.append(f"parent {ptf} {pv['direction']['label'].lower()}, {pv['state']['label'].lower()}")
    out["summary"] = "; ".join(parts) or f"{tf} channel"
    return out


def _channel_type(c: dict, slope: float, half: float, s) -> str:
    kind = chan._direction(slope, c.get("period") or 2, 2 * half, s)
    return {"ASCENDING": "Ascending regression channel", "DESCENDING": "Descending regression channel"}.get(kind, "Horizontal regression channel")


def _breakout_events(symbol: str, tf: str, c: dict, core: dict, provider: str | None, s) -> list[DomainEvent]:
    out: list[DomainEvent] = []
    closes = _closes(c, tf)
    ctx = None
    for b in c.get("breakouts", []):
        if not b["confirmed"] or b["failed"]:
            continue
        d = 1 if b["direction"] == "UP" else -1
        cid = channel_id(symbol, tf, b["fit_start_at"])
        conf_age = b["bars_after"] - (s.confirm_closes - 1)
        ctx = ctx or _context(core, tf, s)
        base = {"channel_type": _channel_type(c, b["slope"], b["half"], s), "upper_boundary": b["mid_break"] + b["half"],
                "lower_boundary": b["mid_break"] - b["half"], "break_level": b["level"], "break_price": b["close"],
                "break_candle_close": b["at"], "closes_beyond": b["closes_beyond"], "body_beyond_atr": b.get("body_beyond_atr"),
                "channel_period": c.get("period"), "atr": c.get("atr"), "context": ctx}
        if 0 <= conf_age <= MAX_AGE_BARS and conf_age < len(closes):
            out.append(DomainEvent(
                "CHANNEL_BREAK", symbol, tf, _word(d), provider, closes[-1 - conf_age], b["close"], b["level"], channel_id=cid,
                identity=b["at"], age_bars=conf_age,
                metadata={**base, "confirmation_close": closes[-1 - conf_age], "confirm_closes": s.confirm_closes}))
        age = _age(closes, b.get("completed_at"))
        if age is not None and age <= MAX_AGE_BARS:
            want = "UPTREND" if d == 1 else "DOWNTREND"
            aligned = ctx.get("parent_direction") == want
            out.append(DomainEvent(
                "BREAK_RETEST_CONTINUATION", symbol, tf, _word(d), provider, b["completed_at"], b.get("retest_level"), b["level"],
                channel_id=cid, identity=b["at"], age_bars=age,
                metadata={**base, "label": f"{_word(d)} TREND CONTINUATION", "break_time": b["at"], "retest_price": b.get("retest_level"),
                          "retest_time": b.get("retest_at"), "continuation_close": b["completed_at"],
                          "confirmation_state": f"Retest held — closed {'above the retest candle high' if d == 1 else 'below the retest candle low'}",
                          "trend_aligned": aligned,
                          "trend_context": f"{'Aligned with' if aligned else 'Not aligned with'} the parent {ctx.get('parent_tf') or ''} channel".strip()}))
    return out


def _touch_events(symbol: str, tf: str, c: dict, core: dict, provider: str | None, s) -> tuple[list[DomainEvent], list[Observation]]:
    candles = (c.get("spark") or {}).get("candles", [])
    if len(candles) < 2:
        return [], []
    closes = _closes(c, tf)
    atr = c.get("atr") or 0.0
    tol = s.touch_atr * atr
    beyond = s.break_atr * atr
    events, obs = [], []
    valid = (c.get("validity") or {}).get("key") == "VALID"
    for side, sign in (("UPPER", 1), ("LOWER", -1)):
        key = f"CHANNEL_TOUCH|{symbol}|{tf}|{side}"
        line = lambda j: (c["upper"] if sign == 1 else c["lower"]) - c["slope"] * j  # noqa: E731
        in_zone = [(x["h"] >= line(j) - tol) if sign == 1 else (x["l"] <= line(j) + tol)
                   for j, x in enumerate(reversed(candles))]
        inactive = next((j for j, z in enumerate(in_zone) if z), len(in_zone))
        obs.append(Observation(key, inactive))
        last = candles[-1]
        closed_inside = (last["c"] <= line(0) + beyond) if sign == 1 else (last["c"] >= line(0) - beyond)
        if not valid or not in_zone[0] or not closed_inside:
            continue
        before = next((j for j, z in enumerate(in_zone[1:]) if z), len(in_zone) - 1)
        touch = last["h"] if sign == 1 else last["l"]
        ctx = _context(core, tf, s)
        dist = (line(0) - touch) * sign
        events.append(DomainEvent(
            "CHANNEL_TOUCH", symbol, tf, _trend_word(ctx.get("channel_direction")), provider, closes[-1], touch, line(0),
            channel_id=channel_id(symbol, tf, c["fit_start"]), identity=side, rearm_key=key, inactive_before=before,
            metadata={"boundary": side, "label": f"{'Upper' if sign == 1 else 'Lower'} Channel Touch", "boundary_level": line(0),
                      "touch_price": touch, "close": last["c"], "distance": dist, "distance_atr": round(dist / atr, 2) if atr else None,
                      "tolerance": tol, "tolerance_atr": s.touch_atr, "trend_direction": ctx.get("channel_direction"),
                      "channel_status": f"{ctx.get('validity', '')} · {ctx.get('channel_state', '')}".strip(" ·"),
                      "touches_upper": c.get("touches_upper"), "touches_lower": c.get("touches_lower"), "channel_period": c.get("period"),
                      "upper_boundary": c["upper"], "lower_boundary": c["lower"], "bars_outside_before": before, "context": ctx}))
    return events, obs


def _tit_events(symbol: str, core: dict, provider: str | None, s) -> tuple[list[DomainEvent], list[Observation]]:
    t = chan.tit_view(symbol, core, None, s)
    active = t.get("available") and t.get("countertrend") and (t.get("state") or {}).get("key") == "ACTIVE"
    if not active:
        return [], [Observation(f"TIT|{symbol}|", 1, prefix=True)]
    ct, st, parent = t["countertrend"], t["setup"], t["parent"]
    d = 1 if parent["direction"] == "UPTREND" else -1
    ct_core = core.get(ct["tf"]) or {}
    key = f"TIT|{symbol}|{ct['layer']}|{_word(d)}"
    reason = " ".join(t.get("takeaways") or [])
    return [DomainEvent(
        "TIT_DETECTED", symbol, ct["tf"], _word(d), provider, ct_core.get("closed_at") or "", t.get("price"), ct["rejoin_level"],
        channel_id=channel_id(symbol, ct["tf"], ct_core.get("fit_start", "")), tit_level=ct["layer"],
        confidence=round(st["quality"] / 100, 2) if st.get("quality") is not None else None, identity=ct["layer"], rearm_key=key,
        metadata={"tit_level": ct["layer"], "htf_direction": parent["direction"], "parent_layer": parent["layer"], "parent_tf": parent["tf"],
                  "parent_state": (parent.get("state") or {}).get("label"), "counter_trend_tf": ct["tf"], "counter_trend_type": ct["type"],
                  "phase": ct["phase"], "maturity": ct["maturity"], "position": ct["position"], "rejoin_level": ct["rejoin_level"],
                  "rejoin_score": ct["rejoin_score"], "exec_tf": ct["exec_tf"], "exec_layer": ct["exec_layer"],
                  "zone": st["zone"], "objective_1": st["objective_1"], "objective_2": st["objective_2"], "invalidation": st["invalidation"],
                  "setup_type": st["type"], "quality": st["quality"], "summary": t.get("summary"), "reason": reason,
                  "layers": [{k: l.get(k) for k in ("id", "tf", "available", "trend", "state", "position", "alignment")} for l in t["layers"]]})], []


def channel_events(symbol: str, core: dict, provider: str | None, s=None) -> tuple[list[DomainEvent], list[Observation]]:
    """Every channel domain event currently satisfied on closed candles for one instrument."""
    s = s or chan.channel_settings()
    events: list[DomainEvent] = []
    obs: list[Observation] = []
    for tf in chan.EVENT_TIMEFRAMES:
        c = core.get(tf) or {}
        if not c.get("available"):
            continue
        events += _breakout_events(symbol, tf, c, core, provider, s)
        e, o = _touch_events(symbol, tf, c, core, provider, s)
        events += e
        obs += o
    e, o = _tit_events(symbol, core, provider, s)
    return events + e, obs + o
