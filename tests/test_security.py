from apps.api.app.core.security import hash_password,verify_password,new_token,token_hash
def test_password_hash_roundtrip():
 h=hash_password('StrongPass!123'); assert 'StrongPass!123' not in h; assert verify_password('StrongPass!123',h); assert not verify_password('wrong',h)
def test_tokens_are_hashed():
 t=new_token(); assert t!=token_hash(t); assert len(token_hash(t))==64
