"""Read-only Windows MT5 attachment and outbound heartbeat worker."""
import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote
from ..market.constants import FX_PAIRS_28

CLOUD_ORIGINS = {'https://cacsms-traders.vercel.app','http://localhost:8000','http://127.0.0.1:8000'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class WindowsBridge:
    def __init__(self, terminal, sdk=None):
        self.terminal = terminal
        self.sdk = sdk
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.session = None
        self.error = None
        self.frame = 0

    def attach(self):
        if self.sdk is None:
            import MetaTrader5
            self.sdk = MetaTrader5
        # Reuse an existing IPC session; no launch/restore on each heartbeat.
        if self.sdk.terminal_info() is None and not self.sdk.initialize(self.terminal, timeout=15000):
            raise RuntimeError('Could not attach to the configured MT5 terminal. Open it and log in, then retry Connect.')
        account = self.sdk.account_info()
        info = self.sdk.terminal_info()
        if account is None or info is None or not info.connected:
            raise RuntimeError('MT5 is not logged in or its broker connection is offline.')
        return account

    def sample(self, *, history=True):
        account = self.attach()
        identity = f'{account.server}/{account.login}'
        if self.session and self.session.get('identity') != identity:
            raise RuntimeError('MT5 account changed. Reconnect from the platform to authorize it.')
        tf = ('H1','M1','M5','M15','M30','H4','D1','W1','MN')[self.frame % 9]
        if history:
            self.frame += 1
        quotes, candles = [], []
        names = {s.name for s in (self.sdk.symbols_get() or ())}
        from ..market.mt5_gateway import symbol_candidates
        for symbol in (*FX_PAIRS_28,'XAUUSD'):
            broker = next((name for name in symbol_candidates(symbol) if name in names), None)
            if not broker or not self.sdk.symbol_select(broker,True):
                continue
            metadata = self.sdk.symbol_info(broker)
            tick = self.sdk.symbol_info_tick(broker)
            if tick and metadata and tick.bid > 0 and tick.ask >= tick.bid:
                quotes.append(dict(symbol=symbol,provider_symbol=broker,bid=float(tick.bid),ask=float(tick.ask),time=int(tick.time),digits=int(metadata.digits),tick_size=float(metadata.trade_tick_size or metadata.point),pip_size=float(metadata.point)*(10 if metadata.digits in (3,5) else 1)))
            if not history:
                continue
            constant = getattr(self.sdk,'TIMEFRAME_'+('MN1' if tf=='MN' else tf))
            rows = self.sdk.copy_rates_from_pos(broker,constant,1,400)
            if rows is not None:
                for r in rows:
                    candles.append(dict(symbol=symbol,timeframe=tf,time=int(r['time']),open=float(r['open']),high=float(r['high']),low=float(r['low']),close=float(r['close']),tick_volume=int(r['tick_volume']),spread=float(r['spread'])))
        after = self.sdk.account_info()
        if after is None or f'{after.server}/{after.login}' != identity:
            raise RuntimeError('MT5 account changed during sampling. Reconnect from the platform.')
        return dict(account=dict(login=str(account.login),server=account.server,company=account.company,currency=account.currency,
                                trade_mode={0:'DEMO',1:'PROP_FIRM',2:'LIVE'}.get(account.trade_mode,'LIVE'),balance=float(account.balance),equity=float(account.equity),margin=float(account.margin),free_margin=float(account.margin_free),leverage=int(account.leverage)),terminal_path=self.terminal,quotes=quotes,candles=candles)

    def upload(self, payload):
        session = self.session
        url = session['origin']+'/api/tenants/'+quote(session['tenant_id'],safe='')+'/mt5-bridge/heartbeat'
        request = urllib.request.Request(url,json.dumps(payload,allow_nan=False).encode(),{'Content-Type':'application/json','X-MT5-Bridge-Token':session['token']},method='POST')
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
                result = json.load(response)
                if not result.get('ok'):
                    raise RuntimeError('Cloud rejected the MT5 heartbeat.')
                return result
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403,409):
                self.stop.set()
            raise RuntimeError(f'Cloud bridge rejected the connection (HTTP {exc.code}). Reconnect from the platform.') from None
        except urllib.error.URLError:
            raise RuntimeError('Windows gateway cannot reach the hosted API. Check the network and retry Connect.') from None

    def connect(self, tenant_id, token, origin):
        if origin not in CLOUD_ORIGINS or not isinstance(tenant_id,str) or not 1 <= len(tenant_id) <= 128 or not isinstance(token,str) or not 32 <= len(token) <= 128:
            raise ValueError('Invalid bridge pairing request')
        self.stop.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=35)
            if self.thread.is_alive():
                raise RuntimeError('Previous bridge request is still finishing. Retry Connect shortly.')
        with self.lock:
            account = self.attach()
            self.session = dict(tenant_id=tenant_id,token=token,origin=origin,identity=f'{account.server}/{account.login}')
            self.stop.clear()
            try:
                result = self.upload(self.sample(history=False))
            except Exception:
                self.stop.set()
                self.session = None
                raise
            self.error = None
            if not self.thread or not self.thread.is_alive():
                self.thread = threading.Thread(target=self.run,daemon=True)
                self.thread.start()
            return {'ok':True,'connected':True,'received_at':result['received_at'],'execution_available':False}

    def run(self):
        while not self.stop.wait(15):
            with self.lock:
                try:
                    self.upload(self.sample())
                    self.error = None
                except Exception as exc:
                    self.error = str(exc)
        with self.lock:
            self.session = None
        # Credential remains in memory only; never write credentials or broker passwords.

