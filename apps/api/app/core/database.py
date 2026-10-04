import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .config import ROOT

def db_path()->Path:
 raw=os.getenv('DATABASE_PATH','database/db_cacsms-traders.db')
 p=Path(raw)
 resolved=p if p.is_absolute() else (ROOT/p).resolve()
 return resolved

class DatabaseUnavailable(RuntimeError):
 pass

def _creation_allowed()->bool:
 if os.getenv('APP_ENV','development').strip().lower()!='production': return True
 return os.getenv('DATABASE_ALLOW_CREATE','0').strip().lower() in ('1','true','yes')

def connect():
 path=db_path()
 if not path.exists():
  # Production never silently starts on a fresh empty database (e.g. an ephemeral disk).
  if not _creation_allowed():
   raise DatabaseUnavailable(f'Production database not found at {path}; set DATABASE_PATH to the durable database file (or DATABASE_ALLOW_CREATE=1 for first provisioning)')
  path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path,timeout=15,check_same_thread=False)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON')
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA synchronous=NORMAL')
 c.execute('PRAGMA busy_timeout=15000')
 return c

def execute_retry(conn: sqlite3.Connection, sql: str, params=(), *, attempts: int = 8) -> sqlite3.Cursor:
    for attempt in range(attempts):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise sqlite3.OperationalError("database is locked")

@contextmanager
def db():
    c=connect()
    try:
        yield c
        for attempt in range(8):
            try:
                c.commit()
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt >= 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except Exception:
        c.rollback(); raise
    finally: c.close()
