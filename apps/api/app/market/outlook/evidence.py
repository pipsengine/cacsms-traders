"""EvidenceAggregator — reads every specialist engine core at the frozen D1 close and turns each fact into a
traceable evidence item. Nothing here invents a level: every price comes from an engine core or a closed bar."""
from __future__ import annotations

from datetime import datetime, timedelta

from .. import bos_choch as bos
from .. import channel_intelligence as chan
from .. import fractal_structure as frac
from ..range_structure import range_view
from ..range_structure_config import range_settings
from ..structure_overview import alignment as structure_alignment
from ..structure_overview_config import overview_settings
from ..trend_structure import trend_view
from ..trend_structure_config import trend_settings

SOURCES = {
    "CHANNEL": "Channel Intelligence",
    "STRUCTURE": "Market Structure",
    "TREND": "Trend Structure",
    "BOS": "BOS / CHoCH",
    "FRACTAL": "Fractals",
    "RANGE": "Range Structure",
    "TIT": "Trend-in-Trend",
    "STRENGTH": "Strength Intelligence",
    "SUPERTREND": "Supertrend",
    "VOLATILITY": "Volatility (ATR)",
    "MOMENTUM": "Momentum",
}
CHANNEL_WEIGHT = {"Y": 0.35, "YTD": 0.25, "HY": 0.35, "Q": 0.45, "MN": 0.6, "W": 0.85, "D1": 0.85, "H8": 0.55, "H1": 0.3}
HTF = ("Y", "HY", "Q", "MN", "W")
REGIME_WEIGHT = {"W": 1.0, "D1": 0.9, "H8": 0.6, "H1": 0.35}
EVENT_WEIGHT = {"W": 0.9, "D1": 0.65, "H8": 0.45, "H1": 0.3}
EVENT_WINDOW_BARS = {"W": 3, "D1": 8, "H8": 12, "H1": 24}
TF_HOURS = {"W": 168, "D1": 24, "H8": 8, "H1": 1}
SUPERTREND_WEIGHT = {"W": 0.5, "D1": 0.45, "H8": 0.3, "H1": 0.15}
SLOPE = {"Strong": 1.0, "Moderate": 0.8, "Weak": 0.55}
VALIDITY = {"VALID": 1.0, "FORMING": 0.85, "LOOSE": 0.6}
DIR_WORD = {1: "bullish", -1: "bearish", 0: "neutral"}


def digits_for(symbol: str) -> int:
    return 2 if symbol.startswith("XAU") else 3 if symbol.endswith("JPY") else 5


class _Collector:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, source: str, tf: str | None, role: str, sign: int, weight: float, title: str, detail: str,
            *, price: float | None = None, at: str | None = None, key: str | None = None) -> None:
        if weight <= 0:
            return
        self.items.append({
            "id": f"E{len(self.items) + 1:02d}",
            "key": key or f"{source}:{tf or '-'}:{len(self.items)}",
            "source": SOURCES[source],
            "source_key": source,
            "tf": tf,
            "role": role,
            "sign": sign,
            "weight": round(weight, 3),
            "title": title,
            "detail": detail,
            "price": price,
            "at": at,
        })


def _f(v: float | None, dp: int) -> str:
    return "—" if v is None else f"{v:,.{dp}f}"


def _recent(at: str, anchor: datetime, tf: str) -> bool:
    return datetime.fromisoformat(at) >= anchor - timedelta(hours=TF_HOURS[tf] * EVENT_WINDOW_BARS[tf])


def aggregate(symbol: str, a: dict, price: float, anchor: datetime, strength: dict | None) -> dict:
    """Facts (structured engine outputs at ``price``) plus the weighted evidence list."""
    dp = digits_for(symbol)
    cs, ts, ovs, fs, bs, rs = (chan.channel_settings(), trend_settings(), overview_settings(), frac.fractal_settings(),
                               bos.bos_settings(), range_settings())
    ev = _Collector()
    atr = (a.get("volatility") or {}).get("atr") or ((a["channel"].get("D1") or {}).get("atr")) or 0.0
    regimes = a["overview"]["regimes"]

    # ----- Channel Intelligence: direction per timeframe and boundary position -----
    channels = {tf: chan.tf_view(a["channel"], tf, price, cs) for tf in chan.CHANNEL_TIMEFRAMES}
    for tf, v in channels.items():
        if not v.get("available"):
            continue
        d = {"UPTREND": 1, "DOWNTREND": -1}.get(v["direction"]["key"], 0)
        w = CHANNEL_WEIGHT[tf] * SLOPE.get(v["slope_strength"], 0.7) * VALIDITY.get(v["validity"]["key"], 0.7)
        if d:
            ev.add("CHANNEL", tf, "trend", d, w, f"{tf} channel {v['direction']['label'].lower()}",
                   f"{v['slope_strength']} slope, {v['validity']['label'].lower()}, price at {v['position']:.0f}% of the channel.",
                   key=f"channel_dir:{tf}")
        else:
            ev.add("CHANNEL", tf, "range", 0, w * 0.6, f"{tf} channel flat", f"Flat {tf} regression channel — rotation between "
                   f"{_f(v['lower'], dp)} and {_f(v['upper'], dp)}.", key=f"channel_dir:{tf}")
        if tf in ("W", "D1", "H8") and v["position"] is not None:
            pos, bw = v["position"], {"W": 0.7, "D1": 0.6, "H8": 0.4}[tf]
            if v["state"]["key"] == "BREAKOUT_UP":
                ev.add("CHANNEL", tf, "breakout", 1, bw * 0.8, f"Above {tf} channel", f"Close {_f(price, dp)} above the {tf} upper boundary {_f(v['upper'], dp)}.",
                       price=v["upper"], key=f"channel_edge:{tf}")
            elif v["state"]["key"] == "BREAKOUT_DOWN":
                ev.add("CHANNEL", tf, "breakout", -1, bw * 0.8, f"Below {tf} channel", f"Close {_f(price, dp)} below the {tf} lower boundary {_f(v['lower'], dp)}.",
                       price=v["lower"], key=f"channel_edge:{tf}")
            elif pos <= 18:
                ev.add("CHANNEL", tf, "reaction", 1, bw, f"At {tf} channel support", f"Price {pos:.0f}% into the {tf} channel — lower boundary {_f(v['lower'], dp)}.",
                       price=v["lower"], key=f"channel_edge:{tf}")
            elif pos >= 82:
                ev.add("CHANNEL", tf, "reaction", -1, bw, f"At {tf} channel resistance", f"Price {pos:.0f}% into the {tf} channel — upper boundary {_f(v['upper'], dp)}.",
                       price=v["upper"], key=f"channel_edge:{tf}")

    # ----- Market Structure: regime per timeframe -----
    for tf, r in regimes.items():
        if r in ("BULLISH", "BEARISH"):
            d = 1 if r == "BULLISH" else -1
            ev.add("STRUCTURE", tf, "trend", d, REGIME_WEIGHT[tf], f"{tf} structure {r.lower()}",
                   f"{tf} swing structure prints {'higher highs and higher lows' if d == 1 else 'lower highs and lower lows'}.", key=f"regime:{tf}")
        elif r == "RANGING":
            ev.add("STRUCTURE", tf, "range", 0, REGIME_WEIGHT[tf] * 0.7, f"{tf} structure ranging", f"{tf} swings overlap without directional sequence.",
                   key=f"regime:{tf}")
    align = structure_alignment(regimes, ovs)

    # ----- Trend Structure -----
    tv = trend_view(a["trend"], a["overview"], price, anchor, ts, ovs)
    if tv.get("available") and tv["direction"]:
        d = 1 if tv["direction"] == "BULLISH" else -1
        ev.add("TREND", tv["analysis_tf"], "trend", d, 0.3 + 0.5 * tv["strength"] / 100, f"{tv['state']['label']}",
               f"Trend strength {tv['strength']}/100, structure sequence {' · '.join(tv['structure_sequence']) or '—'}.", key="trend_dir")
        geo = tv.get("geometry")
        if tv["setup"]["key"] == "CONTINUATION" and geo:
            ev.add("TREND", tv["analysis_tf"], "reaction", d, 0.6, "Pullback inside continuation zone" if geo["status"]["key"] == "IN_ZONE" else "Pullback in trend",
                   f"{geo['depth_pct']:.0f}% retracement of the {tv['analysis_tf']} leg; zone {_f(geo['zone'][0], dp)} – {_f(geo['zone'][1], dp)}.",
                   price=(geo["zone"][0] + geo["zone"][1]) / 2, key="trend_pullback")
        if tv["setup"]["key"] == "REVERSAL_RISK":
            ev.add("TREND", tv["analysis_tf"], "reversal", -d, 0.7, "Trend reversal risk", "; ".join(tv["reversal_reasons"]) or "Reversal conditions present.",
                   key="trend_reversal")

    # ----- BOS / CHoCH (closed breaks in the recent window) -----
    structure_events = {}
    for tf in bos.BOS_TIMEFRAMES:
        c = a["bos"].get(tf) or {}
        events = [e for e in c.get("events", []) if _recent(e["at"], anchor, tf)]
        structure_events[tf] = {"recent": events[-4:], "swing_high": c.get("swing_high"), "swing_low": c.get("swing_low"),
                                "trend": c.get("trend"), "atr": c.get("atr"), "all": c.get("events", [])[-8:]}
        if not events:
            continue
        e = events[-1]
        d = 1 if e["direction"] == "UP" else -1
        kind = "BOS" if e["kind"] == "BOS" else "CHoCH"
        if e.get("failed"):
            ev.add("BOS", tf, "reaction", -d, EVENT_WEIGHT[tf] * 0.45, f"Failed {tf} {kind} {'up' if d == 1 else 'down'}",
                   f"{tf} close back through {_f(e['level'], dp)} — the break was rejected.", price=e["level"], at=e["at"], key=f"bos:{tf}")
            continue
        w = EVENT_WEIGHT[tf] * (1.15 if e.get("body_acceptance") else 1.0)
        role = "trend" if e["kind"] == "BOS" else "reversal"
        accepted = " with body acceptance" if e.get("body_acceptance") else ""
        volume = f"; volume ×{e['volume_ratio']}" if e.get("volume_ratio") else ""
        ev.add("BOS", tf, role, d, w * (1.0 if role == "trend" else 1.2), f"{tf} {'bullish' if d == 1 else 'bearish'} {kind}",
               f"Close through {_f(e['level'], dp)}{accepted}{volume}.", price=e["level"], at=e["at"], key=f"bos:{tf}")

    # ----- Fractals -----
    rv = range_view(a["range_core"], a["range_ltf"], price, rs) if a.get("range_core") else None
    rv = rv if rv and rv.get("available") else None
    fv = frac.fractal_view(a["fractal"], price, regimes, rv, a.get("range_core"), fs)
    if fv.get("available"):
        for side, sign, label in (("support", 1, "support"), ("resistance", -1, "resistance")):
            for cl in fv["clusters"][side][:1]:
                if atr and abs(cl["distance"]) <= 1.6 * atr:
                    ev.add("FRACTAL", "W", "reaction", sign, 0.45 + 0.08 * min(cl["touches"], 4),
                           f"Weekly fractal {label} cluster", f"{cl['touches']} weekly fractals between {_f(cl['lo'], dp)} and {_f(cl['hi'], dp)} "
                           f"({abs(cl['distance_atr'] or 0):.1f} ATR away).", price=(cl["lo"] + cl["hi"]) / 2, key=f"fractal_cluster:{side}")
        for tf in ("W", "D1"):
            v = fv["timeframes"].get(tf) or {}
            for side, f in (v.get("sides") or {}).items():
                if f and f["status"]["key"] in ("CANDIDATE", "DEVELOPING", "PROVISIONAL"):
                    sign = 1 if side == "low" else -1
                    ev.add("FRACTAL", tf, "reaction", sign, (0.45 if tf == "W" else 0.3) * (1.2 if f["status"]["key"] == "PROVISIONAL" else 1.0),
                           f"Developing {f['kind']}", f"{f['kind']} {f['status']['label'].lower()} at {_f(f['price'], dp)} — "
                           f"{'swing low' if sign == 1 else 'swing high'} forming on {tf}.", price=f["price"], at=f["at"], key=f"fractal_dev:{tf}:{side}")

    # ----- Range Structure -----
    core = a.get("range_core") or {}
    if core.get("ranging"):
        ev.add("RANGE", "W", "range", 0, 0.5 + 0.4 * (core.get("quality") or 60) / 100, "Validated weekly range",
               f"Weekly range {_f(core['range_low'], dp)} – {_f(core['range_high'], dp)}, {core['age_weeks']} weeks old, "
               f"{core['touches_high']}/{core['touches_low']} boundary touches.", key="range")
    if rv:
        band = rv["position_band"]["key"]
        if band == "UPPER_EXTREME":
            ev.add("RANGE", "W", "reaction", -1, 0.45, "Upper extreme of weekly range", f"Price {rv['position']:.0f}% of the weekly range.",
                   price=core.get("range_high"), key="range_edge")
        elif band == "LOWER_EXTREME":
            ev.add("RANGE", "W", "reaction", 1, 0.45, "Lower extreme of weekly range", f"Price {rv['position']:.0f}% of the weekly range.",
                   price=core.get("range_low"), key="range_edge")
        elif band == "ABOVE_RANGE":
            ev.add("RANGE", "W", "breakout", 1, 0.6, "Above weekly range", f"Close above the weekly range high {_f(core.get('range_high'), dp)}.",
                   price=core.get("range_high"), key="range_edge")
        elif band == "BELOW_RANGE":
            ev.add("RANGE", "W", "breakout", -1, 0.6, "Below weekly range", f"Close below the weekly range low {_f(core.get('range_low'), dp)}.",
                   price=core.get("range_low"), key="range_edge")

    # ----- Trend-in-Trend -----
    tit = chan.tit_view(symbol, a["channel"], price, cs)
    if tit.get("available"):
        pd = 1 if tit["parent"]["direction"] == "UPTREND" else -1
        if tit.get("setup"):
            st = tit["setup"]
            ev.add("TIT", tit["countertrend"]["tf"], "reaction", pd, 0.3 + 0.5 * st["quality"] / 100,
                   f"{tit['countertrend']['layer']} countertrend {tit['countertrend']['phase'].lower()}",
                   f"{tit['countertrend']['tf']} counter-channel {tit['countertrend']['maturity']}% mature inside the {tit['parent']['tf']} "
                   f"{'up' if pd == 1 else 'down'}trend; continuation zone {_f(st['zone'][0], dp)} – {_f(st['zone'][1], dp)}.",
                   price=(st["zone"][0] + st["zone"][1]) / 2, key="tit_setup")
        else:
            ev.add("TIT", tit["parent"]["tf"], "trend", pd, 0.35, "Channel layers aligned",
                   f"No countertrend layer against the {tit['parent']['tf']} parent channel.", key="tit_aligned")

    # ----- Channel breakouts (walk-forward, frozen lines) -----
    breakouts = []
    for e in chan.live_breakouts(symbol, a["channel"], price, cs):
        if not _recent(e["at"], anchor, e["tf"]):
            continue
        breakouts.append(e)
        d = 1 if e["direction"] == "UP" else -1
        st = e["status"]["key"]
        if st == "FAILED":
            ev.add("CHANNEL", e["tf"], "reaction", -d, EVENT_WEIGHT[e["tf"]] * 0.4, f"Failed {e['tf']} channel breakout",
                   f"{e['label']} at {_f(e['level'], dp)} closed back inside.", price=e["level"], at=e["at"], key=f"breakout:{e['tf']}")
        elif st in ("CONFIRMED", "RETESTING"):
            ev.add("CHANNEL", e["tf"], "breakout", d, EVENT_WEIGHT[e["tf"]] * (1.1 if e["retest"]["key"] == "COMPLETED" else 0.9),
                   f"{e['tf']} {e['label'].lower()}", f"Break of the frozen {e['tf']} channel at {_f(e['level'], dp)}; retest {e['retest']['label'].lower()}.",
                   price=e["level"], at=e["at"], key=f"breakout:{e['tf']}")
    breakouts = breakouts[:6]

    # ----- Strength Intelligence -----
    if strength and strength.get("differential") is not None:
        diff = strength["differential"]
        d = 1 if diff > 0 else -1 if diff < 0 else 0
        if d:
            pct = strength.get("alignment_pct")
            w = min(0.9, abs(diff) / 20) * (0.6 + 0.4 * (pct or 50) / 100)
            ev.add("STRENGTH", "AVG", "trend", d, w, f"{strength['label']}",
                   f"Strength differential {diff:+.1f}{f' ({pct:.0f}% of timeframes aligned)' if pct is not None else ''} at {strength['as_of'][:16]}Z.",
                   key="strength")

    # ----- Supertrend -----
    for tf, st in (a.get("supertrend") or {}).items():
        if st.get("available"):
            d = st["direction"]
            ev.add("SUPERTREND", tf, "trend", d, SUPERTREND_WEIGHT[tf], f"{tf} Supertrend {'up' if d == 1 else 'down'}",
                   f"Price {abs(st['distance_atr'] or 0):.1f} ATR {'above' if d == 1 else 'below'} the {tf} Supertrend line {_f(st['line'], dp)}.",
                   price=st["line"], key=f"supertrend:{tf}")

    # ----- Momentum and volatility -----
    er = ((a["trend"].get("D1") or {}).get("efficiency"))
    if er is not None:
        if abs(er) >= 0.3:
            ev.add("MOMENTUM", "D1", "trend", 1 if er > 0 else -1, 0.3, f"D1 momentum {'positive' if er > 0 else 'negative'}",
                   f"Efficiency ratio {er:+.2f} — directional closes dominate.", key="momentum")
        elif abs(er) < 0.1:
            ev.add("MOMENTUM", "D1", "range", 0, 0.3, "D1 momentum flat", f"Efficiency ratio {er:+.2f} — closes rotate without progress.", key="momentum")
    vol = a.get("volatility") or {}
    if vol.get("key") == "LOW":
        ev.add("VOLATILITY", "D1", "range", 0, 0.25 + (0.1 if vol.get("trend") == "CONTRACTING" else 0), "Volatility compressed",
               f"ATR {vol['ratio']:.2f}× its baseline ({vol.get('trend', '').lower()}).", key="volatility")

    return {
        "symbol": symbol,
        "digits": dp,
        "price": price,
        "anchor": anchor.isoformat(),
        "atr": atr,
        "regimes": regimes,
        "alignment": align,
        "channels": channels,
        "trend": tv if tv.get("available") else None,
        "structure_events": structure_events,
        "fractals": fv if fv.get("available") else None,
        "range": {"core": {k: core.get(k) for k in ("ranging", "range_high", "range_low", "midpoint", "high_zone", "low_zone", "quality", "age_weeks",
                                                     "touches_high", "touches_low", "start", "last_week")} if core else None,
                  "position": rv["position"] if rv else None, "band": rv["position_band"] if rv else None,
                  "breakout_score": ((rv or {}).get("hypotheses") or {}).get("breakout", {}).get("score")},
        "tit": tit,
        "breakouts": breakouts,
        "strength": strength,
        "supertrend": a.get("supertrend") or {},
        "volatility": vol,
        "momentum": er,
        "swings": {tf: (a["trend"].get(tf) or {}).get("swings", []) for tf in ("W", "D1", "H8", "H1")},
        "evidence": ev.items,
    }
