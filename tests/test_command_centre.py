from datetime import datetime, timezone

from apps.api.app.autonomous.command_centre import assemble

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)


def _stage(key, status="PENDING", operation=None, nxt=None, errors=0, blockers=None, focus=None):
    return {"key": key, "status": status, "current_operation": operation, "next_operation": nxt, "errors": errors,
            "blockers": blockers or [], "metrics": {"focus": focus} if focus else {}}


def test_bias_and_confidence_come_only_from_qualified_outlooks():
    board = assemble(
        now=NOW, mode="SHADOW", market_open=False, safety={"status": "DEGRADED", "market_open": False, "blockers": [], "warnings": []},
        ribbon={"system_status": "RUNNING", "safety_status": "DEGRADED"}, stages=[],
        outlook={"analysis_date": "2026-10-09", "published_at": "2026-10-09T21:05:00+00:00", "state": "PUBLISHED",
                 "symbols_published": 3, "rows": [
                     {"symbol": "EURUSD", "qualified": True, "expected_direction": "BULLISH", "confidence": 60, "reason": "D1 channel holds."},
                     {"symbol": "GBPUSD", "qualified": False, "expected_direction": "BEARISH", "confidence": 90, "reason": "Ignored."},
                     {"symbol": "XAUUSD", "qualified": True, "expected_direction": "BULLISH", "confidence": 70, "reason": "H8 pullback."},
                 ]},
        scanner=None, strength=[], opportunities=[], portfolio=None, execution=None, alerts=[],
    )
    assert board["outlook"]["bias"] == "BULLISH"
    assert board["outlook"]["confidence"] == 65.0
    assert board["outlook"]["symbols"][0]["symbol"] == "XAUUSD"
    assert "Ignored" not in (board["outlook"]["narrative"] or "")
    assert board["outlook"]["confidence_basis"].startswith("Mean evidence score")


def test_empty_outlook_does_not_invent_a_bias():
    board = assemble(now=NOW, mode="SHADOW", market_open=False, safety={}, ribbon={}, stages=[], outlook=None,
                     scanner=None, strength=[], opportunities=[], portfolio=None, execution=None, alerts=[])
    assert board["outlook"]["bias"] is None
    assert board["outlook"]["confidence"] is None
    assert board["outlook"]["narrative"] is None


def test_workflow_position_follows_persisted_stage_status():
    stages = [
        _stage("MARKET_DATA", "RUNNING"), _stage("SCANNER", "RUNNING"), _stage("INTELLIGENCE", "RUNNING"),
        _stage("STRUCTURE", "RUNNING"), _stage("CHANNEL", "RUNNING"),
        _stage("OPPORTUNITY", "RUNNING", "Tracking 4 opportunities", "Closed H1 bar inside an entry zone", focus="XAUUSD"),
        _stage("CONFIRMATION", "WAITING"), _stage("RISK", "WAITING"), _stage("EXECUTION", "BLOCKED"),
        _stage("MANAGEMENT", "IDLE"), _stage("LEARNING", "RUNNING"),
    ]
    board = assemble(now=NOW, mode="SHADOW", market_open=True, safety={"status": "NORMAL", "blockers": []}, ribbon={},
                     stages=stages, outlook=None, scanner=None, strength=[], opportunities=[], portfolio=None, execution=None, alerts=[])
    flow = board["workflow"]
    assert flow["current_label"] == "Identify Setups"
    assert flow["step_of"] == 3
    assert flow["operation"] == "Tracking 4 opportunities"
    assert flow["focus_symbol"] == "XAUUSD"
    assert flow["position_basis"].startswith("Share of the six")
    assert flow["steps"][0]["state"] == "done"
    assert flow["steps"][2]["state"] == "current"
    assert flow["steps"][4]["state"] == "pending"


def test_shadow_plans_are_not_broker_positions():
    board = assemble(
        now=NOW, mode="SHADOW", market_open=False, safety={}, ribbon={}, stages=[], outlook=None, scanner=None, strength=[],
        opportunities=[], portfolio={"account": {"floating_pnl": 12.5, "currency": "USD"}, "limits": {}, "outcomes": {"hit_rate": None, "profit_factor": None}},
        execution={"broker": {"open_positions": 0, "orders_submitted": 0}, "shadow": {"open_plans": 4},
                  "plans": [{"symbol": "EURUSD", "direction": "BULLISH", "order_status": "NOT_SUBMITTED", "unrealized_r": 0.4}],
                  "execution_note": "No broker order is submitted."},
        alerts=[],
    )
    assert board["positions"]["broker_open"] == 0
    assert board["positions"]["shadow_open"] == 4
    assert board["positions"]["orders_submitted"] == 0
    assert board["shadow_plans"][0]["order_status"] == "NOT_SUBMITTED"
    assert board["performance"]["profit_factor"] is None
    assert board["execution"] == "BLOCKED"


def test_scanner_groups_count_every_row_once():
    rows = [
        {"symbol": "EURUSD", "status": {"key": "HIGH_INSPECTION"}},
        {"symbol": "USDJPY", "status": {"key": "WATCHING"}},
        {"symbol": "EURJPY", "status": {"key": "NEUTRAL"}},
        {"symbol": "EURAUD", "status": {"key": "EXCLUDED"}, "excluded_reason": "Missing H1"},
        {"symbol": "XAUUSD", "status": {"key": "HIGH_INSPECTION"}},
    ]
    board = assemble(now=NOW, mode="SHADOW", market_open=False, safety={}, ribbon={}, stages=[], outlook=None,
                     scanner={"rows": rows}, strength=[], opportunities=[{"type": "TIT", "tit_level": "L2", "symbol": "XAUUSD", "confidence": 80}],
                     portfolio=None, execution=None, alerts=[])
    scan = board["scanner"]
    assert scan["total"] == 5
    assert scan["actionable"] == 2 and scan["watchlist"] == 1 and scan["no_setup"] == 1 and scan["excluded"] == 1
    assert scan["groups"]["majors"]["HIGH_INSPECTION"] == 1
    assert scan["groups"]["majors"]["WATCHING"] == 1
    assert scan["groups"]["jpy"]["NEUTRAL"] == 1
    assert scan["groups"]["commodities"]["HIGH_INSPECTION"] == 1
    assert scan["excluded_reasons"][0]["reason"] == "Missing H1"
    assert board["tit"] == {"count": 1, "levels": {"L2": 1}}
    assert board["opportunities"][0]["symbol"] == "XAUUSD"
