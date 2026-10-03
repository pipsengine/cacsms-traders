from apps.api.app.market.csm_engine import populate_matrix_cell


def test_strength_eur_positive_when_eur_pairs_rally():
    data = {
        "EURUSD": [1.10, 1.11],
        "EURGBP": [0.85, 0.86],
        "EURJPY": [160.0, 161.0],
        "EURCHF": [0.95, 0.96],
        "EURAUD": [1.60, 1.61],
        "EURCAD": [1.45, 1.46],
        "EURNZD": [1.75, 1.76],
    }
    total, used, _ = populate_matrix_cell("EUR", data, bars_difference=1)
    assert used == 7
    assert total > 0
