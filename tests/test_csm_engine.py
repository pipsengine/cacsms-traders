from apps.api.app.market.csm_engine import (
    compute_matrix,
    is_base_currency,
    pair_contribution,
    populate_matrix_cell,
)
from datetime import datetime, timezone


def test_base_currency_detection():
    assert is_base_currency("EUR", "EURUSD")
    assert not is_base_currency("USD", "EURUSD")


def test_quote_inverts_contribution():
    assert pair_contribution("EUR", "EURUSD", 1.0, 1.01) == 1.0
    assert pair_contribution("USD", "EURUSD", 1.0, 1.01) == -1.0


def test_matrix_cell_sums_pair_contributions():
    pair_closes = {
        "EURUSD": [1.10, 1.11],
        "EURGBP": [0.85, 0.86],
        "EURJPY": [160.0, 161.0],
        "EURCHF": [0.95, 0.96],
        "EURAUD": [1.60, 1.61],
        "EURCAD": [1.45, 1.46],
        "EURNZD": [1.75, 1.76],
    }
    total, used, _ = populate_matrix_cell("EUR", pair_closes, bars_difference=1)
    assert used == 7
    assert total > 0


def test_compute_matrix_includes_avg():
    as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
    tf = "H1"
    pairs = {}
    for p in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"):
        pairs[p] = [1.0, 1.01]
    result = compute_matrix(["H1", "AVG"], {tf: pairs}, bars_difference=1, as_of=as_of)
    assert "AVG" in result.values["EUR"]
    assert result.values["USD"]["H1"] < 0
