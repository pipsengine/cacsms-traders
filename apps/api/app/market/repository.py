from __future__ import annotations
import sqlite3, json
from datetime import datetime
from ..core.database import execute_retry
class MarketRepository:
 def __init__(self,conn:sqlite3.Connection): self.conn=conn
 def upsert_candle(self,c):
  if not c.is_closed:return False
  execute_retry(self.conn,"""INSERT INTO mi_candle(symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,source,is_closed) VALUES(?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(symbol,timeframe,open_time) DO UPDATE SET close_time=excluded.close_time,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,tick_volume=excluded.tick_volume,spread=excluded.spread,source=excluded.source,is_closed=1""",(c.symbol,c.timeframe,c.open_time.isoformat(),c.close_time.isoformat(),c.open,c.high,c.low,c.close,c.tick_volume,c.spread,c.source)); return True
 def candles(self,symbol,timeframe,limit=300):
  return self.conn.execute("SELECT open_time,close_time,open,high,low,close,tick_volume,spread FROM mi_candle WHERE symbol=? AND timeframe=? AND is_closed=1 ORDER BY open_time DESC LIMIT ?",(symbol,timeframe,limit)).fetchall()[::-1]
 def closes_by_timeframe(self,timeframe:str,limit:int=400)->dict[str,list[float]]:
  rows=self.conn.execute(
   """SELECT symbol, close FROM (
        SELECT symbol, close,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS rn
        FROM mi_candle WHERE timeframe=? AND is_closed=1
      ) WHERE rn <= ? ORDER BY symbol, rn DESC""",
   (timeframe, limit),
  ).fetchall()
  out:dict[str,list[float]]={}
  for sym, close in rows:
   c=float(close)
   if c<=0: continue
   out.setdefault(str(sym), []).append(c)
  for k in out:
   out[k]=out[k][::-1]
  return out
 def d1_series_by_symbol(self,limit:int=400)->dict[str,list[tuple[datetime,float]]]:
  rows=self.conn.execute(
   """SELECT symbol, open_time, close FROM (
        SELECT symbol, open_time, close,
               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS rn
        FROM mi_candle WHERE timeframe='D1' AND is_closed=1
      ) WHERE rn <= ? ORDER BY symbol, open_time""",
   (limit,),
  ).fetchall()
  out:dict[str,list[tuple[datetime,float]]]={}
  for sym, ot, close in rows:
   dt=datetime.fromisoformat(ot)
   c=float(close)
   if c<=0: continue
   out.setdefault(str(sym), []).append((dt, c))
  return out
 def resolve_stored_symbol(self,pair:str)->str|None:
  p=pair.upper().replace('/','')
  row=self.conn.execute("SELECT symbol FROM mi_candle WHERE symbol=? LIMIT 1",(p,)).fetchone()
  if row: return str(row[0])
  row=self.conn.execute("SELECT symbol FROM mi_candle WHERE symbol LIKE ? LIMIT 1",(f"%{p}%",)).fetchone()
  return str(row[0]) if row else None
 def save_strength(self,p):
  execute_retry(self.conn,"""INSERT INTO mi_strength_snapshot(currency,timeframe,as_of,value,slope,velocity,acceleration,persistence,confidence,sample_count,quality,score) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(currency,timeframe,as_of) DO UPDATE SET value=excluded.value,slope=excluded.slope,velocity=excluded.velocity,acceleration=excluded.acceleration,persistence=excluded.persistence,confidence=excluded.confidence,sample_count=excluded.sample_count,quality=excluded.quality,score=excluded.score""",(p.currency,p.timeframe,p.as_of.isoformat(),p.value,p.slope,p.velocity,p.acceleration,p.persistence,p.confidence,p.sample_count,p.quality,p.score))
 def score_history(self,currency:str,timeframe:str="AVG",limit:int=32)->list[tuple[str,float]]:
  rows=self.conn.execute("SELECT as_of,score FROM mi_strength_snapshot WHERE currency=? AND timeframe=? AND score IS NOT NULL ORDER BY as_of DESC LIMIT ?",(currency,timeframe,limit)).fetchall()
  return [(str(r[0]),float(r[1])) for r in rows][::-1]
 def strength_history(self,currency,timeframe,limit=96): return self.conn.execute("SELECT as_of,value,slope,velocity,acceleration,persistence,confidence,quality FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",(currency,timeframe,limit)).fetchall()[::-1]
 def save_relationship(self,p):
  execute_retry(self.conn,"""INSERT INTO mi_relationship_snapshot(pair,timeframe,as_of,base_value,quote_value,gap,abs_gap,gap_velocity,gap_acceleration,persistence,state,confidence,inspection_priority,reason_codes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(pair,timeframe,as_of) DO UPDATE SET gap=excluded.gap,abs_gap=excluded.abs_gap,gap_velocity=excluded.gap_velocity,gap_acceleration=excluded.gap_acceleration,persistence=excluded.persistence,state=excluded.state,confidence=excluded.confidence,inspection_priority=excluded.inspection_priority,reason_codes=excluded.reason_codes""",(p.pair,p.timeframe,p.as_of.isoformat(),p.base_value,p.quote_value,p.gap,p.abs_gap,p.gap_velocity,p.gap_acceleration,p.persistence,p.state,p.confidence,p.inspection_priority,json.dumps(p.reason_codes)))
 def latest_matrix(self):
  cur=self.conn.execute("SELECT MAX(as_of) FROM mi_strength_snapshot").fetchone()
  if not cur or cur[0] is None: return []
  as_of=cur[0]
  return self.conn.execute("SELECT * FROM mi_strength_snapshot WHERE as_of=? ORDER BY currency,timeframe",(as_of,)).fetchall()
 def upsert_quality(self,q):
  last=q.last_closed_at.isoformat() if q.last_closed_at else None
  execute_retry(self.conn,"""INSERT INTO mi_data_quality(symbol,timeframe,state,last_closed_at,age_seconds,missing_bars,reason,updated_at)
   VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
   ON CONFLICT(symbol,timeframe) DO UPDATE SET state=excluded.state,last_closed_at=excluded.last_closed_at,age_seconds=excluded.age_seconds,missing_bars=excluded.missing_bars,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP""",
   (q.symbol,q.timeframe,q.state,last,q.age_seconds,q.missing_bars,q.reason or ""))
