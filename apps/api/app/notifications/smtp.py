"""SMTP transport: configuration (environment defaults + administrator overrides), the App Password vault,
secret redaction, STARTTLS sending and failure classification.

The App Password is resolved server-side only — from an encrypted system setting written through the administration
API, otherwise ``SMTP_PASSWORD``. It is never returned by an API, logged, audited or included in an error message.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import smtplib
import socket
import ssl
from dataclasses import asdict, dataclass
from email.message import EmailMessage

from ..core.security import iso

CONFIG_KEY = "notifications.smtp"
SECRET_KEY = "notifications.smtp_secret"
HEALTH_KEY = "notifications.smtp_health"
SECURITY_MODES = ("starttls", "ssl", "none")
EDITABLE = ("enabled", "host", "port", "security", "username", "from_email", "from_name")
DEFAULTS = {"enabled": False, "host": "smtp.gmail.com", "port": 587, "security": "starttls", "username": "",
            "from_email": "", "from_name": "Cacsms Traders"}
KEY_ENV = ("SMTP_ENCRYPTION_KEY", "API_PROXY_SECRET", "CTRADER_CLIENT_SECRET")


class SmtpConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmtpConfig:
    enabled: bool
    host: str
    port: int
    security: str
    username: str
    from_email: str
    from_name: str
    password: str = ""
    password_source: str | None = None
    timeout: float = 20.0

    def problems(self) -> list[str]:
        out = []
        if not self.enabled:
            out.append("SMTP is disabled")
        if not self.host:
            out.append("SMTP host is not set")
        if not self.port:
            out.append("SMTP port is not set")
        if self.security not in SECURITY_MODES:
            out.append("SMTP security mode is invalid")
        if not self.from_email:
            out.append("Sender email is not set")
        if self.username and not self.password:
            out.append("SMTP password (Google App Password) is not configured")
        return out

    @property
    def ready(self) -> bool:
        return not self.problems()

    def public(self) -> dict:
        d = asdict(self)
        d.pop("password")
        d.pop("timeout")
        d["password_configured"] = bool(self.password)
        d["ready"] = self.ready
        d["problems"] = self.problems()
        return d


def _flag(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_defaults() -> dict:
    port = os.getenv("SMTP_PORT", "").strip()
    return {
        "enabled": _flag(os.getenv("SMTP_ENABLED"), DEFAULTS["enabled"]),
        "host": os.getenv("SMTP_HOST", "").strip() or DEFAULTS["host"],
        "port": int(port) if port.isdigit() else DEFAULTS["port"],
        "security": (os.getenv("SMTP_SECURITY", "").strip().lower() or DEFAULTS["security"]),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "from_email": os.getenv("SMTP_FROM_EMAIL", "").strip() or os.getenv("SMTP_USERNAME", "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "").strip() or DEFAULTS["from_name"],
    }


def _setting(conn, key: str) -> dict:
    row = conn.execute("SELECT value_json FROM system_settings WHERE key=?", (key,)).fetchone()
    if not row:
        return {}
    raw = row["value_json"] if hasattr(row, "keys") else row[0]
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def save_setting(conn, key: str, value: dict) -> None:
    conn.execute(
        "INSERT INTO system_settings(key,value_json,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
        (key, json.dumps(value), iso()),
    )


def overrides(conn) -> dict:
    return {k: v for k, v in _setting(conn, CONFIG_KEY).items() if k in EDITABLE}


# ----- App Password vault -----


def _cipher():
    secret = next((os.getenv(k, "").strip() for k in KEY_ENV if os.getenv(k, "").strip()), "")
    if not secret:
        return None
    from cryptography.fernet import Fernet

    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"cacsms-smtp-password:v1\0" + secret.encode()).digest()))


def vault_available() -> bool:
    return _cipher() is not None


def store_password(conn, password: str) -> None:
    cipher = _cipher()
    if cipher is None:
        raise SmtpConfigError("Server encryption key is not configured (set SMTP_ENCRYPTION_KEY) — use the SMTP_PASSWORD environment variable instead")
    cleaned = password.replace(" ", "").strip()
    if not cleaned:
        raise SmtpConfigError("App Password is empty")
    save_setting(conn, SECRET_KEY, {"v": 1, "token": cipher.encrypt(cleaned.encode()).decode("ascii"), "updated_at": iso()})


def clear_password(conn) -> None:
    conn.execute("DELETE FROM system_settings WHERE key=?", (SECRET_KEY,))


def _stored_password(conn) -> tuple[str, str | None]:
    token = _setting(conn, SECRET_KEY).get("token")
    if not token:
        return "", None
    cipher = _cipher()
    if cipher is None:
        return "", "Stored App Password cannot be decrypted: server encryption key is missing"
    try:
        return cipher.decrypt(token.encode("ascii")).decode(), None
    except Exception:
        return "", "Stored App Password cannot be decrypted: server encryption key changed"


def smtp_config(conn) -> SmtpConfig:
    values = {**env_defaults(), **overrides(conn)}
    stored, _ = _stored_password(conn)
    env_password = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()
    password, source = (stored, "database") if stored else (env_password, "environment") if env_password else ("", None)
    return SmtpConfig(enabled=bool(values["enabled"]), host=str(values["host"]).strip(), port=int(values["port"] or 0),
                      security=str(values["security"]).lower(), username=str(values["username"]).strip(),
                      from_email=str(values["from_email"]).strip() or str(values["username"]).strip(),
                      from_name=str(values["from_name"]).strip() or DEFAULTS["from_name"], password=password, password_source=source)


def vault_error(conn) -> str | None:
    return _stored_password(conn)[1]


# ----- redaction -----


def _secrets(conn=None) -> list[str]:
    out = [os.getenv("SMTP_PASSWORD", ""), os.getenv("SMTP_PASSWORD", "").replace(" ", "")]
    if conn is not None:
        out.append(_stored_password(conn)[0])
    return [s for s in out if s and len(s) >= 4]


def redact(text: object, conn=None, extra: tuple[str, ...] = ()) -> str:
    message = str(text)
    for secret in [*_secrets(conn), *[e for e in extra if e]]:
        message = message.replace(secret, "[REDACTED]")
        encoded = base64.b64encode(secret.encode()).decode()
        message = message.replace(encoded, "[REDACTED]")
    return message[:500]


# ----- health -----


def health(conn) -> dict:
    return _setting(conn, HEALTH_KEY)


def record_health(conn, **changes) -> dict:
    current = health(conn)
    current.update(changes)
    save_setting(conn, HEALTH_KEY, current)
    return current


# ----- sending -----


def classify(exc: BaseException) -> tuple[str, bool]:
    """(error kind, retryable). Only transient transport failures are retried."""
    if isinstance(exc, SmtpConfigError):
        return "CONFIG", False
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "AUTH", False
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "RECIPIENT", False
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "CONFIG", False
    if isinstance(exc, smtplib.SMTPConnectError):
        return "TEMPORARY", True
    if isinstance(exc, smtplib.SMTPResponseException):
        return ("TEMPORARY", True) if 400 <= exc.smtp_code < 500 else ("REJECTED", False)
    if isinstance(exc, (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, TimeoutError, ConnectionError)):
        return "TEMPORARY", True
    if isinstance(exc, ssl.SSLError):
        return "TLS", True
    if isinstance(exc, OSError):
        return "TEMPORARY", True
    return "UNKNOWN", True


def describe(kind: str, exc: BaseException, conn=None, cfg: SmtpConfig | None = None) -> str:
    detail = redact(exc, conn, (cfg.password,) if cfg else ())
    if kind == "AUTH":
        return f"SMTP authentication failed — check the SMTP username and Google App Password ({detail})"
    if kind == "CONFIG":
        return f"SMTP configuration error: {detail}"
    return f"{type(exc).__name__}: {detail}"


class SmtpSender:
    """One authenticated SMTP session (STARTTLS on 587 by default) reused for a batch of messages."""

    def __init__(self, cfg: SmtpConfig):
        self.cfg = cfg
        self.server = None

    def __enter__(self) -> "SmtpSender":
        problems = self.cfg.problems()
        if problems:
            raise SmtpConfigError("; ".join(problems))
        context = ssl.create_default_context()
        if self.cfg.security == "ssl":
            self.server = smtplib.SMTP_SSL(self.cfg.host, self.cfg.port, timeout=self.cfg.timeout, context=context)
        else:
            self.server = smtplib.SMTP(self.cfg.host, self.cfg.port, timeout=self.cfg.timeout)
        try:
            self.server.ehlo()
            if self.cfg.security == "starttls":
                self.server.starttls(context=context)
                self.server.ehlo()
            if self.cfg.username:
                self.server.login(self.cfg.username, self.cfg.password)
        except BaseException:
            self._close()
            raise
        return self

    def send(self, message: EmailMessage) -> None:
        self.server.send_message(message)

    def _close(self) -> None:
        if self.server is None:
            return
        try:
            self.server.quit()
        except Exception:
            try:
                self.server.close()
            except Exception:
                pass
        self.server = None

    def __exit__(self, *exc) -> None:
        self._close()
