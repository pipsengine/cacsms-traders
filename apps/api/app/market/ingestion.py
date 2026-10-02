from .quality import assess
class CandleIngestionService:
 def __init__(self,gateway,repo):self.gateway=gateway;self.repo=repo
 def sync(self,symbol,timeframe,count=400):
  candles=self.gateway.closed_candles(symbol,timeframe,count); accepted=0; rejected=0
  for c in candles:
   if c.is_closed and c.high>=max(c.open,c.close,c.low) and c.low<=min(c.open,c.close,c.high): accepted+=bool(self.repo.upsert_candle(c))
   else: rejected+=1
  self.repo.conn.commit(); last=candles[-1].close_time if candles else None
  return {"symbol":symbol,"timeframe":timeframe,"accepted":accepted,"rejected":rejected,"quality":assess(symbol,timeframe,last).__dict__}
