"""Autonomous engine service: lease-locked cycles that advance the persistent state machine from closed-bar evidence.

One cycle reads the scanner's normalized, provider-independent analysis (never a provider API), asks the Global
Safety Supervisor for a verdict, advances channel lineages and opportunities, and writes the 11 stage states, the
append-only transitions and its own cycle record in one transaction. A worker that was down resumes from each
entity's persisted watermark and replays the missed closed bars in order (RECOVERY), so restarts neither skip nor
duplicate transitions. Runs as a local thread, on demand from page reads (serverless) or from the secured cron job.
"""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from ..core.audit import write_audit
from ..core.database import db
from ..market import channel_intelligence as chan
from ..market.quality import assess as assess_quality
from ..market.scanner_analytics import Bar
from ..market.structure_overview_config import overview_settings
from ..market.trend_structure import trend_view
from ..market.trend_structure_config import trend_settings
from . import channels as lifecycle
from . import opportunities as opps
from . import supervisor
from .config import ENGINE_VERSION, LOCK_NAME, STAGE_KEYS, TF_DELTA, WORKERS, ae_settings, enabled
from .store import AERepository, det_id, now_iso

log = logging.getLogger("cacsms.autonomous")
H1 = timedelta(hours=1)
GOLD = "XAUUSD"
CHANNEL_PRIORITY = ("RETESTING", "BREAKING", "BROKEN", "TOUCHED", "CONTINUING", "MATURE", "ACTIVE", "FORMING")
CHANNEL_TASKS = {
    "RETESTING": "Validating retest hold", "BREAKING": "Confirming break closes", "BROKEN": "Watching for retest",
    "TOUCHED": "Evaluating boundary reaction", "CONTINUING": "Tracking continuation", "MATURE": "Monitoring boundaries",
    "ACTIVE": "Monitoring boundaries", "FORMING": "Validating touches",
}
CHANNEL_NEXT = {
    "FORMING": "Second touch on each boundary", "ACTIVE": "Boundary touch or break", "MATURE": "Boundary touch or break",
    "TOUCHED": "Rejection or close beyond the boundary", "BREAKING": "Confirmation closes beyond the boundary",
    "BROKEN": "Retest of the broken boundary", "RETESTING": "Close beyond the retest candle", "CONTINUING": "Follow-through",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def serverless() -> bool:
    return os.getenv("VERCEL", "").strip() == "1"


def _mode(conn) -> str:
    import json

    row = conn.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()
    try:
        return json.loads(dict(row)["value_json"]) if row else "ANALYSIS_ONLY"
    except (TypeError, ValueError, KeyError):
        return "ANALYSIS_ONLY"


def _open_snapshot(conn) -> dict | None:
    row = conn.execute("SELECT id, provider, account_id FROM mi_provider_snapshot WHERE finalized_at IS NULL "
                       "ORDER BY started_at DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def _holiday_gap(a: datetime, b: datetime) -> bool:
    d = a.date()
    while d <= b.date():
        if (d.month, d.day) in ((12, 25), (1, 1)):
            return True
        d += timedelta(days=1)
    return False


def continuous(symbol: str, bars: list[Bar]) -> tuple[list[Bar], str | None]:
    """Bars up to the first unexplained gap (weekend and holiday closures are not gaps)."""
    tolerance = 2 if symbol == GOLD else 1
    for i in range(1, len(bars)):
        hours = (bars[i].t - bars[i - 1].t) / H1
        if tolerance < hours < 40 and not _holiday_gap(bars[i - 1].t, bars[i].t):
            return bars[:i], (bars[i - 1].t + H1).isoformat()
    return bars, None


def _bos_h1(a: dict) -> list[dict]:
    return ((a.get("bos") or {}).get("H1") or {}).get("events") or []


def _midnight(now: datetime) -> str:
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _next_h1_close(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0) + H1


class AutonomousEngine:
    def __init__(self) -> None:
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._demand_lock = threading.Lock()
        self._last_demand_mono = 0.0
        self._last_report: dict = {}

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="autonomous-engine", daemon=True)
        self._thread.start()
        log.info("Autonomous engine started (owner=%s)", self.owner)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)

    def _run(self) -> None:
        # Let the scanner finish its first cycle before the first pass.
        self._stop.wait(5)
        while not self._stop.is_set():
            self.safe_cycle("WORKER")
            self._stop.wait(ae_settings().cycle_seconds)

    def safe_cycle(self, trigger: str) -> dict:
        try:
            self._last_report = self.run_cycle(trigger=trigger)
        except Exception as exc:  # noqa: BLE001 - a failed cycle is recorded and retried next interval
            log.exception("Autonomous cycle failed")
            self._last_report = {"error": type(exc).__name__}
        return self._last_report

    def tick_on_demand(self) -> dict:
        """Serverless: advance inside a page read when the last pass is older than the on-demand interval."""
        if self.running:
            return {"ran": False, "reason": "worker_thread"}
        if time.monotonic() - self._last_demand_mono < ae_settings().on_demand_seconds:
            return {"ran": False, "reason": "throttled"}
        if not self._demand_lock.acquire(blocking=False):
            return {"ran": False, "reason": "busy"}
        try:
            if time.monotonic() - self._last_demand_mono < ae_settings().on_demand_seconds:
                return {"ran": False, "reason": "throttled"}
            # Commit presence before the heavy pass. A serverless request can be cut off mid-cycle;
            # without this the open page stays on STALLED and the stale-stage banner.
            self._note_on_demand()
            report = self.safe_cycle("ON_DEMAND")
            return {"ran": "skipped" not in report and "error" not in report, **report}
        finally:
            self._last_demand_mono = time.monotonic()
            self._demand_lock.release()

    def _note_on_demand(self) -> None:
        """Mark workers present and stages touched so the page leaves the stalled/stale error while the pass runs."""
        if not serverless():
            return
        stamp = utcnow().isoformat()
        try:
            with db() as conn:
                from ..market.strength_intel_store import active_scope

                repo = AERepository(conn, active_scope(conn))
                for key, label in WORKERS.items():
                    repo.heartbeat(key, label, "ON_DEMAND", owner=self.owner, at=stamp)
                conn.execute(
                    "UPDATE ae_stage_state SET last_update=? WHERE tenant_id=? AND trading_account_id=?",
                    (stamp, repo.tenant, repo.account),
                )
                conn.commit()
        except Exception:
            log.exception("On-demand presence update failed")

    # ----- upstream -----

    @staticmethod
    def _advance_upstream() -> None:
        """Serverless has no scanner/strength threads: advance them first (each throttles itself)."""
        from ..market.scanner_engine import get_scanner_engine, scanner_enabled
        from ..market.strength_engine import get_strength_engine

        try:
            get_strength_engine().tick_on_demand()
        except Exception:  # noqa: BLE001
            log.exception("Strength advance failed")
        if scanner_enabled():
            try:
                get_scanner_engine().tick_on_demand()
            except Exception:  # noqa: BLE001
                log.exception("Scanner advance failed")

    @staticmethod
    def _threads() -> dict[str, bool]:
        from ..market.scanner_engine import get_scanner_engine, scanner_enabled
        from ..market.strength_engine import get_strength_engine
        from ..notifications.worker import enabled as notifications_enabled, get_notification_worker

        out = {}
        if scanner_enabled():
            out["market-scanner"] = get_scanner_engine().running
        if os.getenv("STRENGTH_ENGINE_ENABLED", "1").strip() not in ("0", "false", "no"):
            out["strength-engine"] = get_strength_engine().running
        if notifications_enabled():
            t = getattr(get_notification_worker(), "_thread", None)
            out["notification-worker"] = bool(t and t.is_alive())
        return out

    # ----- cycle -----

    def run_cycle(self, now: datetime | None = None, *, trigger: str = "MANUAL", upstream: dict | None = None) -> dict:
        """One pass. ``upstream`` injects scanner/strength state (tests and replays); otherwise the live engines are read."""
        from ..market.scanner_engine import get_scanner_engine
        from ..market.strength_engine import get_strength_engine

        now = now or utcnow()
        ae = ae_settings()
        if upstream is None:
            if serverless() or not get_scanner_engine().running:
                self._advance_upstream()
            scanner = get_scanner_engine()
            strength = get_strength_engine()
            upstream = {
                "state": scanner.analysis_state(), "scanner_meta": scanner.meta(), "strength_meta": strength.engine_meta() or {},
                "intel": strength.intelligence() or {}, "threads": self._threads(),
            }
        with db() as conn:
            started = time.perf_counter()
            db_ok = True
            try:
                conn.execute("SELECT 1").fetchone()
            except Exception:  # noqa: BLE001
                db_ok = False
            db_ms = (time.perf_counter() - started) * 1000
            from ..market.strength_intel_store import active_scope

            scope = active_scope(conn)
            repo = AERepository(conn, scope)
            if not repo.acquire_lock(LOCK_NAME, self.owner, ae.lock_seconds, now):
                return {"skipped": "locked"}
            cycle_id = str(uuid.uuid4())
            try:
                report = self._cycle(conn, repo, cycle_id, now, trigger, upstream, db_ok, db_ms, ae)
                conn.commit()
                return report
            except Exception as exc:
                conn.rollback()
                try:
                    repo.start_cycle({"id": cycle_id, "origin": trigger, "status": "FAILED", "operating_mode": _mode(conn),
                                      "safety_status": "UNKNOWN", "owner": self.owner, "started_at": now.isoformat(),
                                      "completed_at": utcnow().isoformat(), "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
                    repo.heartbeat("autonomous-engine", WORKERS["autonomous-engine"], "ERROR", owner=self.owner,
                                   error=f"{type(exc).__name__}: {str(exc)[:300]}")
                    write_audit(conn, scope[0] or None, None, "AUTONOMOUS_CYCLE_FAILED", "ae_cycle", cycle_id, None,
                                {"error": type(exc).__name__}, str(exc)[:500])
                    conn.commit()
                except Exception:  # noqa: BLE001
                    conn.rollback()
                raise
            finally:
                repo.release_lock(LOCK_NAME, self.owner)

    def _cycle(self, conn, repo: AERepository, cycle_id: str, now: datetime, trigger: str, up: dict, db_ok: bool, db_ms: float,
               ae) -> dict:
        from ..market.market_data import market_context
        from ..notifications.smtp import smtp_config

        t0 = time.perf_counter()
        stamp = now.isoformat()
        st = up["state"]
        analysis: dict = st.get("analysis") or {}
        rows: dict = st.get("rows") or {}
        mode = _mode(conn)
        from ..market.unified_status import compute_platform_status

        ctx = {**market_context(conn), **compute_platform_status(conn)}
        snapshot = _open_snapshot(conn)
        try:
            smtp = smtp_config(conn)
            # Disabled mail is not a fault. A configured server that cannot send still degrades the supervisor.
            smtp_ready = None if not smtp.enabled else smtp.ready
        except Exception:  # noqa: BLE001
            smtp_ready = None
        last_ok = repo.last_cycle("COMPLETED")
        previous = repo.last_cycle()
        gap = (now - datetime.fromisoformat(last_ok["completed_at"])).total_seconds() if last_ok and last_ok.get("completed_at") else None
        origin = "INITIAL" if last_ok is None else "RECOVERY" if gap is not None and gap > ae.recovery_after_seconds else trigger
        safety = supervisor.assess(now=now, mode=mode, ctx=ctx, analysis=analysis, scanner_meta=up.get("scanner_meta") or {},
                                   scanner_state=st, strength_meta=up.get("strength_meta") or {}, db_ok=db_ok, db_ms=db_ms,
                                   snapshot=snapshot, smtp_ready=smtp_ready, threads=up.get("threads"), serverless=serverless(), ae=ae)
        provider = st.get("provider") or ctx.get("active_provider")
        snapshot_id = st.get("snapshot_id")
        repo.start_cycle({"id": cycle_id, "origin": origin, "status": "RUNNING", "operating_mode": mode, "safety_status": safety["status"],
                          "provider": provider, "snapshot_id": snapshot_id, "scanner_cycle_id": st.get("cycle_id"),
                          "data_as_of": safety["data_as_of"], "owner": self.owner, "safety_json": safety, "started_at": stamp})
        tenant = repo.tenant or None
        if previous and previous.get("safety_status") not in (None, "UNKNOWN") and previous["safety_status"] != safety["status"]:
            write_audit(conn, tenant, None, "AUTONOMOUS_SAFETY_CHANGED", "ae_cycle", cycle_id, {"status": previous["safety_status"]},
                        {"status": safety["status"], "blockers": safety["blockers"]})
        if origin == "RECOVERY":
            write_audit(conn, tenant, None, "AUTONOMOUS_RECOVERY_REPLAY", "ae_cycle", cycle_id, None,
                        {"downtime_seconds": round(gap or 0), "last_completed_cycle": last_ok["id"] if last_ok else None})

        cs, ts, ovs = chan.channel_settings(), trend_settings(), overview_settings()
        ok = {s: a for s, a in analysis.items() if a and "excluded" not in a}
        stages: dict[str, dict] = {}
        counts: dict = {"transitions": 0}

        stages["MARKET_DATA"] = self._stage_market_data(analysis, ok, ctx, safety, st, now)
        stages["INTELLIGENCE"] = self._stage_intelligence(up.get("strength_meta") or {}, up.get("intel") or {}, safety, ctx)
        stages["SCANNER"] = self._stage_scanner(rows, up.get("scanner_meta") or {}, st, safety)
        trend = {s: trend_view(a["trend"], a["overview"], None, now, ts, ovs) for s, a in ok.items()
                 if a.get("trend") and a.get("overview") and a["overview"]["regimes"].get("W") is not None}
        stages["STRUCTURE"] = self._stage_structure(ok, trend, safety, now)

        sequence = [0]

        def record(t: dict) -> None:
            # Strictly increasing within the cycle: transitions sharing one evidence time keep their causal order.
            sequence[0] += 1
            created = (now + timedelta(microseconds=sequence[0])).isoformat(timespec="microseconds")
            if repo.add_transition({**t, "provider": provider, "cycle_id": cycle_id, "created_at": created}):
                counts["transitions"] += 1

        # Stage 5: channel lineages
        channel_changes = 0
        if safety["progress_analysis"]:
            active = {(c["symbol"], c["timeframe"]): c for c in repo.active_channels()}
            for sym, a in ok.items():
                core = a.get("channel") or {}
                for tf in chan.EVENT_TIMEFRAMES:
                    plan = lifecycle.advance(active.get((sym, tf)), (repo.tenant, repo.account), sym, tf, core.get(tf) or {}, ae, cs, stamp)
                    if plan["insert"]:
                        repo.insert_channel({**plan["insert"], "provider": provider})
                    if plan["update"]:
                        cid, fields = plan["update"]
                        repo.update_channel(cid, **fields, provider=provider)
                    for t in plan["transitions"]:
                        record(t)
                        channel_changes += 1
        stages["CHANNEL"] = self._stage_channel(repo, ok, safety, now, cs, channel_changes)

        # Stages 6–11: opportunities
        report = self._opportunities(conn, repo, ok, rows, st, safety, now, ae, cs, ts, ovs, record, provider, snapshot_id, mode)
        counts.update(report["counts"])
        stages.update(self._stage_pipeline(repo, report, safety, now, mode, ae))

        # Persist stage states
        for key in STAGE_KEYS:
            s = stages[key]
            success = s["status"] not in ("ERROR", "BLOCKED", "STALE")
            repo.put_stage(key, {**s, "provider": provider, "cycle_id": cycle_id, "last_update": stamp,
                                 "last_success_at": stamp if success else None})
        self._symbol_states(repo, analysis, rows, trend, report, provider, stamp)
        self._heartbeats(repo, up, stamp)
        repo.finish_cycle(cycle_id, status="COMPLETED", completed_at=(now + timedelta(seconds=time.perf_counter() - t0)).isoformat(),
                          counts_json={**counts, "symbols": len(analysis), "analysed": len(ok), "trigger": trigger, "engine": ENGINE_VERSION},
                          duration_ms=int((time.perf_counter() - t0) * 1000))
        return {"cycle_id": cycle_id, "origin": origin, "safety": safety["status"], **counts}

    # ----- opportunities -----

    def _bars_for(self, conn, sym: str, a: dict, since: str, provider, snapshot_id, ae) -> tuple[list[Bar], str | None]:
        h1 = [b for b in (a.get("h1") or []) if (b.t + H1).isoformat() > since]
        first = (a.get("h1") or [None])[0]
        if first is not None and (first.t + H1).isoformat() > since:
            from ..market.outlook.service import candles_between
            from ..market.repository import MarketRepository

            start = datetime.fromisoformat(since) - H1
            repo = MarketRepository(conn, provider=provider or "__unavailable__", snapshot_id=snapshot_id)
            older = candles_between(repo, "H1", [sym], start, first.t).get(sym, [])
            h1 = sorted([b for b in older if (b.t + H1).isoformat() > since], key=lambda b: b.t) + h1
        h1 = h1[: ae.max_replay_bars]
        return continuous(sym, h1)

    def _opportunities(self, conn, repo: AERepository, ok: dict, rows: dict, st: dict, safety: dict, now: datetime, ae, cs, ts, ovs,
                       record, provider, snapshot_id, mode) -> dict:
        stamp = now.isoformat()
        counts = {"created": 0, "advanced": 0, "closed": 0, "replayed_bars": 0, "risk_approved": 0, "risk_deferred": 0,
                  "risk_rejected": 0, "execution_blocked": 0, "candidates": 0}
        progress = safety["progress_opportunities"]
        halted = safety["status"] == "HALTED"
        active = repo.active_opportunities()
        portfolio = [o for o in active if o["stage"] == "EXECUTION"]
        blockers_global = safety["blockers"] if not progress else []
        tenant = repo.tenant or None

        def persist(o: dict, before: dict, steps: list[dict], blockers: list[str]) -> None:
            a = ok.get(o["symbol"]) or {}
            last = a.get("last_close")
            fields = {"stage": o["stage"], "state": o["state"], "stage_entered_at": o["stage_entered_at"],
                      "evaluated_through": o["evaluated_through"], "evidence_json": o.get("evidence") or {},
                      "blockers_json": blockers, "updated_at": stamp, "next_condition": opps.next_condition(o) if o["status"] == "ACTIVE" else None}
            if last:
                fields.update(current_price=last[1], price_at=last[0].isoformat())
            if steps:
                fields["reason_code"] = steps[-1]["reason_code"]
            if o["status"] == "CLOSED":
                fields.update(status="CLOSED", outcome=o.get("outcome"), closed_at=o.get("closed_at"))
            changed = steps or blockers != (before.get("blockers") or []) or fields.get("current_price") != before.get("current_price") \
                or o["evaluated_through"] != before.get("evaluated_through")
            if changed:
                repo.update_opportunity(o["id"], **fields)

        def apply(o: dict, steps: list[dict]) -> list[dict]:
            for s in steps:
                record({"entity_type": "OPPORTUNITY", "entity_id": o["id"], "symbol": o["symbol"], "timeframe": o["trigger_tf"],
                        "from_stage": s["from_stage"], "from_state": s["from_state"], "to_stage": s["to_stage"], "to_state": s["to_state"],
                        "reason_code": s["reason_code"], "detail": s["detail"], "evidence_at": s["evidence_at"], "evidence_json": s["evidence"]})
                o["stage"], o["state"], o["stage_entered_at"] = s["to_stage"], s["to_state"], s["evidence_at"]
                ev = dict(o.get("evidence") or {})
                if s["to_state"] == "REACTION_CONFIRMED":
                    ev["reaction"] = s["evidence"]
                elif s["to_state"] == "RISK_REVIEW":
                    ev["confirmation"] = s["evidence"]
                counts["advanced"] += 1
                if s["close"]:
                    o["status"], o["outcome"], o["closed_at"] = "CLOSED", s["outcome"], s["evidence_at"]
                    ev["outcome"] = {"result": s["outcome"], "reason": s["reason_code"], "at": s["evidence_at"], **s["evidence"]}
                    counts["closed"] += 1
                o["evidence"] = ev
                if s["to_state"] == "EXECUTION_BLOCKED_ANALYSIS_ONLY":
                    counts["execution_blocked"] += 1
                    write_audit(conn, tenant, None, "AUTONOMOUS_EXECUTION_BLOCKED", "ae_opportunity", o["id"], None,
                                {"symbol": o["symbol"], "direction": o["direction"], "type": o["opp_type"], "mode": mode,
                                 "evidence_at": s["evidence_at"]}, "Operating mode ANALYSIS_ONLY — no broker order submitted")
            return steps

        def gate(o: dict, to_stage: str, to_state: str, reason: str, at: str, evidence: dict, close: bool = False,
                 outcome: str | None = None) -> dict:
            return {"from_stage": o["stage"], "from_state": o["state"], "to_stage": to_stage, "to_state": to_state, "reason_code": reason,
                    "detail": opps.REASONS[reason], "evidence_at": at, "evidence": evidence, "close": close, "outcome": outcome}

        def risk(o: dict, at: str) -> tuple[bool, list[dict]]:
            """Risk gate; authorised plans continue into execution, which is always blocked (shadow tracking only)."""
            state, _, metrics = opps.risk_decision(o, [p for p in portfolio if p["id"] != o["id"]], ae)
            o["evidence"] = {**(o.get("evidence") or {}), "risk": {**metrics, "decided_at": at}}
            if state == "RISK_APPROVED":
                applied = apply(o, [gate(o, "RISK", "RISK_APPROVED", "RISK_APPROVED", at, metrics)])
                applied += apply(o, [gate(o, "EXECUTION", "EXECUTION_BLOCKED_ANALYSIS_ONLY", "EXECUTION_BLOCKED_ANALYSIS_ONLY", at,
                                          {"mode": mode, "broker_order": None})])
                portfolio.append(o)
                counts["risk_approved"] += 1
                return True, applied
            if state == "RISK_DEFERRED":
                counts["risk_deferred"] += 1
                if o["state"] == "RISK_DEFERRED":
                    return False, []
                return False, apply(o, [gate(o, "RISK", "RISK_DEFERRED", "RISK_DEFERRED", at, metrics)])
            counts["risk_rejected"] += 1
            return False, apply(o, [gate(o, "LEARNING", "RISK_REJECTED", "RISK_REJECTED", at, metrics, True, "REJECTED")])

        def progress_one(o: dict) -> None:
            before = dict(o)
            a = ok.get(o["symbol"])
            blockers: list[str] = list(blockers_global)
            all_steps: list[dict] = []
            if a is None:
                blockers.append("Instrument excluded from analysis — waiting for valid closed-bar data")
            elif progress:
                bars, gap_at = self._bars_for(conn, o["symbol"], a, o["evaluated_through"], provider, snapshot_id, ae)
                counts["replayed_bars"] += len(bars)
                if gap_at:
                    blockers.append(f"History gap after {gap_at} — waiting for missing H1 bars to be backfilled")
                remaining = bars
                for _ in range(4):
                    steps, through, needs = opps.evaluate(o, remaining, _bos_h1(a), ae)
                    all_steps += apply(o, steps)
                    o["evaluated_through"] = through
                    if o["status"] == "CLOSED" or not needs:
                        break
                    authorised, applied = risk(o, through)
                    all_steps += applied
                    if not authorised or o["status"] == "CLOSED":
                        break
                    remaining = [b for b in remaining if (b.t + H1).isoformat() > through]
                if o["status"] == "ACTIVE" and o["stage"] in ("OPPORTUNITY", "CONFIRMATION") and not gap_at:
                    reason = opps.structural_invalidation(o, a, now, cs, ts, ovs)
                    if reason:
                        at = max(o["evaluated_through"], a["last_close"][0].isoformat())
                        all_steps += apply(o, [gate(o, "LEARNING", "INVALIDATED", reason, at, {}, True, "INVALIDATED")])
                        o["evaluated_through"] = at
            elif halted:
                blockers = ["Operating mode halts autonomous progression"] + blockers
            persist(o, before, all_steps, blockers)

        for o in active:
            progress_one(o)

        # Detection (Stage 6): only from trustworthy data and while not halted
        families = {o["family_key"] for o in active if o["status"] == "ACTIVE"}
        if progress and not halted:
            for sym, a in ok.items():
                for cand in opps.detect(sym, a, rows.get(sym), now, ae, cs, ts, ovs):
                    counts["candidates"] += 1
                    if cand["family_key"] in families:
                        continue
                    last = repo.last_closed_family(cand["family_key"])
                    if last:
                        rearm = datetime.fromisoformat(last["evaluated_through"]) + TF_DELTA[cand["trigger_tf"]] * ae.rearm_bars
                        if datetime.fromisoformat(cand["origin_at"]) <= rearm:
                            continue
                    oid = det_id("OPP", repo.tenant, repo.account, cand["family_key"], cand["origin_at"])
                    row = {k: v for k, v in cand.items() if k != "evidence"}
                    o = {**row, "id": oid, "stage": "OPPORTUNITY", "state": "WAITING_FOR_ZONE", "status": "ACTIVE",
                         "reason_code": "OPPORTUNITY_DETECTED", "provider": provider, "snapshot_id": snapshot_id,
                         "evidence_json": cand["evidence"], "blockers_json": [], "stage_entered_at": cand["origin_at"],
                         "evaluated_through": cand["origin_at"], "created_at": stamp, "updated_at": stamp}
                    if not repo.insert_opportunity(o):
                        continue
                    families.add(cand["family_key"])
                    counts["created"] += 1
                    record({"entity_type": "OPPORTUNITY", "entity_id": oid, "symbol": sym, "timeframe": cand["trigger_tf"], "from_stage": None,
                            "from_state": None, "to_stage": "OPPORTUNITY", "to_state": "WAITING_FOR_ZONE", "reason_code": "OPPORTUNITY_DETECTED",
                            "detail": opps.REASONS["OPPORTUNITY_DETECTED"], "evidence_at": cand["origin_at"],
                            "evidence_json": {**cand["evidence"], "confidence": cand["confidence"], "quality": cand["quality"]}})
                    fresh = repo.opportunity(oid)
                    if fresh:
                        progress_one(fresh)
        return {"counts": counts, "progress": progress, "halted": halted}

    # ----- stage summaries -----

    @staticmethod
    def _base(status: str, operation: str, nxt: str, processed=0, active=0, waiting=0, errors=0, metrics=None, blockers=None,
              detail=None) -> dict:
        return {"status": status, "current_operation": operation, "next_operation": nxt, "processed": processed, "active": active,
                "waiting": waiting, "errors": errors, "metrics_json": metrics or {}, "blockers_json": blockers or [], "detail_json": detail or {}}

    def _stage_market_data(self, analysis: dict, ok: dict, ctx: dict, safety: dict, st: dict, now: datetime) -> dict:
        provider = ctx.get("active_provider")
        label = supervisor.PROVIDER_LABELS.get(provider or "", provider or "none")
        fresh = {"FRESH": 0, "AGING": 0, "STALE": 0, "MARKET_CLOSED": 0}
        rows, blockers = [], []
        for sym in sorted(analysis):
            a = analysis[sym] or {}
            if "excluded" in a:
                rows.append({"symbol": sym, "excluded": a["excluded"]})
                blockers.append(f"{sym}: {a['excluded']}")
                continue
            q = assess_quality(sym, "H1", a["last_close"][0], now=now)
            state = q.state if safety["market_open"] else "MARKET_CLOSED"
            fresh[state] = fresh.get(state, 0) + 1
            rows.append({"symbol": sym, "last_close_at": a["last_close"][0].isoformat(), "close": a["last_close"][1], "freshness": state})
        excluded = len(analysis) - len(ok)
        if ctx.get("provider_phase") == "OFFLINE" or not ctx.get("active_provider"):
            status, op = "OFFLINE", "No market-data provider selected"
        elif not ctx.get("market_data_ready") or ctx.get("provider_phase") == "SYNCHRONIZING":
            loaded = ctx.get("strength_pairs_loaded") or 0
            status, op = "SYNCHRONIZING", f"Synchronizing closed bars ({loaded}/28 strength basket)"
        elif not analysis:
            status, op = "WAITING", f"Awaiting first closed-bar sync from {label}"
        elif fresh.get("STALE"):
            status, op = "STALE", f"{fresh['STALE']} instruments with stale closed bars"
        else:
            status, op = "RUNNING", f"Closed-bar data current via {label}: {len(ok)}/{len(analysis)} instruments"
        nxt = (safety["blockers"][0] if status in ("BLOCKED", "OFFLINE", "SYNCHRONIZING") and safety.get("blockers")
               else f"Next H1 close {_next_h1_close(now).strftime('%H:%M')} UTC")
        return self._base(status, op, nxt, processed=len(ok), active=len(ok) if status == "RUNNING" else 0,
                          waiting=len(analysis) - len(ok) if status == "SYNCHRONIZING" else 0, errors=excluded,
                          metrics={"provider": provider, "provider_label": label, "connected": bool(ctx.get("provider_connected")),
                                   "provider_phase": ctx.get("provider_phase"), "data_phase": ctx.get("data_phase"),
                                   "snapshot_id": st.get("snapshot_id"), "data_as_of": safety["data_as_of"], "freshness": fresh,
                                   "market_open": safety["market_open"], "selection_mode": ctx.get("selection_mode")},
                          blockers=blockers[:20], detail={"instruments": rows})

    def _stage_intelligence(self, meta: dict, intel: dict, safety: dict, ctx: dict | None = None) -> dict:
        scores = intel.get("scores") or {}
        avg = sorted(((c, (v or {}).get("AVG")) for c, v in scores.items() if (v or {}).get("AVG") is not None), key=lambda x: -x[1])
        loaded = meta.get("pairs_loaded") or (ctx or {}).get("strength_pairs_loaded") or 0
        live = bool(meta.get("live_data"))
        engine_state = meta.get("engine_state") or (ctx or {}).get("strength_engine_state")
        if not safety["progress_analysis"]:
            status, op = "BLOCKED", "Upstream market data not ready"
            nxt = safety["blockers"][0] if safety.get("blockers") else "Restore provider readiness"
        elif not meta.get("as_of") and loaded < 1:
            status, op = "SYNCHRONIZING", f"Building strength basket (0/28 pairs)"
            nxt = "First closed-bar calculation"
        elif loaded < 28:
            status, op = "SYNCHRONIZING", f"Strength basket {loaded}/28 pairs ({engine_state or 'sync'})"
            nxt = "Complete missing pair history" if meta.get("missing_pairs") else "Recalculate on next closed bar"
        elif not live:
            status, op = "DEGRADED", f"Strength not live ({meta.get('stale_reason') or engine_state})"
            nxt = "Recalculate on the next closed bar"
        else:
            status, op = "RUNNING", f"Currency strength on closed bars: {loaded}/28 pairs"
            nxt = "Recalculate on the next closed bar"
        blockers = [f"{m['symbol']} {m['timeframe']}: missing history" for m in (meta.get("missing_history") or [])[:10]]
        if not blockers and meta.get("missing_pairs"):
            blockers = [f"Missing pair: {p}" for p in (meta.get("missing_pairs") or [])[:10]]
        return self._base(status, op, nxt, processed=loaded, active=len(avg) if status == "RUNNING" else 0,
                          waiting=max(0, 28 - loaded) if status == "SYNCHRONIZING" else max(0, 28 - loaded),
                          errors=len(meta.get("missing_history") or []),
                          metrics={"as_of": meta.get("as_of"), "live": live, "engine_state": meta.get("engine_state"),
                                   "strongest": avg[0][0] if avg else None, "weakest": avg[-1][0] if avg else None},
                          blockers=blockers, detail={"currencies": [{"currency": c, "score": round(s, 1)} for c, s in avg]})

    def _stage_scanner(self, rows: dict, meta: dict, st: dict, safety: dict) -> dict:
        keys = ("HIGH_INSPECTION", "WATCHING", "NEUTRAL", "EXCLUDED")
        counts = {k: sum(1 for r in rows.values() if (r.get("status") or {}).get("key") == k) for k in keys}
        top = sorted((r for r in rows.values() if r.get("score") is not None), key=lambda r: -(r["score"] or 0))[:12]
        if meta.get("engine_state") == "ERROR":
            status, op = "ERROR", f"Scanner error: {meta.get('engine_error')}"
        elif not rows:
            status, op = "WAITING", "Awaiting first scanner cycle"
        elif meta.get("stale"):
            status, op = "STALE", f"Scanner stale ({meta.get('stale_reason')})"
        else:
            status, op = "RUNNING", f"Ranked {len(rows) - counts['EXCLUDED']} instruments — {counts['HIGH_INSPECTION']} high inspection"
        return self._base(status, op, "Re-rank on the next analysis cycle", processed=len(rows) - counts["EXCLUDED"],
                          active=counts["HIGH_INSPECTION"] + counts["WATCHING"], waiting=counts["NEUTRAL"], errors=counts["EXCLUDED"],
                          metrics={"counts": counts, "cycle_id": st.get("cycle_id"),
                                   "cycle_at": st["cycle_at"].isoformat() if st.get("cycle_at") else None},
                          detail={"top": [{"symbol": r["symbol"], "status": r["status"]["key"], "score": r["score"],
                                           "structure": (r.get("structure") or {}).get("key"), "reason": (r.get("reasons") or [None])[0]}
                                          for r in top]})

    def _stage_structure(self, ok: dict, trend: dict, safety: dict, now: datetime) -> dict:
        since = (now - timedelta(hours=24)).isoformat()
        bos_recent = []
        for sym, a in ok.items():
            for tf in ("H8", "H1"):
                for e in ((a.get("bos") or {}).get(tf) or {}).get("events") or []:
                    if e.get("at", "") >= since:
                        bos_recent.append({"symbol": sym, "tf": tf, "kind": e.get("kind"), "direction": e.get("direction"),
                                           "level": e.get("level"), "at": e.get("at"), "failed": bool(e.get("failed"))})
        bos_recent.sort(key=lambda e: e["at"], reverse=True)
        avail = {s: v for s, v in trend.items() if v.get("available")}
        trending = [s for s, v in avail.items() if v["direction"]]
        cont = [s for s, v in avail.items() if v["setup"]["key"] == "CONTINUATION"]
        rev = [s for s, v in avail.items() if v["setup"]["key"] == "REVERSAL_RISK"]
        status = "BLOCKED" if not safety["progress_analysis"] else "WAITING" if not avail else "RUNNING"
        op = (f"Trend structure on closed bars: {len(trending)} trending, {len(cont)} continuation pullbacks" if avail
              else "Awaiting closed-bar analysis")
        rows = sorted(({"symbol": s, "direction": v["direction"], "state": v["state"]["key"], "setup": v["setup"]["key"],
                        "strength": v["strength"], "confidence": v["confidence"]} for s, v in avail.items()),
                      key=lambda r: (-(r["strength"] or 0), r["symbol"]))
        return self._base(status, op, "Re-evaluate swings and BOS on the next closed bar", processed=len(avail), active=len(trending),
                          waiting=len(avail) - len(trending), errors=len(ok) - len(avail),
                          metrics={"trending": len(trending), "continuation": len(cont), "reversal_risk": len(rev),
                                   "bos_24h": sum(1 for e in bos_recent if e["kind"] == "BOS"),
                                   "choch_24h": sum(1 for e in bos_recent if e["kind"] == "CHOCH")},
                          blockers=safety["blockers"] if not safety["progress_analysis"] else [],
                          detail={"symbols": rows, "events": bos_recent[:20]})

    def _stage_channel(self, repo: AERepository, ok: dict, safety: dict, now: datetime, cs, changes: int) -> dict:
        lineages = repo.active_channels()
        today = repo.transition_counts("CHANNEL", _midnight(now))
        tit_active = []
        for sym, a in ok.items():
            t = chan.tit_view(sym, a.get("channel") or {}, None, cs)
            if t.get("available") and t.get("setup") and t["setup"]["status"]["key"] in ("ACTIVE", "MONITORING"):
                tit_active.append({"symbol": sym, "layer": t["countertrend"]["layer"], "tf": t["countertrend"]["tf"],
                                   "status": t["setup"]["status"]["key"], "quality": t["setup"]["quality"]})
        quality = [c["quality"] for c in lineages if c.get("quality") is not None]
        ranked = sorted(lineages, key=lambda c: (CHANNEL_PRIORITY.index(c["state"]) if c["state"] in CHANNEL_PRIORITY else 99,
                                                 -(c.get("quality") or 0)))
        queue = []
        for c in ranked[:12]:
            nxt = (datetime.fromisoformat(c["last_bar_at"]) + TF_DELTA[c["timeframe"]]).isoformat() if c.get("last_bar_at") else None
            queue.append({"channel_id": c["id"], "symbol": c["symbol"], "timeframe": c["timeframe"], "state": c["state"],
                          "task": CHANNEL_TASKS.get(c["state"], "Monitoring"), "next_at": nxt,
                          "status": "Due" if nxt and nxt <= now.isoformat() else "Pending"})
        current = None
        if ranked:
            c = ranked[0]
            path = ("FORMING", "ACTIVE", "MATURE", "TOUCHED", "BREAKING", "BROKEN", "RETESTING", "CONTINUING")
            idx = path.index(c["state"]) if c["state"] in path else 0
            current = {"channel_id": c["id"], "symbol": c["symbol"], "timeframe": c["timeframe"], "state": c["state"],
                       "task": f"{CHANNEL_TASKS.get(c['state'], 'Monitoring')} — {c['symbol']} {c['timeframe']}",
                       "started_at": c.get("state_entered_at"), "next_step": CHANNEL_NEXT.get(c["state"]),
                       "progress": round(100 * (idx + 1) / len(path))}
        paused = not safety["progress_analysis"]
        status = "BLOCKED" if paused else "WAITING" if not lineages else "RUNNING"
        op = ("Stored channel lineages (not refreshed this cycle)" if paused and lineages
              else current["task"] if current else "Awaiting channel geometry from closed bars")
        nxt = safety["blockers"][0] if paused and safety.get("blockers") else (current["next_step"] if current else "Next closed bar")
        markets = len({c["symbol"] for c in lineages})
        metrics = {
            "active_channels": len(lineages), "stored_lineages": len(lineages), "live_refresh": not paused,
            "markets": markets, "touches_today": today.get("TOUCHED", 0), "breaks_today": today.get("BROKEN", 0),
            "breaking_today": today.get("BREAKING", 0), "retests_today": today.get("RETESTING", 0),
            "continuations_today": today.get("CONTINUING", 0), "tit_active": len(tit_active),
            "avg_quality": round(sum(quality) / len(quality), 1) if quality else None,
            "invalidated_today": today.get("INVALIDATED", 0) + today.get("EXPIRED", 0),
            "by_state": {s: sum(1 for c in lineages if c["state"] == s) for s in CHANNEL_PRIORITY}, "changes_this_cycle": changes,
        }
        waiting = sum(1 for c in lineages if c["state"] in ("FORMING", "ACTIVE", "MATURE"))
        live_active = 0 if paused else len(lineages) - waiting
        return self._base(status, op, nxt, processed=len(ok) * len(chan.EVENT_TIMEFRAMES) if not paused else 0,
                          active=live_active, waiting=len(lineages) if paused else waiting, errors=0, metrics=metrics,
                          blockers=safety["blockers"] if not safety["progress_analysis"] else [],
                          detail={"queue": queue, "current": current, "tit": tit_active[:20]})

    def _stage_pipeline(self, repo: AERepository, report: dict, safety: dict, now: datetime, mode: str, ae) -> dict:
        active = repo.active_opportunities()
        today = repo.transition_counts("OPPORTUNITY", _midnight(now))
        blocked = not report["progress"]
        blockers = safety["blockers"] if blocked else []

        def at(stage: str, state: str | None = None) -> list[dict]:
            return [o for o in active if o["stage"] == stage and (state is None or o["state"] == state)]

        waiting = at("OPPORTUNITY")
        by_type: dict[str, int] = {}
        for o in waiting:
            by_type[o["opp_type"]] = by_type.get(o["opp_type"], 0) + 1
        out = {}
        nearest = sorted(waiting, key=lambda o: -(o.get("confidence") or 0))[:1]
        out["OPPORTUNITY"] = self._base(
            "BLOCKED" if blocked else "RUNNING" if waiting else "WAITING",
            (f"Tracking {len(waiting)} opportunities waiting for their entry zone" if waiting else "No qualifying setup on closed bars"),
            "Closed H1 bar inside an entry zone", processed=report["counts"]["candidates"], active=len(waiting), waiting=len(waiting),
            metrics={"created_today": today.get("WAITING_FOR_ZONE", 0), "by_type": by_type, "created_this_cycle": report["counts"]["created"],
                     "focus": nearest[0]["symbol"] if nearest else None},
            blockers=blockers)
        awaiting, reacted = at("CONFIRMATION", "AWAITING_REACTION"), at("CONFIRMATION", "REACTION_CONFIRMED")
        conf_next = blockers[0] if blocked and blockers else "Rejection candle, then close beyond it or H1 BOS"
        out["CONFIRMATION"] = self._base(
            "BLOCKED" if blocked else "RUNNING" if awaiting or reacted else "WAITING",
            (f"{len(awaiting)} awaiting reaction, {len(reacted)} awaiting break confirmation" if awaiting or reacted
             else "No opportunity inside its entry zone"),
            conf_next, processed=today.get("AWAITING_REACTION", 0), active=len(reacted) if not blocked else 0,
            waiting=len(awaiting), errors=0,
            metrics={"confirmed_today": today.get("RISK_REVIEW", 0), "expired_today": today.get("EXPIRED", 0),
                     "invalidated_today": today.get("INVALIDATED", 0)},
            blockers=blockers)
        deferred = at("RISK", "RISK_DEFERRED") + at("RISK", "RISK_REVIEW")
        execution = at("EXECUTION")
        exposure: dict[str, int] = {}
        for o in execution:
            d = opps.SIGN[o["direction"]]
            b, q = opps.currencies(o["symbol"])
            exposure[b] = exposure.get(b, 0) + d
            exposure[q] = exposure.get(q, 0) - d
        risk_next = blockers[0] if blocked and blockers else "Next confirmed opportunity"
        out["RISK"] = self._base(
            "BLOCKED" if blocked or report["halted"] else "RUNNING" if deferred or today.get("RISK_APPROVED") else "WAITING",
            (f"{today.get('RISK_APPROVED', 0)} authorised, {len(deferred)} deferred, {today.get('RISK_REJECTED', 0)} rejected today"),
            risk_next, processed=today.get("RISK_APPROVED", 0) + today.get("RISK_REJECTED", 0), active=len(execution) if not blocked else 0,
            waiting=len(deferred), errors=0,
            metrics={"authorised_today": today.get("RISK_APPROVED", 0), "deferred": len(deferred), "rejected_today": today.get("RISK_REJECTED", 0),
                     "exposure": {k: v for k, v in exposure.items() if v}, "max_concurrent": ae.max_concurrent,
                     "min_reward_risk": ae.min_reward_risk, "max_currency_exposure": ae.max_currency_exposure},
            blockers=blockers + (["Operating mode halts risk authorisation"] if report["halted"] else []))
        out["EXECUTION"] = self._base(
            "BLOCKED", "EXECUTION_BLOCKED_ANALYSIS_ONLY — no broker orders are submitted",
            "Execution stays disabled while the operating mode is ANALYSIS ONLY", processed=today.get("EXECUTION_BLOCKED_ANALYSIS_ONLY", 0),
            active=0, waiting=len(execution), errors=0,
            metrics={"orders_submitted": 0, "blocked_today": today.get("EXECUTION_BLOCKED_ANALYSIS_ONLY", 0), "operating_mode": mode,
                     "execution_state": "EXECUTION_BLOCKED_ANALYSIS_ONLY", "shadow_plans": len(execution)},
            blockers=["Operating mode ANALYSIS ONLY — broker execution disabled"])
        out["MANAGEMENT"] = self._base(
            "IDLE", "No broker positions — execution is disabled", "Manages positions only when execution is enabled",
            processed=0, active=0, waiting=0, errors=0, metrics={"open_positions": 0, "broker_orders": 0, "shadow_plans_tracked": len(execution)})
        since = (now - timedelta(days=30)).isoformat()
        closed = repo.closed_opportunities(since)
        outcomes: dict[str, int] = {}
        by_type_perf: dict[str, dict] = {}
        rs = []
        for o in closed:
            oc = o.get("outcome") or "UNKNOWN"
            outcomes[oc] = outcomes.get(oc, 0) + 1
            t = by_type_perf.setdefault(o["opp_type"], {"closed": 0, "target_1": 0, "stopped": 0})
            t["closed"] += 1
            t["target_1"] += oc == "TARGET_1"
            t["stopped"] += oc == "STOPPED"
            r = ((o.get("evidence") or {}).get("outcome") or {}).get("r_multiple")
            if r is not None:
                rs.append(r)
        resolved = outcomes.get("TARGET_1", 0) + outcomes.get("STOPPED", 0)
        out["LEARNING"] = self._base(
            "RUNNING" if closed else "WAITING",
            (f"{len(closed)} closed opportunities in 30 days — "
             + (f"shadow hit rate {round(100 * outcomes.get('TARGET_1', 0) / resolved)}% over {resolved} resolved plans" if resolved
                else "no shadow plan has reached its target or stop yet")
             if closed else "No closed opportunity outcomes yet"),
            "Record outcomes as opportunities resolve", processed=len(closed), active=len(execution), waiting=0, errors=0,
            metrics={"closed_30d": len(closed), "outcomes": outcomes, "hit_rate": round(100 * outcomes.get("TARGET_1", 0) / resolved, 1) if resolved else None,
                     "avg_r": round(sum(rs) / len(rs), 2) if rs else None, "by_type": by_type_perf})
        return out

    def _symbol_states(self, repo: AERepository, analysis: dict, rows: dict, trend: dict, report: dict, provider, stamp: str) -> None:
        order = {k: i for i, k in enumerate(STAGE_KEYS)}
        best: dict[str, dict] = {}
        for o in repo.active_opportunities():
            cur = best.get(o["symbol"])
            if cur is None or order[o["stage"]] > order[cur["stage"]]:
                best[o["symbol"]] = o
        for sym, a in analysis.items():
            a = a or {}
            if "excluded" in a:
                repo.put_symbol(sym, {"stage": "MARKET_DATA", "state": "EXCLUDED", "reason_code": "DATA_UNAVAILABLE", "provider": provider,
                                      "evidence_json": {"reason": a["excluded"]}, "updated_at": stamp})
                continue
            o = best.get(sym)
            data_as_of = a["last_close"][0].isoformat()
            if o:
                repo.put_symbol(sym, {"stage": o["stage"], "state": o["state"], "reason_code": o.get("reason_code"), "provider": provider,
                                      "data_as_of": data_as_of, "evidence_json": {"opportunity_id": o["id"], "type": o["opp_type"]},
                                      "updated_at": stamp})
                continue
            tv = trend.get(sym) or {}
            status = ((rows.get(sym) or {}).get("status") or {}).get("key")
            if tv.get("available") and tv.get("direction"):
                repo.put_symbol(sym, {"stage": "STRUCTURE", "state": tv["setup"]["key"], "reason_code": "WAITING_FOR_SETUP",
                                      "provider": provider, "data_as_of": data_as_of,
                                      "evidence_json": {"direction": tv["direction"], "scanner": status}, "updated_at": stamp})
            else:
                repo.put_symbol(sym, {"stage": "SCANNER", "state": status or "ANALYSED", "reason_code": "NO_TREND", "provider": provider,
                                      "data_as_of": data_as_of, "evidence_json": {}, "updated_at": stamp})

    def _heartbeats(self, repo: AERepository, up: dict, stamp: str) -> None:
        threads = up.get("threads") or {}
        mode = "ON_DEMAND" if serverless() else None
        repo.heartbeat("autonomous-engine", WORKERS["autonomous-engine"], "RUNNING" if self.running else mode or "ON_DEMAND",
                       owner=self.owner, success_at=stamp, detail={"engine": ENGINE_VERSION}, at=stamp)
        meta = up.get("scanner_meta") or {}
        sstate = "ERROR" if meta.get("engine_state") == "ERROR" else "RUNNING" if threads.get("market-scanner") else mode or "STOPPED"
        repo.heartbeat("market-scanner", WORKERS["market-scanner"], sstate, success_at=meta.get("last_cycle_at"),
                       error=meta.get("engine_error"), detail={"cycle_id": meta.get("cycle_id"), "state": meta.get("engine_state")}, at=stamp)
        sm = up.get("strength_meta") or {}
        strength_state = "RUNNING" if threads.get("strength-engine") else mode or "STOPPED"
        repo.heartbeat("strength-engine", WORKERS["strength-engine"], strength_state, success_at=sm.get("live_refresh_at") or sm.get("as_of"),
                       error=sm.get("engine_error"), detail={"state": sm.get("engine_state"), "live": sm.get("live_data")}, at=stamp)
        if "notification-worker" in threads or serverless():
            repo.heartbeat("notification-worker", WORKERS["notification-worker"],
                           "RUNNING" if threads.get("notification-worker") else mode or "STOPPED", at=stamp)


_engine: AutonomousEngine | None = None
_engine_lock = threading.Lock()


def get_autonomous_engine() -> AutonomousEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = AutonomousEngine()
        return _engine


__all__ = ["AutonomousEngine", "get_autonomous_engine", "enabled", "continuous", "now_iso"]
