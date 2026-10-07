from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import io
import urllib.error

from test_api import client, _login
from test_mt5_bridge_api import pairing, payload
from apps.api.app.market import live
from apps.api.app.market.live import chart_forming, forming_bar

UTC = timezone.utc


def bar(ot, seconds, o, h, l, c, v=1):
    return (ot, ot + timedelta(seconds=seconds), o, h, l, c, v)


def table(data):
    return lambda tf: data.get(tf, [])


def test_d1_forming_bar_tiles_finer_bars_then_the_tick():
    day_open = datetime(2026, 10, 6, 21, tzinfo=UTC)
    h1 = [bar(day_open + timedelta(hours=i), 3600, 1.0 + i / 100, 1.005 + i / 100, 0.995 + i / 100, 1.002 + i / 100) for i in range(13)]
    m30 = [bar(datetime(2026, 10, 7, 9, 30, tzinfo=UTC), 1800, 9, 9, 9, 9), bar(datetime(2026, 10, 7, 10, tzinfo=UTC), 1800, 1.13, 1.2, 1.12, 1.15)]
    m1 = [bar(datetime(2026, 10, 7, 10, 29, tzinfo=UTC), 60, 9, 9, 9, 9), bar(datetime(2026, 10, 7, 10, 30, tzinfo=UTC), 60, 1.15, 1.16, 0.9, 1.155)]
    rows = table({'D1': [bar(day_open - timedelta(days=1), 86400, 1, 1, 1, 1)], 'H1': h1, 'M30': m30, 'M1': m1})
    now = datetime(2026, 10, 7, 10, 31, 30, tzinfo=UTC)
    out = forming_bar(rows, 'D1', 1.17, now - timedelta(seconds=5), now)
    assert out['t'] == day_open
    assert out['o'] == 1.0 and out['h'] == 1.2 and out['l'] == 0.9 and out['c'] == 1.17
    assert out['v'] == 15
    assert forming_bar(rows, 'D1', 5.0, day_open - timedelta(seconds=1), now)['c'] == 1.155


def test_weekend_gap_keeps_broker_alignment_and_no_tick_means_no_bar():
    friday_close = datetime(2026, 10, 2, 21, tzinfo=UTC)
    rows = table({'D1': [bar(friday_close - timedelta(days=1), 86400, 1, 1, 1, 1)]})
    monday = datetime(2026, 10, 5, 10, tzinfo=UTC)
    out = forming_bar(rows, 'D1', 1.5, monday - timedelta(seconds=2), monday)
    assert out['t'] == datetime(2026, 10, 4, 21, tzinfo=UTC)
    assert out['o'] == out['c'] == 1.5
    assert forming_bar(rows, 'D1', None, None, monday) is None


def test_year_chart_merges_the_forming_month_into_the_calendar_aggregate():
    months = [bar(datetime(2026, m, 1, tzinfo=UTC), 86400 * 28, 1.0 + m / 10, 1.05 + m / 10, 0.95 + m / 10, 1.01 + m / 10) for m in range(1, 10)]
    months[-1] = (months[-1][0], datetime(2026, 10, 1, tzinfo=UTC), *months[-1][2:])
    rows = table({'MN': months, 'D1': [bar(datetime(2026, 10, 1, tzinfo=UTC), 86400, 2.0, 2.5, 1.9, 2.4)]})
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    out = chart_forming(rows, 'Y', 2.6, now, now)
    assert out['t'] == datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    assert out['o'] == months[0][2] and out['h'] == 2.6 and out['c'] == 2.6 and out['l'] == months[0][4]
    assert chart_forming(rows, 'MN', 2.6, now, now)['t'] == datetime(2026, 10, 1, tzinfo=UTC).isoformat()


def _quotes_url(tenant):
    return f'/api/tenants/{tenant}/mt5-bridge/quotes'


def _frame(bid, at):
    return {'quotes': [{'symbol': 'EURUSD', 'provider_symbol': 'EURUSD', 'bid': bid, 'ask': bid + .0001, 'time': at, 'digits': 5, 'tick_size': .00001, 'pip_size': .0001}],
            'broker_utc_offset_seconds': 0}


def _bid():
    from apps.api.app.core.database import db
    from apps.api.app.market.market_data import create_market_data_gateway
    with db() as conn:
        gateway = create_market_data_gateway(conn)
        gateway.observer = None
        return gateway.get_latest_price('EURUSD')['bid']


def test_quote_frames_need_auth_and_a_heartbeat_and_newest_tick_wins(client):
    tenant, headers, bridge_headers = pairing(client)
    now = int(datetime.now(UTC).timestamp())
    assert client.post(_quotes_url(tenant), json=_frame(1.2, now)).status_code == 401
    assert client.post(_quotes_url(tenant), headers=bridge_headers, json=_frame(1.2, now)).status_code == 409
    body = payload()
    body['quotes'][0]['time'] = now - 10
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat', headers=bridge_headers, json=body).status_code == 200
    shifted = _frame(1.2, now - 2)
    shifted['broker_utc_offset_seconds'] = 3600
    shifted['quotes'][0]['broker_time'] = now - 2 + 3600
    assert client.post(_quotes_url(tenant), headers=bridge_headers, json=shifted).status_code == 409
    response = client.post(_quotes_url(tenant), headers=bridge_headers, json=_frame(1.2, now - 2))
    assert response.status_code == 200, response.text
    assert _bid() == 1.2
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat', headers=bridge_headers, json=body).status_code == 200
    assert _bid() == 1.2


def test_live_endpoint_returns_quote_and_display_only_forming_bar(client):
    tenant, headers, bridge_headers = pairing(client)
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat', headers=bridge_headers, json=payload()).status_code == 200
    assert client.post(f'/api/tenants/{tenant}/connections/sync-registry', headers=headers, json={}).status_code == 200
    now = int(datetime.now(UTC).timestamp())
    assert client.post(_quotes_url(tenant), headers=bridge_headers, json=_frame(1.1234, now)).status_code == 200
    live._cache.clear()
    response = client.get('/api/market-intelligence/scanner/EURUSD/live', params={'timeframes': 'H1,D1'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['display_only'] is True
    assert data['quote']['bid'] == 1.1234 and data['quote']['stale'] is False
    h1 = data['forming']['H1']
    assert h1['c'] == 1.1234 and h1['h'] >= 1.1234 >= h1['l']
    assert client.get('/api/market-intelligence/scanner/EURUSD/live', params={'timeframes': 'M2'}).status_code == 400
    assert client.get('/api/market-intelligence/scanner/NOPE/live').status_code == 400


def test_stale_quote_on_live_endpoint_never_degrades_market_data(client):
    tenant, headers, bridge_headers = pairing(client)
    body = payload()
    body['quotes'].append({**body['quotes'][0], 'symbol': 'GBPUSD', 'provider_symbol': 'GBPUSD', 'time': body['quotes'][0]['time'] - 600})
    assert client.post(f'/api/tenants/{tenant}/mt5-bridge/heartbeat', headers=bridge_headers, json=body).status_code == 200
    from apps.api.app.core.database import db
    from apps.api.app.market.market_data import market_context
    for _ in range(2):
        live._cache.clear()
        data = client.get('/api/market-intelligence/scanner/GBPUSD/live', params={'timeframes': 'H1'}).json()
        assert data['quote'] is None and data['error'] == 'mt5_bridge_quote_stale'
    with db() as conn:
        assert market_context(conn)['market_data_ready'] is True


def test_quote_push_never_stops_the_bridge():
    from apps.api.app.domain.mt5_windows_worker import WindowsBridge
    worker = WindowsBridge('broker/terminal64.exe', sdk=Mock())
    sample = {'quotes': [{'symbol': 'EURUSD'}], 'broker_utc_offset_seconds': 0}

    def fail(code):
        return Mock(side_effect=urllib.error.HTTPError('u', code, 'x', {}, io.BytesIO(b'{}')))

    worker._request = fail(404)
    assert worker.push_quotes(sample) is False
    for code in (401, 409, 500):
        worker._request = fail(code)
        assert worker.push_quotes(sample) is True
    assert not worker.stop.is_set()
    assert worker.push_quotes({'quotes': [], 'broker_utc_offset_seconds': 0}) is True
