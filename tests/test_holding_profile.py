from apps.api.app.execution.holding_profile import (
    STYLE_INTRADAY,
    STYLE_POSITION,
    STYLE_SWING,
    holding_profile_for_execution,
    holding_profile_for_opportunity,
)


def test_mode1_fx_defaults_to_swing():
    profile = holding_profile_for_opportunity(
        {"symbol": "EURUSD", "parent_tf": "H8", "trigger_tf": "H1"},
    )
    assert profile["style"] == STYLE_SWING
    assert profile["exit_mechanism"] == "STOP_AND_TARGET"
    assert "Pre-entry" in (profile["setup_window"] or "")


def test_gold_h8_intraday():
    profile = holding_profile_for_opportunity(
        {"symbol": "XAUUSD", "parent_tf": "H8", "trigger_tf": "H1"},
    )
    assert profile["style"] == STYLE_INTRADAY


def test_mode2_quarterly_position():
    profile = holding_profile_for_execution(
        mode="MODE_2", symbol="EURUSD", outlook_horizon="QUARTERLY",
    )
    assert profile["style"] == STYLE_POSITION
    assert profile["derived_from"] == "mode_2_horizon"


def test_evaluate_mode1_infers_timeframes():
    profile = holding_profile_for_execution(mode="MODE_1", symbol="AUDCAD")
    assert profile["style"] == STYLE_SWING
    assert profile["parent_tf"] == "H8"
    assert profile["trigger_tf"] == "H1"
