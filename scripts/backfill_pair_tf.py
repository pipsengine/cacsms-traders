"""Backfill one pair/timeframe into mi_provider_candle (local dev helper)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_PATH", str(ROOT / "database" / "db_cacsms-traders.db"))

pair = (sys.argv[1] if len(sys.argv) > 1 else "EURNZD").upper()
tf = (sys.argv[2] if len(sys.argv) > 2 else "MN").upper()


def main() -> None:
    from apps.api.app.core.database import db
    from apps.api.app.domain.mt5_connection import ensure_gateway_session
    from apps.api.app.market.market_data import create_market_data_gateway, market_context
    from apps.api.app.market.ingestion_runner import MarketIngestionRunner
    from apps.api.app.market.repository import MarketRepository

    with db() as conn:
        ensure_gateway_session(conn, "tenant-cacsms")
        ctx = market_context(conn)
        gw = create_market_data_gateway(conn, context=ctx)
        repo = MarketRepository(conn, provider=gw.provider_id, snapshot_id=gw.snapshot_id)
        repo.account_id = (gw.get_account_context() or {}).get("account_id", "")
        result = MarketIngestionRunner(gw, repo, candle_count=400).sync_pair_timeframe(pair, tf)
        conn.commit()
        print("sync", result)
        n = conn.execute(
            "SELECT COUNT(*) n FROM mi_provider_candle WHERE symbol=? AND timeframe=? AND account_id=?",
            (pair, tf, repo.account_id),
        ).fetchone()["n"]
        print(f"{pair} {tf} rows for account", n)


if __name__ == "__main__":
    main()
