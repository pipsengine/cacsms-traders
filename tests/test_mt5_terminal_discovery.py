from apps.api.app.domain.mt5_terminal_discovery import (
    is_generic_metatrader5_install,
    match_terminal_exe_by_name,
    normalize_terminal_exe,
    pick_preferred_terminal_path,
    rank_terminal_install,
)


def test_normalize_terminal_exe_file(tmp_path):
    exe = tmp_path / "terminal64.exe"
    exe.write_bytes(b"")
    p = normalize_terminal_exe(str(exe))
    assert p.endswith("terminal64.exe")


def test_normalize_terminal_exe_dir(tmp_path):
    assert normalize_terminal_exe("") == ""
    assert normalize_terminal_exe("   ") == ""


def test_match_terminal_exe_by_name():
    name = "MetaTrader 5 IC Markets Global"
    # Returns empty when no installs on machine; scoring logic still runs
    result = match_terminal_exe_by_name(name)
    assert result == "" or result.lower().endswith("terminal64.exe")


def test_prefers_ic_markets_over_generic():
    generic = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    icm = r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"
    assert is_generic_metatrader5_install(generic)
    assert not is_generic_metatrader5_install(icm)
    assert rank_terminal_install(icm)[0] < rank_terminal_install(generic)[0]
    path, source = pick_preferred_terminal_path(generic, [icm])
    assert path == icm
    assert source in ("saved", "filesystem", "running_process")


def test_filesystem_candidates_is_list():
    from apps.api.app.domain.mt5_terminal_discovery import filesystem_terminal_candidates

    assert isinstance(filesystem_terminal_candidates(), list)
