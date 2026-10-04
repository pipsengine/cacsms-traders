"""Background Strength Intelligence engine.

Polls the shared MT5 session for newly closed bars, ingests only the timeframes that changed,
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
from .csm_live import LiveCsmSource, bar_basis
from .csm_scoring import normalize_all_scores
from .csm_service import CurrencyStrengthMatrixService
from .ingestion_runner import MarketIngestionRunner
from .intelligence_cycle import write_relationships
from .mt5_gateway import create_market_data_gateway
from .mt5_platform_status import get_mt5_market_context
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
        self._ctx: dict = {"mt5_connected": False, "market_data_ready": False, "mt5_server": "MetaTrader 5"}
        self._state = "STARTING"
        self._error: str | None = None
        self._last_bar: dict[str, int] = {}
        self._bootstrapped = False
        self._bootstrap_retry_at = 0.0
        self._live: LiveCsmSource | None = None
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
            self._stop.wait(POLL_SECONDS)

    def _probe(self, gw, tf: str) -> int | None:
        try:
            return gw.latest_closed_open_time(PROBE_PAIR, tf)
        except Exception:
            return None

    def _sync_closed_bars(self, repo: MarketRepository, svc: CurrencyStrengthMatrixService) -> bool:
        gw = create_market_data_gateway()
        if not hasattr(gw, "latest_closed_open_time"):
            return False
        if not self._bootstrapped:
            if time.monotonic() < self._bootstrap_retry_at:
                return False
            with self._lock:
                self._state = "SYNCING"
            loaded = svc.calculate().pairs_loaded
            count = 40 if loaded >= len(FX_PAIRS_28) else 400
            try:
                MarketIngestionRunner(gw, repo, candle_count=count).sync_universe()
            except Exception:
                self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                raise
            self._last_bar = {tf: t for tf in PROBE_TIMEFRAMES if (t := self._probe(gw, tf)) is not None}
            self._bootstrapped = True
            return True

        changed = []
        for tf in PROBE_TIMEFRAMES:
            t = self._probe(gw, tf)
            if t is not None and t != self._last_bar.get(tf):
                self._last_bar[tf] = t
                changed.append(tf)
        if not changed:
            return False
        runner = MarketIngestionRunner(gw, repo, candle_count=INCREMENTAL_BARS)
        for tf in changed:
            runner.sync_timeframe_universe(tf, candle_count=INCREMENTAL_BARS)
        if "H1" in changed:
            runner.sync_timeframe_universe("H8", candle_count=INCREMENTAL_BARS)
        return True

    def _wanted_modes(self) -> tuple[str, ...]:
        cutoff = time.monotonic() - MODE_INTEREST_SECONDS
        with self._lock:
            extra = sorted(m for m, t in self._mode_interest.items() if t >= cutoff)
        return ("CLOSE_CLOSE", *extra)

    def _live_result(self, svc: CurrencyStrengthMatrixService, now: datetime) -> CsmMatrixResult | None:
        """EarnForex matrices from current MT5 rates; None when the live source is unavailable."""
        if self._live is None:
            gw = create_market_data_gateway()
            if not hasattr(gw, "current_closes"):
                return None
            self._live = LiveCsmSource(gw)
        try:
            inputs = self._live.inputs_by_mode(now, self._wanted_modes(), bars_difference=1)
        except Exception:
            log.exception("Live strength read failed")
            self._live = None
            return None
        results = {m: svc.calculate_from(data, as_of=now, bars_difference=1) for m, data in inputs.items()}
        with self._lock:
            self._mode_results = {m: r for m, r in results.items() if m != "CLOSE_CLOSE"}
        return results["CLOSE_CLOSE"]

    def _tick(self) -> None:
        with db() as conn:
            ctx = get_mt5_market_context(conn)
            repo = MarketRepository(conn)
            svc = CurrencyStrengthMatrixService(repo)
            connected = bool(ctx["mt5_connected"] and ctx["market_data_ready"])
            with self._lock:
                self._ctx = ctx

            changed = False
            result = None
            now = datetime.now(timezone.utc)
            if connected:
                changed = self._sync_closed_bars(repo, svc)
                result = self._live_result(svc, now)
            else:
                self._bootstrapped = False
                self._live = None

            now_mono = time.monotonic()
            from_live = result is not None
            if result is None and (
                changed or self._result is None or now_mono - self._last_calc_mono >= HEARTBEAT_RECALC_SECONDS
            ):
                result = svc.calculate(calculation_mode=CalculationMode.CLOSE_CLOSE)
            if result is not None:
                signature = tuple(
                    round(result.values[c].get(tf, 0.0), 4) for c in sorted(result.values) for tf in MATRIX_TIMEFRAMES
                )
                # The stored-candle fallback is a different basis from the live source; never mix it into history.
                persist_due = from_live and signature != self._last_persisted_sig and (
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
            self._ctx = ctx
            self._last_tick_ok = datetime.now(timezone.utc)
            self._state = "READY" if connected else "MT5_DISCONNECTED"
            self._error = None

    def _refresh_reference(self, conn, now: datetime, now_mono: float) -> None:
        ref = reference_scores(conn, now - timedelta(minutes=dynamics_lookback_minutes()))
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
        """Calculate once from stored candles when the background loop has not produced a result yet."""
        with db() as conn:
            ctx = get_mt5_market_context(conn)
            svc = CurrencyStrengthMatrixService(MarketRepository(conn))
            result = svc.calculate(calculation_mode=CalculationMode.CLOSE_CLOSE)
            histories = svc.score_histories()
        with self._lock:
            if self._result is None or not self.running:
                self._result = result
                self._histories = histories
                self._ctx = ctx
                self._last_tick_ok = datetime.now(timezone.utc)
                if not self.running:
                    self._state = "READY" if ctx["mt5_connected"] else "MT5_DISCONNECTED"

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
            return None
        now = datetime.now(timezone.utc)
        connected = bool(ctx.get("mt5_connected") and ctx.get("market_data_ready"))
        stale_reason = None
        if not connected:
            stale_reason = "MT5_DISCONNECTED"
        elif state != "SYNCING" and (
            last_tick is None or (now - last_tick).total_seconds() > STALE_AFTER_SECONDS
        ):
            stale_reason = "ENGINE_STALLED"
        live = bool(
            connected and stale_reason is None and result.pairs_loaded >= len(FX_PAIRS_28) and result.historical_ok
        )
        return {
            "as_of": result.as_of.isoformat(),
            "last_calculated_at": result.as_of.isoformat(),
            "mt5_connected": connected,
            "mt5_server": str(ctx.get("mt5_server") or "MetaTrader 5"),
            "live_data": live,
            "historical_ok": result.historical_ok,
            "missing_history": [{"symbol": m.symbol, "timeframe": m.timeframe} for m in result.missing[:50]],
            "pairs_loaded": result.pairs_loaded,
            "pairs_total": len(FX_PAIRS_28),
            "missing_pairs": result.missing_pairs,
            "engine_state": state,
            "bar_basis": bar_basis(),
            "closed_bar_only": bar_basis() == "closed",
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
            return None
        svc = CurrencyStrengthMatrixService(None)  # type: ignore[arg-type]
        out = svc.to_api_payload(
            result,
            sort_by=sort_by.upper(),
            mt5_connected=meta["mt5_connected"],
            mt5_server=meta["mt5_server"],
            live_data=meta["live_data"],
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
            out["meta"]["mode_pending"] = True
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
