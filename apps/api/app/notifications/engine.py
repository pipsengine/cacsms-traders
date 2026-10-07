"""Alert Engine: normalized domain events → validation → deduplication / re-arm → notification queue.

Provider-independent (MT5 and cTrader events look the same) and SMTP-free: it only writes alert events and queued
deliveries; the email worker sends them later, so analysis never waits on mail delivery.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..core.audit import write_audit
from ..market.channel_events import DomainEvent, Observation
from ..market.scanner_config import GOLD
from .render import subject
from .smtp import smtp_config
from .store import ALERT_TYPES, SYSTEM_ALERT_TYPES, NotificationStore, now_iso


def dedup_key(e: DomainEvent) -> str:
    """Deterministic identity: type | symbol | timeframe | channel/structure | direction | qualifier | confirmed bar time."""
    if e.event_type == "CHANNEL_TOUCH":
        # The live channel is refitted every bar, so a boundary touch is identified by boundary + bar, not by the fit.
        parts = [e.event_type, e.symbol, e.timeframe or "-"]
    else:
        parts = [e.event_type, e.symbol, e.timeframe or "-", e.channel_id or e.structure_id or "-", e.direction or "-"]
    if e.identity and e.identity != e.event_time:
        parts.append(e.identity)
    parts.append(e.event_time[:16])
    return "|".join(parts)


def suppression_reason(settings: dict, e: DomainEvent, smtp_problems: list[str]) -> str | None:
    if not settings["email_enabled"]:
        return "Email notifications are disabled"
    if not settings["alert_types"].get(e.event_type, False):
        return f"{ALERT_TYPES.get(e.event_type, e.event_type)} alerts are disabled"
    if e.event_type not in SYSTEM_ALERT_TYPES:
        if e.timeframe and e.timeframe not in settings["timeframes"]:
            return f"Timeframe {e.timeframe} is not enabled for alerts"
        if e.symbol == GOLD and not settings["xauusd_enabled"]:
            return "XAUUSD alerts are disabled"
        if settings["symbols"] and e.symbol not in settings["symbols"]:
            return f"{e.symbol} is not in the alert symbol list"
    if smtp_problems:
        return "SMTP transport not ready: " + "; ".join(smtp_problems)
    return None


class AlertEngine:
    def __init__(self, conn, tenant_id: str, account_id: str = ""):
        self.conn = conn
        self.tenant = tenant_id
        self.account = account_id
        self.store = NotificationStore(conn, tenant_id)

    def _audit(self, action: str, eid: str, payload: dict, reason: str | None = None) -> None:
        write_audit(self.conn, self.tenant or None, None, action, "alert_event", eid, None, payload, reason)

    def _armed(self, e: DomainEvent, settings: dict, now: datetime) -> bool:
        required = settings["touch_rearm_bars"] if e.event_type == "CHANNEL_TOUCH" else 1
        state = self.store.rearm_state(e.rearm_key)
        if state is None:
            armed = e.inactive_before is None or e.inactive_before >= required
        else:
            armed = state["armed"]
        if armed and state and state.get("last_fired_at") and settings["cooldown_minutes"] > 0:
            fired = datetime.fromisoformat(state["last_fired_at"])
            armed = now - fired >= timedelta(minutes=settings["cooldown_minutes"])
        return armed

    def process(self, events: list[DomainEvent], observations: list[Observation], now: datetime) -> dict:
        settings = self.store.settings()
        recipients = self.store.recipients()
        problems = smtp_config(self.conn).problems()
        report = {"queued": 0, "suppressed": 0, "duplicates": 0, "stale": 0, "not_armed": 0}
        required = settings["touch_rearm_bars"]
        for ob in observations:
            need = required if ob.rearm_key.startswith("CHANNEL_TOUCH|") else 1
            if ob.inactive_bars >= need:
                self.store.rearm(ob.rearm_key, ob.prefix, now)
        for e in events:
            if e.age_bars > settings["max_event_age_bars"]:
                report["stale"] += 1
                continue
            key = dedup_key(e)
            if self.store.event_exists(key):
                report["duplicates"] += 1
                continue
            if e.rearm_key and not self._armed(e, settings, now):
                report["not_armed"] += 1
                continue
            reason = suppression_reason(settings, e, problems)
            targets = [r for r in recipients if r["enabled"] and (not r["alert_types"] or e.event_type in r["alert_types"])]
            if reason is None and not targets:
                reason = "No enabled recipients for this alert type"
            stamp = now_iso(now)
            history = [{"status": "DETECTED", "at": stamp}]
            if reason:
                history.append({"status": "SUPPRESSED", "at": stamp, "reason": reason})
                status = "SUPPRESSED"
            else:
                history += [{"status": "VALIDATED", "at": stamp}, {"status": "QUEUED", "at": stamp, "recipients": len(targets)}]
                status = "QUEUED"
            eid = self.store.insert_event(self.account, e, key, status, reason, history, now)
            if eid is None:
                report["duplicates"] += 1
                continue
            if e.rearm_key:
                self.store.disarm(e.rearm_key, now)
            summary = {"event_type": e.event_type, "symbol": e.symbol, "timeframe": e.timeframe, "direction": e.direction,
                       "provider": e.provider, "event_time": e.event_time, "deduplication_key": key}
            self._audit("ALERT_DETECTED", eid, summary)
            if reason:
                self._audit("ALERT_SUPPRESSED", eid, summary, reason)
                report["suppressed"] += 1
                continue
            subj = subject({"symbol": e.symbol, "timeframe": e.timeframe, "event_type": e.event_type, "direction": e.direction,
                            "tit_level": e.tit_level, "metadata": e.metadata})
            for r in targets:
                self.store.create_delivery(eid, r, r["email"], subj, settings["max_attempts"], now)
            self._audit("ALERT_QUEUED", eid, {**summary, "recipients": len(targets)})
            report["queued"] += 1
        return report
