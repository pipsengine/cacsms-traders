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
from .constants import CANDLE_TIMEFRAMES, COMPUTE_TIMEFRAMES, FX_PAIRS_28, MATRIX_TIMEFRAMES, TIMEFRAME_SECONDS
from .csm_engine import (
    CalculationMode,
    CsmMatrixResult,
    apply_live_endpoints,
    compute_matrix,
    overlay_forming_closes,
    stamp_forming_bids,
)
from .csm_scoring import normalize_all_scores
from .csm_service import CurrencyStrengthMatrixService, collect_forming_bids, collect_live_endpoints
from .ingestion import broker_offset
from .ingestion_runner import MarketIngestionRunner
from .intelligence_cycle import write_relationships
from .market_data import configuration, create_market_data_gateway, market_context
from .pair_relationships import Scores, pair_relationships
from .provenance import scoped_query, values
from .repository import MarketRepository
from .store_sync import probe_open_times, store_failures
from .strength_intel_config import dynamics_lookback_minutes
from .strength_intel_store import active_scope, reference_scores, save_pair_snapshot

log = logging.getLogger(__name__)

PROBE_PAIR = "EURUSD"
PROBE_TIMEFRAMES = ("M1", "M5", "M15", "H1", "D1", "W1", "MN")
INCREMENTAL_BARS = 5
# Quality flags from ingestion are soft — stale/missing on one TF must not block the whole basket forever.
_HARD_SYNC_ERRORS = frozenset(
    {"invalid_candles", "no_closed_bars", "mt5_history_unavailable", "Symbol not available in MT5"}
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


POLL_SECONDS = _env_float("STRENGTH_ENGINE_POLL_SECONDS", 1.0)
SNAPSHOT_INTERVAL_SECONDS = _env_float("STRENGTH_SNAPSHOT_INTERVAL_SECONDS", 300.0)
HEARTBEAT_RECALC_SECONDS = 60.0
# Previous-bar closes (iClose shift 1) are stable until a bar closes. The bid is iClose shift 0 and
# is read on this cadence so the matrix follows the MT5 terminal tick.
QUOTE_SECONDS = _env_float("STRENGTH_QUOTE_SECONDS", 0.1)
STALE_AFTER_SECONDS = 120.0
BOOTSTRAP_RETRY_SECONDS = 60.0
MODE_INTEREST_SECONDS = 30.0
REFERENCE_REFRESH_SECONDS = 60.0
ON_DEMAND_INTERVAL_SECONDS = _env_float("STRENGTH_ON_DEMAND_SECONDS", 15.0)
COLD_WAIT_SECONDS = _env_float("STRENGTH_COLD_WAIT_SECONDS", 60.0)


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
        self._lag_retry_at: dict[str, float] = {}
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
        self._on_demand = False
        self._demand_lock = threading.Lock()
        self._last_demand_mono = 0.0
        self._last_profile: dict[str, float] = {}
        self._forming_bids: dict[str, float] = {}
        self._live_endpoints: dict[str, dict[str, list[float]]] = {}
        self._bar_anchors: dict[str, dict[str, list[float]]] = {}
        self._base_pair_data: dict | None = None
        self._last_bids: dict[str, float] = {}
        self._quote_adapter = None
        self._anchor_m1: int | None = None
        self._bids_changed = False

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
            self._safe_tick()
            idle_until = time.monotonic() + POLL_SECONDS
            while not self._stop.is_set() and time.monotonic() < idle_until:
                try:
                    self._apply_quote_tick()
                except Exception:
                    log.exception("Strength quote tick failed")
                    break
                if self._stop.wait(QUOTE_SECONDS):
                    break

    def _safe_tick(self) -> None:
        try:
            self._tick()
        except Exception as exc:
            log.exception("Strength engine tick failed")
            with self._lock:
                self._state = "ERROR"
                self._error = str(exc)
                self._ctx["provider_status"] = "ERROR"
                self._ctx["error_code"] = "market_data_sync_failed"

    def allow_on_demand(self) -> None:
        """Reads will advance this engine, so a missing background worker is not a fault."""
        self._on_demand = True

    def tick_on_demand(self) -> None:
        """Advance the engine inside an API request where no background worker can live (serverless).

        Throttled. Concurrent requests return the cached state while one request ticks; with nothing
        cached yet (cold instance) they wait for that tick instead of answering with an empty matrix.
        """
        if self.running:
            return
        self._on_demand = True
        if time.monotonic() - self._last_demand_mono < ON_DEMAND_INTERVAL_SECONDS:
            return
        with self._lock:
            cold = self._result is None
        if not self._demand_lock.acquire(blocking=cold, timeout=COLD_WAIT_SECONDS if cold else -1):
            return
        try:
            if time.monotonic() - self._last_demand_mono < ON_DEMAND_INTERVAL_SECONDS:
                return
            self._safe_tick()
        finally:
            self._last_demand_mono = time.monotonic()
            self._demand_lock.release()

    def _probe(self, gw, tf: str) -> int | None:
        try:
            return gw.latest_closed_open_time(PROBE_PAIR, tf)
        except Exception:
            return None

    @staticmethod
    def _sync_result_blocking(result: dict) -> bool:
        err = (result.get("error") or "").strip()
        if err in _HARD_SYNC_ERRORS or "unavailable" in err.lower():
            return True
        if result.get("accepted", 0) == 0 and not err:
            return True
        return False

    def _refresh_repository_basket_meta(self, repo: MarketRepository) -> dict:
        from .basket_status import repository_basket_status

        basket = repository_basket_status(
            repo.conn,
            provider=repo.provider,
            snapshot_id=repo.snapshot_id,
            account_id=repo.account_id,
        )
        with self._lock:
            self._ctx.update(
                pairs_loaded=basket["pairs_loaded"],
                missing_pairs=basket["missing_pairs"],
                pairs_total=basket["pairs_total"],
                repository_pairs_loaded=basket["pairs_loaded"],
            )
        return basket

    def _load_bar_anchors(self, gw) -> None:
        """iClose(shift 1) for each matrix timeframe. Shift 0 is applied later from the bid."""
        try:
            endpoints = collect_live_endpoints(gw)
        except Exception:
            log.exception("Forming bar refresh failed")
            endpoints = {}
        anchors: dict[str, dict[str, list[float]]] = {}
        for tf, pairs in endpoints.items():
            framed = {pair: [float(c) for c in series[:-1]] for pair, series in pairs.items() if len(series) >= 2}
            if framed:
                anchors[tf] = framed
        if not anchors:
            return
        self._bar_anchors = anchors
        adapter = getattr(gw, "adapter", gw)
        probe = getattr(adapter, "latest_closed_open_time", None)
        if callable(probe):
            try:
                self._anchor_m1 = probe(PROBE_PAIR, "M1")
            except Exception:
                self._anchor_m1 = None
        self._quote_adapter = adapter if callable(getattr(adapter, "forming_bids", None)) else None

    def _pull_bids(self, gw, *, restamp: bool = False) -> bool:
        """Current bid per pair. Returns True when any bid changed."""
        adapter = getattr(gw, "adapter", gw)
        bids: dict[str, float] = {}
        fetch = getattr(adapter, "forming_bids", None)
        if callable(fetch):
            try:
                raw = fetch(FX_PAIRS_28)
            except Exception:
                log.exception("Forming bid refresh failed")
                raw = {}
            bids = {p: float(raw[p]) for p in FX_PAIRS_28 if raw.get(p) and float(raw[p]) > 0}
            self._quote_adapter = adapter
        if not bids:
            try:
                bids = collect_forming_bids(gw)
            except Exception:
                log.exception("Forming bid refresh failed")
                return False
        if not bids:
            self._bids_changed = False
            return False
        changed = bids != self._last_bids
        if not changed and not restamp:
            self._bids_changed = False
            return False
        self._last_bids = bids
        self._forming_bids = bids
        self._live_endpoints = stamp_forming_bids(self._bar_anchors, bids) if self._bar_anchors else {}
        self._bids_changed = True
        return True

    def _refresh_forming_bids(self, gw, *, force_anchors: bool = False) -> bool:
        reload_anchors = force_anchors or not self._bar_anchors
        if reload_anchors:
            self._load_bar_anchors(gw)
        return self._pull_bids(gw, restamp=reload_anchors)

    def _compose_pair_data(self, base: dict) -> dict:
        bids = self._forming_bids
        endpoints = self._live_endpoints
        if endpoints:
            data = apply_live_endpoints(base, endpoints)
            if bids:
                synthetic = overlay_forming_closes({tf: data[tf] for tf in ("YTD", "Q") if tf in data}, bids)
                data.update(synthetic)
            return data
        if bids:
            return overlay_forming_closes(base, bids)
        return {tf: {pair: list(closes) for pair, closes in pairs.items()} for tf, pairs in base.items()}

    def _recompute_from_cache(self, as_of: datetime) -> CsmMatrixResult | None:
        base = self._base_pair_data
        if not base:
            return None
        data = self._compose_pair_data(base)
        result = compute_matrix(COMPUTE_TIMEFRAMES, data, bars_difference=1, as_of=as_of)
        result.missing_pairs = CurrencyStrengthMatrixService.missing_pairs(data)
        result.pairs_loaded = len(FX_PAIRS_28) - len(result.missing_pairs)
        result.forming_close = bool(self._forming_bids or self._live_endpoints)
        return result

    def _publish_quote(self, result: CsmMatrixResult) -> None:
        signature = tuple(
            round(result.values[c].get(tf, 0.0), 4) for c in sorted(result.values) for tf in MATRIX_TIMEFRAMES
        )
        self._update_intelligence(result, signature)
        with self._lock:
            if self._result is not None and signature != self._last_sig:
                self._last_bar_change_at = result.as_of
            self._last_sig = signature
            self._result = result
            self._last_calc_mono = time.monotonic()
            self._last_tick_ok = result.as_of

    def _apply_quote_tick(self) -> None:
        """Follow the terminal: new bid recompute, and new M1 bar refreshes iClose(shift 1)."""
        adapter = self._quote_adapter
        if adapter is None or self._base_pair_data is None or not self._bar_anchors:
            return
        probe = getattr(adapter, "latest_closed_open_time", None)
        if callable(probe):
            try:
                opened = probe(PROBE_PAIR, "M1")
            except Exception:
                opened = None
            if opened and opened != self._anchor_m1:
                self._anchor_m1 = opened
                try:
                    endpoints = adapter.forming_endpoints(FX_PAIRS_28, ("M1", "M5", "M15", "H1", "D1", "W", "MN"), 1)
                except Exception:
                    log.exception("Forming bar refresh failed")
                    endpoints = {}
                anchors = {
                    tf: {pair: [float(c) for c in series[:-1]] for pair, series in pairs.items() if len(series) >= 2}
                    for tf, pairs in endpoints.items()
                }
                anchors = {tf: pairs for tf, pairs in anchors.items() if pairs}
                if anchors:
                    self._bar_anchors = anchors
                    self._last_bids = {}
        if not self._pull_bids(adapter):
            return
        result = self._recompute_from_cache(datetime.now(timezone.utc))
        if result is not None:
            self._publish_quote(result)

    def _sync_closed_bars(self, repo: MarketRepository, svc: CurrencyStrengthMatrixService) -> bool:
        started = time.monotonic()
        gw = create_market_data_gateway(repo.conn, context=self._ctx, verify_scope=False)
        repo.provider = gw.provider_id
        repo.snapshot_id = gw.snapshot_id
        repo.account_id = (gw.get_account_context() or {}).get("account_id", "")
        # bind_snapshot holds a write lock. Release it before any MT5 call so the scanner can ingest.
        repo.conn.commit()
        self._refresh_forming_bids(gw)
        self._last_profile["gateway"] = round(time.monotonic() - started, 3)
        self._ctx["snapshot_id"] = gw.snapshot_id
        if getattr(getattr(gw, "adapter", None), "candles_persisted", False) is True:
            return self._sync_from_store(gw, repo)
        if not hasattr(gw, "latest_closed_open_time"):
            return False
        if not self._bootstrapped:
            if time.monotonic() < self._bootstrap_retry_at:
                return False
            basket = self._refresh_repository_basket_meta(repo)
            if basket.get("pairs_loaded", 0) >= 20:
                probes = {tf: t for tf in PROBE_TIMEFRAMES if (t := self._probe(gw, tf)) is not None}
                ok, _changed = self._sync_lagging(gw, repo, probes)
                if not ok:
                    return False
                self._last_bar = probes
                self._bootstrapped = True
                with self._lock:
                    self._state = "CALCULATING"
                return True
            with self._lock:
                self._state = "DISCOVERING_SYMBOLS"
            if hasattr(gw, "get_symbols"):
                symbols = gw.get_symbols()
                if not symbols:
                    scope_tid = (self._ctx.get("market_data_scope") or {}).get("tenant_id") or configuration(repo.conn).get("tenant_id")
                    if scope_tid:
                        from ..domain.mt5_connection import ensure_gateway_session

                        if ensure_gateway_session(repo.conn, scope_tid).get("restored"):
                            symbols = gw.get_symbols()
                resolved = {r.get("canonical_symbol") for r in symbols}
                missing = [p for p in FX_PAIRS_28 if p not in resolved]
                sync_status = "CONNECTING" if missing and not self._bootstrapped else ("DEGRADED" if missing else "CONNECTING")
                with self._lock:
                    self._ctx.update(
                        symbols_resolved=28 - len(missing),
                        missing_pairs=missing,
                        failed_symbol_mappings=missing,
                        provider_status=sync_status,
                    )
                if len(missing) == len(FX_PAIRS_28):
                    self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                    return False
            count = 400
            with self._lock:
                self._state = "BACKFILLING"
            try:
                summary = MarketIngestionRunner(gw, repo, candle_count=count).sync_universe()
                blocking = [r for r in summary["results"] if self._sync_result_blocking(r)]
                soft = [
                    {"symbol": r["symbol"], "timeframe": r["timeframe"], "error_code": r.get("error") or "no_new_bars"}
                    for r in summary["results"]
                    if r.get("error") and not self._sync_result_blocking(r)
                ]
                with self._lock:
                    self._ctx.update(
                        provider_status="DEGRADED" if blocking else "CONNECTED",
                        failed_candle_requests=blocking or soft[:40],
                        closed_bar_status="INCOMPLETE" if blocking else "SYNCHRONIZED",
                        last_successful_sync=_iso(datetime.now(timezone.utc)),
                        sync_pairs_attempted=summary.get("pairs"),
                        sync_errors=summary.get("errors"),
                    )
                if len(blocking) > len(summary["results"]) * 0.85:
                    self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                    return False
            except Exception:
                self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                raise
            with self._lock:
                self._state = "VALIDATING"
            self._last_bar = {tf: t for tf in PROBE_TIMEFRAMES if (t := self._probe(gw, tf)) is not None}
            basket = self._refresh_repository_basket_meta(repo)
            probes_ok = len(self._last_bar) >= max(4, len(PROBE_TIMEFRAMES) - 2)
            self._bootstrapped = probes_ok or basket["pairs_loaded"] >= 20
            return self._bootstrapped or basket["pairs_loaded"] > 0

        probes = {}
        for tf in PROBE_TIMEFRAMES:
            t = self._probe(gw, tf)
            if t is None:
                self._bootstrapped = False
                self._ctx.update(closed_bar_status='INCOMPLETE',error_code='stale_or_missing_candles')
                return False
            probes[tf] = t
        ok, changed = self._sync_lagging(gw, repo, probes)
        if not ok or not changed:
            return False
        self._refresh_forming_bids(gw, force_anchors=True)
        return True

    def _catch_up_count(self, stored: datetime | None, probe_open: int, tf: str) -> int:
        """Bars to request so an incremental read overlaps the last stored bar instead of jumping the gap."""
        seconds = TIMEFRAME_SECONDS.get({"W1": "W", "MN1": "MN"}.get(tf, tf), 3600)
        if stored is None:
            return 400
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        probe_dt = datetime.fromtimestamp(int(probe_open), tz=timezone.utc)
        if stored >= probe_dt:
            return 0
        # A session outage can be longer than the old 400-bar window, which then never overlaps the stored bar.
        return min(960, max(INCREMENTAL_BARS, int((probe_dt - stored).total_seconds() / max(seconds, 1)) + 3))

    def _sync_lagging(self, gw, repo: MarketRepository, probes: dict[str, int]) -> tuple[bool, bool]:
        """Fill closed bars that the store skipped. Hourly structure lands before a large minute backfill."""
        stored = repo.latest_open_times(PROBE_PAIR)
        now_m = time.monotonic()
        pending: list[tuple[str, int]] = []
        for tf in ("H1", "D1", "W1", "MN", "M15", "M5", "M1"):
            opened = probes.get(tf)
            if opened is None or now_m < self._lag_retry_at.get(tf, 0.0):
                continue
            lag = self._catch_up_count(stored.get(tf), opened, tf)
            if opened != self._last_bar.get(tf) or lag:
                pending.append((tf, max(lag, INCREMENTAL_BARS)))
        if not pending:
            return True, False
        structure = {"H1", "D1", "W1", "MN"}
        chosen = [(tf, count) for tf, count in pending if tf in structure]
        if not chosen:
            chosen = pending[:1]
        runner = MarketIngestionRunner(gw, repo, candle_count=max(count for _, count in chosen))
        structure_failed = False
        synced: dict[str, int] = {}
        for tf, count in chosen:
            summary = runner.sync_timeframe_universe(tf, candle_count=count)
            failures = [
                r for r in summary["results"]
                if self._sync_result_blocking(r) or r.get("error") == "missing_candles"
            ]
            if failures:
                self._lag_retry_at[tf] = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                log.warning("Closed-bar catch-up failed for %s (%s bars): %s", tf, count, failures[0].get("error"))
                if tf in structure:
                    structure_failed = True
                with self._lock:
                    self._ctx.update(
                        provider_status="DEGRADED",
                        closed_bar_status="INCOMPLETE",
                        failed_candle_requests=failures[:40],
                    )
                continue
            self._last_bar[tf] = probes[tf]
            self._lag_retry_at.pop(tf, None)
            synced[tf] = count
        if "H1" in synced:
            runner.sync_timeframe_universe("H8", candle_count=max(INCREMENTAL_BARS, min(48, synced["H1"] // 8 + 3)))
        if structure_failed:
            self._bootstrapped = False
            self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
            return False, bool(synced)
        return True, bool(synced)

    def _sync_from_store(self, gw, repo: MarketRepository) -> bool:
        """Bridge uploads are already persisted: validate them with bulk reads instead of ~200 gateway round trips."""
        offset = broker_offset(gw)
        latest = probe_open_times(repo, PROBE_PAIR, offset)
        if not self._bootstrapped:
            if time.monotonic() < self._bootstrap_retry_at:
                return False
            with self._lock:
                self._state = "SYNCING"
            resolved = {r.get("canonical_symbol") for r in gw.get_symbols()}
            repo.conn.commit()
            missing = [p for p in FX_PAIRS_28 if p not in resolved]
            failures = [] if missing else store_failures(repo, CANDLE_TIMEFRAMES, offset)
            blocking = [f for f in failures if self._sync_result_blocking(f)] if failures else []
            ok = not missing and not blocking
            with self._lock:
                self._ctx.update(symbols_resolved=28-len(missing), missing_pairs=missing, failed_symbol_mappings=missing,
                                 provider_status="CONNECTED" if ok else "DEGRADED", failed_candle_requests=failures[:40],
                                 closed_bar_status="SYNCHRONIZED" if ok else "INCOMPLETE",
                                 last_successful_sync=_iso(datetime.now(timezone.utc)))
            basket = self._refresh_repository_basket_meta(repo)
            if missing and len(missing) == len(FX_PAIRS_28):
                self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
                return False
            self._last_bar = {tf: latest[tf] for tf in PROBE_TIMEFRAMES if tf in latest}
            self._bootstrapped = len(self._last_bar) >= max(4, len(PROBE_TIMEFRAMES) - 2) or basket["pairs_loaded"] >= 20
            return self._bootstrapped or basket["pairs_loaded"] > 0
        if any(tf not in latest for tf in PROBE_TIMEFRAMES):
            self._bootstrapped = False
            self._ctx.update(closed_bar_status="INCOMPLETE", error_code="stale_or_missing_candles")
            return False
        changed = [tf for tf in PROBE_TIMEFRAMES if latest[tf] != self._last_bar.get(tf)]
        if not changed:
            return False
        failures = store_failures(repo, [*changed, *(["H8"] if "H1" in changed else [])], offset)
        if failures:
            self._bootstrapped = False
            self._bootstrap_retry_at = time.monotonic() + BOOTSTRAP_RETRY_SECONDS
            with self._lock:
                self._ctx.update(provider_status="DEGRADED", closed_bar_status="INCOMPLETE", failed_candle_requests=failures)
            return False
        self._last_bar.update({tf: latest[tf] for tf in changed})
        return True

    def _wanted_modes(self) -> tuple[str, ...]:
        cutoff = time.monotonic() - MODE_INTEREST_SECONDS
        with self._lock:
            extra = sorted(m for m, t in self._mode_interest.items() if t >= cutoff)
        return ("CLOSE_CLOSE", *extra)

    def _tick(self) -> None:
        profile: dict[str, float] = {}
        mark = [time.monotonic()]

        def lap(name: str) -> None:
            now_ = time.monotonic()
            profile[name] = round(now_ - mark[0], 3)
            mark[0] = now_

        self._last_profile = profile
        connected = False
        ctx: dict = {}
        with db() as conn:
            lap("connect")
            from .market_data import ensure_active_provider_snapshot
            from .provider_manager import ProviderManager

            ensure_active_provider_snapshot(conn)
            ProviderManager(conn).refresh_health()
            ctx = market_context(conn)
            for provider, status in ctx.get("providers", {}).items():
                ProviderManager(conn).record_health(provider, status)
            conn.commit()
            lap("context")
            from .market_data import configuration
            cfg = configuration(conn)
            key = (
                ctx.get("active_provider"),
                cfg["tenant_id"],
                ctx.get("providers", {}).get(ctx.get("active_provider"), {}).get("account_id", cfg["account_id"]),
            )
            if key != self._provider_key:
                self._ctx = {}
                self._provider_key = key
                self._bootstrapped = False
                self._bootstrap_retry_at = 0.0
                self._last_bar = {}
                self._lag_retry_at = {}
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
                    self._forming_bids = {}
                    self._live_endpoints = {}
                    self._bar_anchors = {}
                    self._base_pair_data = None
                    self._last_bids = {}
                    self._quote_adapter = None
                    self._anchor_m1 = None
                    self._bids_changed = False
            connected = bool(ctx["market_data_ready"])
            with self._lock:
                for field in (
                    "provider_status",
                    "symbols_resolved",
                    "missing_pairs",
                    "failed_symbol_mappings",
                    "failed_candle_requests",
                    "last_successful_sync",
                    "closed_bar_status",
                ):
                    if key == self._provider_key and field in self._ctx:
                        ctx[field] = self._ctx[field]
                self._ctx = ctx
            if not connected:
                with self._lock:
                    self._state = "WAITING_PROVIDER"
                    self._ctx["provider_status"] = ctx.get("provider_status") or "DISCONNECTED"
                    self._result = None
                    self._bootstrapped = False
                    self._error = None
                return

        changed = False
        now = datetime.now(timezone.utc)
        with db() as conn:
            provider = ctx.get("active_provider") or "__unavailable__"
            repo = MarketRepository(conn, provider=provider)
            svc = CurrencyStrengthMatrixService(repo)
            changed = self._sync_closed_bars(repo, svc)
            basket = self._refresh_repository_basket_meta(repo)
            conn.commit()
            lap("sync")
            if not self._bootstrapped and basket.get("pairs_loaded", 0) == 0:
                with self._lock:
                    self._state = "BACKFILLING"
                    self._result = None
                return
            if not self._bootstrapped and basket.get("pairs_loaded", 0) > 0:
                self._bootstrapped = True

        result = None
        now_mono = time.monotonic()
        with db() as conn:
            provider = ctx.get("active_provider") or "__unavailable__"
            repo = MarketRepository(conn, provider=provider, snapshot_id=ctx.get("snapshot_id"))
            svc = CurrencyStrengthMatrixService(repo)
            with self._lock:
                ctx.update(self._ctx)
            with self._lock:
                self._state = "CALCULATING"
            live_inputs = bool(self._live_endpoints or self._forming_bids)
            recalc_after = QUOTE_SECONDS if live_inputs else HEARTBEAT_RECALC_SECONDS
            if changed or self._result is None or self._bids_changed or now_mono - self._last_calc_mono >= recalc_after:
                if changed or self._base_pair_data is None:
                    self._base_pair_data = svc.build_pair_closes_by_tf(now)
                result = self._recompute_from_cache(now)
            lap("calculate")
            if result is not None:
                signature = tuple(
                    round(result.values[c].get(tf, 0.0), 4) for c in sorted(result.values) for tf in MATRIX_TIMEFRAMES
                )
                if self._last_persist_mono == 0.0:
                    self._adopt_recent_persist(repo, now, now_mono)
                lap("adopt")
                persist_due = connected and signature != self._last_persisted_sig and (
                    self._last_persist_mono == 0.0
                    or now_mono - self._last_persist_mono >= SNAPSHOT_INTERVAL_SECONDS
                )
                if persist_due or now_mono - self._reference_mono >= REFERENCE_REFRESH_SECONDS:
                    self._refresh_reference(conn, now, now_mono)
                self._update_intelligence(result, signature)
                lap("reference")
                if persist_due:
                    svc.persist(result)
                    write_relationships(repo, result)
                    with self._lock:
                        pairs = self._pairs
                    save_pair_snapshot(conn, active_scope(conn), result.as_of, pairs)
                    self._last_persist_mono = now_mono
                    self._last_persisted_sig = signature
                    self._last_persisted_at = now
                lap("persist")
                histories = svc.score_histories() if persist_due or not self._histories else self._histories
                lap("histories")
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
            self._state = (
                "READY"
                if connected and self._result and self._result.pairs_loaded == 28 and self._result.historical_ok
                else "INCOMPLETE_BASKET"
            )
            self._error = None

    def _adopt_recent_persist(self, repo: MarketRepository, now: datetime, now_mono: float) -> None:
        """A fresh (serverless) instance must not duplicate a snapshot another instance just persisted."""
        row = scoped_query(repo.conn, "SELECT MAX(as_of) FROM mi_strength_snapshot", snapshot_id=repo.snapshot_id).fetchone()
        latest = values(row)[0] if row else None
        if not latest:
            return
        at = datetime.fromisoformat(str(latest))
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        age = (now - at).total_seconds()
        if 0 <= age < SNAPSHOT_INTERVAL_SECONDS:
            self._last_persist_mono = now_mono - age
            self._last_persisted_at = at

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
                self._state = 'WAITING_PROVIDER'
                self._error = None
            elif not self.running and not self._on_demand:
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
            connected = bool(
                ctx.get("market_data_ready")
                or ctx.get("connected")
                or str(ctx.get("provider_status", "")).upper() == "CONNECTED"
            )
            display_error = error if connected and state == "ERROR" else None
            if not display_error and not connected:
                code = ctx.get("error_code")
                display_error = str(code).replace("_", " ") if code else None
            repo_loaded = int(ctx.get("repository_pairs_loaded") or ctx.get("pairs_loaded") or 0)
            missing = ctx.get("missing_pairs") or []
            if connected and repo_loaded == 0:
                try:
                    from .basket_status import repository_basket_status

                    with db() as conn:
                        snap = ctx.get("snapshot_id")
                        scope = ctx.get("market_data_scope") or {}
                        basket = repository_basket_status(
                            conn,
                            provider=ctx.get("active_provider"),
                            snapshot_id=snap,
                            account_id=scope.get("account_id"),
                        )
                    repo_loaded = basket["pairs_loaded"]
                    missing = basket["missing_pairs"]
                except Exception:
                    pass
            return {
                **ctx,
                "provider_connected": connected,
                "strength_engine_status": state,
                "engine_state": state,
                "engine_error": display_error,
                "last_calculated_at": None,
                "as_of": None,
                "live_data": False,
                "stale": True,
                "historical_ok": False,
                "missing_history": [],
                "pairs_loaded": repo_loaded,
                "pairs_total": 28,
                "missing_pairs": missing,
                "closed_bar_only": True,
                "bar_basis": "closed",
                "calculation_mode": "CLOSE_CLOSE",
            }
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
            "bar_basis": "forming" if result.forming_close else "closed",
            "closed_bar_only": not result.forming_close,
            "engine_error": error,
            "stale": stale_reason is not None,
            "stale_reason": stale_reason,
            "live_refresh_at": _iso(last_tick),
            "last_persisted_at": _iso(last_persisted),
            "last_bar_change_at": _iso(last_change),
            "snapshot_interval_seconds": SNAPSHOT_INTERVAL_SECONDS,
            "tick_profile": dict(self._last_profile),
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
