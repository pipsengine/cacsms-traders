from apps.api.app.market.csm_engine import (
    apply_live_endpoints,
    stamp_forming_bids,
    compute_matrix,
    is_base_currency,
    overlay_forming_closes,
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


def test_forming_close_matches_earnforex_shift_zero():
    """iClose(0) is the bid; iClose(1) is the previous close. Closed-only series are one bar behind."""
    closed = {"D1": {"EURUSD": [1.10, 1.11]}}
    live = overlay_forming_closes(closed, {"EURUSD": 1.12})
    assert live["D1"]["EURUSD"] == [1.10, 1.11, 1.12]
    total, used, _ = populate_matrix_cell("EUR", live["D1"], bars_difference=1, timeframe="D1")
    assert used == 1
    assert total == round((1.12 - 1.11) * 100.0 / 1.11, 4)
    # Quote currency is inverted, same as IsBaseCurrency == false.
    usd, _, _ = populate_matrix_cell("USD", live["D1"], bars_difference=1, timeframe="D1")
    assert usd == round(-((1.12 - 1.11) * 100.0 / 1.11), 4)


def test_stamp_forming_bids_uses_the_previous_close_and_the_tick():
    stamped = stamp_forming_bids({"M1": {"EURUSD": [1.1000]}, "D1": {"EURUSD": [1.0950]}}, {"EURUSD": 1.1012})
    assert stamped["M1"]["EURUSD"] == [1.1000, 1.1012]
    assert stamped["D1"]["EURUSD"] == [1.0950, 1.1012]


def test_live_endpoints_replace_stale_closed_bars():
    stale = {"M1": {"EURUSD": [1.00, 1.01]}, "D1": {"EURUSD": [1.05, 1.06]}}
    live = apply_live_endpoints(stale, {"M1": {"EURUSD": [1.10, 1.101]}})
    assert live["M1"]["EURUSD"] == [1.10, 1.101]
    assert live["D1"]["EURUSD"] == [1.05, 1.06]


def test_ytd_window_ends_at_the_current_bid():
    framed = overlay_forming_closes({"YTD": {"GBPUSD": [1.20, 1.25]}}, {"GBPUSD": 1.27})
    assert framed["YTD"]["GBPUSD"] == [1.20, 1.27]


def test_compute_matrix_includes_avg():
    as_of = datetime(2025, 6, 1, tzinfo=timezone.utc)
    tf = "H1"
    pairs = {}
    for p in ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"):
        pairs[p] = [1.0, 1.01]
    result = compute_matrix(["H1", "AVG"], {tf: pairs}, bars_difference=1, as_of=as_of)
    assert "AVG" in result.values["EUR"]
    assert result.values["USD"]["H1"] < 0
