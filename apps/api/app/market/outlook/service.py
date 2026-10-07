"""AI Market Outlook (Daily) orchestration.

MarketSnapshotService → DataQualityValidator → AIIntelligenceOrchestrator (per-symbol engine pipeline) →
OpportunityRankingEngine → OutlookPublisher, plus IntradayOutlookMonitor, OutcomeEvaluator, CalibrationEngine and the
DailyOutlookScheduler. Runs on the broker trading calendar from the server (cron / background thread) — never from a browser.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from ...core.audit import write_audit
from ...core.database import db
from ..pair_relationships import pair_relationship
from ..repository import MarketRepository
from ..scanner_analytics import Bar
from ..scanner_config import GOLD
from ..scanner_engine import BARS, SCANNER_UNIVERSE, analysis_cores, get_scanner_engine, scanner_enabled
from ..strength_intel_store import active_scope, reference_scores
from . import calendar as cal
from .config import ENGINE_VERSION, OutlookSettings, outlook_settings
from .engine import build_outlook, insufficient, validate
from .evaluation import calibration_table, evaluate, monitor, performance
from .store import DONE_STATES, OutlookRepository, now_iso

log = logging.getLogger("cacsms.ai_outlook")
LOCK = "ai-outlook-daily"
ACTIVE_STATES = ("SNAPSHOTTING", "VALIDATING_DATA", "ANALYSING", "GENERATING_HYPOTHESES", "SCORING", "PROJECTING",
                 "RANKING_OPPORTUNITIES", "PUBLISHING")
STRENGTH_MAX_AGE = timedelta(hours=36)
FAILED_RECOVERY_MINUTES = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _entry(state: str, message: str, **extra) -> dict:
    return {"at": now_iso(), "state": state, "message": message, **extra}


# ----- MarketSnapshotService -----


def _bars(rows) -> dict[str, list[Bar]]:
    out: dict[str, list[Bar]] = {}
    for r in rows:
        sym, ot, o, h, l, c, v = (tuple(r.values()) if isinstance(r, dict) else tuple(r))[:7]
        t = datetime.fromisoformat(str(ot))
        out.setdefault(str(sym), []).append(Bar(t if t.tzinfo else t.replace(tzinfo=timezone.utc), float(o), float(h), float(l), float(c), int(v or 0)))
    for hist in out.values():
        hist.sort(key=lambda b: b.t)
    return out


def _scope_sql(repo: MarketRepository) -> tuple[str, str, tuple]:
    if repo.provider_storage:
        return "mi_provider_candle", "source=? AND account_id=? AND ", (repo.provider, repo.account_id)
    return "mi_candle", "", ()


def candles_until(repo: MarketRepository, tf: str, limit: int, symbols, cutoff: datetime) -> dict[str, list[Bar]]:
    """Latest ``limit`` bars per symbol that had CLOSED by ``cutoff`` (one round trip per timeframe)."""
    table, scope, sp = _scope_sql(repo)
    member = (f"SELECT * FROM (SELECT symbol,open_time,open,high,low,close,tick_volume FROM {table} WHERE {scope}symbol=? AND timeframe=? "
              f"AND is_closed=1 AND close_time<=? ORDER BY open_time DESC LIMIT ?) AS s{{i}}")
    symbols = list(symbols)
    sql = " UNION ALL ".join(member.format(i=i) for i in range(len(symbols)))
    params = [v for sym in symbols for v in (*sp, sym, tf, cutoff.isoformat(), limit)]
    return _bars(repo.conn.execute(sql, params).fetchall())


def candles_between(repo: MarketRepository, tf: str, symbols, start: datetime, end: datetime) -> dict[str, list[Bar]]:
    table, scope, sp = _scope_sql(repo)
    member = (f"SELECT symbol,open_time,open,high,low,close,tick_volume FROM {table} WHERE {scope}symbol=? AND timeframe=? AND is_closed=1 "
              f"AND open_time>=? AND open_time<?")
    symbols = list(symbols)
    sql = " UNION ALL ".join(member for _ in symbols)
    params = [v for sym in symbols for v in (*sp, sym, tf, start.isoformat(), end.isoformat())]
    return _bars(repo.conn.execute(sql, params).fetchall())


def freeze_snapshot(repo: MarketRepository, analysis_date: date, origin: str) -> tuple[dict, dict[str, dict[str, list[Bar]]]]:
    """Closed-bar snapshot as of the trading day's close plus its manifest; the id is a content hash (reproducible)."""
    cutoff = cal.close_time(analysis_date)
    by_tf = {tf: candles_until(repo, tf, n, SCANNER_UNIVERSE, cutoff) for tf, n in BARS.items()}
    bars = {sym: {tf: by_tf[tf].get(sym, []) for tf in BARS} for sym in SCANNER_UNIVERSE}
    symbols = {}
    for sym, tfs in bars.items():
        symbols[sym] = {tf: {"bars": len(h), "first": h[0].t.isoformat() if h else None, "last": h[-1].t.isoformat() if h else None,
                             "last_close": h[-1].c if h else None} for tf, h in tfs.items()}
    digest = hashlib.sha256(json.dumps({"date": analysis_date.isoformat(), "origin": origin, "provider": repo.provider, "account": repo.account_id,
                                        "symbols": symbols, "engine": ENGINE_VERSION}, sort_keys=True).encode()).hexdigest()
    manifest = {"snapshot_id": f"snap-{analysis_date.isoformat()}-{digest[:12]}", "analysis_date": analysis_date.isoformat(), "origin": origin,
                "cutoff": cutoff.isoformat(), "frozen_at": now_iso(), "provider": repo.provider, "account_id": repo.account_id,
                "market_snapshot_id": repo.snapshot_id, "symbols": symbols}
    return manifest, bars


def strength_for(symbol: str, ref: tuple[datetime, dict] | None, cutoff: datetime) -> dict | None:
    """Strength Intelligence reading as of the frozen close (None when no snapshot is recent enough — never back-filled)."""
    if not ref or cutoff - ref[0] > STRENGTH_MAX_AGE or ref[0] > cutoff:
        return None
    at, scores = ref
    if symbol == GOLD:
        usd = (scores.get("USD") or {}).get("AVG")
        return None if usd is None else {"differential": round(50.0 - usd, 2), "alignment_pct": None, "as_of": at.isoformat(), "basis": "USD inverse"}
    pr = pair_relationship(symbol, scores)
    if not pr:
        return None
    return {"differential": pr["differential"], "alignment_pct": (pr.get("alignment") or {}).get("pct"), "as_of": at.isoformat(),
            "relationship": pr.get("relationship"), "base_strength": pr["base_strength"], "quote_strength": pr["quote_strength"]}


# ----- service -----


class OutlookService:
    def __init__(self) -> None:
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self.last_tick: dict | None = None

    # ----- DailyOutlookScheduler -----

    def tick(self, now: datetime | None = None, *, replay: bool = True, monitor_live: bool = True) -> dict:
        """One idempotent scheduler pass: LEARN (evaluate due outlooks) → generate today's outlook → MONITOR → replay backfill."""
        now = now or utcnow()
        s = outlook_settings()
        if not self._busy.acquire(blocking=False):
            return {"skipped": "busy"}
        try:
            with db() as conn:
                store = OutlookRepository(conn, active_scope(conn))
                if not store.acquire_lock(LOCK, self.owner, s.lock_seconds):
                    return {"skipped": "locked"}
                try:
                    report = {"at": now.isoformat()}
                    report["evaluated"] = self._evaluate_due(conn, store, now, s)
                    report["live"] = self._ensure_live(conn, store, now, s)
                    if monitor_live:
                        report["monitored"] = self._monitor(conn, store, now, s)
                    if replay and s.replay_days > 0:
                        report["replayed"] = self._replay(conn, store, now, s)
                    self.last_tick = report
                    return report
                finally:
                    store.release_lock(LOCK, self.owner)
        finally:
            self._busy.release()

    def start(self) -> None:
        self._stop.clear()
        if self._thread and self._thread.is_alive():
            return

        def loop():
            if self._stop.wait(15):
                return
            while not self._stop.is_set():
                try:
                    self.tick()
                except Exception:
                    log.exception("AI outlook scheduler tick failed")
                self._stop.wait(outlook_settings().monitor_seconds)

        self._thread = threading.Thread(target=loop, name="ai-outlook-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)

    @staticmethod
    def target_day(now: datetime, s: OutlookSettings) -> date:
        return cal.last_closed_day(now - timedelta(minutes=s.close_grace_minutes))

    def _ensure_live(self, conn, store: OutlookRepository, now: datetime, s: OutlookSettings) -> dict:
        day = self.target_day(now, s)
        for r in store.runs(origin="LIVE", limit=12):
            if r["analysis_date"] < day.isoformat() and r["state"] not in DONE_STATES + ("MISSED", "FAILED"):
                store.update_run(r["id"], state="MISSED", error="Not published before the next trading-day close",
                                 log=_entry("MISSED", "Deadline passed; covered by walk-forward replay instead"))
        run = store.run(day.isoformat(), "LIVE")
        if run is None:
            run = store.create_run(day.isoformat(), "LIVE", cal.close_time(day).isoformat(), ENGINE_VERSION)
            store.update_run(run["id"], log=_entry("SCHEDULED", f"D1 close {cal.close_time(day).isoformat()} detected"))
            self._audit(conn, store, "AI_OUTLOOK_RUN_SCHEDULED", run["id"], {"analysis_date": run["analysis_date"]})
        retry_due = run["state"] in ("RETRY", "INSUFFICIENT_DATA", "SCHEDULED") and (not run["next_retry_at"] or run["next_retry_at"] <= now.isoformat())
        stale = run["state"] in ACTIVE_STATES and run["updated_at"] < (now - timedelta(seconds=s.lock_seconds)).isoformat()
        recover = (run["state"] == "FAILED" and run["updated_at"] < (now - timedelta(minutes=FAILED_RECOVERY_MINUTES)).isoformat()
                   and now < cal.close_time(cal.next_trading_day(day)))
        if retry_due or stale or recover:
            self.execute(conn, store, store.run_by_id(run["id"]), now, s)  # type: ignore[arg-type]
            run = store.run_by_id(run["id"])
        return {"analysis_date": day.isoformat(), "state": run["state"], "run_id": run["id"]}  # type: ignore[index]

    # ----- AIIntelligenceOrchestrator (state machine) -----

    def execute(self, conn, store: OutlookRepository, run: dict, now: datetime, s: OutlookSettings) -> dict:
        rid, origin = run["id"], run["origin"]
        day = date.fromisoformat(run["analysis_date"])
        cutoff = cal.close_time(day)
        deadline = cal.close_time(cal.next_trading_day(day))
        attempts = int(run["attempts"] or 0) + 1
        store.update_run(rid, state="SNAPSHOTTING", attempts=attempts, started_at=now_iso(), error=None, next_retry_at=None,
                         log=_entry("SNAPSHOTTING", f"Attempt {attempts}: freezing closed bars as of {cutoff.isoformat()}"))
        counts = {"published": 0, "failed": 0, "insufficient": 0, "qualified": 0}
        try:
            repo = MarketRepository(conn)
            manifest, bars = freeze_snapshot(repo, day, origin)
            ref = reference_scores(conn, cutoff)
            prior = [e for e in store.evaluations() if e["analysis_date"] < day.isoformat()]
            table, samples = calibration_table(prior)
            manifest.update(strength_as_of=ref[0].isoformat() if ref else None, calibration_samples=samples)
            sid = store.save_snapshot(rid, day.isoformat(), cutoff.isoformat(), manifest)
            store.update_run(rid, snapshot_id=sid, state="VALIDATING_DATA", symbols_total=len(SCANNER_UNIVERSE),
                             log=_entry("SNAPSHOTTING", f"Snapshot {sid} frozen ({len(SCANNER_UNIVERSE)} instruments)"))

            expected = cal.d1_open_for(day)
            quality = {sym: validate(bars[sym], cutoff, expected) for sym in SCANNER_UNIVERSE}
            ok = [sym for sym in SCANNER_UNIVERSE if quality[sym]["status"] == "OK"]
            store.update_run(rid, state="ANALYSING", log=_entry("VALIDATING_DATA", f"{len(ok)}/{len(SCANNER_UNIVERSE)} instruments passed data validation"))
            if origin == "LIVE" and len(ok) < len(SCANNER_UNIVERSE) / 2 and now < deadline - timedelta(hours=1):
                store.update_run(rid, state="INSUFFICIENT_DATA", next_retry_at=(now + timedelta(minutes=10)).isoformat(),
                                 symbols_insufficient=len(SCANNER_UNIVERSE) - len(ok),
                                 log=_entry("INSUFFICIENT_DATA", "Closed D1 bars not yet available for most instruments; retrying in 10 minutes"))
                return store.run_by_id(rid)  # type: ignore[return-value]

            outs: list[dict] = []
            cores: dict[str, dict] = {}
            for sym in SCANNER_UNIVERSE:
                if sym not in ok:
                    bad = [c["note"] for c in quality[sym]["checks"] if not (c["complete"] and c["fresh"])]
                    outs.append(insufficient(sym, quality[sym], day.isoformat(), sid, cutoff, "; ".join(bad) or "Data quality below threshold"))
                    counts["insufficient"] += 1
                    continue
                try:
                    cores[sym] = analysis_cores(bars[sym], h8bb=False)
                except Exception as exc:
                    log.exception("AI outlook analysis failed for %s", sym)
                    outs.append(insufficient(sym, quality[sym], day.isoformat(), sid, cutoff, f"Engine error: {exc}", status="FAILED"))
                    counts["failed"] += 1
            store.update_run(rid, state="GENERATING_HYPOTHESES", log=_entry("ANALYSING", f"Specialist engines evaluated {len(cores)} instruments"))

            calibrated = 0
            for sym, a in cores.items():
                try:
                    d1 = bars[sym]["D1"]
                    o = build_outlook(sym, a, d1[-1].c, cutoff, strength_for(sym, ref, cutoff), quality[sym], table, s,
                                      analysis_date=day.isoformat(), snapshot_id=sid)
                    calibrated += 1 if o["confidence"]["calibration"]["applied"] else 0
                    outs.append(o)
                    counts["published"] += 1
                except Exception as exc:
                    log.exception("AI outlook hypothesis generation failed for %s", sym)
                    outs.append(insufficient(sym, quality[sym], day.isoformat(), sid, cutoff, f"Engine error: {exc}", status="FAILED"))
                    counts["failed"] += 1
            n_hyp = max((len(o.get("hypotheses") or []) for o in outs), default=0)
            store.update_run(rid, state="SCORING", log=_entry("GENERATING_HYPOTHESES", f"{n_hyp} competing hypotheses evaluated per instrument ({counts['published']} instruments)"))
            store.update_run(rid, state="PROJECTING", log=_entry("SCORING", f"Scenarios scored; calibration applied to {calibrated} ({samples} evaluated samples)"))
            store.update_run(rid, state="RANKING_OPPORTUNITIES", log=_entry("PROJECTING", "ERZ, objectives, invalidation, path and annotations projected"))

            qualified = sorted((o for o in outs if o.get("qualified")), key=lambda o: (o["symbol"] != GOLD, -(o["opportunity_score"] or 0)))
            for i, o in enumerate(qualified):
                o["opportunity_rank"] = i + 1
            counts["qualified"] = len(qualified)
            store.update_run(rid, state="PUBLISHING", log=_entry("RANKING_OPPORTUNITIES", f"{len(qualified)} qualified opportunities"))

            published_at = now_iso()
            asian = cal.session_windows(cutoff)[0]["start"]
            for o in outs:
                o.update(outlook_id=str(uuid.uuid4()), run_id=rid, origin=origin, published_at=published_at,
                         late=origin == "LIVE" and published_at > asian)
            store.insert_outlooks(run, outs)
            store.save_calibration(rid, table, samples)
            store.update_run(rid, state="PUBLISHED", published_at=published_at, symbols_published=counts["published"], symbols_failed=counts["failed"],
                             symbols_insufficient=counts["insufficient"], qualified=counts["qualified"],
                             log=_entry("PUBLISHED", f"Immutable outlook published: {counts['published']} analysed, {counts['qualified']} qualified, "
                                                     f"{counts['insufficient']} insufficient data, {counts['failed']} failed"))
            self._audit(conn, store, "AI_OUTLOOK_PUBLISHED", rid, {"analysis_date": day.isoformat(), "origin": origin, "snapshot_id": sid, **counts})
        except Exception as exc:
            log.exception("AI outlook run %s failed", rid)
            conn.rollback()
            final = attempts >= s.max_attempts
            store.update_run(rid, state="FAILED" if final else "RETRY", error=str(exc)[:500],
                             next_retry_at=None if final else (now + timedelta(minutes=2 ** attempts)).isoformat(),
                             log=_entry("FAILED" if final else "RETRY", f"{type(exc).__name__}: {exc}"[:300]))
            self._audit(conn, store, "AI_OUTLOOK_RUN_FAILED", rid, {"error": str(exc)[:300], "attempts": attempts, "final": final})
        return store.run_by_id(rid)  # type: ignore[return-value]

    def _audit(self, conn, store: OutlookRepository, action: str, rid: str, after: dict) -> None:
        try:
            write_audit(conn, store.tenant or None, None, action, "ai_outlook_run", rid, None, after, "Autonomous daily outlook cycle", rid)
            conn.commit()
        except Exception:
            conn.rollback()
            log.warning("Audit write failed for %s %s", action, rid, exc_info=True)

    # ----- OutcomeEvaluator + LEARN -----

    def _evaluate_due(self, conn, store: OutlookRepository, now: datetime, s: OutlookSettings, runs: list[dict] | None = None) -> int:
        done = 0
        for run in runs if runs is not None else store.runs(states=("PUBLISHED", "MONITORING", "EVALUATING"), limit=60)[::-1]:
            day = date.fromisoformat(run["analysis_date"])
            nday = cal.next_trading_day(day)
            nclose = cal.close_time(nday)
            if now < nclose + timedelta(minutes=s.close_grace_minutes):
                continue
            outlooks = [o for o in store.outlooks(run["id"]) if o["status"] == "PUBLISHED"]
            seen = store.evaluated_ids(run["id"])
            pending = [o for o in outlooks if o["outlook_id"] not in seen]
            if pending:
                store.update_run(run["id"], state="EVALUATING")
                h1 = candles_between(MarketRepository(conn), "H1", [o["symbol"] for o in pending], cal.close_time(day), nclose)
                for o in pending:
                    ev = evaluate(o, h1.get(o["symbol"], []), nclose, nday.isoformat())
                    if ev is None:
                        continue
                    store.add_evaluation(run, o, ev)
                    done += 1
                conn.commit()
                seen = store.evaluated_ids(run["id"])
            remaining = [o for o in outlooks if o["outlook_id"] not in seen]
            if not remaining or now > nclose + timedelta(days=4):
                store.update_run(run["id"], state="ARCHIVED", evaluated_at=now_iso(),
                                 log=_entry("EVALUATING", f"Outcomes evaluated for {len(outlooks) - len(remaining)}/{len(outlooks)} outlooks; archived"))
        return done

    # ----- IntradayOutlookMonitor -----

    def _monitor(self, conn, store: OutlookRepository, now: datetime, s: OutlookSettings) -> int:
        day = self.target_day(now, s)
        run = store.run(day.isoformat(), "LIVE")
        if not run or run["state"] not in ("PUBLISHED", "MONITORING"):
            return 0
        if run["monitored_at"] and run["monitored_at"] > (now - timedelta(seconds=s.monitor_seconds - 5)).isoformat():
            return 0
        outlooks = [o for o in store.outlooks(run["id"]) if o["status"] == "PUBLISHED"]
        if not outlooks:
            return 0
        anchor = cal.close_time(day)
        repo = MarketRepository(conn)
        syms = [o["symbol"] for o in outlooks]
        h1 = candles_between(repo, "H1", syms, anchor, now + timedelta(hours=1))
        m30 = candles_between(repo, "M30", syms, anchor, now + timedelta(hours=1))
        events = self._live_events(anchor)
        changed = 0
        for o in outlooks:
            ev = (events or {}).get(o["symbol"]) if events is not None else None
            res = monitor(o, h1.get(o["symbol"], []), m30.get(o["symbol"], []), ev, now)
            prev = store.latest_revision(o["outlook_id"])
            sig = (res["status"], sum(1 for st in res["steps"] if st["done"]), res["system_action"]["key"])
            prev_sig = None if prev is None else (prev["status"], sum(1 for st in prev.get("steps", []) if st["done"]), (prev.get("system_action") or {}).get("key"))
            if sig != prev_sig:
                store.add_revision(o, run["id"], res["status"], prev["status"] if prev else None, res["observed_at"], res["price"],
                                   {k: v for k, v in res.items() if k not in ("status", "observed_at", "price")})
                changed += 1
        store.update_run(run["id"], state="MONITORING", monitored_at=now_iso())
        return changed

    @staticmethod
    def _live_events(anchor: datetime) -> dict[str, list[dict]] | None:
        """H1 BOS/CHoCH events from the live scanner cycle (only when it analysed bars after the frozen close)."""
        engine = get_scanner_engine()
        if scanner_enabled() and not engine.running and os.getenv("VERCEL", "").strip() == "1":
            try:
                engine.tick_on_demand()
            except Exception:
                log.warning("Scanner on-demand tick failed during outlook monitoring", exc_info=True)
        st = engine.analysis_state()
        if not st["analysis"] or not st["cycle_at"] or st["cycle_at"] <= anchor:
            return None
        return {sym: ((a.get("bos") or {}).get("H1") or {}).get("events", []) for sym, a in st["analysis"].items() if "bos" in a}

    # ----- walk-forward replay (history for calibration and the Historical tab) -----

    def _replay(self, conn, store: OutlookRepository, now: datetime, s: OutlookSettings) -> list[str]:
        start = time.monotonic()
        live_day = self.target_day(now, s)
        days, d = [], live_day
        for _ in range(int(s.replay_days)):
            d = d - timedelta(days=1)
            while not cal.is_trading_day(d):
                d -= timedelta(days=1)
            days.append(d)
        have = store.dates_with_outlooks()
        out = []
        for day in sorted(days):
            if time.monotonic() - start > s.replay_budget_seconds:
                break
            if day.isoformat() in have or store.run(day.isoformat(), "REPLAY"):
                continue
            run = store.create_run(day.isoformat(), "REPLAY", cal.close_time(day).isoformat(), ENGINE_VERSION)
            store.update_run(run["id"], log=_entry("SCHEDULED", "Walk-forward replay: frozen bars as of that close, no later data"))
            run = self.execute(conn, store, store.run_by_id(run["id"]), now, s)  # type: ignore[arg-type]
            if run["state"] == "PUBLISHED":
                self._evaluate_due(conn, store, now, s, runs=[run])
            out.append(f"{day.isoformat()}:{run['state']}")
        return out

    # ----- manual operations -----

    def run_now(self, analysis_date: date | None = None, *, force: bool = False) -> dict:
        """Operator trigger: (re)attempt a LIVE run that has not published yet. Published outlooks are never regenerated."""
        now = utcnow()
        s = outlook_settings()
        with self._busy:
            with db() as conn:
                store = OutlookRepository(conn, active_scope(conn))
                if not store.acquire_lock(LOCK, self.owner, s.lock_seconds):
                    return {"skipped": "locked"}
                try:
                    day = analysis_date or self.target_day(now, s)
                    run = store.run(day.isoformat(), "LIVE") or store.create_run(day.isoformat(), "LIVE", cal.close_time(day).isoformat(), ENGINE_VERSION)
                    if run["state"] in DONE_STATES:
                        return {"run": run, "skipped": "already published (immutable)"}
                    if run["state"] == "MISSED" and not force:
                        return {"run": run, "skipped": "missed — the next close has passed"}
                    return {"run": self.execute(conn, store, run, now, s)}
                finally:
                    store.release_lock(LOCK, self.owner)


_service: OutlookService | None = None
_service_lock = threading.Lock()


def get_outlook_service() -> OutlookService:
    global _service
    with _service_lock:
        if _service is None:
            _service = OutlookService()
        return _service


# ----- read models for the API -----


def schedule_payload(now: datetime | None = None) -> dict:
    now = now or utcnow()
    s = outlook_settings()
    day = OutlookService.target_day(now, s)
    nxt = cal.next_trading_day(day)
    next_run = cal.close_time(nxt) + timedelta(minutes=s.close_grace_minutes)
    return {"now": now.isoformat(), "analysis_date": day.isoformat(), "close_at": cal.close_time(day).isoformat(),
            "next_close_at": cal.close_time(nxt).isoformat(), "next_run_at": next_run.isoformat(),
            "seconds_to_next_run": max(0, int((next_run - now).total_seconds())), "active_session": cal.active_session(now),
            "sessions": cal.session_windows(cal.close_time(day)), "timezone": "America/New_York 17:00 rollover"}


def run_summary(run: dict | None) -> dict | None:
    if not run:
        return None
    return {k: run[k] for k in ("id", "analysis_date", "origin", "state", "attempts", "snapshot_id", "close_at", "engine_version", "symbols_total",
                                 "symbols_published", "symbols_failed", "symbols_insufficient", "qualified", "started_at", "published_at",
                                 "monitored_at", "evaluated_at", "next_retry_at", "error")} | {"log": json.loads(run.get("log_json") or "[]")}


def performance_payload(store: OutlookRepository, days: int, symbol: str | None = None) -> dict:
    since = (utcnow() - timedelta(days=days)).date().isoformat()
    ev = store.evaluations(symbol=symbol, since=since)
    return {"window_days": days, "since": since, "symbol": symbol, "all": performance(ev), "qualified": performance(ev, qualified_only=True)}
