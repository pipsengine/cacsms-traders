"""Notifications → Email Alerts API: tenant alert settings, recipients, SMTP transport, test email, history and the job.

SMTP_PASSWORD / the stored App Password is write-only: responses only say whether one is configured and where from."""
from __future__ import annotations

import hmac
import os
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.audit import write_audit
from ..core.database import db
from ..deps import current_user
from ..market.channel_intelligence import EVENT_TIMEFRAMES
from ..market.scanner_config import SCANNER_UNIVERSE
from ..notifications import smtp as smtp_mod
from ..notifications.store import ALERT_TYPES, EVENT_STATUSES, NotificationStore
from ..notifications.worker import RETRY_MINUTES, run_cycle, send_test_email, utcnow
from ..services.access import permissions_for, require_permission

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AlertSettingsIn(BaseModel):
    email_enabled: bool
    alert_types: dict[str, bool]
    timeframes: list[str]
    symbols: list[str] = Field(default_factory=list)
    xauusd_enabled: bool = True
    touch_rearm_bars: int = Field(2, ge=1, le=20)
    cooldown_minutes: int = Field(0, ge=0, le=1440)
    max_event_age_bars: int = Field(2, ge=1, le=6)
    max_attempts: int = Field(4, ge=1, le=6)


class SmtpIn(BaseModel):
    enabled: bool
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    security: str
    username: str = Field("", max_length=320)
    from_email: str = Field(..., min_length=3, max_length=320)
    from_name: str = Field("Cacsms Traders", max_length=120)
    password: str | None = Field(None, max_length=256)
    clear_password: bool = False


class RecipientIn(BaseModel):
    email: str
    name: str | None = None
    enabled: bool = True
    alert_types: list[str] = Field(default_factory=list)


class RecipientPatch(BaseModel):
    email: str | None = None
    name: str | None = None
    enabled: bool | None = None
    alert_types: list[str] | None = None


class TestIn(BaseModel):
    to: list[str] = Field(default_factory=list)


def _email(value: str) -> str:
    v = value.strip().lower()
    if not EMAIL.match(v):
        raise HTTPException(400, f"Invalid email address: {value}")
    return v


def _types(values: list[str]) -> list[str]:
    bad = [t for t in values if t not in ALERT_TYPES]
    if bad:
        raise HTTPException(400, f"Unknown alert type: {', '.join(bad)}")
    return list(dict.fromkeys(values))


def _can(conn, user: dict, tenant_id: str, code: str) -> bool:
    return bool(user.get("is_platform_admin")) or code in permissions_for(conn, user["id"], tenant_id)


def _overview(conn, user: dict, tenant_id: str) -> dict:
    store = NotificationStore(conn, tenant_id)
    cfg = smtp_mod.smtp_config(conn)
    since = (utcnow() - timedelta(days=7)).isoformat()
    return {
        "tenant_id": tenant_id,
        "settings": store.settings(),
        "recipients": store.recipients(),
        "smtp": {**cfg.public(), "vault_available": smtp_mod.vault_available(), "vault_error": smtp_mod.vault_error(conn),
                 "env_defaults": {k: v for k, v in smtp_mod.env_defaults().items()}, "overrides": sorted(smtp_mod.overrides(conn))},
        "health": smtp_mod.health(conn),
        "stats": store.stats(since),
        "retry_minutes": list(RETRY_MINUTES),
        "alert_types": [{"key": k, "label": v} for k, v in ALERT_TYPES.items()],
        "timeframes": list(EVENT_TIMEFRAMES),
        "symbols": list(SCANNER_UNIVERSE),
        "statuses": list(EVENT_STATUSES),
        "can_manage": _can(conn, user, tenant_id, "system.manage"),
        "can_manage_smtp": bool(user.get("is_platform_admin")),
        "analysis_only": True,
    }


@router.get("/email")
def email_overview(tenant_id: str = Query(...), user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.read")
        return _overview(conn, user, tenant_id)


@router.put("/email/settings")
def update_settings(body: AlertSettingsIn, tenant_id: str = Query(...), user=Depends(current_user)):
    tfs = [t for t in body.timeframes if t in EVENT_TIMEFRAMES]
    symbols = [s.upper() for s in body.symbols]
    unknown = [s for s in symbols if s not in SCANNER_UNIVERSE]
    if unknown:
        raise HTTPException(400, f"Unknown symbol: {', '.join(unknown)}")
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.manage")
        store = NotificationStore(conn, tenant_id)
        before = store.settings()
        new = {**body.model_dump(), "timeframes": tfs, "symbols": list(dict.fromkeys(symbols)),
               "alert_types": {k: bool(body.alert_types.get(k, False)) for k in ALERT_TYPES}}
        store.save_settings(new, user["id"])
        write_audit(conn, tenant_id, user["id"], "NOTIFICATION_SETTINGS_UPDATED", "notification_settings", tenant_id,
                    {k: before[k] for k in new}, new)
        return _overview(conn, user, tenant_id)


@router.put("/email/smtp")
def update_smtp(body: SmtpIn, tenant_id: str = Query(...), user=Depends(current_user)):
    """Platform SMTP transport (Super Administrator). Values override the SMTP_* environment defaults."""
    if not user.get("is_platform_admin"):
        raise HTTPException(403, "Super Administrator required to change the SMTP transport")
    security = body.security.strip().lower()
    if security not in smtp_mod.SECURITY_MODES:
        raise HTTPException(400, "Security must be starttls, ssl or none")
    from_email = _email(body.from_email)
    username = body.username.strip()
    with db() as conn:
        before = smtp_mod.smtp_config(conn).public()
        smtp_mod.save_setting(conn, smtp_mod.CONFIG_KEY, {"enabled": body.enabled, "host": body.host.strip(), "port": body.port,
                                                          "security": security, "username": username, "from_email": from_email,
                                                          "from_name": body.from_name.strip() or "Cacsms Traders"})
        password_change = None
        try:
            if body.clear_password:
                smtp_mod.clear_password(conn)
                password_change = "cleared"
            elif body.password and body.password.strip():
                smtp_mod.store_password(conn, body.password)
                password_change = "updated"
        except smtp_mod.SmtpConfigError as exc:
            raise HTTPException(400, str(exc)) from exc
        after = smtp_mod.smtp_config(conn).public()
        keep = ("enabled", "host", "port", "security", "username", "from_email", "from_name", "password_configured", "password_source")
        write_audit(conn, None, user["id"], "SMTP_CONFIGURATION_UPDATED", "smtp", "smtp", {k: before.get(k) for k in keep},
                    {**{k: after.get(k) for k in keep}, "password_change": password_change})
        return _overview(conn, user, tenant_id)


@router.post("/email/smtp/reset")
def reset_smtp(tenant_id: str = Query(...), user=Depends(current_user)):
    """Drop administrator overrides so the SMTP_* environment variables apply again (stored App Password is kept)."""
    if not user.get("is_platform_admin"):
        raise HTTPException(403, "Super Administrator required to change the SMTP transport")
    with db() as conn:
        before = smtp_mod.smtp_config(conn).public()
        conn.execute("DELETE FROM system_settings WHERE key=?", (smtp_mod.CONFIG_KEY,))
        write_audit(conn, None, user["id"], "SMTP_CONFIGURATION_UPDATED", "smtp", "smtp",
                    {k: before.get(k) for k in ("enabled", "host", "port", "security", "username", "from_email", "from_name")},
                    {"reset_to_environment": True})
        return _overview(conn, user, tenant_id)


@router.post("/email/recipients")
def add_recipient(body: RecipientIn, tenant_id: str = Query(...), user=Depends(current_user)):
    email = _email(body.email)
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.manage")
        store = NotificationStore(conn, tenant_id)
        if any(r["email"] == email for r in store.recipients()):
            raise HTTPException(409, f"{email} is already a recipient")
        r = store.add_recipient(email, body.name, body.enabled, _types(body.alert_types))
        write_audit(conn, tenant_id, user["id"], "NOTIFICATION_RECIPIENT_ADDED", "notification_recipient", r["id"], None, r)
        return _overview(conn, user, tenant_id)


@router.patch("/email/recipients/{rid}")
def update_recipient(rid: str, body: RecipientPatch, tenant_id: str = Query(...), user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.manage")
        store = NotificationStore(conn, tenant_id)
        before = store.recipient(rid)
        if not before:
            raise HTTPException(404, "Recipient not found")
        email = _email(body.email) if body.email is not None else None
        if email and email != before["email"] and any(r["email"] == email for r in store.recipients()):
            raise HTTPException(409, f"{email} is already a recipient")
        after = store.update_recipient(rid, email=email, name=body.name, enabled=body.enabled,
                                       alert_types=_types(body.alert_types) if body.alert_types is not None else None)
        write_audit(conn, tenant_id, user["id"], "NOTIFICATION_RECIPIENT_UPDATED", "notification_recipient", rid, before, after)
        return _overview(conn, user, tenant_id)


@router.delete("/email/recipients/{rid}")
def delete_recipient(rid: str, tenant_id: str = Query(...), user=Depends(current_user)):
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.manage")
        store = NotificationStore(conn, tenant_id)
        before = store.recipient(rid)
        if not before or not store.delete_recipient(rid):
            raise HTTPException(404, "Recipient not found")
        write_audit(conn, tenant_id, user["id"], "NOTIFICATION_RECIPIENT_REMOVED", "notification_recipient", rid, before, None)
        return _overview(conn, user, tenant_id)


@router.post("/email/test")
def test_email(body: TestIn, tenant_id: str = Query(...), user=Depends(current_user)):
    """Sends "[Cacsms Traders] Email Notification Test" over SMTP only — no alert event is created."""
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.manage")
        to = [_email(x) for x in body.to if x.strip()]
        if not to:
            to = [r["email"] for r in NotificationStore(conn, tenant_id).recipients() if r["enabled"]]
        result = send_test_email(conn, tenant_id, user["id"], to)
        return {"result": result, "overview": _overview(conn, user, tenant_id)}


@router.get("/email/events")
def events(tenant_id: str = Query(...), limit: int = Query(100, ge=1, le=500), status: str | None = Query(None),
           event_type: str | None = Query(None), user=Depends(current_user)):
    if status and status not in EVENT_STATUSES:
        raise HTTPException(400, "Unknown status")
    if event_type and event_type not in ALERT_TYPES:
        raise HTTPException(400, "Unknown alert type")
    with db() as conn:
        require_permission(conn, user, tenant_id, "system.read")
        store = NotificationStore(conn, tenant_id)
        rows = store.events(limit, status, event_type)
        for r in rows:
            r["deliveries"] = [{k: d[k] for k in ("recipient_email", "status", "attempt_count", "sent_at", "failure_reason", "next_attempt_at")}
                               for d in store.deliveries_for(r["id"])]
        return {"events": rows}


def _cron_authorized(authorization: str | None) -> None:
    secret = os.getenv("CRON_SECRET", "").strip()
    if secret and not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "Invalid cron credentials")


@router.get("/jobs/run")
def run_job(authorization: str | None = Header(default=None)):
    """Scheduler entry point (cron): scanner advance → channel events → Alert Engine → email dispatch. Idempotent."""
    _cron_authorized(authorization)
    return run_cycle()
