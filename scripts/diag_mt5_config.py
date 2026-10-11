import sqlite3
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "database" / "db_cacsms-traders.db"
c = sqlite3.connect(p)
c.row_factory = sqlite3.Row

def count(t):
    try:
        return c.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
    except sqlite3.OperationalError:
        return None

for t in ("trading_connections", "trading_accounts", "tenant_settings", "platform_settings"):
    print(t, count(t))

try:
    for r in c.execute("SELECT * FROM trading_connections LIMIT 3").fetchall():
        print("connection", dict(r))
except sqlite3.OperationalError as e:
    print("connections err", e)

try:
    row = c.execute("SELECT value_json FROM system_settings WHERE key='market_data.provider'").fetchone()
    print("market_data.provider", row[0][:200] if row else None)
except sqlite3.OperationalError as e:
    print("system_settings err", e)

try:
    for r in c.execute("SELECT * FROM tenant_settings LIMIT 5").fetchall():
        print("tenant_settings", dict(r))
except sqlite3.OperationalError as e:
    print("tenant_settings err", e)

try:
    for r in c.execute("SELECT tenant_id, key, substr(value,1,120) v FROM tenant_settings WHERE key LIKE 'mt5%' OR key LIKE '%market%'").fetchall():
        print("tenant_setting", dict(r))
except sqlite3.OperationalError:
    pass

try:
    for r in c.execute("SELECT key, substr(value,1,120) v FROM platform_settings").fetchall():
        if "mt5" in (r[0] or "").lower() or "market" in (r[0] or "").lower():
            print("platform", r[0], r[1])
except sqlite3.OperationalError:
    pass

c.close()
