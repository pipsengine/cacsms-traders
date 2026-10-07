"""KeyLevelEngine, NextMoveProjectionEngine, SessionPlanEngine, ChartAnnotationEngine and OpportunityRankingEngine.

All prices are engine levels (channel boundaries, fractals, swing liquidity, range edges, BOS levels, Supertrend);
ATR-derived fallbacks are labelled with their basis so nothing is presented as structure when it is not."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from .calendar import next_trading_day, session_windows
from .config import OutlookSettings

IMPORTANCE = {"High": 3, "Medium": 2, "Low": 1}
CHANNEL_IMPORTANCE = {"Y": "High", "YTD": "High", "HY": "High", "Q": "High", "MN": "High", "W": "High", "D1": "High", "H8": "Medium", "H1": "Low"}
TF_LABEL = {"Y": "Yearly", "YTD": "YTD", "HY": "Half-year", "Q": "Quarterly", "MN": "Monthly", "W": "Weekly", "D1": "D1", "H8": "H8", "H1": "H1"}
WORD = {1: "Bullish", -1: "Bearish", 0: "Range"}


def _f(v: float | None, dp: int) -> str:
    return "—" if v is None else f"{v:,.{dp}f}"


# ----- KeyLevelEngine -----


def key_levels(facts: dict) -> list[dict]:
    """Every structural level with its source, timeframe and importance (side resolved against the frozen close)."""
    px, out = facts["price"], []

    def add(price: float | None, tf: str, source: str, label: str, importance: str, kind: str = "level", *, liquidity: bool = False,
            evidence: str | None = None) -> None:
        if price is None or not math.isfinite(price):
            return
        out.append({"price": price, "tf": tf, "source": source, "label": label, "importance": importance, "kind": kind,
                    "liquidity": liquidity, "evidence_key": evidence})

    for tf, v in facts["channels"].items():
        if v.get("available"):
            add(v["upper"], tf, "Channel Intelligence", f"{TF_LABEL[tf]} upper channel", CHANNEL_IMPORTANCE[tf], "channel", evidence=f"channel_dir:{tf}")
            add(v["lower"], tf, "Channel Intelligence", f"{TF_LABEL[tf]} lower channel", CHANNEL_IMPORTANCE[tf], "channel", evidence=f"channel_dir:{tf}")
            if tf in ("W", "D1", "H8"):
                add(v["mid"], tf, "Channel Intelligence", f"{TF_LABEL[tf]} channel midline", "Low", "mid")
    rc = (facts.get("range") or {}).get("core") or {}
    if rc.get("range_high") is not None:
        word = "range" if rc.get("ranging") else "swing"
        add(rc["range_high"], "W", "Range Structure", f"Weekly {word} high", "High", "range", evidence="range")
        add(rc["range_low"], "W", "Range Structure", f"Weekly {word} low", "High", "range", evidence="range")
        lw = rc.get("last_week") or {}
        add(lw.get("high"), "W", "Range Structure", "Prior week high", "Medium", "liquidity", liquidity=True)
        add(lw.get("low"), "W", "Range Structure", "Prior week low", "Medium", "liquidity", liquidity=True)
    fv = facts.get("fractals") or {}
    for side in ("resistance", "support"):
        for cl in (fv.get("clusters") or {}).get(side, [])[:3]:
            add(cl["hi"] if side == "resistance" else cl["lo"], "W", "Fractals", f"Weekly fractal {side} cluster", "High", "fractal",
                evidence=f"fractal_cluster:{side}")
    for h in fv.get("hierarchy") or []:
        if h.get("kind") != "PRICE" and h.get("status", {}).get("key") != "INVALID":
            add(h["price"], h["tf"], "Fractals", h["title"], "High" if h["tf"] == "W" else "Medium" if h["tf"] == "D1" else "Low", "fractal")
    for tf, se in facts["structure_events"].items():
        if tf == "W":
            continue
        imp = "Medium" if tf in ("D1", "H8") else "Low"
        add(se.get("swing_high"), tf, "BOS / CHoCH", f"{tf} swing high (buy-side liquidity)", imp, "liquidity", liquidity=True, evidence=f"bos:{tf}")
        add(se.get("swing_low"), tf, "BOS / CHoCH", f"{tf} swing low (sell-side liquidity)", imp, "liquidity", liquidity=True, evidence=f"bos:{tf}")
        for e in se.get("recent", [])[-1:]:
            if not e.get("failed"):
                add(e["level"], tf, "BOS / CHoCH", f"{tf} {'BOS' if e['kind'] == 'BOS' else 'CHoCH'} level", imp, "bos", evidence=f"bos:{tf}")
    st = (facts.get("supertrend") or {}).get("D1") or {}
    if st.get("available"):
        add(st["line"], "D1", "Supertrend", "D1 Supertrend", "Medium", "dynamic", evidence="supertrend:D1")
    tit = facts.get("tit") or {}
    if tit.get("setup"):
        s = tit["setup"]
        add(s["objective_1"], tit["countertrend"]["tf"], "Trend-in-Trend", f"TiT objective ({s['objective_1_label']})", "Medium", "objective", evidence="tit_setup")
    for lv in out:
        lv["side"] = "resistance" if lv["price"] > px else "support"
        lv["distance"] = lv["price"] - px
        lv["distance_atr"] = round(lv["distance"] / facts["atr"], 2) if facts["atr"] else None
    out.sort(key=lambda lv: -lv["price"])
    return out


def _cluster(levels: list[dict], tol: float) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for lv in sorted(levels, key=lambda x: x["price"]):
        if groups and lv["price"] - groups[-1][0]["price"] <= tol:
            groups[-1].append(lv)
        else:
            groups.append([lv])
    return groups


def _weight(group: list[dict]) -> float:
    return sum(IMPORTANCE[lv["importance"]] for lv in group) + 0.5 * len({lv["source"] for lv in group})


# ----- NextMoveProjectionEngine -----


def reaction_zone(facts: dict, levels: list[dict], d: int, s: OutlookSettings) -> dict:
    """ERZ: strongest confluence of structure on the pullback side within reach of the close."""
    px, atr, dp = facts["price"], facts["atr"] or 0.0, facts["digits"]
    side = "support" if d >= 0 else "resistance"
    reach = s.near_level_atr * atr
    pool = [lv for lv in levels if lv["side"] == side and abs(lv["distance"]) <= reach and lv["kind"] != "mid"]
    if d == 0:
        pool = [lv for lv in levels if abs(lv["distance"]) <= reach and lv["kind"] in ("range", "channel", "fractal")]
    groups = _cluster(pool, 0.35 * atr) if atr else []
    if groups:
        best = max(groups, key=lambda g: (_weight(g) / (1 + abs((g[0]["price"] + g[-1]["price"]) / 2 - px) / max(atr, 1e-12)), -abs(g[0]["price"] - px)))
        lo, hi = best[0]["price"], best[-1]["price"]
        min_w, max_w = 0.15 * atr, s.erz_max_atr * atr
        if hi - lo < min_w:
            c = (hi + lo) / 2
            lo, hi = c - min_w / 2, c + min_w / 2
        if hi - lo > max_w:
            anchor = hi if d >= 0 else lo
            lo, hi = (anchor - max_w, anchor) if d >= 0 else (anchor, anchor + max_w)
        basis = " + ".join(dict.fromkeys(lv["label"] for lv in best))
        sources = list(dict.fromkeys(lv["source"] for lv in best))
        evidence = [lv["evidence_key"] for lv in best if lv["evidence_key"]]
    else:
        tit = facts.get("tit") or {}
        geo = (facts.get("trend") or {}).get("geometry")
        if tit.get("setup") and (1 if tit["parent"]["direction"] == "UPTREND" else -1) == d:
            lo, hi = tit["setup"]["zone"]
            basis, sources, evidence = "Trend-in-Trend continuation zone", ["Trend-in-Trend"], ["tit_setup"]
        elif geo and d != 0:
            lo, hi = geo["zone"]
            basis, sources, evidence = "Trend pullback zone", ["Trend Structure"], ["trend_pullback"]
        else:
            lo, hi = (px - 0.5 * atr, px - 0.15 * atr) if d >= 0 else (px + 0.15 * atr, px + 0.5 * atr)
            basis, sources, evidence = f"ATR reaction band (no structure within {s.near_level_atr:.1f} ATR)", ["Volatility (ATR)"], []
    inside = lo <= px <= hi
    return {"lo": lo, "hi": hi, "mid": (lo + hi) / 2, "basis": basis, "sources": sources, "evidence_keys": evidence,
            "price_inside": inside, "distance_atr": 0.0 if inside else round(min(abs(px - lo), abs(px - hi)) / atr, 2) if atr else None,
            "label": f"{_f(lo, dp)} – {_f(hi, dp)}"}


def _beyond(levels: list[dict], ref: float, d: int, min_gap: float) -> list[dict]:
    pool = [lv for lv in levels if (lv["price"] - ref) * d >= min_gap and lv["kind"] != "mid"]
    groups = _cluster(pool, min_gap * 0.8) if min_gap else [[lv] for lv in pool]
    reps = []
    for g in groups:
        top = max(g, key=lambda lv: IMPORTANCE[lv["importance"]])
        reps.append({**top, "confluence": [lv["label"] for lv in g], "price": top["price"]})
    reps.sort(key=lambda lv: (lv["price"] - ref) * d)
    return reps


def targets(facts: dict, levels: list[dict], d: int, ref: float, s: OutlookSettings) -> list[dict]:
    atr, out = facts["atr"] or 0.0, []
    for lv in _beyond(levels, ref, d, s.target_min_atr * atr):
        if not out or (lv["price"] - out[-1]["price"]) * d >= 0.5 * atr:
            out.append({"price": lv["price"], "label": lv["label"], "source": lv["source"], "tf": lv["tf"], "basis": "structure",
                        "confluence": lv["confluence"], "evidence_key": lv["evidence_key"]})
        if len(out) == 2:
            break
    while len(out) < 2 and atr:
        base = out[-1]["price"] if out else ref
        out.append({"price": base + d * atr, "label": "ATR extension", "source": "Volatility (ATR)", "tf": "D1", "basis": "atr",
                    "confluence": [], "evidence_key": None})
    return out


def invalidation(facts: dict, levels: list[dict], d: int, erz: dict, s: OutlookSettings) -> dict:
    atr = facts["atr"] or 0.0
    edge = erz["lo"] if d >= 0 else erz["hi"]
    pool = [lv for lv in _beyond(levels, edge, -d, 0.1 * atr) if abs(lv["price"] - edge) <= s.invalidation_max_atr * atr]
    strong = [lv for lv in pool if lv["importance"] == "High"] or pool
    if strong:
        lv = strong[0]
        return {"price": lv["price"], "label": lv["label"], "source": lv["source"], "tf": lv["tf"], "basis": "structure",
                "evidence_key": lv["evidence_key"]}
    return {"price": edge - d * 0.5 * atr, "label": "ATR beyond reaction zone", "source": "Volatility (ATR)", "tf": "D1", "basis": "atr",
            "evidence_key": None}


def _days_ahead(anchor: datetime, n: int) -> datetime:
    t, day = anchor, anchor.date()
    for _ in range(max(1, n)):
        day = next_trading_day(day)
    return t + timedelta(days=(day - anchor.date()).days)


def path(anchor: datetime, px: float, steps: list[float], atr: float) -> list[list]:
    """Expected path through the plan's levels; spacing in trading days from the distance in daily ATRs."""
    pts, t, last = [[anchor.isoformat(), px]], anchor, px
    for k, level in enumerate(steps):
        days = 1 if k == 0 else max(1, math.ceil(abs(level - last) / (0.7 * atr))) if atr else 1
        t = _days_ahead(t, days) if k else t + timedelta(hours=10)
        pts.append([t.isoformat(), level])
        last = level
    return pts


def confirmation_sequence(d: int, erz: dict, inv: dict, tg: list[dict], facts: dict, dp: int, family: str) -> list[dict]:
    """Machine-checkable steps (the intraday monitor evaluates each condition on closed H1/M30 bars)."""
    up = d == 1
    word = "bullish" if up else "bearish"
    h1_against = (facts["structure_events"].get("H1") or {}).get("trend") == -d
    steps = [{"key": "REACTION", "label": f"Asian session: look for reaction at {erz['label']} (ERZ).",
              "condition": {"type": "touch_zone", "lo": erz["lo"], "hi": erz["hi"]}},
             {"key": "EXHAUSTION", "label": f"M30/H1: {'selling' if up else 'buying'} exhaustion inside the ERZ.",
              "condition": {"type": "reject_zone", "tf": "M30", "lo": erz["lo"], "hi": erz["hi"], "dir": d}}]
    if h1_against or family == "REV":
        steps.append({"key": "CHOCH", "label": f"H1 {word} CHoCH.", "condition": {"type": "structure", "tf": "H1", "kind": "CHOCH", "dir": d}})
    steps += [
        {"key": "BOS", "label": f"H1 {word} BOS.", "condition": {"type": "structure", "tf": "H1", "kind": "BOS", "dir": d}},
        {"key": "RETEST", "label": f"Retest of {erz['label']}.", "condition": {"type": "retest", "lo": erz["lo"], "hi": erz["hi"], "dir": d}},
        {"key": "T1", "label": f"Continuation toward {_f(tg[0]['price'], dp)} (Objective 1).", "condition": {"type": "reach", "price": tg[0]["price"], "dir": d}},
        {"key": "T2", "label": f"Extension to {_f(tg[1]['price'], dp)} (Objective 2).", "condition": {"type": "reach", "price": tg[1]["price"], "dir": d}},
    ]
    for i, st in enumerate(steps):
        st["step"] = i + 1
    return steps


def alternative_sequence(d: int, inv: dict, erz: dict, tg: list[dict], dp: int) -> list[dict]:
    word = "bullish" if d == 1 else "bearish"
    edge = erz["hi"] if d == 1 else erz["lo"]
    steps = [
        {"key": "BREAK", "label": f"Break and close {'above' if d == 1 else 'below'} {_f(inv['price'], dp)}.",
         "condition": {"type": "close_beyond", "tf": "H8", "price": inv["price"], "dir": d}},
        {"key": "CHOCH", "label": f"{word.title()} CHoCH on H1.", "condition": {"type": "structure", "tf": "H1", "kind": "CHOCH", "dir": d}},
        {"key": "BOS", "label": "H1 BOS.", "condition": {"type": "structure", "tf": "H1", "kind": "BOS", "dir": d}},
        {"key": "RETEST", "label": f"Retest from {'above' if d == 1 else 'below'} of {_f(inv['price'], dp)}.",
         "condition": {"type": "retest", "lo": min(inv["price"], edge), "hi": max(inv["price"], edge), "dir": d}},
        {"key": "T1", "label": f"Continuation to {_f(tg[0]['price'], dp)}.", "condition": {"type": "reach", "price": tg[0]["price"], "dir": d}},
        {"key": "T2", "label": f"Extension to {_f(tg[1]['price'], dp)}.", "condition": {"type": "reach", "price": tg[1]["price"], "dir": d}},
    ]
    for i, st in enumerate(steps):
        st["step"] = i + 1
    return steps


# ----- SessionPlanEngine -----


def session_plan(anchor: datetime, d: int, erz: dict, tg: list[dict], inv: dict, dp: int, regime: str) -> list[dict]:
    windows = {w["key"]: w for w in session_windows(anchor)}
    word = WORD[d].lower()
    near = erz["price_inside"] or (erz["distance_atr"] is not None and erz["distance_atr"] <= 0.5)
    if d == 0:
        plans = {
            "ASIAN": ("Range Watch", f"Expect rotation inside {erz['label']}; fade extremes only with M30 rejection."),
            "LONDON": ("Breakout Watch", f"Watch for a break of {_f(inv['price'], dp)} or {_f(tg[0]['price'], dp)} with H1 acceptance."),
            "NEW_YORK": ("Key Decision", "Confirm or reject the London break; range persists without acceptance."),
        }
    else:
        plans = {
            "ASIAN": ("Primary Focus" if near else "Watch",
                      f"Look for reaction at {erz['label']} (ERZ). Monitor M30/H1 for {word} structure." if near else
                      f"Watch price rotate toward the ERZ {erz['label']} before any {word} structure."),
            "LONDON": ("Continuation", f"If {word} confirmation occurs (H1 BOS), expect continuation toward {_f(tg[0]['price'], dp)}."),
            "NEW_YORK": ("Key Decision", f"Manage the plan. Watch for higher volatility and potential extension to {_f(tg[1]['price'], dp)}; "
                                         f"{'close below' if d == 1 else 'close above'} {_f(inv['price'], dp)} invalidates."),
        }
    return [{**windows[k], "badge": plans[k][0], "bias": WORD[d] if k == "ASIAN" else None, "plan": plans[k][1]} for k in ("ASIAN", "LONDON", "NEW_YORK")]


# ----- ChartAnnotationEngine -----


def annotations(facts: dict, a_lines: dict, plan: dict, levels: list[dict]) -> list[dict]:
    """Structured, timeframe-linked chart objects (never pixels): channels, structure, fractals, liquidity, plan."""
    dp, out = facts["digits"], []

    def add(obj: dict) -> None:
        obj["id"] = f"A{len(out) + 1:03d}"
        out.append(obj)

    for tf, lines in a_lines.items():
        if not lines:
            continue
        v = facts["channels"].get(tf) or {}
        tone = "blue" if (v.get("direction") or {}).get("key") != "DOWNTREND" else "red"
        add({"type": "channel", "group": "channel", "tf": tf, "label": f"{tf} Channel", "tone": tone, "lines": lines,
             "source": "Channel Intelligence", "evidence_key": f"channel_dir:{tf}",
             "detail": f"{tf} regression channel {_f(v.get('lower'), dp)} – {_f(v.get('upper'), dp)} ({(v.get('direction') or {}).get('label', '—')})."})
    for tf in ("W", "MN", "Q"):
        v = facts["channels"].get(tf) or {}
        if v.get("available"):
            for edge in ("upper", "lower"):
                add({"type": "htf_boundary", "group": "htf", "tf": "*", "label": f"{tf} {'Upper' if edge == 'upper' else 'Lower'} Channel",
                     "price": v[edge], "tone": "res" if edge == "upper" else "sup", "source": "Channel Intelligence",
                     "evidence_key": f"channel_dir:{tf}", "detail": f"Higher-timeframe {tf} channel {edge} boundary at {_f(v[edge], dp)}."})
    for lv in levels:
        if lv["kind"] in ("range", "fractal") and lv["importance"] == "High" and abs(lv["distance_atr"] or 99) <= 4:
            add({"type": "support" if lv["side"] == "support" else "resistance", "group": "sr", "tf": "*", "label": lv["label"],
                 "price": lv["price"], "tone": "sup" if lv["side"] == "support" else "res", "source": lv["source"],
                 "evidence_key": lv["evidence_key"], "detail": f"{lv['label']} at {_f(lv['price'], dp)} ({lv['distance_atr']:+.2f} ATR)."})
        if lv["liquidity"] and abs(lv["distance_atr"] or 99) <= 3:
            add({"type": "liquidity", "group": "liquidity", "tf": lv["tf"] if lv["tf"] in ("D1", "H8", "H1") else "*", "label": lv["label"],
                 "price": lv["price"], "tone": "purple", "source": lv["source"], "evidence_key": lv["evidence_key"],
                 "detail": f"Resting liquidity beyond the {lv['label'].lower()} at {_f(lv['price'], dp)}."})
    fv = facts.get("fractals") or {}
    for tf, marks in (fv.get("marks") or {}).items():
        for m in marks:
            add({"type": "fractal", "group": "fractal", "tf": tf, "label": m["kind"], "at": m["at"], "price": m["price"], "side": m["side"],
                 "status": m["status"], "tone": "red" if m["side"] == "HIGH" else "green", "source": "Fractals",
                 "evidence_key": None, "detail": f"{m['kind']} {m['status'].lower()} at {_f(m['price'], dp)}."})
    for tf, swings in facts["swings"].items():
        for sw in swings[-6:]:
            if sw.get("label"):
                add({"type": "swing", "group": "structure", "tf": tf, "label": sw["label"], "at": sw["at"], "price": sw["price"],
                     "side": sw["side"], "tone": "green" if sw["label"] in ("HH", "HL") else "red", "source": "Trend Structure",
                     "evidence_key": "trend_dir", "detail": f"{tf} {sw['label']} at {_f(sw['price'], dp)}."})
    for tf, se in facts["structure_events"].items():
        for e in se.get("all", [])[-3:]:
            add({"type": "bos" if e["kind"] == "BOS" else "choch", "group": "bos", "tf": tf,
                 "label": "BOS" if e["kind"] == "BOS" else "CHoCH", "at": e.get("break_at") or e["at"], "from": e.get("swing_at"),
                 "price": e["level"], "dir": e["direction"], "failed": bool(e.get("failed")),
                 "tone": "green" if e["direction"] == "UP" else "red", "source": "BOS / CHoCH", "evidence_key": f"bos:{tf}",
                 "detail": f"{tf} {'bullish' if e['direction'] == 'UP' else 'bearish'} {e['kind']} through {_f(e['level'], dp)}"
                           f"{' (failed)' if e.get('failed') else ''}."})
    for e in facts.get("breakouts") or []:
        add({"type": "breakout", "group": "breakout", "tf": e["tf"], "label": "Breakout", "at": e.get("bar_at") or e["at"], "price": e["level"],
             "dir": e["direction"], "tone": "blue", "source": "Channel Intelligence", "evidence_key": f"breakout:{e['tf']}",
             "detail": f"{e['label']} ({e['status']['label']}); retest {e['retest']['label'].lower()}."})
        if e.get("retest_bar_at"):
            add({"type": "retest", "group": "breakout", "tf": e["tf"], "label": "Retest", "at": e["retest_bar_at"], "price": e.get("retest_level") or e["level"],
                 "tone": "amber", "source": "Channel Intelligence", "evidence_key": f"breakout:{e['tf']}", "detail": "Retest of the broken channel boundary."})
    erz, inv = plan["erz"], plan["invalidation"]
    add({"type": "erz", "group": "erz", "tf": "*", "label": "Expected Reaction Zone (ERZ)", "lo": erz["lo"], "hi": erz["hi"], "tone": "green" if plan["direction"] >= 0 else "red",
         "source": " + ".join(erz["sources"]), "evidence_key": (erz["evidence_keys"] or [None])[0], "detail": f"ERZ {erz['label']} — {erz['basis']}."})
    for i, t in enumerate(plan["targets"]):
        add({"type": "target", "group": "targets", "tf": "*", "label": f"Target {i + 1}", "price": t["price"], "tone": "red" if plan["direction"] >= 0 else "green",
             "source": t["source"], "evidence_key": t["evidence_key"], "detail": f"Objective {i + 1}: {t['label']} at {_f(t['price'], dp)}."})
    add({"type": "invalidation", "group": "invalidation", "tf": "*", "label": "Invalidation", "price": inv["price"], "tone": "red",
         "source": inv["source"], "evidence_key": inv["evidence_key"], "detail": f"Close beyond {_f(inv['price'], dp)} ({inv['label']}) invalidates the primary scenario."})
    add({"type": "path", "group": "path", "tf": "*", "label": "Expected Path", "points": plan["path"], "tone": "blue" if plan["direction"] >= 0 else "red",
         "source": "NextMoveProjectionEngine", "evidence_key": None, "detail": "Primary scenario projected path through ERZ and objectives."})
    if plan.get("alt_path"):
        add({"type": "path", "group": "path", "tf": "*", "label": "Alternative Path", "points": plan["alt_path"], "tone": "red" if plan["direction"] >= 0 else "green",
             "dashed": True, "source": "NextMoveProjectionEngine", "evidence_key": None, "detail": "Alternative scenario path after invalidation."})
    return out


# ----- OpportunityRankingEngine -----


def opportunity(primary_p: float, margin: float, rr: float | None, aligned: float, erz_dist: float | None, quality: float,
                primary_dir: int, s: OutlookSettings) -> dict:
    rr_n = min(1.0, (rr or 0) / 3)
    prox = 1.0 if erz_dist is not None and erz_dist <= 0.25 else max(0.0, 1 - (erz_dist or 3) / 3)
    score = 0.42 * primary_p + 0.18 * min(100, margin * 2) + 0.15 * 100 * rr_n + 0.13 * aligned + 0.12 * 100 * prox
    score *= min(1.0, quality / 100)
    reasons = []
    if quality < s.min_data_quality:
        reasons.append(f"Data quality {quality:.0f}% < {s.min_data_quality:.0f}%")
    if primary_dir == 0:
        reasons.append("Primary scenario is consolidation — no directional opportunity")
    if primary_p < s.min_probability:
        reasons.append(f"Primary probability {primary_p:.0f}% < {s.min_probability:.0f}%")
    if margin < s.min_margin:
        reasons.append(f"Margin over alternative {margin:.0f} pts < {s.min_margin:.0f}")
    if rr is None or rr < s.min_reward_risk:
        reasons.append(f"Objective / invalidation ratio {rr or 0:.2f} < {s.min_reward_risk:.2f}")
    return {"score": round(score, 1), "qualified": not reasons, "disqualifiers": reasons,
            "components": {"probability": round(primary_p, 1), "margin": round(margin, 1), "reward_risk": rr, "alignment": round(aligned, 1),
                           "erz_proximity": round(prox * 100)}}
