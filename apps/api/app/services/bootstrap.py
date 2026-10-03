from pathlib import Path
import os
import uuid
from ..core.database import db
from ..core.config import ROOT,BOOTSTRAP_USERNAME,BOOTSTRAP_PASSWORD,BOOTSTRAP_EMAIL
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


def apply_migrations():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
  for p in sorted((ROOT/'database/migrations').glob('*.sql')):
   if not c.execute('SELECT 1 FROM schema_migrations WHERE version=?',(p.name,)).fetchone():
    c.executescript(p.read_text(encoding='utf-8')); c.execute('INSERT INTO schema_migrations VALUES(?,?)',(p.name,iso()))
def bootstrap():
 apply_migrations(); now=iso()
 path=db_path()
 with db() as c:
  removed=remove_demo_mock_accounts(c)
  if removed:
   print(f"[bootstrap] Removed {removed} placeholder demo account(s) from {path}")
  tid='tenant-cacsms'; rid='role-platform-admin'; uid='user-cacsms'
  c.execute("INSERT OR IGNORE INTO tenants(id,name,slug,status,reporting_currency,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(tid,'Cacsms','cacsms','ACTIVE','USD',now,now))
  for code,desc in PERMISSIONS.items(): c.execute('INSERT OR IGNORE INTO permissions(id,code,description) VALUES(?,?,?)',(f'perm-{code}',code,desc))
  c.execute('INSERT OR IGNORE INTO roles(id,tenant_id,name,description,created_at) VALUES(?,?,?,?,?)',(rid,tid,'Platform Administrator','Full foundation administration',now))
  for code in PERMISSIONS: c.execute('INSERT OR IGNORE INTO role_permissions(role_id,permission_id) VALUES(?,?)',(rid,f'perm-{code}'))
  if not c.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():
   bootstrap_pw=os.getenv('BOOTSTRAP_PASSWORD',BOOTSTRAP_PASSWORD)
   c.execute("""INSERT INTO users(id,username,email,password_hash,first_name,last_name,display_name,timezone,preferred_currency,status,is_platform_admin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid,BOOTSTRAP_USERNAME,BOOTSTRAP_EMAIL,hash_password(bootstrap_pw),'Cacsms','Administrator','Cacsms Administrator','Africa/Lagos','USD','ACTIVE',1,now,now))
  c.execute('INSERT OR IGNORE INTO tenant_memberships(id,tenant_id,user_id,role_id,status,created_at) VALUES(?,?,?,?,?,?)',('membership-cacsms',tid,uid,rid,'ACTIVE',now))
  ensure_super_admin(c, tid, now, list(PERMISSIONS.keys()))
  c.execute("INSERT OR IGNORE INTO system_settings(key,value_json,updated_at) VALUES('system.mode',?,?)",('\"ANALYSIS_ONLY\"',now))
  c.execute("INSERT OR IGNORE INTO system_settings(key,value_json,updated_at) VALUES('mt5.local',?,?)",('{\"terminal_path\":\"\",\"login_type\":\"\",\"auto_reconnect\":true,\"heartbeat_interval_seconds\":30}',now))
  clear_stale_mt5_package_errors_all_tenants(c)
