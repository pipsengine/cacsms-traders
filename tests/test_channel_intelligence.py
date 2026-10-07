import json
import math
from datetime import datetime, timedelta, timezone

from apps.api.app.market import channel_intelligence as chan
from apps.api.app.market.scanner_analytics import Bar, regression_channel

T0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
S = chan.channel_settings()


def _bars(closes: list[float], step: timedelta, start: datetime = T0, wick: float = 0.0003) -> list[Bar]:
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append(Bar(start + step * i, prev, max(prev, c) + wick, min(prev, c) - wick, c, 100.0))
        prev = c
    return out


def _wave(n: int, slope: float, amp: float = 0.005, base: float = 1.0, period: float = 12.0) -> list[float]:
    return [base + slope * i + amp * math.sin(2 * math.pi * i / period) for i in range(n)]


def test_prefix_sum_fit_matches_regression_channel():
    closes = _wave(90, 0.0007)
    bars = _bars(closes, timedelta(hours=1))
    slope, mid, sd = chan._Fits(closes).fit(30, 90)
    ref = regression_channel(bars[30:], 60, 2.0)
    assert math.isclose(mid, ref["mid"], rel_tol=1e-9)
    assert math.isclose(mid + 2 * sd, ref["upper"], rel_tol=1e-9)


def test_calendar_aggregates_and_ytd_window():
    mn = [Bar(datetime(2024 + (m // 12), m % 12 + 1, 1, tzinfo=timezone.utc), 1 + m, 2 + m, 0.5 + m, 1.5 + m, 10)
          for m in range(24)]
    years = chan.aggregate(mn, 12)
    assert [b.t.year for b in years] == [2024, 2025]
    assert years[0].o == 1 and years[0].c == 12.5 and years[0].h == 13 and years[0].l == 0.5 and years[0].v == 120
    quarters = chan.aggregate(mn, 3)
    assert len(quarters) == 8 and quarters[1].t.month == 4
    d1 = _bars(_wave(400, 0.0), timedelta(days=1))
    ytd = chan.ytd_bars(d1)
    assert ytd and all(b.t.year == d1[-1].t.year for b in ytd)


def _spiky(closes: list[float], step: timedelta, spike: float = 0.006) -> list[Bar]:
    """Wave bars whose peaks and troughs wick out to the channel boundaries."""
    out = []
    for b, i in zip(_bars(closes, step), range(len(closes))):
        hi = b.h + spike if i % 12 == 3 else b.h
        lo = b.l - spike if i % 12 == 9 else b.l
        out.append(Bar(b.t, b.o, hi, lo, b.c, b.v))
    return out


def test_rising_channel_is_ascending_valid_with_touches():
    core = chan.tf_core(_spiky(_wave(120, 0.001), timedelta(days=1)), "D1", S)
    assert core["available"] and core["direction"] == "ASCENDING"
    assert core["validity"]["key"] == "VALID"
    assert core["touches_upper"] >= 2 and core["touches_lower"] >= 2
    assert core["lower"] < core["mid"] < core["upper"]
    v = chan.tf_view({"D1": core}, "D1", core["mid"], S)
    assert v["direction"]["key"] == "UPTREND" and 40 <= v["position"] <= 60
    assert v["state"]["key"] == "ACTIVE"


def test_walk_forward_breakout_and_retest_never_look_ahead():
    closes = _wave(100, 0.0005) + [1.075, 1.080, 1.082, 1.0595, 1.085, 1.090]
    bars = _bars(closes, timedelta(hours=1))
    core = chan.tf_core(bars, "H1", S)
    ups = [b for b in core["breakouts"] if b["direction"] == "UP"]
    assert len(ups) == 1
    b = ups[-1]
    assert b["bar_at"] == bars[100].t.isoformat()
    assert b["confirmed"] and b["closes_beyond"] >= S.confirm_closes
    assert b["close"] > b["level"]
    assert b["retest_bar_at"] == bars[103].t.isoformat()
    assert b["completed_at"] is not None and not b["failed"]
    early = chan.tf_core(bars[:101], "H1", S)
    same = [x for x in early["breakouts"] if x["bar_at"] == b["bar_at"]]
    assert same and math.isclose(same[0]["level"], b["level"], rel_tol=1e-12)


def test_breakout_status_against_live_price():
    b = {"direction": "UP", "failed": False, "confirmed": True, "_line_now": 1.08, "retest_at": None, "completed_at": None}
    assert chan.breakout_status(b, 1.0801, 0.002, S) == ("RETESTING", "TESTING")
    assert chan.breakout_status(b, 1.09, 0.002, S) == ("CONFIRMED", "PENDING")
    assert chan.breakout_status({**b, "completed_at": "x", "retest_at": "x"}, 1.09, 0.002, S) == ("CONFIRMED", "COMPLETED")
    assert chan.breakout_status({**b, "failed": True}, 1.07, 0.002, S)[0] == "FAILED"
    assert chan.breakout_status({**b, "retest_at": "x"}, 1.07, 0.002, S) == ("INSIDE", "TESTING")


def _universe():
    h1 = _bars(_wave(120, 0.0004), timedelta(hours=1), datetime(2026, 3, 1, tzinfo=timezone.utc))
    return {
        "MN": _bars(_wave(120, 0.002, period=6), timedelta(days=30)),
        "W1": _bars(_wave(120, 0.002), timedelta(days=7)),
        "D1": _bars(_wave(120, -0.001), timedelta(days=1)),
        "H8": _bars(_wave(120, 0.0006), timedelta(hours=8)),
        "H1": h1,
    }


def test_trend_in_trend_finds_countertrend_layer_and_setup():
    bars = _universe()
    core = chan.channel_core(bars, S)
    v = chan.tit_view("EURUSD", core, None, S)
    assert v["available"] and v["parent"]["layer"] == "L1" and v["parent"]["direction"] == "UPTREND"
    assert v["tit_layer"] == "L2" and v["charts"] == {"L1": "W", "CT": "D1", "EXEC": "H8"}
    layers = {l["id"]: l for l in v["layers"]}
    assert layers["L2"]["alignment"] == "Countertrend" and layers["L3"]["alignment"] == "With L1"
    ct = v["countertrend"]
    assert 0 <= ct["maturity"] <= 100 and ct["type"] == "Pullback Channel"
    setup = v["setup"]
    assert setup["zone"][0] <= setup["zone"][1]
    assert setup["objective_2"] >= setup["objective_1"] or setup["objective_2"] > setup["invalidation"]
    assert [s["label"] for s in v["lifecycle"]][-2] == "Handoff to Opportunity Engine"


def test_aligned_layers_report_no_countertrend():
    bars = _universe()
    bars["D1"] = _bars(_wave(120, 0.001), timedelta(days=1))
    bars["H8"] = _bars(_wave(120, 0.0006), timedelta(hours=8))
    bars["H1"] = _bars(_wave(120, 0.0004), timedelta(hours=1))
    v = chan.tit_view("EURUSD", chan.channel_core(bars, S), None, S)
    assert v["state"]["key"] == "ALIGNED" and v["countertrend"] is None


def test_channel_detail_scenarios_and_language():
    core = chan.channel_core(_universe(), S)
    d = chan.channel_detail(core, None, "W", S)
    assert d["available"] and d["view"]["direction"]["key"] == "UPTREND"
    sc = d["scenarios"]
    assert sc["continue"] + sc["breakout"] + sc["reversal"] == 100
    assert d["alignment"]["total"] >= 5
    assert d["key_levels"]["upper_ext_2"] > d["key_levels"]["upper"] > d["key_levels"]["mid"] > d["key_levels"]["lower"]
    text = json.dumps([d, chan.tit_view("EURUSD", core, None, S)], default=str).upper()
    assert "BUY" not in text and "SELL" not in text
