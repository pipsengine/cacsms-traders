from pathlib import Path
import os
import uuid
from ..core.database import db
from ..core.config import ROOT,BOOTSTRAP_USERNAME,BOOTSTRAP_PASSWORD,BOOTSTRAP_EMAIL
from ..core.security import hash_password,iso
from ..core.permissions import PERMISSIONS
from .super_admin import ensure_super_admin

def apply_migrations():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)')
  for p in sorted((ROOT/'database/migrations').glob('*.sql')):
   if not c.execute('SELECT 1 FROM schema_migrations WHERE version=?',(p.name,)).fetchone():
    c.executescript(p.read_text(encoding='utf-8')); c.execute('INSERT INTO schema_migrations VALUES(?,?)',(p.name,iso()))
def bootstrap():
 apply_migrations(); now=iso()
 with db() as c:
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
