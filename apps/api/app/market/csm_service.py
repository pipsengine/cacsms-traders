from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .constants import CSM_CURRENCIES, FX_PAIRS_28, MATRIX_TIMEFRAMES, NATIVE_CANDLE_TIMEFRAMES
from .csm_engine import CalculationMode, CsmMatrixResult, compute_matrix, sort_currencies_by
from .csm_windows import quarter_start, window_closes, year_start
from .models import StrengthPoint
from .mt5_gateway import _broker_symbol
from .repository import MarketRepository


class CurrencyStrengthMatrixService:
    """Loads closed candles, runs CSM math, persists snapshots."""

    def __init__(self, repo: MarketRepository):
        self.repo = repo

    def _db_symbol(self, pair: str, timeframe: str) -> str:
        for candidate in (_broker_symbol(pair), pair.upper()):
            if self.repo.candles(candidate, timeframe, limit=1):
                return candidate
        return _broker_symbol(pair)

    def _load_pair_closes(self, pair: str, timeframe: str, limit: int = 400) -> list[float]:
        symbol = self._db_symbol(pair, timeframe)
        rows = self.repo.candles(symbol, timeframe, limit=limit)
        return [float(r[5]) for r in rows if float(r[5]) > 0]

    def _load_d1_series(self, pair: str, limit: int = 400) -> list[tuple[datetime, float]]:
        symbol = self._db_symbol(pair, "D1")
        rows = self.repo.candles(symbol, "D1", limit=limit)
        out: list[tuple[datetime, float]] = []
        for r in rows:
            ot = datetime.fromisoformat(r[0])
            if ot.tzinfo is None:
                ot = ot.replace(tzinfo=timezone.utc)
            c = float(r[5])
            if c > 0:
                out.append((ot, c))
        return out

    def _synthetic_ytd_q_closes(
        self, as_of: datetime
    ) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
        """Build pseudo close series [start, end] per pair for YTD and Q from D1 history."""
        ytd: dict[str, list[float]] = {}
        q: dict[str, list[float]] = {}
        ys = year_start(as_of)
        qs = quarter_start(as_of)
        for pair in FX_PAIRS_28:
            series = self._load_d1_series(pair)
            y0, y1 = window_closes(series, ys)
            q0, q1 = window_closes(series, qs)
            if y0 is not None and y1 is not None:
                ytd[pair] = [y0, y1]
            if q0 is not None and q1 is not None:
                q[pair] = [q0, q1]
        return ytd, q

    def build_pair_closes_by_tf(self, as_of: datetime) -> dict[str, dict[str, list[float]]]:
        by_tf: dict[str, dict[str, list[float]]] = {tf: {} for tf in MATRIX_TIMEFRAMES if tf != "AVG"}
        ytd, q = self._synthetic_ytd_q_closes(as_of)
        by_tf["YTD"] = ytd
        by_tf["Q"] = q
        for tf in NATIVE_CANDLE_TIMEFRAMES:
            for pair in FX_PAIRS_28:
                closes = self._load_pair_closes(pair, tf)
                if len(closes) >= 2:
                    by_tf[tf][pair] = closes
        return by_tf

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
        return compute_matrix(MATRIX_TIMEFRAMES, pair_data, bars_difference=bars_difference, as_of=as_of)

    def persist(self, result: CsmMatrixResult, run_id: str | None = None) -> None:
        run_id = run_id or str(uuid.uuid4())
        started = datetime.now(timezone.utc).isoformat()
        for currency in CSM_CURRENCIES:
            for tf in MATRIX_TIMEFRAMES:
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
                    )
                )
        self.repo.conn.execute(
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
                json.dumps({"engine": "csm", "historical_ok": result.historical_ok}),
            ),
        )
        self.repo.conn.commit()

    def to_api_payload(
        self,
        result: CsmMatrixResult,
        *,
        calculation_mode: CalculationMode = CalculationMode.CLOSE_CLOSE,
        sort_by: str = "AVG",
        bars_difference: int = 1,
        mt5_connected: bool = False,
    ) -> dict:
        order = sort_currencies_by(result.values, sort_by)
        by_avg = sorted(CSM_CURRENCIES, key=lambda x: -result.values[x]["AVG"])
        ranking = [{"currency": c, "value": result.values[c]["AVG"], "rank": i + 1} for i, c in enumerate(by_avg)]
        flat = []
        for currency in CSM_CURRENCIES:
            for tf in MATRIX_TIMEFRAMES:
                flat.append(
                    {
                        "currency": currency,
                        "timeframe": tf,
                        "as_of": result.as_of.isoformat(),
                        "value": result.values[currency][tf],
                        "slope": 0.0,
                        "velocity": 0.0,
                        "acceleration": 0.0,
                        "persistence": 0.0,
                        "confidence": min(1.0, result.sample_counts[currency].get(tf, 0) / 7.0),
                        "sample_count": result.sample_counts[currency].get(tf, 0),
                        "quality": result.quality[currency].get(tf, "MISSING"),
                    }
                )
        missing = [{"symbol": m.symbol, "timeframe": m.timeframe} for m in result.missing[:50]]
        return {
            "meta": {
                "as_of": result.as_of.isoformat(),
                "last_calculated_at": result.as_of.isoformat(),
                "calculation_mode": calculation_mode.value,
                "bars_difference": bars_difference,
                "sort_by": sort_by,
                "closed_bar_only": True,
                "data_source": "MT5",
                "mt5_connected": mt5_connected,
                "historical_ok": result.historical_ok,
                "missing_history": missing,
                "stale": False,
                "currency_order": order,
            },
            "matrix": [
                {
                    "currency": c,
                    "values": result.values[c],
                    "quality": result.quality[c],
                    "sample_counts": result.sample_counts[c],
                }
                for c in order
            ],
            "avg_ranking": ranking,
            "rows": flat,
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
            c, tf = r["currency"], r["timeframe"]
            if c not in values:
                continue
            values[c][tf] = float(r["value"])
            quality[c][tf] = r["quality"]
            sample_counts[c][tf] = int(r["sample_count"] or 0)
            if r["quality"] == "MISSING":
                historical_ok = False
        for c in CSM_CURRENCIES:
            if "AVG" not in values[c]:
                from .csm_engine import compute_avg

                values[c]["AVG"] = compute_avg(values[c], MATRIX_TIMEFRAMES)
                quality[c]["AVG"] = "FRESH" if historical_ok else "MISSING"
        result = CsmMatrixResult(values, quality, sample_counts, [], historical_ok, as_of)
        return self.to_api_payload(result, sort_by=sort_by)
