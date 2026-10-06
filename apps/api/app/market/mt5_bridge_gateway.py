"""Provider adapter over fresh, account-scoped Windows bridge uploads."""
from datetime import datetime, timezone
from ..domain.mt5_bridge import status
from .models import Candle
from .provider_contract import MarketDataUnavailable


class MT5BridgeGateway:
    def __init__(self, conn, tenant_id):
        self.conn, self.tenant_id = conn, tenant_id

    def state(self):
        state = status(self.conn,self.tenant_id)
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
        price = self.get_latest_price(symbol)
        return {**price,'point':price['tick_size'],'broker_symbol':price['provider_symbol']}

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
