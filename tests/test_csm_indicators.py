from apps.api.app.market.csm_engine import pct_change
from apps.api.app.market.csm_indicators import ema, mode_series, rsi, stochastic_close


def test_ema_seeds_with_first_value():
    out = ema([1.0, 2.0, 3.0], 2)
    assert out[0] == 1.0
    assert round(out[1], 6) == round(2 * 2 / 3 + 1 / 3, 6)
    assert round(out[2], 6) == round(3 * 2 / 3 + out[1] / 3, 6)


def test_rsi_wilder():
    closes = [float(x) for x in range(1, 20)]
    out = rsi(closes, 14)
    assert out[13] is None and out[14] == 100.0
    # period 2: moves +1, -0.5 → avg gain 0.5, avg loss 0.25 → RSI 66.67; next move +1 → (0.75, 0.125) → 85.71
    out = rsi([10.0, 11.0, 10.5, 11.5], 2)
    assert round(out[2], 2) == 66.67
    assert round(out[3], 2) == 85.71


def test_stochastic_close_bounds_and_signal():
    closes = [1.0, 1.2, 1.1, 1.3, 1.25, 1.4, 1.35, 1.5, 1.45, 1.6]
    main, signal = stochastic_close(closes, 5, 3, 3)
    defined = [m for m in main if m is not None]
    assert defined and all(0 <= m <= 100 for m in defined)
    assert main[6] is None or main.index(next(m for m in main if m is not None)) == 6
    assert signal[-1] is not None


def test_rsi_ma_is_ema_of_rsi():
    closes = [1.0 + 0.01 * ((i * 7) % 5) for i in range(40)]
    assert mode_series("RSI_MA", closes)[-1] == ema(rsi(closes), 2)[-1]


def test_zero_start_uses_plain_difference():
    assert pct_change(0.0, 12.5) == 12.5
    assert pct_change(50.0, 55.0) == 10.0
