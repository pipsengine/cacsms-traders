import json
from apps.api.app.core.database import db
from apps.api.app.domain.mt5_connection import read_terminal_account_for_tenant
from apps.api.app.services.trading_account_sync import sync_trading_account_from_terminal

with db() as conn:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()
    mode = json.loads(row[0]) if row else None
    print("mode", mode)
    t = read_terminal_account_for_tenant(conn, "tenant-cacsms", force_attach=True)
    print("terminal", t.get("login") if t else None, t.get("equity") if t else None)
    if t and t.get("available"):
        aid = sync_trading_account_from_terminal(conn, "tenant-cacsms", t)
        conn.commit()
        print("synced account id", aid)
    print("accounts", conn.execute("SELECT id, account_number, environment FROM trading_accounts").fetchall())
    print("live", conn.execute("SELECT live_trading_enabled FROM account_risk_profiles").fetchall())
