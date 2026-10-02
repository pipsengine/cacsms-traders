import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .config import ROOT

def db_path()->Path:
 raw=os.getenv('DATABASE_PATH','database/db_cacsms-traders.db')
 p=Path(raw)
 return p if p.is_absolute() else ROOT/p

def connect():
 path=db_path()
 path.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(path,timeout=15)
 c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON')
 c.execute('PRAGMA journal_mode=WAL')
 c.execute('PRAGMA synchronous=NORMAL')
 c.execute('PRAGMA busy_timeout=5000')
 return c

@contextmanager
def db():
    c=connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()
