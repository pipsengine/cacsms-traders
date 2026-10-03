from fastapi import Header,HTTPException
import sqlite3
import time

from .core.database import connect, db
from .core.security import token_hash,iso

def get_db():
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
  c.rollback()
  raise
 finally:
  c.close()

def current_user(authorization:str|None=Header(default=None)):
 if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
 with db() as c:
  r=c.execute("""SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.status='ACTIVE' """,(token_hash(authorization[7:]),iso())).fetchone()
  if not r: raise HTTPException(401,'Session invalid or expired')
  return dict(r)
