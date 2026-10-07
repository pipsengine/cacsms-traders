"""Opportunity detection and closed-bar progression (pure functions, no I/O).

Detection reuses the existing engines only — Trend Structure (P1 retracement), Channel Intelligence breakouts (P2
breakout-retest), with-trend channel boundaries (continuation) and Trend-in-Trend. Each opportunity freezes its
plan (entry zone, invalidation, objectives) at creation; progression replays closed H1 bars after the opportunity's
watermark in order, so the same bars always produce the same transitions.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..market import channel_intelligence as chan
from ..market.scanner_analytics import Bar
from ..market.structure_overview import alignment as overview_alignment
from ..market.trend_structure import trend_view
from .config import OPP_TYPES, TF_DELTA, AESettings

H1 = timedelta(hours=1)
SIGN = {"BULLISH": 1, "BEARISH": -1}
REASONS = {
    "OPPORTUNITY_DETECTED": "Opportunity detected from closed-bar evidence",
    "ZONE_REACHED": "Closed bar traded into the entry zone",
    "REACTION_CONFIRMED": "Rejection candle closed out of the entry zone in the trade direction",
    "REACTION_BAR_BROKEN": "Close beyond the reaction candle extreme",
    "H1_BOS_CONFIRMED": "H1 break of structure in the trade direction",
    "INVALIDATED_PRE_ENTRY": "Closed beyond the invalidation level before confirmation",
    "ZONE_NOT_REACHED": "Entry zone not reached within the waiting window",
    "CONFIRMATION_TIMEOUT": "No confirmation within the confirmation window",
    "RISK_APPROVED": "Risk and portfolio checks passed",
    "RISK_DEFERRED": "Portfolio limits defer this opportunity",
    "RISK_REJECTED": "Risk rules reject this opportunity",
    "RISK_DEFER_TIMEOUT": "Deferred beyond the risk window",
    "EXECUTION_BLOCKED_ANALYSIS_ONLY": "Operating mode is ANALYSIS ONLY — no broker order is submitted",
    "TARGET_1_REACHED": "Shadow plan reached objective 1",
    "INVALIDATED_AFTER_CONFIRMATION": "Shadow plan hit its invalidation level",
    "NO_RESOLUTION": "Shadow plan unresolved within the tracking window",
    "PARENT_TREND_CHANGED": "Parent trend no longer supports the setup",
    "BREAKOUT_FAILED": "The source breakout failed",
    "TREND_REVERSAL_RISK": "Trend structure flags reversal risk",
    "CHANNEL_INVALIDATED": "The source channel no longer holds",
}


def _finite(*xs) -> bool:
    return all(x is not None and isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def _geometry_ok(d: int, lo: float, hi: float, inv: float, t1: float) -> bool:
    if not _finite(lo, hi, inv, t1) or lo > hi:
        return False
    return inv < lo and t1 > hi if d == 1 else inv > hi and t1 < lo


def _rr(d: int, entry: float, inv: float, t1: float) -> float | None:
    risk = (entry - inv) * d
    return round((t1 - entry) * d / risk, 2) if risk > 0 else None


def strength_component(row: dict | None, d: int) -> float:
    st = (row or {}).get("strength") or {}
    diff = st.get("differential")
    if diff is None and st.get("quote_score") is not None:
        diff = 50 - st["quote_score"]  # XAUUSD: gold strength is the inverse of USD strength
    if diff is None:
        return 50.0
    return max(0.0, min(100.0, 50 + 2.5 * diff * d))


def confidence(quality: float, row: dict | None, align_score: float | None, d: int) -> float:
    """Structural confidence (0–100): setup quality, strength agreement, MTF alignment and scanner score."""
    align = 50.0 if align_score is None else (align_score if d == 1 else 100 - align_score)
    scanner = (row or {}).get("score")
    return round(0.45 * quality + 0.20 * strength_component(row, d) + 0.20 * align + 0.15 * (50.0 if scanner is None else scanner), 1)


def _candidate(symbol: str, opp_type: str, direction: str, parent_tf: str, trigger_tf: str, zone, inv: float, t1: float,
               t2: float | None, quality: float, origin_at: str, evidence: dict, *, tit_level: str | None = None) -> dict | None:
    d = SIGN[direction]
    lo, hi = sorted(zone)
    if not _geometry_ok(d, lo, hi, inv, t1):
        return None
    family = f"{symbol}|{opp_type}|{direction}|{parent_tf}|{trigger_tf}"
    entry = (lo + hi) / 2
    return {
        "family_key": family, "symbol": symbol, "direction": direction, "opp_type": opp_type, "tit_level": tit_level,
        "parent_tf": parent_tf, "trigger_tf": trigger_tf, "entry_lo": lo, "entry_hi": hi, "invalidation": inv,
        "target_1": t1, "target_2": t2 if _finite(t2) else None, "quality": round(quality, 1),
        "reward_risk": _rr(d, entry, inv, t1), "origin_at": origin_at,
        "evidence": {"source": OPP_TYPES[opp_type], **evidence},
    }


def detect(symbol: str, a: dict, row: dict | None, now: datetime, ae: AESettings, cs: chan.ChannelSettings, ts, ovs) -> list[dict]:
    """Opportunity candidates for one instrument from its closed-bar cores (no live price is used)."""
    core = a.get("channel") or {}
    out: list[dict] = []
    align = overview_alignment(a["overview"]["regimes"], ovs) if a.get("overview") else None
    align_score = align["score"] if align else None

    # TiT: countertrend channel inside a trending parent (Channel Intelligence → Trend-in-Trend)
    t = chan.tit_view(symbol, core, None, cs)
    if t.get("available") and t.get("setup") and t.get("countertrend") and t["setup"]["status"]["key"] in ("ACTIVE", "MONITORING"):
        st, ct = t["setup"], t["countertrend"]
        direction = "BULLISH" if t["parent"]["direction"] == "UPTREND" else "BEARISH"
        cand = _candidate(symbol, "TIT", direction, t["parent"]["tf"], ct["exec_tf"], st["zone"], st["invalidation"], st["objective_1"],
                          st["objective_2"], st["quality"], (core.get(ct["tf"]) or {}).get("closed_at") or a["last_close"][0].isoformat(),
                          {"countertrend_tf": ct["tf"], "maturity": ct["maturity"], "rejoin_level": ct["rejoin_level"],
                           "setup_status": st["status"]["key"], "layer": ct["layer"]}, tit_level=ct["layer"])
        if cand:
            out.append(cand)

    # P2: confirmed channel breakout awaiting its retest
    for tf in ("D1", "H8", "H1"):
        bd = chan.breakout_detail(symbol, core, None, tf, cs)
        if not bd.get("available"):
            continue
        e = bd["event"]
        if not e["confirmed"] or e["failed"] or e.get("completed_at") or e["bars_after"] > ae.max_breakout_age_bars:
            continue
        c = core.get(tf) or {}
        atr = c.get("atr") or 0
        if not atr:
            continue
        d = 1 if e["direction"] == "UP" else -1
        line, tol = e["retest_now"], cs.retest_atr * atr
        inv = line - d * max(2 * tol, 0.5 * atr)
        width = 2 * e["half"]
        t1 = line + d * width
        t2 = line + d * 2 * width
        q = 40 * bool(bd["details"]["valid_structure"]) + 30 * bool(bd["details"]["body_acceptance"]) + 30 * min(1.0, (e.get("mfe_atr") or 0) / 1.5)
        cand = _candidate(symbol, "P2_BREAKOUT_RETEST", "BULLISH" if d == 1 else "BEARISH", chan.PARENT[tf], tf, (line - tol, line + tol),
                          inv, t1, t2, q, e["at"], {"break_at": e["at"], "break_level": e["level"], "retest_line": line,
                                                     "body_beyond_atr": e.get("body_beyond_atr"), "closes_beyond": e["closes_beyond"]})
        if cand:
            out.append(cand)

    # Continuation: valid trending channel aligned with its parent, last close at the with-trend boundary
    for tf in ("H8", "H1"):
        v = chan.tf_view(core, tf, None, cs)
        p = chan.tf_view(core, chan.PARENT[tf], None, cs)
        if not v.get("available") or not p.get("available") or v["validity"]["key"] != "VALID":
            continue
        dk = v["direction"]["key"]
        if dk not in ("UPTREND", "DOWNTREND") or p["direction"]["key"] != dk or v["position"] is None:
            continue
        pos = v["position"]
        at_edge = 0 <= pos <= cs.approach_pct if dk == "UPTREND" else 100 - cs.approach_pct <= pos <= 100
        if not at_edge:
            continue
        c = core[tf]
        d = 1 if dk == "UPTREND" else -1
        w = c["upper"] - c["lower"]
        zone = (c["lower"], c["lower"] + 0.2 * w) if d == 1 else (c["upper"] - 0.2 * w, c["upper"])
        inv = (c["lower"] if d == 1 else c["upper"]) - d * 0.5 * (c["atr"] or 0)
        t1 = c["upper"] if d == 1 else c["lower"]
        t2 = p["upper"] if d == 1 else p["lower"]
        q = 40 * c["inside_ratio"] + 30 * min(1.0, (c["touches_upper"] + c["touches_lower"]) / 6) + 30
        cand = _candidate(symbol, "CONTINUATION", "BULLISH" if d == 1 else "BEARISH", chan.PARENT[tf], tf, zone, inv, t1, t2, q,
                          c["closed_at"], {"channel_tf": tf, "position": pos, "touches": c["touches_upper"] + c["touches_lower"]})
        if cand:
            out.append(cand)

    # P1: Trend Structure continuation pullback into the retracement zone
    if a.get("trend") and a.get("overview") and a["overview"]["regimes"].get("W") is not None:
        tv = trend_view(a["trend"], a["overview"], None, now, ts, ovs)
        geo = tv.get("geometry") if tv.get("available") else None
        if tv.get("available") and tv["direction"] and tv["setup"]["key"] == "CONTINUATION" and geo \
                and geo["status"]["key"] in ("MONITORING", "IN_ZONE"):
            cand = _candidate(symbol, "P1_RETRACEMENT", tv["direction"], tv["analysis_tf"], "H1", geo["zone"], geo["invalidation"],
                              geo["objective_1"], geo["objective_2"], tv["confidence"], tv["anchor"],
                              {"depth_pct": geo["depth_pct"], "pullback": geo["pullback"]["key"], "trend_state": tv["state"]["key"],
                               "strength": tv["strength"]})
            if cand:
                out.append(cand)

    row_score = row or {}
    for cand in out:
        cand["confidence"] = confidence(cand["quality"], row_score, align_score, SIGN[cand["direction"]])
        cand["next_condition"] = next_condition({"stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", **cand})
    return out


def structural_invalidation(opp: dict, a: dict, now: datetime, cs: chan.ChannelSettings, ts, ovs) -> str | None:
    """Reason the opportunity's source condition no longer holds (checked before confirmation only)."""
    core = a.get("channel") or {}
    t = opp["opp_type"]
    if t == "TIT":
        tit = chan.tit_view(opp["symbol"], core, None, cs)
        want = "UPTREND" if opp["direction"] == "BULLISH" else "DOWNTREND"
        if not tit.get("available") or tit["parent"]["direction"] != want:
            return "PARENT_TREND_CHANGED"
    elif t == "P2_BREAKOUT_RETEST":
        brk = (opp.get("evidence") or {}).get("break_at")
        b = next((x for x in (core.get(opp["trigger_tf"]) or {}).get("breakouts", []) if x["at"] == brk), None)
        if b is not None and b["failed"]:
            return "BREAKOUT_FAILED"
    elif t == "CONTINUATION":
        v = chan.tf_view(core, opp["trigger_tf"], None, cs)
        want = "UPTREND" if opp["direction"] == "BULLISH" else "DOWNTREND"
        if not v.get("available") or v["validity"]["key"] == "LOOSE" or v["direction"]["key"] not in (want, "RANGING"):
            return "CHANNEL_INVALIDATED"
    elif t == "P1_RETRACEMENT" and a.get("trend") and a.get("overview"):
        tv = trend_view(a["trend"], a["overview"], None, now, ts, ovs)
        if tv.get("available") and (tv["setup"]["key"] == "REVERSAL_RISK" or (tv["direction"] and tv["direction"] != opp["direction"])):
            return "TREND_REVERSAL_RISK"
    return None


def next_condition(o: dict) -> str:
    d = SIGN[o["direction"]]
    word = "bullish" if d == 1 else "bearish"
    st = o["state"]
    if st == "WAITING_FOR_ZONE":
        return f"Closed H1 bar trading into {o['entry_lo']:.5g}–{o['entry_hi']:.5g}"
    if st == "AWAITING_REACTION":
        return f"H1 {word} rejection candle closing out of the entry zone"
    if st == "REACTION_CONFIRMED":
        return f"H1 close beyond the reaction candle or H1 {('bullish' if d == 1 else 'bearish')} BOS"
    if st in ("RISK_REVIEW", "RISK_DEFERRED"):
        return "Portfolio capacity (concurrency / currency exposure)"
    if st == "EXECUTION_BLOCKED_ANALYSIS_ONLY":
        return f"Shadow tracking: objective {o['target_1']:.5g} or invalidation {o['invalidation']:.5g}"
    return "—"


def _bars_between(start_iso: str, end: datetime, tf: str) -> float:
    return (end - datetime.fromisoformat(start_iso)) / TF_DELTA[tf]


def evaluate(o: dict, bars: list[Bar], bos_events: list[dict], ae: AESettings) -> tuple[list[dict], str, bool]:
    """Advance one opportunity over closed H1 bars (ascending, all after its watermark).

    Returns (steps, evaluated_through, needs_risk). Stops at a step that needs the portfolio (risk review)."""
    d = SIGN[o["direction"]]
    lo, hi, inv, t1 = o["entry_lo"], o["entry_hi"], o["invalidation"], o["target_1"]
    ev = dict(o.get("evidence") or {})
    stage, state, entered = o["stage"], o["state"], o["stage_entered_at"]
    through = o["evaluated_through"]
    steps: list[dict] = []

    def step(to_stage: str, to_state: str, reason: str, at: str, extra: dict | None = None, *, close: bool = False,
             outcome: str | None = None) -> None:
        nonlocal stage, state, entered
        steps.append({"from_stage": stage, "from_state": state, "to_stage": to_stage, "to_state": to_state, "reason_code": reason,
                      "detail": REASONS[reason], "evidence_at": at, "evidence": extra or {}, "close": close, "outcome": outcome})
        stage, state, entered = to_stage, to_state, at

    for b in bars:
        close_at = b.t + H1
        at = close_at.isoformat()
        if at <= through:
            continue
        through = at
        if state == "WAITING_FOR_ZONE":
            if (b.c - inv) * d < 0:
                step("LEARNING", "INVALIDATED", "INVALIDATED_PRE_ENTRY", at, {"close": b.c}, close=True, outcome="INVALIDATED")
                break
            if b.l <= hi and b.h >= lo:
                step("CONFIRMATION", "AWAITING_REACTION", "ZONE_REACHED", at, {"high": b.h, "low": b.l, "close": b.c})
            elif _bars_between(o["origin_at"], close_at, o["trigger_tf"]) > ae.zone_wait_bars:
                step("LEARNING", "EXPIRED", "ZONE_NOT_REACHED", at, close=True, outcome="EXPIRED")
                break
            else:
                continue
        if state == "AWAITING_REACTION":
            if (b.c - inv) * d < 0:
                step("LEARNING", "INVALIDATED", "INVALIDATED_PRE_ENTRY", at, {"close": b.c}, close=True, outcome="INVALIDATED")
                break
            rejected = (b.l <= hi and b.c > b.o and b.c >= lo) if d == 1 else (b.h >= lo and b.c < b.o and b.c <= hi)
            if rejected:
                ev["reaction"] = {"at": at, "high": b.h, "low": b.l, "close": b.c}
                step("CONFIRMATION", "REACTION_CONFIRMED", "REACTION_CONFIRMED", at, ev["reaction"])
                continue
            if _bars_between(entered, close_at, "H1") > ae.confirm_bars:
                step("LEARNING", "EXPIRED", "CONFIRMATION_TIMEOUT", at, close=True, outcome="EXPIRED")
                break
            continue
        if state == "REACTION_CONFIRMED":
            if (b.c - inv) * d < 0:
                step("LEARNING", "INVALIDATED", "INVALIDATED_PRE_ENTRY", at, {"close": b.c}, close=True, outcome="INVALIDATED")
                break
            r = ev.get("reaction") or {}
            broke = r and ((b.c > r["high"]) if d == 1 else (b.c < r["low"]))
            want = "UP" if d == 1 else "DOWN"
            bos = next((e for e in bos_events if e.get("direction") == want and not e.get("failed")
                        and (r.get("at") or "") < e.get("at", "") <= at), None)
            if broke or bos:
                ev["confirmation"] = {"at": at, "close": b.c, "by": "REACTION_BAR_BROKEN" if broke else "H1_BOS_CONFIRMED",
                                      "bos_level": (bos or {}).get("level")}
                step("RISK", "RISK_REVIEW", "REACTION_BAR_BROKEN" if broke else "H1_BOS_CONFIRMED", at, ev["confirmation"])
                return steps, through, True
            if _bars_between(entered, close_at, "H1") > ae.confirm_bars:
                step("LEARNING", "EXPIRED", "CONFIRMATION_TIMEOUT", at, close=True, outcome="EXPIRED")
                break
            continue
        if state == "RISK_DEFERRED":
            if (b.c - inv) * d < 0:
                step("LEARNING", "INVALIDATED", "INVALIDATED_PRE_ENTRY", at, {"close": b.c}, close=True, outcome="INVALIDATED")
                break
            if _bars_between(entered, close_at, "H1") > ae.risk_defer_bars:
                step("LEARNING", "EXPIRED", "RISK_DEFER_TIMEOUT", at, close=True, outcome="EXPIRED")
                break
            continue
        if state == "EXECUTION_BLOCKED_ANALYSIS_ONLY":
            entry = (ev.get("confirmation") or {}).get("close") or (lo + hi) / 2
            risk = abs(entry - inv) or None
            hit_inv = (b.l <= inv) if d == 1 else (b.h >= inv)
            hit_t1 = (b.h >= t1) if d == 1 else (b.l <= t1)
            if hit_inv:
                step("LEARNING", "COMPLETED", "INVALIDATED_AFTER_CONFIRMATION", at, {"r_multiple": -1.0 if risk else None},
                     close=True, outcome="STOPPED")
                break
            if hit_t1:
                step("LEARNING", "COMPLETED", "TARGET_1_REACHED", at,
                     {"r_multiple": round((t1 - entry) * d / risk, 2) if risk else None}, close=True, outcome="TARGET_1")
                break
            if _bars_between(entered, close_at, "H1") > ae.shadow_bars:
                step("LEARNING", "COMPLETED", "NO_RESOLUTION", at,
                     {"r_multiple": round((b.c - entry) * d / risk, 2) if risk else None}, close=True, outcome="NO_RESOLUTION")
                break
            continue
    needs_risk = state in ("RISK_REVIEW", "RISK_DEFERRED") and not (steps and steps[-1]["close"])
    return steps, through, needs_risk


def currencies(symbol: str) -> tuple[str, str]:
    return symbol[:3], symbol[3:6]


def risk_decision(o: dict, portfolio: list[dict], ae: AESettings) -> tuple[str, str, dict]:
    """Risk & portfolio gate for a confirmed opportunity: (state, reason_code, metrics).

    ``portfolio`` holds the analysis-only plans already authorised (stage EXECUTION, still being tracked)."""
    d = SIGN[o["direction"]]
    ev = o.get("evidence") or {}
    entry = (ev.get("confirmation") or {}).get("close") or (o["entry_lo"] + o["entry_hi"]) / 2
    rr = _rr(d, entry, o["invalidation"], o["target_1"])
    metrics: dict = {"entry_reference": entry, "reward_risk": rr, "confidence": o.get("confidence"),
                     "open_plans": len(portfolio), "max_concurrent": ae.max_concurrent}
    if rr is None or rr < ae.min_reward_risk:
        return "RISK_REJECTED", "RISK_REJECTED", {**metrics, "rule": "MIN_REWARD_RISK", "required": ae.min_reward_risk}
    if (o.get("confidence") or 0) < ae.min_confidence:
        return "RISK_REJECTED", "RISK_REJECTED", {**metrics, "rule": "MIN_CONFIDENCE", "required": ae.min_confidence}
    if any(p["symbol"] == o["symbol"] for p in portfolio):
        return "RISK_DEFERRED", "RISK_DEFERRED", {**metrics, "rule": "SYMBOL_EXPOSURE"}
    if len(portfolio) >= ae.max_concurrent:
        return "RISK_DEFERRED", "RISK_DEFERRED", {**metrics, "rule": "MAX_CONCURRENT"}
    base, quote = currencies(o["symbol"])
    exposure: dict[str, int] = {}
    for p in portfolio:
        pd = SIGN[p["direction"]]
        pb, pq = currencies(p["symbol"])
        exposure[pb] = exposure.get(pb, 0) + pd
        exposure[pq] = exposure.get(pq, 0) - pd
    for ccy, sign in ((base, d), (quote, -d)):
        if abs(exposure.get(ccy, 0) + sign) > ae.max_currency_exposure:
            return "RISK_DEFERRED", "RISK_DEFERRED", {**metrics, "rule": "CURRENCY_EXPOSURE", "currency": ccy,
                                                      "exposure": exposure.get(ccy, 0)}
    return "RISK_APPROVED", "RISK_APPROVED", {**metrics, "rule": None}
