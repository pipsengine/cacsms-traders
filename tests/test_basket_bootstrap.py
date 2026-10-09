from apps.api.app.market.strength_engine import StrengthEngine


def test_soft_stale_sync_does_not_block_bootstrap():
    eng = StrengthEngine()
    assert not eng._sync_result_blocking({"symbol": "EURUSD", "timeframe": "H1", "accepted": 0, "error": "stale_candles"})
    assert not eng._sync_result_blocking({"symbol": "EURUSD", "timeframe": "H1", "accepted": 0, "error": "missing_candles"})


def test_hard_sync_errors_block():
    eng = StrengthEngine()
    assert eng._sync_result_blocking({"symbol": "EURUSD", "timeframe": "H1", "accepted": 0, "error": "invalid_candles"})
    assert eng._sync_result_blocking({"symbol": "EURUSD", "timeframe": "H1", "accepted": 0, "error": None})
