from fastapi import APIRouter,Depends,HTTPException
import uuid
from ..deps import current_user
from ..core.database import db, db_path
from ..core.security import iso,hash_password
from ..core.audit import write_audit
from ..services.access import require_permission
from ..services.bootstrap import remove_demo_mock_accounts
from ..schemas.admin import UserCreate,UserPatch,AccountCreate,AccountPatch,ConnectionCreate
from ..schemas.mt5 import Mt5ConnectRequest, Mt5SettingsPatch
from ..domain.gateway import LocalMT5Gateway
from ..domain.mt5_diagnostics import mt5_python_package_status
from ..domain.mt5_terminal_launcher import terminal_launch_capability
from ..market import mt5_session
from ..domain.mt5_connection import (
    connection_in_progress,
    ensure_autodetected_terminal_path,
    ensure_gateway_session,
    read_terminal_account_for_tenant,
    sync_trading_registry_from_terminal,
)
from ..domain.mt5_lifecycle import compute_connection_lifecycle
from ..domain.mt5_terminal_account import environment_from_terminal, read_terminal_account
from ..domain.mt5_terminal_discovery import filesystem_terminal_candidates, running_terminal64_processes
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
  require_permission(c,user,tenant_id,'accounts.read')
  return [dict(r) for r in c.execute('SELECT * FROM trading_accounts WHERE tenant_id=? ORDER BY created_at DESC',(tenant_id,))]
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
 gw_svc=LocalMT5Gateway(tenant_id)
 with db() as c:
  require_permission(c,user,tenant_id,'connections.read')
  settings=gw_svc.settings(conn=c)
  session=settings.get('session_status')
  reconnect = None
  if session == 'CONNECTED' and not mt5_session.is_initialized() and not connection_in_progress(tenant_id):
   reconnect = ensure_gateway_session(c, tenant_id)
  auto_meta=ensure_autodetected_terminal_path(
   c, tenant_id, allow_probe=False, persist=False,
  )
  rows=c.execute("""SELECT c.id,c.tenant_id,c.trading_account_id,c.adapter_type,c.terminal_path,c.server_name,c.status,
   c.last_heartbeat_at,c.last_error,c.created_at,c.updated_at,
   a.account_name,a.account_number,a.environment,a.server AS account_server,a.broker,a.account_currency
   FROM trading_connections c JOIN trading_accounts a ON a.id=c.trading_account_id
   WHERE c.tenant_id=? ORDER BY c.updated_at DESC""",(tenant_id,)).fetchall()
  connection_rows=[dict(r) for r in rows]
  from ..domain.mt5_bridge import status as bridge_status, gateway as bridge_gateway
  bridge=bridge_status(c,tenant_id)
  if bridge:
   settings={**settings,'session_status':'CONNECTED' if bridge['connected'] else 'DISCONNECTED','terminal_path':bridge['terminal_path'],'last_heartbeat_at':bridge['received_at'],'last_error':None if bridge['connected'] else 'Windows bridge heartbeat expired.'}
   return {'gateway':bridge_gateway(bridge,tenant_id),'settings':settings,'connections':connection_rows,'diagnostics':{'python_package':'remote','terminal_launch_mode':'WINDOWS_GATEWAY_REQUIRED','terminal_launch_supported':False,'bridge_connected':bridge['connected'],'terminal_account':{**bridge['account'],'available':bridge['connected']}}}
  live=mt5_session.is_initialized()
  terminal_account=read_terminal_account_for_tenant(
   c, tenant_id, force_attach=False, persist_snapshot=live,
  )
  gateway=gw_svc.health(conn=c, allow_reconnect=False)
  diag_reconnect = reconnect if reconnect and reconnect.get('restored') else None
  from ..domain.mt5_terminal_launcher import terminal_launch_capability
  diag={**mt5_python_package_status(),**terminal_launch_capability()}
  diag['database_path']=str(db_path())
  diag['terminal_candidates']=filesystem_terminal_candidates()[:8]
  diag['terminal_running_processes']=running_terminal64_processes()
  if auto_meta.get('path'):
   diag['terminal_auto_detect_path']=auto_meta['path']
   diag['terminal_auto_detect_source']=auto_meta.get('source')
  diag['terminal_auto_saved']=auto_meta
  diag['terminal_account']=terminal_account
  if diag_reconnect:
   diag['gateway_reconnect']=diag_reconnect
  if not (terminal_account and terminal_account.get('available')):
   diag['terminal_account_hint']='Open MetaTrader 5, log in, then use Connect or Sync from MT5.'
  from ..market.market_data import configuration
  from ..market.strength_engine import get_strength_engine
  cfg=configuration(c)
  scope_tid=(cfg.get('tenant_id') or cfg.get('mt5_tenant_id') or '').strip()
  intelligence=get_strength_engine().engine_meta() if scope_tid == tenant_id else None
  lifecycle=compute_connection_lifecycle(
   gateway, settings, intelligence, connect_in_progress=connection_in_progress(tenant_id),
  )
  return {
   'gateway':{**gateway, **lifecycle},
   'settings':settings,
   'connections':connection_rows,
   'diagnostics':diag,
   'lifecycle':lifecycle,
   'intelligence':intelligence,
  }
@router.patch('/connections/settings')
def patch_connection_settings(tenant_id:str,x:Mt5SettingsPatch,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway(tenant_id)
  updated=gw.patch_settings(x.model_dump(exclude_none=True), conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_SETTINGS_UPDATED','TenantSettings',f'{tenant_id}/mt5.local',after=updated)
  return {'settings':updated,'gateway':gw.health(conn=c)}
@router.post('/connections/gateway/connect')
def gateway_connect(tenant_id:str,x:Mt5ConnectRequest,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway(tenant_id)
  result=gw.connect(x.terminal_path, conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_CONNECT','TenantSettings',f'{tenant_id}/mt5.local',after={'ok':result.get('ok'),'error':result.get('error'),'terminal_launch':result.get('terminal_launch')})
  return result
@router.post('/connections/gateway/disconnect')
def gateway_disconnect(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway(tenant_id)
  result=gw.disconnect(conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_DISCONNECT','TenantSettings',f'{tenant_id}/mt5.local',after={'ok':True})
  return result
@router.post('/connections/gateway/restart')
def gateway_restart(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  gw=LocalMT5Gateway(tenant_id)
  result=gw.restart(conn=c)
  write_audit(c,tenant_id,user['id'],'MT5_RESTART','TenantSettings',f'{tenant_id}/mt5.local',after={'ok':result.get('ok'),'error':result.get('error')})
  return result
@router.delete('/connections/{connection_id}')
def delete_connection(tenant_id:str,connection_id:str,delete_account:bool=False,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  row=c.execute(
   'SELECT c.id,c.trading_account_id FROM trading_connections c WHERE c.id=? AND c.tenant_id=?',
   (connection_id,tenant_id),
  ).fetchone()
  if not row: raise HTTPException(404,'Connection not found')
  aid=row['trading_account_id']
  c.execute('DELETE FROM trading_connections WHERE id=?',(connection_id,))
  if delete_account:
   c.execute('DELETE FROM account_risk_profiles WHERE trading_account_id=?',(aid,))
   c.execute('DELETE FROM trading_accounts WHERE id=? AND tenant_id=?',(aid,tenant_id))
  else:
   c.execute("UPDATE trading_accounts SET connection_status='DISCONNECTED',updated_at=? WHERE id=?",(iso(),aid))
  write_audit(c,tenant_id,user['id'],'CONNECTION_REMOVED','TradingConnection',connection_id,after={'delete_account':delete_account})
  return {'ok':True,'deleted_connection_id':connection_id}
@router.post('/connections/cleanup-placeholders')
def cleanup_placeholder_accounts(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  removed=remove_demo_mock_accounts(c)
  rows=c.execute("""SELECT c.id,c.tenant_id,c.trading_account_id,c.adapter_type,c.terminal_path,c.server_name,c.status,c.created_at,c.updated_at,
   a.account_name,a.account_number,a.environment,a.server AS account_server,a.broker,a.account_currency
   FROM trading_connections c JOIN trading_accounts a ON a.id=c.trading_account_id
   WHERE c.tenant_id=? ORDER BY c.updated_at DESC""",(tenant_id,)).fetchall()
  write_audit(c,tenant_id,user['id'],'MT5_CLEANUP_PLACEHOLDERS','TenantSettings',tenant_id,after={'removed':removed})
  return {'ok':True,'removed':removed,'connections':[dict(r) for r in rows]}
@router.post('/connections')
def add_connection(tenant_id:str,x:ConnectionCreate,user=Depends(current_user)):
 if x.adapter_type not in {'LOCAL_MT5','REMOTE_MT5','BROKER_GATEWAY'}: raise HTTPException(400,'Invalid adapter type')
 cid=str(uuid.uuid4()); now=iso()
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  ac=c.execute('SELECT id FROM trading_accounts WHERE id=? AND tenant_id=?',(x.trading_account_id,tenant_id)).fetchone()
  if not ac: raise HTTPException(404,'Trading account not found')
  dup=c.execute('SELECT id FROM trading_connections WHERE tenant_id=? AND trading_account_id=?',(tenant_id,x.trading_account_id)).fetchone()
  if dup: raise HTTPException(409,'This trading account is already linked in the registry.')
  gw=LocalMT5Gateway(tenant_id)
  tenant_terminal=(gw.settings(conn=c).get('terminal_path') or '').strip() or None
  terminal_path=x.terminal_path or tenant_terminal
  gw_session=(gw.settings(conn=c).get('session_status') or 'DISCONNECTED')
  terminal_account=read_terminal_account() if gw_session == 'CONNECTED' else None
  server_name=(x.server_name or '').strip() or None
  if not server_name and terminal_account and terminal_account.get('available'):
    server_name=terminal_account.get('server') or None
  link_status='CONNECTED' if gw_session == 'CONNECTED' and terminal_account and terminal_account.get('available') else 'DISCONNECTED'
  c.execute("""INSERT INTO trading_connections(id,tenant_id,trading_account_id,adapter_type,terminal_path,server_name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",(cid,tenant_id,x.trading_account_id,x.adapter_type,terminal_path,server_name,link_status,now,now))
  c.execute("UPDATE trading_accounts SET connection_type=?,connection_status=?,updated_at=? WHERE id=?",(x.adapter_type,link_status,now,x.trading_account_id))
  if terminal_account and terminal_account.get('available'):
    login=(terminal_account.get('login') or '').strip()
    env=environment_from_terminal(terminal_account.get('trade_mode') or 'DEMO')
    c.execute(
     """UPDATE trading_accounts SET account_number=?,server=?,environment=?,broker=COALESCE(NULLIF(broker,''),?),
        balance=?,equity=?,margin=?,free_margin=?,last_synced_at=?,updated_at=? WHERE id=?""",
     (
      login,
      server_name or terminal_account.get('server'),
      env,
      terminal_account.get('company') or 'MT5',
      float(terminal_account.get('balance') or 0),
      float(terminal_account.get('equity') or 0),
      float(terminal_account.get('margin') or 0),
      float(terminal_account.get('free_margin') or 0),
      now,
      now,
      x.trading_account_id,
     ),
    )
  write_audit(c,tenant_id,user['id'],'CONNECTION_CONFIGURED','TradingConnection',cid,after=x.model_dump())
 return {'id':cid,'status':link_status,'terminal_account':terminal_account}
@router.post('/connections/auto-link-terminal')
def auto_link_terminal_account(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  from ..domain.mt5_bridge import status as bridge_status, sync_registry as bridge_sync
  bridge=bridge_status(c,tenant_id)
  if bridge and bridge['connected']:
   aid=bridge_sync(c,tenant_id,bridge)
   return {'ok':True,'trading_account_id':aid,'terminal_account':{**bridge['account'],'available':True}}
  gw=LocalMT5Gateway(tenant_id)
  ensure_gateway_session(c, tenant_id)
  terminal_account=read_terminal_account_for_tenant(c, tenant_id, force_attach=True)
  if not terminal_account or not terminal_account.get('available'):
    detail=terminal_account.get('error') if terminal_account else 'No terminal account data.'
    raise HTTPException(400,detail or 'Could not read MT5 account.')
  login=(terminal_account.get('login') or '').strip()
  server=(terminal_account.get('server') or '').strip()
  env=environment_from_terminal(terminal_account.get('trade_mode') or 'DEMO')
  now=iso()
  tenant_terminal=(gw.settings(conn=c).get('terminal_path') or '').strip() or None
  row=c.execute(
   'SELECT id FROM trading_accounts WHERE tenant_id=? AND TRIM(COALESCE(account_number,""))=?',
   (tenant_id,login),
  ).fetchone()
  trading_account_id=row['id'] if row else None
  if not trading_account_id:
    aid=str(uuid.uuid4())
    name=(terminal_account.get('name') or f'MT5 {login}').strip()
    c.execute(
     """INSERT INTO trading_accounts(id,tenant_id,account_name,account_number,broker,server,environment,account_currency,balance,equity,free_margin,leverage,status,connection_type,connection_status,trading_enabled,autonomous_trading_enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
     (aid,tenant_id,name,login,terminal_account.get('company') or 'MT5',server,env,terminal_account.get('currency') or 'USD',float(terminal_account.get('balance') or 0),float(terminal_account.get('equity') or 0),float(terminal_account.get('free_margin') or 0),str(terminal_account.get('leverage') or ''),'ACTIVE','LOCAL_MT5','CONNECTED',0,0,now,now),
    )
    c.execute('INSERT INTO account_risk_profiles(id,tenant_id,trading_account_id,created_at,updated_at) VALUES(?,?,?,?,?)',(str(uuid.uuid4()),tenant_id,aid,now,now))
    trading_account_id=aid
  else:
    c.execute('UPDATE trading_accounts SET account_number=?,server=?,environment=?,updated_at=? WHERE id=?',(login,server,env,now,trading_account_id))
  existing=c.execute('SELECT id FROM trading_connections WHERE tenant_id=? AND trading_account_id=?',(tenant_id,trading_account_id)).fetchone()
  if existing:
    cid=existing['id']
    c.execute('UPDATE trading_connections SET terminal_path=?,server_name=?,status=?,updated_at=? WHERE id=?',(tenant_terminal,server,'CONNECTED',now,cid))
  else:
    cid=str(uuid.uuid4())
    c.execute("""INSERT INTO trading_connections(id,tenant_id,trading_account_id,adapter_type,terminal_path,server_name,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",(cid,tenant_id,trading_account_id,'LOCAL_MT5',tenant_terminal,server,'CONNECTED',now,now))
  c.execute("UPDATE trading_accounts SET connection_type=?,connection_status=?,updated_at=? WHERE id=?",('LOCAL_MT5','CONNECTED',now,trading_account_id))
  sync_trading_registry_from_terminal(c, tenant_id)
  write_audit(c,tenant_id,user['id'],'MT5_AUTO_LINK','TradingConnection',cid,after={'login':login,'server':server})
  rows=c.execute("""SELECT c.id,c.tenant_id,c.trading_account_id,c.adapter_type,c.terminal_path,c.server_name,c.status,c.created_at,c.updated_at,
   a.account_name,a.account_number,a.environment,a.server AS account_server,a.broker,a.account_currency
   FROM trading_connections c JOIN trading_accounts a ON a.id=c.trading_account_id WHERE c.id=?""",(cid,)).fetchone()
  return {'ok':True,'connection':dict(rows) if rows else {'id':cid},'terminal_account':terminal_account}
@router.post('/connections/sync-registry')
def sync_connection_registry(tenant_id:str,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'connections.manage')
  from ..domain.mt5_bridge import status as bridge_status, sync_registry as bridge_sync
  bridge=bridge_status(c,tenant_id)
  if bridge and bridge['connected']:
    bridge_sync(c,tenant_id,bridge)
    result={'synced':True}
  else:
    if not terminal_launch_capability()['terminal_launch_supported']:
      raise HTTPException(409, 'MT5 registry sync requires a connected Windows market-data bridge. Use Connect first.')
    ensure_gateway_session(c, tenant_id)
    result=sync_trading_registry_from_terminal(c, tenant_id, force_attach=True)
  if not result.get('synced'):
    msg=result.get('error') or result.get('reason') or 'Registry sync failed.'
    raise HTTPException(400, f'{msg} Open IC Markets MT5, log in, then retry Sync from MT5.')
  rows=c.execute("""SELECT c.id,c.tenant_id,c.trading_account_id,c.adapter_type,c.terminal_path,c.server_name,c.status,c.created_at,c.updated_at,
   a.account_name,a.account_number,a.environment,a.server AS account_server,a.broker,a.account_currency
   FROM trading_connections c JOIN trading_accounts a ON a.id=c.trading_account_id
   WHERE c.tenant_id=? ORDER BY c.updated_at DESC""",(tenant_id,)).fetchall()
  return {'ok':True,'sync':result,'connections':[dict(r) for r in rows]}
@router.get('/audit')
def audit(tenant_id:str,limit:int=100,user=Depends(current_user)):
 with db() as c:
  require_permission(c,user,tenant_id,'audit.read'); return [dict(r) for r in c.execute('SELECT * FROM audit_events WHERE tenant_id=? OR tenant_id IS NULL ORDER BY created_at DESC LIMIT ?', (tenant_id,min(limit,500)))]
