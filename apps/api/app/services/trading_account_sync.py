"""Ensure trading_accounts matches the MT5 terminal attached to this host."""
from __future__ import annotations

import uuid

from ..core.security import iso
from ..execution.baselines import touch_baseline


def sync_trading_account_from_terminal(conn, tenant_id: str, terminal: dict) -> str | None:
    """Create or refresh registry row + risk profile for the logged-in terminal. Returns account id."""
    if not tenant_id or not terminal or not terminal.get("available"):
        return None
    login = str(terminal.get("login") or "").strip()
    server = str(terminal.get("server") or "").strip()
    if not login or not server:
        return None
    stamp = iso()
    mode = str(terminal.get("trade_mode") or "LIVE").upper()
    environment = "LIVE" if mode == "LIVE" else "DEMO" if mode == "DEMO" else mode
    row = conn.execute(
        "SELECT id FROM trading_accounts WHERE tenant_id=? AND account_number=? AND server=?",
        (tenant_id, login, server),
    ).fetchone()
    aid = row["id"] if row else str(uuid.uuid4())
    if not row:
        conn.execute(
            """INSERT INTO trading_accounts(
                id, tenant_id, account_name, account_number, broker, server, environment, account_currency,
                balance, equity, free_margin, leverage, status, connection_type, connection_status,
                trading_enabled, autonomous_trading_enabled, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                aid, tenant_id, f"MT5 {login}", login, terminal.get("company") or "MT5", server, environment,
                terminal.get("currency") or "USD", terminal.get("balance"), terminal.get("equity"),
                terminal.get("free_margin"), str(terminal.get("leverage") or ""), "ACTIVE", "LOCAL_MT5", "CONNECTED",
                1, 1, stamp, stamp,
            ),
        )
        conn.execute(
            "INSERT INTO account_risk_profiles(id, tenant_id, trading_account_id, live_trading_enabled, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (str(uuid.uuid4()), tenant_id, aid, 1 if environment == "LIVE" else 0, stamp, stamp),
        )
    conn.execute(
        """UPDATE trading_accounts SET account_currency=?, balance=?, equity=?, free_margin=?, margin=?,
           margin_level=?, floating_pnl=?, leverage=?, connection_status='CONNECTED', trading_enabled=1,
           autonomous_trading_enabled=1, last_synced_at=?, updated_at=? WHERE id=?""",
        (
            terminal.get("currency"), terminal.get("balance"), terminal.get("equity"), terminal.get("free_margin"),
            terminal.get("margin"), terminal.get("margin_level"), terminal.get("profit"), str(terminal.get("leverage") or ""),
            stamp, stamp, aid,
        ),
    )
    prof = conn.execute("SELECT id, live_trading_enabled FROM account_risk_profiles WHERE trading_account_id=?", (aid,)).fetchone()
    if prof and environment == "LIVE" and not prof["live_trading_enabled"]:
        conn.execute(
            "UPDATE account_risk_profiles SET live_trading_enabled=1, updated_at=? WHERE trading_account_id=?",
            (stamp, aid),
        )
    touch_baseline(conn, tenant_id, aid, terminal.get("currency") or "USD", terminal.get("equity"), source="mt5")
    return aid
