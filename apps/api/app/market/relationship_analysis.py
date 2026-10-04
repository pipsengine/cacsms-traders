"""Relationship Analysis: structural interpretation of one pair's strength differential.

Builds on ``pair_relationships`` (current differentials) and persisted strength history. Output is a
description of what the differential is doing — never a trade direction or signal.
"""
from __future__ import annotations

from datetime import datetime

from .pair_relationships import Scores, classify_relationship, differential, pair_relationship, split_pair
from .strength_history import downsample
from .strength_intel_config import HTF, LTF, ANALYSIS_TIMEFRAMES, RelationshipThresholds, relationship_thresholds

Point = tuple[datetime, float]

STATE_LABELS = {
    "EXPANDING_DIVERGENCE": "Expanding divergence",
    "CONTRACTING_DIVERGENCE": "Contracting divergence",
    "CONVERGENCE": "Convergence",
    "EQUILIBRIUM": "Equilibrium",
    "REVERSAL": "Relationship reversal",
    "PERSISTENT_DIVERGENCE": "Persistent divergence",
    "STABLE_DIVERGENCE": "Stable divergence",
    "DIVERGENCE": "Divergence (awaiting history)",
}


def _sign(v: float, eps: float = 0.0) -> int:
    return 1 if v > eps else -1 if v < -eps else 0


def diff_series(base: list[Point], quote: list[Point]) -> list[Point]:
    """Differential at snapshot times where both currencies were persisted together."""
    q = dict(quote)
    return [(at, round(v - q[at], 1)) for at, v in base if at in q]


def persistence_ratio(series: list[Point], current: float, eps: float) -> float | None:
    """Share of history points whose differential points the same way as the current one."""
    if len(series) < 3:
        return None
    s = _sign(current, eps)
    if s == 0:
        return None
    return round(sum(1 for _, d in series if _sign(d, eps) == s) / len(series), 3)


def classify_state(diff: float, prev: float | None, persistence: float | None, t: RelationshipThresholds) -> dict:
    band = t.moderate
    if prev is not None and prev * diff < 0 and max(abs(prev), abs(diff)) >= band:
        key = "REVERSAL"
    elif abs(diff) < band:
        key = "CONVERGENCE" if prev is not None and abs(prev) >= band else "EQUILIBRIUM"
    elif prev is None:
        key = "PERSISTENT_DIVERGENCE" if (persistence or 0) >= t.persistent_ratio else "DIVERGENCE"
    elif abs(diff) - abs(prev) >= t.dynamics_epsilon:
        key = "EXPANDING_DIVERGENCE"
    elif abs(prev) - abs(diff) >= t.dynamics_epsilon:
        key = "CONVERGENCE" if abs(diff) < t.divergence else "CONTRACTING_DIVERGENCE"
    elif (persistence or 0) >= t.persistent_ratio:
        key = "PERSISTENT_DIVERGENCE"
    else:
        key = "STABLE_DIVERGENCE"
    return {"key": key, "label": STATE_LABELS[key]}


def _bias(diffs: list[float], eps: float) -> int:
    return _sign(sum(diffs) / len(diffs), eps) if diffs else 0


def htf_ltf(by_tf: dict[str, float], t: RelationshipThresholds) -> dict:
    h = _bias([by_tf[tf] for tf in HTF if tf in by_tf], t.alignment_epsilon)
    l = _bias([by_tf[tf] for tf in LTF if tf in by_tf], t.alignment_epsilon)
    if h and l:
        key, label = ("AGREE", "HTF and LTF agree") if h == l else ("DISAGREE", "HTF and LTF disagree")
    else:
        key, label = "INCONCLUSIVE", "Inconclusive"
    side = {1: "BASE", -1: "QUOTE", 0: "NONE"}
    return {"key": key, "label": label, "htf": side[h], "ltf": side[l]}


def currency_direction(current: float | None, previous: float | None, eps: float) -> dict:
    if current is None or previous is None:
        return {"key": "NO_HISTORY", "label": "Awaiting history", "change": None}
    change = round(current - previous, 1)
    if change >= eps:
        return {"key": "STRENGTHENING", "label": "Strengthening", "change": change}
    if change <= -eps:
        return {"key": "WEAKENING", "label": "Weakening", "change": change}
    return {"key": "STABLE", "label": "Stable", "change": change}


def trajectory(series: list[Point], current: float, t: RelationshipThresholds) -> dict:
    """Least-squares slope of the composite differential, expressed relative to its current side."""
    if len(series) < 3:
        return {"key": "NO_HISTORY", "label": "Awaiting history", "slope_per_hour": None, "window_change": None}
    t0 = series[0][0]
    xs = [(at - t0).total_seconds() / 3600.0 for at, _ in series]
    ys = [d for _, d in series]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    slope = 0.0 if var == 0 else sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var
    window_change = slope * (xs[-1] - xs[0])
    side = _sign(current, t.alignment_epsilon) or _sign(window_change)
    rel = window_change * side
    if rel >= t.dynamics_epsilon:
        key, label = "WIDENING", "Widening"
    elif rel <= -t.dynamics_epsilon:
        key, label = "NARROWING", "Narrowing"
    else:
        key, label = "FLAT", "Flat"
    return {"key": key, "label": label, "slope_per_hour": round(slope, 3), "window_change": round(window_change, 1)}


def current_run(series: list[Point], current: float, eps: float) -> dict:
    """When the differential last switched to its current side (within the loaded history)."""
    s = _sign(current, eps)
    if not series or s == 0:
        return {"since": None, "bounded_by_history": False, "last_reversal_at": None}
    since = series[-1][0]
    last_flip = None
    for at, d in reversed(series):
        ds = _sign(d, eps)
        if ds == -s:
            last_flip = at
            break
        if ds == s:
            since = at
    return {
        "since": since.isoformat(),
        "bounded_by_history": last_flip is None,
        "last_reversal_at": last_flip.isoformat() if last_flip else None,
    }


def persistence_label(ratio: float | None, t: RelationshipThresholds) -> dict:
    if ratio is None:
        return {"key": "NO_HISTORY", "label": "Awaiting history", "ratio": None}
    if ratio >= t.persistent_ratio:
        key, label = "PERSISTENT", "Persistent"
    elif ratio >= t.developing_ratio:
        key, label = "DEVELOPING", "Developing"
    else:
        key, label = "UNSTABLE", "Unstable"
    return {"key": key, "label": label, "ratio": ratio, "pct": round(ratio * 100.0, 1)}


def _side_name(pair_row: dict, side: str) -> str:
    return pair_row["base"] if side == "BASE" else pair_row["quote"] if side == "QUOTE" else "neither currency"


def format_age(minutes: float | None) -> str:
    if minutes is None:
        return "reference window"
    if minutes < 90:
        return f"{minutes:.0f} minutes"
    if minutes < 48 * 60:
        return f"{minutes / 60:.1f} hours"
    return f"{minutes / 1440:.1f} days"


def interpret(a: dict) -> list[str]:
    """Plain-language structural summary built only from computed fields (no trade language)."""
    p, s = a["relationship"], a["summary"]
    base, quote = p["base"], p["quote"]
    out: list[str] = []
    stronger, weaker = (base, quote) if p["differential"] >= 0 else (quote, base)
    sv = p["base_strength"] if stronger == base else p["quote_strength"]
    wv = p["quote_strength"] if stronger == base else p["base_strength"]
    if p["relationship"]["key"] == "BALANCED":
        out.append(
            f"{base} ({p['base_strength']:.1f}) and {quote} ({p['quote_strength']:.1f}) are near equilibrium — "
            f"the composite differential is {p['differential']:+.1f} points."
        )
    else:
        out.append(
            f"{stronger} ({sv:.1f}) is stronger than {weaker} ({wv:.1f}) by {p['abs_differential']:.1f} points "
            f"on the composite average — a {p['relationship']['label'].lower()} relationship."
        )
    st = s["state"]["key"]
    dyn = p["dynamics"]
    window = format_age(a["meta"]["reference_age_minutes"])
    if st == "REVERSAL":
        out.append(f"The differential has changed side over the last {window} (relationship reversal).")
    elif dyn["change"] is not None and st in ("EXPANDING_DIVERGENCE", "CONTRACTING_DIVERGENCE", "CONVERGENCE"):
        verb = "widened" if st == "EXPANDING_DIVERGENCE" else "narrowed"
        out.append(f"Over the last {window} it has {verb} by {abs(dyn['change']):.1f} points ({s['state']['label'].lower()}).")
    elif st == "PERSISTENT_DIVERGENCE":
        out.append("The gap is holding steady and has kept the same side for most of the analysed history (persistent divergence).")
    elif dyn["key"] == "NO_HISTORY":
        out.append("Not enough persisted history yet to measure how the differential is changing.")
    bd, qd = s["base_direction"], s["quote_direction"]
    if bd["key"] != "NO_HISTORY" and qd["key"] != "NO_HISTORY":
        out.append(f"{base} is {bd['label'].lower()} ({bd['change']:+.1f}) while {quote} is {qd['label'].lower()} ({qd['change']:+.1f}).")
    al, hl = s["alignment"], s["htf_ltf"]
    if al["total"]:
        side = _side_name(p, al["direction"])
        out.append(f"{al['aligned']} of {al['total']} timeframes ({al['pct']:.0f}%) favour {side}, matching the composite direction.")
    if hl["key"] == "DISAGREE":
        out.append(f"Higher timeframes favour {_side_name(p, hl['htf'])} while lower timeframes favour {_side_name(p, hl['ltf'])}.")
    elif hl["key"] == "AGREE":
        out.append(f"Higher and lower timeframes both favour {_side_name(p, hl['htf'])}.")
    per, tr = s["persistence"], s["trajectory"]
    if per["key"] != "NO_HISTORY":
        out.append(
            f"Across the selected period the differential kept its current side {per['pct']:.0f}% of the time "
            f"({per['label'].lower()}), and its trajectory is {tr['label'].lower()}."
        )
    out.append("Structural description only — Strength Intelligence does not issue trade signals.")
    return out


def _chart(series: list[Point]) -> list[dict]:
    keep = set(downsample([at for at, _ in series]))
    return [{"at": at.isoformat(), "differential": d} for at, d in series if at in keep]


def analyze_pair(
    pair: str,
    scores: Scores,
    reference: Scores | None,
    history_by_tf: dict[str, list[Point]],
    *,
    lookback_minutes: float,
    reference_age_minutes: float | None = None,
) -> dict | None:
    """``history_by_tf`` maps AVG + matrix timeframes to persisted differential series for the period."""
    t = relationship_thresholds()
    row = pair_relationship(pair, scores, reference, t)
    if row is None:
        return None
    base, quote = split_pair(pair)
    matrix = []
    for tf in ANALYSIS_TIMEFRAMES:
        d = differential(scores, base, quote, tf)
        if d is None:
            matrix.append({"timeframe": tf, "available": False})
            continue
        prev = differential(reference, base, quote, tf) if reference else None
        per = persistence_ratio(history_by_tf.get(tf, []), d, t.alignment_epsilon)
        matrix.append(
            {
                "timeframe": tf,
                "available": True,
                "group": "HTF" if tf in HTF else "LTF",
                "base": scores[base][tf],
                "quote": scores[quote][tf],
                "differential": d,
                "previous": prev,
                "change": None if prev is None else round(d - prev, 1),
                "relationship": classify_relationship(abs(d), t),
                "state": classify_state(d, prev, per, t),
                "persistence": per,
                "favours": {1: "BASE", -1: "QUOTE", 0: "NONE"}[_sign(d, t.alignment_epsilon)],
            }
        )
    composite_hist = history_by_tf.get("AVG", [])
    per = persistence_ratio(composite_hist, row["differential"], t.alignment_epsilon)
    prev = row["dynamics"]["previous"]
    summary = {
        "state": classify_state(row["differential"], prev, per, t),
        "alignment": row["alignment"],
        "htf_ltf": htf_ltf(row["timeframes"], t),
        "base_direction": currency_direction(
            scores[base].get("AVG"), reference.get(base, {}).get("AVG") if reference else None, t.dynamics_epsilon
        ),
        "quote_direction": currency_direction(
            scores[quote].get("AVG"), reference.get(quote, {}).get("AVG") if reference else None, t.dynamics_epsilon
        ),
        "persistence": persistence_label(per, t),
        "trajectory": trajectory(composite_hist, row["differential"], t),
        "run": current_run(composite_hist, row["differential"], t.alignment_epsilon),
        "states_by_timeframe": {
            k: sum(1 for m in matrix if m.get("state", {}).get("key") == k) for k in STATE_LABELS
        },
    }
    out = {
        "meta": {"lookback_minutes": lookback_minutes, "reference_age_minutes": reference_age_minutes},
        "relationship": row,
        "summary": summary,
        "matrix": matrix,
        "history": _chart(composite_hist),
    }
    out["interpretation"] = interpret(out)
    return out
