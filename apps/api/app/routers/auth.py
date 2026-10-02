from fastapi import APIRouter,Depends,HTTPException,Header
import uuid
from ..schemas.auth import LoginRequest,ChangePasswordRequest,ProfilePatch
from ..core.database import db
from ..core.security import verify_password,new_token,token_hash,expires,iso,hash_password
from ..deps import current_user
from ..core.audit import write_audit
router=APIRouter(prefix='/auth',tags=['Authentication'])

def user_payload(c,user_row):
 memberships=[dict(r) for r in c.execute("""SELECT m.tenant_id,t.name tenant_name,r.name role_name FROM tenant_memberships m JOIN tenants t ON t.id=m.tenant_id LEFT JOIN roles r ON r.id=m.role_id WHERE m.user_id=? AND m.status='ACTIVE' """,(user_row['id'],))]
 body={k:v for k,v in dict(user_row).items() if k!='password_hash'}
 body['is_platform_admin']=bool(body.get('is_platform_admin'))
 body['memberships']=memberships
 return body

@router.post('/login')
def login(x:LoginRequest):
 with db() as c:
  u=c.execute("SELECT * FROM users WHERE username=? AND status='ACTIVE'",(x.username,)).fetchone()
  if not u or not verify_password(x.password,u['password_hash']): raise HTTPException(401,'Invalid credentials')
  token=new_token(); sid=str(uuid.uuid4()); c.execute('INSERT INTO auth_sessions(id,user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)',(sid,u['id'],token_hash(token),expires(),iso())); c.execute('UPDATE users SET last_login_at=? WHERE id=?',(iso(),u['id']))
  return {'access_token':token,'token_type':'bearer','user':user_payload(c,u)}
@router.post('/logout')
def logout(user=Depends(current_user),authorization:str|None=Header(default=None)):
 with db() as c:
  if authorization and authorization.startswith('Bearer '):
   c.execute('UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL',(iso(),token_hash(authorization[7:])))
 return {'ok':True}
@router.get('/me')
def me(user=Depends(current_user)):
 with db() as c: return user_payload(c,user)
@router.patch('/me')
def patch_me(x:ProfilePatch,user=Depends(current_user)):
 vals=x.model_dump(exclude_none=True)
 if not vals:
  with db() as c: return user_payload(c,user)
 if vals.get('preferred_currency') not in (None,'USD','NGN'): raise HTTPException(400,'preferred_currency must be USD or NGN')
 with db() as c:
  parts=[]; args=[]
  for k,v in vals.items(): parts.append(f'{k}=?'); args.append(v)
  parts.append('updated_at=?'); args.append(iso()); args.append(user['id'])
  c.execute(f"UPDATE users SET {', '.join(parts)} WHERE id=?",args)
  if any(k in vals for k in ('first_name','middle_name','last_name')):
   row=c.execute('SELECT first_name,middle_name,last_name FROM users WHERE id=?',(user['id'],)).fetchone()
   display=' '.join(filter(None,[row['first_name'],row['middle_name'],row['last_name']]))
   c.execute('UPDATE users SET display_name=? WHERE id=?',(display,user['id']))
  row=c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
  return user_payload(c,row)
@router.post('/change-password')
def change_password(x:ChangePasswordRequest,user=Depends(current_user)):
 if len(x.new_password)<8: raise HTTPException(400,'Password must be at least 8 characters')
 with db() as c:
  row=c.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
  if not verify_password(x.current_password,row['password_hash']): raise HTTPException(400,'Current password is incorrect')
  c.execute('UPDATE users SET password_hash=?,updated_at=? WHERE id=?',(hash_password(x.new_password),iso(),user['id']))
 return {'ok':True}
