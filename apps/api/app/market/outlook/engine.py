"""Per-symbol pipeline: DataQualityValidator → EvidenceAggregator → RegimeClassifier → HypothesisEngine →
ScenarioScoringEngine → NextMoveProjectionEngine → ChartAnnotationEngine → OpportunityRankingEngine.

Deterministic: identical frozen bars, strength snapshot and calibration table always yield the identical outlook."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import channel_intelligence as chan
from .. import fractal_structure as frac
from ..scanner_analytics import Bar
from . import planning as pl
from . import reasoning as rz
from .config import ENGINE_VERSION, FRESHNESS_TIMEFRAMES, REQUIRED_TIMEFRAMES, OutlookSettings
from .evidence import aggregate, digits_for

MIN_BARS = {"MN": 24, "W1": 52, "D1": 120, "H8": 90, "H1": 120}
TF_SPAN = {"W1": timedelta(days=7), "D1": timedelta(days=1), "H8": timedelta(hours=8), "H1": timedelta(hours=1)}
STALE_AFTER = {"D1": timedelta(hours=6), "H8": timedelta(hours=12), "H1": timedelta(hours=4)}
MTF_ROWS = ("Y", "YTD", "HY", "Q", "MN", "W", "D1", "H8", "H1")
WORD = {1: "Bullish", -1: "Bearish", 0: "Range"}


def _f(v: float | None, dp: int) -> str:
    return "—" if v is None else f"{v:,.{dp}f}"


# ----- DataQualityValidator -----


def validate(bars: dict[str, list[Bar]], cutoff: datetime, expected_d1_open: datetime) -> dict:
    """Completeness (bar counts) and freshness (last closed bar versus the frozen close) per timeframe."""
    checks, score = [], 0.0
    weights = {"MN": 10, "W1": 15, "D1": 35, "H8": 20, "H1": 20}
    for tf in REQUIRED_TIMEFRAMES:
        hist = bars.get(tf) or []
        n = len(hist)
        last_close = (hist[-1].t + TF_SPAN[tf]) if hist and tf != "MN" else None
        ok_count = n >= MIN_BARS[tf]
        fresh, note = True, f"{n} closed bars"
        if tf == "D1":
            fresh = bool(hist) and abs((hist[-1].t - expected_d1_open).total_seconds()) <= 3 * 3600
            if not fresh:
                note = f"Last D1 bar opened {hist[-1].t.isoformat()[:16] if hist else '—'}, expected {expected_d1_open.isoformat()[:16]}"
        elif tf in FRESHNESS_TIMEFRAMES and last_close is not None:
            fresh = cutoff - last_close <= STALE_AFTER[tf]
            if not fresh:
                note = f"Last {tf} close {last_close.isoformat()[:16]} is stale versus the frozen close"
        if not ok_count:
            note = f"Only {n}/{MIN_BARS[tf]} closed bars"
        part = (1.0 if ok_count else n / MIN_BARS[tf]) * (1.0 if fresh else 0.25)
        score += weights[tf] * min(1.0, part)
        checks.append({"tf": "W" if tf == "W1" else tf, "bars": n, "last_close_at": last_close.isoformat() if last_close else None,
                       "complete": ok_count, "fresh": fresh, "note": note})
    d1_ok = next(c for c in checks if c["tf"] == "D1")
    status = "OK" if score >= 70 and d1_ok["fresh"] and d1_ok["complete"] else "INSUFFICIENT_DATA"
    return {"score": round(score, 1), "status": status, "checks": checks}


# ----- composition helpers -----


def _strength_label(symbol: str, st: dict | None) -> dict | None:
    if not st:
        return None
    diff = st["differential"]
    base, quote = symbol[:3], symbol[3:6]
    st = dict(st)
    st["label"] = (f"{base} stronger than {quote}" if diff > 0 else f"{quote} stronger than {base}") if diff else f"{base}/{quote} balanced"
    return st


def _mtf_rows(facts: dict, d: int) -> list[dict]:
    rows = []
    tit = facts.get("tit") or {}
    ct_tf = ((tit.get("countertrend") or {}).get("tf"))
    for tf in MTF_ROWS:
        v = facts["channels"].get(tf) or {}
        if not v.get("available"):
            rows.append({"tf": tf, "available": False})
            continue
        dk = v["direction"]["key"]
        sign = 1 if dk == "UPTREND" else -1 if dk == "DOWNTREND" else 0
        pos = v["position"] or 0
        if v["state"]["key"].startswith("BREAKOUT"):
            state = v["state"]["label"]
        elif tf == ct_tf or (d and sign == -d and tf in ("H8", "H1")):
            state = "Pullback"
        else:
            state = "Active" if v["validity"]["key"] == "VALID" else "Forming"
        zone = "Upper Zone" if pos >= 80 else "Upper Half" if pos >= 50 else "Lower Half" if pos >= 20 else "Lower Zone"
        rows.append({"tf": tf, "available": True, "state": state, "direction": {1: "Bullish", -1: "Bearish", 0: "Ranging"}[sign],
                     "dir": sign, "position": pos, "zone": zone, "lower": v["lower"], "upper": v["upper"], "validity": v["validity"]["key"],
                     "with_bias": bool(d) and sign == d})
    return rows


def _phase(facts: dict, regime: dict, d: int) -> dict:
    tv = facts.get("trend") or {}
    tit = facts.get("tit") or {}
    title = tv["state"]["label"] if tv else regime["label"]
    sub = None
    if tit.get("countertrend"):
        ct = tit["countertrend"]
        edge = "lower" if (tit["parent"]["direction"] == "UPTREND") else "upper"
        sub = f"{ct['tf']} countertrend {ct['maturity']}% mature, nearing {edge} boundary" if ct["maturity"] >= 50 else f"{ct['tf']} countertrend {ct['phase'].lower()}"
    elif tv and tv.get("geometry"):
        sub = f"{tv['geometry']['pullback']['label']} ({tv['geometry']['depth_pct']:.0f}% of the {tv['analysis_tf']} leg)"
    return {"title": title, "subtitle": sub or regime["reason"]}


def _next_move(d: int, family: str, erz: dict, tg: list[dict], dp: int) -> dict:
    zone = f"{_f(tg[0]['price'], dp)} – {_f(tg[1]['price'], dp)}"
    if d == 0:
        return {"label": "Range rotation", "path": f"{erz['label']} ↔ {_f(tg[0]['price'], dp)}", "target_zone": zone}
    word = "Upside" if d == 1 else "Downside"
    label = f"{word} {'reversal' if family == 'REV' else 'breakout' if family == 'BRK' else 'continuation'}"
    path = f"{_f(tg[0]['price'], dp)} → {_f(tg[1]['price'], dp)}"
    if not erz["price_inside"]:
        label = f"Pullback then {label.lower()}"
    return {"label": label, "path": path, "target_zone": zone}


def _status(d: int, erz: dict, facts: dict, dp: int) -> dict:
    word = "bullish" if d == 1 else "bearish"
    if d == 0:
        return {"key": "RANGE_WATCH", "title": "Watching range boundaries", "detail": f"Rotation expected inside the range; reaction zone {erz['label']}."}
    if erz["price_inside"]:
        return {"key": "AT_ERZ", "title": f"Waiting for H1 {word} confirmation",
                "detail": f"Price at reaction zone. Monitoring for {word} CHoCH → BOS → Retest."}
    if (erz["distance_atr"] or 0) <= 0.6:
        return {"key": "NEAR_ERZ", "title": "Approaching reaction zone", "detail": f"Price {erz['distance_atr']:.2f} ATR from the ERZ {erz['label']}."}
    return {"key": "EXTENDED", "title": "Waiting for pullback", "detail": f"Price extended {erz['distance_atr']:.2f} ATR from the ERZ {erz['label']}."}


def _conditions(d: int, erz: dict, inv: dict, tg: list[dict], alt_tg: list[dict] | None, dp: int) -> list[dict]:
    if d == 0:
        return []
    up = d == 1
    word = "Bullish" if up else "Bearish"
    above, below = ("above", "below") if up else ("below", "above")
    rows = [
        (f"Price {above} {_f(erz['lo'] if up else erz['hi'], dp)}", True, False, None),
        (f"H1 {word} CHoCH", True, False, None),
        (f"H1 {word} BOS", True, False, None),
        (f"Retest of {erz['label']}", True, False, None),
        (f"{inv['label']} holds", True, False, True),
        (f"Close {below} {_f(inv['price'], dp)}", False, True, False),
        (f"Break {above} {_f(tg[0]['price'], dp)}", True, False, False),
    ]
    if alt_tg:
        rows.append((f"Break {below} {_f(alt_tg[0]['price'], dp)}", False, True, False))
    return [{"condition": c, "primary": p, "alternative": a, "range": r} for c, p, a, r in rows]


def _summary(facts: dict, d: int, evidence: list[dict]) -> dict:
    """Smart Analysis Summary: one line per evidence item, flagged as supporting / caution / against the primary bias."""
    groups = {"technical": ("TREND", "SUPERTREND", "MOMENTUM", "VOLATILITY", "STRENGTH"), "structure": ("STRUCTURE", "BOS", "FRACTAL"),
              "channel": ("CHANNEL", "TIT"), "context": ("RANGE", "STRENGTH", "STRUCTURE")}
    out = {}
    for g, keys in groups.items():
        lines = []
        for e in sorted((e for e in evidence if e["source_key"] in keys), key=lambda e: -e["weight"])[:7]:
            if e["role"] == "range":
                tone = "warn" if d else "ok"
            elif e["sign"] == 0:
                tone = "warn"
            else:
                tone = "ok" if e["sign"] == d else "fail"
            lines.append({"tone": tone, "text": f"{e['title']} — {e['detail']}", "evidence_id": e["id"]})
        out[g] = lines
    return out


def _system_action(qualified: bool, erz: dict, d: int) -> dict:
    if not qualified:
        return {"key": "IGNORE", "label": "Ignore", "detail": "Not a qualified opportunity today."}
    if erz["price_inside"]:
        return {"key": "PREPARE", "label": "Prepare", "detail": "Price in the reaction zone — awaiting lower-timeframe confirmation before handoff to the Opportunity Engine."}
    return {"key": "WATCH", "label": "Watch", "detail": "Plan published — waiting for price to reach the reaction zone."}


# ----- pipeline -----


def build_outlook(symbol: str, a: dict, price: float, anchor: datetime, strength: dict | None, quality: dict,
                  calibration: dict | None, s: OutlookSettings, *, analysis_date: str, snapshot_id: str) -> dict:
    dp = digits_for(symbol)
    facts = aggregate(symbol, a, price, anchor, _strength_label(symbol, strength))
    if facts.get("fractals"):
        facts["fractals"]["marks"] = {tf: frac.fractal_marks(a["fractal"], tf, 24) for tf in frac.FRACTAL_TIMEFRAMES}
    evidence = facts["evidence"]
    b = rz.biases(evidence)
    regime = rz.classify_regime(facts, b, quality["score"], s)
    scored = rz.score(facts, b, s)
    hyps = scored["hypotheses"]
    raw_dirs = rz.direction_probabilities(hyps)
    lead = max(raw_dirs, key=lambda k: raw_dirs[k])
    dirs, cal = rz.calibrate(raw_dirs, lead, calibration, s)
    sc = rz.select_scenarios(hyps, dirs)
    primary, alt, rng = sc["primary"], sc["alternative"], sc["range"]
    d = primary["dir"]

    levels = pl.key_levels(facts)
    erz = pl.reaction_zone(facts, levels, d, s)
    plan_dir = d if d else 1
    tg = pl.targets(facts, levels, plan_dir, erz["hi"] if plan_dir == 1 else erz["lo"], s)
    inv = pl.invalidation(facts, levels, plan_dir, erz, s)
    if d == 0:
        rc = (facts.get("range") or {}).get("core") or {}
        lo = rc.get("range_low") if rc.get("ranging") else inv["price"]
        hi = rc.get("range_high") if rc.get("ranging") else tg[0]["price"]
        tg = [{**tg[0], "price": hi, "label": "Range high" if rc.get("ranging") else tg[0]["label"]},
              {**tg[1], "price": (lo + hi) / 2, "label": "Range midpoint"}]
    entry = erz["mid"]
    risk = abs(entry - inv["price"])
    rr = round(abs(tg[0]["price"] - entry) / risk, 2) if risk else None

    alt_dir = alt["dir"] if alt and alt["dir"] else -plan_dir
    alt_tg = pl.targets(facts, levels, alt_dir, inv["price"], s)
    expected = pl.path(anchor, price, ([] if erz["price_inside"] else [erz["mid"]]) + [tg[0]["price"], tg[1]["price"]], facts["atr"])
    alt_path = pl.path(anchor, price, [inv["price"], alt_tg[0]["price"], alt_tg[1]["price"]], facts["atr"])
    plan = {"direction": d, "erz": erz, "targets": tg, "invalidation": inv, "path": expected, "alt_path": alt_path}

    margin = dirs[d] - max(p for k, p in dirs.items() if k != d)
    mtf = _mtf_rows(facts, d)
    with_bias = [r for r in mtf if r.get("available")]
    aligned = 100 * sum(1 for r in with_bias if r["with_bias"]) / len(with_bias) if with_bias and d else 0.0
    opp = pl.opportunity(dirs[d], margin, rr, aligned, erz["distance_atr"], quality["score"], d, s)
    ann = pl.annotations(facts, channel_lines(a), plan, levels)
    alt_word = WORD[alt_dir]

    scenario = lambda h, p, label, extra: {  # noqa: E731
        "key": h["key"] if h else None, "label": label, "direction": WORD[h["dir"]] if h else None, "probability": round(p, 1), **extra,
        "evidence_for": (h or {}).get("evidence_for", []), "evidence_against": (h or {}).get("evidence_against", []),
    }
    primary_label = primary["label"]
    trigger = next((e["title"] for e in evidence if e["sign"] == d and e["role"] in ("reversal", "reaction")), None)
    primary_s = scenario(primary, dirs[d], primary_label, {
        "summary": (f"Price respects the {erz['basis'].split(' + ')[0].lower()}. Expect H1 {WORD[plan_dir].lower()} CHoCH and BOS, "
                    f"followed by retest and continuation to {_f(tg[0]['price'], dp)} – {_f(tg[1]['price'], dp)}.") if d else
                   f"Rotation inside {_f(inv['price'], dp)} – {_f(tg[0]['price'], dp)} while higher timeframes stay undecided.",
        "key_trigger": f"H1 {WORD[plan_dir].lower()} CHoCH & BOS" if d else "Rejection at range boundary",
        "trigger_evidence": trigger,
        "targets": tg, "invalidation": inv, "erz": erz,
        "sequence": pl.confirmation_sequence(plan_dir, erz, inv, tg, facts, dp, primary["family"]),
        "path": expected,
    })
    alt_inv = {"price": erz["hi"] if alt_dir == -1 else erz["lo"], "label": f"Holds {'above' if alt_dir == -1 else 'below'} {_f(erz['lo'] if alt_dir == -1 else erz['hi'], dp)}"}
    alternative_s = scenario(alt, dirs.get(alt_dir, 0.0), alt["label"] if alt else f"{alt_word} Breakdown", {
        "summary": f"Sustained close {'below' if alt_dir == -1 else 'above'} {_f(inv['price'], dp)} invalidates the {WORD[plan_dir].lower()} view and targets "
                   f"{_f(alt_tg[0]['price'], dp)}.",
        "key_trigger": f"Close {'below' if alt_dir == -1 else 'above'} {_f(inv['price'], dp)}",
        "targets": alt_tg, "invalidation": alt_inv,
        "sequence": pl.alternative_sequence(alt_dir, inv, erz, alt_tg, dp),
        "path": alt_path,
    })
    r_lo, r_hi = sorted((inv["price"], tg[0]["price"]))
    range_s = scenario(rng, dirs[0], "Consolidation / Range", {
        "summary": f"Continued ranging within {_f(r_lo, dp)} – {_f(r_hi, dp)} while awaiting higher timeframe confirmation.",
        "range": [r_lo, r_hi], "invalidation": {"price": None, "label": "Break and close outside range"},
        "path": [[anchor.isoformat(), price], [(anchor + timedelta(days=1)).isoformat(), (r_lo + r_hi) / 2],
                 [(anchor + timedelta(days=2)).isoformat(), r_hi - 0.15 * (r_hi - r_lo)], [(anchor + timedelta(days=3)).isoformat(), r_lo + 0.2 * (r_hi - r_lo)]],
    })

    drivers = sorted((c for c in primary.get("evidence_for", [])), key=lambda c: -c["vote"])[:4]
    by_id = {e["id"]: e for e in evidence}
    conclusion = (f"{WORD[d]} bias remains valid while price holds {'above' if d == 1 else 'below'} {_f(inv['price'], dp)}. "
                  f"Monitor H1 for {WORD[d].lower()} CHoCH and BOS. Reaction expected at the ERZ {erz['label']} during the Asian session."
                  if d else f"No directional edge: {regime['reason'].lower()}. Expect rotation between {_f(r_lo, dp)} and {_f(r_hi, dp)}.")
    marks = sorted(
        [{"type": "Resistance" if t["price"] > price else "Support", "price": t["price"], "label": t["label"], "description": f"{t['source']} ({t['tf']})",
          "tone": "res" if t["price"] > price else "sup"} for t in levels if t["importance"] == "High" and abs(t["distance_atr"] or 99) <= 3][:4]
        + [{"type": f"Target {i + 1}", "price": t["price"], "label": t["label"], "description": "Final target if continuation" if i else "First objective", "tone": "target"}
           for i, t in enumerate(tg)]
        + [{"type": "ERZ", "price": erz["mid"], "lo": erz["lo"], "hi": erz["hi"], "label": "Expected Reaction Zone", "description": erz["basis"], "tone": "erz"},
           {"type": "Invalidation", "price": inv["price"], "label": "Invalidation", "description": f"Close {'below' if plan_dir == 1 else 'above'} ({inv['label']})", "tone": "inv"}],
        key=lambda m: -m["price"])
    key_table = [
        {"type": "Resistance" if lv["side"] == "resistance" else "Support", "price": lv["price"], "label": lv["label"], "tf": lv["tf"],
         "source": lv["source"], "importance": lv["importance"], "distance_atr": lv["distance_atr"], "liquidity": lv["liquidity"]}
        for lv in levels if lv["kind"] != "mid"
    ]
    zones = [
        {"zone": "Target Zone 2", "from": tg[1]["price"], "to": tg[1]["price"] + plan_dir * 0.25 * facts["atr"], "type": "Resistance" if plan_dir == 1 else "Support"},
        {"zone": "Target Zone 1", "from": tg[0]["price"], "to": tg[1]["price"], "type": "Resistance" if plan_dir == 1 else "Support"},
        {"zone": "Reaction Zone (ERZ)", "from": erz["lo"], "to": erz["hi"], "type": "Support" if plan_dir == 1 else "Resistance"},
        {"zone": "Invalidation Zone", "from": inv["price"] - plan_dir * 0.2 * facts["atr"], "to": inv["price"], "type": "Support" if plan_dir == 1 else "Resistance"},
    ]
    for z in zones:
        lo, hi = sorted((z["from"], z["to"]))
        z.update({"from": lo, "to": hi, "width_atr": round((hi - lo) / facts["atr"], 2) if facts["atr"] else None,
                  "strength": "Strong" if z["zone"] != "Target Zone 2" else "Moderate",
                  "status": "Active" if not (lo <= price <= hi) else "Testing"})

    return {
        "analysis_date": analysis_date,
        "snapshot_id": snapshot_id,
        "symbol": symbol,
        "digits": dp,
        "status": "PUBLISHED",
        "price": price,
        "anchor": anchor.isoformat(),
        "engine_version": ENGINE_VERSION,
        "regime": regime,
        "htf_bias": {"key": WORD[b["htf_dir"]].upper(), "label": WORD[b["htf_dir"]] if b["htf_dir"] else "Neutral", "score": b["htf"]},
        "biases": b,
        "expected_direction": WORD[d].upper(),
        "expected_next_move": _next_move(d, primary["family"], erz, tg, dp),
        "phase": _phase(facts, regime, d),
        "current_status": _status(d, erz, facts, dp),
        "timeframe_focus": ["H8", "H1", "M30"] if d else ["D1", "H8", "H1"],
        "primary_scenario": primary_s,
        "alternative_scenario": alternative_s,
        "range_scenario": range_s,
        "scenario_conditions": _conditions(d, erz, inv, tg, alt_tg, dp),
        "hypotheses": hyps,
        "confidence": {"primary": round(dirs[d], 1), "bullish": round(dirs[1], 1), "bearish": round(dirs[-1], 1), "range": round(dirs[0], 1),
                       "raw": {k: round(v, 1) for k, v in (("bullish", raw_dirs[1]), ("bearish", raw_dirs[-1]), ("range", raw_dirs[0]))},
                       "calibration": cal, "margin": round(margin, 1)},
        "uncertainty": rz.uncertainty(dirs),
        "evidence": evidence,
        "evidence_for": primary.get("evidence_for", []),
        "evidence_against": primary.get("evidence_against", []),
        "key_drivers": [{"id": c["id"], "title": by_id[c["id"]]["title"], "detail": by_id[c["id"]]["detail"], "source": c["source"], "tf": c["tf"]} for c in drivers],
        "erz": erz,
        "targets": tg,
        "invalidation": inv,
        "reward_risk": rr,
        "supports": [lv for lv in key_table if lv["type"] == "Support"][:8],
        "resistances": [lv for lv in key_table if lv["type"] == "Resistance"][-8:][::-1],
        "liquidity": [lv for lv in key_table if lv["liquidity"]],
        "key_levels": key_table,
        "key_zones": zones,
        "mark_points": marks,
        "channels": mtf,
        "fractals": {"hierarchy": (facts.get("fractals") or {}).get("hierarchy", []), "clusters": (facts.get("fractals") or {}).get("clusters")},
        "bos_choch": {tf: {k: v for k, v in se.items() if k != "all"} for tf, se in facts["structure_events"].items()},
        "tit": {k: (facts.get("tit") or {}).get(k) for k in ("state", "parent", "countertrend", "setup", "quality", "summary", "layers")},
        "trend": None if not facts.get("trend") else {k: facts["trend"].get(k) for k in ("direction", "state", "strength", "setup", "geometry", "structure_sequence", "analysis_tf")},
        "strength": facts.get("strength"),
        "supertrend": facts.get("supertrend"),
        "volatility": facts.get("volatility"),
        "range": facts.get("range"),
        "confirmation_sequence": primary_s["sequence"],
        "expected_path": expected,
        "session_plan": pl.session_plan(anchor, d, erz, tg, inv, dp, regime["key"]),
        "smart_summary": _summary(facts, d, evidence),
        "conclusion": conclusion,
        "opportunity": opp,
        "opportunity_score": opp["score"],
        "qualified": opp["qualified"],
        "system_action": _system_action(opp["qualified"], erz, d),
        "data_quality": quality,
        "chart_annotations": ann,
        "handoff": "Prediction is not trade authorisation — Opportunity, Confirmation and Risk engines decide execution.",
    }


def insufficient(symbol: str, quality: dict, analysis_date: str, snapshot_id: str, anchor: datetime, reason: str, status: str = "INSUFFICIENT_DATA") -> dict:
    return {"analysis_date": analysis_date, "snapshot_id": snapshot_id, "symbol": symbol, "digits": digits_for(symbol), "status": status,
            "anchor": anchor.isoformat(), "engine_version": ENGINE_VERSION, "qualified": False, "opportunity_score": None, "reason": reason,
            "data_quality": quality}


def channel_lines(a: dict) -> dict:
    return {tf: (a["channel"].get(tf) or {}).get("lines") for tf in chan.CHANNEL_TIMEFRAMES}
