from datetime import datetime, timezone
from .models import DataQuality
from .timeframes import freshness_threshold
def assess(symbol,timeframe,last_closed_at,missing_bars=0,now=None):
 now=now or datetime.now(timezone.utc)
 if last_closed_at is None:return DataQuality(symbol,timeframe,"MISSING",None,None,missing_bars,"NO_CLOSED_CANDLE")
 age=max(0,(now-last_closed_at).total_seconds()); limit=freshness_threshold(timeframe)
 state="FRESH" if age<=limit else "AGING" if age<=limit*2 else "STALE"
 if missing_bars>=3 and state=="FRESH": state="AGING"
 return DataQuality(symbol,timeframe,state,last_closed_at,age,missing_bars,"" if state=="FRESH" else "DATA_FRESHNESS")
