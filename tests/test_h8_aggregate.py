from datetime import datetime, timezone

from apps.api.app.market.h8_aggregate import aggregate_h8_from_h1
from apps.api.app.market.models import Candle


def _h1(i: int, close: float) -> Candle:
    t = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() + i * 3600
    ot = datetime.fromtimestamp(t, tz=timezone.utc)
    return Candle("EURUSD", "H1", ot, ot, close - 0.001, close + 0.001, close - 0.002, close, 1, 0, "TEST", True)


def test_h8_requires_eight_h1_bars():
    h1 = [_h1(i, 1.0 + i * 0.001) for i in range(16)]
    h8 = aggregate_h8_from_h1(h1)
    assert len(h8) == 2
    assert h8[0].timeframe == "H8"
    assert h8[-1].close > h8[0].close


def test_closure_gaps_close_a_bucket_but_the_forming_bucket_waits():
    # Hour 5 missing (gold daily break) in the first bucket; the last bucket has only 3 bars so far.
    h1 = [_h1(i, 1.0 + i * 0.001) for i in range(19) if i != 5]
    h8 = aggregate_h8_from_h1(h1)
    assert [c.open_time.hour for c in h8] == [0, 8]
    assert h8[0].close == h1[6].close
    assert (h8[0].close_time - h8[0].open_time).total_seconds() == 8 * 3600
