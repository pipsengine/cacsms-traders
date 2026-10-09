"""Maintain local MT5 IPC for tenants with session_status=CONNECTED in SQLite (tenant_settings)."""
from __future__ import annotations

import json
import logging
import threading
import time

from ..core.database import db
from ..market import mt5_session
from .mt5_connection import SETTINGS_KEY, ensure_gateway_session, LocalMT5Gateway

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 10.0


class LocalMT5SessionKeeper:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mt5-session-keeper", daemon=True)
        self._thread.start()
        log.info("Local MT5 session keeper started")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(DEFAULT_INTERVAL):
            try:
                self._tick()
            except Exception:
                log.exception("Local MT5 session keeper tick failed")

    def _tick(self) -> None:
        with db() as conn:
            rows = conn.execute(
                "SELECT tenant_id, value_json FROM tenant_settings WHERE key=?",
                (SETTINGS_KEY,),
            ).fetchall()
        targets: list[tuple[str, dict, float]] = []
        for row in rows:
            settings = json.loads(row["value_json"])
            if settings.get("session_status") != "CONNECTED":
                continue
            try:
                interval = float(settings.get("heartbeat_interval_seconds") or DEFAULT_INTERVAL)
            except (TypeError, ValueError):
                interval = DEFAULT_INTERVAL
            targets.append((row["tenant_id"], settings, max(5.0, min(interval, 120.0))))

        if not targets:
            return

        for tenant_id, settings, interval in targets:
            if self._stop.is_set():
                return
            last = settings.get("last_heartbeat_at")
            if last:
                try:
                    from datetime import datetime, timezone

                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
                    if age < interval * 0.85:
                        continue
                except ValueError:
                    pass
            with db() as conn:
                restored = ensure_gateway_session(conn, tenant_id)
                if restored.get("restored"):
                    log.info("MT5 session re-attached for tenant %s", tenant_id)
                gw = LocalMT5Gateway(tenant_id)
                current = gw._load_settings(conn)
                if current.get("session_status") != "CONNECTED":
                    continue
                if mt5_session.is_initialized():
                    gw._touch_heartbeat(conn, current)
                elif current.get("auto_reconnect", True):
                    current["last_error"] = current.get("last_error") or (
                        "MT5 session lost — open your broker terminal or use Connect in System Control."
                    )
                    gw._save_settings(conn, current)


_keeper: LocalMT5SessionKeeper | None = None
_keeper_lock = threading.Lock()


def get_mt5_session_keeper() -> LocalMT5SessionKeeper:
    global _keeper
    with _keeper_lock:
        if _keeper is None:
            _keeper = LocalMT5SessionKeeper()
        return _keeper
