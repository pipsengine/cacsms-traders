"""Notification bus and email worker.

``publish_channel_events`` is the hand-off from the intelligence engines (they publish; this subsystem decides). The
dispatcher claims due deliveries, sends them over one SMTP session and applies bounded exponential backoff. Every
failure is contained here — market data, strength, scanner, structure and channel analysis never depend on mail.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from ..core.audit import write_audit
from ..core.database import db
from ..market.channel_events import channel_events
from . import render
from .engine import AlertEngine
from .smtp import SmtpConfigError, SmtpSender, classify, describe, record_health, smtp_config
from .store import NotificationStore, claim, due_deliveries, now_iso

log = logging.getLogger("cacsms.notifications")
RETRY_MINUTES = (1, 5, 15)
LEASE = timedelta(minutes=10)
EXPIRE_AFTER = timedelta(hours=24)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enabled() -> bool:
    return os.getenv("NOTIFICATIONS_ENABLED", "1").strip().lower() not in ("0", "false", "no")


# ----- bus -----


def alert_scope(conn) -> tuple[str, str]:
    """Tenant owning the market-data scope that produced the analysis (explicit → MT5 bridge tenant → primary tenant)."""
    from ..market.market_data import configuration
    from ..market.provenance import values

    cfg = configuration(conn)
    tenant = cfg.get("tenant_id") or cfg.get("mt5_tenant_id") or ""
    if not tenant:
        row = conn.execute("SELECT id FROM tenants WHERE status='ACTIVE' ORDER BY created_at, id LIMIT 1").fetchone()
        tenant = str(values(row)[0]) if row else ""
    return tenant, cfg.get("account_id") or ""


def publish_channel_events(analysis: dict[str, dict], provider: str | None, now: datetime | None = None) -> dict:
    """Channel Intelligence → Alert Engine for the tenant whose market-data scope produced the analysis."""
    now = now or utcnow()
    events, observations = [], []
    for symbol, a in analysis.items():
        core = (a or {}).get("channel")
        if not core or "excluded" in a:
            continue
        e, o = channel_events(symbol, core, provider)
        events += e
        observations += o
    with db() as conn:
        tenant, account = alert_scope(conn)
        report = AlertEngine(conn, tenant, account).process(events, observations, now)
    report["events"] = len(events)
    return report


# ----- dispatch -----


def _next_retry(attempt: int, now: datetime) -> datetime:
    return now + timedelta(minutes=RETRY_MINUTES[min(attempt - 1, len(RETRY_MINUTES) - 1)])


def _roll_up(store: NotificationStore, event_id: str, now: datetime) -> str | None:
    """Event status from its deliveries; returns the new status when it changed."""
    ev = store.event(event_id)
    if not ev:
        return None
    ds = store.deliveries_for(event_id)
    states = [d["status"] for d in ds]
    if states and all(s == "SENT" for s in states):
        status = "SENT"
    elif "SENDING" in states:
        status = "SENDING"
    elif "RETRY_PENDING" in states:
        status = "RETRY_PENDING"
    elif "QUEUED" in states:
        status = "QUEUED"
    elif "SENT" in states:
        status = "SENT"
    else:
        status = "FAILED"
    failures = [d for d in ds if d["status"] in ("FAILED", "RETRY_PENDING") and d.get("failure_reason")]
    fields = {"status": status, "attempt_count": max([d["attempt_count"] or 0 for d in ds] or [0]),
              "last_attempt_at": max([d["last_attempt_at"] for d in ds if d.get("last_attempt_at")] or [None], key=lambda x: x or ""),
              "failure_reason": failures[-1]["failure_reason"] if failures else None}
    if status == "SENT":
        fields["sent_at"] = max(d["sent_at"] for d in ds if d.get("sent_at"))
        if failures:
            fields["status_reason"] = f"{len(failures)} of {len(ds)} recipients failed"
    if status != ev["status"]:
        fields["history_entry"] = {"status": status, "at": now_iso(now)}
    store.update_event(event_id, **fields)
    return status if status != ev["status"] else None


def dispatch(now: datetime | None = None, *, limit: int = 25, budget_seconds: float = 20.0) -> dict:
    now = now or utcnow()
    started = time.monotonic()
    report = {"sent": 0, "retry": 0, "failed": 0, "expired": 0}
    with db() as conn:
        cfg = smtp_config(conn)
        if not cfg.ready:
            report["skipped"] = "; ".join(cfg.problems())
            return report
        batch = []
        for d in due_deliveries(conn, now, now - LEASE, limit):
            if claim(conn, d, now, now - LEASE):
                d["attempt_count"] = (d["attempt_count"] or 0) + 1
                batch.append(d)
        if not batch:
            return report
        for tenant, eid in {(d["tenant_id"], d["alert_event_id"]) for d in batch if d.get("alert_event_id")}:
            _roll_up(NotificationStore(conn, tenant), eid, now)
        conn.commit()
        touched: set[tuple[str, str]] = set()
        sender, session_error = None, None
        try:
            for d in batch:
                store = NotificationStore(conn, d["tenant_id"])
                ev = store.event(d["alert_event_id"]) if d.get("alert_event_id") else None
                stamp = now_iso(now)
                if ev is None:
                    store.update_delivery(d["id"], status="FAILED", failure_reason="Alert event missing", error_kind="EXPIRED")
                    report["expired"] += 1
                    continue
                touched.add((d["tenant_id"], ev["id"]))
                queued = datetime.fromisoformat(d["queued_at"]) if d.get("queued_at") else now
                if now - queued > EXPIRE_AFTER:
                    store.update_delivery(d["id"], status="FAILED", failure_reason="Expired before delivery", error_kind="EXPIRED")
                    report["expired"] += 1
                    continue
                if time.monotonic() - started > budget_seconds:
                    # Out of time: release the claim without consuming an attempt.
                    store.update_delivery(d["id"], status="RETRY_PENDING" if d["attempt_count"] > 1 else "QUEUED",
                                          attempt_count=d["attempt_count"] - 1, next_attempt_at=stamp)
                    continue
                try:
                    if session_error is not None:
                        raise session_error
                    if sender is None:
                        sender = SmtpSender(cfg).__enter__()
                    sender.send(render.alert_message(cfg, ev, d["recipient_email"]))
                except Exception as exc:  # noqa: BLE001 - every SMTP failure is classified, never raised
                    kind, retryable = classify(exc)
                    reason = describe(kind, exc, conn, cfg)
                    if sender is None:
                        # Connecting or logging in failed: the rest of this batch would fail the same way.
                        session_error = exc
                    final = not retryable or d["attempt_count"] >= (d["max_attempts"] or 1)
                    if final:
                        store.update_delivery(d["id"], status="FAILED", failure_reason=reason, error_kind=kind)
                        write_audit(conn, d["tenant_id"] or None, None, "ALERT_FAILED", "alert_event", ev["id"], None,
                                    {"recipient": d["recipient_email"], "attempts": d["attempt_count"], "error_kind": kind}, reason)
                        report["failed"] += 1
                    else:
                        store.update_delivery(d["id"], status="RETRY_PENDING", failure_reason=reason, error_kind=kind,
                                              next_attempt_at=now_iso(_next_retry(d["attempt_count"], now)))
                        report["retry"] += 1
                    record_health(conn, last_failure_at=stamp, last_error=reason, last_error_kind=kind)
                    log.warning("Alert email to recipient %s failed (%s): %s", d["id"], kind, reason)
                else:
                    store.update_delivery(d["id"], status="SENT", sent_at=stamp, failure_reason=None, error_kind=None)
                    write_audit(conn, d["tenant_id"] or None, None, "ALERT_SENT", "alert_event", ev["id"], None,
                                {"recipient": d["recipient_email"], "attempts": d["attempt_count"], "subject": d.get("subject")})
                    record_health(conn, last_success_at=stamp, last_error=None, last_error_kind=None)
                    report["sent"] += 1
        finally:
            if sender is not None:
                sender.__exit__(None, None, None)
        for tenant, eid in touched:
            _roll_up(NotificationStore(conn, tenant), eid, now)
    return report


# ----- test email -----


def send_test_email(conn, tenant_id: str, user_id: str | None, recipients: list[str]) -> dict:
    """SMTP-only check: sends the fixed test message; never creates an alert event."""
    cfg = smtp_config(conn)
    store = NotificationStore(conn, tenant_id)
    stamp = now_iso()
    try:
        if not recipients:
            raise SmtpConfigError("No recipient — add a recipient or enter a test address")
        with SmtpSender(cfg) as sender:
            for to in recipients:
                sender.send(render.test_message(cfg, to))
    except Exception as exc:  # noqa: BLE001
        kind, _ = classify(exc)
        reason = describe(kind, exc, conn, cfg)
        for to in recipients:
            store.create_delivery(None, None, to, render.TEST_SUBJECT, 1, utcnow(), kind="TEST", status="FAILED")
        result = {"status": "FAILED", "at": stamp, "error": reason, "error_kind": kind, "recipients": recipients}
        record_health(conn, last_test={k: v for k, v in result.items() if k != "recipients"}, last_failure_at=stamp,
                      last_error=reason, last_error_kind=kind)
        write_audit(conn, tenant_id or None, user_id, "SMTP_TEST_FAILED", "smtp", "smtp", None,
                    {"recipients": recipients, "error_kind": kind, "host": cfg.host, "port": cfg.port}, reason)
        return result
    for to in recipients:
        did = store.create_delivery(None, None, to, render.TEST_SUBJECT, 1, utcnow(), kind="TEST", status="SENT")
        store.update_delivery(did, sent_at=stamp, attempt_count=1, last_attempt_at=stamp)
    result = {"status": "SENT", "at": stamp, "error": None, "error_kind": None, "recipients": recipients}
    record_health(conn, last_test={k: v for k, v in result.items() if k != "recipients"}, last_success_at=stamp,
                  last_error=None, last_error_kind=None)
    write_audit(conn, tenant_id or None, user_id, "SMTP_TEST_SENT", "smtp", "smtp", None, {"recipients": recipients, "host": cfg.host, "port": cfg.port})
    return result


# ----- scheduling -----


def run_cycle(now: datetime | None = None) -> dict:
    """Serverless entry point (cron): advance the scanner (which publishes channel events), then deliver due emails."""
    report: dict = {"at": now_iso(now)}
    try:
        from ..market.scanner_engine import get_scanner_engine, scanner_enabled

        if scanner_enabled():
            engine = get_scanner_engine()
            engine.tick_on_demand()
            report["scanner"] = engine.meta().get("state") if hasattr(engine, "meta") else None
    except Exception as exc:  # noqa: BLE001
        log.exception("Scanner advance for notifications failed")
        report["scanner_error"] = type(exc).__name__
    try:
        report["dispatch"] = dispatch(now)
    except Exception as exc:  # noqa: BLE001
        log.exception("Notification dispatch failed")
        report["dispatch_error"] = type(exc).__name__
    return report


class NotificationWorker:
    def __init__(self, interval: float | None = None):
        self.interval = interval or float(os.getenv("NOTIFICATION_DISPATCH_SECONDS", "20") or 20)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(self.interval):
                try:
                    dispatch()
                except Exception:
                    log.exception("Notification dispatch tick failed")

        self._thread = threading.Thread(target=loop, name="notification-worker", daemon=True)
        self._thread.start()
        log.info("Notification worker started (interval=%ss)", self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=10)


_worker: NotificationWorker | None = None
_worker_lock = threading.Lock()


def get_notification_worker() -> NotificationWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = NotificationWorker()
        return _worker
