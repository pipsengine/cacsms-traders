"""Background Strength Intelligence engine.

Polls the active provider for newly closed bars, ingests only the timeframes that changed,
recalculates the currency strength matrix and persists throttled snapshots. API requests read
the cached result — they never trigger ingestion or a 28-pair recalculation themselves.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from ..core.database import db
from .constants import COMPUTE_TIMEFRAMES, FX_PAIRS_28, MATRIX_TIMEFRAMES
from .csm_engine import CalculationMode, CsmMatrixResult
from .csm_scoring import normalize_all_scores
from .csm_service import CurrencyStrengthMatrixService
from .ingestion_runner import MarketIngestionRunner
from .intelligence_cycle import write_relationships
from .market_data import create_market_data_gateway, market_context
from .pair_relationships import Scores, pair_relationships
from .repository import MarketRepository
from .strength_intel_config import dynamics_lookback_minutes
from .strength_intel_store import active_scope, reference_scores, save_pair_snapshot

log = logging.getLogger(__name__)

PROBE_PAIR = "EURUSD"
PROBE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "D1", "W1", "MN")
INCREMENTAL_BARS = 5


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


POLL_SECONDS = _env_float("STRENGTH_ENGINE_POLL_SECONDS", 1.0)
SNAPSHOT_INTERVAL_SECONDS = _env_float("STRENGTH_SNAPSHOT_INTERVAL_SECONDS", 300.0)
HEARTBEAT_RECALC_SECONDS = 60.0
STALE_AFTER_SECONDS = 120.0
BOOTSTRAP_RETRY_SECONDS = 60.0
MODE_INTEREST_SECONDS = 30.0
REFERENCE_REFRESH_SECONDS = 60.0


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class StrengthEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._result: CsmMatrixResult | None = None
        self._histories: dict[str, list[tuple[str, float]]] = {}
        self._ctx: dict = {"market_data_ready": False}
        self._provider_key = None
        self._state = "STARTING"
        self._error: str | None = None
        self._last_bar: dict[str, int] = {}
        self._bootstrapped = False
        self._bootstrap_retry_at = 0.0
        self._mode_interest: dict[str, float] = {}
        self._mode_results: dict[str, CsmMatrixResult] = {}
        self._last_sig: tuple | None = None
        self._last_persisted_sig: tuple | None = None
        self._last_calc_mono = 0.0
        self._last_persist_mono = 0.0
        self._last_tick_ok: datetime | None = None
        self._last_persisted_at: datetime | None = None
        self._last_bar_change_at: datetime | None = None
        self._scores: Scores = {}
        self._pairs: list[dict] = []
        self._reference: tuple[datetime, Scores] | None = None
        self._reference_mono = 0.0
        self._scores_sig: tuple | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="strength-engine", daemon=True)
        self._thread.start()
        log.info("Strength engine started (poll=%ss, snapshot=%ss)", POLL_SECONDS, SNAPSHOT_INTERVAL_SECONDS)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            with db() as conn:
                n = CurrencyStrengthMatrixService(MarketRepository(conn)).backfill_scores()
            if n:
                log.info("Strength engine backfilled %s snapshot scores", n)
        except Exception:
            log.exception("Strength score backfill failed")
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                log.exception("Strength engine tick failed")
                with self._lock:
                    self._state = "ERROR"
                    self._error = str(exc)
                    self._ctx["provider_status"] = "ERROR"
                    self._ctx["error_code"] = "market_data_sync_failed"
            self._stop.wait(POLL_SECONDS)

    def _probe(self, gw, tf: str) -> int | None:
        try:
            return gw.latest_closed_open_time(PROBE_PAIR, tf)
        except Exception:
            return None

    def _sync_closed_bars(self, repo: MarketRepository, svc: CurrencyStrengthMatrixService) -> bool:
        gw = create_market_data_gateway(repo.conn, context=self._ctx)
        repo.provider = gw.provider_id
        repo.snapshot_id = gw.snapshot_id
        repo.account_id = (gw.get_account_context() or {}).get("account_id", "")
        self._ctx["snapshot_id"] = gw.snapshot_id
        if not hasattr(gw, "latest_closed_open_time"):
            return False
        if not self._bootstrapped:
            if time.monotonic() < self._bootstrap_retry_at:
                return False
            with self._lock:
                self._state = "SYNCING"
            if hasattr(gw, "get_symbols"):
                symbols = gw.get_symbols()
                resolved = {r.get("canonical_symbol") for r in symbols}
                missing = [p for p in FX_PAIRS_28 if p not in resolved]
                with self._lock:
                    self._ctx.update(symbols_resolved=28-len(missing), missing_pairs=missing, failed_symbol_mappings=missing, provider_status="DEGRADED" if missing else "CONNECTING")
                if missing:
                    self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                    return False
            count = 400
            try:
                summary = MarketIngestionRunner(gw, repo, candle_count=count).sync_universe()
                failures = [{"symbol": r["symbol"], "timeframe": r["timeframe"], "error_code": r.get("error") or "no_closed_bars"} for r in summary["results"] if r.get("error") or not r.get("accepted")]
                with self._lock:
                    self._ctx.update(provider_status="DEGRADED" if failures else "CONNECTED", failed_candle_requests=failures, closed_bar_status="INCOMPLETE" if failures else "SYNCHRONIZED", last_successful_sync=None if failures else _iso(datetime.now(timezone.utc)))
                if failures:
                    self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                    return False
            except Exception:
                self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                raise
            self._last_bar = {tf: t for tf in PROBE_TIMEFRAMES if (t := self._probe(gw, tf)) is not None}
            self._bootstrapped = len(self._last_bar) == len(PROBE_TIMEFRAMES)
            return self._bootstrapped

        changed = []
        for tf in PROBE_TIMEFRAMES:
            t = self._probe(gw, tf)
            if t is None:
                self._bootstrapped = False
                self._ctx.update(closed_bar_status='INCOMPLETE',error_code='stale_or_missing_candles')
                return False
            if t != self._last_bar.get(tf):
                self._last_bar[tf] = t
                changed.append(tf)
        if not changed:
            return False
        runner = MarketIngestionRunner(gw, repo, candle_count=INCREMENTAL_BARS)
        for tf in changed:
            summary = runner.sync_timeframe_universe(tf, candle_count=INCREMENTAL_BARS)
            failures = [r for r in summary["results"] if r.get("error") or not r.get("accepted")]
            if failures:
                self._bootstrapped = False
                self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                with self._lock:
                    self._ctx.update(provider_status="DEGRADED", closed_bar_status="INCOMPLETE",
                                     failed_candle_requests=failures)
                return False
        if "H1" in changed:
            runner.sync_timeframe_universe("H8", candle_count=INCREMENTAL_BARS)
        return True

    def _wanted_modes(self) -> tuple[str, ...]:
        cutoff = time.monotonic() - MODE_INTEREST_SECONDS
        with self._lock:
            extra = sorted(m for m, t in self._mode_interest.items() if t >= cutoff)
        return ("CLOSE_CLOSE", *extra)

    def _tick(self) -> None:
        with db() as conn:
            from .provider_manager import ProviderManager
            ProviderManager(conn).refresh_health()
            ctx = market_context(conn)
            for provider, status in ctx.get('providers', {}).items():
                ProviderManager(conn).record_health(provider, status)
            from .market_data import configuration
            cfg = configuration(conn)
            key = (ctx.get("active_provider"), cfg["tenant_id"], ctx.get("providers", {}).get(ctx.get("active_provider"), {}).get("account_id", cfg["account_id"]))
            if key != self._provider_key:
                self._ctx = {}
                self._provider_key = key
                self._bootstrapped = False
                self._bootstrap_retry_at = 0.0
                self._last_bar = {}
                with self._lock:
                    self._result = None
                    self._scores = {}
                    self._pairs = []
                    self._reference = None
                    self._histories = {}
                    self._last_persisted_sig = None
                    self._last_persist_mono = 0.0
                    self._last_sig = None
                    self._scores_sig = None
                    self._mode_results = {}
                    self._last_persisted_at = None
            repo = MarketRepository(conn, provider=ctx.get("active_provider") or "__unavailable__")
            svc = CurrencyStrengthMatrixService(repo)
            connected = bool(ctx["market_data_ready"])
            with self._lock:
                for field in ("provider_status", "symbols_resolved", "missing_pairs", "failed_symbol_mappings", "failed_candle_requests", "last_successful_sync", "closed_bar_status"):
                    if key == self._provider_key and field in self._ctx:
                        ctx[field] = self._ctx[field]
                self._ctx = ctx

            if not connected:
                if ctx.get("providers"):
                    ProviderManager(conn).finalize_snapshot()
                with self._lock:
                    self._state = ctx["provider_status"]
                    self._result = None
                    self._bootstrapped = False
                return

            changed = False
            result = None
            now = datetime.now(timezone.utc)
            if connected:
                changed = self._sync_closed_bars(repo, svc)
                result = None  # Calculate from synchronized closed bars only.
            else:
                self._bootstrapped = False

            if not self._bootstrapped:
                with self._lock:
                    self._state = "INCOMPLETE_BASKET"
                    self._result = None
                return
            now_mono = time.monotonic()
            if result is None and (
                changed or self._result is None or now_mono - self._last_calc_mono >= HEARTBEAT_RECALC_SECONDS
            ):
                result = svc.calculate(calculation_mode=CalculationMode.CLOSE_CLOSE)
            if result is not None:
                signature = tuple(
                    round(result.values[c].get(tf, 0.0), 4) for c in sorted(result.values) for tf in MATRIX_TIMEFRAMES
                )
                # Persist only provider-synchronized closed-bar results.
                persist_due = connected and signature != self._last_persisted_sig and (
                    self._last_persist_mono == 0.0
                    or now_mono - self._last_persist_mono >= SNAPSHOT_INTERVAL_SECONDS
                )
                if persist_due or now_mono - self._reference_mono >= REFERENCE_REFRESH_SECONDS:
                    self._refresh_reference(conn, now, now_mono)
                self._update_intelligence(result, signature)
                if persist_due:
                    svc.persist(result)
                    write_relationships(repo, result)
                    with self._lock:
                        pairs = self._pairs
                    save_pair_snapshot(conn, active_scope(conn), result.as_of, pairs)
                    self._last_persist_mono = now_mono
                    self._last_persisted_sig = signature
                    self._last_persisted_at = now
                histories = svc.score_histories() if persist_due or not self._histories else self._histories
                with self._lock:
                    if self._result is not None and signature != self._last_sig:
                        self._last_bar_change_at = now
                    self._last_sig = signature
                    self._result = result
                    self._histories = histories
                self._last_calc_mono = now_mono

        with self._lock:
            ctx.update(self._ctx)
            self._ctx = ctx
            self._last_tick_ok = datetime.now(timezone.utc)
            self._state = "READY" if connected and self._result and self._result.pairs_loaded == 28 and self._result.historical_ok else "INCOMPLETE_BASKET"
            self._error = None

    def _refresh_reference(self, conn, now: datetime, now_mono: float) -> None:
        ref = reference_scores(conn, now - timedelta(minutes=dynamics_lookback_minutes()), snapshot_id=self._ctx.get("snapshot_id"))
        with self._lock:
            self._reference = ref
            self._reference_mono = now_mono
            self._scores_sig = None

    def _update_intelligence(self, result: CsmMatrixResult, signature: tuple) -> None:
        """Scores + 28-pair relationships, recomputed only when values or the reference change."""
        with self._lock:
            if signature == self._scores_sig:
                return
            ref = self._reference
        scores = normalize_all_scores(result.values, COMPUTE_TIMEFRAMES, result.quality)
        pairs = pair_relationships(scores, ref[1] if ref else None)
        with self._lock:
            self._scores = scores
            self._pairs = pairs
            self._scores_sig = signature

    def intelligence(self) -> dict | None:
        """Current scores, pair relationships and lookback reference shared by all Strength Intelligence tabs."""
        with self._lock:
            result = self._result
            if result is None:
                return None
            if not self._scores or self._scores_sig is None:
                self._scores = normalize_all_scores(result.values, COMPUTE_TIMEFRAMES, result.quality)
                self._pairs = pair_relationships(self._scores, self._reference[1] if self._reference else None)
                self._scores_sig = ("on-demand",)
            ref = self._reference
            return {
                "as_of": result.as_of,
                "scores": self._scores,
                "pairs": self._pairs,
                "reference": ref[1] if ref else None,
                "reference_as_of": ref[0] if ref else None,
                "last_persisted_at": self._last_persisted_at,
            }

    def ensure_reference(self) -> None:
        if self._reference is None and time.monotonic() - self._reference_mono >= REFERENCE_REFRESH_SECONDS:
            with db() as conn:
                self._refresh_reference(conn, datetime.now(timezone.utc), time.monotonic())

    def seed_from_db(self) -> None:
        """Refresh passive diagnostics and invalidate results when the selected scope changes."""
        with db() as conn:
            ctx = market_context(conn)
            from .provenance import active_snapshot
            scope = active_snapshot(conn)
        with self._lock:
            same_scope = self._ctx.get('active_provider') == ctx.get('active_provider') and self._ctx.get('market_data_scope') == ctx.get('market_data_scope') and self._ctx.get('snapshot_id') == (scope['id'] if scope else None)
            if not same_scope:
                self._result = None
                self._scores = {}
                self._pairs = []
                self._reference = None
                self._histories = {}
                self._bootstrapped = False
            else:
                for field in ('snapshot_id','symbols_resolved','missing_pairs','failed_symbol_mappings','failed_candle_requests','last_successful_sync','closed_bar_status'):
                    if field in self._ctx:
                        ctx[field] = self._ctx[field]
            self._ctx = ctx
            if not ctx['market_data_ready']:
                self._result = None
                self._state = ctx['provider_status']
            elif not self.running:
                self._state = 'WORKER_UNAVAILABLE'
            elif not same_scope:
                self._state = 'SYNCING'

    def engine_meta(self) -> dict | None:
        """Connection / freshness / basket state shared by every Strength Intelligence payload."""
        with self._lock:
            result = self._result
            ctx = dict(self._ctx)
            state = self._state
            error = self._error
            last_tick = self._last_tick_ok
            last_persisted = self._last_persisted_at
            last_change = self._last_bar_change_at
        if result is None:
            return {**ctx, "provider_connected": False, "strength_engine_status": state, "engine_state": state, "engine_error": error, "last_calculated_at": None, "as_of": None, "live_data": False, "stale": True, "historical_ok": False, "missing_history": [], "pairs_loaded": 0, "pairs_total": 28, "closed_bar_only": True, "calculation_mode": "CLOSE_CLOSE"}
        now = datetime.now(timezone.utc)
        connected = bool(ctx.get("market_data_ready"))
        stale_reason = None
        if not connected:
            stale_reason = "PROVIDER_DISCONNECTED"
        elif state != "SYNCING" and (
            last_tick is None or (now - last_tick).total_seconds() > STALE_AFTER_SECONDS
        ):
            stale_reason = "ENGINE_STALLED"
        live = bool(
            connected and state == "READY" and stale_reason is None
            and result.pairs_loaded >= len(FX_PAIRS_28) and result.historical_ok
        )
        return {
            "as_of": result.as_of.isoformat(),
            "last_calculated_at": result.as_of.isoformat(),
            **ctx,
            "provider_connected": connected,
            "data_source": ctx.get("active_provider"),
            "last_calculation": result.as_of.isoformat(),
            "strength_engine_status": state,
            "closed_bar_status": "SYNCHRONIZED" if result.historical_ok else "INCOMPLETE",
            "live_data": live,
            "historical_ok": result.historical_ok,
            "missing_history": [{"symbol": m.symbol, "timeframe": m.timeframe} for m in result.missing[:50]],
            "pairs_loaded": result.pairs_loaded,
            "pairs_total": len(FX_PAIRS_28),
            "missing_pairs": result.missing_pairs,
            "symbols_resolved": ctx.get("symbols_resolved", 0),
            "engine_state": state,
            "bar_basis": "closed",
            "closed_bar_only": True,
            "engine_error": error,
            "stale": stale_reason is not None,
            "stale_reason": stale_reason,
            "live_refresh_at": _iso(last_tick),
            "last_persisted_at": _iso(last_persisted),
            "last_bar_change_at": _iso(last_change),
            "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
        }

    def payload(self, sort_by: str = "AVG", mode: CalculationMode = CalculationMode.CLOSE_CLOSE) -> dict | None:
        with self._lock:
            result = self._result
            histories = self._histories
        meta = self.engine_meta()
        if result is None or meta is None:
            return {"meta": meta, "matrix": [], "avg_ranking": [], "currency_summary": []}
        svc = CurrencyStrengthMatrixService(None)  # type: ignore[arg-type]
        out = svc.to_api_payload(
            result,
            sort_by=sort_by.upper(),

            live_data=meta["live_data"],
            active_provider=meta.get("active_provider", "none"),
            provider_connected=meta.get("provider_connected", False),
            histories=histories,
        )
        out["meta"].update({k: v for k, v in meta.items() if k not in ("as_of", "last_calculated_at")})
        if mode != CalculationMode.CLOSE_CLOSE:
            self._apply_mode(out, svc, mode, sort_by)
        return out

    def _apply_mode(self, out: dict, svc: CurrencyStrengthMatrixService, mode: CalculationMode, sort_by: str) -> None:
        """Swap matrix + ranking for the requested EarnForex mode; cards/history stay close-to-close."""
        with self._lock:
            self._mode_interest[mode.value] = time.monotonic()
            mode_result = self._mode_results.get(mode.value)
        out["meta"]["calculation_mode"] = mode.value
        if mode_result is None:
            out["matrix"], out["avg_ranking"] = [], []
            out["meta"]["mode_pending"] = False
            out["meta"]["engine_state"] = "UNSUPPORTED_CALCULATION_MODE"
            out["meta"]["engine_error"] = "This calculation mode is unavailable for synchronized closed bars"
            return
        part = svc.to_api_payload(mode_result, calculation_mode=mode, sort_by=sort_by.upper())
        out["matrix"], out["avg_ranking"] = part["matrix"], part["avg_ranking"]
        out["meta"]["currency_order"] = part["meta"]["currency_order"]


_engine: StrengthEngine | None = None
_engine_lock = threading.Lock()


def get_strength_engine() -> StrengthEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = StrengthEngine()
        return _engine
