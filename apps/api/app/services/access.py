from fastapi import HTTPException

def tenant_access(c,user,tenant_id):
 if user['is_platform_admin']: return True
 ok=c.execute("SELECT 1 FROM tenant_memberships WHERE tenant_id=? AND user_id=? AND status='ACTIVE'",(tenant_id,user['id'])).fetchone()
 if not ok: raise HTTPException(403,'Tenant access denied')
 return True

def permissions_for(c,user_id,tenant_id):
 return {r['code'] for r in c.execute("""SELECT p.code FROM tenant_memberships m JOIN role_permissions rp ON rp.role_id=m.role_id JOIN permissions p ON p.id=rp.permission_id WHERE m.user_id=? AND m.tenant_id=? AND m.status='ACTIVE' """,(user_id,tenant_id))}

def require_permission(c,user,tenant_id,code):
 tenant_access(c,user,tenant_id)
 if user['is_platform_admin']: return
 if code not in permissions_for(c,user['id'],tenant_id): raise HTTPException(403,f'Missing permission: {code}')
