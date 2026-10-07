from datetime import datetime, timedelta, timezone
import pytest
from test_api import client, _login


def pairing(client):
    token,user = _login(client)
    headers = {'Authorization':f'Bearer {token}'}
    tenant = client.get('/api/tenants',headers=headers).json()[0]['id']
    response = client.post(f'/api/tenants/{tenant}/mt5-bridge/credential',headers=headers,json={})
    assert response.status_code == 200, response.text
    return tenant, headers, {'X-MT5-Bridge-Token':response.json()['token']}


def payload():
    now = datetime.now(timezone.utc)
    opened = now.replace(minute=0,second=0,microsecond=0)-timedelta(hours=1)
    return {'account':{'login':'123456','server':'Demo-Server','company':'Broker','currency':'USD','trade_mode':'DEMO','balance':1000.,'equity':1001.,'margin':1.,'free_margin':1000.,'leverage':100},'terminal_path':'C:\\Broker\\terminal64.exe',
            'quotes':[{'symbol':'EURUSD','provider_symbol':'EURUSD','bid':1.1,'ask':1.1001,'time':int(now.timestamp()),'digits':5,'tick_size':.00001,'pip_size':.0001}],
            'candles':[{'symbol':'EURUSD','timeframe':'H1','time':int(opened.timestamp()),'open':1.1,'high':1.11,'low':1.09,'close':1.105,'tick_volume':100,'spread':10}]}


def test_bridge_accepts_heartbeat_imports_account_and_uses_cloud_candles(client):
    tenant,headers,bridge_headers = pairing(client)
    response = client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat',headers=bridge_headers,json=payload())
    assert response.status_code == 200, response.text
    assert response.json()['execution_available'] is False
    state = client.get(f'/api/tenants/{tenant}/connections',headers=headers)
    assert state.status_code == 200, state.text
    assert state.json()['gateway']['status'] == 'CONNECTED'
    assert state.json()['gateway']['execution_enabled'] is False
    assert state.json()['diagnostics']['terminal_account']['login'] == '123456'
    accounts = client.get(f'/api/tenants/{tenant}/accounts',headers=headers).json()
    imported = next(a for a in accounts if a['account_number']=='123456')
    assert imported['trading_enabled'] == 0 and imported['autonomous_trading_enabled'] == 0
    assert client.post(f'/api/tenants/{tenant}/connections/sync-registry',headers=headers,json={}).status_code == 200
    from apps.api.app.core.database import db
    from apps.api.app.market.market_data import market_context, create_market_data_gateway
    with db() as conn:
        context = market_context(conn)
        assert context['active_provider']=='mt5',context
        gateway = create_market_data_gateway(conn,context)
        assert gateway.get_latest_price('EURUSD')['bid']==1.1
        candles = gateway.get_closed_candles('EURUSD','H1',count=2)
        assert len(candles)==1 and candles[0].account_id==response.json()['account_id']


def test_bridge_tokens_are_tenant_scoped_revocable_and_account_pinned(client):
    tenant,headers,bridge_headers = pairing(client)
    url = f'/api/tenants/{tenant}/mt5-bridge/heartbeat'
    assert client.post(url,json=payload()).status_code == 401
    assert client.post('/api/tenants/other/mt5-bridge/heartbeat',headers=bridge_headers,json=payload()).status_code == 401
    assert client.post(url,headers=bridge_headers,json=payload()).status_code == 200
    changed=payload(); changed['account']['login']='999999'
    assert client.post(url,headers=bridge_headers,json=changed).status_code == 409
    changed=payload(); changed['account']['trade_mode']='LIVE'
    assert client.post(url,headers=bridge_headers,json=changed).status_code == 409
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/disconnect',headers=headers,json={}).status_code == 200
    assert client.post(url,headers=bridge_headers,json=payload()).status_code == 401
    assert client.get(f'/api/tenants/{tenant}/connections',headers=headers).json()['gateway']['status']=='DISCONNECTED'


def test_bridge_rejects_live_bar_and_stale_heartbeat_fails_closed(client):
    tenant,headers,bridge_headers = pairing(client)
    body=payload(); body['candles'][0]['time']=int(datetime.now(timezone.utc).timestamp())
    url = f'/api/tenants/{tenant}/mt5-bridge/heartbeat'
    assert client.post(url,headers=bridge_headers,json=body).status_code == 422
    assert client.post(url,headers=bridge_headers,json=payload()).status_code == 200
    from apps.api.app.core.database import db
    from apps.api.app.domain.mt5_bridge import read, save
    from apps.api.app.market.market_data import market_context
    with db() as conn:
        state = read(conn,tenant,'state')
        state['received_at']=(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat()
        save(conn,tenant,'state',state)
    assert client.get(f'/api/tenants/{tenant}/connections',headers=headers).json()['gateway']['status']=='DISCONNECTED'
    with db() as conn:
        assert market_context(conn)['active_provider'] is None


def test_uploaded_window_replaces_bars_the_broker_no_longer_has(client):
    tenant,headers,bridge_headers = pairing(client)
    url = f'/api/tenants/{tenant}/mt5-bridge/heartbeat'
    body = payload()
    first = body['candles'][0]
    body['candles'] = [{**first,'time':first['time']-3600*i} for i in (4,0)]
    response = client.post(url,headers=bridge_headers,json=body)
    assert response.status_code == 200, response.text
    account_id = response.json()['account_id']
    from apps.api.app.core.database import db
    def stored():
        with db() as conn:
            return [r['open_time'] for r in conn.execute("SELECT open_time FROM mi_provider_candle WHERE account_id=? AND symbol='EURUSD' AND timeframe='H1' ORDER BY open_time",(account_id,)).fetchall()]
    assert len(stored()) == 2
    body['candles'] = [{**first,'time':first['time']-3600*i} for i in (5,3,2,1,0)]
    assert client.post(url,headers=bridge_headers,json=body).status_code == 200
    expected = [datetime.fromtimestamp(first['time']-3600*i,timezone.utc).isoformat() for i in (5,3,2,1,0)]
    assert stored() == expected


def test_bridge_accepts_normalized_broker_time_and_preserves_month_boundary(client):
    tenant,headers,bridge_headers=pairing(client)
    body=payload()
    body['broker_utc_offset_seconds']=10800
    for item in [*body['quotes'],*body['candles']]:
        item['broker_time']=item['time']+10800
    now=datetime.now(timezone.utc)
    local_month_start=datetime(now.year,now.month,1,tzinfo=timezone.utc)
    previous_month=datetime(now.year-(now.month==1),12 if now.month==1 else now.month-1,1,tzinfo=timezone.utc)
    bar={**body['candles'][0],'timeframe':'MN','time':int((previous_month-timedelta(hours=3)).timestamp()),'broker_time':int(previous_month.timestamp())}
    body['candles'].append(bar)
    response=client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat',headers=bridge_headers,json=body)
    assert response.status_code==200,response.text
    from apps.api.app.core.database import db
    from apps.api.app.market.market_data import create_market_data_gateway
    with db() as conn:
        rows=create_market_data_gateway(conn).get_closed_candles('EURUSD','MN',count=1)
        assert rows[0].close_time==local_month_start-timedelta(hours=3)
    body['quotes'][0]['time']+=10800
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat',headers=bridge_headers,json=body).status_code==422
