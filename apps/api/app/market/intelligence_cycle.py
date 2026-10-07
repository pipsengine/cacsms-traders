"""Backend intelligence cycle: ingest closed candles → CSM → relationships."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ..core.database import db
from .constants import COMPUTE_TIMEFRAMES, FX_PAIRS
from .csm_engine import CalculationMode
from .csm_service import CurrencyStrengthMatrixService
from .ingestion_runner import MarketIngestionRunner
from .models import StrengthPoint
from .market_data import create_market_data_gateway, market_context
from .relationship_engine import RelationshipEngine
from .repository import MarketRepository

log = logging.getLogger(__name__)

RELATIONSHIP_TIMEFRAMES = ("AVG", "H1", "D1")


def write_relationships(repo: MarketRepository, result) -> int:
    rel_engine = RelationshipEngine()
    relationships = []
    as_of = result.as_of
    for tf in RELATIONSHIP_TIMEFRAMES:
        for pair in FX_PAIRS:
            b, q = pair[:3], pair[3:]
            if b not in result.values or q not in result.values:
                continue
            points = []
            for cur in (b, q):
                n = result.sample_counts[cur].get(tf, 0)
                points.append(
                    StrengthPoint(
                        cur,
                        tf,
                        as_of,
                        result.values[cur].get(tf, 0.0),
                        sample_count=n,
                        quality=result.quality[cur].get(tf, "MISSING"),
                        confidence=min(1.0, n / 7.0),
                    )
                )
            relationships.append(rel_engine.classify(pair, tf, points[0], points[1], [], as_of))
    repo.save_relationships(relationships)
    repo.conn.commit()
    return len(relationships)


def run_intelligence_cycle(*, ingest: bool = True, candle_count: int = 400) -> dict:
    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    with db() as conn:
        from .provider_manager import ProviderManager
        ProviderManager(conn).refresh_health()
        context = market_context(conn)
        if not context["market_data_ready"]:
            return {"market_data": context, "analysis_only": True}
        gateway = create_market_data_gateway(conn)
        repo = MarketRepository(conn)
        ingest_summary = None
        if ingest:
            try:
                ingest_summary = MarketIngestionRunner(gateway, repo, candle_count=candle_count).sync_universe()
            except Exception:
                log.exception("Ingestion phase failed")
                ingest_summary = {"errors": -1, "message": "ingestion_failed"}

        if ingest_summary and ingest_summary.get("errors"):
            return {"market_data": context, "ingest": ingest_summary, "strength_engine_status": "INCOMPLETE_BASKET"}
        csm = CurrencyStrengthMatrixService(repo)
        result = csm.calculate(calculation_mode=CalculationMode.CLOSE_CLOSE)
        csm.persist(result, run_id=run_id)
        rel_count = write_relationships(repo, result)

        payload = csm.to_api_payload(
            result,
            provider_connected=context["market_data_ready"],
            active_provider=context["active_provider"],
        )
        return {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "ingest": ingest_summary,
            "historical_ok": result.historical_ok,
            "relationships_written": rel_count,
            "matrix_timeframes": list(COMPUTE_TIMEFRAMES),
            "meta": payload["meta"],
        }
