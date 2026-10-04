from fastapi import APIRouter,Depends,HTTPException,Header,Request,Response
import uuid
from ..schemas.auth import LoginRequest,ChangePasswordRequest,ProfilePatch
from ..core.config import SESSION_COOKIE,SESSION_HOURS,session_cookie_samesite,session_cookie_secure
from ..core.database import db, execute_retry
from ..core.security import verify_password,new_token,token_hash,expires,iso,hash_password
from ..deps import current_user,session_token
from ..core.audit import write_audit
router=APIRouter(prefix='/auth',tags=['Authentication'])

def user_payload(c,user_row):
 memberships=[dict(r) for r in c.execute("""SELECT m.tenant_id,t.name tenant_name,r.name role_name FROM tenant_memberships m JOIN tenants t ON t.id=m.tenant_id LEFT JOIN roles r ON r.id=m.role_id WHERE m.user_id=? AND m.status='ACTIVE' """,(user_row['id'],))]
 body={k:v for k,v in dict(user_row).items() if k!='password_hash'}
 body['is_platform_admin']=bool(body.get('is_platform_admin'))
 body['is_system_protected']=bool(body.get('is_system_protected'))
 body['memberships']=memberships
 return body

def _is_https(request:Request)->bool:
 return request.url.scheme=='https' or request.headers.get('x-forwarded-proto','').split(',')[0].strip()=='https'

def _cookie_args(request:Request)->dict:
 return {'key':SESSION_COOKIE,'path':'/api','httponly':True,'secure':session_cookie_secure(_is_https(request)),'samesite':session_cookie_samesite()}

@router.post('/login')
def login(x:LoginRequest,request:Request,response:Response):
 with db() as c:
  u=c.execute("SELECT * FROM users WHERE username=? AND status='ACTIVE'",(x.username,)).fetchone()
  if not u or not verify_password(x.password,u['password_hash']): raise HTTPException(401,'Invalid credentials')
  token=new_token(); sid=str(uuid.uuid4())
  execute_retry(c,'INSERT INTO auth_sessions(id,user_id,token_hash,expires_at,created_at) VALUES(?,?,?,?,?)',(sid,u['id'],token_hash(token),expires(),iso()))
  execute_retry(c,'UPDATE users SET last_login_at=? WHERE id=?',(iso(),u['id']))
  response.set_cookie(value=token,max_age=SESSION_HOURS*3600,**_cookie_args(request))
  return {'access_token':token,'token_type':'bearer','user':user_payload(c,u)}
@router.post('/logout')
def logout(request:Request,response:Response,user=Depends(current_user),authorization:str|None=Header(default=None)):
 token=session_token(request,authorization)
 with db() as c:
  if token:
   c.execute('UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL',(iso(),token_hash(token)))
 args=_cookie_args(request)
 response.delete_cookie(args.pop('key'),**args)
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
  if user.get('is_system_protected') and any(k in vals for k in ('first_name','last_name','middle_name','email')):
   raise HTTPException(403,'Protected super administrator profile fields are managed by the system')
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
