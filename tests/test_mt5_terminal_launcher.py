from unittest.mock import Mock
from apps.api.app.domain import mt5_terminal_launcher as launcher
from apps.api.app.domain import mt5_connection


def test_visible_terminal_launch_uses_exact_executable_without_shell(tmp_path, monkeypatch):
    terminal = tmp_path / 'Broker MT5' / 'terminal64.exe'
    terminal.parent.mkdir()
    terminal.write_bytes(b'')
    monkeypatch.setattr(launcher, 'terminal_launch_capability', lambda: {'terminal_launch_supported': True})
    monkeypatch.setattr(launcher, 'running_terminal64_processes', lambda: [])
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    result = launcher.launch_terminal(str(terminal))
    assert result['ok'] and result['launched']
    spawn.assert_called_once_with([str(terminal.resolve())], cwd=str(terminal.parent.resolve()), close_fds=True)


def test_already_running_terminal_is_not_duplicated(tmp_path, monkeypatch):
    terminal = tmp_path / 'terminal64.exe'
    terminal.write_bytes(b'')
    monkeypatch.setattr(launcher, 'terminal_launch_capability', lambda: {'terminal_launch_supported': True})
    monkeypatch.setattr(launcher, 'running_terminal64_processes', lambda: [str(terminal.resolve())])
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    result = launcher.launch_terminal(str(terminal))
    assert result['ok'] and not result['launched']
    spawn.assert_not_called()


def test_other_executables_cannot_be_launched(tmp_path, monkeypatch):
    executable = tmp_path / 'arbitrary.exe'
    executable.write_bytes(b'')
    monkeypatch.setattr(launcher, 'terminal_launch_capability', lambda: {'terminal_launch_supported': True})
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    assert launcher.launch_terminal(str(executable))['code'] == 'MT5_TERMINAL_PATH_REQUIRED'
    spawn.assert_not_called()


def test_process_launch_failure_is_explicit(tmp_path, monkeypatch):
    terminal = tmp_path / 'terminal64.exe'
    terminal.write_bytes(b'')
    monkeypatch.setattr(launcher, 'terminal_launch_capability', lambda: {'terminal_launch_supported': True})
    monkeypatch.setattr(launcher, 'running_terminal64_processes', lambda: [])
    monkeypatch.setattr(launcher.subprocess, 'Popen', Mock(side_effect=OSError('denied')))
    result = launcher.launch_terminal(str(terminal))
    assert not result['ok'] and result['code'] == 'MT5_TERMINAL_LAUNCH_FAILED'


def test_hosted_api_requires_desktop_companion_without_launching(monkeypatch):
    monkeypatch.setenv('VERCEL', '1')
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    assert launcher.terminal_launch_capability()['terminal_launch_mode'] == 'DESKTOP_COMPANION'
    assert launcher.launch_terminal('terminal64.exe')['code'] == 'MT5_DESKTOP_COMPANION_REQUIRED'
    spawn.assert_not_called()


def test_connect_opens_terminal_even_when_python_sdk_is_missing(monkeypatch):
    gateway = mt5_connection.LocalMT5Gateway('tenant')
    settings = dict(terminal_path='broker/terminal64.exe')
    monkeypatch.setattr(gateway, '_load_settings', lambda conn: settings)
    monkeypatch.setattr(gateway, '_save_settings', Mock())
    monkeypatch.setattr(gateway, '_health', lambda conn: {'status': 'DISCONNECTED'})
    monkeypatch.setattr(mt5_connection, 'terminal_launch_capability', lambda: {'terminal_launch_supported': True})
    monkeypatch.setattr(mt5_connection, 'normalize_terminal_exe', lambda path: path)
    sequence = []
    def launch(path):
        sequence.append('launch')
        return dict(ok=True, launched=True, path=path)
    def package():
        sequence.append('sdk')
        return dict(python_package='missing', hint='Install the SDK on the Windows gateway.')
    monkeypatch.setattr(mt5_connection, 'launch_terminal', launch)
    monkeypatch.setattr(mt5_connection, 'mt5_python_package_status', package)
    result = gateway.connect(conn=Mock())
    assert sequence == ['launch', 'sdk']
    assert result['terminal_launch']['launched']
    assert not result['ok'] and result['code'] == 'MT5_PACKAGE_MISSING'


def test_hosted_connect_does_not_discover_or_initialize_a_desktop(monkeypatch):
    gateway = mt5_connection.LocalMT5Gateway('tenant')
    monkeypatch.setattr(gateway, '_load_settings', lambda conn: {})
    monkeypatch.setattr(mt5_connection, 'terminal_launch_capability', lambda: {'terminal_launch_supported': False})
    discover = Mock(side_effect=AssertionError('Hosted API cannot discover the client PC'))
    monkeypatch.setattr(mt5_connection, 'auto_detect_terminal_path', discover)
    result = gateway.connect(conn=Mock())
    assert result['code'] == 'MT5_DESKTOP_COMPANION_REQUIRED'
    discover.assert_not_called()
