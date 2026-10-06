"""Visible MT5 launch on a Windows gateway, independent of the Python MT5 SDK."""
import os
import subprocess
from pathlib import Path
from .mt5_terminal_discovery import normalize_terminal_exe, running_terminal64_processes


def restore_terminal_window(executable):
    """Restore only windows owned by the configured broker executable."""
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    restored = []
    @callback_type
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = kernel.OpenProcess(0x1000, False, pid.value)
        if process:
            try:
                size = wintypes.DWORD(32768)
                path = ctypes.create_unicode_buffer(size.value)
                if kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)) and os.path.normcase(path.value) == os.path.normcase(executable):
                    user.ShowWindow(hwnd, 9)  # SW_RESTORE
                    restored.append(bool(user.SetForegroundWindow(hwnd)))
            finally:
                kernel.CloseHandle(process)
        return True
    user.EnumWindows(visit, 0)
    return bool(restored)


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
        restored = restore_terminal_window(executable)
        return dict(ok=True, code='MT5_TERMINAL_ALREADY_RUNNING', path=executable, launched=False, restored=restored)
    try:
        # The user explicitly requests a visible terminal. No shell or command interpolation.
        subprocess.Popen([executable], cwd=str(Path(executable).parent), close_fds=True)
    except OSError:
        return dict(ok=False, code='MT5_TERMINAL_LAUNCH_FAILED', error='Windows could not open the configured MT5 terminal. Check the installation and gateway user permissions.')
    return dict(ok=True, code='MT5_TERMINAL_STARTED', path=executable, launched=True)
