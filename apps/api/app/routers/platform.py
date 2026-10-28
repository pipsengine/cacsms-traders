from fastapi import APIRouter,Depends,HTTPException,Request,Response
import logging,os,uuid,json
from ..core.config import app_env
from ..deps import current_user
from ..core.database import db
from ..core.security import iso
from ..core.audit import write_audit
from ..schemas.admin import TenantCreate,SystemModeUpdate
from ..domain.gateway import LocalMT5Gateway
from ..domain.mt5_connection import _active_tenant_id
log=logging.getLogger(__name__)
router=APIRouter(tags=['Platform'])
def _service_state(enabled:bool,running:bool)->str: return 'disabled' if not enabled else 'running' if running else 'stopped'
def autonomous_services(app)->dict:
 """Backend-resident engines (independent of any browser session): state only."""
 from ..market.scanner_engine import get_scanner_engine,scanner_enabled
 from ..market.strength_engine import get_strength_engine
 worker=getattr(app.state,'mi_worker',None)
 return {
  'strength_engine':_service_state(os.getenv('STRENGTH_ENGINE_ENABLED','1').strip() not in ('0','false','no'),get_strength_engine().running),
  'market_scanner':_service_state(scanner_enabled(),get_scanner_engine().running),
  'intelligence_worker':_service_state(worker is not None,bool(worker and worker.running)),
 }
@router.get('/health/live')
def liveness(request:Request,response:Response):
 """Liveness reports only that the HTTP application is serving requests."""
 return {'status':'ok','api':'reachable','environment':app_env(),'time':iso()}

@router.get('/health/ready')
def readiness(request:Request,response:Response):
 """Readiness endpoint: database and bootstrap dependencies must be ready for requests."""
 bootstrap=getattr(request.app.state,'database_bootstrap_status','not_started')
 database='unavailable'; auth='not_ready'; ok=False
 try:
  with db() as c:
   c.execute('SELECT 1').fetchone()
   database='reachable'
   if bootstrap == 'ready':
    ready=c.execute("SELECT 1 FROM users WHERE is_platform_admin=1 AND status='ACTIVE' LIMIT 1").fetchone()
    c.execute('SELECT 1 FROM auth_sessions LIMIT 1').fetchone()
    auth='ready' if ready else 'not_ready'
   ok = database == 'reachable' and bootstrap == 'ready' and auth == 'ready'
 except Exception as exc:
  log.warning('Health check database unavailable; error_type=%s',type(exc).__name__)
  database='unavailable'; auth='unavailable'; ok=False
 if not ok:
  response.status_code=503
 return {'status':'ok' if ok else 'degraded','api':'reachable','database':database,'bootstrap':bootstrap,'auth':auth,'environment':app_env(),'time':iso()}

@router.get('/health')
def health(request:Request,response:Response):
 """Public health summary for the cloud backend."""
 live = liveness(request, response)
 ready = readiness(request, response)
 try:
  services=autonomous_services(request.app)
 except Exception:
  services='unavailable'
 payload = {
  'status': 'ok' if live.get('status') == 'ok' and ready.get('status') == 'ok' else 'degraded',
  'api': live.get('api'),
  'database': ready.get('database'),
  'bootstrap': ready.get('bootstrap'),
  'auth': ready.get('auth'),
  'environment': app_env(),
  'autonomous_services': services,
  'time': iso(),
 }
 if payload['status'] != 'ok':
  response.status_code = 503
 return payload

@router.get('/system/health')
def system_health(user=Depends(current_user)):
 """Shell status. Saved session and engine memory only — a page load must not wait on the terminal."""
 with db() as c:
  c.execute('SELECT 1').fetchone()
  active=_active_tenant_id(c)
  settings=LocalMT5Gateway(active)._load_settings(c) if active else {}
  mode_row=c.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()
 mode='ANALYSIS_ONLY'
 if mode_row:
  try:
   mode=json.loads(mode_row['value_json'])
  except (TypeError, ValueError):
   mode='ANALYSIS_ONLY'
 session=settings.get('session_status') or 'DISCONNECTED'
 execution_disabled=mode in ('ANALYSIS_ONLY','PAUSED','EMERGENCY_STOP')
 from ..market.strength_engine import get_strength_engine
 meta=get_strength_engine().engine_meta() or {}
 mt5={
  'status':session if session in ('CONNECTED','CONNECTING','RECONNECTING','DISCONNECTED') else 'DISCONNECTED',
  'session_status':session,
  'adapter':'LOCAL_MT5',
  'message':settings.get('last_error') or 'Local MT5 adapter foundation installed.',
  'terminal_configured':bool((settings.get('terminal_path') or '').strip()),
  'heartbeat_at':settings.get('last_heartbeat_at'),
  'last_connected_at':settings.get('last_connected_at'),
  'last_error':settings.get('last_error'),
  'execution_enabled':not execution_disabled,
  'execution':'Disabled' if execution_disabled else 'Restricted',
  'market_data_connected':bool(meta.get('market_data_ready')),
 }
 return {
  'application':'Cacsms-Traders','api':'HEALTHY','database':'HEALTHY','mt5':mt5,
  'market_data':{
   'active_provider':meta.get('active_provider'),
   'provider_status':meta.get('provider_status') or 'UNKNOWN',
   'market_data_ready':meta.get('market_data_ready'),
   'engine_state':meta.get('engine_state'),
  },
 }
@router.get('/dashboard/summary')
def summary(user=Depends(current_user)):
 with db() as c:
  if user['is_platform_admin']:
   return {'tenants':c.execute('SELECT count(*) n FROM tenants').fetchone()['n'],'users':c.execute('SELECT count(*) n FROM users').fetchone()['n'],'accounts':c.execute('SELECT count(*) n FROM trading_accounts').fetchone()['n'],'connections':c.execute("SELECT count(*) n FROM trading_connections WHERE status='CONNECTED'").fetchone()['n'],'mode':json.loads(c.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()['value_json'])}
  return {'tenants':0,'users':0,'accounts':0,'connections':0,'mode':'ANALYSIS_ONLY'}
@router.get('/tenants')
def tenants(user=Depends(current_user)):
 with db() as c:
  rows=c.execute('SELECT * FROM tenants ORDER BY name').fetchall() if user['is_platform_admin'] else c.execute('SELECT t.* FROM tenants t JOIN tenant_memberships m ON m.tenant_id=t.id WHERE m.user_id=?',(user['id'],)).fetchall()
  return [dict(r) for r in rows]
@router.post('/tenants')
def create_tenant(x:TenantCreate,user=Depends(current_user)):
 if not user['is_platform_admin']: raise HTTPException(403,'Platform administrator required')
 tid=str(uuid.uuid4()); now=iso()
 with db() as c: c.execute('INSERT INTO tenants(id,name,slug,status,reporting_currency,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(tid,x.name,x.slug,'ACTIVE',x.reporting_currency,now,now)); write_audit(c,tid,user['id'],'TENANT_CREATED','Tenant',tid,after=x.model_dump())
 return {'id':tid}
@router.get('/system/mode')
def get_mode(user=Depends(current_user)):
 with db() as c:return {'mode':json.loads(c.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()['value_json'])}
@router.get('/reference/currencies')
def reference_currencies(user=Depends(current_user)):
 with db() as c:
  return [dict(r) for r in c.execute('SELECT code,name,kind FROM reference_currencies ORDER BY code')]
@router.get('/reference/instruments')
def reference_instruments(user=Depends(current_user)):
 with db() as c:
  return [dict(r) for r in c.execute('SELECT symbol,base_code,quote_code,enabled FROM reference_instruments ORDER BY symbol')]
@router.put('/system/mode')
def set_mode(x:SystemModeUpdate,user=Depends(current_user)):
 if not user['is_platform_admin']: raise HTTPException(403,'Platform administrator required')
 allowed={'ANALYSIS_ONLY','SHADOW','DEMO_AUTONOMOUS','LIVE_AUTONOMOUS','PAUSED','EMERGENCY_STOP'}
 if x.mode not in allowed: raise HTTPException(400,'Invalid mode')
 if app_env() == 'production' and x.mode not in {'ANALYSIS_ONLY','PAUSED','EMERGENCY_STOP','LIVE_AUTONOMOUS','DEMO_AUTONOMOUS'}: raise HTTPException(403,'Invalid mode for this environment')
 with db() as c:
  old=json.loads(c.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()['value_json']); c.execute("UPDATE system_settings SET value_json=?,updated_at=? WHERE key='system.mode'",(json.dumps(x.mode),iso())); write_audit(c,None,user['id'],'SYSTEM_MODE_CHANGED','System','system',before={'mode':old},after={'mode':x.mode},reason=x.reason)
 return {'mode':x.mode}
