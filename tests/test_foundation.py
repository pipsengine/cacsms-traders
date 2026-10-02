import os,tempfile
from pathlib import Path

def test_required_structure_exists():
 root=Path(__file__).resolve().parents[1]
 for p in ['apps/api/app/main.py','apps/web/src/App.tsx','database/migrations/001_platform_foundation.sql','docs/ARCHITECTURE.md']:
  assert (root/p).exists()
def test_no_market_strategy_in_foundation():
 root=Path(__file__).resolve().parents[1]
 assert not (root/'engine/opportunities').exists()
