"""Local MT5 gateway — settings, session lifecycle, health (no order submission)."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from ..core.database import db
from ..core.security import iso
from ..market.mt5_gateway import create_market_data_gateway
from .mt5_diagnostics import mt5_python_package_status

SETTINGS_KEY = "mt5.local"

DEFAULT_SETTINGS: dict[str, Any] = {
    "terminal_path": "",
    "login_type": "",
    "auto_reconnect": True,
    "heartbeat_interval_seconds": 30,
    "last_connected_at": None,
    "session_status": "DISCONNECTED",
    "last_error": None,
    "last_heartbeat_at": None,
}

def _system_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key='system.mode'").fetchone()
    if not row:
        return "ANALYSIS_ONLY"
    return json.loads(row["value_json"])


class LocalMT5Gateway:
    def _load_settings(self, conn: sqlite3.Connection) -> dict[str, Any]:
        row = conn.execute("SELECT value_json FROM system_settings WHERE key=?", (SETTINGS_KEY,)).fetchone()
        if not row:
            return dict(DEFAULT_SETTINGS)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(json.loads(row["value_json"]))
        return merged

    def _save_settings(self, conn: sqlite3.Connection, settings: dict[str, Any]) -> None:
        conn.execute(
            """INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?)
               ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at""",
            (SETTINGS_KEY, json.dumps(settings), iso()),
        )

    def _health(self, conn: sqlite3.Connection) -> dict[str, Any]:
        settings = self._load_settings(conn)
        mode = _system_mode(conn)
        md = create_market_data_gateway().connection_state()
        market_connected = bool(md.get("connected"))
        session = settings.get("session_status", "DISCONNECTED")
        status = "CONNECTED" if market_connected or session == "CONNECTED" else "DISCONNECTED"
        if market_connected:
            status = "CONNECTED"
        execution_disabled = mode in ("ANALYSIS_ONLY", "PAUSED", "EMERGENCY_STOP")
        path = (settings.get("terminal_path") or os.getenv("MT5_TERMINAL_PATH", "")).strip()
        return {
            "status": status,
            "adapter": "LOCAL_MT5",
            "message": md.get("message") or settings.get("last_error") or "Local MT5 adapter foundation installed.",
            "terminal_configured": bool(path),
            "terminal": path or "Not configured",
            "heartbeat_at": settings.get("last_heartbeat_at"),
            "last_connected_at": settings.get("last_connected_at"),
            "last_error": settings.get("last_error"),
            "execution_enabled": not execution_disabled,
            "execution": "Disabled" if execution_disabled else "Restricted",
            "market_data_connected": market_connected,
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
            current = self.patch_settings(patch, conn=c)
            return current

    def health(self, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
        if conn is not None:
            return self._health(conn)
        with db() as c:
            return self._health(c)

    def _touch_heartbeat(self, conn: sqlite3.Connection, settings: dict[str, Any]) -> None:
        settings["last_heartbeat_at"] = iso()
        self._save_settings(conn, settings)

    def connect(
        self, terminal_path: str | None = None, conn: sqlite3.Connection | None = None
    ) -> dict[str, Any]:
        def _run(c: sqlite3.Connection) -> dict[str, Any]:
            settings = self._load_settings(c)
            path = (terminal_path or settings.get("terminal_path") or os.getenv("MT5_TERMINAL_PATH", "")).strip()
            if path:
                settings["terminal_path"] = path
                self._save_settings(c, settings)

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
                }

            try:
                import MetaTrader5 as mt5  # type: ignore

                if path:
                    ok = mt5.initialize(path=path)
                else:
                    ok = mt5.initialize()
                if not ok:
                    err_tuple = mt5.last_error()
                    err = f"{err_tuple}" if err_tuple else "MT5 initialize failed"
                    settings["last_error"] = (
                        f"{err}. Confirm terminal64.exe exists, MetaTrader 5 is installed, "
                        "and the terminal is allowed to run (not blocked by antivirus)."
                    )
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
                self._touch_heartbeat(c, settings)
                return {"ok": True, "settings": settings, "gateway": self._health(c)}
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
            try:
                import MetaTrader5 as mt5  # type: ignore

                mt5.shutdown()
            except Exception:
                pass
            settings["session_status"] = "DISCONNECTED"
            self._save_settings(c, settings)
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
