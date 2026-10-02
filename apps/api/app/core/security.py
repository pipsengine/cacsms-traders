import hashlib,secrets,datetime
from .config import SESSION_HOURS

def now(): return datetime.datetime.now(datetime.timezone.utc)
def iso(dt=None): return (dt or now()).isoformat()
def hash_password(password,salt=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,240000)
    return f'pbkdf2_sha256$240000${salt.hex()}${digest.hex()}'
def verify_password(password,stored):
    try:
        _,rounds,salt_hex,digest=stored.split('$')
        calc=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt_hex),int(rounds)).hex()
        return secrets.compare_digest(calc,digest)
    except Exception:return False
def new_token(): return secrets.token_urlsafe(48)
def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()
def expires(): return iso(now()+datetime.timedelta(hours=SESSION_HOURS))
