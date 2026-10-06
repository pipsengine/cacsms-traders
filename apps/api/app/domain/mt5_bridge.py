"""Tenant-scoped, expiring read-only Windows bridge state. Never grants execution."""
import json
from datetime import datetime, timezone


def key(tenant_id, kind):
    return f'mt5.bridge.{kind}.{tenant_id}'


def read(conn, tenant_id, kind):
    row = conn.execute('SELECT value_json FROM system_settings WHERE key=?', (key(tenant_id, kind),)).fetchone()
    return json.loads(row['value_json']) if row else {}


def save(conn, tenant_id, kind, value):
    from ..core.security import iso
    conn.execute('INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at', (key(tenant_id, kind), json.dumps(value), iso()))


def status(conn, tenant_id):
    state = read(conn, tenant_id, 'state')
    if not state:
        return None
    credential = read(conn, tenant_id, 'credential')
    now = datetime.now(timezone.utc)
    fresh = bool(credential.get('hash') and state.get('generation') == credential.get('generation') and
                 datetime.fromisoformat(credential['expires_at']) > now and
                 (now - datetime.fromisoformat(state['received_at'])).total_seconds() <= 90)
    return {**state, 'connected': fresh and state.get('connected', False)}


def gateway(state, tenant_id):
    connected = bool(state['connected'])
    return dict(status='CONNECTED' if connected else 'DISCONNECTED', session_status='CONNECTED' if connected else 'DISCONNECTED',
                adapter='WINDOWS_MT5_BRIDGE', tenant_id=tenant_id, terminal=state['terminal_path'], terminal_configured=True,
                terminal_path_detected=state['terminal_path'], heartbeat_at=state['received_at'], last_connected_at=state['received_at'],
                last_error=None if connected else 'Windows bridge heartbeat expired or disconnected.',
                market_data_connected=connected, execution_enabled=False, execution='Disabled',
                message='Windows bridge connected' if connected else 'Windows bridge disconnected',
                terminal_account={**state['account'], 'available': connected})


def sync_registry(conn, tenant_id, state):
    """Import the attached account without changing trading flags or execution binding."""
    import uuid
    from ..core.security import iso
    account = state['account']
    stamp = iso()
    row = conn.execute('SELECT id FROM trading_accounts WHERE tenant_id=? AND account_number=? AND server=?', (tenant_id, account['login'], account['server'])).fetchone()
    aid = row['id'] if row else str(uuid.uuid4())
    if not row:
        conn.execute('INSERT INTO trading_accounts(id,tenant_id,account_name,account_number,broker,server,environment,account_currency,balance,equity,free_margin,leverage,status,connection_type,connection_status,trading_enabled,autonomous_trading_enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                     (aid,tenant_id,f"MT5 {account['login']}",account['login'],account['company'],account['server'],account['trade_mode'],account['currency'],account['balance'],account['equity'],account['free_margin'],str(account['leverage']),'ACTIVE','LOCAL_MT5','CONNECTED',0,0,stamp,stamp))
        conn.execute('INSERT INTO account_risk_profiles(id,tenant_id,trading_account_id,created_at,updated_at) VALUES(?,?,?,?,?)', (str(uuid.uuid4()),tenant_id,aid,stamp,stamp))
    conn.execute("UPDATE trading_accounts SET balance=?,equity=?,free_margin=?,margin=?,last_synced_at=?,updated_at=?,connection_status='CONNECTED' WHERE id=?", (account['balance'],account['equity'],account['free_margin'],account['margin'],stamp,stamp,aid))
    existing = conn.execute('SELECT id FROM trading_connections WHERE tenant_id=? AND trading_account_id=?', (tenant_id,aid)).fetchone()
    if not existing:
        conn.execute('INSERT INTO trading_connections(id,tenant_id,trading_account_id,adapter_type,terminal_path,server_name,status,last_heartbeat_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)', (str(uuid.uuid4()),tenant_id,aid,'LOCAL_MT5',state['terminal_path'],account['server'],'CONNECTED',stamp,stamp,stamp))
    else:
        conn.execute("UPDATE trading_connections SET status='CONNECTED',last_error=NULL,last_heartbeat_at=?,updated_at=? WHERE id=?", (stamp,stamp,existing['id']))
    return aid
