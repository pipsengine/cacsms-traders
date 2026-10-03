from fastapi import APIRouter,Depends,HTTPException
import uuid
from ..deps import current_user
from ..core.database import db
from ..core.security import iso,hash_password
from ..core.audit import write_audit
from ..services.access import require_permission
from ..schemas.admin import UserCreate,UserPatch,AccountCreate,AccountPatch,ConnectionCreate
from ..schemas.mt5 import Mt5ConnectRequest, Mt5SettingsPatch
from ..domain.gateway import LocalMT5Gateway
from ..domain.mt5_diagnostics import mt5_python_package_status
router=APIRouter(prefix='/tenants/{tenant_id}',tags=['Tenant Administration'])
@router.get('/users')
def users(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'users.read'); return [dict(r) for r in c.execute("""SELECT u.id,u.username,u.email,u.first_name,u.middle_name,u.last_name,u.display_name,u.phone,u.timezone,u.preferred_currency,u.status,u.last_login_at,r.name role_name FROM tenant_memberships m JOIN users u ON u.id=m.user_id LEFT JOIN roles r ON r.id=m.role_id WHERE m.tenant_id=? ORDER BY u.display_name""",(tenant_id,))]
@router.post('/users')
def add_user(tenant_id:str,x:UserCreate,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'users.manage'); uid=str(uuid.uuid4()); now=iso(); display=' '.join(filter(None,[x.first_name,x.middle_name,x.last_name])); c.execute("""INSERT INTO users(id,username,email,password_hash,first_name,middle_name,last_name,display_name,timezone,preferred_currency,status,is_platform_admin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid,x.username,x.email,hash_password(x.password),x.first_name,x.middle_name,x.last_name,display,'Africa/Lagos','USD','ACTIVE',0,now,now)); c.execute('INSERT INTO tenant_memberships(id,tenant_id,user_id,role_id,status,created_at) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),tenant_id,uid,x.role_id,'ACTIVE',now)); write_audit(c,tenant_id,user['id'],'USER_CREATED','User',uid,after={'username':x.username,'display_name':display})
 return {'id':uid}
@router.get('/roles')
def roles(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'users.read'); return [dict(r) for r in c.execute('SELECT * FROM roles WHERE tenant_id=? ORDER BY name',(tenant_id,))]
@router.get('/accounts')
def accounts(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'accounts.read'); return [dict(r) for r in c.execute('SELECT * FROM trading_accounts WHERE tenant_id=? ORDER BY created_at DESC',(tenant_id,))]
@router.post('/accounts')
def add_account(tenant_id:str,x:AccountCreate,user=Depends(current_user)):
 if x.environment not in {'DEMO','LIVE','PROP_FIRM'}: raise HTTPException(400,'Invalid environment')
 aid=str(uuid.uuid4()); now=iso()
 with db() as c:
  require_permission(c,user,tenant_id,'accounts.manage'); c.execute("""INSERT INTO trading_accounts(id,tenant_id,account_name,account_number,broker,server,environment,account_currency,balance,equity,free_margin,leverage,status,connection_type,connection_status,trading_enabled,autonomous_trading_enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(aid,tenant_id,x.account_name,x.account_number,x.broker,x.server,x.environment,x.account_currency,0,0,0,x.leverage,'ACTIVE','LOCAL_MT5','DISCONNECTED',0,0,now,now)); c.execute('INSERT INTO account_risk_profiles(id,tenant_id,trading_account_id,created_at,updated_at) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),tenant_id,aid,now,now)); write_audit(c,tenant_id,user['id'],'TRADING_ACCOUNT_CREATED','TradingAccount',aid,after=x.model_dump())
 return {'id':aid}
@router.patch('/accounts/{account_id}')
def patch_account(tenant_id:str,account_id:str,x:AccountPatch,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'accounts.manage'); old=c.execute('SELECT * FROM trading_accounts WHERE id=? AND tenant_id=?',(account_id,tenant_id)).fetchone();
  if not old: raise HTTPException(404,'Account not found')
  vals=x.model_dump(exclude_none=True)
  if ('trading_enabled' in vals or 'autonomous_trading_enabled' in vals) and old['environment']=='LIVE': require_permission(c,user,tenant_id,'accounts.enable_live')
  for k,v in vals.items(): c.execute(f'UPDATE trading_accounts SET {k}=?,updated_at=? WHERE id=?',(int(v) if isinstance(v,bool) else v,iso(),account_id))
  new=dict(c.execute('SELECT * FROM trading_accounts WHERE id=?',(account_id,)).fetchone()); write_audit(c,tenant_id,user['id'],'TRADING_ACCOUNT_UPDATED','TradingAccount',account_id,before=dict(old),after=new)
 return new
@router.get('/connections')
def connections(tenant_id:str,user=Depends(current_user)):
 gw_svc=LocalMT5Gateway()
 with db() as c:
  require_permission(c,user,tenant_id,'connections.read')
  rows=c.execute("""SELECT c.*,a.account_name,a.account_number,a.environment,a.server AS account_server
   FROM trading_connections c JOIN trading_accounts a ON a.id=c.trading_account_id
   WHERE c.tenant_id=? ORDER BY c.updated_at DESC""",(tenant_id,)).fetchall()
  return {
   'gateway':gw_svc.health(),
   'settings':gw_svc.settings(),
   'connections':[dict(r) for r in rows],
   'diagnostics':mt5_python_package_status(),
  }
@router.patch('/connections/settings')
def patch_connection_settings(tenant_id:str,x:Mt5SettingsPatch,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway()
  updated=gw.patch_settings(x.model_dump(exclude_none=True), conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_SETTINGS_UPDATED','System','mt5.local',after=updated)
  return {'settings':updated,'gateway':gw.health(conn=c)}
@router.post('/connections/gateway/connect')
def gateway_connect(tenant_id:str,x:Mt5ConnectRequest,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway()
  result=gw.connect(x.terminal_path, conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_CONNECT','System','mt5.local',after={'ok':result.get('ok'),'error':result.get('error')})
  return result
@router.post('/connections/gateway/disconnect')
def gateway_disconnect(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway()
  result=gw.disconnect(conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_DISCONNECT','System','mt5.local',after={'ok':True})
  return result
@router.post('/connections/gateway/restart')
def gateway_restart(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway()
  result=gw.restart(conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_RESTART','System','mt5.local',after={'ok':result.get('ok'),'error':result.get('error')})
  return result
@router.post('/connections')
def add_connection(tenant_id:str,x:ConnectionCreate,user=Depends(current_user)):
 if x.adapter_type not in {'LOCAL_MT5','REMOTE_MT5','BROKER_GATEWAY'}: raise HTTPException(400,'Invalid adapter type')
 cid=str(uuid.uuid4()); now=iso()
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  ac=c.execute('SELECT id FROM trading_accounts WHERE id=? AND tenant_id=?',(x.trading_account_id,tenant_id)).fetchone()
  if not ac: raise HTTPException(404,'Trading account not found')
  c.execute("""INSERT INTO trading_connections(id,tenant_id,trading_account_id,adapter_type,terminal_path,server_name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",(cid,tenant_id,x.trading_account_id,x.adapter_type,x.terminal_path,x.server_name,'DISCONNECTED',now,now))
  c.execute("UPDATE trading_accounts SET connection_type=?,connection_status=?,updated_at=? WHERE id=?",(x.adapter_type,'DISCONNECTED',now,x.trading_account_id))
  write_audit(c,tenant_id,user['id'],'CONNECTION_CONFIGURED','TradingConnection',cid,after=x.model_dump())
 return {'id':cid,'status':'DISCONNECTED'}
@router.get('/audit')
def audit(tenant_id:str,limit:int=100,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'audit.read'); return [dict(r) for r in c.execute('SELECT * FROM audit_events WHERE tenant_id=? OR tenant_id IS NULL ORDER BY created_at DESC LIMIT ?', (tenant_id,min(limit,500)))]
