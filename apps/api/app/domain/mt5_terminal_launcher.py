"""Visible MT5 launch on a Windows gateway, independent of the Python MT5 SDK."""
import os
import subprocess
from pathlib import Path
from .mt5_terminal_discovery import normalize_terminal_exe, running_terminal64_processes


def terminal_launch_capability():
    local = os.name == 'nt' and not os.getenv('VERCEL')
    return {'terminal_launch_mode': 'WINDOWS_GATEWAY' if local else 'WINDOWS_GATEWAY_REQUIRED', 'terminal_launch_supported': local}


def launch_terminal(path):
    if not terminal_launch_capability()['terminal_launch_supported']:
        return dict(ok=False, code='MT5_WINDOWS_GATEWAY_REQUIRED', error='No Windows MT5 gateway is connected. This API cannot open the terminal on another machine.')
    executable = normalize_terminal_exe(path or '')
    if not executable or Path(executable).name.lower() != 'terminal64.exe':
        return dict(ok=False, code='MT5_TERMINAL_PATH_REQUIRED', error='Select the installed broker terminal64.exe in MT5 settings.')
    if any(os.path.normcase(p) == os.path.normcase(executable) for p in running_terminal64_processes()):
        return dict(ok=True, code='MT5_TERMINAL_ALREADY_RUNNING', path=executable, launched=False)
    try:
        # The user explicitly requests a visible terminal. No shell or command interpolation.
        subprocess.Popen([executable], cwd=str(Path(executable).parent), close_fds=True)
    except OSError:
        return dict(ok=False, code='MT5_TERMINAL_LAUNCH_FAILED', error='Windows could not open the configured MT5 terminal. Check the installation and gateway user permissions.')
    return dict(ok=True, code='MT5_TERMINAL_STARTED', path=executable, launched=True)
