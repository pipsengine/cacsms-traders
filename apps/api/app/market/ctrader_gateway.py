"""Read-only cTrader adapter. Secrets stay in the child process stdin."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from ..core.security import decrypt_ctrader_token
from ..services import ctrader_discovery_worker
from .models import Candle
from .provider_contract import MarketDataUnavailable


class CTraderGateway:
    provider_id = 'ctrader'

    def __init__(self, conn, cfg):
        from ..services.ctrader_application_state import application_state
        if application_state(conn) == 'APP_INACTIVE':
            raise MarketDataUnavailable('CTRADER_APP_INACTIVE')
        from ..routers.ctrader import _refresh_if_needed, ctrader_config
        row = conn.execute("SELECT * FROM ctrader_connections WHERE tenant_id=? AND environment='demo'", (cfg['tenant_id'],)).fetchone()
        row = _refresh_if_needed(dict(row), ctrader_config())
        if row['authorization_status'] != 'AUTHORIZED':
            raise MarketDataUnavailable('ctrader_authorization_required')
        self._token = decrypt_ctrader_token(row['access_token'])
        self._conn = conn
        self.account_id = cfg['account_id']
        self._context = dict(provider='ctrader', account_id=self.account_id, environment='demo')

    def _request(self, action, **kwargs):
        from .constants import FX_PAIRS_28
        kwargs.setdefault('symbols', [*FX_PAIRS_28, 'XAUUSD'])
        try:
            result = subprocess.run([sys.executable, ctrader_discovery_worker.__file__],
                input=json.dumps(dict(environment='demo', access_token=self._token, account_id=self.account_id, action=action, **kwargs)),
                capture_output=True, text=True, timeout=22)
            marker = next(line[15:] for line in reversed(result.stdout.splitlines()) if line.startswith('CTRADER_RESULT:'))
            payload = json.loads(marker)
        except Exception:
            raise MarketDataUnavailable('ctrader_provider_unavailable') from None
        if payload.get('error') == 'CTRADER_APP_INACTIVE':
            from ..services.ctrader_application_state import record_application_state
            record_application_state(self._conn, 'APP_INACTIVE')
            self._conn.commit()
        if result.returncode or payload.get('error'):
            raise MarketDataUnavailable(payload.get('error') or 'ctrader_provider_unavailable')
        return payload

    def get_symbols(self):
        return self._request('symbols')['symbols']

    def get_symbol(self, symbol):
        return next((s for s in self.get_symbols() if s['canonical_symbol'] == symbol.upper().replace('/', '')), None)

    def get_latest_price(self, symbol):
        return self._request('quote', symbols=[symbol])['quote']

    def symbol_snapshot(self, symbol):
        quote = self.get_latest_price(symbol)
        day = self.closed_candles(symbol, 'D1', 1)
        return {**quote, 'symbol': symbol, 'tick_time': datetime.fromisoformat(quote['timestamp']),
                'day_high': day[-1].high if day else None, 'day_low': day[-1].low if day else None}

    def get_provider_health(self):
        return dict(configured=True, authorized=True, connected=True, healthy=True, market_data_available=True, execution_available=False)

    def get_account_context(self):
        return self._context

    def get_candles(self, symbol, timeframe, **kwargs):
        return self.get_closed_candles(symbol, timeframe, **kwargs)

    def get_closed_candles(self, symbol, timeframe, *, start=None, end=None, count=400):
        request = dict(symbol=symbol, timeframe=timeframe, count=count)
        if start:
            request['start'] = int(start.timestamp() * 1000)
        if end:
            request['end'] = int(end.timestamp() * 1000)
        payload = self._request('history', requests=[request])
        if payload.get('missing_symbols'):
            raise MarketDataUnavailable('symbol_mapping_failed')
        return [Candle(**{**row, 'open_time': datetime.fromtimestamp(row['open_time'], timezone.utc),
                         'close_time': datetime.fromtimestamp(row['close_time'], timezone.utc)}) for row in payload['candles']]

    def closed_candles(self, symbol, timeframe, count=400):
        return self.get_closed_candles(symbol, timeframe, count=count)

    def latest_closed_open_time(self, symbol, timeframe):
        candles = self.closed_candles(symbol, timeframe, 1)
        return int(candles[-1].open_time.timestamp()) if candles else None
