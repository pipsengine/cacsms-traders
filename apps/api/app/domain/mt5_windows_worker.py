"""Windows MT5 attachment. Market-data sampling does not send orders.

Authorized orders are pulled from the API and submitted only by drain_orders.
"""
import json
import math
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote
from ..market.constants import FX_PAIRS_28

CLOUD_ORIGINS = {'https://cacsms-traders.vercel.app','http://localhost:8000','http://127.0.0.1:8000'}
M1_TAIL_BARS = 5
HEARTBEAT_SECONDS = 15


def quote_seconds():
    """Quotes-only push cadence for live charts (MT5_QUOTE_PUSH_SECONDS; 0 disables)."""
    try:
        return max(0.0, float(os.getenv('MT5_QUOTE_PUSH_SECONDS', '1') or 0))
    except ValueError:
        return 1.0


def valid_bar(r):
    o,h,l,c = (float(r[k]) for k in ('open','high','low','close'))
    return all(math.isfinite(v) and v > 0 for v in (o,h,l,c)) and h >= max(o,c,l) and l <= min(o,c,h)


def valid_suffix(rows):
    """Bars after the newest corrupt one: one bad historical bar must not reject the whole upload or leave a gap."""
    rows = list(rows)
    return rows[next((i+1 for i in range(len(rows)-1,-1,-1) if not valid_bar(rows[i])),0):]


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
        self.quote_thread = None
        self.session = None
        self.error = None
        self.frame = 0
        self.broker_utc_offset_seconds = None

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
        quotes, candles, contracts = [], [], []
        names = [s.name for s in (self.sdk.symbols_get() or ())]
        from ..execution.symbols import choose_account_symbol, trade_mode_allows_entry
        for symbol in (*FX_PAIRS_28,'XAUUSD'):
            def tradable(name, _sdk=self.sdk):
                info = _sdk.symbol_info(name)
                if info is None:
                    return False
                return trade_mode_allows_entry(getattr(info, "trade_mode", None))

            broker = choose_account_symbol(
                symbol, names,
                lambda name: bool(self.sdk.symbol_select(name, True)),
                lambda name: self.sdk.symbol_info_tick(name),
                tradable=tradable,
            )
            if not broker or not self.sdk.symbol_select(broker,True):
                continue
            metadata = self.sdk.symbol_info(broker)
            tick = self.sdk.symbol_info_tick(broker)
            if tick and metadata and tick.bid > 0 and tick.ask >= tick.bid:
                quotes.append(dict(symbol=symbol,provider_symbol=broker,bid=float(tick.bid),ask=float(tick.ask),time=int(tick.time),digits=int(metadata.digits),tick_size=float(metadata.trade_tick_size or metadata.point),pip_size=float(metadata.point)*(10 if metadata.digits in (3,5) else 1)))
                tick_value = float(getattr(metadata, 'trade_tick_value', 0) or 0)
                volume_min = float(getattr(metadata, 'volume_min', 0) or 0)
                volume_step = float(getattr(metadata, 'volume_step', 0) or 0)
                volume_max = float(getattr(metadata, 'volume_max', 0) or 0)
                if tick_value > 0 and volume_min > 0 and volume_step > 0 and volume_max > 0:
                    contracts.append(dict(
                        symbol=symbol, broker_symbol=broker, tick_size=float(metadata.trade_tick_size or metadata.point),
                        tick_value=tick_value, tick_value_currency=str(account.currency),
                        currency_profit=str(getattr(metadata, 'currency_profit', '') or '') or None,
                        currency_margin=str(getattr(metadata, 'currency_margin', '') or '') or None,
                        digits=int(metadata.digits), point=float(metadata.point),
                        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
                        stops_level_points=int(getattr(metadata, 'trade_stops_level', 0) or 0),
                        spread_points=float(getattr(metadata, 'spread', 0) or 0),
                        margin_per_lot=float(getattr(metadata, 'margin_initial', 0) or 0) or None,
                        commission_per_lot=0,
                    ))
            if not history:
                continue
            # M1 goes stale faster than the 9-frame rotation, so every frame also carries a short M1 tail.
            for frame_tf, count in ((tf, 400),) if tf == 'M1' else ((tf, 400), ('M1', M1_TAIL_BARS)):
                constant = getattr(self.sdk,'TIMEFRAME_'+('MN1' if frame_tf=='MN' else frame_tf))
                rows = self.sdk.copy_rates_from_pos(broker,constant,1,count)
                if rows is not None:
                    for r in valid_suffix(rows):
                        candles.append(dict(symbol=symbol,timeframe=frame_tf,time=int(r['time']),open=float(r['open']),high=float(r['high']),low=float(r['low']),close=float(r['close']),tick_volume=int(r['tick_volume']),spread=float(r['spread'])))
        after = self.sdk.account_info()
        if after is None or f'{after.server}/{after.login}' != identity:
            raise RuntimeError('MT5 account changed during sampling. Reconnect from the platform.')
        if self.broker_utc_offset_seconds is None and quotes:
            delta = max(q['time'] for q in quotes)-datetime.now(timezone.utc).timestamp()
            # Infer only a clearly future broker clock. Old/weekend ticks stay old.
            offset = round(delta/900)*900 if delta > 90 else 0
            if offset > 50400 or (offset and abs(delta-offset)>90):
                raise RuntimeError('Broker clock could not be normalized. Check the Windows clock and gateway configuration.')
            self.broker_utc_offset_seconds = offset
        offset = self.broker_utc_offset_seconds or 0
        for item in [*quotes,*candles]:
            item['broker_time'] = item['time']
            item['time'] -= offset
        return dict(account=dict(login=str(account.login),server=account.server,company=account.company,currency=account.currency,
                                trade_mode={0:'DEMO',1:'PROP_FIRM',2:'LIVE'}.get(account.trade_mode,'LIVE'),balance=float(account.balance),equity=float(account.equity),margin=float(account.margin),free_margin=float(account.margin_free),leverage=int(account.leverage),
                                margin_level=float(getattr(account, 'margin_level', 0) or 0), profit=float(getattr(account, 'profit', 0) or 0),
                                trade_allowed=bool(getattr(account, 'trade_allowed', False)), trade_expert=bool(getattr(account, 'trade_expert', False))),
                    terminal_path=self.terminal,quotes=quotes,candles=candles,contracts=contracts,broker_utc_offset_seconds=offset)

    def _request(self, endpoint, payload, timeout):
        session = self.session
        if not session:
            raise RuntimeError('MT5 bridge is not connected.')
        url = session['origin']+'/api/tenants/'+quote(session['tenant_id'],safe='')+'/mt5-bridge/'+endpoint
        request = urllib.request.Request(url,json.dumps(payload,allow_nan=False).encode(),{'Content-Type':'application/json','X-MT5-Bridge-Token':session['token']},method='POST')
        return urllib.request.build_opener(NoRedirect()).open(request,timeout=timeout)

    def push_quotes(self, payload):
        """Quotes-only frame. Returns False when the server cannot accept them (older API); never stops the bridge."""
        frame = dict(quotes=payload['quotes'],broker_utc_offset_seconds=payload['broker_utc_offset_seconds'])
        if not frame['quotes']:
            return True
        try:
            with self._request('quotes',frame,10) as response:
                return bool(json.load(response).get('ok'))
        except urllib.error.HTTPError as exc:
            if exc.code in (404,405):
                return False
            return True
        except (urllib.error.URLError,OSError,ValueError):
            return True

    def upload(self, payload):
        try:
            with self._request('heartbeat',payload,30) as response:
                result = json.load(response)
                if not result.get('ok'):
                    raise RuntimeError('Cloud rejected the MT5 heartbeat.')
                return result
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403,409):
                self.stop.set()
            if exc.code == 422:
                try:
                    detail = json.loads(exc.read(65536)).get('detail',[])
                    fields = ', '.join('.'.join(str(part) for part in error.get('loc',[])) for error in detail[:3]) if isinstance(detail,list) else ''
                except (ValueError,TypeError):
                    fields = ''
                raise RuntimeError('Cloud rejected MT5 data validation'+(f' at {fields}' if fields else '')+'. Check the gateway clock and data format.') from None
            raise RuntimeError(f'Cloud bridge rejected the connection (HTTP {exc.code}). Reconnect from the platform.') from None
        except urllib.error.URLError:
            raise RuntimeError('Windows gateway cannot reach the hosted API. Check the network and retry Connect.') from None

    def connect(self, tenant_id, token, origin):
        if origin not in CLOUD_ORIGINS or not isinstance(tenant_id,str) or not 1 <= len(tenant_id) <= 128 or not isinstance(token,str) or not 32 <= len(token) <= 128:
            raise ValueError('Invalid bridge pairing request')
        self.stop.set()
        for worker in (self.thread, self.quote_thread):
            if worker and worker.is_alive():
                worker.join(timeout=35)
                if worker.is_alive():
                    raise RuntimeError('Previous bridge request is still finishing. Retry Connect shortly.')
        with self.lock:
            account = self.attach()
            self.broker_utc_offset_seconds = None
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
            interval = quote_seconds()
            if interval and (not self.quote_thread or not self.quote_thread.is_alive()):
                self.quote_thread = threading.Thread(target=self.quote_loop,args=(interval,),daemon=True)
                self.quote_thread.start()
            return {'ok':True,'connected':True,'received_at':result['received_at'],'execution_available':False}

    def quote_loop(self, interval):
        """Latest ticks between history heartbeats; the MT5 SDK is only touched under the lock, uploads happen outside it."""
        while not self.stop.wait(interval):
            try:
                with self.lock:
                    payload = self.sample(history=False) if self.session else None
                if payload and not self.push_quotes(payload):
                    return
            except Exception:  # noqa: BLE001 - the heartbeat loop reports bridge errors
                continue

    def _send_order(self, order):
        """Submit the already sized volume. An uncertain result is not sent again."""
        sdk = self.sdk
        done = {10008, 10009, 10010}
        uncertain = {10012, 10032}
        symbol = order.get('broker_symbol') or order.get('symbol')
        info = sdk.symbol_info(symbol)
        if info is None or not sdk.symbol_select(symbol, True):
            return {'request_id': order['id'], 'ok': False, 'uncertain': False, 'error': f'Symbol {symbol} is not on the terminal'}
        action = (order.get('action') or 'PLACE').upper()
        if action == 'CLOSE':
            rows = sdk.positions_get(ticket=int(order['ticket']))
            if not rows:
                return {'request_id': order['id'], 'ok': False, 'uncertain': False, 'error': 'Ticket is not open'}
            pos = rows[0]
            tick = sdk.symbol_info_tick(pos.symbol)
            closing = int(pos.type) == int(sdk.POSITION_TYPE_BUY)
            request = {'action': sdk.TRADE_ACTION_DEAL, 'symbol': pos.symbol, 'volume': float(pos.volume),
                       'type': sdk.ORDER_TYPE_SELL if closing else sdk.ORDER_TYPE_BUY, 'position': int(pos.ticket),
                       'price': float(tick.bid if closing else tick.ask), 'deviation': 20, 'magic': 260151,
                       'comment': 'cacsms-close', 'type_time': sdk.ORDER_TIME_GTC, 'type_filling': sdk.ORDER_FILLING_RETURN}
        elif action == 'MODIFY':
            request = {'action': sdk.TRADE_ACTION_SLTP, 'symbol': symbol, 'position': int(order['ticket']),
                       'sl': float(order['stop_price'] or 0), 'tp': float(order['target_price'] or 0)}
        else:
            tick = sdk.symbol_info_tick(symbol)
            buy = (order.get('direction') or '').upper() == 'BULLISH'
            request = {'action': sdk.TRADE_ACTION_DEAL, 'symbol': symbol, 'volume': float(order['volume']),
                       'type': sdk.ORDER_TYPE_BUY if buy else sdk.ORDER_TYPE_SELL,
                       'price': float(tick.ask if buy else tick.bid), 'sl': float(order['stop_price'] or 0),
                       'tp': float(order['target_price'] or 0), 'deviation': 20, 'magic': 260151, 'comment': 'cacsms',
                       'type_time': sdk.ORDER_TIME_GTC, 'type_filling': sdk.ORDER_FILLING_FOK}
        result = sdk.order_send(request)
        retcode = None if result is None else int(result.retcode)
        if result is None or retcode in uncertain:
            return {'request_id': order['id'], 'ok': False, 'uncertain': True, 'retcode': retcode, 'error': 'Broker result is uncertain'}
        if retcode == 10031 and request.get('type_filling') != sdk.ORDER_FILLING_RETURN:
            request['type_filling'] = sdk.ORDER_FILLING_RETURN
            result = sdk.order_send(request)
            retcode = None if result is None else int(result.retcode)
            if result is None or retcode in uncertain:
                return {'request_id': order['id'], 'ok': False, 'uncertain': True, 'retcode': retcode, 'error': 'Broker result is uncertain'}
        if result is None or retcode not in done:
            comment = '' if result is None else str(getattr(result, 'comment', '') or '')
            return {'request_id': order['id'], 'ok': False, 'uncertain': False, 'retcode': retcode, 'error': comment or f'Broker retcode {retcode}'}
        return {'request_id': order['id'], 'ok': True, 'uncertain': False, 'retcode': retcode,
                'ticket': str(getattr(result, 'order', '') or getattr(result, 'deal', '') or ''),
                'deal': str(getattr(result, 'deal', '') or ''), 'volume': float(order.get('volume') or 0)}

    def drain_orders(self):
        """Pull at most one authorized order. Sampling never calls this."""
        if not self.session:
            return None
        try:
            with self._request('orders/pull', {'open_tickets': []}, 20) as response:
                payload = json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            return None
        order = payload.get('order')
        if not order:
            return None
        with self.lock:
            result = self._send_order(order)
        try:
            with self._request('orders/result', result, 20) as response:
                json.load(response)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            self.error = 'Order result was not acknowledged. It will not be retried until reconciliation.'
        return result

    def run(self):
        while not self.stop.wait(HEARTBEAT_SECONDS):
            try:
                with self.lock:
                    payload = self.sample()
                self.upload(payload)
                self.drain_orders()
                self.error = None
            except Exception as exc:
                self.error = str(exc)
        with self.lock:
            self.session = None
        # Credential remains in memory only; never write credentials or broker passwords.

