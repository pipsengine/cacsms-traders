from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sqlite3
from unittest.mock import Mock

import pytest

from apps.api.app.market.provider_manager import ProviderManager, select_provider
from apps.api.app.market.models import Candle, StrengthPoint
from apps.api.app.market.repository import MarketRepository
from apps.api.app.market.normalized_provider import NormalizedProvider, candle_close
from apps.api.app.market.ingestion import CandleIngestionService, missing_candles
from apps.api.app.market.h8_aggregate import aggregate_h8_from_h1
from apps.api.app.domain.execution_binding import bind_campaign
from apps.api.app.market.constants import FX_PAIRS_28, MATRIX_TIMEFRAMES
from apps.api.app.market.csm_service import CurrencyStrengthMatrixService
from apps.api.app.market.strength_history import load_score_series

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.now(timezone.utc)
T0 = datetime(2026, 1, 5, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    connection = sqlite3.connect(':memory:',check_same_thread=False)
    connection.row_factory = sqlite3.Row
    for path in sorted((ROOT / 'database/migrations').glob('*.sql')):
        connection.executescript(path.read_text(encoding='utf-8'))
    yield connection
    connection.close()


def candle(source='mt5', opened=T0, value=1.0, tf='H1'):
    return Candle('EURUSD', tf, opened, candle_close(opened, tf), value, value + .2, value - .2, value + .1, source=source)


@pytest.mark.parametrize('mt5,ctrader,mode,expected', [
    (True, False, 'AUTO', 'mt5'), (False, True, 'AUTO', 'ctrader'),
    (True, True, 'AUTO', 'mt5'), (False, False, 'AUTO', None),
    (True, True, 'MT5_PREFERRED', 'mt5'), (True, True, 'CTRADER_PREFERRED', 'ctrader'),
    (False, True, 'MT5_PREFERRED', 'ctrader'), (True, False, 'CTRADER_PREFERRED', 'mt5'),
])
def test_selection_matrix(mt5, ctrader, mode, expected):
    states = {p: dict(healthy=ready, market_data_available=ready) for p, ready in [('mt5', mt5), ('ctrader', ctrader)]}
    assert select_provider(states, mode) == expected


def test_unhealthy_data_is_not_selectable():
    assert select_provider({'mt5': dict(healthy=False, market_data_available=True), 'ctrader': dict(healthy=False, market_data_available=False)}) is None


def test_snapshots_finalize_on_provider_or_account_change(conn):
    manager = ProviderManager(conn)
    first = manager.bind_snapshot('mt5', 'm1')
    assert manager.bind_snapshot('mt5', 'm1') == first
    second = manager.bind_snapshot('ctrader', 'c1')
    assert second != first
    assert conn.execute('SELECT finalized_at FROM mi_provider_snapshot WHERE id=?', (first,)).fetchone()[0]
    assert conn.execute('SELECT COUNT(*) FROM mi_provider_snapshot WHERE finalized_at IS NULL').fetchone()[0] == 1
    assert manager.bind_snapshot('ctrader', 'c2') != second


def test_provider_bars_do_not_overwrite_or_mix(conn):
    mt5 = MarketRepository(conn, provider='mt5')
    ctrader = MarketRepository(conn, provider='ctrader')
    for i in range(3):
        mt5.upsert_candle(candle(opened=T0 + timedelta(hours=i), value=1+i))
        ctrader.upsert_candle(candle('ctrader', T0 + timedelta(hours=i), value=10+i))
    mt5.upsert_candle(candle())
    assert conn.execute('SELECT COUNT(*) FROM mi_provider_candle').fetchone()[0] == 6
    assert mt5.closes_by_timeframe('H1')['EURUSD'] == [1.1, 2.1, 3.1]
    assert ctrader.closes_by_timeframe('H1')['EURUSD'] == [10.1, 11.1, 12.1]
    with pytest.raises(ValueError, match='Mixed-provider'):
        mt5.upsert_candle(candle('ctrader'))
    assert not mt5.upsert_candle(replace(candle(), is_closed=False))
    assert not mt5.upsert_candle(candle(opened=NOW + timedelta(hours=1)))


def test_history_reference_excludes_previous_provider_snapshot(conn):
    manager = ProviderManager(conn)
    first = manager.bind_snapshot('mt5', 'm1')
    repo = MarketRepository(conn, provider='mt5', snapshot_id=first)
    repo.save_strength(StrengthPoint('EUR', 'AVG', T0, 1, score=80))
    second = manager.bind_snapshot('ctrader', 'c1')
    repo = MarketRepository(conn, provider='ctrader', snapshot_id=second)
    repo.save_strength(StrengthPoint('EUR', 'AVG', T0 + timedelta(hours=1), -1, score=20))
    series = load_score_series(conn, 'AVG', T0, ('EUR',))
    assert series['EUR'] == [(T0 + timedelta(hours=1), 20)]
    assert repo.score_history('EUR') == [((T0 + timedelta(hours=1)).isoformat(), 20)]


def test_execution_ownership_survives_market_data_failover(conn):
    bind_campaign(conn, 'campaign-1', 'mt5', 'm1')
    ProviderManager(conn).bind_snapshot('ctrader', 'c1')
    assert bind_campaign(conn, 'campaign-1', 'mt5', 'm1')['provider'] == 'mt5'
    with pytest.raises(ValueError, match='immutable'):
        bind_campaign(conn, 'campaign-1', 'ctrader', 'c1')
    with pytest.raises(ValueError, match='explicit'):
        bind_campaign(conn, 'campaign-2', 'mt5', '')


def test_normalized_history_deduplicates_and_excludes_forming_bars():
    adapter = Mock()
    adapter.closed_candles.return_value = [candle(), candle(), candle(opened=NOW + timedelta(hours=1))]
    gateway = NormalizedProvider(adapter, 'mt5')
    rows = gateway.get_closed_candles('EUR/USD', 'H1')
    assert len(rows) == 1
    assert rows[0].source == 'mt5' and rows[0].symbol == 'EURUSD'
    assert rows[0].close_time == T0 + timedelta(hours=1)
    assert candle_close(datetime(2024, 2, 1, tzinfo=timezone.utc), 'MN') == datetime(2024, 3, 1, tzinfo=timezone.utc)


def test_missing_and_stale_candles_are_reported_not_fabricated(conn):
    gateway = Mock()
    gateway.closed_candles.return_value = [candle(), candle(opened=T0 + timedelta(hours=2))]
    result = CandleIngestionService(gateway, MarketRepository(conn, provider='mt5')).sync('EURUSD', 'H1')
    assert result['quality']['missing_bars'] == 1
    assert result['error'] == 'missing_candles'
    assert conn.execute('SELECT COUNT(*) FROM mi_provider_candle').fetchone()[0] == 2
    gateway.closed_candles.return_value = [candle(), candle(opened=T0 + timedelta(hours=1))]
    assert CandleIngestionService(gateway, MarketRepository(conn, provider='mt5')).sync('EURUSD', 'H1')['error'] == 'stale_candles'


def test_h8_refuses_mixed_sources_and_noncontiguous_bars():
    rows = [candle(opened=T0 + timedelta(hours=i)) for i in range(8)]
    assert len(aggregate_h8_from_h1(rows)) == 1
    assert not aggregate_h8_from_h1([*rows[:7], replace(rows[7], source='ctrader')])
    assert not aggregate_h8_from_h1([*rows[:7], rows[6]])


@pytest.mark.parametrize('source', ['mt5', 'ctrader'])
def test_real_28_pair_strength_methodology_is_provider_independent(source, conn):
    repo = MarketRepository(conn, provider=source)
    for tf in ('M1', 'M5', 'M15', 'H1', 'H8', 'W1', 'MN'):
        times = [datetime(2025, 10, 1, tzinfo=timezone.utc), datetime(2025, 11, 1, tzinfo=timezone.utc)] if tf=='MN' else [T0-timedelta(days=20), T0-timedelta(days=10)]
        for pair in FX_PAIRS_28:
            for i, at in enumerate(times):
                repo.upsert_candle(replace(candle(source, at, value=1.0+i*.1, tf=tf), symbol=pair))
    for pair in FX_PAIRS_28:
        for i, at in enumerate((datetime(2025,9,1,tzinfo=timezone.utc),datetime(2025,12,31,tzinfo=timezone.utc),datetime(2026,1,4,tzinfo=timezone.utc))):
            repo.upsert_candle(replace(candle(source, at, value=1.0+i*.1, tf='D1'), symbol=pair))
    result = CurrencyStrengthMatrixService(repo).calculate(as_of=T0)
    assert result.pairs_loaded == 28
    assert result.historical_ok
    assert len(result.values) == 8
    assert result.values['AUD']['H1'] != result.values['USD']['H1']
    assert repo.provider == source


def test_inactive_ctrader_does_not_construct_or_retry_adapter(conn, monkeypatch):
    from apps.api.app.market import market_data
    from apps.api.app.market import provider_manager
    def context(_conn, cfg):
        return dict(active_provider=cfg['provider'], provider_status='APP_INACTIVE' if cfg['provider']=='ctrader' else 'DISCONNECTED',
                    authorization_status='PENDING_PROVIDER_ACTIVATION', market_data_ready=False, error_code='CTRADER_APP_INACTIVE')
    monkeypatch.setattr(provider_manager, 'provider_context', context)
    gateway = Mock(side_effect=AssertionError('Must not retry inactive OAuth'))
    from apps.api.app.market import ctrader_gateway
    monkeypatch.setattr(ctrader_gateway, 'CTraderGateway', gateway)
    for _ in range(3):
        assert not market_data.market_context(conn)['market_data_ready']
        ProviderManager(conn).refresh_health()
    gateway.assert_not_called()


def test_health_disconnect_recovery_and_audit(conn, monkeypatch):
    from apps.api.app.market import provider_manager
    monkeypatch.setattr(provider_manager, 'provider_context', lambda c, cfg: dict(provider_status='CONNECTED', authorization_status='AUTHORIZED', market_data_ready=True, error_code=None))
    manager = ProviderManager(conn)
    manager.observe('ctrader', success=True, data_available=True)
    manager.observe('mt5', success=True, data_available=True)
    manager.observe('mt5', success=False, error='connection_lost')
    assert manager.context()['active_provider'] == 'ctrader'
    manager.observe('mt5', success=True, data_available=True)
    assert manager.context()['active_provider'] == 'mt5'
    actions = {r[0] for r in conn.execute('SELECT action FROM audit_events').fetchall()}
    assert {'PROVIDER_CONNECTED', 'PROVIDER_DISCONNECTED', 'PROVIDER_DEGRADED', 'PROVIDER_RECOVERED'} <= actions
    state = manager.context()['providers']['mt5']
    assert state['last_heartbeat'] and state['last_market_data']
    assert not state['execution_available']


def test_account_isolation_and_finalized_snapshot_refusal(conn):
    manager = ProviderManager(conn)
    first = manager.bind_snapshot('mt5', 'account-1')
    original = MarketRepository(conn, provider='mt5', snapshot_id=first)
    original.upsert_candle(replace(candle(), account_id='account-1'))
    second = manager.bind_snapshot('mt5', 'account-2')
    current = MarketRepository(conn, provider='mt5', snapshot_id=second)
    current.upsert_candle(replace(candle(value=10), account_id='account-2'))
    assert current.closes_by_timeframe('H1')['EURUSD'] == [10.1]
    assert original.closes_by_timeframe('H1')['EURUSD'] == [1.1]
    with pytest.raises(ValueError, match='finalized'):
        original.save_strength(StrengthPoint('EUR', 'AVG', T0, 1))


def test_incremental_sync_detects_an_outage_gap(conn):
    repo = MarketRepository(conn, provider='mt5')
    repo.upsert_candle(candle())
    adapter = Mock()
    adapter.closed_candles.return_value = [candle(opened=T0+timedelta(hours=5)), candle(opened=T0+timedelta(hours=6))]
    result = CandleIngestionService(adapter,repo).sync('EURUSD','H1',2)
    assert result['quality']['missing_bars'] == 4
    assert result['error'] == 'missing_candles'


def test_factory_pins_the_normalized_provider_and_account(conn, monkeypatch):
    from apps.api.app.market import market_data, mt5_gateway
    adapter = Mock()
    adapter.get_account_context.return_value = dict(provider='mt5',account_id='m1',environment='demo')
    adapter.closed_candles.return_value = [candle()]
    monkeypatch.setattr(mt5_gateway,'create_market_data_gateway',lambda:adapter)
    gateway = market_data.create_market_data_gateway(conn, context=dict(active_provider='mt5',market_data_ready=True))
    repo = MarketRepository(conn)
    assert repo.provider == 'mt5' and repo.account_id == 'm1'
    assert repo.snapshot_id == gateway.snapshot_id
    bar = gateway.get_closed_candles('EUR/USD','H1')[0]
    assert bar.symbol == 'EURUSD' and bar.account_id == 'm1'
    assert repo.upsert_candle(bar)
    health = gateway.get_provider_health()
    assert {'configured','authorized','connected','healthy','market_data_available','execution_available','last_heartbeat','last_market_data','last_error','environment'} <= health.keys()
    assert not health['execution_available']


def test_provider_policy_api_requires_admin_and_preserves_execution_binding(conn, monkeypatch):
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from apps.api.app.routers import providers
    from apps.api.app.deps import current_user
    @contextmanager
    def db():
        yield conn
    monkeypatch.setattr(providers,'db',db)
    monkeypatch.setattr(providers,'market_context',lambda c:dict(active_provider=None,market_data_ready=False,providers={}))
    app = FastAPI()
    app.include_router(providers.router)
    client = TestClient(app)
    assert client.get('/api/providers').status_code == 401
    app.dependency_overrides[current_user] = lambda:dict(id='u',is_platform_admin=0)
    assert client.get('/api/providers').status_code == 403
    app.dependency_overrides[current_user] = lambda:dict(id=None,is_platform_admin=1)
    bind_campaign(conn,'campaign','mt5','m1')
    assert client.put('/api/providers/selection',json=dict(selection_mode='CTRADER_PREFERRED')).status_code == 200
    assert configuration_mode(conn) == 'CTRADER_PREFERRED'
    assert conn.execute("SELECT provider FROM execution_provider_binding WHERE campaign_id='campaign'").fetchone()[0] == 'mt5'
    assert client.put('/api/providers/selection',json=dict(selection_mode='CTRADER_PREFERRED',tenant_id='other',account_id='unverified')).status_code == 400


def configuration_mode(conn):
    return json.loads(conn.execute("SELECT value_json FROM system_settings WHERE key='market_data.provider'").fetchone()[0])['selection_mode']


def test_production_autonomous_modes_remain_disabled(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from apps.api.app.routers import platform
    monkeypatch.setattr(platform,'app_env',lambda:'production')
    for mode in ('SHADOW','DEMO_AUTONOMOUS','LIVE_AUTONOMOUS'):
        with pytest.raises(HTTPException) as exc:
            platform.set_mode(SimpleNamespace(mode=mode),dict(is_platform_admin=1))
        assert exc.value.status_code == 403


def test_account_switch_during_provider_read_is_refused():
    from apps.api.app.market.provider_contract import MarketDataUnavailable
    adapter = Mock()
    pinned = dict(account_id='m1',environment='demo')
    adapter.get_account_context.side_effect = [pinned,dict(account_id='m2',environment='demo')]
    adapter.closed_candles.return_value = [candle()]
    gateway = NormalizedProvider(adapter,'mt5',pinned)
    with pytest.raises(MarketDataUnavailable,match='provider_account_changed'):
        gateway.get_closed_candles('EURUSD','H1')


def test_stale_probe_cannot_keep_strength_bootstrapped():
    from apps.api.app.market.provider_contract import MarketDataUnavailable
    adapter = Mock()
    adapter.closed_candles.return_value = [candle()]
    gateway = NormalizedProvider(adapter,'mt5')
    with pytest.raises(MarketDataUnavailable,match='stale_or_missing'):
        gateway.latest_closed_open_time('EURUSD','H1')


def test_protocol_inactive_rejection_blocks_subsequent_worker_probes(conn,monkeypatch):
    from types import SimpleNamespace
    from apps.api.app.market.ctrader_gateway import CTraderGateway
    from apps.api.app.market.provider_contract import MarketDataUnavailable
    from apps.api.app.services.ctrader_application_state import application_state
    from apps.api.app.routers import ctrader
    import subprocess
    gateway = object.__new__(CTraderGateway)
    gateway._conn = conn
    gateway._token = 'test-token'
    gateway.account_id = 'test-account'
    request = Mock(return_value=SimpleNamespace(returncode=1,stdout='CTRADER_RESULT:'+json.dumps({'error':'CTRADER_APP_INACTIVE'})))
    monkeypatch.setattr(subprocess,'run',request)
    monkeypatch.setattr(ctrader,'ctrader_config',lambda:dict(configured=True))
    with pytest.raises(MarketDataUnavailable,match='CTRADER_APP_INACTIVE'):
        gateway.get_symbols()
    assert application_state(conn) == 'APP_INACTIVE'
    for _ in range(3):
        ProviderManager(conn).refresh_health()
    assert request.call_count == 1
