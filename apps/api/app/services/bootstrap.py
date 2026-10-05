from pathlib import Path
import os
from ..core.database import db, database_url
from ..core.config import ROOT,BOOTSTRAP_USERNAME,BOOTSTRAP_PASSWORD,BOOTSTRAP_EMAIL, app_env
from ..core.security import hash_password,iso
from ..core.permissions import PERMISSIONS
from .super_admin import ensure_super_admin
from ..core.database import db_path
from ..domain.mt5_connection import clear_stale_mt5_package_errors_all_tenants


_MOCK_ACCOUNT_NAMES = frozenset({"verify demo", "demo account", "test account"})


def _delete_trading_account(c, aid: str) -> None:
    c.execute("DELETE FROM trading_connections WHERE trading_account_id=?", (aid,))
    c.execute("DELETE FROM account_risk_profiles WHERE trading_account_id=?", (aid,))
    c.execute("DELETE FROM trading_accounts WHERE id=?", (aid,))


def remove_demo_mock_accounts(c) -> int:
    """Remove placeholder demo registry accounts (e.g. Verify Demo) so real MT5 can be linked."""
    rows = c.execute("SELECT id, account_name, account_number FROM trading_accounts").fetchall()
    removed = 0
    for row in rows:
        name = (row["account_name"] or "").strip().lower()
        if name not in _MOCK_ACCOUNT_NAMES:
            continue
        _delete_trading_account(c, row["id"])
        removed += 1
    return removed


def _migration_dir():
    if app_env() == 'production':
        return ROOT / 'database' / 'migrations' / 'postgres'
    return ROOT / 'database' / 'migrations'


def apply_migrations():
    migration_dir = _migration_dir()
    if not migration_dir.exists():
        raise FileNotFoundError(f'Migration directory not found: {migration_dir}')
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
        if app_env() == 'production' and database_url():
            c.execute("SELECT pg_advisory_lock(hashtext('cacsms-bootstrap-migrations'))")
            try:
                for p in sorted(migration_dir.glob('*.sql')):
                    if not c.execute('SELECT 1 FROM schema_migrations WHERE version=?', (p.name,)).fetchone():
                        c.executescript(p.read_text(encoding='utf-8'))
                        c.execute('INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)', (p.name, iso()))
            finally:
                c.execute("SELECT pg_advisory_unlock(hashtext('cacsms-bootstrap-migrations'))")
            return
        for p in sorted(migration_dir.glob('*.sql')):
            if not c.execute('SELECT 1 FROM schema_migrations WHERE version=?', (p.name,)).fetchone():
                c.executescript(p.read_text(encoding='utf-8'))
                c.execute('INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)', (p.name, iso()))
def bootstrap():
    apply_migrations()
    now = iso()
    path = db_path()
    with db() as c:
        removed = remove_demo_mock_accounts(c)
        if removed:
            print(f"[bootstrap] Removed {removed} placeholder demo account(s) from {path}")

        tenant_id = 'tenant-cacsms'
        role_id = 'role-platform-admin'
        user_id = 'user-cacsms'

        c.execute(
            "INSERT INTO tenants(id,name,slug,status,reporting_currency,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
            (tenant_id, 'Cacsms', 'cacsms', 'ACTIVE', 'USD', now, now),
        )
        for code, description in PERMISSIONS.items():
            c.execute(
                'INSERT INTO permissions(id,code,description) VALUES(?,?,?) ON CONFLICT (id) DO NOTHING',
                (f'perm-{code}', code, description),
            )
        c.execute(
            'INSERT INTO roles(id,tenant_id,name,description,created_at) VALUES(?,?,?,?,?) ON CONFLICT (id) DO NOTHING',
            (role_id, tenant_id, 'Platform Administrator', 'Full foundation administration', now),
        )
        for code in PERMISSIONS:
            c.execute(
                'INSERT INTO role_permissions(role_id,permission_id) VALUES(?,?) ON CONFLICT (role_id, permission_id) DO NOTHING',
                (role_id, f'perm-{code}'),
            )

        if not c.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
            bootstrap_password = os.getenv('BOOTSTRAP_PASSWORD', BOOTSTRAP_PASSWORD)
            c.execute(
                """INSERT INTO users(id,username,email,password_hash,first_name,last_name,display_name,timezone,preferred_currency,status,is_platform_admin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (user_id, BOOTSTRAP_USERNAME, BOOTSTRAP_EMAIL, hash_password(bootstrap_password), 'Cacsms', 'Administrator', 'Cacsms Administrator', 'Africa/Lagos', 'USD', 'ACTIVE', 1, now, now),
            )
        c.execute(
            'INSERT INTO tenant_memberships(id,tenant_id,user_id,role_id,status,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING',
            ('membership-cacsms', tenant_id, user_id, role_id, 'ACTIVE', now),
        )
        ensure_super_admin(c, tenant_id, now, list(PERMISSIONS.keys()))
        c.execute(
            "INSERT INTO system_settings(key,value_json,updated_at) VALUES('system.mode',?,?) ON CONFLICT (key) DO NOTHING",
            ('"ANALYSIS_ONLY"', now),
        )
        c.execute(
            "INSERT INTO system_settings(key,value_json,updated_at) VALUES('mt5.local',?,?) ON CONFLICT (key) DO NOTHING",
            ('{"terminal_path":"","login_type":"","auto_reconnect":true,"heartbeat_interval_seconds":30}', now),
        )
        clear_stale_mt5_package_errors_all_tenants(c)
