from pathlib import Path
import os
ROOT=Path(__file__).resolve().parents[4]
APP_NAME=os.getenv('APP_NAME','Cacsms-Traders')
ENV=os.getenv('APP_ENV','development')
DB_PATH=ROOT/os.getenv('DATABASE_PATH','database/db_cacsms-traders.db')
WEB_ORIGIN=os.getenv('WEB_ORIGIN','http://localhost:5173')

def cors_origins():
 origins={WEB_ORIGIN}
 if ENV=='development':
  for host in ('localhost','127.0.0.1'):
   origins.add(f'http://{host}:5173')
 extra=os.getenv('WEB_ORIGINS','')
 if extra:
  origins.update(x.strip() for x in extra.split(',') if x.strip())
 return sorted(origins)
SESSION_HOURS=int(os.getenv('SESSION_HOURS','12'))
BOOTSTRAP_USERNAME=os.getenv('BOOTSTRAP_USERNAME','cacsms')
BOOTSTRAP_PASSWORD=os.getenv('BOOTSTRAP_PASSWORD','ChangeMe!2026')
BOOTSTRAP_EMAIL=os.getenv('BOOTSTRAP_EMAIL','admin@cacsms.local')
