"""RegimeClassifier, HypothesisEngine and ScenarioScoringEngine.

Every hypothesis score is the sum of explicit per-evidence votes, so each probability can be traced back to the
engine facts that produced it. Probabilities come from a tempered softmax and are then calibrated against the
measured hit rate of past outlooks (Learning/CalibrationEngine) — never hard-coded."""
from __future__ import annotations

import math

from .config import OutlookSettings

HYPOTHESES = {
    "BULL_CONT": {"dir": 1, "family": "CONT", "label": "Bullish Continuation"},
    "BEAR_CONT": {"dir": -1, "family": "CONT", "label": "Bearish Continuation"},
    "BULL_REV": {"dir": 1, "family": "REV", "label": "Bullish Reversal"},
    "BEAR_REV": {"dir": -1, "family": "REV", "label": "Bearish Reversal"},
    "BREAKOUT_UP": {"dir": 1, "family": "BRK", "label": "Bullish Breakout"},
    "BREAKOUT_DOWN": {"dir": -1, "family": "BRK", "label": "Bearish Breakdown"},
    "RANGE": {"dir": 0, "family": "RANGE", "label": "Consolidation / Range"},
}
PRIOR = {"CONT": 0.35, "REV": -0.3, "BRK": -0.15, "RANGE": 0.0}
# Vote multipliers: role → (same-direction by family, opposite-direction by family, range hypothesis).
VOTES = {
    "trend": ({"CONT": 1.0, "REV": 0.7, "BRK": 0.6}, {"CONT": -0.6, "REV": -0.6, "BRK": -0.5}, -0.35),
    "reaction": ({"CONT": 1.0, "REV": 0.8, "BRK": 0.2}, {"CONT": -0.4, "REV": -0.4, "BRK": -0.1}, 0.3),
    "reversal": ({"CONT": 0.3, "REV": 1.2, "BRK": 0.6}, {"CONT": -0.8, "REV": -0.5, "BRK": -0.3}, 0.1),
    "breakout": ({"CONT": 0.5, "REV": 0.6, "BRK": 1.2}, {"CONT": -0.6, "REV": -0.6, "BRK": -0.6}, -0.6),
    "range": ({}, {}, 1.0),
}
RANGE_AGAINST = {"CONT": -0.4, "REV": -0.2, "BRK": -0.3}
HTF_TFS = ("Y", "HY", "Q", "MN", "W")
MTF_TFS = ("D1", "AVG")


def _bias(items: list[dict], tfs: tuple[str, ...] | None = None) -> float:
    pool = [e for e in items if e["role"] == "trend" and (tfs is None or e["tf"] in tfs)]
    total = sum(e["weight"] for e in pool)
    return sum(e["sign"] * e["weight"] for e in pool) / total if total else 0.0


def biases(items: list[dict]) -> dict:
    htf, mtf = _bias(items, HTF_TFS), _bias(items, MTF_TFS + ("H8",))
    ltf, overall = _bias(items, ("H8", "H1")), _bias(items)
    return {"htf": round(htf, 3), "mtf": round(mtf, 3), "ltf": round(ltf, 3), "overall": round(overall, 3),
            "htf_dir": 1 if htf >= 0.3 else -1 if htf <= -0.3 else 0,
            "mtf_dir": 1 if mtf >= 0.3 else -1 if mtf <= -0.3 else 0}


def classify_regime(facts: dict, b: dict, data_quality: float, s: OutlookSettings) -> dict:
    """bullish / bearish / ranging / transitional / uncertain — with the reason that decided it."""
    items = facts["evidence"]
    ranging = bool(((facts.get("range") or {}).get("core") or {}).get("ranging"))
    counter_choch = any(e["source_key"] == "BOS" and e["role"] == "reversal" and e["tf"] in ("W", "D1") and b["htf_dir"]
                        and e["sign"] == -b["htf_dir"] for e in items)
    if data_quality < s.min_data_quality:
        key, why = "UNCERTAIN", f"Data quality {data_quality:.0f}% below the {s.min_data_quality:.0f}% threshold"
    elif b["htf_dir"] and b["mtf_dir"] and b["htf_dir"] == -b["mtf_dir"]:
        key, why = "TRANSITIONAL", "Higher and daily timeframes point in opposite directions"
    elif counter_choch:
        key, why = "TRANSITIONAL", "Counter-trend CHoCH on a higher timeframe"
    elif ranging and abs(b["overall"]) < 0.35:
        key, why = "RANGING", "Validated weekly range with no dominant directional evidence"
    elif b["overall"] >= 0.3:
        key, why = "BULLISH", f"Directional evidence {b['overall'] * 100:+.0f}% bullish across timeframes"
    elif b["overall"] <= -0.3:
        key, why = "BEARISH", f"Directional evidence {b['overall'] * 100:+.0f}% bearish across timeframes"
    elif abs(b["overall"]) < 0.15:
        has_range = any(e["role"] == "range" for e in items)
        key, why = ("RANGING", "Balanced directional evidence with range characteristics") if has_range else (
            "UNCERTAIN", "Directional evidence balanced and no range structure")
    else:
        key, why = "TRANSITIONAL", "Moderate directional evidence without timeframe agreement"
    return {"key": key, "label": key.title(), "reason": why}


def applicable(b: dict, facts: dict) -> dict[str, str | None]:
    """Hypotheses that make structural sense here (None) or the reason they are excluded."""
    htf, mtf = b["htf_dir"], b["mtf_dir"]
    edge = (facts.get("range") or {}).get("band") or {}
    breakout_live = {e["sign"] for e in facts["evidence"] if e["role"] == "breakout"}
    out: dict[str, str | None] = {}
    for key, h in HYPOTHESES.items():
        d, fam = h["dir"], h["family"]
        if fam == "RANGE":
            out[key] = None
        elif fam == "CONT":
            ok = htf == d or (htf == 0 and mtf == d)
            out[key] = None if ok else "No prevailing trend in this direction to continue"
        elif fam == "REV":
            out[key] = None if htf == -d else "Requires an opposing higher-timeframe trend to reverse"
        else:
            ok = htf in (0, -d) or d in breakout_live or edge.get("key") in ("UPPER_EXTREME", "LOWER_EXTREME", "ABOVE_RANGE", "BELOW_RANGE")
            out[key] = None if ok else "With-trend breaks are scored as continuation"
    return out


def _vote(h: dict, e: dict) -> float:
    fam, d = h["family"], h["dir"]
    same, opp, rng = VOTES[e["role"]]
    w = e["weight"]
    if fam == "RANGE":
        return w * rng
    if e["role"] == "range":
        return w * RANGE_AGAINST[fam]
    if e["sign"] == 0:
        return 0.0
    return w * (same[fam] if e["sign"] == d else opp[fam])


def score(facts: dict, b: dict, s: OutlookSettings) -> dict:
    items = facts["evidence"]
    gate = applicable(b, facts)
    total_w = sum(e["weight"] for e in items) or 1.0
    raw, contributions = {}, {}
    for key, h in HYPOTHESES.items():
        if gate[key]:
            continue
        votes = [(e["id"], round(_vote(h, e), 3)) for e in items]
        contributions[key] = [v for v in votes if v[1]]
        raw[key] = PRIOR[h["family"]] + 3.0 * sum(v for _, v in votes) / total_w
    m = max(raw.values())
    exp = {k: math.exp((v - m) / s.softmax_temperature) for k, v in raw.items()}
    z = sum(exp.values())
    n = len(exp)
    prob = {k: 100 * (0.85 * exp[k] / z + 0.15 / n) for k in exp}
    hyps = []
    for key, h in HYPOTHESES.items():
        entry = {"key": key, **h, "applicable": gate[key] is None, "excluded_reason": gate[key]}
        if gate[key] is None:
            by_id = {e["id"]: e for e in items}
            contrib = sorted(contributions[key], key=lambda v: -abs(v[1]))
            entry.update(
                score=round(raw[key], 3),
                probability=round(prob[key], 1),
                evidence_for=[{"id": i, "vote": v, "title": by_id[i]["title"], "source": by_id[i]["source"], "tf": by_id[i]["tf"]}
                              for i, v in contrib if v > 0][:8],
                evidence_against=[{"id": i, "vote": v, "title": by_id[i]["title"], "source": by_id[i]["source"], "tf": by_id[i]["tf"]}
                                  for i, v in contrib if v < 0][:8],
            )
        hyps.append(entry)
    return {"hypotheses": hyps, "biases": b}


def direction_probabilities(hyps: list[dict]) -> dict[int, float]:
    out = {1: 0.0, -1: 0.0, 0: 0.0}
    for h in hyps:
        if h["applicable"]:
            out[h["dir"]] += h["probability"]
    return out


def calibrate(dirs: dict[int, float], primary_dir: int, table: dict | None, s: OutlookSettings) -> tuple[dict[int, float], dict]:
    """Shrink the primary probability toward the measured hit rate of its confidence bucket (Beta smoothing)."""
    raw = dirs[primary_dir]
    bucket = None if table is None else table.get(bucket_of(raw))
    info = {"method": "bucket-beta", "raw": round(raw, 1), "bucket": bucket_of(raw), "samples": 0, "hit_rate": None, "applied": False}
    if not bucket or not bucket["n"]:
        return dirs, info
    k = s.calibration_strength
    cal = (bucket["hits"] * 100 + k * raw) / (bucket["n"] + k)
    cal = min(95.0, max(5.0, cal))
    rest = 100 - raw
    out = {primary_dir: cal}
    for d, p in dirs.items():
        if d != primary_dir:
            out[d] = (p / rest * (100 - cal)) if rest else (100 - cal) / 2
    info.update(samples=bucket["n"], hit_rate=round(100 * bucket["hits"] / bucket["n"], 1), applied=True, calibrated=round(cal, 1))
    return out, info


def bucket_of(p: float) -> str:
    if p < 40:
        return "<40"
    if p >= 80:
        return ">80"
    lo = int(p // 10 * 10)
    return f"{lo}-{lo + 10}"


def select_scenarios(hyps: list[dict], dirs: dict[int, float]) -> dict:
    """Primary = strongest hypothesis; Alternative = strongest of the opposing direction; Range = consolidation."""
    live = [h for h in hyps if h["applicable"]]
    primary = max(live, key=lambda h: (dirs[h["dir"]], h["probability"]))
    if primary["dir"] == 0:
        directional = [h for h in live if h["dir"] != 0]
        alt = max(directional, key=lambda h: h["probability"]) if directional else None
    else:
        opp = [h for h in live if h["dir"] == -primary["dir"]]
        alt = max(opp, key=lambda h: h["probability"]) if opp else None
    rng = next(h for h in live if h["key"] == "RANGE")
    return {"primary": primary, "alternative": alt, "range": rng}


def uncertainty(dirs: dict[int, float]) -> float:
    ps = [p / 100 for p in dirs.values() if p > 0]
    h = -sum(p * math.log(p) for p in ps)
    return round(100 * h / math.log(3), 1)
