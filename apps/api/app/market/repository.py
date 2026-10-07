from __future__ import annotations
import sqlite3, json
from datetime import datetime
from ..core.database import execute_retry
from .models import Candle
from .provenance import scoped_query, values
def _utc(value):
 from datetime import timezone
 dt=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
 return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
class MarketRepository:
 def __init__(self,conn:sqlite3.Connection,provider=None,snapshot_id=None):
  self.conn=conn
  self.provider=provider.lower() if provider else None
  self.snapshot_id=snapshot_id
  self.account_id=""
  self.provider_storage=bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mi_provider_candle'").fetchone()) if isinstance(conn,sqlite3.Connection) or getattr(conn,'provider',None)=='sqlite' else True
  if self.provider_storage and self.provider is None:
   row=conn.execute("SELECT id,provider FROM mi_provider_snapshot WHERE finalized_at IS NULL LIMIT 1").fetchone()
   if row:
    self.provider=row['provider']; self.snapshot_id=row['id']
   else:
    sources=conn.execute('SELECT DISTINCT source FROM mi_provider_candle').fetchall()
    self.provider=str(sources[0]['source']) if len(sources)==1 else '__unavailable__'
  if self.provider_storage and self.snapshot_id:
   scope=conn.execute('SELECT account_id FROM mi_provider_snapshot WHERE id=?',(self.snapshot_id,)).fetchone()
   self.account_id=scope['account_id'] if scope else ''
 def _candles_query(self,sql,params=()):
  if self.provider_storage:
   sql=sql.replace('mi_candle','(SELECT * FROM mi_provider_candle WHERE source=? AND account_id=?) AS provider_candles')
   params=(self.provider,self.account_id,*params)
  return self.conn.execute(sql,params)
 def record_provenance(self,kind,as_of):
  if self.snapshot_id:
   scope=self.conn.execute('SELECT finalized_at FROM mi_provider_snapshot WHERE id=?',(self.snapshot_id,)).fetchone()
   if not scope or scope['finalized_at'] is not None: raise ValueError('Analytical snapshot has been finalized')
   stamp=as_of.isoformat() if hasattr(as_of,'isoformat') else as_of
   self.conn.execute('INSERT INTO mi_analysis_provenance(kind,as_of,snapshot_id) VALUES(?,?,?) ON CONFLICT DO NOTHING',(kind,stamp,self.snapshot_id))
   binding=self.conn.execute('SELECT snapshot_id FROM mi_analysis_provenance WHERE kind=? AND as_of=?',(kind,stamp)).fetchone()
   if binding['snapshot_id']!=self.snapshot_id: raise ValueError('Analysis provenance is immutable')
 def upsert_candle(self,c):
  if not c.is_closed:return False
  if self.provider_storage:
   from datetime import timezone
   from math import isfinite
   if c.close_time > datetime.now(timezone.utc) or not all(isfinite(v) and v>0 for v in (c.open,c.high,c.low,c.close)): return False
   source=c.source.lower()
   if c.account_id!=self.account_id: raise ValueError('Mixed-account candle ingestion refused')
   if self.provider not in (None,'__unavailable__',source): raise ValueError('Mixed-provider candle ingestion refused')
   if self.provider=='__unavailable__': self.provider=source
   execute_retry(self.conn,"""INSERT INTO mi_provider_candle(symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,source,account_id,is_closed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(source,account_id,symbol,timeframe,open_time) DO UPDATE SET close_time=excluded.close_time,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,tick_volume=excluded.tick_volume,spread=excluded.spread""",(c.symbol,c.timeframe,c.open_time.isoformat(),c.close_time.isoformat(),c.open,c.high,c.low,c.close,c.tick_volume,c.spread,source,c.account_id))
   return True
  execute_retry(self.conn,"""INSERT INTO mi_candle(symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,source,is_closed) VALUES(?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(symbol,timeframe,open_time) DO UPDATE SET close_time=excluded.close_time,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,tick_volume=excluded.tick_volume,spread=excluded.spread,source=excluded.source,is_closed=1""",(c.symbol,c.timeframe,c.open_time.isoformat(),c.close_time.isoformat(),c.open,c.high,c.low,c.close,c.tick_volume,c.spread,c.source)); return True
 def candles(self,symbol,timeframe,limit=300):
  return [values(row) for row in self._candles_query("SELECT open_time,close_time,open,high,low,close,tick_volume,spread FROM mi_candle WHERE symbol=? AND timeframe=? AND is_closed=1 ORDER BY open_time DESC LIMIT ?",(symbol,timeframe,limit)).fetchall()[::-1]]
 def recent_candles(self,timeframe:str,limit:int)->dict[str,list[Candle]]:
  """Latest `limit` closed candles per symbol in one round trip, oldest first."""
  rows=self._candles_query(
   """SELECT symbol,open_time,close_time,open,high,low,close,tick_volume,spread FROM (
        SELECT symbol,open_time,close_time,open,high,low,close,tick_volume,spread,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS rn
        FROM mi_candle WHERE timeframe=? AND is_closed=1
      ) WHERE rn <= ? ORDER BY symbol, open_time""",
   (timeframe, limit),
  ).fetchall()
  out:dict[str,list[Candle]]={}
  for row in rows:
   sym,ot,ct,o,h,l,c,v,s=values(row)
   out.setdefault(str(sym),[]).append(Candle(str(sym),timeframe,_utc(ot),_utc(ct),float(o),float(h),float(l),float(c),int(v or 0),s,self.provider or "UNKNOWN",True,self.account_id))
  return out
 def latest_open_times(self,symbol:str)->dict[str,datetime]:
  rows=self._candles_query("SELECT timeframe,MAX(open_time) FROM mi_candle WHERE symbol=? AND is_closed=1 GROUP BY timeframe",(symbol,)).fetchall()
  return {str(tf):_utc(t) for tf,t in (values(r) for r in rows) if t}
 def closes_by_timeframe(self,timeframe:str,limit:int=400)->dict[str,list[float]]:
  rows=self._candles_query(
   """SELECT symbol, close FROM (
        SELECT symbol, close,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS rn
        FROM mi_candle WHERE timeframe=? AND is_closed=1
      ) WHERE rn <= ? ORDER BY symbol, rn DESC""",
   (timeframe, limit),
  ).fetchall()
  out:dict[str,list[float]]={}
  for row in rows:
   sym, close=values(row)
   c=float(close)
   if c<=0: continue
   out.setdefault(str(sym), []).append(c)
  return out
 def d1_series_by_symbol(self,limit:int=400)->dict[str,list[tuple[datetime,float]]]:
  rows=self._candles_query(
   """SELECT symbol, open_time, close FROM (
        SELECT symbol, open_time, close,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS rn
        FROM mi_candle WHERE timeframe='D1' AND is_closed=1
      ) WHERE rn <= ? ORDER BY symbol, open_time""",
   (limit,),
  ).fetchall()
  out:dict[str,list[tuple[datetime,float]]]={}
  for row in rows:
   sym, ot, close=values(row)
   dt=datetime.fromisoformat(ot)
   c=float(close)
   if c<=0: continue
   out.setdefault(str(sym), []).append((dt, c))
  return out
 def resolve_stored_symbol(self,pair:str)->str|None:
  p=pair.upper().replace('/','')
  row=self._candles_query("SELECT symbol FROM mi_candle WHERE symbol=? LIMIT 1",(p,)).fetchone()
  if row: return str(values(row)[0])
  row=self._candles_query("SELECT symbol FROM mi_candle WHERE symbol LIKE ? LIMIT 1",(f"%{p}%",)).fetchone()
  return str(values(row)[0]) if row else None
 def save_strength(self,p):
  self.record_provenance("strength",p.as_of)
  execute_retry(self.conn,"""INSERT INTO mi_strength_snapshot(currency,timeframe,as_of,value,slope,velocity,acceleration,persistence,confidence,sample_count,quality,score) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(currency,timeframe,as_of) DO UPDATE SET value=excluded.value,slope=excluded.slope,velocity=excluded.velocity,acceleration=excluded.acceleration,persistence=excluded.persistence,confidence=excluded.confidence,sample_count=excluded.sample_count,quality=excluded.quality,score=excluded.score""",(p.currency,p.timeframe,p.as_of.isoformat(),p.value,p.slope,p.velocity,p.acceleration,p.persistence,p.confidence,p.sample_count,p.quality,p.score))
 def score_history(self,currency:str,timeframe:str="AVG",limit:int=32)->list[tuple[str,float]]:
  rows=scoped_query(self.conn,"SELECT as_of,score FROM mi_strength_snapshot WHERE currency=? AND timeframe=? AND score IS NOT NULL ORDER BY as_of DESC LIMIT ?",(currency,timeframe,limit),snapshot_id=self.snapshot_id).fetchall()
  return [(str(values(r)[0]),float(values(r)[1])) for r in rows][::-1]
 def strength_history(self,currency,timeframe,limit=96): return scoped_query(self.conn,"SELECT as_of,value,slope,velocity,acceleration,persistence,confidence,quality FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",(currency,timeframe,limit)).fetchall()[::-1]
 def save_relationship(self,p):
  self.record_provenance("relationship",p.as_of)
  execute_retry(self.conn,"""INSERT INTO mi_relationship_snapshot(pair,timeframe,as_of,base_value,quote_value,gap,abs_gap,gap_velocity,gap_acceleration,persistence,state,confidence,inspection_priority,reason_codes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(pair,timeframe,as_of) DO UPDATE SET gap=excluded.gap,abs_gap=excluded.abs_gap,gap_velocity=excluded.gap_velocity,gap_acceleration=excluded.gap_acceleration,persistence=excluded.persistence,state=excluded.state,confidence=excluded.confidence,inspection_priority=excluded.inspection_priority,reason_codes=excluded.reason_codes""",(p.pair,p.timeframe,p.as_of.isoformat(),p.base_value,p.quote_value,p.gap,p.abs_gap,p.gap_velocity,p.gap_acceleration,p.persistence,p.state,p.confidence,p.inspection_priority,json.dumps(p.reason_codes)))
 def latest_matrix(self):
  cur=scoped_query(self.conn,"SELECT MAX(as_of) FROM mi_strength_snapshot").fetchone()
  if not cur or values(cur)[0] is None: return []
  as_of=values(cur)[0]
  return scoped_query(self.conn,"SELECT * FROM mi_strength_snapshot WHERE as_of=? ORDER BY currency,timeframe",(as_of,)).fetchall()
 def upsert_quality(self,q):
  last=q.last_closed_at.isoformat() if q.last_closed_at else None
  execute_retry(self.conn,"""INSERT INTO mi_data_quality(symbol,timeframe,state,last_closed_at,age_seconds,missing_bars,reason,updated_at)
   VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
   ON CONFLICT(symbol,timeframe) DO UPDATE SET state=excluded.state,last_closed_at=excluded.last_closed_at,age_seconds=excluded.age_seconds,missing_bars=excluded.missing_bars,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP""",
   (q.symbol,q.timeframe,q.state,last,q.age_seconds,q.missing_bars,q.reason or ""))
