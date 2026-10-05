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
        from ..routers.ctrader import _refresh_if_needed, ctrader_config
        row = conn.execute("SELECT * FROM ctrader_connections WHERE tenant_id=? AND environment='demo'", (cfg['tenant_id'],)).fetchone()
        row = _refresh_if_needed(dict(row), ctrader_config())
        if row['authorization_status'] != 'AUTHORIZED':
            raise MarketDataUnavailable('ctrader_authorization_required')
        self._token = decrypt_ctrader_token(row['access_token'])
        self.account_id = cfg['account_id']

    def _request(self, action, **kwargs):
        from .constants import FX_PAIRS_28
        kwargs.setdefault('symbols', list(FX_PAIRS_28))
        try:
            result = subprocess.run([sys.executable, ctrader_discovery_worker.__file__],
                input=json.dumps(dict(environment='demo', access_token=self._token, account_id=self.account_id, action=action, **kwargs)),
                capture_output=True, text=True, timeout=22)
            marker = next(line[15:] for line in reversed(result.stdout.splitlines()) if line.startswith('CTRADER_RESULT:'))
            payload = json.loads(marker)
        except Exception:
            raise MarketDataUnavailable('ctrader_provider_unavailable') from None
        if result.returncode or payload.get('error'):
            raise MarketDataUnavailable(payload.get('error') or 'ctrader_provider_unavailable')
        return payload

    def get_symbols(self):
        return self._request('symbols')['symbols']

    def closed_candles(self, symbol, timeframe, count=400):
        payload = self._request('history', requests=[dict(symbol=symbol, timeframe=timeframe, count=count)])
        if payload.get('missing_symbols'):
            raise MarketDataUnavailable('symbol_mapping_failed')
        return [Candle(**{**row, 'open_time': datetime.fromtimestamp(row['open_time'], timezone.utc),
                         'close_time': datetime.fromtimestamp(row['close_time'], timezone.utc)}) for row in payload['candles']]

    def latest_closed_open_time(self, symbol, timeframe):
        candles = self.closed_candles(symbol, timeframe, 1)
        return int(candles[-1].open_time.timestamp()) if candles else None
