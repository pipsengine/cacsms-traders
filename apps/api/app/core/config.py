from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[4]
APP_NAME = os.getenv('APP_NAME', 'Cacsms-Traders')
ENV = os.getenv('APP_ENV', 'development').strip().lower()
APP_HOST = os.getenv('APP_HOST', '0.0.0.0').strip() or '0.0.0.0'
APP_PORT = int(os.getenv('APP_PORT', '8000'))
DB_PATH = ROOT / os.getenv('DATABASE_PATH', 'database/db_cacsms-traders.db')
WEB_ORIGIN = os.getenv('WEB_ORIGIN', '').strip()
API_ORIGIN = os.getenv('API_ORIGIN', '').strip()


def cors_origins():
    origins = set()
    for candidate in (WEB_ORIGIN, API_ORIGIN):
        if candidate:
            origins.add(candidate.rstrip('/'))

    if ENV == 'production':
        extra = os.getenv('WEB_ORIGINS', '')
        if extra:
            origins.update(x.strip().rstrip('/') for x in extra.split(',') if x.strip())
        if not origins:
            origins.add('https://cacsms-traders.vercel.app')
        return sorted(origins)

    for host in ('localhost', '127.0.0.1'):
        origins.add(f'http://{host}:5173')
    extra = os.getenv('WEB_ORIGINS', '')
    if extra:
        origins.update(x.strip().rstrip('/') for x in extra.split(',') if x.strip())
    return sorted(origins)


SESSION_HOURS = int(os.getenv('SESSION_HOURS', '12'))
SESSION_COOKIE='ct_session'
CSRF_HEADER='x-ct-client'

def app_env()->str:
 return os.getenv('APP_ENV','development').strip().lower()

def is_production()->bool:
 return app_env()=='production'

def _flag(name:str)->bool|None:
 raw=os.getenv(name,'').strip().lower()
 if raw in ('1','true','yes'): return True
 if raw in ('0','false','no'): return False
 return None

def session_cookie_secure(request_is_https:bool)->bool:
 """Secure is always on in production; otherwise follows the request scheme (http dev keeps it off)."""
 forced=_flag('SESSION_COOKIE_SECURE')
 if forced is not None and not is_production(): return forced
 return is_production() or request_is_https

def session_cookie_samesite()->str:
 v=os.getenv('SESSION_COOKIE_SAMESITE','lax').strip().lower()
 return v if v in ('lax','strict') else 'lax'
BOOTSTRAP_USERNAME=os.getenv('BOOTSTRAP_USERNAME','cacsms')
BOOTSTRAP_PASSWORD=os.getenv('BOOTSTRAP_PASSWORD','ChangeMe!2026')
BOOTSTRAP_EMAIL=os.getenv('BOOTSTRAP_EMAIL','admin@cacsms.local')
MI_WORKER_ENABLED=os.getenv('MI_WORKER_ENABLED','0')
MI_WORKER_INTERVAL=int(os.getenv('MI_WORKER_INTERVAL','300'))
MT5_SYMBOL_PREFIX=os.getenv('MT5_SYMBOL_PREFIX','')
MT5_SYMBOL_SUFFIX=os.getenv('MT5_SYMBOL_SUFFIX','')
