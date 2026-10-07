"""BOS / CHoCH intelligence (Market Structure → BOS / CHoCH) on closed candles.

Enriches the Structure Overview break events (same detection, so every tab agrees) with break-candle quality,
volume, retest tracking and a lifecycle, then builds the per-symbol context and evidence. Developing breaks
(live price beyond the active swing) are never reported as confirmed. Analysis only — never trade direction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .scanner_analytics import Bar
from .scanner_config import _floats
from .structure_overview import TF_DELTA

BOS_TIMEFRAMES = ("W", "D1", "H8", "H1")
BAR_KEYS = {"W": "W1", "D1": "D1", "H8": "H8", "H1": "H1"}
EVENT_STATUS = {
    "CONFIRMED": "Confirmed",
    "RETESTING": "Retesting",
    "DEVELOPING": "Developing",
    "MONITORING": "Monitoring",
    "FAILED": "Failed",
}
RETEST = {"PENDING": "Pending", "RETESTING": "Retesting", "COMPLETED": "Completed", "NONE": "—"}


@dataclass(frozen=True)
class BosSettings:
    retest_atr: float
    body_atr: float
    volume_ratio: float
    volume_bars: int
    monitor_atr: float
    key_level_atr: float
    lookback_days: float


def bos_settings() -> BosSettings:
    # BOS_SETTINGS="retest_atr,body_atr,volume_ratio,volume_bars,monitor_atr,key_level_atr,lookback_days"
    ra, ba, vr, vb, ma, ka, ld = _floats("BOS_SETTINGS", (0.3, 0.1, 1.2, 20.0, 1.0, 0.5, 30.0))
    return BosSettings(
        retest_atr=ra, body_atr=ba, volume_ratio=max(1.0, vr), volume_bars=max(5, int(vb)),
        monitor_atr=max(ra, ma), key_level_atr=ka, lookback_days=max(1.0, ld),
    )


def bos_settings_payload() -> dict:
    s = bos_settings()
    return {k: getattr(s, k) for k in s.__dataclass_fields__}


def label(kind: str, direction: str) -> str:
    return f"{'Bullish' if direction == 'UP' else 'Bearish'} {'BOS' if kind == 'BOS' else 'CHoCH'}"


def enrich(bars: list[Bar], ev: dict, tf: str, s: BosSettings) -> list[dict]:
    """Closed-bar quality and retest facts for every break on one timeframe (price-independent)."""
    index = {b.t.isoformat(): k for k, b in enumerate(bars)}
    atr = ev.get("atr") or 0.0
    tol = s.retest_atr * atr
    out = []
    for e in ev.get("events", []):
        k = index.get(e.get("break_at", ""))
        if k is None:
            continue
        b = bars[k]
        up = e["direction"] == "UP"
        prior = [x.v for x in bars[max(0, k - s.volume_bars) : k] if x.v]
        vol_ratio = round(b.v / (sum(prior) / len(prior)), 2) if prior and b.v else None
        beyond = (b.c - e["level"]) if up else (e["level"] - b.c)
        retest_at = completed_at = None
        retest_k = None
        for j in range(k + 1, len(bars)):
            x = bars[j]
            touched = (x.l <= e["level"] + tol) if up else (x.h >= e["level"] - tol)
            if retest_k is None and touched:
                retest_k, retest_at = j, (x.t + TF_DELTA[tf]).isoformat()
            if retest_k is not None and j > retest_k and ((x.c > bars[retest_k].h) if up else (x.c < bars[retest_k].l)):
                completed_at = (x.t + TF_DELTA[tf]).isoformat()
                break
        after = bars[k + 1 :]
        follow = max(((x.h - e["level"]) if up else (e["level"] - x.l) for x in after), default=0.0)
        out.append({
            **{key: v for key, v in e.items() if key != "index"},
            "label": label(e["kind"], e["direction"]),
            "close": b.c,
            "body_beyond_atr": round(beyond / atr, 2) if atr else None,
            "body_acceptance": atr > 0 and beyond >= s.body_atr * atr,
            "volume_ratio": vol_ratio,
            "retest_at": retest_at,
            "retest_completed_at": completed_at,
            "follow_through_atr": round(follow / atr, 2) if atr else None,
            "bars_since": len(bars) - 1 - k,
        })
    return out


def bos_core(bars: dict[str, list[Bar]], overview: dict, s: BosSettings) -> dict:
    return {
        tf: {
            "events": enrich(bars[BAR_KEYS[tf]], overview["events"].get(tf, {}), tf, s),
            "atr": overview["events"].get(tf, {}).get("atr"),
            "swing_high": overview["events"].get(tf, {}).get("swing_high"),
            "swing_low": overview["events"].get(tf, {}).get("swing_low"),
            "trend": overview["events"].get(tf, {}).get("trend"),
        }
        for tf in BOS_TIMEFRAMES
    }


def _status(e: dict, price: float | None, atr: float | None, s: BosSettings) -> tuple[str, str]:
    """(status, retest) for a closed break given the live price."""
    if e.get("failed"):
        return "FAILED", "NONE" if not e.get("retest_at") else "COMPLETED" if e.get("retest_completed_at") else "RETESTING"
    tol = s.retest_atr * (atr or 0)
    up = e["direction"] == "UP"
    dist = None if price is None else (price - e["level"]) if up else (e["level"] - price)
    if dist is not None and dist <= tol:
        return "RETESTING", "RETESTING"
    if e.get("retest_completed_at"):
        return "CONFIRMED", "COMPLETED"
    if e.get("retest_at"):
        return "RETESTING", "RETESTING"
    if dist is not None and atr and dist <= s.monitor_atr * atr:
        return "MONITORING", "PENDING"
    return "CONFIRMED", "PENDING"


def live_events(core: dict, price: float | None, now: datetime, s: BosSettings) -> list[dict]:
    """All breaks with live status (newest first), plus developing breaks of the active swings."""
    out = []
    for tf in BOS_TIMEFRAMES:
        c = core.get(tf) or {}
        for e in c.get("events", []):
            st, rt = _status(e, price, c.get("atr"), s)
            out.append({**e, "closed": True, "status": {"key": st, "label": EVENT_STATUS[st]},
                        "retest": {"key": rt, "label": RETEST[rt]}})
        if price is None:
            continue
        for direction, level in (("UP", c.get("swing_high")), ("DOWN", c.get("swing_low"))):
            if level is None or not ((price > level) if direction == "UP" else (price < level)):
                continue
            kind = "BOS" if c.get("trend") == (1 if direction == "UP" else -1) else "CHOCH"
            out.append({"tf": tf, "kind": kind, "direction": direction, "level": level, "at": now.isoformat(),
                        "label": label(kind, direction), "closed": False, "close": None, "body_acceptance": None,
                        "volume_ratio": None, "retest_at": None, "retest_completed_at": None,
                        "status": {"key": "DEVELOPING", "label": "Developing"}, "retest": {"key": "NONE", "label": "—"}})
    out.sort(key=lambda e: (e["at"], -BOS_TIMEFRAMES.index(e["tf"])), reverse=True)
    return out


def _since(at: str, now: datetime) -> str:
    sec = max(0, (now - datetime.fromisoformat(at)).total_seconds())
    if sec < 3600:
        return f"{int(sec // 60)} minutes"
    if sec < 86400:
        h, m = divmod(int(sec // 60), 60)
        return f"{h} hour{'s' if h != 1 else ''} {m} minutes"
    d = int(sec // 86400)
    return f"{d} day{'s' if d != 1 else ''}"


def _structure_after(swings: list[dict], at: str) -> str:
    labs = [x["label"] for x in swings if x.get("label") and x["at"] >= at]
    hi = next((x for x in reversed(labs) if x in ("HH", "LH")), None)
    lo = next((x for x in reversed(labs) if x in ("HL", "LL")), None)
    return " / ".join(x for x in (hi, lo) if x) or "Pending swings"


def symbol_view(core: dict, events: list[dict], trend_core: dict, regimes: dict, state: dict, range_view: dict | None,
                price: float | None, tf: str, now: datetime, s: BosSettings) -> dict:
    """Per-symbol context, focus-event details, MTF table, lifecycle, evidence and related levels."""
    px = price
    closed = [e for e in events if e["closed"]]
    focus = next((e for e in events if e["tf"] == tf), None) or (events[0] if events else None)
    last_bos = next((e for e in closed if e["kind"] == "BOS"), None)
    last_choch = next((e for e in closed if e["kind"] == "CHOCH"), None)

    levels = []
    for t in ("H1", "H8", "D1"):
        for sw in (trend_core.get(t) or {}).get("swings", [])[-6:]:
            levels.append({"price": sw["price"], "type": "Resistance" if sw["side"] == "HIGH" else "Support", "tf": t})
    for e in (last_bos, last_choch):
        if e:
            levels.append({"price": e["level"], "type": f"{'BOS' if e['kind'] == 'BOS' else 'CHoCH'} Level", "tf": e["tf"]})
    if px is not None:
        above = sorted((x for x in levels if x["price"] > px and x["type"] == "Resistance"), key=lambda x: x["price"])
        below = sorted((x for x in levels if x["price"] < px and x["type"] == "Support"), key=lambda x: -x["price"])
    else:
        above = below = []
    related = []
    seen: set[float] = set()
    for x in [l for l in levels if "Level" in l["type"]] + above[:2] + below[:2]:
        if round(x["price"], 6) in seen:
            continue
        seen.add(round(x["price"], 6))
        related.append({**x, "distance": None if px is None else x["price"] - px})
    related.sort(key=lambda x: -x["price"])

    w_regime = regimes.get("W")
    w_band = ((range_view or {}).get("position_band") or {}).get("label")
    align_dir = {"UP": "BULLISH", "DOWN": "BEARISH"}

    details = lifecycle = evidence = None
    if focus:
        up = focus["direction"] == "UP"
        tc = trend_core.get(focus["tf"]) or {}
        sw = tc.get("swings", [])
        opp = [e for e in closed if e["at"] > focus["at"] and e["direction"] != focus["direction"] and e["tf"] in (focus["tf"], _higher(focus["tf"]))]
        higher = [t for t in BOS_TIMEFRAMES[: BOS_TIMEFRAMES.index(focus["tf"])] if t != "W"] or ["W"]
        higher_agree = [t for t in higher if regimes.get(t) == align_dir[focus["direction"]]]
        atr = (core.get(focus["tf"]) or {}).get("atr") or 0
        key_level = any(
            abs(x["price"] - focus["level"]) <= s.key_level_atr * atr
            for t in higher
            for x in (trend_core.get(t) or {}).get("swings", [])
        ) if atr else False
        invalid = next((x["price"] for x in reversed(sw) if x["side"] == ("LOW" if up else "HIGH") and x["at"] <= focus.get("break_at", focus["at"])), None)
        details = {
            "label": focus["label"],
            "kind": focus["kind"],
            "direction": focus["direction"],
            "tf": focus["tf"],
            "level": focus["level"],
            "at": focus["at"],
            "break_candle": focus.get("break_at"),
            "closed": focus["closed"],
            "close_side": "Above" if up else "Below",
            "body_acceptance": focus.get("body_acceptance"),
            "retest": focus["retest"],
            "status": focus["status"],
            "parent_w": w_regime,
            "d1": regimes.get("D1"),
            "h8": regimes.get("H8"),
            "structure_after": _structure_after(sw, focus.get("break_at", focus["at"])),
            "volume_ratio": focus.get("volume_ratio"),
            "volume_confirmed": (focus.get("volume_ratio") or 0) >= s.volume_ratio,
            "invalidation": invalid,
            "since": _since(focus["at"], now),
        }
        rt = focus["retest"]["key"]
        lifecycle = [
            {"key": "BREAK", "label": "Break Detected", "done": True, "at": focus.get("break_at") or focus["at"]},
            {"key": "CLOSE", "label": "Close Validation", "done": focus["closed"], "at": focus["at"] if focus["closed"] else None},
            {"key": "RETEST", "label": "Retest in Progress" if rt in ("RETESTING", "PENDING") else "Retest",
             "done": bool(focus.get("retest_at")), "current": rt == "RETESTING", "at": focus.get("retest_at")},
            {"key": "CONFIRMED", "label": "Confirmed", "done": bool(focus.get("retest_completed_at")) and not focus.get("failed"),
             "at": focus.get("retest_completed_at")},
        ]
        vr = focus.get("volume_ratio")
        evidence = [
            {"label": "Structure break at key level", "met": key_level},
            {"label": "Close confirmation", "met": focus["closed"]},
            {"label": f"Volume above average ({vr:.1f}x)" if vr else "Volume above average", "met": (vr or 0) >= s.volume_ratio},
            {"label": f"Multi-TF alignment ({' / '.join(higher)} {'bullish' if up else 'bearish'})", "met": len(higher_agree) == len(higher)},
            {"label": f"Retest {focus['retest']['label'].lower()}" if rt != "NONE" else "Retest not started", "met": rt == "COMPLETED"},
            {"label": "No opposing structure", "met": not opp},
        ]
    mtf = []
    for t in BOS_TIMEFRAMES:
        last = next((e for e in events if e["tf"] == t), None)
        r = regimes.get(t)
        mtf.append({
            "tf": t,
            "structure": r,
            "last_event": None if not last else ("BOS" if last["kind"] == "BOS" else "CHoCH"),
            "last_direction": None if not last else last["direction"],
            "status": "Developing" if last and not last["closed"] else "Failed" if last and last["status"]["key"] == "FAILED"
            else "Active" if last else "—",
        })
    bias_dir = regimes.get("D1") or regimes.get("H8")
    bias = (bias_dir or "Neutral").title()
    if w_regime == "RANGING" and bias_dir in ("BULLISH", "BEARISH"):
        bias += " (within range)"
    context = {
        "parent": w_regime,
        "parent_band": w_band,
        "d1": regimes.get("D1"),
        "phase": state,
        "last_bos": None if not last_bos else {"level": last_bos["level"], "tf": last_bos["tf"], "direction": last_bos["direction"]},
        "last_choch": None if not last_choch else {"level": last_choch["level"], "tf": last_choch["tf"], "direction": last_choch["direction"]},
        "price": px,
        "nearest_resistance": above[0] if above else None,
        "nearest_support": below[0] if below else None,
        "bias": bias,
        "invalidation": (details or {}).get("invalidation"),
        "retest": (focus or {}).get("retest"),
        "since": (details or {}).get("since"),
    }
    return {"context": context, "details": details, "lifecycle": lifecycle, "evidence": evidence, "mtf": mtf, "levels": related}


def _higher(tf: str) -> str:
    k = BOS_TIMEFRAMES.index(tf)
    return BOS_TIMEFRAMES[max(0, k - 1)]


def chart_marks(core: dict, trend_core: dict, tf: str, limit: int = 12) -> dict:
    evs = (core.get(tf) or {}).get("events", [])[-limit:]
    swings = (trend_core.get(tf) or {}).get("swings", [])
    return {
        "events": [{"kind": e["kind"], "direction": e["direction"], "level": e["level"], "swing_at": e.get("swing_at"),
                    "break_at": e.get("break_at"), "failed": e.get("failed", False)} for e in evs],
        "swings": [{"label": x["label"], "side": x["side"], "price": x["price"], "at": x["at"]} for x in swings if x.get("label")],
    }


def window_since(now: datetime, days: float) -> datetime:
    return now - timedelta(days=days)
