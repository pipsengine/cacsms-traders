import os
import random
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from apps.api.app.autonomous import channels as lifecycle
from apps.api.app.autonomous import opportunities as opps
from apps.api.app.autonomous import supervisor
from apps.api.app.autonomous.config import STAGE_KEYS, ae_settings
from apps.api.app.market import channel_intelligence as chan
from apps.api.app.market.scanner_analytics import Bar

H1 = timedelta(hours=1)
T0 = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)  # Tuesday 08:00 UTC — opportunity origin (bar close)
ZONE = (1.1000, 1.1010)
CRAFTED = [  # EURUSD H1 bars after the origin: zone touch → bullish rejection → break of the reaction high → objective 1
    Bar(T0 - H1, 1.1050, 1.1056, 1.1044, 1.1050, 100),
    Bar(T0, 1.1050, 1.1060, 1.1040, 1.1045, 100),
    Bar(T0 + H1, 1.1040, 1.1042, 1.1005, 1.1008, 100),
    Bar(T0 + 2 * H1, 1.1006, 1.1030, 1.1002, 1.1025, 100),
    Bar(T0 + 3 * H1, 1.1025, 1.1045, 1.1020, 1.1040, 100),
    Bar(T0 + 4 * H1, 1.1040, 1.1210, 1.1035, 1.1190, 100),
]
SCHEMA = ("ae_cycle", "ae_stage_state", "ae_symbol_state", "ae_opportunity", "ae_channel", "ae_transition", "ae_worker", "ae_lock")
ORDER_APIS = re.compile(r"order_send|OrderSend|place_order|submit_order|NewOrderReq|create_order", re.I)


@pytest.fixture()
def env(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("DATABASE_PATH", path)
    monkeypatch.setenv("BOOTSTRAP_PASSWORD", "TestPass!123")
    for k in ("API_PROXY_SECRET", "CTRADER_CLIENT_SECRET", "VERCEL", "CRON_SECRET", "SMTP_ENABLED"):
        monkeypatch.delenv(k, raising=False)
    from apps.api.app.services.bootstrap import bootstrap

    bootstrap()
    yield path
    try:
        Path(path).unlink(missing_ok=True)
    except PermissionError:
        pass


def _db():
    from apps.api.app.core.database import db

    return db()


def _series(end: datetime, step: timedelta, n: int, base: float, drift: float, amp: float, seed: int) -> list[Bar]:
    rnd = random.Random(seed)
    out, p = [], base
    start = end - step * n
    for i in range(n):
        o = p
        c = o + drift + rnd.uniform(-amp, amp)
        out.append(Bar(start + step * i, o, max(o, c) + rnd.uniform(0, amp / 2), min(o, c) - rnd.uniform(0, amp / 2), c, 100))
        p = c
    return out


def _cores(end: datetime, seed: int = 7) -> dict:
    from apps.api.app.market.scanner_engine import analysis_cores

    bars = {
        "MN": _series(end, timedelta(days=30), 240, 1.0, 0.0005, 0.01, seed),
        "W1": _series(end, timedelta(days=7), 260, 1.0, 0.0002, 0.006, seed + 1),
        "D1": _series(end, timedelta(days=1), 300, 1.05, 0.0002, 0.003, seed + 2),
        "H8": _series(end, timedelta(hours=8), 200, 1.08, 0.0001, 0.0015, seed + 3),
        "H1": _series(end, H1, 200, 1.09, 0.00003, 0.0008, seed + 4),
        "M30": _series(end, timedelta(minutes=30), 200, 1.09, 0.00002, 0.0005, seed + 5),
    }
    return analysis_cores(bars)


@pytest.fixture(scope="module")
def cores():
    return _cores(T0 - timedelta(days=1))


def _analysis(cores: dict, bars: list[Bar]) -> dict:
    eur = {**cores, "h1": bars, "last_close": (bars[-1].t + H1, bars[-1].c)}
    return {"EURUSD": eur, "GBPUSD": {"excluded": "Insufficient D1 history (10/120 closed bars)"}}


def _upstream(analysis: dict, now: datetime) -> dict:
    return {"state": {"analysis": analysis, "rows": {}, "cycle_id": 1, "cycle_at": now - timedelta(seconds=30), "snapshot_id": None,
                      "provider": "mt5", "connected": True},
            "scanner_meta": {"engine_state": "READY"}, "strength_meta": {}, "intel": {}, "threads": {}}


def _candidate(**over) -> dict:
    c = {"family_key": "EURUSD|P2_BREAKOUT_RETEST|BULLISH|H8|H1", "symbol": "EURUSD", "direction": "BULLISH", "opp_type": "P2_BREAKOUT_RETEST",
         "tit_level": None, "parent_tf": "H8", "trigger_tf": "H1", "entry_lo": ZONE[0], "entry_hi": ZONE[1], "invalidation": 1.0980,
         "target_1": 1.1200, "target_2": 1.1300, "quality": 70.0, "confidence": 70.0, "reward_risk": 3.5, "origin_at": T0.isoformat(),
         "evidence": {"source": "P2 Breakout Retest", "break_at": "2026-10-05T00:00:00+00:00"}, "next_condition": "zone"}
    c.update(over)
    return c


@pytest.fixture()
def live(env, monkeypatch):
    """Ready provider context and a deterministic detector (one P2 candidate) for engine-level tests."""
    import apps.api.app.market.market_data as md

    monkeypatch.setattr(md, "market_context", lambda conn: {"active_provider": "mt5", "market_data_ready": True,
                                                           "market_data_scope": {"tenant_id": "", "account_id": ""},
                                                           "providers": {"mt5": {"healthy": True}}})
    calls = []

    def detect(symbol, a, row, now, ae, cs, ts, ovs):
        calls.append(symbol)
        return [_candidate()] if symbol == "EURUSD" else []

    monkeypatch.setattr(opps, "detect", detect)
    return calls


def _engine():
    from apps.api.app.autonomous.engine import AutonomousEngine

    return AutonomousEngine()


def _repo(conn):
    from apps.api.app.autonomous.store import AERepository
    from apps.api.app.market.strength_intel_store import active_scope

    return AERepository(conn, active_scope(conn))


def _opp_transitions(conn):
    return [t for t in reversed(_repo(conn).transitions(entity_type="OPPORTUNITY", limit=500))]


# ----- schema & store -----


def test_migrations_create_schema_and_transitions_are_append_only(env):
    with _db() as conn:
        names = {tuple(r)[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert set(SCHEMA) <= names
        repo = _repo(conn)
        t = {"entity_type": "OPPORTUNITY", "entity_id": "OPP-1", "to_stage": "OPPORTUNITY", "to_state": "WAITING_FOR_ZONE",
             "reason_code": "OPPORTUNITY_DETECTED", "evidence_at": T0.isoformat()}
        assert repo.add_transition(t)
        assert not repo.add_transition(t)  # deterministic id: the same evidence never duplicates
        conn.commit()
        with pytest.raises(Exception, match="append-only"):
            conn.execute("UPDATE ae_transition SET reason_code='X'")
        with pytest.raises(Exception, match="append-only"):
            conn.execute("DELETE FROM ae_transition")


def test_postgres_migration_mirrors_sqlite_and_splits_trigger_function():
    from apps.api.app.core.database import split_sql_script

    root = Path(__file__).resolve().parents[1]
    pg = (root / "apps/api/database/migrations/postgres/007_autonomous_engine.sql").read_text(encoding="utf-8")
    lite = (root / "database/migrations/018_autonomous_engine.sql").read_text(encoding="utf-8")
    for table in SCHEMA:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in pg and f"CREATE TABLE IF NOT EXISTS {table}" in lite
    parts = split_sql_script(pg)
    fn = next(p for p in parts if p.startswith("CREATE OR REPLACE FUNCTION ae_transition_append_only"))
    assert "RAISE EXCEPTION" in fn and fn.endswith("$$")
    assert " REAL" not in pg and "%" not in pg and "%" not in lite


def test_lease_lock_is_exclusive_reentrant_and_expires(env):
    with _db() as conn:
        repo = _repo(conn)
        assert repo.acquire_lock("ae", "a", 60)
        assert not repo.acquire_lock("ae", "b", 60)
        assert repo.acquire_lock("ae", "a", 60)
        repo.release_lock("ae", "a")
        assert repo.acquire_lock("ae", "a", -1)
        assert repo.acquire_lock("ae", "b", 60)


# ----- channel lifecycle -----


def _core(closed_at: str, **over) -> dict:
    c = {"available": True, "closed_at": closed_at, "fit_start": "2026-09-01T00:00:00+00:00", "direction": "ASCENDING",
         "validity": {"key": "VALID", "label": "Valid"}, "upper": 1.12, "mid": 1.11, "lower": 1.10, "width_atr": 4.0, "atr": 0.005,
         "last_close": 1.105, "touches_upper": 2, "touches_lower": 2, "inside_ratio": 0.95, "age": 40, "period": 60,
         "lines": {"upper": [], "mid": [], "lower": []}, "events": [], "breakouts": []}
    c.update(over)
    return c


def _apply(prev, plan):
    if plan["insert"]:
        return {**plan["insert"], "lines": plan["insert"]["lines_json"]}
    if plan["update"]:
        cid, fields = plan["update"]
        return {**prev, **fields, "lines": fields.get("lines_json", prev.get("lines"))}
    return prev


def test_channel_lifecycle_replays_break_retest_continuation_in_order():
    s, ae, scope = chan.channel_settings(), ae_settings(), ("t", "a")
    opened = "2026-10-05T10:00:00+00:00"
    plan = lifecycle.advance(None, scope, "EURUSD", "H1", _core(opened), ae, s, opened)
    assert [t["to_state"] for t in plan["transitions"]] == ["ACTIVE"]
    row = _apply(None, plan)
    brk = {"tf": "H1", "direction": "UP", "at": "2026-10-05T12:00:00+00:00", "level": 1.12, "close": 1.123, "confirmed": True, "failed": False,
           "failed_at": None, "retest_at": "2026-10-05T15:00:00+00:00", "completed_at": "2026-10-05T17:00:00+00:00", "bars_after": 8}
    later = "2026-10-05T19:00:00+00:00"  # worker was down: every step is replayed with its own evidence time
    plan = lifecycle.advance(row, scope, "EURUSD", "H1", _core(later, breakouts=[brk]), ae, s, later)
    steps = [(t["to_state"], t["evidence_at"]) for t in plan["transitions"]]
    assert steps == [("BREAKING", brk["at"]), ("BROKEN", "2026-10-05T13:00:00+00:00"), ("RETESTING", brk["retest_at"]),
                     ("CONTINUING", brk["completed_at"])]
    row = _apply(row, plan)
    assert row["state"] == "CONTINUING" and row["break_at"] == brk["at"]
    assert lifecycle.advance(row, scope, "EURUSD", "H1", _core(later, breakouts=[brk]), ae, s, later)["transitions"] == []
    aged = {**brk, "bars_after": ae.max_breakout_age_bars + 1}
    final = "2026-10-07T00:00:00+00:00"
    plan = lifecycle.advance(row, scope, "EURUSD", "H1", _core(final, breakouts=[aged]), ae, s, final)
    assert [t["to_state"] for t in plan["transitions"]] == ["EXPIRED"] and plan["update"][1]["status"] == "CLOSED"


def test_channel_touch_false_break_and_invalidation():
    s, ae, scope = chan.channel_settings(), ae_settings(), ("t", "a")
    t1 = "2026-10-05T10:00:00+00:00"
    row = _apply(None, lifecycle.advance(None, scope, "EURUSD", "H1", _core(t1), ae, s, t1))
    t2 = "2026-10-05T11:00:00+00:00"
    touch = {"at": t2, "event": "Channel Touch", "level": 1.10, "result": "Testing"}
    plan = lifecycle.advance(row, scope, "EURUSD", "H1", _core(t2, events=[touch]), ae, s, t2)
    assert [t["to_state"] for t in plan["transitions"]] == ["TOUCHED"]
    row = _apply(row, plan)
    assert row["last_touch_side"] == "LOWER"
    t3 = "2026-10-05T12:00:00+00:00"
    false_break = {"tf": "H1", "direction": "DOWN", "at": t3, "level": 1.10, "close": 1.099, "confirmed": False, "failed": True,
                   "failed_at": t3, "retest_at": None, "completed_at": None, "bars_after": 1}
    plan = lifecycle.advance(row, scope, "EURUSD", "H1", _core(t3, events=[touch], breakouts=[false_break]), ae, s, t3)
    assert [(t["to_state"], t["reason_code"]) for t in plan["transitions"]] == [("BREAKING", "BREAK_DETECTED"), ("ACTIVE", "FALSE_BREAK")]
    row = _apply(row, plan)
    assert row["break_at"] is None and row["lines"]["consumed_break_at"] == t3
    t4 = "2026-10-05T13:00:00+00:00"
    plan = lifecycle.advance(row, scope, "EURUSD", "H1", _core(t4, breakouts=[false_break], validity={"key": "LOOSE", "label": "Loose"}),
                             ae, s, t4)
    assert [t["reason_code"] for t in plan["transitions"]] == ["CLOSES_OUTSIDE"] and plan["update"][1]["status"] == "CLOSED"


# ----- opportunity progression -----


def _opp(**over) -> dict:
    o = {**_candidate(), "id": "OPP-x", "stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", "status": "ACTIVE",
         "stage_entered_at": T0.isoformat(), "evaluated_through": T0.isoformat()}
    o.update(over)
    return o


def test_evaluate_zone_reaction_confirmation_is_deterministic():
    ae = ae_settings()
    steps, through, needs = opps.evaluate(_opp(), CRAFTED[:5], [], ae)
    assert [(s["to_state"], s["evidence_at"]) for s in steps] == [
        ("AWAITING_REACTION", (T0 + 2 * H1).isoformat()),
        ("REACTION_CONFIRMED", (T0 + 3 * H1).isoformat()),
        ("RISK_REVIEW", (T0 + 4 * H1).isoformat()),
    ]
    assert needs and through == (T0 + 4 * H1).isoformat()
    again, _, _ = opps.evaluate(_opp(), CRAFTED[:5], [], ae)
    assert again == steps
    o = _opp(stage="RISK", state="RISK_REVIEW", evaluated_through=through, stage_entered_at=through)
    assert opps.evaluate(o, CRAFTED[:5], [], ae)[0] == []


def test_evaluate_invalidation_expiry_and_bos_confirmation():
    ae = ae_settings()
    crash = [Bar(T0, 1.1050, 1.1052, 1.0970, 1.0975, 100)]
    steps, _, needs = opps.evaluate(_opp(), crash, [], ae)
    assert [(s["to_state"], s["reason_code"], s["close"]) for s in steps] == [("INVALIDATED", "INVALIDATED_PRE_ENTRY", True)] and not needs
    far = [Bar(T0 + H1 * i, 1.1100, 1.1110, 1.1090, 1.1100, 100) for i in range(ae.zone_wait_bars + 2)]
    steps, _, _ = opps.evaluate(_opp(), far, [], ae)
    assert steps[-1]["reason_code"] == "ZONE_NOT_REACHED" and steps[-1]["outcome"] == "EXPIRED"
    reacted = _opp(stage="CONFIRMATION", state="REACTION_CONFIRMED", evidence={"reaction": {"at": T0.isoformat(), "high": 1.1100, "low": 1.1000}})
    bos = [{"at": (T0 + H1).isoformat(), "direction": "UP", "kind": "BOS", "level": 1.1030, "failed": False}]
    steps, _, needs = opps.evaluate(reacted, [Bar(T0, 1.1020, 1.1035, 1.1015, 1.1032, 100)], bos, ae)
    assert steps[-1]["reason_code"] == "H1_BOS_CONFIRMED" and needs


def test_risk_rules_reject_defer_and_approve():
    ae = ae_settings()
    confirmed = _opp(stage="RISK", state="RISK_REVIEW", evidence={"confirmation": {"close": 1.1040}})
    assert opps.risk_decision(confirmed, [], ae)[0] == "RISK_APPROVED"
    assert opps.risk_decision({**confirmed, "target_1": 1.1060}, [], ae)[2]["rule"] == "MIN_REWARD_RISK"
    assert opps.risk_decision({**confirmed, "confidence": 20}, [], ae)[2]["rule"] == "MIN_CONFIDENCE"
    assert opps.risk_decision(confirmed, [{"symbol": "EURUSD", "direction": "BULLISH"}], ae)[2]["rule"] == "SYMBOL_EXPOSURE"
    full = [{"symbol": f"X{i}Y{i}", "direction": "BULLISH"} for i in range(ae.max_concurrent)]
    assert opps.risk_decision(confirmed, full, ae)[2]["rule"] == "MAX_CONCURRENT"
    eur_long = [{"symbol": "EURGBP", "direction": "BULLISH"}, {"symbol": "EURJPY", "direction": "BULLISH"}]
    out = opps.risk_decision(confirmed, eur_long, ae)
    assert out[0] == "RISK_DEFERRED" and out[2]["rule"] == "CURRENCY_EXPOSURE" and out[2]["currency"] == "EUR"


def test_shadow_tracking_records_outcomes_without_orders():
    ae = ae_settings()
    at = (T0 + 4 * H1).isoformat()
    blocked = _opp(stage="EXECUTION", state="EXECUTION_BLOCKED_ANALYSIS_ONLY", evaluated_through=at, stage_entered_at=at,
                   evidence={"confirmation": {"close": 1.1040}})
    steps, _, _ = opps.evaluate(blocked, CRAFTED, [], ae)
    assert [(s["to_state"], s["outcome"]) for s in steps] == [("COMPLETED", "TARGET_1")]
    assert steps[0]["evidence"]["r_multiple"] == pytest.approx(2.67, abs=0.01)
    stop = [Bar(T0 + 4 * H1, 1.1040, 1.1150, 1.0975, 1.1000, 100)]  # both levels in one bar: the stop is assumed first
    assert opps.evaluate(blocked, stop, [], ae)[0][0]["outcome"] == "STOPPED"


def test_detection_on_real_engine_cores_yields_consistent_plans(cores):
    from apps.api.app.market.structure_overview_config import overview_settings
    from apps.api.app.market.trend_structure_config import trend_settings

    a = {**cores}
    found = opps.detect("EURUSD", a, None, T0, ae_settings(), chan.channel_settings(), trend_settings(), overview_settings())
    for c in found:
        d = opps.SIGN[c["direction"]]
        assert c["opp_type"] in ("P1_RETRACEMENT", "P2_BREAKOUT_RETEST", "CONTINUATION", "TIT")
        assert (c["invalidation"] - c["entry_lo"]) * d < 0 and (c["target_1"] - c["entry_hi"]) * d > 0
        assert 0 <= c["confidence"] <= 100 and c["family_key"].startswith("EURUSD|")


# ----- safety supervisor -----


def _assess(**over):
    now = over.pop("now", T0 + 10 * 60 * timedelta(seconds=1))
    analysis = over.pop("analysis", {"EURUSD": {"last_close": (T0, 1.1)}})
    kw = dict(now=now, mode="ANALYSIS_ONLY", ctx={"active_provider": "mt5", "market_data_ready": True, "market_data_scope": {"account_id": "1"}},
              analysis=analysis, scanner_meta={}, scanner_state={"cycle_at": now, "cycle_id": 3, "provider": "mt5"},
              strength_meta={"live_data": True, "pairs_loaded": 28}, db_ok=True, db_ms=3.0, snapshot=None, smtp_ready=True, threads={},
              serverless=False, ae=ae_settings())
    kw.update(over)
    return supervisor.assess(**kw)


def test_supervisor_verdicts():
    ok = _assess()
    assert ok["status"] == "NORMAL" and ok["progress_opportunities"] and ok["execution"] == "BLOCKED"
    assert _assess(ctx={"market_data_ready": False})["status"] == "CRITICAL"
    stale = _assess(now=T0 + timedelta(hours=5))
    assert stale["status"] == "CRITICAL" and not stale["progress_analysis"]
    paused = _assess(mode="PAUSED")
    assert paused["status"] == "HALTED" and not paused["progress_opportunities"] and paused["progress_analysis"]
    mismatch = _assess(snapshot={"id": "s1", "provider": "ctrader", "account_id": "9"})
    assert mismatch["status"] == "CRITICAL" and any("Account scope" in b for b in mismatch["blockers"])
    assert _assess(db_ok=False)["status"] == "CRITICAL"
    assert _assess(smtp_ready=False)["status"] == "DEGRADED"  # email failure never blocks analysis
    weekend = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)  # Saturday; last bar closed Friday 17:00 New York
    friday = datetime(2026, 10, 9, 21, 0, tzinfo=timezone.utc)
    closed = _assess(now=weekend, analysis={"EURUSD": {"last_close": (friday, 1.1)}}, scanner_state={"cycle_at": weekend, "cycle_id": 1})
    assert closed["status"] == "NORMAL" and closed["market_open"] is False


# ----- engine (persistence, idempotency, restart, recovery, safety) -----


def test_engine_cycle_is_idempotent_restart_safe_and_blocks_execution(live, cores):
    now = T0 + 4 * H1 + timedelta(minutes=10)
    analysis = _analysis(cores, CRAFTED[:5])
    first = _engine().run_cycle(now, upstream=_upstream(analysis, now))
    assert first["safety"] in ("NORMAL", "DEGRADED") and first["created"] == 1 and first["execution_blocked"] == 1
    with _db() as conn:
        repo = _repo(conn)
        assert set(repo.stages()) == set(STAGE_KEYS)
        stages = repo.stages()
        assert stages["EXECUTION"]["status"] == "BLOCKED" and stages["EXECUTION"]["metrics"]["orders_submitted"] == 0
        assert stages["MANAGEMENT"]["metrics"]["open_positions"] == 0
        [o] = repo.opportunities(status="ACTIVE")
        assert (o["stage"], o["state"]) == ("EXECUTION", "EXECUTION_BLOCKED_ANALYSIS_ONLY")
        assert o["evidence"]["confirmation"]["close"] == 1.1040 and o["evaluated_through"] == (T0 + 4 * H1).isoformat()
        assert [t["to_state"] for t in _opp_transitions(conn)] == [
            "WAITING_FOR_ZONE", "AWAITING_REACTION", "REACTION_CONFIRMED", "RISK_REVIEW", "RISK_APPROVED", "EXECUTION_BLOCKED_ANALYSIS_ONLY"]
        audit = [tuple(r)[0] for r in conn.execute("SELECT action FROM audit_events WHERE action LIKE 'AUTONOMOUS_%'").fetchall()]
        assert audit.count("AUTONOMOUS_EXECUTION_BLOCKED") == 1
        symbols = {s["symbol"]: s for s in repo.symbols()}
        assert symbols["EURUSD"]["stage"] == "EXECUTION" and symbols["GBPUSD"]["state"] == "EXCLUDED"
        before = conn.execute("SELECT COUNT(*) FROM ae_transition").fetchone()[0]

    # Same evidence again, from a fresh engine instance (simulated restart): nothing new happens.
    again = _engine().run_cycle(now + timedelta(minutes=1), upstream=_upstream(analysis, now))
    assert again["transitions"] == 0 and again["created"] == 0
    with _db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ae_transition").fetchone()[0] == before

    # A new closed bar resolves the shadow plan; the family does not immediately re-arm.
    later = now + H1
    third = _engine().run_cycle(later, upstream=_upstream(_analysis(cores, CRAFTED), later))
    assert third["closed"] == 1 and third["created"] == 0
    with _db() as conn:
        repo = _repo(conn)
        [o] = repo.opportunities(status="CLOSED")
        assert (o["state"], o["outcome"]) == ("COMPLETED", "TARGET_1") and o["evidence"]["outcome"]["r_multiple"] > 0
        assert repo.stages()["LEARNING"]["metrics"]["outcomes"] == {"TARGET_1": 1}


def test_engine_recovery_replays_missed_bars_in_order(live, cores):
    early = T0 + H1 + timedelta(minutes=5)
    _engine().run_cycle(early, upstream=_upstream(_analysis(cores, CRAFTED[:2]), early))
    with _db() as conn:
        assert [t["to_state"] for t in _opp_transitions(conn)] == ["WAITING_FOR_ZONE"]
    late = T0 + 5 * H1 + timedelta(minutes=5)  # four hours of worker downtime
    report = _engine().run_cycle(late, upstream=_upstream(_analysis(cores, CRAFTED), late))
    assert report["origin"] == "RECOVERY"
    with _db() as conn:
        trail = _opp_transitions(conn)
        assert [t["to_state"] for t in trail] == ["WAITING_FOR_ZONE", "AWAITING_REACTION", "REACTION_CONFIRMED", "RISK_REVIEW",
                                                  "RISK_APPROVED", "EXECUTION_BLOCKED_ANALYSIS_ONLY", "COMPLETED"]
        times = [t["evidence_at"] for t in trail]
        assert times == sorted(times) and times[1] == (T0 + 2 * H1).isoformat()
        actions = [tuple(r)[0] for r in conn.execute("SELECT action FROM audit_events").fetchall()]
        assert "AUTONOMOUS_RECOVERY_REPLAY" in actions


def test_engine_history_gap_waits_instead_of_skipping(live, cores):
    gapped = CRAFTED[:2] + CRAFTED[4:]  # two H1 bars missing mid-week
    now = T0 + 5 * H1 + timedelta(minutes=5)
    _engine().run_cycle(now, upstream=_upstream(_analysis(cores, gapped), now))
    with _db() as conn:
        [o] = _repo(conn).opportunities(status="ACTIVE")
        assert o["state"] == "WAITING_FOR_ZONE" and o["evaluated_through"] == (T0 + H1).isoformat()
        assert any("History gap" in b for b in o["blockers"])


def test_engine_safety_halts_progression(live, cores):
    now = T0 + 4 * H1 + timedelta(minutes=10)
    with _db() as conn:
        conn.execute("UPDATE system_settings SET value_json=? WHERE key='system.mode'", ('"PAUSED"',))
        conn.commit()
    report = _engine().run_cycle(now, upstream=_upstream(_analysis(cores, CRAFTED[:5]), now))
    assert report["safety"] == "HALTED" and report["created"] == 0 and live == []
    stale_now = T0 + 10 * H1
    with _db() as conn:
        conn.execute("UPDATE system_settings SET value_json=? WHERE key='system.mode'", ('"ANALYSIS_ONLY"',))
        conn.commit()
    report = _engine().run_cycle(stale_now, upstream=_upstream(_analysis(cores, CRAFTED[:5]), stale_now))
    assert report["safety"] == "CRITICAL" and report["created"] == 0 and report["transitions"] == 0
    with _db() as conn:
        stages = _repo(conn).stages()
        assert stages["CHANNEL"]["status"] == "BLOCKED" and stages["OPPORTUNITY"]["blockers"]


def test_autonomous_package_has_no_broker_order_path():
    root = Path(__file__).resolve().parents[1] / "apps" / "api" / "app"
    for path in list((root / "autonomous").glob("*.py")) + [root / "routers" / "autonomous.py"]:
        assert not ORDER_APIS.search(path.read_text(encoding="utf-8")), path.name


# ----- API -----


def test_api_is_read_only_rbac_protected_and_cron_secured(live, cores, monkeypatch):
    from fastapi.testclient import TestClient

    for k in ("STRENGTH_ENGINE_ENABLED", "AI_OUTLOOK_SCHEDULER_ENABLED", "NOTIFICATIONS_ENABLED", "MARKET_SCANNER_ENABLED",
              "AUTONOMOUS_ENGINE_ENABLED"):
        monkeypatch.setenv(k, "0")
    now = T0 + 4 * H1 + timedelta(minutes=10)
    _engine().run_cycle(now, upstream=_upstream(_analysis(cores, CRAFTED[:5]), now))
    from apps.api.app.main import app

    with TestClient(app) as client:
        assert client.get("/api/autonomous/overview").status_code == 401
        r = client.post("/api/auth/login", json={"username": "cacsms", "password": "TestPass!123"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        ov = client.get("/api/autonomous/overview", headers=h).json()
        assert [s["key"] for s in ov["stages"]] == list(STAGE_KEYS) and len({s["color"] for s in ov["stages"]}) == 11
        assert ov["ribbon"]["operating_mode"] == "ANALYSIS_ONLY" and ov["ribbon"]["execution"] == "EXECUTION_BLOCKED_ANALYSIS_ONLY"
        assert ov["ribbon"]["last_successful_cycle"] and ov["safety"]["checks"]
        ch = client.get("/api/autonomous/stages/channel", headers=h).json()
        assert ch["number"] == 5 and "alerts" in ch and "channels" in ch
        rows = client.get("/api/autonomous/opportunities", headers=h).json()["rows"]
        assert rows[0]["stage"] == "EXECUTION" and rows[0]["parent_tf"] == "H8" and rows[0]["digits"] == 5
        hist = client.get(f"/api/autonomous/opportunities/{rows[0]['id']}/history", headers=h).json()
        assert hist["transitions"][-1]["to_state"] == "EXECUTION_BLOCKED_ANALYSIS_ONLY"
        assert client.get("/api/autonomous/opportunities/nope/history", headers=h).status_code == 404
        assert client.get("/api/autonomous/stages/nope", headers=h).status_code == 404
        monkeypatch.setenv("CRON_SECRET", "s3cret")
        assert client.get("/api/autonomous/jobs/cycle").status_code == 401
    mutating = [r for r in app.routes if getattr(r, "path", "").startswith("/api/autonomous") and set(getattr(r, "methods", ())) - {"GET", "HEAD"}]
    assert [r.path for r in mutating] == ["/api/autonomous/jobs/catch-up"]
