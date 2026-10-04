from datetime import datetime, timedelta, timezone

from apps.api.app.market.range_structure import (
    developing_fractals,
    ltf_context,
    position_band,
    range_view,
    weekly_range,
)
from apps.api.app.market.range_structure_config import range_settings
from apps.api.app.market.scanner_analytics import Bar

T0 = datetime(2024, 1, 7, tzinfo=timezone.utc)


def _bars(closes, wick=0.6, step=timedelta(weeks=1)):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(Bar(T0 + step * i, o, max(o, c) + wick, min(o, c) - wick, c))
        prev = c
    return out


def _oscillate(lo, hi, weeks, leg=5):
    out, up, p = [], True, lo
    span = (hi - lo) / leg
    for _ in range(weeks):
        p = p + span if up else p - span
        if p >= hi:
            p, up = hi, False
        elif p <= lo:
            p, up = lo, True
        out.append(p)
    return out


def test_detects_weekly_range_with_fractal_cluster_boundaries():
    w = _bars([105.0] * 20 + _oscillate(100.0, 110.0, 60))
    core = weekly_range(w, range_settings())
    assert core["regime"]["key"] == "RANGING"
    assert core["touches_high"] >= 2 and core["touches_low"] >= 2
    assert 109 <= core["range_high"] <= 111.5
    assert 98.5 <= core["range_low"] <= 101
    assert core["quality"] is not None and 0 <= core["quality"] <= 100


def test_trend_is_not_a_range():
    closes = []
    p = 100.0
    for k in range(80):
        p += 3.0 if k % 6 < 4 else -2.0
        closes.append(p)
    core = weekly_range(_bars(closes), range_settings())
    assert core["regime"]["key"] != "RANGING"
    assert core["quality"] is None


def test_sustained_close_outside_breaks_the_range():
    closes = _oscillate(100.0, 110.0, 60) + [96.0, 94.0, 92.0]
    core = weekly_range(_bars(closes), range_settings())
    assert not (core["ranging"] and core["range_low"] <= 100.5 and core["age_weeks"] > 40)


def test_developing_fractal_needs_confirmation_bars():
    w = _bars([105, 104, 103, 102, 100])
    dev = developing_fractals(w, 2)
    assert dev and dev[0]["kind"] == "WFL" and dev[0]["bars_to_confirm"] == 2


def test_position_bands():
    assert position_band(10)["key"] == "LOWER_EXTREME"
    assert position_band(50)["key"] == "MID_RANGE"
    assert position_band(90)["key"] == "UPPER_EXTREME"
    assert position_band(-5)["key"] == "BELOW_RANGE"
    assert position_band(105)["key"] == "ABOVE_RANGE"


def test_view_at_range_low_reports_reversal_evidence_without_trade_language():
    s = range_settings()
    w = _bars([105.0] * 20 + _oscillate(100.0, 110.0, 60))
    core = weekly_range(w, s)
    d1 = _bars([100 + (i % 5) * 0.3 for i in range(80)], wick=0.2, step=timedelta(days=1))
    view = range_view(core, ltf_context(d1, d1, d1, s), core["range_low"] + 0.5, s)
    assert view["position_band"]["key"] == "LOWER_EXTREME"
    assert view["fractal_kind"] == "WFL"
    assert next(e for e in view["evidence"] if e["key"] == "near_boundary")["met"]
    assert view["workflow"][0]["done"] and view["workflow"][1]["done"]
    assert not view["workflow"][-1]["done"]
    assert view["hypotheses"]["reversal"]["direction"] == "UP"
    text = (view["decision"]["narrative"] + view["decision"]["title"] + view["decision"]["subtitle"]).lower()
    for word in ("buy", "sell", "entry", "long ", "short "):
        assert word not in text
