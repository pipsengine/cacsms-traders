import time
class TTLCache:
 def __init__(self):self._d={}
 def get(self,k):
  v=self._d.get(k)
  if not v:return None
  if v[0]<time.time():self._d.pop(k,None);return None
  return v[1]
 def set(self,k,v,ttl=5):self._d[k]=(time.time()+ttl,v)
 def clear(self):self._d.clear()
