"""Ingest closed FX candles from MT5 into mi_candle (28 pairs × native timeframes)."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.core.database import db
from apps.api.app.market.ingestion_runner import MarketIngestionRunner
from apps.api.app.market.mt5_gateway import create_market_data_gateway
from apps.api.app.market.repository import MarketRepository


def main():
    p = argparse.ArgumentParser(description="Ingest closed MT5 candles for Market Intelligence")
    p.add_argument("--count", type=int, default=400, help="Closed bars per symbol/timeframe")
    args = p.parse_args()
    gw = create_market_data_gateway()
    print("Market data:", gw.connection_state())
    with db() as conn:
        summary = MarketIngestionRunner(gw, MarketRepository(conn), candle_count=args.count).sync_universe()
    print("Ingest complete:", summary["pairs"], "pairs,", len(summary["results"]), "syncs,", summary["errors"], "issues")


if __name__ == "__main__":
    main()
