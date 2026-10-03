from datetime import datetime, timezone
from .constants import TIMEFRAME_SECONDS
_ALIASES={"W1":"W","MN1":"MN"}
def canonical(tf:str)->str:
 t=tf.upper().replace("1D","D1").replace("1H","H1").replace("15M","M15").replace("5M","M5").replace("1M","M1")
 t=_ALIASES.get(t,t)
 if t not in TIMEFRAME_SECONDS: raise ValueError(f"Unsupported timeframe: {tf}")
 return t
def freshness_threshold(tf:str)->int: return max(90, int(TIMEFRAME_SECONDS[canonical(tf)]*1.6))
def is_closed(close_time:datetime, now:datetime|None=None)->bool:
 now=now or datetime.now(timezone.utc); return close_time<=now
