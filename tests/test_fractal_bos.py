import json
from datetime import datetime, timedelta, timezone

from apps.api.app.market import bos_choch as bos
from apps.api.app.market import fractal_structure as frac
from apps.api.app.market.scanner_analytics import Bar

T0 = datetime(2025, 1, 6, tzinfo=timezone.utc)
H1 = timedelta(hours=1)
W = timedelta(days=7)


def _bars(closes: list[float], step: timedelta = H1, wick: float = 0.0002, vols: list[float] | None = None) -> list[Bar]:
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        v = vols[i] if vols else 100.0
        out.append(Bar(T0 + step * i, prev, max(prev, c) + wick, min(prev, c) - wick, c, v))
        prev = c
    return out


def _zigzag(legs: int, top: float = 1.010, bottom: float = 1.000, leg: int = 5) -> list[float]:
    pts = []
    for _ in range(legs):
        pts += [bottom + (top - bottom) * k / leg for k in range(leg)]
        pts += [top - (top - bottom) * k / leg for k in range(leg)]
    return pts


S = frac.FractalSettings(fractal_strength=2, active_bars=3, away_atr=0.25, cluster_atr=0.5, cluster_lookback=156,
                         cluster_min=2, near_cluster_atr=2.0)


# ----- fractals -----


def test_confirmed_fractals_need_closed_bars_on_both_sides():
    closes = _zigzag(6)
    core = frac.tf_core(_bars(closes), "H1", S)
    assert core["available"]
    highs = [f for f in core["confirmed"] if f["side"] == "HIGH"]
    lows = [f for f in core["confirmed"] if f["side"] == "LOW"]
    assert highs and lows
    assert all(f["kind"] == "FH" for f in highs) and all(f["kind"] == "FL" for f in lows)
    assert all(f["index"] + S.fractal_strength < core["size"] for f in core["confirmed"])


def test_weekly_fractals_are_labelled_and_clustered():
    core = frac.tf_core(_bars(_zigzag(6), W), "W", S)
    assert {f["kind"] for f in core["confirmed"]} <= {"WFH", "WFL"}
    highs = [c for c in core["clusters"] if c["side"] == "HIGH"]
    assert highs and max(c["touches"] for c in highs) >= 2


def test_new_extreme_is_pending_and_staged_by_live_price():
    closes = _zigzag(4) + [1.006, 1.012, 1.016]
    core = frac.tf_core(_bars(closes), "H1", S)
    pend = [f for f in core["pending"] if f["side"] == "HIGH"]
    assert pend and pend[-1]["right"] == 0
    top = pend[-1]["price"]
    assert frac.active_fractals(core, top - 0.00001, S)["HIGH"]["status"] == "CANDIDATE"
    assert frac.active_fractals(core, top - 10 * core["atr"], S)["HIGH"]["status"] == "DEVELOPING"
    assert frac.active_fractals(core, top + 0.001, S)["HIGH"]["status"] == "INVALID"


def test_candidate_taken_out_inside_confirmation_window_is_rejected():
    closes = _zigzag(4) + [1.006 + 0.002 * k for k in range(8)]
    core = frac.tf_core(_bars(closes), "H1", S)
    assert any(f["side"] == "HIGH" for f in core["rejected"])
    marks = frac.fractal_marks({"H1": core}, "H1")
    assert {m["status"] for m in marks} >= {"CONFIRMED", "INVALID"}


def test_fractal_view_builds_hierarchy_around_price():
    w = _bars(_zigzag(6), W)
    d1 = _bars(_zigzag(6), timedelta(days=1))
    h = _bars(_zigzag(6))
    core = frac.fractal_core({"W1": w, "D1": d1, "H8": h, "H1": h}, S)
    v = frac.fractal_view(core, 1.005, {"W": "RANGING"}, None, None, S)
    assert v["available"]
    prices = [x["price"] for x in v["hierarchy"]]
    assert prices == sorted(prices, reverse=True)
    assert any(x["kind"] == "PRICE" for x in v["hierarchy"])
    assert [x["tf"] for x in v["ltf"]] == list(frac.FRACTAL_TIMEFRAMES)
    assert [x["key"] for x in v["lifecycle"]] == [k for k, _ in frac.LIFECYCLE]


# ----- BOS / CHoCH -----

BS = bos.BosSettings(retest_atr=0.3, body_atr=0.1, volume_ratio=1.2, volume_bars=20, monitor_atr=1.0,
                     key_level_atr=0.5, lookback_days=30)


def _break_series():
    # Flat base, a high-volume break above 1.0100, pullback into the level, then a close above the retest bar.
    closes = [1.0050 + 0.0005 * ((k % 4) - 2) for k in range(30)] + [1.0130, 1.0120, 1.0102, 1.0125, 1.0140]
    vols = [100.0] * 30 + [300.0, 100.0, 100.0, 100.0, 100.0]
    return _bars(closes, vols=vols), 30


def _ev(bars, k, kind="BOS", direction="UP", level=1.0100):
    return {"atr": 0.002, "events": [{"tf": "H1", "kind": kind, "direction": direction, "level": level,
                                      "at": (bars[k].t + H1).isoformat(), "break_at": bars[k].t.isoformat(),
                                      "index": k, "failed": False}]}


def test_enrich_measures_body_volume_retest_and_follow_through():
    bars, k = _break_series()
    (e,) = bos.enrich(bars, _ev(bars, k), "H1", BS)
    assert e["label"] == "Bullish BOS" and "index" not in e
    assert e["close"] == bars[k].c and e["body_acceptance"] is True
    assert e["volume_ratio"] == 3.0
    assert e["retest_at"] is not None and e["retest_completed_at"] is not None
    assert e["follow_through_atr"] > 0 and e["bars_since"] == len(bars) - 1 - k


def test_status_reflects_live_price_against_broken_level():
    bars, k = _break_series()
    (e,) = bos.enrich(bars, _ev(bars, k), "H1", BS)
    assert bos._status(e, 1.0101, 0.002, BS) == ("RETESTING", "RETESTING")
    assert bos._status(e, 1.0200, 0.002, BS) == ("CONFIRMED", "COMPLETED")
    assert bos._status({**e, "failed": True}, 1.0200, 0.002, BS)[0] == "FAILED"
    fresh = {**e, "retest_at": None, "retest_completed_at": None}
    assert bos._status(fresh, 1.0115, 0.002, BS) == ("MONITORING", "PENDING")


def test_live_events_add_developing_break_only_with_price():
    bars, k = _break_series()
    core = {tf: {"events": [], "atr": 0.002, "swing_high": None, "swing_low": None, "trend": 0} for tf in bos.BOS_TIMEFRAMES}
    core["H1"] = {"events": bos.enrich(bars, _ev(bars, k), "H1", BS), "atr": 0.002, "swing_high": 1.0145,
                  "swing_low": 1.0000, "trend": 1}
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    closed = bos.live_events(core, None, now, BS)
    assert closed and all(e["closed"] for e in closed)
    live = bos.live_events(core, 1.0150, now, BS)
    dev = [e for e in live if not e["closed"]]
    assert dev and dev[0]["label"] == "Bullish BOS" and dev[0]["status"]["key"] == "DEVELOPING"
    core["H1"]["trend"] = -1
    assert [e for e in bos.live_events(core, 1.0150, now, BS) if not e["closed"]][0]["kind"] == "CHOCH"


def test_bos_output_never_contains_trade_instructions():
    bars, k = _break_series()
    text = json.dumps(bos.enrich(bars, _ev(bars, k, direction="DOWN", level=1.0200), "H1", BS)).upper()
    assert "BUY" not in text and "SELL" not in text
