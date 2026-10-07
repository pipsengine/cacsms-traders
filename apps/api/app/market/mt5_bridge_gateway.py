"""Provider adapter over fresh, account-scoped Windows bridge uploads."""
import time
from datetime import datetime, timezone
from ..domain.mt5_bridge import status
from .models import Candle
from .provider_contract import MarketDataUnavailable

# Heartbeats arrive every ~15s; re-reading them per symbol costs a database round trip each.
STATE_CACHE_SECONDS = 5.0


class MT5BridgeGateway:
    candles_persisted = True

    def __init__(self, conn, tenant_id):
        self.conn, self.tenant_id = conn, tenant_id
        self._state, self._state_mono = None, 0.0

    def state(self):
        if self._state is None or time.monotonic() - self._state_mono > STATE_CACHE_SECONDS:
            self._state, self._state_mono = status(self.conn,self.tenant_id), time.monotonic()
        state = self._state
        if not state or not state['connected']:
            raise MarketDataUnavailable('mt5_bridge_heartbeat_expired')
        return state

    def get_account_context(self):
        state = self.state()
        account = state['account']
        return dict(provider='mt5',account_id=state['account_id'],account_number=account['login'],server=account['server'],environment=account['trade_mode'].lower(),currency=account['currency'],broker_utc_offset_seconds=state.get('broker_utc_offset_seconds',0))

    def get_symbols(self):
        return [{**q,'canonical_symbol':q['symbol'],'provider':'mt5','spread':q['ask']-q['bid']} for q in self.state()['quotes']]

    def get_latest_price(self, symbol):
        q = next((q for q in self.state()['quotes'] if q['symbol']==symbol),None)
        if not q or datetime.now(timezone.utc).timestamp()-q['time'] > 120:
            raise MarketDataUnavailable('mt5_bridge_quote_stale')
        return {**q,'provider':'mt5','spread':q['ask']-q['bid'],'timestamp':datetime.fromtimestamp(q['time'],timezone.utc).isoformat()}

    def symbol_snapshot(self,symbol):
        """Same contract as the direct MT5 gateway; the bridge does not upload the forming D1 bar."""
        price = self.get_latest_price(symbol)
        point = price['tick_size']
        return {**price,'symbol':symbol,'point':point,'broker_symbol':price['provider_symbol'],'description':'',
                'spread_points':round((price['ask']-price['bid'])/point) if point else 0,
                'tick_time':datetime.fromtimestamp(price['time'],timezone.utc),'day_high':None,'day_low':None}

    def get_closed_candles(self,symbol,timeframe,*,start=None,end=None,count=400):
        state = self.state()
        rows = self.conn.execute('SELECT * FROM mi_provider_candle WHERE source=? AND account_id=? AND symbol=? AND timeframe=? ORDER BY open_time DESC LIMIT ?', ('mt5',state['account_id'],symbol,timeframe,min(count,16000))).fetchall()
        result = []
        for row in reversed(rows):
            opened, closed = datetime.fromisoformat(row['open_time']),datetime.fromisoformat(row['close_time'])
            if (start is None or opened>=start) and (end is None or closed<=end):
                result.append(Candle(symbol,timeframe,opened,closed,row['open'],row['high'],row['low'],row['close'],row['tick_volume'],row['spread'],'mt5',True,state['account_id']))
        return result

    def closed_candles(self,symbol,timeframe,count=400):
        return self.get_closed_candles(symbol,timeframe,count=count)
