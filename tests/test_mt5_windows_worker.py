from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from datetime import datetime, timezone
from apps.api.app.domain.mt5_windows_worker import WindowsBridge


def sdk():
    account = SimpleNamespace(login=123,server='Demo',company='Broker',currency='USD',trade_mode=0,balance=100.,equity=100.,margin=0.,margin_free=100.,leverage=100)
    return Mock(terminal_info=Mock(return_value=SimpleNamespace(connected=True)),account_info=Mock(return_value=account),symbols_get=Mock(return_value=[]))


def test_attachment_reuses_running_terminal_without_launching():
    terminal = sdk()
    worker = WindowsBridge('broker/terminal64.exe',sdk=terminal)
    worker.sample(history=False)
    terminal.initialize.assert_not_called()
    terminal.order_send.assert_not_called()


def test_offline_terminal_never_reports_connected():
    terminal = sdk()
    terminal.terminal_info.return_value.connected = False
    with pytest.raises(RuntimeError,match='offline'):
        WindowsBridge('broker/terminal64.exe',sdk=terminal).attach()


def test_account_change_stops_sampling():
    worker = WindowsBridge('broker/terminal64.exe',sdk=sdk())
    worker.session = {'identity':'Other/456'}
    with pytest.raises(RuntimeError,match='account changed'):
        worker.sample(history=False)


def test_pairing_cannot_select_arbitrary_upload_destination():
    worker = WindowsBridge('broker/terminal64.exe',sdk=sdk())
    with pytest.raises(ValueError):
        worker.connect('tenant','a'*64,'https://unrelated.example')
    worker.sdk.initialize.assert_not_called()


def test_connect_requires_cloud_acknowledgement(monkeypatch):
    worker = WindowsBridge('broker/terminal64.exe',sdk=sdk())
    worker.upload = Mock(side_effect=RuntimeError('Cloud did not accept heartbeat'))
    with pytest.raises(RuntimeError,match='did not accept'):
        worker.connect('tenant','a'*64,'https://cacsms-traders.vercel.app')
    assert worker.session is None
    assert worker.thread is None
    worker.sdk.initialize.assert_not_called()


def test_broker_three_hour_clock_is_normalized_without_refreshing_stale_ticks():
    terminal = sdk()
    terminal.symbols_get.return_value = [SimpleNamespace(name='EURUSD')]
    terminal.symbol_select.return_value = True
    terminal.symbol_info.return_value = SimpleNamespace(digits=5,trade_tick_size=.00001,point=.00001)
    stamp=int(datetime.now(timezone.utc).timestamp())
    terminal.symbol_info_tick.return_value = SimpleNamespace(time=stamp+10800,bid=1.1,ask=1.1001)
    worker=WindowsBridge('broker/terminal64.exe',sdk=terminal)
    body=worker.sample(history=False)
    assert body['broker_utc_offset_seconds']==10800
    assert body['quotes'][0]['time']==stamp
    assert body['quotes'][0]['broker_time']==stamp+10800
    terminal.symbol_info_tick.return_value.time=stamp+10800-300
    assert worker.sample(history=False)['quotes'][0]['time']==stamp-300


def test_weekend_ticks_are_never_shifted_to_the_present():
    terminal = sdk()
    terminal.symbols_get.return_value=[SimpleNamespace(name='EURUSD')]
    terminal.symbol_info.return_value=SimpleNamespace(digits=5,trade_tick_size=.00001,point=.00001)
    stamp=int(datetime.now(timezone.utc).timestamp())-172800
    terminal.symbol_info_tick.return_value=SimpleNamespace(time=stamp,bid=1.1,ask=1.1001)
    body=WindowsBridge('broker/terminal64.exe',sdk=terminal).sample(history=False)
    assert body['quotes'][0]['time']==stamp
