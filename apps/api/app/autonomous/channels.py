"""Channel lifecycle state machine (pure): one lineage per symbol/timeframe, advanced from Channel Intelligence cores.

FORMING → ACTIVE → MATURE → TOUCHED → BREAKING → BROKEN → RETESTING → CONTINUING → INVALIDATED / EXPIRED.
Every transition carries the closed-bar time of its evidence (touch bar, break bar, retest bar, continuation bar),
so a worker that was down replays the missed steps in order with their original timestamps — never duplicated,
because a step is applied only when its evidence is newer than the lineage watermark.
"""
from __future__ import annotations

from datetime import datetime

from ..market import channel_intelligence as chan
from ..market.channel_events import channel_id as event_channel_id
from .config import TF_DELTA, AESettings
from .store import det_id

BREAK_PATH = ("BREAKING", "BROKEN", "RETESTING", "CONTINUING")
TOUCH_EVENTS = {"Test Upper": "UPPER", "Test Lower": "LOWER", "Channel Touch": "LOWER"}
REASONS = {
    "CHANNEL_IDENTIFIED": "Regression channel identified on closed bars",
    "CHANNEL_VALIDATED": "Channel respected with two or more touches per boundary",
    "CHANNEL_MATURED": "Channel matured (touch count / persistence)",
    "BOUNDARY_TOUCH": "Closed bar touched a channel boundary",
    "TOUCH_RELEASED": "Price moved away from the boundary",
    "BREAK_DETECTED": "Close beyond the channel boundary",
    "BREAK_CONFIRMED": "Break confirmed by consecutive closes beyond the boundary",
    "RETEST_STARTED": "Price returned to the broken boundary",
    "RETEST_CONTINUATION": "Retest held and price closed beyond the retest candle",
    "FALSE_BREAK": "Break failed — price closed back inside the channel",
    "DIRECTION_REVERSED": "Channel slope reversed",
    "CLOSES_OUTSIDE": "Closes no longer respect the channel",
    "BREAK_AGED": "Break resolved; lineage superseded by the new leg",
}


def quality(c: dict) -> float:
    validity = {"VALID": 1.0, "FORMING": 0.5}.get(c["validity"]["key"], 0.0)
    touches = min(1.0, (c["touches_upper"] + c["touches_lower"]) / 6)
    return round(100 * (0.4 * c["inside_ratio"] + 0.3 * touches + 0.3 * validity), 1)


def erz(c: dict) -> tuple[float | None, float | None]:
    """With-trend reaction zone: the lower 20% of a rising channel, the upper 20% of a falling one."""
    w = c["upper"] - c["lower"]
    if c["direction"] == "ASCENDING":
        return c["lower"], c["lower"] + 0.2 * w
    if c["direction"] == "DESCENDING":
        return c["upper"] - 0.2 * w, c["upper"]
    return None, None


def _base_state(c: dict) -> str:
    if c["validity"]["key"] == "FORMING":
        return "FORMING"
    touches = c["touches_upper"] + c["touches_lower"]
    return "MATURE" if touches >= 5 or c["age"] >= 1.5 * c["period"] else "ACTIVE"


def _geometry(c: dict) -> dict:
    lo, hi = erz(c)
    w = c["upper"] - c["lower"]
    return {
        "direction": c["direction"], "validity": c["validity"]["key"], "upper": c["upper"], "mid": c["mid"], "lower": c["lower"],
        "width": w, "width_atr": c["width_atr"], "atr": c["atr"],
        "position": round((c["last_close"] - c["lower"]) / w * 100, 1) if w else None,
        "touches_upper": c["touches_upper"], "touches_lower": c["touches_lower"], "quality": quality(c), "age_bars": c["age"],
        "erz_lo": lo, "erz_hi": hi,
    }


def _confirm_at(b: dict, tf: str, s: chan.ChannelSettings) -> str:
    return (datetime.fromisoformat(b["at"]) + TF_DELTA[tf] * max(0, s.confirm_closes - 1)).isoformat()


def _break_steps(b: dict, tf: str, s: chan.ChannelSettings) -> list[tuple[str, str, str]]:
    steps = [("BREAKING", b["at"], "BREAK_DETECTED")]
    if b["confirmed"]:
        steps.append(("BROKEN", _confirm_at(b, tf, s), "BREAK_CONFIRMED"))
    if b.get("retest_at"):
        steps.append(("RETESTING", b["retest_at"], "RETEST_STARTED"))
    if b.get("completed_at"):
        steps.append(("CONTINUING", b["completed_at"], "RETEST_CONTINUATION"))
    if b["failed"] and b.get("failed_at"):
        steps = [x for x in steps if x[1] <= b["failed_at"]]
    steps.sort(key=lambda x: (x[1], BREAK_PATH.index(x[0])))
    return steps


def advance(prev: dict | None, scope: tuple[str, str], symbol: str, tf: str, c: dict, ae: AESettings,
            s: chan.ChannelSettings, now_iso: str) -> dict:
    """Next lineage state from one closed-bar channel core.

    Returns {"insert": row | None, "update": (id, fields) | None, "transitions": [...]}; empty when no new bar closed."""
    out: dict = {"insert": None, "update": None, "transitions": []}
    if not c.get("available"):
        return out
    closed_at = c["closed_at"]
    if prev and prev.get("last_bar_at") and closed_at <= prev["last_bar_at"]:
        return out
    geo = _geometry(c)
    meta_lines = c["lines"]

    def tr(cid: str, frm: str | None, to: str, reason: str, at: str, evidence: dict | None = None) -> None:
        out["transitions"].append({
            "entity_type": "CHANNEL", "entity_id": cid, "symbol": symbol, "timeframe": tf,
            "from_stage": "CHANNEL" if frm else None, "from_state": frm, "to_stage": "CHANNEL", "to_state": to,
            "reason_code": reason, "detail": REASONS[reason], "evidence_at": at, "evidence_json": evidence or {},
        })

    if prev is None:
        if c["validity"]["key"] == "LOOSE":
            return out
        cid = det_id("CH", scope[0], scope[1], symbol, tf, c["fit_start"], closed_at)
        state = "FORMING" if c["validity"]["key"] == "FORMING" else "ACTIVE"
        tr(cid, None, state, "CHANNEL_IDENTIFIED", closed_at, {"validity": geo["validity"], "direction": geo["direction"],
                                                                 "upper": geo["upper"], "lower": geo["lower"]})
        out["insert"] = {
            "id": cid, "symbol": symbol, "timeframe": tf, "status": "ACTIVE", "state": state, **geo, "state_entered_at": closed_at,
            "started_at": c["fit_start"], "last_bar_at": closed_at, "updated_at": now_iso,
            "lines_json": {"lines": meta_lines, "opened_at": closed_at, "ref": event_channel_id(symbol, tf, c["fit_start"]),
                           "consumed_break_at": None},
        }
        return out

    cid = prev["id"]
    meta = dict(prev.get("lines") or {})
    opened_at = meta.get("opened_at") or prev["state_entered_at"] or prev["started_at"]
    state = prev["state"]
    entered = prev["state_entered_at"]
    fields: dict = {**geo, "last_bar_at": closed_at, "updated_at": now_iso}
    breaks = c.get("breakouts") or []
    tracked = None
    if prev.get("break_at"):
        tracked = next((b for b in breaks if b["at"] == prev["break_at"]), None)
    floor = max(opened_at, meta.get("consumed_break_at") or "")
    if tracked is None and not prev.get("break_at"):
        fresh = [b for b in breaks if b["at"] > floor]
        tracked = fresh[-1] if fresh else None

    def move(to: str, reason: str, at: str, evidence: dict | None = None) -> None:
        nonlocal state, entered
        if to == state:
            return
        tr(cid, state, to, reason, at, evidence)
        state, entered = to, at

    if tracked is not None:
        d = 1 if tracked["direction"] == "UP" else -1
        fields.update(break_direction=tracked["direction"], break_level=tracked["level"], break_at=tracked["at"],
                      retest_at=tracked.get("retest_at"), continuation_at=tracked.get("completed_at"))
        current = BREAK_PATH.index(state) if state in BREAK_PATH else -1
        for to, at, reason in _break_steps(tracked, tf, s):
            if BREAK_PATH.index(to) > current:
                move(to, reason, at, {"level": tracked["level"], "direction": tracked["direction"], "close": tracked["close"]})
                current = BREAK_PATH.index(to)
        if tracked["failed"] and tracked.get("failed_at"):
            move(_base_state(c), "FALSE_BREAK", tracked["failed_at"], {"level": tracked["level"], "direction": tracked["direction"]})
            meta["consumed_break_at"] = tracked["at"]
            fields.update(break_direction=None, break_level=None, break_at=None, retest_at=None, continuation_at=None)
        elif tracked.get("bars_after", 0) > ae.max_breakout_age_bars and state in ("BROKEN", "RETESTING", "CONTINUING"):
            move("EXPIRED", "BREAK_AGED", closed_at, {"bars_after": tracked["bars_after"], "direction": d})
    elif prev.get("break_at"):
        # The tracked break left the scan window without resolving: the lineage is history.
        move("EXPIRED", "BREAK_AGED", closed_at, {"break_at": prev["break_at"]})
    else:
        flipped = {prev.get("direction"), c["direction"]} == {"ASCENDING", "DESCENDING"}
        if flipped:
            move("INVALIDATED", "DIRECTION_REVERSED", closed_at, {"from": prev.get("direction"), "to": c["direction"]})
        elif c["validity"]["key"] == "LOOSE":
            move("INVALIDATED", "CLOSES_OUTSIDE", closed_at, {"inside_ratio": c["inside_ratio"]})
        else:
            watermark = prev.get("last_bar_at") or opened_at
            touches = sorted((e for e in c.get("events") or [] if e["event"] in TOUCH_EVENTS and e["at"] > watermark),
                             key=lambda e: e["at"])
            base = _base_state(c)
            for e in touches:
                side = TOUCH_EVENTS[e["event"]]
                if state == "TOUCHED":
                    move(base, "TOUCH_RELEASED", e["at"])
                move("TOUCHED", "BOUNDARY_TOUCH", e["at"], {"side": side, "level": e["level"], "result": e.get("result")})
                fields.update(last_touch_at=e["at"], last_touch_side=side)
            touching = bool(touches) and touches[-1]["at"] == closed_at
            if not touching:
                reason = ("TOUCH_RELEASED" if state == "TOUCHED" else "CHANNEL_MATURED" if base == "MATURE"
                          else "CHANNEL_VALIDATED" if base == "ACTIVE" else "CHANNEL_IDENTIFIED")
                move(base, reason, closed_at)

    fields.update(state=state, state_entered_at=entered, lines_json={**meta, "lines": meta_lines})
    if state in ("INVALIDATED", "EXPIRED"):
        fields.update(status="CLOSED", closed_at=entered)
    out["update"] = (cid, fields)
    return out
