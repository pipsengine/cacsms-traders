from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..core.database import execute_retry
from .constants import (
    CSM_CURRENCIES,
    COMPUTE_TIMEFRAMES,
    FX_PAIRS_28,
    MATRIX_TIMEFRAMES,
    MATRIX_TO_CANDLE,
    SYNTHETIC_MATRIX_TIMEFRAMES,
    normalize_matrix_timeframe,
)
from .csm_engine import (
    CalculationMode,
    CsmMatrixResult,
    compute_avg,
    compute_matrix,
)
from .csm_scoring import normalize_all_scores
from .csm_windows import rolling_quarter_start, window_closes, year_start
from .models import StrengthPoint
from .repository import MarketRepository
from .strength_classification import classify, thresholds_payload

SPARKLINE_POINTS = 32


class CurrencyStrengthMatrixService:
    """Loads closed candles, runs EarnForex CSM close-to-close math, persists snapshots."""

    def __init__(self, repo: MarketRepository):
        self.repo = repo

    def _closes_for_pair(self, pair: str, by_symbol: dict[str, list[float]]) -> list[float] | None:
        p = pair.upper()
        if p in by_symbol and len(by_symbol[p]) >= 2:
            return by_symbol[p]
        stored = self.repo.resolve_stored_symbol(p)
        if stored and stored in by_symbol and len(by_symbol[stored]) >= 2:
            return by_symbol[stored]
        return None

    def _d1_series_for_pair(
        self, pair: str, by_symbol: dict[str, list[tuple[datetime, float]]]
    ) -> list[tuple[datetime, float]]:
        p = pair.upper()
        if p in by_symbol:
            return by_symbol[p]
        stored = self.repo.resolve_stored_symbol(p)
        if stored and stored in by_symbol:
            return by_symbol[stored]
        return []

    def _synthetic_ytd_q(
        self, as_of: datetime, d1_by_symbol: dict[str, list[tuple[datetime, float]]] | None = None
    ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
        ytd: dict[str, list[float]] = {}
        q: dict[str, list[float]] = {}
        ys = year_start(as_of)
        qs = rolling_quarter_start(as_of)
        d1 = d1_by_symbol if d1_by_symbol is not None else self.repo.d1_series_by_symbol()
        for pair in FX_PAIRS_28:
            series = self._d1_series_for_pair(pair, d1)
            if not series:
                continue
            normalized: list[tuple[datetime, float]] = []
            for ot, c in series:
                if ot.tzinfo is None:
                    ot = ot.replace(tzinfo=timezone.utc)
                normalized.append((ot, c))
            y0, y1 = window_closes(normalized, ys)
            q0, q1 = window_closes(normalized, qs)
            if y0 is not None and y1 is not None:
                ytd[pair] = [y0, y1]
            if q0 is not None and q1 is not None:
                q[pair] = [q0, q1]
        return ytd, q

    def build_pair_closes_by_tf(self, as_of: datetime) -> dict[str, dict[str, list[float]]]:
        by_tf: dict[str, dict[str, list[float]]] = {tf: {} for tf in MATRIX_TIMEFRAMES}
        d1_series = self.repo.d1_series_by_symbol()
        ytd, q = self._synthetic_ytd_q(as_of, d1_series)
        by_tf["YTD"] = ytd
        by_tf["Q"] = q
        candle_cache: dict[str, dict[str, list[float]]] = {}
        for matrix_tf, candle_tf in MATRIX_TO_CANDLE.items():
            if candle_tf not in candle_cache:
                candle_cache[candle_tf] = self.repo.closes_by_timeframe(candle_tf)
            by_symbol = candle_cache[candle_tf]
            for pair in FX_PAIRS_28:
                closes = self._closes_for_pair(pair, by_symbol)
                if closes:
                    by_tf[matrix_tf][pair] = closes
        return by_tf

    @staticmethod
    def missing_pairs(pair_data: dict[str, dict[str, list[float]]]) -> list[str]:
        """Pairs lacking closed-bar history on at least one provider-backed matrix timeframe."""
        candle_tfs = [tf for tf in MATRIX_TIMEFRAMES if tf not in SYNTHETIC_MATRIX_TIMEFRAMES]
        return [p for p in FX_PAIRS_28 if not all(p in pair_data.get(tf, {}) for tf in candle_tfs)]

    @classmethod
    def pairs_loaded(cls, pair_data: dict[str, dict[str, list[float]]]) -> int:
        return len(FX_PAIRS_28) - len(cls.missing_pairs(pair_data))

    def calculate(
        self,
        *,
        calculation_mode: CalculationMode = CalculationMode.CLOSE_CLOSE,
        bars_difference: int = 1,
        as_of: datetime | None = None,
    ) -> CsmMatrixResult:
        if calculation_mode != CalculationMode.CLOSE_CLOSE:
            raise NotImplementedError(f"Calculation mode {calculation_mode} is reserved for a future release")
        as_of = as_of or datetime.now(timezone.utc)
        pair_data = self.build_pair_closes_by_tf(as_of)
        return self.calculate_from(pair_data, as_of=as_of, bars_difference=bars_difference)

    def calculate_from(
        self,
        pair_data: dict[str, dict[str, list[float]]],
        *,
        as_of: datetime,
        bars_difference: int = 1,
    ) -> CsmMatrixResult:
        result = compute_matrix(COMPUTE_TIMEFRAMES, pair_data, bars_difference=bars_difference, as_of=as_of)
        result.missing_pairs = self.missing_pairs(pair_data)
        result.pairs_loaded = len(FX_PAIRS_28) - len(result.missing_pairs)
        return result

    def persist(self, result: CsmMatrixResult, run_id: str | None = None) -> None:
        run_id = run_id or str(uuid.uuid4())
        started = datetime.now(timezone.utc).isoformat()
        scores = normalize_all_scores(result.values, COMPUTE_TIMEFRAMES, result.quality)
        for currency in CSM_CURRENCIES:
            for tf in COMPUTE_TIMEFRAMES:
                val = result.values[currency].get(tf, 0.0)
                q = result.quality[currency].get(tf, "MISSING")
                sc = result.sample_counts[currency].get(tf, 0)
                self.repo.save_strength(
                    StrengthPoint(
                        currency,
                        tf,
                        result.as_of,
                        val,
                        sample_count=sc,
                        quality=q,
                        confidence=min(1.0, sc / 7.0) if sc else 0.0,
                        score=scores[currency].get(tf),
                    )
                )
        execute_retry(
            self.repo.conn,
            """INSERT INTO mi_calculation_run(id,tenant_id,timeframe,started_at,completed_at,status,pair_count,currency_count,error,metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                None,
                "MATRIX",
                started,
                datetime.now(timezone.utc).isoformat(),
                "OK" if result.historical_ok else "PARTIAL",
                len(FX_PAIRS_28),
                len(CSM_CURRENCIES),
                None if result.historical_ok else "MISSING_HISTORY",
                json.dumps({"engine": "csm", "historical_ok": result.historical_ok, "source_provider": self.repo.provider, "snapshot_id": self.repo.snapshot_id}),
            ),
        )
        self.repo.conn.commit()

    def backfill_scores(self) -> int:
        """Derive 0–100 scores for persisted snapshots that predate the score column."""
        conn = self.repo.conn
        pending = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT as_of FROM mi_strength_snapshot WHERE timeframe='AVG' AND score IS NULL ORDER BY as_of"
            ).fetchall()
        ]
        updated = 0
        for as_of in pending:
            rows = conn.execute(
                "SELECT currency, timeframe, value, quality FROM mi_strength_snapshot WHERE as_of=?", (as_of,)
            ).fetchall()
            values: dict[str, dict[str, float]] = {c: {} for c in CSM_CURRENCIES}
            quality: dict[str, dict[str, str]] = {c: {} for c in CSM_CURRENCIES}
            for currency, tf, value, q in rows:
                tf = normalize_matrix_timeframe(tf)
                if currency in values and tf in MATRIX_TIMEFRAMES:
                    values[currency][tf] = float(value)
                    quality[currency][tf] = q or "MISSING"
            scores = normalize_all_scores(values, COMPUTE_TIMEFRAMES, quality)
            for currency, by_tf in scores.items():
                for tf, score in by_tf.items():
                    stored = ("W", "W1") if tf == "W" else (tf,)
                    for name in stored:
                        updated += conn.execute(
                            "UPDATE mi_strength_snapshot SET score=? WHERE as_of=? AND currency=? AND timeframe=? AND score IS NULL",
                            (score, as_of, currency, name),
                        ).rowcount
        conn.commit()
        return updated

    def score_histories(self, limit: int = SPARKLINE_POINTS) -> dict[str, list[tuple[str, float]]]:
        return {c: self.repo.score_history(c, "AVG", limit) for c in CSM_CURRENCIES}

    @staticmethod
    def currency_summary(
        scores: dict[str, dict[str, float]],
        histories: dict[str, list[tuple[str, float]]],
    ) -> list[dict]:
        """Card data ranked strongest → weakest; sparklines come from persisted AVG scores."""
        out: list[dict] = []
        for c in CSM_CURRENCIES:
            current = scores[c].get("AVG")
            if current is None:
                continue
            series = [s for _, s in histories.get(c, [])]
            if not series or series[-1] != current:
                series = (series + [current])[-SPARKLINE_POINTS:]
            base = series[0]
            change = round(current - base, 1)
            change_pct = round(change / base * 100.0, 1) if base else 0.0
            out.append(
                {
                    "currency": c,
                    "score": current,
                    "classification": classify(current),
                    "sparkline": series,
                    "change": change,
                    "change_pct": change_pct,
                }
            )
        out.sort(key=lambda r: -r["score"])
        for i, r in enumerate(out):
            r["rank"] = i + 1
        return out

    def to_api_payload(
        self,
        result: CsmMatrixResult,
        *,
        calculation_mode: CalculationMode = CalculationMode.CLOSE_CLOSE,
        sort_by: str = "AVG",
        bars_difference: int = 1,
        provider_connected: bool = False,
        active_provider: str = "none",
        live_data: bool = False,
        histories: dict[str, list[tuple[str, float]]] | None = None,
    ) -> dict:
        scores = normalize_all_scores(result.values, COMPUTE_TIMEFRAMES, result.quality)
        key = normalize_matrix_timeframe(sort_by.upper() if sort_by.upper() != "CURRENT" else "AVG")
        order = sorted(CSM_CURRENCIES, key=lambda c: -scores[c].get(key, -1.0))
        by_avg = sorted(CSM_CURRENCIES, key=lambda c: -scores[c].get("AVG", -1.0))
        ranking = []
        for i, c in enumerate(by_avg):
            s = scores[c].get("AVG")
            ranking.append(
                {
                    "currency": c,
                    "value": result.values[c].get("AVG", 0.0),
                    "score": s,
                    "rank": i + 1,
                    "classification": classify(s) if s is not None else None,
                }
            )
        missing = [{"symbol": m.symbol, "timeframe": m.timeframe} for m in result.missing[:50]]
        matrix_rows = [
            {
                "currency": c,
                "values": {tf: result.values[c].get(tf, 0.0) for tf in COMPUTE_TIMEFRAMES},
                "scores": {tf: scores[c][tf] for tf in COMPUTE_TIMEFRAMES if tf in scores[c]},
                "quality": {tf: result.quality[c].get(tf, "MISSING") for tf in COMPUTE_TIMEFRAMES},
                "sample_counts": {tf: result.sample_counts[c].get(tf, 0) for tf in COMPUTE_TIMEFRAMES},
            }
            for c in order
        ]
        return {
            "meta": {
                "as_of": result.as_of.isoformat(),
                "last_calculated_at": result.as_of.isoformat(),
                "calculation_mode": calculation_mode.value,
                "bars_difference": bars_difference,
                "sort_by": sort_by,
                "closed_bar_only": True,
                "data_source": active_provider,
                "provider_connected": provider_connected,
                "active_provider": active_provider,
                "live_data": live_data,
                "historical_ok": result.historical_ok,
                "missing_history": missing,
                "stale": False,
                "currency_order": order,
                "pairs_loaded": result.pairs_loaded,
                "pairs_total": len(FX_PAIRS_28),
                "missing_pairs": result.missing_pairs,
                "classification_thresholds": thresholds_payload(),
            },
            "matrix": matrix_rows,
            "avg_ranking": ranking,
            "currency_summary": self.currency_summary(scores, histories or {}),
        }

    def latest_from_db(self, sort_by: str = "AVG") -> dict | None:
        rows = self.repo.latest_matrix()
        if not rows:
            return None
        rows = [dict(r) for r in rows]
        as_of = max(datetime.fromisoformat(r["as_of"]) for r in rows)
        values: dict[str, dict[str, float]] = {c: {} for c in CSM_CURRENCIES}
        quality: dict[str, dict[str, str]] = {c: {} for c in CSM_CURRENCIES}
        sample_counts: dict[str, dict[str, int]] = {c: {} for c in CSM_CURRENCIES}
        historical_ok = True
        for r in rows:
            c, tf = r["currency"], normalize_matrix_timeframe(r["timeframe"])
            if c not in values or tf not in MATRIX_TIMEFRAMES:
                continue
            values[c][tf] = float(r["value"])
            quality[c][tf] = r["quality"]
            sample_counts[c][tf] = int(r["sample_count"] or 0)
            if r["quality"] == "MISSING":
                historical_ok = False
        for c in CSM_CURRENCIES:
            for tf in MATRIX_TIMEFRAMES:
                values[c].setdefault(tf, 0.0)
                quality[c].setdefault(tf, "MISSING")
                sample_counts[c].setdefault(tf, 0)
            values[c]["AVG"] = compute_avg(values[c], quality[c], MATRIX_TIMEFRAMES)
            quality[c]["AVG"] = "FRESH" if historical_ok else "PARTIAL"
        result = CsmMatrixResult(values, quality, sample_counts, [], historical_ok, as_of)
        return self.to_api_payload(result, sort_by=sort_by, histories=self.score_histories())
