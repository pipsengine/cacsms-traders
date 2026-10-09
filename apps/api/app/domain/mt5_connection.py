"""Local MT5 gateway — per-tenant settings, session lifecycle, health (no order submission)."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from ..core.database import db, execute_retry
from ..core.security import iso
from ..market import mt5_session
from .mt5_diagnostics import mt5_python_package_status
from .mt5_terminal_launcher import launch_terminal, terminal_launch_capability
from .mt5_terminal_account import environment_from_terminal, read_terminal_account
from .mt5_terminal_discovery import (
    auto_detect_terminal_path,
    match_terminal_exe_by_name,
    normalize_terminal_exe,
    pick_preferred_terminal_path,
    running_terminal64_processes,
)

SETTINGS_KEY = "mt5.local"
ACTIVE_TENANT_KEY = "mt5.active_tenant_id"
_IPC_LOCK = threading.RLock()
_CONNECT_IN_PROGRESS: set[str] = set()


def connection_in_progress(tenant_id: str | None) -> bool:
    tid = (tenant_id or "").strip()
    return bool(tid and tid in _CONNECT_IN_PROGRESS)

DEFAULT_SETTINGS: dict[str, Any] = {
    "terminal_path": "",
    "login_type": "",
    "auto_reconnect": True,
    "heartbeat_interval_seconds": 30,
    "last_connected_at": None,
    "session_status": "DISCONNECTED",
    "last_error": None,
    "last_heartbeat_at": None,
    "terminal_account_snapshot": None,
}


def _resolve_terminal_path(conn: sqlite3.Connection, tenant_id: str, *, persist: bool = True) -> str:
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    saved = normalize_terminal_exe((settings.get("terminal_path") or "").strip())
    passive, _src = auto_detect_terminal_path(use_env=False, allow_probe=False)
    path, _source = pick_preferred_terminal_path(saved, [passive] if passive else None)
    if not path:
        path = saved
    if persist and path and path != saved:
        settings["terminal_path"] = path
        gw._save_settings(conn, settings)
    return path


def _terminal_paths_to_try(conn: sqlite3.Connection, tenant_id: str, primary: str | None = None) -> list[str]:
    resolved = _resolve_terminal_path(conn, tenant_id, persist=False)
    paths: list[str] = []
    for p in (primary, resolved):
        exe = normalize_terminal_exe((p or "").strip())
        if exe and exe not in paths:
            paths.append(exe)
    for p in running_terminal64_processes():
        if p not in paths:
            paths.append(p)
    passive, _ = auto_detect_terminal_path(use_env=False, allow_probe=False)
    if passive and passive not in paths:
        paths.append(passive)
    return paths


def _initialize_mt5_for_tenant(
    conn: sqlite3.Connection | None, tenant_id: str, primary: str | None = None
) -> tuple[bool, str]:
    with _IPC_LOCK:
        if conn is not None:
            paths = _terminal_paths_to_try(conn, tenant_id, primary)
        else:
            with db() as c:
                paths = _terminal_paths_to_try(c, tenant_id, primary)
        ok, used = mt5_session.initialize_first(paths)
        if ok and used:
            gw = LocalMT5Gateway(tenant_id)
            if conn is not None:
                settings = gw._load_settings(conn)
                settings["terminal_path"] = used
                gw._save_settings(conn, settings)
            else:
                with db() as c:
                    settings = gw._load_settings(c)
                    settings["terminal_path"] = used
                    gw._save_settings(c, settings)
        return ok, used


def _snapshot_as_terminal_account(settings: dict[str, Any]) -> dict[str, Any] | None:
    snap = settings.get("terminal_account_snapshot")
    if not isinstance(snap, dict) or not (snap.get("login") or "").strip():
        return None
    return {"available": True, "from_snapshot": True, **snap}


def persist_terminal_account_snapshot(
    conn: sqlite3.Connection, tenant_id: str, terminal: dict[str, Any]
) -> None:
    if not terminal.get("available"):
        return
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    settings["terminal_account_snapshot"] = {
        "login": terminal.get("login"),
        "server": terminal.get("server"),
        "name": terminal.get("name"),
        "company": terminal.get("company"),
        "currency": terminal.get("currency"),
        "trade_mode": terminal.get("trade_mode"),
        "balance": terminal.get("balance"),
        "equity": terminal.get("equity"),
        "margin": terminal.get("margin"),
        "free_margin": terminal.get("free_margin"),
        "captured_at": iso(),
    }
    try:
        gw._save_settings(conn, settings)
    except sqlite3.OperationalError as exc:
        if "locked" not in str(exc).lower():
            raise


def ensure_gateway_session(conn: sqlite3.Connection, tenant_id: str) -> dict[str, Any]:
    """Re-attach MT5 after API restart when tenant session was CONNECTED."""
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    if settings.get("session_status") != "CONNECTED":
        return {"restored": False, "reason": "not_connected"}
    if mt5_session.is_initialized():
        return {"restored": False, "reason": "already_live"}
    if not settings.get("auto_reconnect", True):
        return {"restored": False, "reason": "auto_reconnect_off"}
    path = _resolve_terminal_path(conn, tenant_id)
    if not path:
        return {"restored": False, "reason": "no_terminal_path"}
    if connection_in_progress(tenant_id):
        return {"restored": False, "reason": "connect_in_progress"}
    ok, used = _initialize_mt5_for_tenant(conn, tenant_id, path)
    if not ok:
        settings["last_error"] = (
            "Auto-reconnect failed — open your broker terminal, then use Connect in System Control."
        )
        gw._save_settings(conn, settings)
        return {"restored": False, "reason": "initialize_failed"}
    settings["last_error"] = None
    gw._touch_heartbeat(conn, settings)
    return {"restored": True, "path": used or path}


def read_terminal_account_for_tenant(
    conn: sqlite3.Connection,
    tenant_id: str,
    *,
    force_attach: bool = False,
    persist_snapshot: bool = True,
) -> dict[str, Any] | None:
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    keep_session = settings.get("session_status") == "CONNECTED"
    if mt5_session.is_initialized():
        terminal = read_terminal_account()
    elif force_attach or keep_session:
        ok, _used = _initialize_mt5_for_tenant(conn, tenant_id)
        if not ok:
            return _snapshot_as_terminal_account(settings)
        terminal = read_terminal_account()
    else:
        return _snapshot_as_terminal_account(settings)
    if terminal and terminal.get("available"):
        if persist_snapshot:
            persist_terminal_account_snapshot(conn, tenant_id, terminal)
        return terminal
    return _snapshot_as_terminal_account(settings) or terminal


def _terminal_path_from_mt5() -> str:
    try:
        import MetaTrader5 as mt5  # type: ignore

        ti = mt5.terminal_info()
        if ti is None:
            return ""
        by_name = match_terminal_exe_by_name(getattr(ti, "name", None) or "")
        if by_name:
            return by_name
        return normalize_terminal_exe(getattr(ti, "path", None) or "")
    except Exception:
        return ""


def _terminal_label(path: str, md: dict[str, Any], connected: bool) -> str:
    if path:
        return path
    if connected:
        return str(md.get("message") or "MetaTrader 5 (auto-detected)")
    return "Not configured"


def _active_tenant_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key=?", (ACTIVE_TENANT_KEY,)).fetchone()
    if not row:
        return None
    val = json.loads(row["value_json"])
    return val if isinstance(val, str) and val.strip() else None


def _set_active_tenant_id(conn: sqlite3.Connection, tenant_id: str | None) -> None:
    conn.execute(
        """INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?)
           ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
        (ACTIVE_TENANT_KEY, json.dumps(tenant_id), iso()),
    )


def _legacy_system_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key=?", (SETTINGS_KEY,)).fetchone()
    if not row:
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(json.loads(row["value_json"]))
    return merged


def ensure_autodetected_terminal_path(
    conn: sqlite3.Connection,
    tenant_id: str,
    *,
    allow_probe: bool | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Persist tenant terminal_path when empty (UI / auto-detect only — no .env)."""
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    existing = (settings.get("terminal_path") or "").strip()
    if existing:
        return {"path": existing, "source": "saved", "persisted": False}
    if allow_probe is None:
        allow_probe = settings.get("session_status") == "CONNECTED"
    path, source = auto_detect_terminal_path(use_env=False, allow_probe=allow_probe)
    if not path:
        path = _terminal_path_from_mt5()
        source = "running" if path else source
    if path:
        if persist:
            settings["terminal_path"] = path
            gw._save_settings(conn, settings)
            return {"path": path, "source": source, "persisted": True}
        return {"path": path, "source": source, "persisted": False}
    return {"path": "", "source": "", "persisted": False}


def sync_trading_registry_from_terminal(
    conn: sqlite3.Connection,
    tenant_id: str,
    *,
    force_attach: bool = True,
    live_only: bool = False,
    terminal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backfill linked registry rows from the logged-in MT5 terminal (login, server, status)."""
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    if terminal is None:
        terminal = read_terminal_account_for_tenant(conn, tenant_id, force_attach=force_attach)
    if live_only and terminal and terminal.get("from_snapshot"):
        return {"synced": False, "reason": "snapshot_only", "error": "Terminal account is a stored snapshot"}
    if not terminal or not terminal.get("available"):
        return {
            "synced": False,
            "reason": "no_terminal_account",
            "error": (terminal or {}).get("error") if terminal else "No MT5 account data",
        }
    link_status = "CONNECTED" if terminal.get("available") else "DISCONNECTED"
    live_mt5 = mt5_session.is_initialized()
    login = (terminal.get("login") or "").strip()
    server = (terminal.get("server") or "").strip()
    env = environment_from_terminal(terminal.get("trade_mode") or "DEMO")
    leverage = str(terminal.get("leverage") or "")
    now = iso()
    rows = conn.execute(
        """SELECT c.id AS connection_id, c.trading_account_id,
                  a.account_number, a.account_name
           FROM trading_connections c
           JOIN trading_accounts a ON a.id = c.trading_account_id
           WHERE c.tenant_id=? ORDER BY c.updated_at DESC""",
        (tenant_id,),
    ).fetchall()
    balance = float(terminal.get("balance") or 0)
    equity = float(terminal.get("equity") or 0)
    margin = float(terminal.get("margin") or 0)
    free_margin = float(terminal.get("free_margin") or 0)
    currency = (terminal.get("currency") or "").strip() or None
    candidates: list[Any] = []
    for row in rows:
        num = (row["account_number"] or "").strip()
        if not num or num == login:
            candidates.append(row)
    if not candidates and len(rows) == 1:
        candidates = [rows[0]]
    updated = 0
    for row in candidates:
        tid = row["trading_account_id"]
        cid = row["connection_id"]
        conn.execute(
            """UPDATE trading_accounts SET account_number=?, server=?, environment=?, broker=COALESCE(NULLIF(broker,''), ?),
               account_currency=COALESCE(?, account_currency),
               balance=?, equity=?, margin=?, free_margin=?,
               leverage=CASE WHEN leverage IS NULL OR leverage='' THEN ? ELSE leverage END,
               connection_type=?, connection_status=?, last_synced_at=?, updated_at=?
               WHERE id=? AND tenant_id=?""",
            (
                login,
                server,
                env,
                terminal.get("company") or "MT5",
                currency,
                balance,
                equity,
                margin,
                free_margin,
                leverage,
                "LOCAL_MT5",
                link_status,
                now,
                now,
                tid,
                tenant_id,
            ),
        )
        conn.execute(
            "UPDATE trading_connections SET server_name=?, status=?, updated_at=? WHERE id=?",
            (server, link_status, now, cid),
        )
        updated += 1
    if updated == 0:
        orphan = conn.execute(
            """SELECT id, account_number FROM trading_accounts
               WHERE tenant_id=? ORDER BY updated_at DESC""",
            (tenant_id,),
        ).fetchall()
        orphan_targets: list[Any] = []
        for ac in orphan:
            num = (ac["account_number"] or "").strip()
            if not num or num == login:
                orphan_targets.append(ac)
        if not orphan_targets and len(orphan) == 1:
            orphan_targets = [orphan[0]]
        for ac in orphan_targets:
            conn.execute(
                """UPDATE trading_accounts SET account_number=?, server=?, environment=?, broker=COALESCE(NULLIF(broker,''), ?),
                   account_currency=COALESCE(?, account_currency),
                   balance=?, equity=?, margin=?, free_margin=?,
                   leverage=CASE WHEN leverage IS NULL OR leverage='' THEN ? ELSE leverage END,
                   connection_type=?, connection_status=?, last_synced_at=?, updated_at=?
                   WHERE id=? AND tenant_id=?""",
                (
                    login,
                    server,
                    env,
                    terminal.get("company") or "MT5",
                    currency,
                    balance,
                    equity,
                    margin,
                    free_margin,
                    leverage,
                    "LOCAL_MT5",
                    link_status,
                    now,
                    now,
                    ac["id"],
                    tenant_id,
                ),
            )
            updated += 1
    return {
        "synced": True,
        "updated": updated,
        "login": login,
        "server": server,
        "balance": balance,
        "equity": equity,
        "free_margin": free_margin,
        "gateway_connected": live_mt5 and settings.get("session_status") == "CONNECTED",
    }


def _registry_sync_age_seconds(conn: sqlite3.Connection, tenant_id: str) -> float | None:
    row = conn.execute(
        "SELECT MAX(last_synced_at) AS synced FROM trading_accounts WHERE tenant_id=?",
        (tenant_id,),
    ).fetchone()
    synced = None if row is None else row["synced"]
    if not synced:
        return None
    try:
        stamp = datetime.fromisoformat(str(synced))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def refresh_trading_account_if_stale(tenant_id: str, *, max_age_seconds: float = 60) -> dict[str, Any]:
    """Refresh balance, equity and margin from the live terminal when the registry row is old.

    The terminal read happens outside the database lock. A stored snapshot is not written back as a new sync time.
    """
    if not (tenant_id or "").strip():
        return {"synced": False, "reason": "no_tenant"}
    with db() as conn:
        age = _registry_sync_age_seconds(conn, tenant_id)
    if age is not None and age <= max_age_seconds:
        return {"synced": False, "reason": "fresh"}
    if not mt5_session.is_initialized():
        return {"synced": False, "reason": "session_down"}
    terminal = read_terminal_account()
    if not terminal or not terminal.get("available") or terminal.get("from_snapshot"):
        return {"synced": False, "reason": "no_live_account"}
    with db() as conn:
        return sync_trading_registry_from_terminal(
            conn, tenant_id, force_attach=False, live_only=True, terminal=terminal
        )


def sync_tenant_terminal_path_if_connected(conn: sqlite3.Connection, tenant_id: str) -> None:
    """When gateway is live but DB path is empty, resolve and save without disconnecting MT5."""
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    if (settings.get("terminal_path") or "").strip():
        return
    session_ok = settings.get("session_status") == "CONNECTED"
    md = mt5_session.connection_state()
    if not session_ok and not md.get("connected"):
        return
    ensure_autodetected_terminal_path(conn, tenant_id)


def clear_stale_mt5_package_error(conn: sqlite3.Connection, tenant_id: str) -> None:
    gw = LocalMT5Gateway(tenant_id)
    settings = gw._load_settings(conn)
    err = settings.get("last_error")
    if err and "MetaTrader5 Python package" in str(err):
        if mt5_python_package_status()["python_package"] == "installed":
            settings["last_error"] = None
            gw._save_settings(conn, settings)


def clear_stale_mt5_package_errors_all_tenants(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM tenants").fetchall()
    for row in rows:
        clear_stale_mt5_package_error(conn, row["id"])


def _system_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()
    if not row:
        return "ANALYSIS_ONLY"
    return json.loads(row["value_json"])


class LocalMT5Gateway:
    def __init__(self, tenant_id: str | None = None) -> None:
        self.tenant_id = tenant_id

    def _load_settings(self, conn: sqlite3.Connection) -> dict[str, Any]:
        if not self.tenant_id:
            active = _active_tenant_id(conn)
            if active:
                return LocalMT5Gateway(active)._load_settings(conn)
            return _legacy_system_settings(conn)

        row = conn.execute(
            "SELECT value_json FROM tenant_settings WHERE tenant_id=? AND key=?",
            (self.tenant_id, SETTINGS_KEY),
        ).fetchone()
        if row:
            merged = dict(DEFAULT_SETTINGS)
            merged.update(json.loads(row["value_json"]))
            return merged

        merged = _legacy_system_settings(conn)
        self._save_settings(conn, merged)
        return merged

    def _save_settings(self, conn: sqlite3.Connection, settings: dict[str, Any]) -> None:
        if not self.tenant_id:
            execute_retry(
                conn,
                """INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
                (SETTINGS_KEY, json.dumps(settings), iso()),
            )
            return
        row_id = f"ts-{self.tenant_id}-{SETTINGS_KEY.replace('.', '-')}"
        execute_retry(
            conn,
            """INSERT INTO tenant_settings(id,tenant_id,key,value_json,updated_at) VALUES(?,?,?,?,?)
               ON CONFLICT(tenant_id,key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
            (row_id, self.tenant_id, SETTINGS_KEY, json.dumps(settings), iso()),
        )

    def _health(self, conn: sqlite3.Connection, *, allow_reconnect: bool = True) -> dict[str, Any]:
        settings = self._load_settings(conn)
        mode = _system_mode(conn)
        session = settings.get("session_status", "DISCONNECTED")
        if (
            allow_reconnect
            and session == "CONNECTED"
            and not mt5_session.is_initialized()
        ):
            if settings.get("auto_reconnect", True) and _initialize_mt5_for_tenant(
                conn, self.tenant_id or "", None
            )[0]:
                settings["last_error"] = None
                self._touch_heartbeat(conn, settings)
            else:
                settings["last_error"] = settings.get("last_error") or (
                    "MT5 not attached — open your broker terminal or use Connect in System Control."
                )
                self._save_settings(conn, settings)
        md = (
            mt5_session.connection_state()
            if session == "CONNECTED"
            else {
                "connected": False,
                "adapter": "LOCAL_MT5",
                "message": "Not connected — use Connect in System Control",
            }
        )
        market_connected = session == "CONNECTED" and bool(md.get("connected"))
        if session == "CONNECTED" and market_connected:
            status = "CONNECTED"
        elif session == "CONNECTED" and settings.get("auto_reconnect", True):
            status = "RECONNECTING" if settings.get("last_error") else "CONNECTING"
        else:
            status = "DISCONNECTED"
        if connection_in_progress(self.tenant_id) and not market_connected:
            status = "CONNECTING"
        execution_disabled = mode in ("ANALYSIS_ONLY", "PAUSED", "EMERGENCY_STOP")
        saved_path = (settings.get("terminal_path") or "").strip()
        path = saved_path
        live_connected = status == "CONNECTED"
        if live_connected and not path:
            path = _terminal_path_from_mt5()
        return {
            "status": status,
            "session_status": session,
            "adapter": "LOCAL_MT5",
            "message": md.get("message") or settings.get("last_error") or "Local MT5 adapter foundation installed.",
            "terminal_configured": bool(saved_path),
            "terminal_auto_detected": bool(path and not saved_path),
            "terminal": _terminal_label(path or saved_path, md, live_connected),
            "terminal_path_detected": path if live_connected else "",
            "tenant_id": self.tenant_id,
            "heartbeat_at": settings.get("last_heartbeat_at"),
            "last_connected_at": settings.get("last_connected_at"),
            "last_error": settings.get("last_error"),
            "execution_enabled": not execution_disabled,
            "execution": "Disabled" if execution_disabled else "Restricted",
            "market_data_connected": market_connected,
            "terminal_account": (
                read_terminal_account()
                if live_connected
                else _snapshot_as_terminal_account(settings)
            ),
        }

    def settings(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        if conn is not None:
            return self._load_settings(conn)
        with db() as c:
            return self._load_settings(c)

    def patch_settings(self, patch: dict[str, Any], conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        if conn is not None:
            current = self._load_settings(conn)
            for k, v in patch.items():
                if k in DEFAULT_SETTINGS or k in current:
                    current[k] = v
            if patch.get("terminal_path") and mt5_python_package_status()["python_package"] == "installed":
                if current.get("last_error") and "MetaTrader5 Python package" in str(current.get("last_error")):
                    current["last_error"] = None
            self._save_settings(conn, current)
            return current
        with db() as c:
            return self.patch_settings(patch, conn=c)

    def health(
        self, conn: sqlite3.Connection | None = None, *, allow_reconnect: bool = True
    ) -> dict[str, Any]:
        if conn is not None:
            return self._health(conn, allow_reconnect=allow_reconnect)
        with db() as c:
            return self._health(c, allow_reconnect=allow_reconnect)

    def _touch_heartbeat(self, conn: sqlite3.Connection, settings: dict[str, Any]) -> None:
        settings["last_heartbeat_at"] = iso()
        self._save_settings(conn, settings)

    def connect(
        self, terminal_path: str | None = None, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any]:
        def _run(c: sqlite3.Connection) -> dict[str, Any]:
            settings = self._load_settings(c)
            tid = (self.tenant_id or "").strip()
            if tid and tid in _CONNECT_IN_PROGRESS:
                return {
                    "ok": False,
                    "code": "CONNECT_IN_PROGRESS",
                    "error": "Connect already in progress for this tenant.",
                    "settings": settings,
                    "gateway": self._health(c, allow_reconnect=False),
                }
            if tid:
                _CONNECT_IN_PROGRESS.add(tid)
            try:
                return _connect_body(c, settings, terminal_path)
            finally:
                if tid:
                    _CONNECT_IN_PROGRESS.discard(tid)

        def _connect_body(c: sqlite3.Connection, settings: dict[str, Any], terminal_path: str | None) -> dict[str, Any]:
            if not terminal_launch_capability()['terminal_launch_supported']:
                return {'ok':False,'code':'MT5_WINDOWS_GATEWAY_REQUIRED','error':'No Windows MT5 gateway is connected. The hosted API cannot open the terminal on another machine.','settings':settings}
            path = normalize_terminal_exe((terminal_path or settings.get("terminal_path") or "").strip())
            if not path:
                detected, _src = auto_detect_terminal_path(use_env=False, allow_probe=False)
                path = normalize_terminal_exe(detected)
            if path:
                settings["terminal_path"] = path
                self._save_settings(c, settings)

            launch = launch_terminal(path)
            if not launch['ok']:
                settings['last_error'] = launch['error']
                settings['session_status'] = 'DISCONNECTED'
                self._save_settings(c, settings)
                return {**launch,'settings':settings}
            pkg = mt5_python_package_status()
            if pkg["python_package"] == "missing":
                settings["last_error"] = (
                    "MetaTrader5 Python package is not installed in the API process. "
                    f"{pkg['hint']}"
                )
                settings["session_status"] = "DISCONNECTED"
                self._save_settings(c, settings)
                return {
                    "ok": False,
                    "error": settings["last_error"],
                    "settings": settings,
                    "gateway": self._health(c),
                    "code": "MT5_PACKAGE_MISSING",
                    "terminal_launch": launch,
                }

            try:
                import MetaTrader5 as mt5  # type: ignore

                ok, used_path = _initialize_mt5_for_tenant(c, self.tenant_id or "", path)
                if used_path:
                    settings["terminal_path"] = used_path
                    self._save_settings(c, settings)
                if not ok:
                    err_tuple = mt5.last_error()
                    err = f"{err_tuple}" if err_tuple else "MT5 initialize failed"
                    running = running_terminal64_processes()
                    hint = (
                        "Use the same terminal as in your taskbar (e.g. IC Markets). "
                        f"Detected running: {running[0]}" if running else "Open your broker MT5 and log in, then Connect."
                    )
                    settings["last_error"] = f"{err}. {hint}"
                    settings["session_status"] = "DISCONNECTED"
                    self._save_settings(c, settings)
                    return {
                        "ok": False,
                        "error": err,
                        "settings": settings,
                        "gateway": self._health(c),
                    }
                settings["session_status"] = "CONNECTED"
                settings["last_connected_at"] = iso()
                settings["last_error"] = None
                detected = _terminal_path_from_mt5()
                if not detected:
                    path, _ = auto_detect_terminal_path(use_env=False, allow_probe=False)
                    detected = path
                if detected:
                    settings["terminal_path"] = detected
                self._touch_heartbeat(c, settings)
                if self.tenant_id:
                    _set_active_tenant_id(c, self.tenant_id)
                    from ..market.market_data import bind_market_data_tenant

                    bind_market_data_tenant(c, self.tenant_id)
                    terminal = read_terminal_account()
                    if terminal and terminal.get("available"):
                        persist_terminal_account_snapshot(c, self.tenant_id, terminal)
                        bind_market_data_tenant(
                            c,
                            self.tenant_id,
                            account_id=f"{terminal.get('server')}/{terminal.get('login')}",
                        )
                    tid = self.tenant_id

                    def _registry_sync() -> None:
                        from ..core.database import db

                        try:
                            with db() as bg:
                                sync_trading_registry_from_terminal(bg, tid, force_attach=False)
                        except Exception:
                            pass

                    threading.Thread(target=_registry_sync, name="mt5-registry-sync", daemon=True).start()
                return {"ok": True, "settings": settings, "gateway": self._health(c), "terminal_launch": launch}
            except Exception as exc:
                settings["last_error"] = str(exc)
                settings["session_status"] = "DISCONNECTED"
                self._save_settings(c, settings)
                return {
                    "ok": False,
                    "error": str(exc),
                    "settings": settings,
                    "gateway": self._health(c),
                }

        if conn is not None:
            return _run(conn)
        with db() as c:
            return _run(c)

    def disconnect(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        def _run(c: sqlite3.Connection) -> dict[str, Any]:
            settings = self._load_settings(c)
            with _IPC_LOCK:
                mt5_session.shutdown()
            settings["session_status"] = "DISCONNECTED"
            self._save_settings(c, settings)
            if self.tenant_id and _active_tenant_id(c) == self.tenant_id:
                _set_active_tenant_id(c, None)
            return {"ok": True, "settings": settings, "gateway": self._health(c)}

        if conn is not None:
            return _run(conn)
        with db() as c:
            return _run(c)

    def restart(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        if conn is not None:
            self.disconnect(conn=conn)
            return self.connect(None, conn=conn)
        with db() as c:
            self.disconnect(conn=c)
            return self.connect(None, conn=c)
