from datetime import datetime, timedelta, timezone

from apps.api.app.market.scanner_analytics import (
    Bar,
    channel_zone,
    inspection_score,
    market_structure,
    reasons,
    regression_channel,
    session_for,
    status_for,
    structure_agrees,
    volatility,
)
from apps.api.app.market.scanner_config import SCANNER_UNIVERSE, instrument_name, settings

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _bars(closes, spread=0.5):
    return [Bar(T0 + timedelta(days=i), c, c + spread, c - spread, c) for i, c in enumerate(closes)]


def _zigzag(start, step, legs, leg_len=4, drift=1.0):
    """Swings with rising (drift>0) or falling (drift<0) highs and lows."""
    out, price = [], start
    for k in range(legs):
        direction = 1 if k % 2 == 0 else -1
        move = step + (drift if direction == 1 else -drift)
        for _ in range(leg_len):
            price += direction * move / leg_len
            out.append(price)
    return out


def test_universe_is_gold_plus_28_fx():
    assert SCANNER_UNIVERSE[0] == "XAUUSD"
    assert len(SCANNER_UNIVERSE) == 29
    assert instrument_name("XAUUSD") == "Gold vs US Dollar"


def test_structure_bullish_and_bearish():
    up = market_structure(_bars(_zigzag(100, 4, 12, drift=1.0)), 2)
    down = market_structure(_bars(_zigzag(100, 4, 12, drift=-1.0)), 2)
    assert up["key"] == "BULLISH"
    assert down["key"] == "BEARISH"
    assert market_structure(_bars([1.0, 1.1]), 2)["key"] == "INSUFFICIENT"


def test_channel_zones_and_position():
    assert channel_zone(1.2)[0] == "ABOVE"
    assert channel_zone(0.85)[0] == "NEAR_UPPER"
    assert channel_zone(0.5)[0] == "MID"
    assert channel_zone(0.1)[0] == "NEAR_LOWER"
    assert channel_zone(-0.1)[0] == "BELOW"
    closes = [100 + i * 0.1 + (0.3 if i % 2 else -0.3) for i in range(60)]
    ch = regression_channel(_bars(closes), 50, 2.0)
    assert ch["direction"] == "ASCENDING"
    assert ch["lower"] < ch["mid"] < ch["upper"]
    assert regression_channel(_bars(closes), 50, 2.0, price=ch["upper"] + 1)["key"] == "ABOVE"
    assert regression_channel(_bars(closes[:10]), 50, 2.0)["key"] == "INSUFFICIENT"


def test_volatility_regime():
    calm = _bars([100.0] * 120, spread=0.5)
    wild = calm[:-20] + _bars([100.0] * 20, spread=3.0)
    assert volatility(calm, 14, 100, 0.8, 1.25)["key"] == "NORMAL"
    assert volatility(wild, 14, 100, 0.8, 1.25)["key"] == "HIGH"
    assert volatility(calm[:50], 14, 100, 0.8, 1.25)["key"] == "INSUFFICIENT"


def test_score_renormalizes_missing_components():
    s = settings()
    full = inspection_score(
        s, abs_differential=40, structure_key="BULLISH", agrees=True, channel_position=1.0, vol_key="HIGH", alignment_pct=100
    )
    assert full["score"] == 100
    gold = inspection_score(
        s, abs_differential=None, structure_key="BULLISH", agrees=None, channel_position=1.0, vol_key="HIGH", alignment_pct=None
    )
    assert gold["components"]["strength"] is None
    assert 0 < gold["score"] <= 100
    assert status_for(full["score"], s)["key"] == "HIGH_INSPECTION"
    assert status_for(60, s)["key"] == "WATCHING"
    assert status_for(10, s)["key"] == "NEUTRAL"


def test_structure_agreement_and_reasons_have_no_trade_language():
    assert structure_agrees("BULLISH", 12.0) is True
    assert structure_agrees("BEARISH", 12.0) is False
    assert structure_agrees("RANGE", 12.0) is None
    text = " ".join(
        reasons(
            base="EUR",
            quote="JPY",
            differential=-25.0,
            quote_only_score=None,
            structure={"key": "BEARISH", "label": "Bearish", "event": None},
            structure_tf="D1",
            channel={"key": "NEAR_LOWER", "label": "Near Lower"},
            vol={"key": "HIGH", "ratio": 1.4},
            alignment={"aligned": 8, "total": 10},
        )
    ).lower()
    assert "jpy strength vs eur weakness" in text
    for word in ("buy", "sell", "long", "short", "entry"):
        assert word not in text


def test_session_labels():
    assert session_for(datetime(2026, 10, 3, 12, tzinfo=timezone.utc)) == "Closed (weekend)"
    assert session_for(datetime(2026, 10, 5, 13, tzinfo=timezone.utc)) == "London / New York"
    assert session_for(datetime(2026, 10, 5, 2, tzinfo=timezone.utc)) == "Asian"
