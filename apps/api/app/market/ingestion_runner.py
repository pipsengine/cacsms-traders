from __future__ import annotations

import logging
from dataclasses import asdict, replace

from .constants import FX_PAIRS_28, NATIVE_CANDLE_TIMEFRAMES
from .h8_aggregate import aggregate_h8_from_h1
from .ingestion import CandleIngestionService
from .models import Candle, DataQuality
from .provider_contract import MarketDataUnavailable
from .quality import assess

log = logging.getLogger(__name__)

_NATIVE = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN")


class MarketIngestionRunner:
    def __init__(self, gateway, repo, *, candle_count: int = 400):
        self.gateway = gateway
        self.repo = repo
        self.ingestion = CandleIngestionService(gateway, repo)
        self.candle_count = candle_count

    def _save_quality(self, symbol: str, timeframe: str, last_closed_at, missing_bars: int = 0, reason: str = ""):
        q = assess(symbol, timeframe, last_closed_at, missing_bars=missing_bars)
        if reason:
            q = DataQuality(q.symbol, q.timeframe, "MISSING", q.last_closed_at, q.age_seconds, missing_bars, reason)
        self.repo.upsert_quality(q)

    def sync_h8(self, pair: str) -> dict:
        try:
            h1 = self.gateway.closed_candles(pair, "H1", self.candle_count * 8 + 16)
        except MarketDataUnavailable as e:
            self._save_quality(pair, "H8", None, missing_bars=1, reason=str(e))
            return {"symbol": pair, "timeframe": "H8", "accepted": 0, "rejected": 0, "error": str(e)}
        h8 = aggregate_h8_from_h1(h1)
        accepted = 0
        store = pair.upper()
        for c in h8:
            row = replace(c, symbol=store) if c.symbol != store else c
            accepted += int(self.repo.upsert_candle(row))
        self.repo.conn.commit()
        last = h8[-1].close_time if h8 else None
        self._save_quality(store, "H8", last)
        return {"symbol": store, "timeframe": "H8", "accepted": accepted, "rejected": 0}

    def sync_pair_timeframe(self, pair: str, timeframe: str) -> dict:
        if timeframe == "H8":
            return self.sync_h8(pair)
        try:
            result = self.ingestion.sync(pair, timeframe, self.candle_count, store_as=pair)
            q = result.get("quality") or {}
            self._save_quality(pair, timeframe, q.get("last_closed_at"))
            return result
        except MarketDataUnavailable as e:
            self._save_quality(pair, timeframe, None, missing_bars=1, reason=str(e))
            return {"symbol": pair, "timeframe": timeframe, "accepted": 0, "rejected": 0, "error": str(e)}

    def sync_universe(self) -> dict:
        summary = {"pairs": len(FX_PAIRS_28), "results": [], "errors": 0}
        for pair in FX_PAIRS_28:
            for tf in NATIVE_CANDLE_TIMEFRAMES:
                if tf not in _NATIVE and tf != "H8":
                    continue
                r = self.sync_pair_timeframe(pair, tf)
                summary["results"].append(r)
                if r.get("error") or r.get("accepted", 0) == 0:
                    summary["errors"] += 1
        self.repo.conn.commit()
        return summary

    def sync_timeframe_universe(self, timeframe: str, *, candle_count: int | None = None) -> dict:
        """Pull latest closed bars for one timeframe across the 28-pair basket (live refresh)."""
        count = candle_count if candle_count is not None else min(12, self.candle_count)
        tf = timeframe.upper()
        summary = {"timeframe": tf, "pairs": len(FX_PAIRS_28), "results": [], "errors": 0}
        prev = self.candle_count
        self.candle_count = count
        try:
            for pair in FX_PAIRS_28:
                if tf == "H8":
                    r = self.sync_h8(pair)
                else:
                    r = self.sync_pair_timeframe(pair, tf)
                summary["results"].append(r)
                if r.get("error"):
                    summary["errors"] += 1
        finally:
            self.candle_count = prev
        self.repo.conn.commit()
        return summary
