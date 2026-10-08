"""Notification persistence (SQLite locally, PostgreSQL/Neon in production). Every query is tenant-scoped."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from ..market.channel_intelligence import EVENT_TIMEFRAMES
from ..market.provenance import values

ALERT_TYPES = {
    "CHANNEL_BREAK": "Channel Break",
    "CHANNEL_TOUCH": "Channel Touch",
    "BREAK_RETEST_CONTINUATION": "Break & Retest / Trend Continuation",
    "TIT_DETECTED": "Trend-in-Trend (TiT)",
    "AI_OUTLOOK_PUBLISHED": "AI Analysis Complete",
}
# Platform-wide alerts (not tied to one symbol or timeframe): symbol, timeframe and XAUUSD filters do not apply.
SYSTEM_ALERT_TYPES = frozenset({"AI_OUTLOOK_PUBLISHED"})
# Suppression reasons that concern email delivery only: the event still passed the alert rules and belongs in the in-app bell.
EMAIL_OFF_REASON = "Email notifications are disabled"
SMTP_NOT_READY_REASON = "SMTP transport not ready"
EVENT_STATUSES = ("DETECTED", "VALIDATED", "QUEUED", "SENDING", "SENT", "FAILED", "RETRY_PENDING", "SUPPRESSED", "DUPLICATE")
DUE_STATUSES = ("QUEUED", "RETRY_PENDING")
SETTINGS_DEFAULTS = {
    "email_enabled": True,
    "alert_types": {k: True for k in ALERT_TYPES},
    "timeframes": list(EVENT_TIMEFRAMES),
    "symbols": [],
    "xauusd_enabled": True,
    "touch_rearm_bars": 2,
    "cooldown_minutes": 0,
    "max_event_age_bars": 2,
    "max_attempts": 4,
}
EVENT_COLUMNS = ("id", "tenant_id", "trading_account_id", "event_type", "symbol", "timeframe", "direction", "provider", "event_time",
                 "detected_at", "price", "level", "channel_id", "structure_id", "tit_level", "confidence", "metadata_json", "status",
                 "status_reason", "deduplication_key", "history_json", "queued_at", "sent_at", "attempt_count", "last_attempt_at",
                 "failure_reason", "updated_at")
DELIVERY_COLUMNS = ("id", "tenant_id", "alert_event_id", "recipient_id", "recipient_email", "kind", "channel", "status", "subject",
                    "attempt_count", "max_attempts", "next_attempt_at", "queued_at", "last_attempt_at", "sent_at", "failure_reason",
                    "error_kind", "created_at", "updated_at")
RECIPIENT_COLUMNS = ("id", "tenant_id", "email", "name", "enabled", "alert_types", "created_at", "updated_at")


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


def _row(r, columns) -> dict:
    return dict(r) if hasattr(r, "keys") else dict(zip(columns, tuple(r)))


def _json(raw, default):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return default
    return default if value is None else value


def event_dict(r) -> dict:
    d = _row(r, EVENT_COLUMNS)
    d["metadata"] = _json(d.pop("metadata_json", None), {})
    d["history"] = _json(d.pop("history_json", None), [])
    return d


def recipient_dict(r) -> dict:
    d = _row(r, RECIPIENT_COLUMNS)
    d["enabled"] = bool(d["enabled"])
    d["alert_types"] = [t for t in _json(d.get("alert_types"), []) if t in ALERT_TYPES]
    return d


class NotificationStore:
    def __init__(self, conn, tenant_id: str):
        self.conn = conn
        self.tenant = tenant_id

    # ----- settings -----

    def settings(self) -> dict:
        r = self.conn.execute(
            "SELECT email_enabled, alert_types_json, timeframes_json, symbols_json, xauusd_enabled, touch_rearm_bars, cooldown_minutes, "
            "max_event_age_bars, max_attempts, updated_by, updated_at FROM notification_settings WHERE tenant_id=?", (self.tenant,)).fetchone()
        out = {**SETTINGS_DEFAULTS, "alert_types": dict(SETTINGS_DEFAULTS["alert_types"]), "updated_by": None, "updated_at": None}
        if not r:
            return out
        v = values(r)
        out.update(email_enabled=bool(v[0]), timeframes=[t for t in _json(v[2], []) if t in EVENT_TIMEFRAMES],
                   symbols=[str(s).upper() for s in _json(v[3], [])], xauusd_enabled=bool(v[4]), touch_rearm_bars=int(v[5]),
                   cooldown_minutes=int(v[6]), max_event_age_bars=int(v[7]), max_attempts=int(v[8]), updated_by=v[9], updated_at=v[10])
        out["alert_types"].update({k: bool(b) for k, b in _json(v[1], {}).items() if k in ALERT_TYPES})
        return out

    def save_settings(self, s: dict, user_id: str | None) -> None:
        stamp = now_iso()
        self.conn.execute(
            "INSERT INTO notification_settings(tenant_id, email_enabled, alert_types_json, timeframes_json, symbols_json, xauusd_enabled, "
            "touch_rearm_bars, cooldown_minutes, max_event_age_bars, max_attempts, updated_by, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(tenant_id) DO UPDATE SET email_enabled=excluded.email_enabled, alert_types_json=excluded.alert_types_json, "
            "timeframes_json=excluded.timeframes_json, symbols_json=excluded.symbols_json, xauusd_enabled=excluded.xauusd_enabled, "
            "touch_rearm_bars=excluded.touch_rearm_bars, cooldown_minutes=excluded.cooldown_minutes, max_event_age_bars=excluded.max_event_age_bars, "
            "max_attempts=excluded.max_attempts, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
            (self.tenant, int(s["email_enabled"]), json.dumps(s["alert_types"]), json.dumps(s["timeframes"]), json.dumps(s["symbols"]),
             int(s["xauusd_enabled"]), int(s["touch_rearm_bars"]), int(s["cooldown_minutes"]), int(s["max_event_age_bars"]),
             int(s["max_attempts"]), user_id, stamp, stamp),
        )

    # ----- recipients -----

    def recipients(self) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(RECIPIENT_COLUMNS)} FROM notification_recipients WHERE tenant_id=? ORDER BY email",
                                 (self.tenant,)).fetchall()
        return [recipient_dict(r) for r in rows]

    def recipient(self, rid: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(RECIPIENT_COLUMNS)} FROM notification_recipients WHERE tenant_id=? AND id=?",
                              (self.tenant, rid)).fetchone()
        return recipient_dict(r) if r else None

    def add_recipient(self, email: str, name: str | None, enabled: bool, alert_types: list[str]) -> dict:
        stamp = now_iso()
        rid = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO notification_recipients(id, tenant_id, email, name, enabled, alert_types, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (rid, self.tenant, email.strip().lower(), (name or "").strip() or None, int(enabled), json.dumps(alert_types), stamp, stamp))
        return self.recipient(rid)

    def update_recipient(self, rid: str, **changes) -> dict | None:
        cur = self.recipient(rid)
        if not cur:
            return None
        merged = {**cur, **{k: v for k, v in changes.items() if v is not None}}
        self.conn.execute(
            "UPDATE notification_recipients SET email=?, name=?, enabled=?, alert_types=?, updated_at=? WHERE tenant_id=? AND id=?",
            (merged["email"].strip().lower(), (merged.get("name") or "").strip() or None, int(merged["enabled"]),
             json.dumps(merged["alert_types"]), now_iso(), self.tenant, rid))
        return self.recipient(rid)

    def delete_recipient(self, rid: str) -> bool:
        cur = self.conn.execute("DELETE FROM notification_recipients WHERE tenant_id=? AND id=?", (self.tenant, rid))
        return (cur.rowcount or 0) > 0

    # ----- re-arm state -----

    def rearm_state(self, key: str) -> dict | None:
        r = self.conn.execute("SELECT armed, last_fired_at FROM alert_rearm_state WHERE tenant_id=? AND rearm_key=?", (self.tenant, key)).fetchone()
        if not r:
            return None
        armed, fired = values(r)
        return {"armed": bool(armed), "last_fired_at": fired}

    def rearm(self, key: str, prefix: bool, now: datetime) -> None:
        stamp = now_iso(now)
        if prefix:
            self.conn.execute("UPDATE alert_rearm_state SET armed=1, last_seen_at=?, updated_at=? WHERE tenant_id=? AND armed=0 AND rearm_key LIKE ?",
                              (stamp, stamp, self.tenant, key + "%"))
        else:
            self.conn.execute("UPDATE alert_rearm_state SET armed=1, last_seen_at=?, updated_at=? WHERE tenant_id=? AND armed=0 AND rearm_key=?",
                              (stamp, stamp, self.tenant, key))

    def disarm(self, key: str, now: datetime) -> None:
        stamp = now_iso(now)
        self.conn.execute(
            "INSERT INTO alert_rearm_state(tenant_id, rearm_key, armed, last_fired_at, last_seen_at, updated_at) VALUES(?,?,0,?,?,?) "
            "ON CONFLICT(tenant_id, rearm_key) DO UPDATE SET armed=0, last_fired_at=excluded.last_fired_at, last_seen_at=excluded.last_seen_at, "
            "updated_at=excluded.updated_at", (self.tenant, key, stamp, stamp, stamp))

    # ----- events -----

    def event_exists(self, dedup_key: str) -> bool:
        return self.conn.execute("SELECT 1 FROM alert_events WHERE tenant_id=? AND deduplication_key=?", (self.tenant, dedup_key)).fetchone() is not None

    def insert_event(self, account_id: str, e, dedup_key: str, status: str, reason: str | None, history: list[dict], now: datetime) -> str | None:
        eid = str(uuid.uuid4())
        stamp = now_iso(now)
        cur = self.conn.execute(
            f"INSERT INTO alert_events({','.join(EVENT_COLUMNS)}) VALUES({','.join('?' * len(EVENT_COLUMNS))}) "
            "ON CONFLICT(tenant_id, deduplication_key) DO NOTHING",
            (eid, self.tenant, account_id or "", e.event_type, e.symbol, e.timeframe, e.direction, e.provider, e.event_time, stamp, e.price,
             e.level, e.channel_id, e.structure_id, e.tit_level, e.confidence, json.dumps(e.metadata, default=str), status, reason, dedup_key,
             json.dumps(history), stamp if status == "QUEUED" else None, None, 0, None, None, stamp))
        return eid if (cur.rowcount or 0) > 0 else None

    def event(self, eid: str) -> dict | None:
        r = self.conn.execute(f"SELECT {','.join(EVENT_COLUMNS)} FROM alert_events WHERE tenant_id=? AND id=?", (self.tenant, eid)).fetchone()
        return event_dict(r) if r else None

    def events(self, limit: int = 100, status: str | None = None, event_type: str | None = None) -> list[dict]:
        sql = f"SELECT {','.join(EVENT_COLUMNS)} FROM alert_events WHERE tenant_id=?"
        params: list = [self.tenant]
        if status:
            sql += " AND status=?"
            params.append(status)
        if event_type:
            sql += " AND event_type=?"
            params.append(event_type)
        sql += " ORDER BY detected_at DESC LIMIT ?"
        params.append(limit)
        return [event_dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def inbox(self, since: str, limit: int = 8) -> dict:
        """Top-bar bell: every event that passed the alert rules (emailed or not), newest first."""
        visible = "tenant_id=? AND (status<>'SUPPRESSED' OR status_reason=? OR status_reason LIKE ?)"
        scope = (self.tenant, EMAIL_OFF_REASON, SMTP_NOT_READY_REASON + "%")
        counted = self.conn.execute(
            f"SELECT COUNT(*) AS unread FROM alert_events WHERE {visible} AND detected_at>?", (*scope, since)
        ).fetchone()
        unread = values(counted)[0] if counted else 0
        cols = ("id", "event_type", "symbol", "timeframe", "direction", "status", "detected_at", "metadata_json")
        rows = self.conn.execute(
            f"SELECT {','.join(cols)} FROM alert_events WHERE {visible} ORDER BY detected_at DESC LIMIT ?", (*scope, limit)).fetchall()
        items = []
        for r in rows:
            d = _row(r, cols)
            meta = _json(d.pop("metadata_json"), {})
            d["label"] = ALERT_TYPES.get(d["event_type"], d["event_type"])
            detected = d["detected_at"]
            d["detected_at"] = detected if isinstance(detected, str) else detected.isoformat()
            d["unread"] = d["detected_at"] > since
            if d["event_type"] in SYSTEM_ALERT_TYPES:
                d["qualified"] = (meta.get("counts") or {}).get("qualified")
                d["late"] = bool(meta.get("late"))
            items.append(d)
        return {"unread": int(unread or 0), "items": items}

    def update_event(self, eid: str, **fields) -> None:
        history_entry = fields.pop("history_entry", None)
        if history_entry:
            cur = self.event(eid)
            fields["history_json"] = json.dumps(((cur or {}).get("history") or []) + [history_entry])
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE alert_events SET {cols} WHERE tenant_id=? AND id=?", (*fields.values(), self.tenant, eid))

    # ----- deliveries -----

    def create_delivery(self, event_id: str | None, recipient: dict | None, email: str, subject: str, max_attempts: int, now: datetime,
                        kind: str = "ALERT", status: str = "QUEUED") -> str | None:
        did = str(uuid.uuid4())
        stamp = now_iso(now)
        cur = self.conn.execute(
            f"INSERT INTO notification_deliveries({','.join(DELIVERY_COLUMNS)}) VALUES({','.join('?' * len(DELIVERY_COLUMNS))}) "
            "ON CONFLICT(alert_event_id, recipient_id) DO NOTHING",
            (did, self.tenant, event_id, (recipient or {}).get("id"), email, kind, "EMAIL", status, subject, 0, max_attempts, stamp, stamp,
             None, None, None, None, stamp, stamp))
        return did if (cur.rowcount or 0) > 0 else None

    def deliveries_for(self, event_id: str) -> list[dict]:
        rows = self.conn.execute(f"SELECT {','.join(DELIVERY_COLUMNS)} FROM notification_deliveries WHERE tenant_id=? AND alert_event_id=?",
                                 (self.tenant, event_id)).fetchall()
        return [_row(r, DELIVERY_COLUMNS) for r in rows]

    def update_delivery(self, did: str, **fields) -> None:
        fields["updated_at"] = now_iso()
        cols = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE notification_deliveries SET {cols} WHERE tenant_id=? AND id=?", (*fields.values(), self.tenant, did))

    def stats(self, since: str) -> dict:
        def one(sql, params):
            r = self.conn.execute(sql, params).fetchone()
            return values(r)[0] if r else None

        t = self.tenant
        return {
            "last_sent_at": one("SELECT MAX(sent_at) FROM notification_deliveries WHERE tenant_id=? AND status='SENT' AND kind='ALERT'", (t,)),
            "failed_total": one("SELECT COUNT(*) FROM notification_deliveries WHERE tenant_id=? AND status='FAILED'", (t,)) or 0,
            "failed_recent": one("SELECT COUNT(*) FROM notification_deliveries WHERE tenant_id=? AND status='FAILED' AND updated_at>=?", (t, since)) or 0,
            "sent_recent": one("SELECT COUNT(*) FROM notification_deliveries WHERE tenant_id=? AND status='SENT' AND sent_at>=?", (t, since)) or 0,
            "pending": one("SELECT COUNT(*) FROM notification_deliveries WHERE tenant_id=? AND status IN ('QUEUED','RETRY_PENDING','SENDING')", (t,)) or 0,
            "events_recent": one("SELECT COUNT(*) FROM alert_events WHERE tenant_id=? AND detected_at>=?", (t, since)) or 0,
            "suppressed_recent": one("SELECT COUNT(*) FROM alert_events WHERE tenant_id=? AND status='SUPPRESSED' AND detected_at>=?", (t, since)) or 0,
        }


def due_deliveries(conn, now: datetime, lease_cutoff: datetime, limit: int) -> list[dict]:
    """Deliveries ready to send across tenants (the worker is platform-wide; each row keeps its tenant)."""
    rows = conn.execute(
        f"SELECT {','.join(DELIVERY_COLUMNS)} FROM notification_deliveries WHERE "
        "((status IN ('QUEUED','RETRY_PENDING') AND next_attempt_at<=?) OR (status='SENDING' AND last_attempt_at<?)) "
        "ORDER BY next_attempt_at LIMIT ?", (now_iso(now), now_iso(lease_cutoff), limit)).fetchall()
    return [_row(r, DELIVERY_COLUMNS) for r in rows]


def claim(conn, d: dict, now: datetime, lease_cutoff: datetime) -> bool:
    stamp = now_iso(now)
    cur = conn.execute(
        "UPDATE notification_deliveries SET status='SENDING', attempt_count=attempt_count+1, last_attempt_at=?, updated_at=? "
        "WHERE id=? AND ((status IN ('QUEUED','RETRY_PENDING') AND next_attempt_at<=?) OR (status='SENDING' AND last_attempt_at<?))",
        (stamp, stamp, d["id"], stamp, now_iso(lease_cutoff)))
    return (cur.rowcount or 0) > 0
