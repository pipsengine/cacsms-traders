from datetime import datetime, timezone

from apps.api.app.market.constants import CSM_CURRENCIES
from apps.api.app.market.csm_scoring import normalize_all_scores
from apps.api.app.market.csm_service import CurrencyStrengthMatrixService
from apps.api.app.market.csm_windows import window_closes
from apps.api.app.market.strength_classification import classify

RAW = {"USD": 3.0, "JPY": 1.5, "CHF": 0.5, "EUR": 0.0, "GBP": -0.5, "CAD": -1.0, "AUD": -1.5, "NZD": -2.0}


def _grid(tfs=("H1", "D1")):
    values = {c: {tf: RAW[c] for tf in tfs} for c in CSM_CURRENCIES}
    quality = {c: {tf: "FRESH" for tf in tfs} for c in CSM_CURRENCIES}
    return values, quality


def test_scores_are_bounded_and_ordered():
    values, quality = _grid()
    scores = normalize_all_scores(values, ("H1", "D1", "AVG"), quality)
    ranked = sorted(CSM_CURRENCIES, key=lambda c: -scores[c]["H1"])
    assert ranked[0] == "USD" and ranked[-1] == "NZD"
    assert all(0 < scores[c]["H1"] < 100 for c in CSM_CURRENCIES)


def test_avg_is_mean_of_timeframe_scores():
    values, quality = _grid()
    values["USD"]["D1"] = -2.0
    scores = normalize_all_scores(values, ("H1", "D1", "AVG"), quality)
    expected = round((scores["USD"]["H1"] + scores["USD"]["D1"]) / 2, 1)
    assert scores["USD"]["AVG"] == expected


def test_missing_cells_are_not_scored():
    values, quality = _grid()
    quality["EUR"]["D1"] = "MISSING"
    scores = normalize_all_scores(values, ("H1", "D1", "AVG"), quality)
    assert "D1" not in scores["EUR"]
    assert scores["EUR"]["AVG"] == scores["EUR"]["H1"]


def test_classification_thresholds():
    assert classify(60.9)["label"] == "Strong"
    assert classify(53.0)["label"] == "Moderate"
    assert classify(49.8)["label"] == "Neutral"
    assert classify(44.1)["label"] == "Weak"
    assert classify(30.0)["label"] == "Very Weak"


def test_score_keeps_earnforex_sign():
    values = {c: {"M1": v} for c, v in zip(CSM_CURRENCIES, (0.0017, -0.0142, 0.1052, -0.0060, 0.0, 0.0325, -0.0042, -0.0054))}
    quality = {c: {"M1": "FRESH"} for c in CSM_CURRENCIES}
    scores = normalize_all_scores(values, ("M1",), quality)
    for c in CSM_CURRENCIES:
        raw = values[c]["M1"]
        assert (scores[c]["M1"] > 50) == (raw > 0)
        assert (scores[c]["M1"] < 50) == (raw < 0)


def test_cell_matches_earnforex_formula():
    from apps.api.app.market.csm_engine import populate_matrix_cell

    closes = {"EURUSD": [1.10, 1.111], "EURGBP": [0.85, 0.84]}
    total, used, _ = populate_matrix_cell("EUR", closes, 1)
    expected = (1.111 - 1.10) * 100 / 1.10 + (0.84 - 0.85) * 100 / 0.85
    assert used == 2 and round(expected, 4) == total


def test_currency_summary_ranks_and_uses_history():
    scores = {c: {"AVG": 50.0} for c in CSM_CURRENCIES}
    scores["USD"]["AVG"] = 60.0
    scores["NZD"]["AVG"] = 20.0
    histories = {"USD": [("t0", 48.0), ("t1", 55.0)]}
    out = CurrencyStrengthMatrixService.currency_summary(scores, histories)
    assert out[0]["currency"] == "USD" and out[0]["rank"] == 1
    assert out[-1]["currency"] == "NZD"
    assert out[0]["sparkline"] == [48.0, 55.0, 60.0]
    assert out[0]["change"] == 12.0
    assert out[0]["change_pct"] == 25.0


def test_quarter_window_uses_close_before_period_start():
    utc = timezone.utc
    rows = [
        (datetime(2026, 9, 29, tzinfo=utc), 1.10),
        (datetime(2026, 9, 30, tzinfo=utc), 1.12),
        (datetime(2026, 10, 1, tzinfo=utc), 1.15),
    ]
    assert window_closes(rows, datetime(2026, 10, 1, tzinfo=utc)) == (1.12, 1.15)
