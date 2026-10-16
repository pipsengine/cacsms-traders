"""Cacsms Engine qualification, slot policy and read-model tests."""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.app.autonomous.config import ae_settings
from apps.api.app.autonomous import opportunities as opps
from apps.api.app.cacsms_engine.policy import (
    authorise_entries,
    confirmed_entry_keys,
    global_position_limit,
    horizon_slot_cap,
    reconcile_orders,
)
from apps.api.app.cacsms_engine.project import build_overview
from apps.api.app.cacsms_engine.qualify import OutlookSignal, qualify


def signal(**changes):
    base = dict(
        outlook_id="outlook-1", scenario_id="scenario-1", version=1, symbol="EURJPY", horizon="DAILY",
        score=80, direction="SELL", valid=True, stale=False, invalidated=False,
    )
    base.update(changes)
    return OutlookSignal(**base)


def test_qualified_is_candidate_not_execution():
    decision = qualify(signal())
    assert decision.qualified and decision.stage == "QUALIFICATION" and decision.max_positions == 5


def test_score_threshold_69_70_80():
    assert not qualify(signal(score=69)).qualified
    assert qualify(signal(score=69)).stage == "MONITORING"
    assert qualify(signal(score=70)).qualified
    assert qualify(signal(score=80)).qualified
    assert qualify(signal(score=80)).stage == "QUALIFICATION"


def test_invalidated_or_stale_stay_unqualified():
    assert not qualify(signal(invalidated=True)).qualified
    assert not qualify(signal(stale=True)).qualified
    assert qualify(signal(valid=False)).stage == "MONITORING"


def test_h8_only_gold_and_has_no_count_ceiling():
    assert qualify(signal(horizon="GOLD_H8", symbol="EURJPY")).stage == "BLOCKED"
    decision = qualify(signal(horizon="GOLD_H8", symbol="XAUUSD", score=80))
    assert decision.qualified and decision.max_positions is None
    assert qualify(signal(horizon="GOLD_H8", symbol="XAUUSD", score=62)).stage == "MONITORING"


def test_horizon_caps_and_stricter_account_limit():
    assert qualify(signal(horizon="DAILY")).max_positions == 5
    assert qualify(signal(horizon="WEEKLY")).max_positions == 3
    assert qualify(signal(horizon="MONTHLY")).max_positions == 1
    assert qualify(signal(horizon="QUARTERLY")).max_positions == 1
    assert horizon_slot_cap("DAILY", engine_cap=6, account_cap=3) == 5
    assert horizon_slot_cap("WEEKLY", engine_cap=6, account_cap=3) == 3
    assert horizon_slot_cap("MONTHLY", engine_cap=6, account_cap=3) == 1
    assert horizon_slot_cap("H8", engine_cap=6, account_cap=3) is None
    assert global_position_limit(6, 3) == (3, "ACCOUNT_POSITION_CAP")
    assert global_position_limit(6, None) == (6, "MAX_CONCURRENT")


def test_risk_gate_uses_stricter_cap_and_horizon_budget():
    ae = ae_settings()
    confirmed = {
        "symbol": "EURUSD", "direction": "BULLISH", "entry_lo": 1.10, "entry_hi": 1.101, "invalidation": 1.09,
        "target_1": 1.13, "confidence": 80, "evidence": {"confirmation": {"close": 1.104}},
    }
    assert opps.risk_decision(confirmed, [], ae)[0] == "RISK_APPROVED"
    many_pairs = [{"symbol": f"PAIR{i}USD", "direction": "BULLISH"} for i in range(3)]
    assert opps.risk_decision(confirmed, many_pairs, ae, position_cap=3)[0] == "RISK_APPROVED"
    pair = [{"symbol": "EURUSD", "direction": "BULLISH", "state": "ORDER_ACCEPTED"}]
    assert opps.risk_decision(confirmed, pair, ae)[0] == "RISK_APPROVED"
    full_pair = pair + [{"symbol": "EURUSD", "direction": "BULLISH", "state": "ORDER_ACCEPTED"}]
    assert opps.risk_decision(confirmed, full_pair, ae)[2]["rule"] == "STRATEGY_PAIR_CAP"
    held = {**confirmed, "evidence": {**confirmed["evidence"], "outlook_horizon": "DAILY", "horizon_slots_used": 5}}
    assert opps.risk_decision(held, [], ae, position_cap=3)[2]["rule"] == "HORIZON_SLOT_CEILING"
    weekly = {**confirmed, "evidence": {**confirmed["evidence"], "outlook_horizon": "WEEKLY", "horizon_slots_used": 3}}
    assert opps.risk_decision(weekly, [], ae)[2]["rule"] == "HORIZON_SLOT_CEILING"
    priced = {**confirmed, "evidence": {**confirmed["evidence"], "trade_risk_pct": 1, "open_risk_pct": 3, "max_exposure_percent": 3}}
    assert opps.risk_decision(priced, [], ae)[2]["rule"] == "RISK_BUDGET"
    gold = {
        **confirmed, "symbol": "XAUUSD",
        "evidence": {**confirmed["evidence"], "outlook_horizon": "H8"},
    }
    assert opps.risk_decision(gold, [], ae)[2]["rule"] == "GOLD_RISK_BUDGET"
    funded = {
        **gold,
        "evidence": {**gold["evidence"], "exposure_percent": 1.0, "max_exposure_percent": 3.0},
    }
    assert opps.risk_decision(funded, [], ae)[0] == "RISK_APPROVED"


def _row(outlook_id, symbol, score, horizon="DAILY", **extra):
    outlook = {
        "outlook_id": outlook_id,
        "symbol": symbol,
        "status": "PUBLISHED",
        "expected_direction": extra.pop("direction", "BEARISH"),
        "evidence_score": {"value": score, "meaning": "Alignment of closed-bar evidence. Not a statistically calibrated win probability."},
        "erz": {"mid": 177.5},
        "invalidation": {"price": 178.2},
        "targets": [{"price": 176.4}],
        "qualified": extra.pop("qualified", True),
        "primary_scenario": {"key": "BEAR_CONT"},
        "current_status": {"title": extra.pop("title", "Waiting for pullback"), "detail": "From the published outlook"},
        "data_quality": {"status": extra.pop("quality", "OK"), "checks": [{"fresh": extra.pop("fresh", True)}]},
        "lifecycle": extra.pop("lifecycle", "PUBLISHED"),
    }
    return {
        "outlook": outlook,
        "horizon": horizon,
        "tenant_id": extra.pop("tenant_id", "tenant-a"),
        "account_id": "account-a",
        "lifecycle": outlook["lifecycle"],
        "invalidated": extra.pop("invalidated", False),
        "updated_at": "2026-10-14T16:00:00+00:00",
        **extra,
    }


def _book(rows, **kwargs):
    return build_overview(
        rows,
        system_mode=kwargs.pop("system_mode", "ANALYSIS_ONLY"),
        engine_cap=kwargs.pop("engine_cap", 6),
        account_cap=kwargs.pop("account_cap", 3),
        exposure_percent=kwargs.pop("exposure_percent", None),
        max_exposure_percent=kwargs.pop("max_exposure_percent", 3.0),
        market_data_status="READY",
        broker_status="BLOCKED",
        broker_basis="test",
        opportunities=kwargs.pop("opportunities", []),
        orders=kwargs.pop("orders", []),
        broker_positions=kwargs.pop("broker_positions", None),
    )


def test_projection_threshold_stale_and_duplicate_collapse():
    book = _book([
        _row("o-low", "EURJPY", 69),
        _row("o-ok", "USDJPY", 80),
        _row("o-ok", "USDJPY", 80),
        _row("o-stale", "GBPUSD", 88, quality="INSUFFICIENT_DATA"),
        _row("o-dead", "AUDUSD", 91, invalidated=True, lifecycle="INVALIDATED"),
    ])
    by_id = {row["id"]: row for row in book["campaigns"]}
    assert len(book["campaigns"]) == 4
    assert by_id["o-low"]["stage"] == "MONITORING"
    assert by_id["o-ok"]["stage"] == "QUALIFICATION"
    assert by_id["o-ok"]["maxPositions"] == 5
    assert by_id["o-stale"]["stage"] == "MONITORING"
    assert by_id["o-dead"]["stage"] == "CLOSED"
    assert book["summary"]["tradingMode"] == "SHADOW"
    assert book["summary"]["qualified"] == 1
    assert "win probability" in by_id["o-ok"]["risk"]["evidence_meaning"]


def test_simultaneous_horizons_do_not_share_slots():
    orders = [
        {"broker_order_id": "b1", "symbol": "EURUSD", "horizon": "DAILY", "state": "OPEN"},
        {"broker_order_id": "b1", "symbol": "EURUSD", "horizon": "DAILY", "state": "OPEN"},
        {"broker_order_id": "b2", "symbol": "EURUSD", "horizon": "WEEKLY", "state": "PENDING"},
    ]
    book = _book([
        _row("d", "EURUSD", 80, horizon="DAILY"),
        _row("w", "EURUSD", 80, horizon="WEEKLY"),
    ], orders=orders, account_cap=None)
    by_id = {row["id"]: row for row in book["campaigns"]}
    assert by_id["d"]["positionsOpen"] == 1
    assert by_id["d"]["positionsUsed"] == 1
    assert by_id["d"]["stage"] == "MANAGEMENT"
    assert by_id["w"]["positionsPending"] == 1
    assert by_id["w"]["positionsOpen"] == 0
    assert by_id["w"]["stage"] == "EXECUTION"


def test_stage_progression_does_not_invent_a_fill():
    opportunity = {
        "symbol": "EURJPY", "direction": "BEARISH", "status": "ACTIVE", "stage": "EXECUTION",
        "state": "EXECUTION_BLOCKED_ANALYSIS_ONLY", "next_condition": "Shadow tracking",
        "parent_tf": "D1", "updated_at": "2026-10-14T17:01:13+00:00",
    }
    book = _book([_row("o", "EURJPY", 82)], opportunities=[opportunity])
    campaign = book["campaigns"][0]
    assert campaign["stage"] == "RISK"
    assert campaign["updatedAt"] == "2026-10-14T17:01:13+00:00"
    assert campaign["positionsOpen"] == 0
    assert "No broker order" in campaign["nextAction"]
    confirmed = {**opportunity, "stage": "CONFIRMATION", "state": "AWAITING_REACTION", "next_condition": "Closed H1 rejection"}
    moved = _book([_row("o", "EURJPY", 82)], opportunities=[confirmed])
    assert moved["campaigns"][0]["stage"] == "CONFIRMATION"
    assert moved["summary"]["qualified"] == 0
    assert moved["summary"]["awaitingConfirmation"] == 1
    weekly = _book([_row("w", "EURJPY", 82, horizon="WEEKLY")], opportunities=[confirmed])
    assert weekly["campaigns"][0]["stage"] == "QUALIFICATION"
    assert weekly["campaigns"][0]["updatedAt"] == "2026-10-14T16:00:00+00:00"
    assert weekly["campaigns"][0]["positionsOpen"] == 0


def test_outlook_confirmation_reaches_risk_and_execution_without_inventing_a_fill():
    from apps.api.app.cacsms_engine.advance import decide_outlook_order

    confirmed = _book([_row("o", "EURJPY", 82, lifecycle="BOS")])
    assert confirmed["campaigns"][0]["stage"] == "CONFIRMATION"
    pending = _book([_row("o", "EURJPY", 82, lifecycle="AUTHORIZATION_PENDING")])
    assert pending["campaigns"][0]["stage"] == "RISK"
    submitted = _book([_row("o", "EURJPY", 82, lifecycle="ORDER_SUBMITTED", execution_ref="88421")])
    campaign = submitted["campaigns"][0]
    assert campaign["stage"] == "EXECUTION"
    assert campaign["positionsOpen"] == 0
    assert "88421" in campaign["nextAction"]
    payload = {
        "symbol": "EURJPY", "qualified": True, "expected_direction": "BEARISH",
        "evidence_score": {"value": 80}, "erz": {"mid": 176.8}, "invalidation": {"price": 177.4},
        "targets": [{"price": 175.2}],
    }
    common = dict(open_symbols=set(), engine_cap=6, account_cap=3, exposure_percent=0.4, max_exposure_percent=3.0, slots_remaining=2)
    assert decide_outlook_order(payload, horizon="DAILY", horizon_used=0, **common)["action"] == "send"
    assert decide_outlook_order(payload, horizon="DAILY", horizon_used=0, **common)["order"]["direction"] == "BEARISH"
    assert decide_outlook_order(payload, horizon="WEEKLY", horizon_used=2, **common)["action"] == "send"
    assert decide_outlook_order(payload, horizon="WEEKLY", horizon_used=3, **common)["action"] == "hold"
    tight = {**payload, "targets": [{"price": 176.7}]}
    assert decide_outlook_order(tight, horizon="DAILY", horizon_used=0, **common)["action"] == "hold"
    assert decide_outlook_order(payload, horizon="DAILY", horizon_used=0, open_symbols={"EURJPY"}, **{k: v for k, v in common.items() if k != "open_symbols"})["action"] == "send"


def test_strategy_and_outlook_share_one_order_and_keep_conflicts():
    from apps.api.app.cacsms_engine.registry import unify

    outlook = _book([
        _row("daily", "EURJPY", 82, direction="BEARISH"),
        _row("weekly", "GBPUSD", 74, horizon="WEEKLY", direction="BULLISH"),
    ])["campaigns"]
    strategy = {
        "id": "strat-1", "symbol": "EURJPY", "direction": "BEARISH", "opp_type": "TIT", "status": "ACTIVE",
        "stage": "CONFIRMATION", "state": "AWAITING_REACTION", "entry_lo": 176.7, "entry_hi": 176.9,
        "invalidation": 177.4, "target_1": 175.2, "confidence": 61, "family_key": "eurjpy-tit",
        "next_condition": "Wait for the H1 rejection", "updated_at": "2026-10-15T09:00:00+00:00",
    }
    opposite = {
        "id": "strat-2", "symbol": "GBPUSD", "direction": "BEARISH", "opp_type": "P2_BREAKOUT_RETEST", "status": "ACTIVE",
        "stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", "entry_lo": 1.30, "entry_hi": 1.301,
        "invalidation": 1.32, "target_1": 1.28, "confidence": 55, "family_key": "gbpusd-p2",
        "next_condition": "Wait for the retest", "updated_at": "2026-10-15T09:00:00+00:00",
    }
    low_score = {
        "id": "strat-3", "symbol": "AUDUSD", "direction": "BULLISH", "opp_type": "CONTINUATION", "status": "ACTIVE",
        "stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", "entry_lo": 0.65, "entry_hi": 0.651,
        "invalidation": 0.64, "target_1": 0.67, "confidence": 42, "family_key": "audusd-ch",
        "next_condition": "Channel touch", "updated_at": "2026-10-15T09:00:00+00:00",
    }
    # Outlook entry is the zone mid, so the strategy zone must contain  the published entry.
    outlook[0]["entry"] = 176.8
    outlook[0]["entryLo"] = 176.8
    outlook[0]["entryHi"] = 176.8
    book = unify(outlook, [strategy, opposite, low_score], account_cap=3)
    by_symbol = {}
    for row in book:
        by_symbol.setdefault(row["symbol"], []).append(row)
    assert len(by_symbol["EURJPY"]) == 1
    assert by_symbol["EURJPY"][0]["sourceMode"] == "COMBINED"
    assert by_symbol["EURJPY"][0]["evidenceScore"] == 82
    assert by_symbol["EURJPY"][0]["horizon"] == "DAILY"
    assert {by_symbol["EURJPY"][0]["id"], *by_symbol["EURJPY"][0]["linkedIds"]} == {"daily", "strat-1"}
    assert by_symbol["AUDUSD"][0]["sourceMode"] == "STRATEGY"
    assert by_symbol["AUDUSD"][0]["evidenceScore"] == 42
    gbpusd = {row["direction"]: row for row in by_symbol["GBPUSD"]}
    assert set(gbpusd) == {"BUY", "SELL"}
    assert gbpusd["BUY"]["conflict"] == "OPPOSITE_DIRECTION"
    assert gbpusd["SELL"]["conflict"] == "OPPOSITE_DIRECTION"
    second = {
        "id": "strat-4", "symbol": "AUDUSD", "direction": "BULLISH", "opp_type": "P2_BREAKOUT_RETEST", "status": "ACTIVE",
        "stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", "entry_lo": 0.6502, "entry_hi": 0.6508,
        "invalidation": 0.64, "target_1": 0.66, "confidence": 81, "family_key": "audusd-p2",
        "parent_tf": "D1", "next_condition": "Retest", "updated_at": "2026-10-15T09:00:00+00:00",
    }
    paired = unify([], [low_score, second], account_cap=3)
    assert len(paired) == 1
    assert paired[0]["sourceMode"] == "STRATEGY"
    assert paired[0]["evidenceScore"] == 42


def test_only_outlook_qualified_opportunities_are_listed():
    book = _book([
        _row("yes", "EURUSD", 80, qualified=True),
        _row("no", "GBPUSD", 95, qualified=False),
    ])
    assert [row["symbol"] for row in book["campaigns"]] == ["EURUSD"]
    assert book["summary"]["horizonCounts"]["DAILY"] == 1
    assert book["summary"]["campaigns"] == 1


def test_closed_terminal_ticket_leaves_execution():
    accepted = {
        "id": "strat-closed", "symbol": "EURUSD", "direction": "BEARISH", "status": "ACTIVE",
        "stage": "EXECUTION", "state": "ORDER_ACCEPTED", "opp_type": "P2_BREAKOUT_RETEST",
        "confidence": 67, "entry_lo": 1.119, "entry_hi": 1.12, "invalidation": 1.13, "target_1": 1.10,
        "updated_at": "2026-10-15T10:00:33+00:00",
        "evidence": {"broker_order": {"ticket": 2011034153}},
        "next_condition": "Broker order 2011034153 is open.",
    }
    empty = _book([], opportunities=[accepted], broker_positions=[])
    row = next(item for item in empty["campaigns"] if item["id"] == "strat-closed")
    assert row["stage"] == "CLOSED"
    assert row["positionsOpen"] == 0
    assert "2011034153" in row["nextAction"]
    assert empty["summary"]["executing"] == 0
    still_open = _book([], opportunities=[accepted], broker_positions=[
        {"ticket": "2011034153", "symbol": "EURUSD", "direction": "SELL", "volume": 0.03, "profit": 1.2},
    ])
    live = next(item for item in still_open["campaigns"] if item["symbol"] == "EURUSD")
    assert live["stage"] == "MANAGEMENT"
    assert live["positionsOpen"] == 1
    unknown = _book([], opportunities=[accepted])
    held = next(item for item in unknown["campaigns"] if item["id"] == "strat-closed")
    assert held["stage"] == "EXECUTION"


def test_terminal_position_is_shown_once_on_the_matching_campaign():
    positions = [
        {"ticket": "200444001", "symbol": "NZDCHFm", "direction": "SELL", "volume": 0.1,
         "priceOpen": 0.46675, "priceCurrent": 0.46676, "stopLoss": 0.46674, "takeProfit": 0.12, "profit": -0.12},
        {"ticket": "2001391028", "symbol": "CHFJPY", "direction": "SELL", "volume": 0.1,
         "priceOpen": 190.299, "priceCurrent": 189.8, "stopLoss": 183.887, "takeProfit": 189.687, "profit": 42.27},
        {"ticket": "9", "symbol": "GBPCAD", "direction": "BUY", "volume": 0.1,
         "priceOpen": 1.8, "priceCurrent": 1.81, "stopLoss": 1.7, "takeProfit": 1.9, "profit": 1.0},
    ]
    book = _book([
        _row("d", "NZDCHF", 74, horizon="DAILY", direction="BEARISH"),
        _row("w", "NZDCHF", 80, horizon="WEEKLY", direction="BEARISH"),
        _row("buy", "NZDCHF", 90, horizon="WEEKLY", direction="BULLISH"),
        _row("q", "CHFJPY", 80, horizon="QUARTERLY", direction="BEARISH"),
    ], broker_positions=positions)
    by_id = {row["id"]: row for row in book["campaigns"]}
    assert by_id["d"]["positionsOpen"] == 1
    assert by_id["d"]["stage"] == "MANAGEMENT"
    assert by_id["d"]["brokerPositions"][0]["ticket"] == "200444001"
    assert "200444001" in by_id["d"]["nextAction"]
    assert by_id["w"]["positionsOpen"] == 0
    assert by_id["w"]["stage"] == "QUALIFICATION"
    assert by_id["buy"]["positionsOpen"] == 0
    assert by_id["q"]["positionsOpen"] == 1
    assert by_id["q"]["stage"] == "MANAGEMENT"
    assert book["summary"]["openPositions"] == 3
    assert book["summary"]["fxPositions"] == 3
    assert book["summary"]["goldPositions"] == 0


def test_rejected_partial_and_restart_reconciliation():
    orders = [
        {"broker_order_id": "rej", "symbol": "XAUUSD", "horizon": "GOLD_H8", "state": "REJECTED"},
        {"broker_order_id": "part", "symbol": "XAUUSD", "horizon": "H8", "state": "PARTIAL"},
        {"broker_order_id": "part", "symbol": "XAUUSD", "horizon": "H8", "state": "PARTIAL"},
        {"broker_order_id": "fly", "symbol": "XAUUSD", "horizon": "H8", "state": "INFLIGHT"},
    ]
    counted = reconcile_orders(orders)
    assert counted[("XAUUSD", "GOLD_H8")] == {"open": 1, "pending": 0, "inflight": 1, "rejected": 1}
    assert reconcile_orders(orders) == counted


def test_repeated_m15_events_and_risk_exhaustion():
    events = [
        {"event_id": "m15-1", "confirmed": True, "closed": True},
        {"event_id": "m15-1", "confirmed": True, "closed": True},
        {"event_id": "m15-2", "confirmed": True, "closed": False},
        {"event_id": "m15-3", "confirmed": True, "closed": True},
    ]
    assert confirmed_entry_keys(events) == ["m15-1", "m15-3"]
    assert authorise_entries(events, budget_is_open=True, slots_remaining=None) == 2
    assert authorise_entries(events, budget_is_open=True, slots_remaining=1) == 1
    assert authorise_entries(events, budget_is_open=False, slots_remaining=None) == 0


def test_gold_below_threshold_is_monitoring():
    book = _book([_row("gold", "XAUUSD", 62, horizon="H8", direction="BEARISH")])
    campaign = book["campaigns"][0]
    assert campaign["horizon"] == "GOLD_H8"
    assert campaign["stage"] == "MONITORING"
    assert campaign["maxPositions"] is None
    assert campaign["positionsOpen"] == 0


@pytest.fixture()
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    from apps.api.app.main import app

    with TestClient(app) as test_client:
        yield test_client
    Path(path).unlink(missing_ok=True)


def _login(client: TestClient):
    response = client.post("/api/auth/login", json={"username": "cacsms", "password": "TestPass!123"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def test_overview_requires_auth_and_ignores_query_tenant(client):
    assert client.get("/api/cacsms-engine/overview").status_code == 401
    token = _login(client)
    headers = {"Authorization": f"Bearer {token}"}
    from apps.api.app.core.database import db
    from apps.api.app.market.outlook.store import OutlookRepository
    from apps.api.app.market.strength_intel_store import active_scope

    with db() as conn:
        conn.execute(
            "INSERT INTO system_settings(key, value_json, updated_at) VALUES('market_data.provider', ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            ('{"provider":"mt5","tenant_id":"tenant-cacsms","account_id":"acct-1"}', "2026-10-14T16:00:00+00:00"),
        )
        conn.commit()
        scope = active_scope(conn)
        assert scope == ("tenant-cacsms", "acct-1")
        store = OutlookRepository(conn, scope)
        run = store.create_run("2026-10-14", "LIVE", "2026-10-14T21:00:00+00:00", "test", "DAILY")
        store.update_run(run["id"], state="PUBLISHED", published_at="2026-10-14T21:05:00+00:00")
        store.insert_outlooks(run, [{
            "outlook_id": "scoped-outlook",
            "symbol": "EURJPY",
            "status": "PUBLISHED",
            "engine_version": "test",
            "expected_direction": "BEARISH",
            "confidence": {"primary": 80},
            "evidence_score": {"value": 80, "meaning": "Not a win probability."},
            "erz": {"mid": 177.7},
            "invalidation": {"price": 178.2},
            "targets": [{"price": 176.8}],
            "qualified": True,
            "primary_scenario": {"key": "BEAR_CONT"},
            "current_status": {"title": "Waiting for pullback", "detail": "Published snapshot"},
            "data_quality": {"status": "OK", "checks": [{"fresh": True}]},
            "lifecycle": "PUBLISHED",
        }])
        conn.execute(
            "INSERT INTO ai_outlook_run(id, tenant_id, trading_account_id, analysis_date, origin, state, close_at, engine_version, created_at, updated_at, horizon) "
            "VALUES('foreign-run','other-tenant','other-account','2026-10-14','LIVE','PUBLISHED','2026-10-14T21:00:00+00:00','test','2026-10-14T21:00:00+00:00','2026-10-14T21:00:00+00:00','DAILY')"
        )
        conn.execute(
            "INSERT INTO ai_outlook_symbol(id, run_id, tenant_id, trading_account_id, analysis_date, origin, symbol, status, qualified, engine_version, payload_json, created_at, horizon) "
            "VALUES('foreign-outlook','foreign-run','other-tenant','other-account','2026-10-14','LIVE','GBPJPY','PUBLISHED',1,'test','{\"symbol\":\"GBPJPY\",\"status\":\"PUBLISHED\",\"expected_direction\":\"SELL\",\"evidence_score\":{\"value\":99},\"erz\":{\"mid\":1},\"invalidation\":{\"price\":2},\"targets\":[{\"price\":0.5}],\"primary_scenario\":{\"key\":\"X\"}}','2026-10-14T21:00:00+00:00','DAILY')"
        )
        conn.commit()

    own = client.get("/api/cacsms-engine/overview?tenant_id=other-tenant", headers=headers)
    assert own.status_code == 200, own.text
    body = own.json()
    symbols = {row["symbol"] for row in body["campaigns"]}
    assert "EURJPY" in symbols
    assert "GBPJPY" not in symbols
    assert all(row["tenantId"] == scope[0] for row in body["campaigns"])
    assert body["summary"]["tradingMode"] in ("SHADOW", "DEMO", "LIVE", "PAUSED")
    detail = client.get("/api/cacsms-engine/campaigns/scoped-outlook?tenant_id=other-tenant", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["symbol"] == "EURJPY"
    hidden = client.get("/api/cacsms-engine/campaigns/foreign-outlook", headers=headers)
    assert hidden.status_code == 404
