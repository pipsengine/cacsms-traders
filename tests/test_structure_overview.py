from datetime import datetime, timedelta, timezone

from apps.api.app.market.scanner_analytics import Bar
from apps.api.app.market.structure_overview import (
    alignment,
    cells_for,
    current_state,
    live_events,
    ltf_regime,
    structure_events,
)
from apps.api.app.market.structure_overview_config import overview_settings

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
H1 = timedelta(hours=1)


def _bars(closes, wick=0.3, step=H1):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append(Bar(T0 + step * i, prev, max(prev, c) + wick, min(prev, c) - wick, c))
        prev = c
    return out


def _zigzag(start, legs, up=4.0, down=2.0, n=4):
    """Rising zigzag (HH/HL) when up > down, falling (LH/LL) when down > up."""
    out, p = [], start
    for _ in range(legs):
        for _ in range(n):
            p += up / n
            out.append(p)
        for _ in range(n):
            p -= down / n
            out.append(p)
    return out


def test_regime_from_swing_structure():
    s = overview_settings()
    assert ltf_regime(_bars(_zigzag(100, 10)), s) == "BULLISH"
    assert ltf_regime(_bars(_zigzag(100, 10, up=2.0, down=4.0)), s) == "BEARISH"
    assert ltf_regime(_bars([100.0] * 3), s) is None


def test_pullback_cell_and_alignment_score():
    s = overview_settings()
    regimes = {"W": "BULLISH", "D1": "BULLISH", "H8": "BEARISH", "H1": "BULLISH"}
    cells = cells_for(regimes)
    assert cells["H8"]["key"] == "PULLBACK"
    assert cells["H1"]["key"] == "BULL"
    assert alignment({"W": "BULLISH", "D1": "BULLISH", "H8": "BULLISH", "H1": "BULLISH"}, s)["score"] == 100
    assert alignment({"W": "BEARISH", "D1": "BEARISH", "H8": "BEARISH", "H1": "BEARISH"}, s)["score"] == 0
    mixed = alignment({"W": "RANGING", "D1": "BULLISH", "H8": "BULLISH", "H1": "TRANSITION"}, s)
    assert mixed["score"] == 75 and mixed["key"] == "BULLISH"


def test_current_state_rules():
    trend = {"W": "BULLISH", "D1": "BULLISH", "H8": "BULLISH", "H1": "BULLISH"}
    assert current_state(trend, cells_for(trend), None)["key"] == "TRENDING"
    pull = {**trend, "H8": "BEARISH"}
    assert current_state(pull, cells_for(pull), None)["key"] == "CONTINUATION"
    rev = {**trend, "D1": "BEARISH"}
    assert current_state(rev, cells_for(rev), None)["key"] == "REVERSAL"
    rng = {**trend, "W": "RANGING"}
    assert current_state(rng, cells_for(rng), "UPPER_EXTREME")["key"] == "REACTION"
    assert current_state(rng, cells_for(rng), "MID_RANGE")["key"] == "ROTATION"
    assert current_state(rng, cells_for(rng), "ABOVE_RANGE")["key"] == "BREAKOUT"


def test_bos_then_choch_on_closed_bars():
    closes = _zigzag(100, 8) + [p for p in (114, 112, 110, 108, 106, 104, 102, 100)]
    ev = structure_events(_bars(closes), "H1", 2)
    kinds = [(e["kind"], e["direction"]) for e in ev["events"]]
    assert ("BOS", "UP") in kinds
    assert kinds[-1] == ("CHOCH", "DOWN")
    assert all(not e["failed"] for e in ev["events"][-1:])


def test_live_break_is_developing_never_confirmed():
    s = overview_settings()
    bars = _bars(_zigzag(100, 8))
    ev = structure_events(bars, "H1", 2)
    core = {"events": {"H1": ev}, "anchor": (bars[-1].t + H1).isoformat()}
    assert ev["swing_high"] is not None
    now = bars[-1].t + 2 * H1
    out = live_events(core, ev["swing_high"] + 1.0, now, s)
    dev = [e for e in out if e["status"]["key"] == "DEVELOPING"]
    assert dev and dev[0]["direction"] == "UP"
    assert all(e["status"]["key"] != "DEVELOPING" for e in live_events(core, ev["swing_high"] - 0.5, now, s) if e["at"] != now.isoformat())
