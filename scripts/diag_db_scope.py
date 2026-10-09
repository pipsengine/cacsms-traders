import json
import sqlite3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "database" / "db_cacsms-traders.db"
c = sqlite3.connect(p)
c.row_factory = sqlite3.Row
cfg = json.loads(c.execute("SELECT value_json FROM system_settings WHERE key='market_data.provider'").fetchone()[0])
print("cfg account_id", cfg.get("account_id"))
snap = c.execute("SELECT * FROM mi_provider_snapshot WHERE finalized_at IS NULL").fetchone()
print("active snapshot", dict(snap) if snap else None)
for row in c.execute(
    "SELECT source, account_id, COUNT(*) n, COUNT(DISTINCT symbol) syms FROM mi_provider_candle GROUP BY source, account_id ORDER BY n DESC LIMIT 10"
):
    print(dict(row))
for prov in ("mt5", "ctrader"):
    row = c.execute("SELECT state_json FROM mi_provider_health WHERE provider=?", (prov,)).fetchone()
    print(prov, "health", row["state_json"] if row else None)
