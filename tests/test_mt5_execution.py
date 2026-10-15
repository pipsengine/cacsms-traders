from types import SimpleNamespace

from apps.api.app.domain.mt5_execution import execution_allowed, lot_size


def test_outlook_direction_is_required():
    from apps.api.app.cacsms_engine.project import outlook_allows, outlook_blocks

    book = {"NZDCHF": {"BEARISH"}, "CHFJPY": {"BEARISH"}}
    assert outlook_allows(book, "NZDCHF", "BEARISH")
    assert not outlook_allows(book, "NZDCHF", "BULLISH")
    assert outlook_blocks(book, "NZDCHF", "BULLISH")
    assert not outlook_blocks(book, "NZDCHF", "BEARISH")
    assert not outlook_blocks(book, "EURUSD", "BEARISH")
    assert not outlook_blocks(book, "CADJPY", "BEARISH")
    assert not outlook_blocks({"EURNZD": {"BULLISH", "BEARISH"}}, "EURNZD", "BULLISH")


def test_execution_matches_terminal_environment():
    assert execution_allowed("DEMO_AUTONOMOUS", "DEMO")
    assert execution_allowed("LIVE_AUTONOMOUS", "LIVE")
    assert not execution_allowed("DEMO_AUTONOMOUS", "LIVE")
    assert not execution_allowed("LIVE_AUTONOMOUS", "DEMO")
    assert not execution_allowed("SHADOW", "DEMO")
    assert not execution_allowed("ANALYSIS_ONLY", "DEMO")
    assert not execution_allowed("PAUSED", "DEMO")


def test_lot_size_stays_inside_the_risk_budget():
    info = SimpleNamespace(trade_tick_size=0.00001, trade_tick_value=1.0, point=0.00001, volume_min=0.01, volume_max=50, volume_step=0.01)
    # 1% of 10,000 is 100. A 20-pip stop costs 200 per lot, so the budget buys 0.50.
    assert lot_size(info, equity=10_000, risk_pct=1, price=1.10, stop=1.0980) == 0.5


def test_lot_size_refuses_a_minimum_that_exceeds_the_budget():
    info = SimpleNamespace(trade_tick_size=0.00001, trade_tick_value=1.0, point=0.00001, volume_min=0.1, volume_max=50, volume_step=0.01)
    assert lot_size(info, equity=1_000, risk_pct=1, price=1.10, stop=1.0980) is None
