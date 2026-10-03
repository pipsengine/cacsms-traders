"""Backend intelligence cycle: ingest closed candles → CSM → relationships."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ..core.database import db
from .constants import FX_PAIRS, MATRIX_TIMEFRAMES
from .csm_engine import CalculationMode
from .csm_service import CurrencyStrengthMatrixService
from .ingestion_runner import MarketIngestionRunner
from .models import StrengthPoint
from .mt5_gateway import create_market_data_gateway
from .relationship_engine import RelationshipEngine
from .repository import MarketRepository

log = logging.getLogger(__name__)

RELATIONSHIP_TIMEFRAMES = ("AVG", "H1", "D1")


def run_intelligence_cycle(*, ingest: bool = True, candle_count: int = 400) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    gateway = create_market_data_gateway()
    with db() as conn:
        repo = MarketRepository(conn)
        ingest_summary = None
        if ingest:
            try:
                ingest_summary = MarketIngestionRunner(gateway, repo, candle_count=candle_count).sync_universe()
            except Exception:
                log.exception("Ingestion phase failed")
                ingest_summary = {"errors": -1, "message": "ingestion_failed"}

        csm = CurrencyStrengthMatrixService(repo)
        result = csm.calculate(calculation_mode=CalculationMode.CLOSE_CLOSE)
        csm.persist(result, run_id=run_id)

        rel_engine = RelationshipEngine()
        rel_count = 0
        as_of = result.as_of
        for tf in RELATIONSHIP_TIMEFRAMES:
            for pair in FX_PAIRS:
                b, q = pair[:3], pair[3:]
                if b not in result.values or q not in result.values:
                    continue
                sb = StrengthPoint(
                    b,
                    tf,
                    as_of,
                    result.values[b].get(tf, 0.0),
                    sample_count=result.sample_counts[b].get(tf, 0),
                    quality=result.quality[b].get(tf, "MISSING"),
                    confidence=min(1.0, result.sample_counts[b].get(tf, 0) / 7.0),
                )
                sq = StrengthPoint(
                    q,
                    tf,
                    as_of,
                    result.values[q].get(tf, 0.0),
                    sample_count=result.sample_counts[q].get(tf, 0),
                    quality=result.quality[q].get(tf, "MISSING"),
                    confidence=min(1.0, result.sample_counts[q].get(tf, 0) / 7.0),
                )
                rp = rel_engine.classify(pair, tf, sb, sq, [], as_of)
                repo.save_relationship(rp)
                rel_count += 1

        payload = csm.to_api_payload(
            result,
            mt5_connected=bool(gateway.connection_state().get("connected")),
        )
        return {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "ingest": ingest_summary,
            "historical_ok": result.historical_ok,
            "relationships_written": rel_count,
            "matrix_timeframes": list(MATRIX_TIMEFRAMES),
            "meta": payload["meta"],
        }
