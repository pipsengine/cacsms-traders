from fastapi import Header,HTTPException,Request
import sqlite3
import time

from .core.config import CSRF_HEADER,SESSION_COOKIE
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

SAFE_METHODS=('GET','HEAD','OPTIONS')

def session_token(request:Request,authorization:str|None)->str|None:
 """Bearer header (API clients) or the HttpOnly session cookie (browser)."""
 if authorization and authorization.startswith('Bearer '): return authorization[7:]
 return request.cookies.get(SESSION_COOKIE)

def current_user(request:Request,authorization:str|None=Header(default=None)):
 token=session_token(request,authorization)
 if not token: raise HTTPException(401,'Authentication required')
 # Cookies ride along on cross-site requests; a custom header cannot be sent cross-site without CORS approval.
 from_cookie=not (authorization and authorization.startswith('Bearer '))
 if from_cookie and request.method not in SAFE_METHODS and not request.headers.get(CSRF_HEADER):
  raise HTTPException(403,'Missing client header')
 with db() as c:
  r=c.execute("""SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.status='ACTIVE' """,(token_hash(token),iso())).fetchone()
  if not r: raise HTTPException(401,'Session invalid or expired')
  return dict(r)
