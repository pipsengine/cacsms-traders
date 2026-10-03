from __future__ import annotations
import sqlite3, json
from datetime import datetime
class MarketRepository:
 def __init__(self,conn:sqlite3.Connection): self.conn=conn
 def upsert_candle(self,c):
  if not c.is_closed:return False
  self.conn.execute("""INSERT INTO mi_candle(symbol,timeframe,open_time,close_time,open,high,low,close,tick_volume,spread,source,is_closed) VALUES(?,?,?,?,?,?,?,?,?,?,?,1) ON CONFLICT(symbol,timeframe,open_time) DO UPDATE SET close_time=excluded.close_time,open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,tick_volume=excluded.tick_volume,spread=excluded.spread,source=excluded.source,is_closed=1""",(c.symbol,c.timeframe,c.open_time.isoformat(),c.close_time.isoformat(),c.open,c.high,c.low,c.close,c.tick_volume,c.spread,c.source)); return True
 def candles(self,symbol,timeframe,limit=300):
  return self.conn.execute("SELECT open_time,close_time,open,high,low,close,tick_volume,spread FROM mi_candle WHERE symbol=? AND timeframe=? AND is_closed=1 ORDER BY open_time DESC LIMIT ?",(symbol,timeframe,limit)).fetchall()[::-1]
 def save_strength(self,p):
  self.conn.execute("""INSERT INTO mi_strength_snapshot(currency,timeframe,as_of,value,slope,velocity,acceleration,persistence,confidence,sample_count,quality) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(currency,timeframe,as_of) DO UPDATE SET value=excluded.value,slope=excluded.slope,velocity=excluded.velocity,acceleration=excluded.acceleration,persistence=excluded.persistence,confidence=excluded.confidence,sample_count=excluded.sample_count,quality=excluded.quality""",(p.currency,p.timeframe,p.as_of.isoformat(),p.value,p.slope,p.velocity,p.acceleration,p.persistence,p.confidence,p.sample_count,p.quality))
 def strength_history(self,currency,timeframe,limit=96): return self.conn.execute("SELECT as_of,value,slope,velocity,acceleration,persistence,confidence,quality FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",(currency,timeframe,limit)).fetchall()[::-1]
 def save_relationship(self,p):
  self.conn.execute("""INSERT INTO mi_relationship_snapshot(pair,timeframe,as_of,base_value,quote_value,gap,abs_gap,gap_velocity,gap_acceleration,persistence,state,confidence,inspection_priority,reason_codes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(pair,timeframe,as_of) DO UPDATE SET gap=excluded.gap,abs_gap=excluded.abs_gap,gap_velocity=excluded.gap_velocity,gap_acceleration=excluded.gap_acceleration,persistence=excluded.persistence,state=excluded.state,confidence=excluded.confidence,inspection_priority=excluded.inspection_priority,reason_codes=excluded.reason_codes""",(p.pair,p.timeframe,p.as_of.isoformat(),p.base_value,p.quote_value,p.gap,p.abs_gap,p.gap_velocity,p.gap_acceleration,p.persistence,p.state,p.confidence,p.inspection_priority,json.dumps(p.reason_codes)))
 def latest_matrix(self):
  cur=self.conn.execute("SELECT MAX(as_of) FROM mi_strength_snapshot").fetchone()
  if not cur or cur[0] is None: return []
  as_of=cur[0]
  return self.conn.execute("SELECT * FROM mi_strength_snapshot WHERE as_of=? ORDER BY currency,timeframe",(as_of,)).fetchall()
 def upsert_quality(self,q):
  last=q.last_closed_at.isoformat() if q.last_closed_at else None
  self.conn.execute("""INSERT INTO mi_data_quality(symbol,timeframe,state,last_closed_at,age_seconds,missing_bars,reason,updated_at)
   VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
   ON CONFLICT(symbol,timeframe) DO UPDATE SET state=excluded.state,last_closed_at=excluded.last_closed_at,age_seconds=excluded.age_seconds,missing_bars=excluded.missing_bars,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP""",
   (q.symbol,q.timeframe,q.state,last,q.age_seconds,q.missing_bars,q.reason or ""))
