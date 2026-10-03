"""Discover MetaTrader 5 terminal64.exe on Windows (env, running terminal, common install paths)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .mt5_diagnostics import mt5_python_package_status

_TERMINAL_EXE = "terminal64.exe"
_MAX_FS_CANDIDATES = 24


def normalize_terminal_exe(path: str) -> str:
    if not path or not str(path).strip():
        return ""
    p = Path(path.strip())
    if p.is_file() and p.name.lower() == _TERMINAL_EXE.lower():
        return str(p.resolve())
    if p.is_dir():
        exe = p / _TERMINAL_EXE
        if exe.is_file():
            return str(exe.resolve())
    if p.suffix.lower() == ".exe" and p.is_file():
        return str(p.resolve())
    return ""


def filesystem_terminal_candidates() -> list[str]:
    roots: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "APPDATA"):
        raw = os.environ.get(key)
        if raw:
            roots.append(Path(raw))
    found: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        try:
            patterns: tuple[str, ...]
            if root.name.lower() in ("program files", "program files (x86)"):
                patterns = (
                    "MetaTrader 5/" + _TERMINAL_EXE,
                    "MetaTrader*/" + _TERMINAL_EXE,
                    "*MetaTrader*/" + _TERMINAL_EXE,
                )
            else:
                patterns = ("**/" + _TERMINAL_EXE,)
            for pattern in patterns:
                for exe in root.glob(pattern):
                    if not exe.is_file():
                        continue
                    resolved = str(exe.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    found.append(resolved)
                    if len(found) >= _MAX_FS_CANDIDATES:
                        return _sort_candidates(found)
        except OSError:
            continue
    return _sort_candidates(found)


def is_generic_metatrader5_install(path: str) -> bool:
    """True for the default MetaQuotes 'MetaTrader 5' folder (not broker-branded installs)."""
    if not path:
        return False
    parent = Path(path).parent.name.lower().replace("_", " ").strip()
    if parent not in ("metatrader 5", "metatrader5"):
        return False
    low = path.lower()
    return "ic markets" not in low and "icmarkets" not in low


def rank_terminal_install(path: str) -> tuple[int, str]:
    """Lower rank = preferred. Broker terminals (e.g. IC Markets) beat generic MetaTrader 5."""
    low = path.lower()
    if is_generic_metatrader5_install(path):
        return (3, path)
    if "ic markets" in low or "icmarkets" in low:
        return (0, path)
    if "program files" in low:
        return (1, path)
    if "metaquotes" in low:
        return (2, path)
    return (4, path)


def _sort_candidates(paths: list[str]) -> list[str]:
    return sorted(paths, key=rank_terminal_install)


def running_terminal64_processes() -> list[str]:
    """Paths of terminal64.exe currently running (Windows). Matches the taskbar MT5 instance."""
    if os.name != "nt":
        return []
    found: list[str] = []
    try:
        raw = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-Process terminal64 -ErrorAction SilentlyContinue | "
                "ForEach-Object { $_.Path } | Where-Object { $_ }",
            ],
            stderr=subprocess.DEVNULL,
            timeout=12,
            text=True,
        )
        for line in raw.splitlines():
            exe = normalize_terminal_exe(line.strip())
            if exe and exe not in found:
                found.append(exe)
    except Exception:
        pass
    return _sort_candidates(found)


def pick_preferred_terminal_path(saved: str, extra: list[str] | None = None) -> tuple[str, str]:
    """
    Choose terminal64.exe for Python API attach.
    Prefer the running broker terminal (IC Markets) over a saved generic MetaTrader 5 path.
    Returns (path, source_tag).
    """
    running = running_terminal64_processes()
    pool: list[str] = []
    for p in running + ([saved] if saved else []) + (extra or []):
        exe = normalize_terminal_exe(p)
        if exe and exe not in pool:
            pool.append(exe)
    if not pool:
        return "", ""
    if running:
        best = sorted(running, key=rank_terminal_install)[0]
        return best, "running_process"
    best = sorted(pool, key=rank_terminal_install)[0]
    if saved and normalize_terminal_exe(saved) == best:
        return best, "saved"
    return best, "filesystem"


def _mt5_terminal_info():
    try:
        import MetaTrader5 as mt5  # type: ignore

        return mt5.terminal_info()
    except Exception:
        return None


def _is_mt5_initialized() -> bool:
    return _mt5_terminal_info() is not None


def match_terminal_exe_by_name(terminal_name: str) -> str:
    """Map terminal_info().name (e.g. 'MetaTrader 5 IC Markets Global') to terminal64.exe on disk."""
    if not terminal_name or not terminal_name.strip():
        return ""
    norm = terminal_name.lower().replace("_", " ").strip()
    best = ""
    best_score = 0
    for candidate in filesystem_terminal_candidates():
        folder = Path(candidate).parent.name.lower()
        if folder == norm:
            return candidate
        score = 0
        if norm in folder or folder in norm:
            score = min(len(norm), len(folder))
        for token in norm.split():
            if len(token) > 3 and token in folder:
                score += len(token)
        if score > best_score:
            best_score = score
            best = candidate
    return best if best_score >= 8 else ""


def _path_from_running_mt5() -> tuple[str, str]:
    ti = _mt5_terminal_info()
    if ti is None:
        return "", ""
    name = (getattr(ti, "name", None) or "").strip()
    by_name = match_terminal_exe_by_name(name)
    if by_name:
        return by_name, "running_name"
    raw = (getattr(ti, "path", None) or "").strip()
    if raw:
        exe = normalize_terminal_exe(raw)
        if exe:
            return exe, "running"
        parent = Path(raw).parent
        for candidate in (parent / _TERMINAL_EXE, parent.parent / _TERMINAL_EXE):
            if candidate.is_file():
                return str(candidate.resolve()), "running"
    return "", ""


def _probe_initialize(path: str | None) -> bool:
    import MetaTrader5 as mt5  # type: ignore

    if mt5.terminal_info() is not None:
        return True
    try:
        mt5.shutdown()
    except Exception:
        pass
    if path:
        return bool(mt5.initialize(path=path))
    return bool(mt5.initialize())


def auto_detect_terminal_path(*, use_env: bool = False, allow_probe: bool = True) -> tuple[str, str]:
    """
    Returns (terminal64.exe path, source tag).
    source: env | running | default_init | filesystem | filesystem_probe | ''
    Tenant UI flows must use use_env=False (no .env override).
    When allow_probe=False (e.g. GET /connections while disconnected), never call mt5.initialize.
    """
    if use_env:
        env = normalize_terminal_exe(os.getenv("MT5_TERMINAL_PATH", ""))
        if env:
            return env, "env"

    proc_paths = running_terminal64_processes()
    if proc_paths:
        return proc_paths[0], "running_process"

    pkg = mt5_python_package_status()
    if pkg["python_package"] == "installed":
        running, src = _path_from_running_mt5()
        if running:
            return running, src
        if _is_mt5_initialized():
            ti = _mt5_terminal_info()
            name = (getattr(ti, "name", None) or "") if ti else ""
            matched = match_terminal_exe_by_name(name)
            if matched:
                return matched, "running_name"
        if allow_probe:
            if _probe_initialize(None):
                running, src = _path_from_running_mt5()
                try:
                    import MetaTrader5 as mt5  # type: ignore

                    mt5.shutdown()
                except Exception:
                    pass
                if running:
                    return running, "default_init"

            for candidate in filesystem_terminal_candidates()[:6]:
                if _probe_initialize(candidate):
                    try:
                        import MetaTrader5 as mt5  # type: ignore

                        mt5.shutdown()
                    except Exception:
                        pass
                    return candidate, "filesystem_probe"
                try:
                    import MetaTrader5 as mt5  # type: ignore

                    mt5.shutdown()
                except Exception:
                    pass

    fs = filesystem_terminal_candidates()
    if fs:
        return fs[0], "filesystem"

    return "", ""


def terminal_detection_diagnostics() -> dict[str, Any]:
    path, source = auto_detect_terminal_path()
    return {
        "terminal_auto_detect_path": path or None,
        "terminal_auto_detect_source": source or None,
        "terminal_candidates": filesystem_terminal_candidates()[:8],
    }
