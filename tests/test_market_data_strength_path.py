from contextlib import contextmanager
import sqlite3
from unittest.mock import Mock

from apps.api.app.market import market_data, strength_engine


def connection():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.executescript('''
        CREATE TABLE system_settings(key TEXT, value_json TEXT);
        CREATE TABLE ctrader_connections(tenant_id TEXT,environment TEXT,authorization_status TEXT,connection_status TEXT,last_error_code TEXT);
        CREATE TABLE ctrader_accounts(tenant_id TEXT,ctid_trader_account_id TEXT,environment TEXT,authorization_status TEXT);
    ''')
    return c


def test_unconfigured_provider_is_explicit(monkeypatch):
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'none')
    state = market_data.market_context(connection())
    assert state['provider_status'] == 'NOT CONFIGURED'
    assert state['symbols_resolved'] == 0
    assert len(state['missing_pairs']) == 28
    assert not state['market_data_ready']


def test_ctrader_requires_oauth_before_data(monkeypatch):
    from apps.api.app.routers import ctrader
    monkeypatch.setattr(ctrader, 'ctrader_config', lambda: {'configured': True})
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'ctrader')
    monkeypatch.setenv('MARKET_DATA_TENANT_ID', 't1')
    state = market_data.market_context(connection())
    assert state['provider_status'] == 'AUTHORIZATION REQUIRED'
    assert state['error_code'] == 'ctrader_authorization_required'
    assert not state['market_data_ready']


def test_authorized_connection_does_not_imply_selected_account(monkeypatch):
    from apps.api.app.routers import ctrader
    monkeypatch.setattr(ctrader, 'ctrader_config', lambda: {'configured': True})
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'ctrader')
    monkeypatch.setenv('MARKET_DATA_TENANT_ID', '')
    c = connection()
    c.execute("INSERT INTO ctrader_connections VALUES('t1','demo','AUTHORIZED','CONNECTED',NULL)")
    c.execute("INSERT INTO ctrader_accounts VALUES('t1','a1','demo','AUTHORIZED')")
    state = market_data.market_context(c)
    assert state['authorization_status'] == 'AUTHORIZED'
    assert state['account_status'] == 'DISCOVERED'
    assert state['error_code'] == 'market_data_scope_selection_required'
    assert not state['market_data_ready']


def test_unavailable_engine_never_calculates_or_loads_candles(monkeypatch):
    c = connection()
    @contextmanager
    def db():
        yield c
    monkeypatch.setattr(strength_engine, 'db', db)
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'none')
    calc = Mock(side_effect=AssertionError('No calculation without market data'))
    gateway = Mock(side_effect=AssertionError('No candle requests without authorization'))
    monkeypatch.setattr(strength_engine, 'CurrencyStrengthMatrixService', calc)
    monkeypatch.setattr(strength_engine, 'create_market_data_gateway', gateway)
    # Service construction is allowed; only calculate must stay unused.
    calc.side_effect = None
    engine = strength_engine.StrengthEngine()
    engine._tick()
    calc.return_value.calculate.assert_not_called()
    gateway.assert_not_called()
    payload = engine.payload()
    assert payload['matrix'] == []
    assert payload['meta']['engine_state'] == 'NOT CONFIGURED'
    assert payload['meta']['last_calculated_at'] is None


def test_stopped_worker_returns_diagnostics_without_seed_calculation(monkeypatch):
    c = connection()
    @contextmanager
    def db():
        yield c
    monkeypatch.setattr(strength_engine, 'db', db)
    monkeypatch.setattr(strength_engine, 'market_context', lambda c: dict(active_provider='ctrader', market_data_ready=True, provider_status='CONNECTED'))
    engine = strength_engine.StrengthEngine()
    engine.seed_from_db()
    assert engine.payload()['meta']['engine_state'] == 'WORKER_UNAVAILABLE'
    assert engine.payload()['matrix'] == []


def test_diagnostics_support_postgres_dictionary_rows(monkeypatch):
    from apps.api.app.routers import ctrader
    monkeypatch.setattr(ctrader, 'ctrader_config', lambda: {'configured': True})
    c = connection()
    c.execute('INSERT INTO system_settings VALUES(?,?)',
              ('market_data.provider', '{"provider":"ctrader"}'))

    class DictionaryCursor:
        def __init__(self, cursor):
            self.cursor = cursor
        def fetchone(self):
            row = self.cursor.fetchone()
            return dict(row) if row else None
        def fetchall(self):
            return [dict(row) for row in self.cursor.fetchall()]

    class DictionaryConnection:
        def execute(self, *args):
            return DictionaryCursor(c.execute(*args))

    monkeypatch.setenv('MARKET_DATA_TENANT_ID', '')
    state = market_data.market_context(DictionaryConnection())
    assert state['provider_status'] == 'AUTHORIZATION REQUIRED'
    assert state['accounts_discovered'] == 0


def test_status_api_returns_unavailable_state_without_constructing_adapter(monkeypatch):
    from apps.api.app.routers import market_intelligence
    c = connection()
    @contextmanager
    def db():
        yield c
    monkeypatch.setenv('MARKET_DATA_PROVIDER', 'none')
    monkeypatch.setattr(market_intelligence, 'db', db)
    monkeypatch.setattr(strength_engine, 'db', db)
    engine = strength_engine.StrengthEngine()
    monkeypatch.setattr(market_intelligence, 'get_strength_engine', lambda: engine)
    gateway = Mock(side_effect=AssertionError('Status must not connect'))
    monkeypatch.setattr(market_intelligence, 'create_market_data_gateway', gateway)
    state = market_intelligence.mi_status()['market_data']
    assert state['provider_status'] == 'NOT CONFIGURED'
    assert state['engine_state'] == 'NOT CONFIGURED'
    gateway.assert_not_called()
