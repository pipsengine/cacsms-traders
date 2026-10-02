from fastapi import Header,HTTPException
from .core.database import db
from .core.security import token_hash,iso

def current_user(authorization:str|None=Header(default=None)):
 if not authorization or not authorization.startswith('Bearer '): raise HTTPException(401,'Authentication required')
 with db() as c:
  r=c.execute("""SELECT u.* FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.status='ACTIVE' """,(token_hash(authorization[7:]),iso())).fetchone()
  if not r: raise HTTPException(401,'Session invalid or expired')
  return dict(r)
