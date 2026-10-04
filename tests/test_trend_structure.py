import json
from datetime import datetime, timedelta, timezone

from apps.api.app.market.scanner_analytics import Bar
from apps.api.app.market.structure_overview import structure_events
from apps.api.app.market.structure_overview_config import overview_settings
from apps.api.app.market.trend_structure import trend_core, trend_events, trend_view
from apps.api.app.market.trend_structure_config import trend_settings

T0 = datetime(2025, 1, 6, tzinfo=timezone.utc)
STEP = {"W1": timedelta(days=7), "D1": timedelta(days=1), "H8": timedelta(hours=8), "H1": timedelta(hours=1)}
OV_TF = {"W1": "W", "D1": "D1", "H8": "H8", "H1": "H1"}


def _bars(closes: list[float], step: timedelta, wick: float = 0.0002) -> list[Bar]:
    start = T0
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


def _zigzag(legs: int, sign: int = 1) -> list[float]:
    pts = []
    for k in range(legs):
        pts += [1.0 + sign * 0.004 * k, 1.0 + sign * (0.004 * k + 0.010)]
    return pts


def _universe(closes: list[float]) -> dict[str, list[Bar]]:
    return {k: _bars(closes, step) for k, step in STEP.items()}


def _overview(bars: dict[str, list[Bar]], regimes: dict[str, str]) -> dict:
    s = overview_settings()
    events = {OV_TF[k]: structure_events(b, OV_TF[k], s.fractal_strength, s.atr_period) for k, b in bars.items()}
    h1 = bars["H1"]
    return {"regimes": regimes, "events": events, "anchor": (h1[-1].t + STEP["H1"]).isoformat(), "changes": []}


BULL = {"W": "BULLISH", "D1": "BULLISH", "H8": "BULLISH", "H1": "BULLISH"}
NOW = datetime(2030, 1, 1, tzinfo=timezone.utc)


def _view(closes, regimes, price=None):
    bars = _universe(closes)
    s, ovs = trend_settings(), overview_settings()
    core = trend_core(bars, s)
    ov = _overview(bars, regimes)
    return core, ov, trend_view(core, ov, price, NOW, s, ovs)


def test_aligned_uptrend_classified_with_higher_highs_and_lows():
    closes = _path(_zigzag(14), 5)
    _, _, v = _view(closes, BULL)
    assert v["available"] and v["direction"] == "BULLISH"
    assert v["state"]["key"] in ("STRONG_UPTREND", "UPTREND", "UPTREND_PULLBACK")
    assert v["structure_sequence"] and set(v["structure_sequence"]) <= {"HH", "HL"}
    assert v["components"]["structure"] == 100
    assert v["components"]["channel"] == 100
    assert v["age_weeks"] is not None and v["age_weeks"] > 0
    assert 0 <= v["strength"] <= 100
    assert v["closed_bar_only"] is True


def test_lower_timeframe_against_trend_is_pullback():
    closes = _path(_zigzag(14), 5)
    _, _, v = _view(closes, {**BULL, "H8": "BEARISH"})
    assert v["cells"]["H8"]["key"] == "PULLBACK"
    assert v["state"]["key"] == "UPTREND_PULLBACK"
    assert "H8" in v["pullback_cells"]


def test_mixed_regimes_have_no_trend_and_no_setup():
    closes = _path(_zigzag(14), 5)
    _, _, v = _view(closes, {"W": "RANGING", "D1": "BEARISH", "H8": "BULLISH", "H1": "TRANSITION"})
    assert v["direction"] is None
    assert v["state"]["key"] == "RANGING"
    assert v["setup"]["key"] == "NO_TREND"
    assert v["confidence"] == 0 and v["geometry"] is None


def test_pullback_geometry_and_invalidation_from_live_price():
    closes = _path(_zigzag(14), 5)
    _, _, v = _view(closes, BULL)
    geo = v["geometry"]
    assert geo is not None and geo["leg_extreme"] > geo["leg_start"]
    lo, hi = geo["zone"]
    assert geo["leg_start"] < lo < hi < geo["leg_extreme"]
    assert geo["objective_2"] > geo["objective_1"]
    _, _, broken = _view(closes, BULL, price=geo["invalidation"] - 0.001)
    assert broken["geometry"]["status"]["key"] == "INVALIDATED"
    assert broken["setup"]["key"] == "REVERSAL_RISK"
    assert broken["closed_bar_only"] is False


def test_developing_breaks_only_in_live_view():
    closes = _path(_zigzag(14), 5)
    core, ov, _ = _view(closes, BULL)
    s, ovs = trend_settings(), overview_settings()
    closed = trend_events(core, ov, None, NOW, s, ovs)
    assert all(e["status"]["key"] != "DEVELOPING" for e in closed)
    live = trend_events(core, ov, 5.0, NOW, s, ovs)
    assert any(e["status"]["key"] == "DEVELOPING" for e in live) or all(
        ov["events"][tf]["swing_high"] is None for tf in ("D1", "H8", "H1")
    )


def test_output_never_contains_trade_instructions():
    closes = _path(_zigzag(14, sign=-1), 5)
    core, ov, v = _view(closes, {k: "BEARISH" for k in BULL})
    assert v["direction"] == "BEARISH"
    text = json.dumps(v, default=str).upper()
    assert "BUY" not in text and "SELL" not in text
