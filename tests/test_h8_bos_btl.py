from datetime import datetime, timedelta, timezone

from apps.api.app.market.h8_bos_btl import h1_validation, h8_core, m30_confirmation, sch_series
from apps.api.app.market.h8_bos_btl_config import h8_bos_btl_settings
from apps.api.app.market.scanner_analytics import Bar

T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _bars(closes: list[float], step: timedelta, wick: float = 0.0002, start: datetime = T0) -> list[Bar]:
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append(Bar(start + step * i, prev, max(prev, c) + wick, min(prev, c) - wick, c))
        prev = c
    return out


def _path(points: list[float], leg: int) -> list[float]:
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        out += [a + (b - a) * k / leg for k in range(1, leg + 1)]
    return out


def _ascending(legs: int = 10) -> list[float]:
    pts = []
    for k in range(legs):
        pts += [1.0 + 0.002 * k, 1.006 + 0.002 * k]
    return pts


def test_composite_bos_btl_on_closed_bar_break():
    s = h8_bos_btl_settings()
    pts = _ascending()
    last_low = pts[-2]
    closes = _path(pts, 6) + _path([pts[-1], last_low - 0.003], 6)[1:]
    core = h8_core(_bars(closes, timedelta(hours=8)), s)
    ev = core["event"]
    assert ev is not None
    assert ev["kind"] == "BOS + BTL"
    assert ev["direction"] == "Bearish"
    assert abs(ev["bos"]["level"] - (last_low - 0.0002)) < 1e-9
    assert ev["btl"]["line"] and ev["invalidation"] > ev["retest"][1]
    assert "Closed H8 bar" in ev["bos"]["proof"]
    assert core["structure"].endswith("(Broken)")


def test_wick_below_swing_is_not_bos():
    s = h8_bos_btl_settings()
    pts = _ascending()
    last_low = pts[-2]
    closes = _path(pts, 6)
    bars = _bars(closes, timedelta(hours=8))
    t = bars[-1].t + timedelta(hours=8)
    bars.append(Bar(t, closes[-1], closes[-1], last_low - 0.002, closes[-1] - 0.0005))
    core = h8_core(bars, s)
    assert all(e["direction"] != "Bearish" for e in core["history"]["bos"])


def test_sch_bounded_and_separate_from_price():
    s = h8_bos_btl_settings()
    closes = _path(_ascending(14), 4)
    bars = _bars(closes, timedelta(days=7))
    series = sch_series(bars, s)
    vals = [v for v in series if v is not None]
    assert len(series) == len(bars) and vals
    assert all(0.0 <= f <= 100.0 and 0.0 <= g <= 100.0 for f, g in vals)


def test_h1_validation_lh_then_ll():
    s = h8_bos_btl_settings()
    at = T0 + timedelta(hours=30)
    pre = _bars([1.010] * 30, timedelta(hours=1))
    post = _bars(_path([1.010, 1.004, 1.007, 1.001], 6), timedelta(hours=1), start=at)
    ev = {"direction": "Bearish", "invalidation": 1.012, "at": at.isoformat(), "retest": [1.008, 1.009]}
    out = h1_validation(pre + post[1:], ev, s)
    assert out["status"]["key"] == "CONFIRMED"
    assert out["structure"] == "LH → LL"


def test_m30_retest_reaction_and_ltf_confirmation():
    s = h8_bos_btl_settings()
    at = T0 + timedelta(hours=15)
    pre = _bars([1.010] * 30, timedelta(minutes=30))
    post = _bars(_path([1.006, 1.005, 1.0085, 1.0065, 1.003], 4), timedelta(minutes=30), wick=0.0001, start=at)
    ev = {"direction": "Bearish", "invalidation": 1.012, "at": at.isoformat(), "retest": [1.008, 1.009]}
    out = m30_confirmation(pre + post[1:], ev, s)
    assert out["status"]["key"] == "LTF_CONFIRMED"
    assert [m["label"] for m in out["markers"]] == ["Retest", "Reaction", "LTF BOS"]
