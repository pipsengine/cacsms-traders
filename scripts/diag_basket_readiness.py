"""Check whether persisted candles satisfy CSM basket rules for active snapshot."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_PATH", str(ROOT / "database" / "db_cacsms-traders.db"))

from apps.api.app.core.database import db
from apps.api.app.market.constants import FX_PAIRS_28, MATRIX_TIMEFRAMES, MATRIX_TO_CANDLE, SYNTHETIC_MATRIX_TIMEFRAMES
from apps.api.app.market.csm_service import CurrencyStrengthMatrixService
from apps.api.app.market.repository import MarketRepository


def main() -> None:
    with db() as conn:
        snap = conn.execute(
            "SELECT * FROM mi_provider_snapshot WHERE finalized_at IS NULL ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not snap:
            print("no active snapshot")
            return
        print("snapshot", dict(snap))
        repo = MarketRepository(conn, provider=snap["provider"], snapshot_id=snap["id"])
        print("repo provider", repo.provider, "account_id", repo.account_id)
        candle_tfs = [tf for tf in MATRIX_TIMEFRAMES if tf not in SYNTHETIC_MATRIX_TIMEFRAMES]
        missing_by_tf = {}
        for tf in candle_tfs:
            ct = MATRIX_TO_CANDLE.get(tf, tf)
            by = repo.closes_by_timeframe(ct)
            miss = [p for p in FX_PAIRS_28 if p not in by or not by[p]]
            missing_by_tf[tf] = miss
            print(f"TF {tf} (candles {ct}): {len(FX_PAIRS_28) - len(miss)}/28 pairs with closes")
        svc = CurrencyStrengthMatrixService(repo)
        result = svc.calculate()
        print("calculate pairs_loaded", result.pairs_loaded, "historical_ok", result.historical_ok)
        print("missing_pairs sample", result.missing_pairs[:5], "count", len(result.missing_pairs))


if __name__ == "__main__":
    main()
