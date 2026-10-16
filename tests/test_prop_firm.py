"""Prop firm drawdown, lifecycle and tenant isolation."""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.api.app.prop_firm.compliance import FirmRules, Observation, evaluate, weekend_window
from apps.api.app.prop_firm.store import PropRepository


def rules(**changes):
    base = dict(
        daily_loss_pct=5, max_loss_pct=10, drawdown_method="STATIC", daily_reference="BALANCE",
        reset_timezone="UTC", max_positions=5, max_lot=2, floating_loss_pct=5, news_block_minutes=0,
        weekend_holding=True, automation_permitted=True, permitted_strategies=["OUTLOOK"],
        slippage_buffer_pct=0, emergency_close=False,
    )
    base.update(changes)
    return FirmRules.from_dict(base)


def obs(**changes):
    base = dict(
        balance=100000, equity=100000, initial_balance=100000, day_start_balance=100000, day_start_equity=100000,
        equity_high=100000, eod_equity_high=100000, floating_pnl=0, snapshot_age_seconds=1,
        now=datetime(2026, 10, 14, 12, tzinfo=timezone.utc), automation_confirmed=True, autonomous=True,
        strategy="OUTLOOK", proposed_lot=0.1, proposed_risk_pct=0.4,
    )
    base.update(changes)
    return Observation(**base)


def test_static_drawdown_blocks_at_the_firm_limit():
    allowed = evaluate(rules(), obs(equity=96000, balance=96000, floating_pnl=0))
    assert allowed.allow and allowed.close_positions is False
    blocked = evaluate(rules(), obs(equity=89000, balance=89000))
    assert not blocked.allow
    assert "Maximum loss limit is reached" in blocked.reasons
    assert blocked.close_positions is False


def test_trailing_and_end_of_day_use_their_own_highs():
    trailing = evaluate(rules(drawdown_method="TRAILING"), obs(equity=94000, equity_high=105000, balance=94000))
    assert not trailing.allow
    eod = evaluate(rules(drawdown_method="EOD_TRAILING"), obs(equity=94000, eod_equity_high=105000, balance=94000))
    assert not eod.allow
    static = evaluate(rules(drawdown_method="STATIC"), obs(
        equity=94000, balance=94000, day_start_balance=94000, equity_high=105000,
    ))
    assert static.allow


def test_daily_reset_reference_and_floating_loss():
    daily = evaluate(rules(daily_reference="EQUITY"), obs(day_start_equity=100000, equity=94000, balance=100000, floating_pnl=-6000))
    assert not daily.allow
    assert "Daily loss limit is reached" in daily.reasons
    floating = evaluate(rules(floating_loss_pct=3), obs(equity=100000, floating_pnl=-4000, balance=104000))
    assert not floating.allow
    assert floating.close_positions is False


def test_warning_does_not_close_positions():
    decision = evaluate(rules(), obs(equity=97000, balance=97000))
    assert decision.allow and decision.protection == "WARNING" and decision.close_positions is False


def test_emergency_close_requires_the_account_policy():
    hit = evaluate(rules(emergency_close=True), obs(equity=89000, balance=89000))
    assert hit.protection == "EMERGENCY" and hit.close_positions is True


def test_fail_closed_on_stale_missing_rules_and_news():
    assert not evaluate(None, obs()).allow
    assert not evaluate(rules(), obs(snapshot_age_seconds=None)).allow
    assert not evaluate(rules(), obs(snapshot_age_seconds=31)).allow
    assert not evaluate(rules(news_block_minutes=15), obs()).allow
    assert "News calendar is not available" in evaluate(rules(news_block_minutes=15), obs()).reasons


def test_weekend_boundary_and_duplicate_and_lot():
    assert weekend_window(datetime(2026, 10, 16, 20, 59, tzinfo=timezone.utc), "UTC") is False
    assert weekend_window(datetime(2026, 10, 16, 21, 0, tzinfo=timezone.utc), "UTC") is True
    friday = evaluate(rules(weekend_holding=False), obs(now=datetime(2026, 10, 16, 21, tzinfo=timezone.utc)))
    assert not friday.allow
    assert not evaluate(rules(), obs(duplicate=True)).allow
    assert not evaluate(rules(max_lot=0.05), obs(proposed_lot=0.2)).allow
    assert not evaluate(rules(max_positions=2), obs(open_positions=2)).allow
    assert not evaluate(rules(automation_permitted=False), obs()).allow


def test_reserved_risk_uses_remaining_capacity():
    decision = evaluate(rules(), obs(equity=98000, balance=98000, open_risk_pct=2, proposed_risk_pct=2))
    assert not decision.allow
    assert "Reserved risk exceeds the remaining daily capacity" in decision.reasons


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    sql = Path("database/migrations/023_prop_firm.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    return conn


def test_lifecycle_requires_firm_confirmation_and_stays_in_tenant():
    conn = _db()
    one = PropRepository(conn, "tenant-a")
    two = PropRepository(conn, "tenant-b")
    firm = one.create_firm("Example", {
        "daily_loss_pct": 5, "max_loss_pct": 10, "automation_permitted": False,
    }, "tester")
    account = one.create_account({
        "firm_id": firm["id"], "display_name": "Eval 1", "account_size": 100000, "lifecycle": "REGISTERED",
        "broker_login": "1001",
    }, "tester")
    moved = one.transition(account["id"], "CONNECTED", "tester")
    phase = one.transition(moved["id"], "EVALUATION_PHASE_1", "tester")
    with pytest.raises(ValueError):
        one.transition(phase["id"], "EVALUATION_PASSED", "tester", firm_confirmed=False)
    passed = one.transition(phase["id"], "EVALUATION_PASSED", "tester", firm_confirmed=True)
    assert passed["lifecycle"] == "EVALUATION_PASSED"
    assert two.accounts() == []
    assert len(one.accounts()) == 1
