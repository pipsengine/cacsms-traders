"""Fractal Structure analytics (Market Structure → Fractals) on closed candles.

Per-timeframe fractal lifecycle (Candidate → Developing → Provisional → Confirmed, or Invalid when price takes
the extreme out before confirmation), weekly fractal clusters, a fractal hierarchy around price and
lower-timeframe confirmation. ``price=None`` evaluates closed bars only. Analysis only — never trade direction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .scanner_analytics import Bar, market_structure, pivots, true_ranges, wilder_atr
from .scanner_config import _floats
from .structure_overview import TF_DELTA

FRACTAL_TIMEFRAMES = ("W", "D1", "H8", "H1")
BAR_KEYS = {"W": "W1", "D1": "D1", "H8": "H8", "H1": "H1"}
STATUS = {
    "CANDIDATE": "Candidate",
    "DEVELOPING": "Developing",
    "PROVISIONAL": "Provisional",
    "CONFIRMED": "Confirmed",
    "INVALID": "Invalid",
}
LIFECYCLE = (
    ("CANDIDATE", "Potential fractal identified by swing structure"),
    ("DEVELOPING", "Additional evidence being formed"),
    ("PROVISIONAL", "Criteria almost met (waiting confirmation)"),
    ("CONFIRMED", "Fractal confirmed on closed bars"),
)
_PENDING = ("CANDIDATE", "DEVELOPING", "PROVISIONAL")


@dataclass(frozen=True)
class FractalSettings:
    fractal_strength: int
    active_bars: int
    away_atr: float
    cluster_atr: float
    cluster_lookback: int
    cluster_min: int
    near_cluster_atr: float
    atr_period: int = 14


def fractal_settings() -> FractalSettings:
    # FRACTAL_SETTINGS="fractal_strength,active_bars,away_atr,cluster_atr,cluster_lookback_weeks,cluster_min_touches,near_cluster_atr"
    fs, ab, aw, ca, cl, cm, nc = _floats("FRACTAL_SETTINGS", (2.0, 3.0, 0.25, 0.5, 156.0, 2.0, 2.0))
    return FractalSettings(
        fractal_strength=max(1, int(fs)),
        active_bars=max(1, int(ab)),
        away_atr=aw,
        cluster_atr=max(0.05, ca),
        cluster_lookback=max(26, int(cl)),
        cluster_min=max(2, int(cm)),
        near_cluster_atr=max(0.1, nc),
    )


def fractal_settings_payload() -> dict:
    s = fractal_settings()
    return {k: getattr(s, k) for k in s.__dataclass_fields__}


def kind_for(tf: str, side: str) -> str:
    return ("WF" if tf == "W" else "F") + ("H" if side == "HIGH" else "L")


def _closed_at(bar: Bar, tf: str) -> str:
    return (bar.t + TF_DELTA[tf]).isoformat()


def _clusters(points: list[tuple[int, float]], bars: list[Bar], tol: float, side: str) -> list[dict]:
    """Greedy price clusters of confirmed fractals (within ±tol of the cluster's running extent)."""
    out: list[list[tuple[int, float]]] = []
    for i, p in sorted(points, key=lambda x: x[1]):
        if out and p - min(q for _, q in out[-1]) <= 2 * tol:
            out[-1].append((i, p))
        else:
            out.append([(i, p)])
    last = bars[-1].t
    res = []
    for grp in out:
        first, latest = min(i for i, _ in grp), max(i for i, _ in grp)
        res.append({
            "side": side,
            "lo": min(p for _, p in grp),
            "hi": max(p for _, p in grp),
            "touches": len(grp),
            "first_at": bars[first].t.isoformat(),
            "last_at": bars[latest].t.isoformat(),
            "age_weeks": round((last - bars[first].t).days / 7),
        })
    return res


def tf_core(bars: list[Bar], tf: str, s: FractalSettings) -> dict:
    """Price-independent fractal state for one timeframe."""
    n = s.fractal_strength
    size = len(bars)
    if size < 2 * n + 5:
        return {"available": False}
    atr = wilder_atr(true_ranges(bars), min(s.atr_period, size - 2))
    highs, lows = pivots(bars, n)
    confirmed = [
        {"side": side, "kind": kind_for(tf, side), "price": p, "index": i, "at": bars[i].t.isoformat(),
         "confirmed_at": _closed_at(bars[i + n], tf)}
        for side, pts in (("HIGH", highs), ("LOW", lows))
        for i, p in pts
    ]
    confirmed.sort(key=lambda f: f["index"])
    pending, rejected = [], []
    # A candidate is an extreme versus the n bars on its left; it confirms after n closed bars on its right
    # and is rejected if one of those bars takes the extreme out first.
    for c in range(max(n, size - n - s.active_bars - n), size):
        b, left = bars[c], bars[c - n : c]
        right = bars[c + 1 : c + 1 + n]
        for side in ("HIGH", "LOW"):
            hi = side == "HIGH"
            if not all((x.h < b.h) if hi else (x.l > b.l) for x in left):
                continue
            price = b.h if hi else b.l
            broken = next((k for k, x in enumerate(right) if ((x.h >= b.h) if hi else (x.l <= b.l))), None)
            if broken is not None:
                rejected.append({"side": side, "kind": kind_for(tf, side), "price": price, "index": c, "at": b.t.isoformat(),
                                 "rejected_at": _closed_at(right[broken], tf), "rejected_index": c + 1 + broken})
            elif len(right) < n:
                pending.append({"side": side, "kind": kind_for(tf, side), "price": price, "index": c, "at": b.t.isoformat(),
                                "right": len(right), "closed_at": _closed_at(b, tf),
                                "first_right_at": _closed_at(right[0], tf) if right else None})
    clusters = None
    if tf == "W":
        tol = s.cluster_atr * (atr[-1] if atr else 0)
        since = max(0, size - s.cluster_lookback)
        clusters = (
            _clusters([(i, p) for i, p in highs if i >= since], bars, tol, "HIGH")
            + _clusters([(i, p) for i, p in lows if i >= since], bars, tol, "LOW")
        )
    return {
        "available": True,
        "size": size,
        "atr": atr[-1] if atr else None,
        "structure": market_structure(bars, n)["key"],
        "confirmed": confirmed[-40:],
        "pending": pending,
        "rejected": rejected,
        "clusters": clusters,
        "last_close": bars[-1].c,
        "closed_at": _closed_at(bars[-1], tf),
    }


def fractal_core(bars: dict[str, list[Bar]], s: FractalSettings) -> dict:
    return {tf: tf_core(bars[BAR_KEYS[tf]], tf, s) for tf in FRACTAL_TIMEFRAMES}


# ----- live view -----


def _stage(f: dict, price: float | None, atr: float | None, s: FractalSettings) -> str:
    hi = f["side"] == "HIGH"
    if price is not None and ((price > f["price"]) if hi else (price < f["price"])):
        return "INVALID"
    away = price is not None and atr and ((f["price"] - price) if hi else (price - f["price"])) >= s.away_atr * atr
    if f["right"] == 0:
        return "DEVELOPING" if away else "CANDIDATE"
    return "PROVISIONAL" if away else "DEVELOPING"


def active_fractals(core: dict, price: float | None, s: FractalSettings) -> dict[str, dict | None]:
    """Most relevant fractal per side: a pending candidate, else a recently confirmed or rejected one."""
    out: dict[str, dict | None] = {}
    last = core["size"] - 1
    n = s.fractal_strength
    for side in ("HIGH", "LOW"):
        pend = [f for f in core["pending"] if f["side"] == side]
        if pend:
            f = pend[-1]
            out[side] = {**f, "status": _stage(f, price, core["atr"], s)}
            continue
        conf = [f for f in core["confirmed"] if f["side"] == side and last - (f["index"] + n) < s.active_bars]
        rej = [f for f in core["rejected"] if f["side"] == side and last - f["rejected_index"] < s.active_bars]
        best = max(conf + rej, key=lambda f: f["index"], default=None)
        out[side] = None if best is None else {**best, "status": "INVALID" if "rejected_at" in best else "CONFIRMED"}
    return out


def _public(f: dict | None) -> dict | None:
    if f is None:
        return None
    return {
        "kind": f["kind"],
        "side": f["side"],
        "price": f["price"],
        "at": f["at"],
        "status": {"key": f["status"], "label": STATUS[f["status"]]},
    }


def tf_view(core: dict, price: float | None, s: FractalSettings) -> dict:
    if not core.get("available"):
        return {"available": False}
    act = active_fractals(core, price, s)
    latest = max((f for f in act.values() if f), key=lambda f: f["index"], default=None)
    return {"available": True, "sides": {k.lower(): _public(v) for k, v in act.items()}, "latest": _public(latest),
            "_act": act}


def nearest(core: dict, act: dict, price: float, side: str) -> dict | None:
    """Closest level on one side of price: the active fractal if it is on that side, else the nearest confirmed one."""
    above = side == "HIGH"
    a = act.get(side)
    if a and a["status"] != "INVALID" and ((a["price"] >= price) if above else (a["price"] <= price)):
        return a
    pool = [f for f in core["confirmed"] if f["side"] == side and ((f["price"] >= price) if above else (f["price"] <= price))]
    if not pool:
        return None
    f = min(pool, key=lambda f: abs(f["price"] - price))
    return {**f, "status": "CONFIRMED"}


def clusters_view(core: dict, price: float, s: FractalSettings) -> dict:
    atr = core.get("atr") or 0
    out = {"resistance": [], "support": []}
    for c in core.get("clusters") or []:
        if c["touches"] < s.cluster_min:
            continue
        item = {**c, "distance": (c["lo"] - price) if c["side"] == "HIGH" else (price - c["hi"])}
        item["distance_atr"] = round(item["distance"] / atr, 2) if atr else None
        item["near"] = atr > 0 and abs(item["distance"]) <= s.near_cluster_atr * atr
        out["resistance" if c["side"] == "HIGH" else "support"].append(item)
    out["resistance"].sort(key=lambda c: abs(c["distance"]))
    out["support"].sort(key=lambda c: abs(c["distance"]))
    return out


def cluster_for(clusters: dict, f: dict | None) -> dict | None:
    if not f:
        return None
    pool = clusters["resistance"] if f["side"] == "HIGH" else clusters["support"]
    atr_pad = 0.0
    return next((c for c in pool if c["lo"] - atr_pad <= f["price"] <= c["hi"] + atr_pad), None)


def lifecycle(f: dict | None, tf: str) -> list[dict]:
    status = (f or {}).get("status")
    reached = {k: False for k, _ in LIFECYCLE}
    if status in _PENDING or status == "CONFIRMED":
        order = [k for k, _ in LIFECYCLE]
        for k in order[: order.index(status) + 1]:
            reached[k] = True
    times = {}
    if f:
        times["CANDIDATE"] = f.get("closed_at") or f.get("at")
        if f.get("first_right_at"):
            times["DEVELOPING"] = f["first_right_at"]
        if f.get("confirmed_at"):
            times["CONFIRMED"] = f["confirmed_at"]
    return [
        {"key": k, "label": STATUS[k], "description": d, "done": reached[k], "current": k == status, "at": times.get(k)}
        for k, d in LIFECYCLE
    ]


def ltf_evidence(tf: str, core: dict, act: dict, price: float | None) -> str:
    if not core.get("available"):
        return "Insufficient history"
    pend = [f for f in act.values() if f and f["status"] in _PENDING]
    if pend:
        f = max(pend, key=lambda f: f["index"])
        prev = [x for x in core["confirmed"] if x["side"] == f["side"]]
        if f["side"] == "LOW":
            higher = bool(prev) and f["price"] > prev[-1]["price"]
            return "Higher low forming" if higher else "Swing low forming"
        lower = bool(prev) and f["price"] < prev[-1]["price"]
        return "Lower high forming" if lower else "Swing high forming"
    conf = [f for f in act.values() if f and f["status"] == "CONFIRMED"]
    if conf:
        f = max(conf, key=lambda f: f["index"])
        return f"{f['kind']} confirmed — {'support' if f['side'] == 'LOW' else 'resistance'} reference"
    if any(f and f["status"] == "INVALID" for f in act.values()):
        return "Fractal invalidated — waiting for new swing"
    return "Waiting for BOS confirmation" if tf == "H1" else "No active fractal"


def _short(status: str) -> str:
    return {"CANDIDATE": "Cand", "DEVELOPING": "Dev", "PROVISIONAL": "Prov", "CONFIRMED": "Conf", "INVALID": "Inv"}[status]


def fractal_view(core: dict, price: float | None, regimes: dict, range_view: dict | None, range_core: dict | None,
                 s: FractalSettings) -> dict:
    """Live per-symbol fractal intelligence."""
    w = core.get("W") or {}
    if not w.get("available"):
        return {"available": False, "reason": "Insufficient closed weekly history"}
    px = price if price is not None else w["last_close"]
    tfs = {tf: tf_view(core[tf], price, s) for tf in FRACTAL_TIMEFRAMES}
    clusters = clusters_view(w, px, s)

    hierarchy = []
    for tf in ("W", "D1", "H8"):
        c = core[tf]
        if not c.get("available"):
            continue
        act = tfs[tf]["_act"]
        for side in ("HIGH", "LOW"):
            f = nearest(c, act, px, side)
            if f:
                cl = cluster_for(clusters, f) if tf == "W" else None
                role = ("Major " if tf == "W" else "") + ("resistance" if side == "HIGH" else "support")
                hierarchy.append({
                    "tf": tf, "kind": f["kind"], "price": f["price"], "side": side,
                    "status": {"key": f["status"], "label": STATUS[f["status"]]},
                    "title": f"{'Weekly' if tf == 'W' else 'Daily' if tf == 'D1' else tf} Fractal {'High' if side == 'HIGH' else 'Low'}",
                    "note": f"{role}{' cluster' if cl else ''}" if tf == "W" else f"{'Higher' if tf == 'D1' else 'Lower'} TF {role}",
                })
    hierarchy.sort(key=lambda h: -h["price"])
    pos = (range_view or {}).get("position")
    band = ((range_view or {}).get("position_band") or {}).get("label")
    current = {"tf": None, "kind": "PRICE", "price": px, "side": None, "status": None, "title": "Current Price",
               "note": (f"{band} of weekly range ({pos:.0f}%)" if pos is not None and band else "Live price")}
    idx = next((k for k, h in enumerate(hierarchy) if h["price"] < px), len(hierarchy))
    hierarchy.insert(idx, current)

    # Focus fractal: the weekly fractal on the side price is working (range module's developing WFH/WFL), else latest W.
    w_act = tfs["W"]["_act"]
    want = (range_view or {}).get("fractal_kind")
    focus = None
    if want:
        side = "HIGH" if want == "WFH" else "LOW"
        focus = w_act.get(side)
    focus = focus or max((f for f in w_act.values() if f), key=lambda f: f["index"], default=None)
    focus_cluster = cluster_for(clusters, focus)

    ltf = []
    for tf in FRACTAL_TIMEFRAMES:
        v = tfs[tf]
        f = (v.get("latest") or None) if v.get("available") else None
        r = regimes.get(tf)
        ltf.append({
            "tf": tf,
            "structure": {"key": r or "NEUTRAL", "label": (r or "Neutral").title()},
            "fractal": f"{f['kind']} ({_short(f['status']['key'])})" if f else "—",
            "fractal_status": f["status"]["key"] if f else None,
            "evidence": ltf_evidence(tf, core[tf], v.get("_act", {}), price),
        })

    details = None
    if focus:
        details = {
            "kind": focus["kind"],
            "side": focus["side"],
            "label": f"{focus['kind']} ({STATUS[focus['status']]})",
            "price": focus["price"],
            "tf": "W",
            "status": {"key": focus["status"], "label": STATUS[focus["status"]]},
            "cluster_zone": [focus_cluster["lo"], focus_cluster["hi"]] if focus_cluster else None,
            "touches": focus_cluster["touches"] if focus_cluster else 1,
            "last_touch": focus_cluster["last_at"] if focus_cluster else focus["at"],
            "range_position": pos,
            "range_band": band,
            "atr": w["atr"],
            "validation": "Confirmed on closed weekly bars" if focus["status"] == "CONFIRMED"
            else "Invalidated by price" if focus["status"] == "INVALID" else "Pending lower TF confirmation",
        }
    return {
        "available": True,
        "price": px,
        "closed_bar_only": price is None,
        "timeframes": {tf: {k: v for k, v in tfs[tf].items() if k != "_act"} for tf in FRACTAL_TIMEFRAMES},
        "hierarchy": hierarchy,
        "details": details,
        "lifecycle": lifecycle(focus, "W"),
        "evidence": (range_view or {}).get("evidence") or [],
        "evidence_score": (range_view or {}).get("evidence_score"),
        "ltf": ltf,
        "clusters": clusters,
        "range": None if not range_core or range_core.get("regime", {}).get("key") == "INSUFFICIENT" else {
            "high": range_core.get("range_high"), "low": range_core.get("range_low"), "start": range_core.get("start"),
            "ranging": range_core.get("ranging"),
        },
    }


def fractal_marks(core: dict, tf: str, limit: int = 40) -> list[dict]:
    """Chart marks for one timeframe: confirmed fractals plus pending and rejected candidates."""
    c = core.get(tf) or {}
    if not c.get("available"):
        return []
    marks = [{"kind": f["kind"], "side": f["side"], "price": f["price"], "at": f["at"], "status": "CONFIRMED"} for f in c["confirmed"]]
    marks += [{"kind": f["kind"], "side": f["side"], "price": f["price"], "at": f["at"], "status": "PENDING"} for f in c["pending"]]
    marks += [{"kind": f["kind"], "side": f["side"], "price": f["price"], "at": f["at"], "status": "INVALID"} for f in c["rejected"]]
    marks.sort(key=lambda m: m["at"])
    return marks[-limit:]


def is_recent(at: str | None, anchor: datetime, hours: float) -> bool:
    return bool(at) and (anchor - datetime.fromisoformat(at)).total_seconds() <= hours * 3600
