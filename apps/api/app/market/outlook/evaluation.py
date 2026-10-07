"""OutcomeEvaluator, CalibrationEngine and IntradayOutlookMonitor.

All three read only closed bars after the outlook's frozen close; none of them modifies the published prediction."""
from __future__ import annotations

from datetime import datetime

from ..scanner_analytics import Bar
from .reasoning import bucket_of

DIR = {"BULLISH": 1, "BEARISH": -1, "RANGE": 0}
RANGE_MOVE_ATR = 0.5


def _t(v: str) -> datetime:
    return datetime.fromisoformat(v)


def _touch(b: Bar, lo: float, hi: float) -> bool:
    return b.l <= hi and b.h >= lo


# ----- OutcomeEvaluator -----


def evaluate(outlook: dict, h1: list[Bar], next_close: datetime, evaluated_date: str) -> dict | None:
    """Score one published outlook against the next trading day's closed H1 path (first event wins).

    Returns None while that day's bars are incomplete."""
    anchor = _t(outlook["anchor"])
    path = [b for b in h1 if anchor <= b.t < next_close]
    if not path or path[-1].t.timestamp() + 3600 < next_close.timestamp() - 3 * 3600:
        return None
    d = DIR.get(outlook.get("expected_direction") or "", 0)
    px, atr = outlook["price"], ((outlook.get("volatility") or {}).get("atr") or 0.0)
    erz, tg, inv = outlook["erz"], outlook["targets"], outlook["invalidation"]
    close = path[-1].c
    move = close - px
    hi, lo = max(b.h for b in path), min(b.l for b in path)
    erz_touched = any(_touch(b, erz["lo"], erz["hi"]) for b in path)
    t1 = t2 = invalidated = False
    first = None
    if d:
        for b in path:
            if not invalidated and (b.c - inv["price"]) * d < 0:
                invalidated = True
                first = first or "INVALIDATED"
            if not t1 and ((b.h >= tg[0]["price"]) if d == 1 else (b.l <= tg[0]["price"])):
                t1 = True
                first = first or "TARGET_1"
            if not t2 and ((b.h >= tg[1]["price"]) if d == 1 else (b.l <= tg[1]["price"])):
                t2 = True
        direction_correct = int(move * d > 0)
        if first == "TARGET_1":
            outcome = "WIN"
        elif first == "INVALIDATED":
            outcome = "LOSS"
        else:
            outcome = "WIN" if direction_correct and abs(move) >= 0.25 * atr else "LOSS" if not direction_correct and abs(move) >= 0.25 * atr else "NEUTRAL"
        alt_dir = -d
    else:
        r_lo, r_hi = outlook["range_scenario"]["range"]
        broke = any(b.c > r_hi or b.c < r_lo for b in path)
        direction_correct = int(not broke and abs(move) < RANGE_MOVE_ATR * atr) if atr else int(not broke)
        outcome = "WIN" if direction_correct else "LOSS"
        alt_dir = 1 if move > 0 else -1
    if d and outcome == "WIN":
        scenario = "PRIMARY"
    elif abs(move) < RANGE_MOVE_ATR * atr and not t1 and not invalidated:
        scenario = "RANGE"
    elif move * alt_dir > 0 and (invalidated or abs(move) >= RANGE_MOVE_ATR * atr):
        scenario = "ALTERNATIVE"
    elif not d and outcome == "WIN":
        scenario = "RANGE"
    else:
        scenario = "NONE"
    conf = outlook.get("confidence") or {}
    return {
        "evaluated_date": evaluated_date, "outcome": outcome, "scenario_result": scenario, "direction_correct": direction_correct,
        "target1_hit": t1, "target2_hit": t2, "invalidated": invalidated, "erz_touched": erz_touched,
        "move_pct": round(move / px * 100, 4) if px else None, "move_atr": round(move / atr, 2) if atr else None,
        "close": close, "high": hi, "low": lo, "bars": len(path), "first_event": first,
        "raw_confidence": (conf.get("calibration") or {}).get("raw", conf.get("primary")),
        "realised_direction": "BULLISH" if move > 0 else "BEARISH" if move < 0 else "FLAT",
    }


# ----- CalibrationEngine -----


def calibration_table(evaluations: list[dict]) -> tuple[dict, int]:
    """Hit counts per raw-confidence bucket from directional calls only (range calls have no directional hit)."""
    table: dict[str, dict] = {}
    n = 0
    for e in evaluations:
        if e["direction"] not in ("BULLISH", "BEARISH") or e["direction_correct"] is None:
            continue
        raw = (e.get("detail") or {}).get("raw_confidence", e["confidence"])
        if raw is None:
            continue
        b = table.setdefault(bucket_of(float(raw)), {"n": 0, "hits": 0})
        b["n"] += 1
        b["hits"] += int(e["direction_correct"])
        n += 1
    return table, n


def performance(evaluations: list[dict], qualified_only: bool = False) -> dict:
    """Rolling accuracy, calibration buckets, distribution and error analysis for the Historical Outlook tab."""
    rows = [e for e in evaluations if e["qualified"]] if qualified_only else list(evaluations)
    directional = [e for e in rows if e["direction"] in ("BULLISH", "BEARISH")]
    decided = [e for e in rows if e["outcome"] in ("WIN", "LOSS")]
    wins = sum(1 for e in decided if e["outcome"] == "WIN")
    buckets = []
    for key in ("<40", "40-50", "50-60", "60-70", "70-80", ">80"):
        sel = [e for e in directional if bucket_of(float(e["confidence"] or 0)) == key]
        hits = sum(int(e["direction_correct"] or 0) for e in sel)
        mid = {"<40": 35, ">80": 85}.get(key) or (int(key.split("-")[0]) + 5)
        buckets.append({"bucket": key, "n": len(sel), "hit_rate": round(100 * hits / len(sel), 1) if sel else None, "expected": mid,
                        "avg_confidence": round(sum(float(e["confidence"] or 0) for e in sel) / len(sel), 1) if sel else None})
    by_scenario = {}
    for e in rows:
        s = by_scenario.setdefault(e["scenario_result"], 0)
        by_scenario[e["scenario_result"]] = s + 1
    by_direction = {}
    for key in ("BULLISH", "BEARISH", "RANGE"):
        sel = [e for e in rows if e["direction"] == key]
        w = sum(1 for e in sel if e["outcome"] == "WIN")
        lo = sum(1 for e in sel if e["outcome"] == "LOSS")
        by_direction[key] = {"n": len(sel), "wins": w, "losses": lo, "accuracy": round(100 * w / (w + lo), 1) if (w + lo) else None}
    false_pos = sum(1 for e in directional if e["qualified"] and e["outcome"] == "LOSS")
    false_neg = sum(1 for e in directional if not e["qualified"] and e["outcome"] == "WIN" and e["target1_hit"])
    brier = [((float(e["confidence"] or 0) / 100) - int(e["direction_correct"] or 0)) ** 2 for e in directional]
    return {
        "samples": len(rows),
        "decided": len(decided),
        "wins": wins,
        "losses": len(decided) - wins,
        "accuracy": round(100 * wins / len(decided), 1) if decided else None,
        "direction_accuracy": round(100 * sum(int(e["direction_correct"] or 0) for e in directional) / len(directional), 1) if directional else None,
        "avg_confidence": round(sum(float(e["confidence"] or 0) for e in rows) / len(rows), 1) if rows else None,
        "target1_rate": round(100 * sum(1 for e in directional if e["target1_hit"]) / len(directional), 1) if directional else None,
        "target2_rate": round(100 * sum(1 for e in directional if e["target2_hit"]) / len(directional), 1) if directional else None,
        "invalidation_rate": round(100 * sum(1 for e in directional if e["invalidated"]) / len(directional), 1) if directional else None,
        "erz_touch_rate": round(100 * sum(1 for e in directional if e["erz_touched"]) / len(directional), 1) if directional else None,
        "brier": round(sum(brier) / len(brier), 4) if brier else None,
        "false_positives": false_pos,
        "false_negatives": false_neg,
        "buckets": buckets,
        "by_scenario": by_scenario,
        "by_direction": by_direction,
    }


# ----- IntradayOutlookMonitor -----


def _structure_hit(events: list[dict], kind: str, d: int, after: datetime) -> datetime | None:
    want = "BOS" if kind == "BOS" else "CHOCH"
    for e in events:
        at = _t(e["at"])
        if at < after or e.get("failed"):
            continue
        if (e["kind"].upper() == want) and (e["direction"] == ("UP" if d == 1 else "DOWN")):
            return at
    return None


def _condition_hit(cond: dict, h1: list[Bar], m30: list[Bar], events: list[dict] | None, after: datetime) -> datetime | None:
    kind = cond["type"]
    if kind == "structure":
        return None if events is None else _structure_hit(events, cond["kind"], cond["dir"], after)
    bars = m30 if cond.get("tf") == "M30" and m30 else h1
    span = 1800 if bars is m30 else 3600
    for b in bars:
        if b.t < after:
            continue
        done = b.t.timestamp() + span
        hit = False
        if kind == "touch_zone":
            hit = _touch(b, cond["lo"], cond["hi"])
        elif kind == "reject_zone":
            hit = _touch(b, cond["lo"], cond["hi"]) and ((b.c > b.o and b.c >= cond["lo"]) if cond["dir"] == 1 else (b.c < b.o and b.c <= cond["hi"]))
        elif kind == "retest":
            hit = _touch(b, cond["lo"], cond["hi"]) and ((b.c >= cond["lo"]) if cond["dir"] == 1 else (b.c <= cond["hi"]))
        elif kind == "reach":
            hit = b.h >= cond["price"] if cond["dir"] == 1 else b.l <= cond["price"]
        elif kind == "close_beyond":
            hit = (b.c - cond["price"]) * cond["dir"] > 0
        if hit:
            return datetime.fromtimestamp(done, tz=b.t.tzinfo)
    return None


def monitor(outlook: dict, h1: list[Bar], m30: list[Bar], events: list[dict] | None, now: datetime) -> dict:
    """Progress of the published confirmation sequence plus invalidation; the system action follows from it."""
    anchor = _t(outlook["anchor"])
    h1 = [b for b in h1 if b.t >= anchor]
    m30 = [b for b in m30 if b.t >= anchor]
    d = DIR.get(outlook.get("expected_direction") or "", 0)
    last = (h1[-1].c if h1 else None) if not m30 else m30[-1].c
    steps, after = [], anchor
    invalid_at = None
    if d:
        inv = outlook["invalidation"]["price"]
        invalid_at = next((datetime.fromtimestamp(b.t.timestamp() + 3600, tz=b.t.tzinfo) for b in h1 if (b.c - inv) * d < 0), None)
    blocked = False
    for st in outlook.get("confirmation_sequence") or []:
        at = None if blocked else _condition_hit(st["condition"], h1, m30, events, after)
        if invalid_at and at and at > invalid_at:
            at = None
        pending_structure = st["condition"]["type"] == "structure" and events is None
        steps.append({"key": st["key"], "step": st["step"], "label": st["label"], "done": at is not None, "at": at.isoformat() if at else None,
                      "unavailable": pending_structure and not blocked})
        if at is None:
            blocked = True
        else:
            after = at
    done = [s for s in steps if s["done"]]
    if not d:
        status = "RANGE_WATCH"
    elif invalid_at:
        status = "INVALIDATED"
    elif not done:
        status = "AWAITING_REACTION"
    else:
        status = done[-1]["key"]
    keys = {s["key"] for s in done}
    qualified = bool(outlook.get("qualified"))
    if status == "INVALIDATED" or not qualified:
        action = {"key": "IGNORE", "label": "Ignore", "detail": "Plan invalidated — the alternative scenario is now in focus." if status == "INVALIDATED" else "Not a qualified opportunity."}
    elif {"BOS", "RETEST"} <= keys and not ({"T1", "T2"} & keys):
        action = {"key": "AUTHORIZE", "label": "Handoff to Opportunity Engine",
                  "detail": "Confirmation sequence complete (BOS + retest). Prediction is not trade authorisation — the Opportunity, Confirmation and Risk engines decide."}
    elif {"T1", "T2"} & keys:
        action = {"key": "WAIT", "label": "Wait", "detail": "Objective reached — no fresh plan until the next daily outlook."}
    elif "REACTION" in keys:
        action = {"key": "PREPARE", "label": "Prepare", "detail": "Price reacted at the ERZ — waiting for H1 structure confirmation."}
    else:
        action = {"key": "WATCH", "label": "Watch", "detail": "Waiting for price to reach the expected reaction zone."}
    return {"status": status, "steps": steps, "invalidated_at": invalid_at.isoformat() if invalid_at else None, "price": last,
            "observed_at": now.isoformat(), "system_action": action, "structure_source": "scanner" if events is not None else None,
            "bars": {"H1": len(h1), "M30": len(m30)}}
