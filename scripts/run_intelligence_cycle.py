"""Full MI cycle: optional ingest → CSM matrix → relationship snapshots."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.api.app.market.intelligence_cycle import run_intelligence_cycle


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-ingest", action="store_true", help="Skip MT5 ingest; calculate from DB only")
    p.add_argument("--count", type=int, default=400)
    args = p.parse_args()
    out = run_intelligence_cycle(ingest=not args.no_ingest, candle_count=args.count)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
