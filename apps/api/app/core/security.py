import base64,hashlib,os,secrets,datetime
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


def _ctrader_token_cipher():
    secret = os.getenv('CTRADER_CLIENT_SECRET', '').strip()
    if not secret:
        raise ValueError('cTrader token encryption is not configured')
    from cryptography.fernet import Fernet

    key = hashlib.sha256(b'cacsms-ctrader-token:v1\0' + secret.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_ctrader_token(token: str) -> str:
    if not token:
        raise ValueError('Cannot encrypt an empty cTrader token')
    encrypted = _ctrader_token_cipher().encrypt(token.encode('utf-8')).decode('ascii')
    return f'fernet:v1:{encrypted}'


def decrypt_ctrader_token(token: str) -> str:
    if not token.startswith('fernet:v1:'):
        return token
    try:
        return _ctrader_token_cipher().decrypt(token.removeprefix('fernet:v1:').encode('ascii')).decode('utf-8')
    except Exception as exc:
        raise ValueError('Stored cTrader token cannot be decrypted; reconnect the provider') from exc


def is_encrypted_ctrader_token(token: str | None) -> bool:
    return bool(token and token.startswith('fernet:v1:'))
