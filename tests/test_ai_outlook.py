import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.app.market.outlook import calendar as cal
from apps.api.app.market.outlook.config import outlook_settings
from apps.api.app.market.outlook.engine import build_outlook, validate
from apps.api.app.market.outlook.evaluation import calibration_table, evaluate, monitor, performance
from apps.api.app.market.scanner_analytics import Bar

DAY = date(2026, 7, 15)  # Wednesday, New York daylight time
CUTOFF = cal.close_time(DAY)
TRADE_WORDS = re.compile(r"\b(BUY|SELL|Buy|Sell)\b(?!-side)")


# ----- synthetic market -----


def _price(t: datetime) -> float:
    h = (t - CUTOFF).total_seconds() / 3600
    return 1.2 + 0.05 * math.sin(2 * math.pi * h / (24 * 365)) + 0.012 * math.sin(2 * math.pi * h / (24 * 18)) + 0.002 * math.sin(2 * math.pi * h / 30) + 2e-7 * h


def _bar(t: datetime, span: timedelta) -> Bar:
    pts = [_price(t + span * k / 4) for k in range(5)]
    return Bar(t, pts[0], max(pts) + 0.0004, min(pts) - 0.0004, pts[-1], 100)


def _series(last_open: datetime, span: timedelta, n: int) -> list[Bar]:
    return [_bar(last_open - span * i, span) for i in range(n)][::-1]


def _months(n: int) -> list[Bar]:
    out, y, m = [], CUTOFF.year, CUTOFF.month
    for _ in range(n):
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        out.append(_bar(start, timedelta(days=30)))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def _daily(n: int) -> list[Bar]:
    days, d = [], DAY
    while len(days) < n:
        if cal.is_trading_day(d):
            days.append(d)
        d -= timedelta(days=1)
    return [_bar(cal.d1_open_for(x), timedelta(days=1)) for x in days[::-1]]


def market() -> dict[str, list[Bar]]:
    return {
        "MN": _months(240),
        "W1": _series(cal.d1_open_for(date(2026, 7, 13)), timedelta(days=7), 260),
        "D1": _daily(300),
        "H8": _series(CUTOFF - timedelta(hours=8), timedelta(hours=8), 200),
        "H1": _series(CUTOFF - timedelta(hours=1), timedelta(hours=1), 200),
        "M30": _series(CUTOFF - timedelta(minutes=30), timedelta(minutes=30), 200),
    }


@pytest.fixture(scope="module")
def outlook():
    from apps.api.app.market.scanner_engine import analysis_cores

    bars = market()
    quality = validate(bars, CUTOFF, cal.d1_open_for(DAY))
    a = analysis_cores(bars, h8bb=False)
    return build_outlook("EURUSD", a, bars["D1"][-1].c, CUTOFF, None, quality, {}, outlook_settings(), analysis_date=DAY.isoformat(), snapshot_id="snap-test")


# ----- calendar -----


def test_trading_day_closes_at_new_york_rollover_across_dst():
    assert cal.close_time(date(2026, 7, 15)) == datetime(2026, 7, 15, 21, tzinfo=timezone.utc)
    assert cal.close_time(date(2026, 12, 2)) == datetime(2026, 12, 2, 22, tzinfo=timezone.utc)
    assert cal.d1_open_for(date(2026, 7, 13)) == datetime(2026, 7, 12, 21, tzinfo=timezone.utc)  # Monday bar opens Sunday
    assert cal.next_trading_day(date(2026, 7, 17)) == date(2026, 7, 20)


def test_last_closed_day_skips_weekends_and_waits_for_close():
    assert cal.last_closed_day(datetime(2026, 7, 18, 12, tzinfo=timezone.utc)) == date(2026, 7, 17)
    assert cal.last_closed_day(datetime(2026, 7, 15, 20, 59, tzinfo=timezone.utc)) == date(2026, 7, 14)
    assert cal.last_closed_day(datetime(2026, 7, 15, 21, tzinfo=timezone.utc)) == date(2026, 7, 15)
    sessions = cal.session_windows(cal.close_time(date(2026, 7, 17)))
    assert [s["key"] for s in sessions] == ["ASIAN", "LONDON", "NEW_YORK"]
    assert sessions[0]["start"].startswith("2026-07-20")


# ----- data quality -----


def test_validator_accepts_complete_fresh_snapshot_and_rejects_stale_d1():
    bars = market()
    ok = validate(bars, CUTOFF, cal.d1_open_for(DAY))
    assert ok["status"] == "OK" and ok["score"] >= 90
    stale = dict(bars, D1=bars["D1"][:-1])
    bad = validate(stale, CUTOFF, cal.d1_open_for(DAY))
    assert bad["status"] == "INSUFFICIENT_DATA"
    assert any(c["tf"] == "D1" and not c["fresh"] for c in bad["checks"])
    thin = validate(dict(bars, H1=bars["H1"][-20:]), CUTOFF, cal.d1_open_for(DAY))
    assert any(c["tf"] == "H1" and not c["complete"] for c in thin["checks"])


# ----- outlook contract -----


def test_outlook_probabilities_sum_to_100(outlook):
    c = outlook["confidence"]
    assert abs(c["bullish"] + c["bearish"] + c["range"] - 100) <= 0.3
    probs = [outlook[k]["probability"] for k in ("primary_scenario", "alternative_scenario", "range_scenario")]
    assert all(0 <= p <= 100 for p in probs)
    assert outlook["primary_scenario"]["probability"] == max(c["bullish"], c["bearish"], c["range"])


def test_outlook_contract_is_complete_and_analysis_only(outlook):
    for key in ("regime", "expected_direction", "expected_next_move", "primary_scenario", "alternative_scenario", "range_scenario", "erz", "targets",
                "invalidation", "key_levels", "session_plan", "confirmation_sequence", "chart_annotations", "system_action", "data_quality", "handoff"):
        assert key in outlook, key
    assert outlook["expected_direction"] in ("BULLISH", "BEARISH", "RANGE")
    assert outlook["system_action"]["key"] in ("WATCH", "WAIT", "PREPARE", "AUTHORIZE", "IGNORE")
    assert len(outlook["targets"]) == 2 and outlook["invalidation"]["price"] > 0
    assert [p["key"] for p in outlook["session_plan"]] == ["ASIAN", "LONDON", "NEW_YORK"]
    assert not TRADE_WORDS.search(json.dumps(outlook)), TRADE_WORDS.search(json.dumps(outlook))


def test_chart_annotations_are_structured_market_coordinates(outlook):
    ann = outlook["chart_annotations"]
    assert ann and len({a["id"] for a in ann}) == len(ann)
    for a in ann:
        assert a["tf"] and a["type"] and a["group"]
        assert not {"x", "y", "px", "left", "top", "pixel"} & set(a)
        if a["type"] in ("support", "resistance", "target", "invalidation", "fractal"):
            assert isinstance(a["price"], float | int)
        if a.get("at"):
            datetime.fromisoformat(a["at"])
        for pt in a.get("points") or []:
            datetime.fromisoformat(pt[0]) and float(pt[1])


def test_outlook_is_deterministic_for_identical_snapshot(outlook):
    from apps.api.app.market.scanner_engine import analysis_cores

    bars = market()
    again = build_outlook("EURUSD", analysis_cores(bars, h8bb=False), bars["D1"][-1].c, CUTOFF, None, validate(bars, CUTOFF, cal.d1_open_for(DAY)), {},
                          outlook_settings(), analysis_date=DAY.isoformat(), snapshot_id="snap-test")
    assert json.dumps(again, sort_keys=True, default=str) == json.dumps(outlook, sort_keys=True, default=str)


# ----- evaluation, calibration, monitoring -----


def _plan(direction="BULLISH"):
    up = direction == "BULLISH"
    return {
        "anchor": CUTOFF.isoformat(), "expected_direction": direction, "price": 1.1000, "volatility": {"atr": 0.0100},
        "erz": {"lo": 1.0960, "hi": 1.0980, "mid": 1.0970, "label": "1.0960 – 1.0980", "price_inside": False},
        "targets": [{"price": 1.1050 if up else 1.0950}, {"price": 1.1100 if up else 1.0900}],
        "invalidation": {"price": 1.0940 if up else 1.1060},
        "range_scenario": {"range": [1.0940, 1.1050]}, "confidence": {"primary": 64.0, "calibration": {"raw": 66.0}},
        "confirmation_sequence": [
            {"step": 1, "key": "REACTION", "label": "Reaction at ERZ", "condition": {"type": "touch_zone", "lo": 1.0960, "hi": 1.0980}},
            {"step": 2, "key": "EXHAUSTION", "label": "Exhaustion", "condition": {"type": "reject_zone", "tf": "M30", "lo": 1.0960, "hi": 1.0980, "dir": 1}},
            {"step": 3, "key": "BOS", "label": "H1 BOS", "condition": {"type": "structure", "tf": "H1", "kind": "BOS", "dir": 1}},
            {"step": 4, "key": "RETEST", "label": "Retest", "condition": {"type": "retest", "lo": 1.0960, "hi": 1.0980, "dir": 1}},
            {"step": 5, "key": "T1", "label": "Objective 1", "condition": {"type": "reach", "price": 1.1050, "dir": 1}},
        ],
        "qualified": True,
    }


def _h1(closes, start=CUTOFF):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append(Bar(start + timedelta(hours=i), prev, max(prev, c) + 0.0002, min(prev, c) - 0.0002, c, 10))
        prev = c
    return out


NEXT_CLOSE = cal.close_time(cal.next_trading_day(DAY))


def test_evaluator_target_first_is_win_and_close_beyond_invalidation_is_loss():
    up = [1.1000 + 0.0003 * i for i in range(24)]
    win = evaluate(_plan(), _h1(up), NEXT_CLOSE, "2026-07-16")
    assert win["outcome"] == "WIN" and win["target1_hit"] and win["scenario_result"] == "PRIMARY" and win["direction_correct"] == 1

    down = [1.1000 - 0.0005 * i for i in range(24)]
    loss = evaluate(_plan(), _h1(down), NEXT_CLOSE, "2026-07-16")
    assert loss["outcome"] == "LOSS" and loss["invalidated"] and loss["first_event"] == "INVALIDATED" and loss["direction_correct"] == 0
    assert loss["scenario_result"] == "ALTERNATIVE"


def test_evaluator_waits_for_complete_next_day():
    assert evaluate(_plan(), _h1([1.1] * 6), NEXT_CLOSE, "2026-07-16") is None
    assert evaluate(_plan(), [], NEXT_CLOSE, "2026-07-16") is None


def test_calibration_table_and_performance_use_directional_calls():
    rows = [
        {"direction": "BULLISH", "confidence": 65, "direction_correct": 1, "detail": {"raw_confidence": 66}, "qualified": True, "outcome": "WIN",
         "scenario_result": "PRIMARY", "target1_hit": True, "target2_hit": False, "invalidated": False, "erz_touched": True},
        {"direction": "BEARISH", "confidence": 62, "direction_correct": 0, "detail": {"raw_confidence": 61}, "qualified": True, "outcome": "LOSS",
         "scenario_result": "ALTERNATIVE", "target1_hit": False, "target2_hit": False, "invalidated": True, "erz_touched": True},
        {"direction": "RANGE", "confidence": 45, "direction_correct": 1, "detail": {}, "qualified": False, "outcome": "WIN",
         "scenario_result": "RANGE", "target1_hit": False, "target2_hit": False, "invalidated": False, "erz_touched": False},
    ]
    table, n = calibration_table(rows)
    assert n == 2 and table["60-70"] == {"n": 2, "hits": 1}
    perf = performance(rows)
    assert perf["samples"] == 3 and perf["accuracy"] == pytest.approx(66.7, abs=0.1)
    assert perf["direction_accuracy"] == 50.0 and perf["false_positives"] == 1
    assert next(b for b in perf["buckets"] if b["bucket"] == "60-70")["n"] == 2
    assert performance(rows, qualified_only=True)["samples"] == 2


def test_monitor_tracks_sequence_without_touching_published_outlook():
    plan = _plan()
    before = json.dumps(plan, sort_keys=True)
    h1 = _h1([1.1000, 1.0985, 1.0975, 1.0985, 1.0995, 1.0978, 1.0990])
    res = monitor(plan, h1, [], None, CUTOFF + timedelta(hours=7))
    assert [s["key"] for s in res["steps"] if s["done"]] == ["REACTION", "EXHAUSTION"]
    assert res["status"] == "EXHAUSTION" and res["system_action"]["key"] == "PREPARE"
    assert next(s for s in res["steps"] if s["key"] == "BOS")["unavailable"]

    bos = [{"at": (CUTOFF + timedelta(hours=4)).isoformat(), "kind": "BOS", "direction": "UP"}]
    confirmed = monitor(plan, h1, [], bos, CUTOFF + timedelta(hours=7))
    assert confirmed["status"] == "RETEST" and confirmed["system_action"]["key"] == "AUTHORIZE"
    assert "not trade authorisation" in confirmed["system_action"]["detail"]

    assert monitor(dict(plan, qualified=False), h1, [], bos, CUTOFF)["system_action"]["key"] == "IGNORE"
    broke = monitor(plan, _h1([1.1000, 1.0950, 1.0930]), [], None, CUTOFF + timedelta(hours=3))
    assert broke["status"] == "INVALIDATED" and broke["system_action"]["key"] == "IGNORE"
    assert json.dumps(plan, sort_keys=True) == before


# ----- scheduler, persistence, recovery -----


@pytest.fixture()
def service_env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    from apps.api.app.market.outlook import service as svc

    universe = ["XAUUSD", "EURUSD", "GBPUSD"]
    real_cores = svc.analysis_cores

    def fake_freeze(repo, day, origin):
        bars = market()
        return ({"snapshot_id": f"snap-{day.isoformat()}-test", "frozen_at": svc.now_iso(), "symbols": {}}, {s: bars for s in universe})

    def cores(bars, h8bb=False):
        if bars is fake_bad:
            raise RuntimeError("engine exploded")
        return real_cores(bars, h8bb=h8bb)

    fake_bad = market()

    def freeze_with_failure(repo, day, origin):
        manifest, bars = fake_freeze(repo, day, origin)
        bars["GBPUSD"] = fake_bad
        return manifest, bars

    monkeypatch.setattr(svc, "SCANNER_UNIVERSE", universe)
    monkeypatch.setattr(svc, "freeze_snapshot", freeze_with_failure)
    monkeypatch.setattr(svc, "analysis_cores", cores)
    monkeypatch.setattr(svc, "MarketRepository", lambda conn: None)
    monkeypatch.setattr(svc, "reference_scores", lambda conn, cutoff: None)
    monkeypatch.setattr(svc, "candles_between", lambda *a, **k: {})
    monkeypatch.setattr(svc.OutlookService, "_live_events", staticmethod(lambda anchor: None))
    yield svc
    Path(path).unlink(missing_ok=True)


def _store(svc):
    from apps.api.app.core.database import db

    ctx = db()
    conn = ctx.__enter__()
    return ctx, conn, svc.OutlookRepository(conn, svc.active_scope(conn))


def test_daily_cycle_publishes_isolates_failures_and_is_idempotent(service_env):
    svc = service_env
    now = CUTOFF + timedelta(hours=2)
    service = svc.OutlookService()
    first = service.tick(now, replay=False)
    assert first["live"]["analysis_date"] == DAY.isoformat()
    ctx, conn, store = _store(svc)
    try:
        run = store.run(DAY.isoformat(), "LIVE")
        assert run["state"] in ("PUBLISHED", "MONITORING")
        assert run["symbols_published"] == 2 and run["symbols_failed"] == 1 and run["attempts"] == 1
        rows = store.outlooks(run["id"])
        assert {r["symbol"]: r["status"] for r in rows} == {"XAUUSD": "PUBLISHED", "EURUSD": "PUBLISHED", "GBPUSD": "FAILED"}
        ranked = [r for r in rows if r.get("qualified")]
        if ranked and any(r["symbol"] == "XAUUSD" for r in ranked):
            assert next(r for r in ranked if r["symbol"] == "XAUUSD")["opportunity_rank"] == 1
        states = [e["state"] for e in json.loads(run["log_json"])]
        for st in ("SNAPSHOTTING", "VALIDATING_DATA", "ANALYSING", "GENERATING_HYPOTHESES", "SCORING", "PROJECTING", "RANKING_OPPORTUNITIES", "PUBLISHED"):
            assert st in states
        audit = conn.execute("SELECT COUNT(*) FROM audit_events WHERE action IN ('AI_OUTLOOK_RUN_SCHEDULED','AI_OUTLOOK_PUBLISHED')").fetchone()[0]
        assert audit == 2
    finally:
        ctx.__exit__(None, None, None)

    service.tick(now + timedelta(minutes=5), replay=False)
    ctx, conn, store = _store(svc)
    try:
        assert len(store.runs(origin="LIVE")) == 1
        run = store.run(DAY.isoformat(), "LIVE")
        assert run["attempts"] == 1 and len(store.outlooks(run["id"])) == 3
        with pytest.raises(Exception, match="immutable"):
            conn.execute("UPDATE ai_outlook_symbol SET status='EDITED' WHERE run_id=?", (run["id"],))
    finally:
        ctx.__exit__(None, None, None)


def test_failed_run_retries_with_backoff(service_env, monkeypatch):
    svc = service_env

    def boom(repo, day, origin):
        raise RuntimeError("provider offline")

    monkeypatch.setattr(svc, "freeze_snapshot", boom)
    service = svc.OutlookService()
    now = CUTOFF + timedelta(hours=1)
    service.tick(now, replay=False)
    ctx, conn, store = _store(svc)
    try:
        run = store.run(DAY.isoformat(), "LIVE")
        assert run["state"] == "RETRY" and run["attempts"] == 1 and "provider offline" in run["error"]
        assert run["next_retry_at"] > now.isoformat()
    finally:
        ctx.__exit__(None, None, None)
    service.tick(now + timedelta(seconds=30), replay=False)
    ctx, conn, store = _store(svc)
    try:
        assert store.run(DAY.isoformat(), "LIVE")["attempts"] == 1
    finally:
        ctx.__exit__(None, None, None)


def test_job_lock_is_exclusive_reentrant_and_expires(service_env):
    svc = service_env
    ctx, conn, store = _store(svc)
    try:
        assert store.acquire_lock("job", "a", 60)
        assert not store.acquire_lock("job", "b", 60)
        assert store.acquire_lock("job", "a", 60)
        store.release_lock("job", "a")
        assert store.acquire_lock("job", "a", -1)
        assert store.acquire_lock("job", "b", 60)
        assert store.acquire_lock(svc.LOCK, "other-instance", 60)
        assert svc.OutlookService().tick(CUTOFF + timedelta(hours=2), replay=False) == {"skipped": "locked"}
    finally:
        ctx.__exit__(None, None, None)
