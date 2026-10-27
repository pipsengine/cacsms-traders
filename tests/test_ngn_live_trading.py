import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.api.app.execution.money import D
from apps.api.app.execution.pipeline import acquire_lock, classify_broker_result, reconcile_account, release_lock
from apps.api.app.execution.service import execute_candidate
from apps.api.app.execution.sizing import account_tick_value, size_position
from apps.api.app.execution.symbols import resolve_broker_symbol

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def memory():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE trading_accounts(
          id TEXT PRIMARY KEY, tenant_id TEXT, account_currency TEXT, environment TEXT,
          balance REAL, equity REAL, free_margin REAL, margin REAL, connection_status TEXT
        );
        CREATE TABLE account_risk_profiles(
          id TEXT PRIMARY KEY, tenant_id TEXT, trading_account_id TEXT UNIQUE,
          max_open_positions INTEGER, max_total_risk_pct REAL, max_trade_risk_pct REAL,
          max_daily_loss_pct REAL, max_total_loss_pct REAL, profit_target_pct REAL,
          weekend_holding_allowed INTEGER, created_at TEXT, updated_at TEXT
        );
        """
    )
    conn.executescript((ROOT / "database" / "migrations" / "025_ngn_live_execution.sql").read_text(encoding="utf-8"))
    return conn


def account(environment="LIVE", currency="NGN", equity=100_000, free_margin=80_000):
    return {
        "id": "acc", "tenant_id": "tenant", "environment": environment, "account_currency": currency,
        "equity": equity, "balance": equity, "free_margin": free_margin, "margin": 0, "connection_status": "CONNECTED",
    }


def profile(**overrides):
    row = {
        "max_trade_risk_pct": 1, "max_total_risk_pct": 2, "max_open_positions": 4,
        "max_daily_loss_pct": None, "max_weekly_loss_pct": None, "max_drawdown_pct": None,
        "max_spread_points": None, "margin_floor_pct": None, "emergency_stop": 0, "live_trading_enabled": 0,
    }
    row.update(overrides)
    return row


def spec():
    return {
        "symbol": "XAUUSD", "broker_symbol": "XAUUSD.hf", "tick_size": "0.01", "tick_value": "150",
        "tick_value_currency": "NGN", "point": "0.01", "volume_min": "0.01", "volume_max": "50",
        "volume_step": "0.01", "spread_points": "0", "commission_per_lot": "0", "stops_level_points": 0,
        "currency_profit": "USD",
    }


def place(conn, *, mode="MODE_1", key="mode1:1", environment="LIVE", system_mode="LIVE_AUTONOMOUS",
          terminal_mode="LIVE", enabled=0, send=None, connected=True, stale=False, **profile_overrides):
    calls = {"n": 0}

    def _send(volume):
        calls["n"] += 1
        if send:
            return send(volume)
        return {"ok": True, "ticket": "9001", "deal": "9001", "retcode": 10009}

    result = execute_candidate(
        conn, tenant_id="tenant", account_id="acc", mode=mode, idempotency_key=key, symbol="XAUUSD",
        direction="BULLISH", stop=D("2648"), target=D("2660"), price=D("2650"), spec=spec(),
        system_mode=system_mode, terminal_mode=terminal_mode, account=account(environment),
        profile=profile(**profile_overrides, live_trading_enabled=enabled), connected=connected, stale=stale,
        send=_send, now=NOW,
    )
    result["calls"] = calls["n"]
    return result


def test_ngn_volume_uses_account_currency_tick_value_and_rounds_down():
    sized = size_position(
        equity=100_000, risk_pct=1, price="2650", stop="2648", tick_size="0.01", tick_value="150",
        volume_min="0.01", volume_max="50", volume_step="0.01",
    )
    assert sized.ok
    assert sized.volume == D("0.03")
    assert sized.risk_amount == D("1000.00")
    assert sized.projected_loss == D("900.00")


def test_mode2_outlook_allows_minimum_lot_within_ceiling():
    from apps.api.app.execution.service import _outlook_min_lot_size

    sized = size_position(
        equity=50_000, risk_pct=1, price="175.95", stop="176.66", tick_size="0.001", tick_value="843.74",
        volume_min="0.01", volume_max="60", volume_step="0.01",
    )
    assert not sized.ok and sized.reason == "MINIMUM_EXCEEDS_BUDGET"
    retry, ok = _outlook_min_lot_size(sized, equity=50_000, volume_min="0.01", ceiling_pct=13.0)
    assert ok and retry.ok and retry.volume == D("0.01")


def test_minimum_lot_above_the_budget_is_rejected_and_not_raised():
    sized = size_position(
        equity=100_000, risk_pct=1, price="2650", stop="2648", tick_size="0.01", tick_value="150",
        volume_min="0.10", volume_max="50", volume_step="0.01",
    )
    assert not sized.ok and sized.reason == "MINIMUM_EXCEEDS_BUDGET" and sized.volume is None


def test_usd_tick_value_is_not_treated_as_naira_without_a_validated_rate():
    value, reason = account_tick_value(account_currency="NGN", tick_value="1", tick_value_currency="USD", profit_currency="USD")
    assert value is None and reason == "PROFIT_CURRENCY_UNCONVERTED"
    converted, converted_reason = account_tick_value(
        account_currency="NGN", tick_value=None, tick_value_currency="USD", profit_tick_value="1",
        profit_currency="USD", conversion_rate="1600", conversion_from="USD", conversion_to="NGN",
    )
    assert converted_reason is None and converted == D("1600")


def test_symbol_resolution_uses_the_account_symbol_and_refuses_an_ambiguous_suffix():
    assert resolve_broker_symbol("EURUSD", ["EURUSDm"]) == "EURUSDm"
    assert resolve_broker_symbol("EURUSD", ["EURUSD.a"]) == "EURUSD.a"
    assert resolve_broker_symbol("EURUSD", ["EURUSD", "EURUSD.a"]) is None
    assert resolve_broker_symbol("EURJPY", ["EURJPY", "EURJPYb"]) == "EURJPY"
    assert resolve_broker_symbol("EURUSD", ["EURUSD", "EURUSD.a"], mapped="EURUSD.a") == "EURUSD.a"
    assert resolve_broker_symbol("EURUSD", ["GBPUSD"], mapped="EURUSDm") is None


def test_live_account_does_not_send_until_the_owner_enables_it():
    conn = memory()
    blocked = place(conn, enabled=0)
    assert blocked["calls"] == 0 and blocked["error"] == "LIVE_TRADING_DISABLED"
    allowed = place(conn, key="mode1:live", enabled=1)
    assert allowed["ok"] and allowed["calls"] == 1 and allowed["currency"] == "NGN"


def test_demo_can_send_without_the_live_switch():
    conn = memory()
    result = place(conn, environment="DEMO", system_mode="DEMO_AUTONOMOUS", terminal_mode="DEMO", enabled=0)
    assert result["ok"] and result["calls"] == 1


def test_both_modes_share_one_exposure_budget():
    conn = memory()
    first = place(conn, key="mode1:a", enabled=1, max_total_risk_pct=1.5)
    second = place(conn, mode="MODE_2", key="mode2:b", enabled=1, max_total_risk_pct=1.5)
    assert first["ok"] and first["calls"] == 1
    assert second["error"] == "AGGREGATE_EXPOSURE" and second["calls"] == 0


def test_uncertain_broker_result_is_not_sent_again():
    conn = memory()

    def uncertain(_volume):
        return {"ok": False, "uncertain": True, "retcode": 10012, "error": "timeout"}

    first = place(conn, enabled=1, send=uncertain)
    second = place(conn, enabled=1, send=uncertain)
    assert first["uncertain"] and first["calls"] == 1
    assert second["uncertain"] and second["calls"] == 0
    assert classify_broker_result({"ok": False, "retcode": 10006, "error": "rejected"}) == "BROKER_REJECTED"


def test_execution_lock_blocks_the_other_mode():
    conn = memory()
    assert acquire_lock(conn, "tenant", "acc", "mode2:held", NOW)
    blocked = place(conn, enabled=1)
    assert blocked["error"] == "EXECUTION_LOCK" and blocked["calls"] == 0
    release_lock(conn, "acc", "mode2:held")
    allowed = place(conn, key="mode1:after", enabled=1)
    assert allowed["ok"] and allowed["calls"] == 1


def test_disconnected_account_rejects_and_recovers_after_reconciliation():
    conn = memory()
    disconnected = place(conn, enabled=1, connected=False)
    assert disconnected["error"] == "DISCONNECTED" and disconnected["calls"] == 0

    def uncertain(_volume):
        return {"ok": False, "uncertain": True, "retcode": None, "ticket": "77", "error": "no result"}

    pending = place(conn, key="mode1:pending", enabled=1, send=uncertain)
    assert pending["uncertain"]
    reconcile_account(conn, "tenant", "acc", {"77"}, NOW + timedelta(seconds=5))
    row = conn.execute("SELECT status FROM trade_requests WHERE idempotency_key='mode1:pending'").fetchone()
    assert row["status"] == "CONFIRMED"


def test_emergency_stop_blocks_a_demo_account():
    conn = memory()
    result = place(conn, environment="DEMO", system_mode="DEMO_AUTONOMOUS", terminal_mode="DEMO", emergency_stop=1)
    assert result["error"] == "EMERGENCY_STOP" and result["calls"] == 0


def test_confirmed_gateway_result_writes_the_broker_ticket_back():
    from apps.api.app.execution.pipeline import upsert_request
    from apps.api.app.execution.service import apply_gateway_result

    conn = memory()
    conn.execute("CREATE TABLE ae_opportunity(id TEXT PRIMARY KEY, tenant_id TEXT, evidence_json TEXT, updated_at TEXT)")
    conn.execute("CREATE TABLE ai_outlook_handoff(outlook_id TEXT PRIMARY KEY, tenant_id TEXT, execution_ref TEXT, lifecycle TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO ae_opportunity(id,tenant_id,evidence_json,updated_at) VALUES('opp','tenant','{}','x')")
    conn.execute("INSERT INTO ai_outlook_handoff(outlook_id,tenant_id,execution_ref,lifecycle,updated_at) VALUES('out','tenant',NULL,'AUTHORIZATION_PENDING','x')")
    mode1 = upsert_request(
        conn, tenant_id="tenant", account_id="acc", key="mode1:opp", mode="MODE_1", symbol="XAUUSD",
        direction="BULLISH", currency="NGN", status="SUBMITTING", now=NOW,
    )
    mode2 = upsert_request(
        conn, tenant_id="tenant", account_id="acc", key="mode2:out:H1", mode="MODE_2", symbol="XAUUSD",
        direction="BULLISH", currency="NGN", status="SUBMITTING", now=NOW,
    )
    assert apply_gateway_result(conn, "tenant", "acc", mode1["id"], {"ok": True, "ticket": "555", "retcode": 10009})["ok"]
    assert apply_gateway_result(conn, "tenant", "acc", mode2["id"], {"ok": True, "ticket": "556", "retcode": 10009})["ok"]
    evidence = conn.execute("SELECT evidence_json FROM ae_opportunity WHERE id='opp'").fetchone()["evidence_json"]
    assert '"555"' in evidence
    handoff = conn.execute("SELECT execution_ref, lifecycle FROM ai_outlook_handoff WHERE outlook_id='out'").fetchone()
    assert handoff["execution_ref"] == "556" and handoff["lifecycle"] == "ORDER_SUBMITTED"


def test_gateway_pull_is_isolated_to_the_tenant_account():
    from apps.api.app.execution.pipeline import claim_queued, upsert_request

    conn = memory()
    upsert_request(
        conn, tenant_id="tenant", account_id="acc", key="mode1:queued", mode="MODE_1", symbol="EURUSD",
        direction="BULLISH", currency="NGN", status="QUEUED", now=NOW, volume=D("0.01"),
    )
    assert claim_queued(conn, "other", "acc", NOW) is None
    claimed = claim_queued(conn, "tenant", "acc", NOW)
    assert claimed["status"] == "SUBMITTING"
    assert claim_queued(conn, "tenant", "acc", NOW) is None
