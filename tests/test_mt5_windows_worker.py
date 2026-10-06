from types import SimpleNamespace
from unittest.mock import Mock
import pytest
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
