"""Structure Overview analytics on closed candles: per-timeframe regime, MTF alignment, BOS/CHoCH events.

Pure functions over ``Bar`` tuples so they are testable without MT5. Confirmed structure uses closed bars only;
a live price beyond the active swing is reported as a *developing* event and never as a confirmed one.
Outputs describe market structure only — never trade direction.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .scanner_analytics import Bar, market_structure, pivots, regression_channel, true_ranges, wilder_atr
from .structure_overview_config import CELLS, OVERVIEW_TIMEFRAMES, REGIMES, STATES, OverviewSettings

TF_DELTA = {"W": timedelta(days=7), "D1": timedelta(days=1), "H8": timedelta(hours=8), "H1": timedelta(hours=1)}
EVENT_TIMEFRAMES = ("W", "D1", "H8", "H1")
_DIR = {"BULLISH": 1, "BEARISH": -1}


def _kl(key: str, table: dict[str, str]) -> dict:
    return {"key": key, "label": table[key]}


def ltf_regime(bars: list[Bar], s: OverviewSettings) -> str | None:
    """Swing structure decides trend; mixed swings are Ranging in a flat channel, otherwise Transition."""
    st = market_structure(bars, s.fractal_strength)["key"]
    if st == "INSUFFICIENT":
        return None
    if st in _DIR:
        return st
    ch = regression_channel(bars, min(s.channel_period, len(bars)), 2.0)
    return "RANGING" if ch.get("direction") == "FLAT" else "TRANSITION"


def weekly_regime(core: dict) -> str | None:
    key = (core.get("regime") or {}).get("key")
    if key in ("RANGING", "BULLISH", "BEARISH"):
        return key
    if key == "TRANSITIONAL":
        return "TRANSITION"
    return None


def cells_for(regimes: dict[str, str | None]) -> dict[str, dict | None]:
    """Matrix cells; a timeframe running against the dominant (highest trending) higher timeframe is a Pullback."""
    out: dict[str, dict | None] = {}
    for k, tf in enumerate(OVERVIEW_TIMEFRAMES):
        r = regimes.get(tf)
        if r is None:
            out[tf] = None
            continue
        higher = next((regimes[h] for h in OVERVIEW_TIMEFRAMES[:k] if regimes.get(h) in _DIR), None)
        if r in _DIR and higher and _DIR[higher] == -_DIR[r]:
            key = "PULLBACK"
        else:
            key = {"BULLISH": "BULL", "BEARISH": "BEAR", "RANGING": "RANGE"}.get(r, "NEUTRAL")
        out[tf] = {**_kl(key, CELLS), "regime": r}
    return out


def alignment(regimes: dict[str, str | None], s: OverviewSettings) -> dict:
    """0 = fully bearish, 50 = no directional agreement, 100 = fully bullish (weighted W/D1/H8/H1)."""
    bias = sum(s.weights[tf] * _DIR.get(regimes.get(tf) or "", 0) for tf in OVERVIEW_TIMEFRAMES)
    score = round(50 + 50 * bias)
    if score >= s.bullish_min:
        label = {"key": "BULLISH", "label": "Bullish"}
    elif score <= s.bearish_max:
        label = {"key": "BEARISH", "label": "Bearish"}
    else:
        label = {"key": "MIXED", "label": "Mixed"}
    return {"score": score, **label}


def current_state(regimes: dict[str, str | None], cells: dict[str, dict | None], position_band: str | None) -> dict:
    w = regimes.get("W")
    if w is None:
        return _kl("INSUFFICIENT", STATES)
    if w == "RANGING":
        if position_band in ("ABOVE_RANGE", "BELOW_RANGE"):
            return _kl("BREAKOUT", STATES)
        if position_band in ("UPPER_EXTREME", "LOWER_EXTREME"):
            return _kl("REACTION", STATES)
        return _kl("ROTATION", STATES)
    if w == "TRANSITION":
        return _kl("TRANSITION", STATES)
    d1 = _DIR.get(regimes.get("D1") or "", 0)
    if d1 == -_DIR[w]:
        return _kl("REVERSAL", STATES)
    if d1 == 0:
        return _kl("TRANSITION", STATES)
    if any((cells.get(tf) or {}).get("key") == "PULLBACK" for tf in ("H8", "H1")):
        return _kl("CONTINUATION", STATES)
    return _kl("TRENDING", STATES)


def structure_events(bars: list[Bar], tf: str, n: int, atr_period: int = 14) -> dict:
    """Replay closed bars: a close through the active swing is a BOS with the prevailing trend, else a CHoCH."""
    highs, lows = pivots(bars, n)
    hq = [(i + n, p) for i, p in highs]
    lq = [(i + n, p) for i, p in lows]
    trend = 0
    swing_h: float | None = None
    swing_l: float | None = None
    swing_h_at = swing_l_at = None
    hp = lp = 0
    events: list[dict] = []
    for k, b in enumerate(bars):
        while hp < len(hq) and hq[hp][0] < k:
            swing_h, swing_h_at = hq[hp][1], bars[hq[hp][0] - n].t
            hp += 1
        while lp < len(lq) and lq[lp][0] < k:
            swing_l, swing_l_at = lq[lp][1], bars[lq[lp][0] - n].t
            lp += 1
        if swing_h is not None and b.c > swing_h:
            events.append({"tf": tf, "kind": "BOS" if trend == 1 else "CHOCH", "direction": "UP", "level": swing_h, "index": k,
                           "at": (b.t + TF_DELTA[tf]).isoformat(), "break_at": b.t.isoformat(), "swing_at": swing_h_at.isoformat()})
            trend, swing_h = 1, None
        elif swing_l is not None and b.c < swing_l:
            events.append({"tf": tf, "kind": "BOS" if trend == -1 else "CHOCH", "direction": "DOWN", "level": swing_l, "index": k,
                           "at": (b.t + TF_DELTA[tf]).isoformat(), "break_at": b.t.isoformat(), "swing_at": swing_l_at.isoformat()})
            trend, swing_l = -1, None
    atr = wilder_atr(true_ranges(bars), atr_period)[-1] if len(bars) > atr_period + 1 else None
    for e in events:
        after = bars[e["index"] + 1 :]
        up = e["direction"] == "UP"
        e["failed"] = any((c.c < e["level"]) if up else (c.c > e["level"]) for c in after)
        e.pop("index")
    return {"events": events, "trend": trend, "swing_high": swing_h, "swing_low": swing_l, "atr": atr,
            "last_close": bars[-1].c if bars else None, "last_low": bars[-1].l if bars else None,
            "last_high": bars[-1].h if bars else None}


def regime_changes(bars: list[Bar], tf: str, since: datetime, s: OverviewSettings) -> list[dict]:
    """Regime at every bar close since ``since`` versus the close before it (closed bars only)."""
    out: list[dict] = []
    idx = [k for k, b in enumerate(bars) if b.t + TF_DELTA[tf] > since]
    if not idx or idx[0] == 0:
        return out
    prev = ltf_regime(bars[: idx[0]], s)
    for k in idx:
        cur = ltf_regime(bars[: k + 1], s)
        if prev and cur and cur != prev:
            out.append({"tf": tf, "from": _kl(prev, REGIMES), "to": _kl(cur, REGIMES), "at": (bars[k].t + TF_DELTA[tf]).isoformat()})
        prev = cur or prev
    return out


def overview_core(bars: dict[str, list[Bar]], range_core: dict, prev_week_core: dict | None, s: OverviewSettings) -> dict:
    """Price-independent per-symbol structure: regimes, events per timeframe, regime changes in the window."""
    key_map = {"W": "W1", "D1": "D1", "H8": "H8", "H1": "H1"}
    regimes: dict[str, str | None] = {"W": weekly_regime(range_core)}
    for tf in ("D1", "H8", "H1"):
        regimes[tf] = ltf_regime(bars[key_map[tf]], s)
    h1 = bars["H1"]
    anchor = (h1[-1].t + TF_DELTA["H1"]) if h1 else None
    events = {tf: structure_events(bars[key_map[tf]], tf, s.fractal_strength, s.atr_period) for tf in EVENT_TIMEFRAMES}
    changes: list[dict] = []
    if anchor is not None:
        since = anchor - timedelta(hours=s.regime_change_hours)
        for tf in ("D1", "H8", "H1"):
            changes += regime_changes(bars[key_map[tf]], tf, since, s)
        w = bars["W1"]
        if prev_week_core is not None and w and w[-1].t + TF_DELTA["W"] > since:
            before, after = weekly_regime(prev_week_core), regimes["W"]
            if before and after and before != after:
                changes.append({"tf": "W", "from": _kl(before, REGIMES), "to": _kl(after, REGIMES),
                                "at": (w[-1].t + TF_DELTA["W"]).isoformat()})
    return {"regimes": regimes, "events": events, "changes": changes, "anchor": anchor.isoformat() if anchor else None}


def _event_status(e: dict, ev: dict, price: float | None, s: OverviewSettings) -> str:
    if e["failed"]:
        return "FAILED"
    tol = (ev["atr"] or 0) * s.retest_atr
    probe = [x for x in (ev["last_low"] if e["direction"] == "UP" else ev["last_high"], price) if x is not None]
    if e["direction"] == "UP" and any(x <= e["level"] + tol for x in probe):
        return "RETESTING"
    if e["direction"] == "DOWN" and any(x >= e["level"] - tol for x in probe):
        return "RETESTING"
    return "CONFIRMED"


EVENT_STATUS = {"CONFIRMED": "Confirmed", "RETESTING": "Retesting", "DEVELOPING": "Developing", "FAILED": "Failed"}


def live_events(core: dict, price: float | None, now: datetime, s: OverviewSettings) -> list[dict]:
    """Closed events in the lookback window with live status, plus developing (unclosed) breaks."""
    anchor = datetime.fromisoformat(core["anchor"]) if core.get("anchor") else now
    since = anchor - timedelta(hours=s.event_lookback_hours)
    out: list[dict] = []
    for tf, ev in core["events"].items():
        for e in ev["events"]:
            if datetime.fromisoformat(e["at"]) < since:
                continue
            st = _event_status(e, ev, price, s)
            out.append({**{k: v for k, v in e.items() if k != "failed"}, "status": {"key": st, "label": EVENT_STATUS[st]}})
        if price is None:
            continue
        for direction, level in (("UP", ev["swing_high"]), ("DOWN", ev["swing_low"])):
            if level is None:
                continue
            beyond = price > level if direction == "UP" else price < level
            if beyond:
                trend = 1 if direction == "UP" else -1
                out.append({"tf": tf, "kind": "BOS" if ev["trend"] == trend else "CHOCH", "direction": direction,
                            "level": level, "at": now.isoformat(), "status": {"key": "DEVELOPING", "label": "Developing"}})
    for e in out:
        word = "Bullish" if e["direction"] == "UP" else "Bearish"
        e["label"] = f"{word} {'BOS' if e['kind'] == 'BOS' else 'CHoCH'}"
    out.sort(key=lambda e: e["at"], reverse=True)
    return out
