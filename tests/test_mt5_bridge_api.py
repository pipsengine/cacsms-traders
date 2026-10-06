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
