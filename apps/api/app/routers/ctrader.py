"""cTrader Open API account authorization (OAuth authorization-code flow).

Credentials come only from server-side environment variables (CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET,
CTRADER_REDIRECT_URI, CTRADER_ENVIRONMENT). Neither they nor the issued tokens are ever returned or logged.
"""
from __future__ import annotations

import datetime
import hmac
import json
import logging
import os
import subprocess
import sys
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core.audit import write_audit
from ..core.database import db
from ..core.security import (
    decrypt_ctrader_token,
    encrypt_ctrader_token,
    is_encrypted_ctrader_token,
    iso,
    now,
    token_hash,
)
from ..deps import current_user
from ..services.access import require_permission
from ..services import ctrader_discovery_worker
from ..services.ctrader_application_state import (
    APP_INACTIVE, application_state, diagnostic_state, needs_application_probe,
    provider_error_code, record_application_state, status_message,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/connections/ctrader", tags=["cTrader"])

AUTHORIZE_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
STATE_TTL = datetime.timedelta(minutes=10)
REGISTERED_REDIRECT_URI = "https://cacsms-traders.vercel.app/api/connections/ctrader/callback"
APP_RETURN = "/?ctrader={result}#/system-control/mt5"
ACCOUNT_DISCOVERY_TIMEOUT = 14
LIVE_AUTH_TIMEOUT = 12
DISCOVERY_COOLDOWN = datetime.timedelta(seconds=45)
DISCOVERY_IN_FLIGHT = datetime.timedelta(seconds=20)
RETRY_LATER = {"transport_timeout", "provider_timeout", "provider_unavailable"}
PROVIDER_MESSAGES = {
    "transport_timeout": "cTrader did not open a broker connection. No trading account was authenticated.",
    "provider_timeout": "cTrader did not return the authorized account list in time. No account was marked connected.",
    "provider_unavailable": "cTrader account discovery failed before a broker session was confirmed.",
    "no_authorized_accounts": "cTrader returned no authorized trading accounts.",
    "account_auth_timeout": "The account list was received, but account authentication did not finish.",
}


class CTraderProviderError(RuntimeError):
    def __init__(self, code: str):
        self.code = provider_error_code(code)
        super().__init__(self.code)


def _configuration_error() -> str | None:
    if not os.getenv("CTRADER_CLIENT_ID", "").strip() or not os.getenv("CTRADER_CLIENT_SECRET", "").strip():
        return "missing_credentials"
    if os.getenv("CTRADER_ENVIRONMENT", "").strip().lower() != "demo":
        return "demo_environment_required"
    redirect = os.getenv("CTRADER_REDIRECT_URI", "").strip()
    parsed = urlparse(redirect)
    if redirect != REGISTERED_REDIRECT_URI or parsed.query or parsed.fragment:
        return "redirect_uri_mismatch"
    return None


def ctrader_config() -> dict | None:
    cid = os.getenv("CTRADER_CLIENT_ID", "").strip()
    secret = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
    redirect = os.getenv("CTRADER_REDIRECT_URI", "").strip()
    env = os.getenv("CTRADER_ENVIRONMENT", "").strip().lower()
    parsed_redirect = urlparse(redirect)
    if not (cid and secret and redirect) or env != "demo":
        return None
    if redirect != REGISTERED_REDIRECT_URI or parsed_redirect.query or parsed_redirect.fragment:
        return None
    return {"client_id": cid, "client_secret": secret, "redirect_uri": redirect, "environment": "demo"}


def _mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    return f"****{value[-4:]}"


def _expiry(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _encrypt_connection_tokens(c, row: dict) -> dict:
    access = row["access_token"]
    refresh = row["refresh_token"]
    if int(row.get("token_key_version") or 0) == 1 and is_encrypted_ctrader_token(access) and (
        refresh is None or is_encrypted_ctrader_token(refresh)
    ):
        return row
    encrypted_access = access if is_encrypted_ctrader_token(access) else encrypt_ctrader_token(access)
    encrypted_refresh = refresh if not refresh or is_encrypted_ctrader_token(refresh) else encrypt_ctrader_token(refresh)
    c.execute(
        "UPDATE ctrader_connections SET access_token=?,refresh_token=?,token_key_version=1 WHERE tenant_id=? AND environment='demo'",
        (encrypted_access, encrypted_refresh, row["tenant_id"]),
    )
    row["access_token"] = encrypted_access
    row["refresh_token"] = encrypted_refresh
    row["token_key_version"] = 1
    return row


def _token_request(params: dict, method: str = "GET") -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{TOKEN_URL}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        code = provider_error_code(payload.get("errorCode") or payload.get("error"), payload.get("description") or payload.get("error_description") or '')
        raise CTraderProviderError(code) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise CTraderProviderError("provider_unavailable") from None
    if not isinstance(payload, dict):
        raise CTraderProviderError("invalid_provider_response")
    if payload.get("errorCode") or payload.get('error'):
        raise CTraderProviderError(provider_error_code(payload.get("errorCode") or payload.get('error'), payload.get("description") or payload.get("error_description") or ''))
    return payload


class AuthorizeRequest(BaseModel):
    tenant_id: str


def probe_application() -> str:
    """Ask cTrader to authenticate the Open API application. Never raises and never invents ACTIVE."""
    worker = Path(ctrader_discovery_worker.__file__).resolve()
    try:
        result = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps({"environment": "demo", "action": "verify_application"}),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "UNVERIFIED"
    marker = next((line[len("CTRADER_RESULT:"):] for line in reversed(result.stdout.splitlines()) if line.startswith("CTRADER_RESULT:")), None)
    if marker is None:
        return "UNVERIFIED"
    try:
        payload = json.loads(marker)
    except ValueError:
        return "UNVERIFIED"
    error = payload.get("error")
    if error == APP_INACTIVE or provider_error_code(error or "") == APP_INACTIVE:
        return "APP_INACTIVE"
    if not result.returncode and payload.get("application_status") == "ACTIVE":
        return "ACTIVE"
    return "UNVERIFIED"


def _diagnostics(config_error: str | None, app_state: str, row, accounts: list, provider_status: str) -> list[dict]:
    items = []
    if config_error == "missing_credentials":
        items.append({"code": "credentials", "status": "ERROR", "detail": "CTRADER_CLIENT_ID or CTRADER_CLIENT_SECRET is missing."})
    elif config_error == "redirect_uri_mismatch":
        items.append({"code": "redirect_uri", "status": "ERROR", "detail": "CTRADER_REDIRECT_URI must be the registered callback without a query or fragment."})
    elif config_error == "demo_environment_required":
        items.append({"code": "environment", "status": "ERROR", "detail": "CTRADER_ENVIRONMENT must be demo."})
    elif config_error:
        items.append({"code": "configuration", "status": "ERROR", "detail": config_error.replace("_", " ")})
    else:
        items.append({"code": "credentials", "status": "OK", "detail": "Client credentials and the registered redirect URI are configured."})
    application_detail = {
        "ACTIVE": "cTrader accepted application authentication.",
        "APP_INACTIVE": "cTrader rejected application authentication.",
        "UNVERIFIED": "Application authentication has not been confirmed.",
        "UNKNOWN": "Application authentication has not been confirmed.",
        "AUTHORIZING": "An authorization attempt is in progress.",
    }.get(app_state, "Application authentication has not been confirmed.")
    items.append({"code": "application", "status": app_state, "detail": application_detail})
    if row is None:
        items.append({"code": "oauth", "status": "OAUTH_NOT_AUTHORIZED", "detail": "No authorization code has been exchanged for this tenant."})
    else:
        items.append({"code": "oauth", "status": row.get("authorization_status") or "UNKNOWN", "detail": f"Connection status {row.get('connection_status') or 'unknown'}."})
        if row.get("expires_at"):
            items.append({"code": "token", "status": "OK", "detail": "An encrypted access token is stored. Refresh runs before expiry."})
        elif row.get("authorization_status") == "AUTHORIZED":
            items.append({"code": "token", "status": "ERROR", "detail": "The stored authorization has no expiry and must be renewed."})
    items.append({"code": "accounts", "status": "OK" if accounts else "OAUTH_NOT_AUTHORIZED", "detail": f"{len(accounts)} authorized account(s) discovered." if accounts else "No trading accounts have been discovered."})
    items.append({"code": "broker", "status": provider_status, "detail": status_message(provider_status)})
    items.append({"code": "execution", "status": "DISABLED", "detail": "Trading execution stays disabled."})
    return items


@router.get("/status")
def status(tenant_id: str = Query(...), user=Depends(current_user)):
    cfg = ctrader_config()
    can_manage = False
    if cfg is not None:
        with db() as c:
            require_permission(c, user, tenant_id, "connections.read")
            should_probe = needs_application_probe(c)
        if should_probe:
            observed = probe_application()
            with db() as c:
                record_application_state(c, observed)
    with db() as c:
        require_permission(c, user, tenant_id, "connections.read")
        app_state = application_state(c)
        try:
            require_permission(c, user, tenant_id, "connections.manage")
            can_manage = True
        except HTTPException:
            can_manage = False
        row = c.execute(
            "SELECT * FROM ctrader_connections WHERE tenant_id=? AND environment='demo' LIMIT 1",
            (tenant_id,),
        ).fetchone()
        accounts = c.execute(
            "SELECT ctid_trader_account_id,trader_login,broker_name,account_type,environment,currency_code,authorization_status,last_synced_at "
            "FROM ctrader_accounts WHERE tenant_id=? ORDER BY environment,broker_name,trader_login",
            (tenant_id,),
        ).fetchall()
        if row is not None and row["access_token"]:
            try:
                row = _encrypt_connection_tokens(c, dict(row))
                decrypt_ctrader_token(row["access_token"])
                decrypt_ctrader_token(row["refresh_token"] or "")
            except ValueError:
                _record_failure(
                    row["tenant_id"], row["connected_by"], "reauthorization_required",
                    "REAUTH_REQUIRED", authorization_status="REAUTH_REQUIRED",
                )
                row["authorization_status"] = "REAUTH_REQUIRED"
                row["connection_status"] = "REAUTH_REQUIRED"
                row["last_error_code"] = "reauthorization_required"
                accounts = [dict(account, authorization_status="REAUTH_REQUIRED") for account in accounts]
        elif row is not None:
            row = dict(row)
    row = _refresh_if_needed(dict(row), cfg) if row is not None and cfg is not None and app_state != 'APP_INACTIVE' else row
    with db() as c:
        app_state = application_state(c)
    safe_accounts = [
        {
            "account": _mask_identifier(account["trader_login"] or account["ctid_trader_account_id"]),
            "broker": account["broker_name"],
            "account_type": account["account_type"],
            "environment": account["environment"] if account["environment"] in ("demo", "live") else "demo",
            "currency": account["currency_code"],
            "authorization": (
                account["authorization_status"]
                if account["authorization_status"] != "AUTHORIZED"
                else row["authorization_status"]
                if row is not None and row["authorization_status"] != "AUTHORIZED"
                else "UNVERIFIED"
                if row is not None and row["connection_status"] != "CONNECTED"
                else account["authorization_status"]
            ),
            "last_sync_at": account["last_synced_at"],
        }
        for account in accounts
    ]
    authorized = row is not None and row["authorization_status"] == "AUTHORIZED"
    connected = cfg is not None and app_state == 'ACTIVE' and authorized and row["connection_status"] == "CONNECTED" and bool(safe_accounts)
    provider_status = diagnostic_state(cfg is not None, app_state, dict(row) if row else None, connected)
    inactive = provider_status == 'APP_INACTIVE'
    if inactive:
        for account in safe_accounts:
            account['authorization'] = 'PENDING_PROVIDER_ACTIVATION'
    config_error = None if cfg else _configuration_error()
    if inactive:
        authorization_status = 'PENDING_PROVIDER_ACTIVATION'
    elif row:
        authorization_status = row["authorization_status"]
    elif provider_status == 'APPLICATION_UNVERIFIED':
        authorization_status = 'APPLICATION_UNVERIFIED'
    else:
        authorization_status = 'OAUTH_NOT_AUTHORIZED'
    return {
        "configured": cfg is not None,
        "can_manage": can_manage,
        "configuration_error": config_error,
        "provider": "cTrader",
        "environment": "demo",
        "connected": bool(connected),
        "provider_status": provider_status,
        "application_status": 'APPLICATION_ACTIVE' if app_state == 'ACTIVE' else app_state,
        "message": status_message(provider_status),
        "authorization_status": authorization_status,
        "connection_status": 'DISCONNECTED' if inactive else row["connection_status"] if row else "DISCONNECTED",
        "last_successful_connection_at": row["last_successful_connection_at"] if row else None,
        "last_sync_at": row["last_sync_at"] if row else None,
        "last_error_code": APP_INACTIVE if inactive else row["last_error_code"] if row else None,
        "accounts": safe_accounts,
        "diagnostics": _diagnostics(config_error, app_state, dict(row) if row else None, safe_accounts, provider_status),
        "discovery": _stored_discovery(row),
        "execution_available": False,
    }


@router.post("/authorize")
def authorize(x: AuthorizeRequest, user=Depends(current_user)):
    cfg = ctrader_config()
    if cfg is None:
        raise HTTPException(503, "cTrader integration is not configured on the server")
    state = secrets.token_urlsafe(32)
    with db() as c:
        require_permission(c, user, x.tenant_id, "connections.manage")
        if application_state(c) != 'APP_INACTIVE':
            record_application_state(c, 'AUTHORIZING')
        c.execute(
            "INSERT INTO ctrader_oauth_states(state_hash,tenant_id,user_id,environment,expires_at,created_at) VALUES(?,?,?,?,?,?)",
            (token_hash(state), x.tenant_id, user["id"], cfg["environment"], iso(now() + STATE_TTL), iso()),
        )
        write_audit(c, x.tenant_id, user["id"], "CTRADER_OAUTH_STARTED", "CtraderConnection", x.tenant_id, after={"environment": "demo", "scope": "accounts"})
    query = urllib.parse.urlencode(
        {"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "scope": "accounts", "product": "web", "state": state}
    )
    return {"authorize_url": f"{AUTHORIZE_URL}?{query}"}


def _back(result: str) -> RedirectResponse:
    return RedirectResponse(APP_RETURN.format(result=urllib.parse.quote(result)), status_code=303)


def _exchange(cfg: dict, code: str) -> dict:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["redirect_uri"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        }
    )


def _refresh(cfg: dict, refresh_token: str) -> dict:
    return _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        },
        method="POST",
    )


def _provider_message(code: str) -> str:
    return PROVIDER_MESSAGES.get(code, "cTrader account discovery is temporarily unavailable")


def account_was_authenticated(account: dict) -> bool:
    """Legacy discovery results without an explicit flag were already account-authenticated."""
    if "authenticated" not in account:
        return True
    return bool(account.get("authenticated"))


def discovery_connection_status(accounts: list[dict]) -> str:
    if not accounts:
        return "NO_ACCOUNTS"
    if any(account_was_authenticated(account) for account in accounts):
        return "CONNECTED"
    return "DEGRADED"


def _run_worker(payload: dict, timeout: int) -> dict:
    worker = Path(ctrader_discovery_worker.__file__).resolve()
    try:
        result = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"accounts": [], "error": "provider_timeout", "stage": "worker", "market_data": "unverified"}
    except OSError:
        return {"accounts": [], "error": "provider_unavailable", "stage": "worker", "market_data": "unverified"}
    marker = next((line[len("CTRADER_RESULT:"):] for line in reversed(result.stdout.splitlines()) if line.startswith("CTRADER_RESULT:")), None)
    if marker is None:
        return {"accounts": [], "error": "provider_unavailable", "stage": "worker", "market_data": "unverified"}
    try:
        body = json.loads(marker)
    except ValueError:
        return {"accounts": [], "error": "invalid_provider_response", "stage": "worker", "market_data": "unverified"}
    if not isinstance(body, dict):
        return {"accounts": [], "error": "invalid_provider_response", "stage": "worker", "market_data": "unverified"}
    return body


def _discover_accounts(access_token: str) -> list[dict]:
    demo = _run_worker({"environment": "demo", "access_token": access_token, "action": "discover"}, ACCOUNT_DISCOVERY_TIMEOUT)
    accounts = demo.get("accounts") if isinstance(demo.get("accounts"), list) else []
    error = str(demo.get("error") or "")
    fatal = {APP_INACTIVE, "CH_ACCESS_TOKEN_INVALID", "invalid_grant", "not_configured", "invalid_provider_response"}
    diagnostic = {key: demo.get(key) for key in ("stage", "market_data", "error", "host")}
    if error in fatal or (error and not accounts):
        _discover_accounts.last_diagnostic = diagnostic
        raise CTraderProviderError(error or "provider_unavailable")
    live_ids = [
        account["ctid_trader_account_id"]
        for account in accounts
        if account.get("environment") == "live" and not account_was_authenticated(account)
    ]
    market_data = demo.get("market_data") or "unverified"
    if live_ids:
        live = _run_worker(
            {"environment": "live", "access_token": access_token, "action": "authenticate", "account_ids": live_ids},
            LIVE_AUTH_TIMEOUT,
        )
        by_id = {
            item.get("ctid_trader_account_id"): item
            for item in (live.get("accounts") or [])
            if isinstance(item, dict)
        }
        for account in accounts:
            extra = by_id.get(account.get("ctid_trader_account_id"))
            if not extra:
                continue
            if extra.get("authenticated"):
                account["authenticated"] = True
                account.pop("auth_error", None)
            elif extra.get("auth_error"):
                account["auth_error"] = extra["auth_error"]
        if live.get("market_data") == "ok":
            market_data = "ok"
    if any(account.get("environment") not in ("demo", "live") or not account.get("ctid_trader_account_id") for account in accounts):
        raise CTraderProviderError("invalid_provider_response")
    if not accounts:
        raise CTraderProviderError("no_authorized_accounts")
    _discover_accounts.last_diagnostic = {
        "stage": "market_data" if market_data == "ok" else "account_auth",
        "market_data": market_data,
        "error": None,
        "host": demo.get("host") or "demo",
        "authenticated_accounts": sum(1 for account in accounts if account_was_authenticated(account)),
        "discovered_accounts": len(accounts),
    }
    return accounts


def _token_values(payload: dict) -> tuple[str, str, str, str]:
    access = payload.get("accessToken") or payload.get("access_token")
    refresh = payload.get("refreshToken") or payload.get("refresh_token")
    expires_in = payload.get("expiresIn") or payload.get("expires_in")
    if not access or not refresh or not expires_in:
        raise CTraderProviderError("invalid_provider_response")
    try:
        expires_at = iso(now() + datetime.timedelta(seconds=int(expires_in)))
    except (TypeError, ValueError, OverflowError):
        raise CTraderProviderError("invalid_provider_response") from None
    token_type = payload.get("tokenType") or payload.get("token_type") or "bearer"
    return str(access), str(refresh), str(token_type), expires_at


def _persist_tokens(tenant_id: str, user_id: str, payload: dict) -> None:
    access, refresh, token_type, expires_at = _token_values(payload)
    timestamp = iso()
    with db() as c:
        c.execute(
            """INSERT INTO ctrader_connections(
                 id,tenant_id,environment,access_token,refresh_token,token_type,expires_at,connected_by,created_at,updated_at,
                 authorization_status,connection_status,token_key_version,permission_scope,last_error_code)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id,environment) DO UPDATE SET
                 access_token=excluded.access_token,refresh_token=excluded.refresh_token,token_type=excluded.token_type,
                 expires_at=excluded.expires_at,connected_by=excluded.connected_by,updated_at=excluded.updated_at,
                 authorization_status='AUTHORIZED',connection_status='DISCOVERING',token_key_version=1,
                 permission_scope='accounts',last_error_code=NULL""",
            (
                str(uuid.uuid4()), tenant_id, "demo", encrypt_ctrader_token(access), encrypt_ctrader_token(refresh),
                token_type, expires_at, user_id, timestamp, timestamp, "AUTHORIZED", "DISCOVERING", 1, "accounts", None,
            ),
        )
        write_audit(c, tenant_id, user_id, "CTRADER_OAUTH_COMPLETED", "CtraderConnection", tenant_id, after={"environment": "demo", "scope": "accounts"})


def _discovery_diagnostic() -> dict:
    diagnostic = getattr(_discover_accounts, "last_diagnostic", None)
    return diagnostic if isinstance(diagnostic, dict) else {}


def _persist_accounts(tenant_id: str, user_id: str, accounts: list[dict]) -> None:
    timestamp = iso()
    connection_status = discovery_connection_status(accounts)
    diagnostic = json.dumps({**_discovery_diagnostic(), "connection_status": connection_status})
    with db() as c:
        record_application_state(c, 'ACTIVE')
        c.execute(
            "UPDATE ctrader_accounts SET authorization_status='NOT_AUTHORIZED',updated_at=? WHERE tenant_id=?",
            (timestamp, tenant_id),
        )
        for account in accounts:
            c.execute(
                """INSERT INTO ctrader_accounts(
                     tenant_id,ctid_trader_account_id,trader_login,broker_name,account_type,environment,currency_code,
                     authorization_status,last_synced_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(tenant_id,ctid_trader_account_id) DO UPDATE SET
                     trader_login=excluded.trader_login,broker_name=excluded.broker_name,account_type=excluded.account_type,
                     environment=excluded.environment,currency_code=excluded.currency_code,authorization_status=excluded.authorization_status,
                     last_synced_at=excluded.last_synced_at,updated_at=excluded.updated_at""",
                (
                    tenant_id, str(account["ctid_trader_account_id"]), account.get("trader_login"), account.get("broker_name"),
                    account.get("account_type"), account.get("environment") or "demo", account.get("currency_code"),
                    "AUTHORIZED" if account_was_authenticated(account) else "DISCOVERED", timestamp, timestamp, timestamp,
                ),
            )
            write_audit(
                c,
                tenant_id,
                user_id,
                "CTRADER_ACCOUNT_DISCOVERED",
                "CtraderAccount",
                tenant_id,
                after={"environment": account.get("environment") or "demo", "broker": account.get("broker_name"), "account_type": account.get("account_type")},
            )
        success_at = timestamp if connection_status == "CONNECTED" else None
        c.execute(
            """UPDATE ctrader_connections SET authorization_status='AUTHORIZED',connection_status=?,
                 permission_scope='accounts',last_successful_connection_at=COALESCE(?,last_successful_connection_at),
                 last_sync_at=?,last_error_code=NULL,last_diagnostic_json=?,last_attempt_at=?,updated_at=?
               WHERE tenant_id=? AND environment='demo'""",
            (connection_status, success_at, timestamp, diagnostic, timestamp, timestamp, tenant_id),
        )


def _record_failure(
    tenant_id: str,
    user_id: str,
    code: str,
    connection_status: str = "DISCOVERY_FAILED",
    authorization_status: str | None = None,
) -> None:
    code = provider_error_code(code)
    if code == APP_INACTIVE:
        connection_status = 'DISCONNECTED'
        authorization_status = 'PENDING_PROVIDER_ACTIVATION'
    timestamp = iso()
    with db() as c:
        if code == APP_INACTIVE:
            record_application_state(c, 'APP_INACTIVE')
        elif application_state(c) == 'AUTHORIZING':
            record_application_state(c, 'UNKNOWN')
        diagnostic = json.dumps({**_discovery_diagnostic(), "error": code[:80], "connection_status": connection_status})
        c.execute(
            """UPDATE ctrader_connections SET connection_status=?,authorization_status=COALESCE(?,authorization_status),
                 last_error_code=?,last_diagnostic_json=?,last_attempt_at=?,updated_at=? WHERE tenant_id=? AND environment='demo'""",
            (connection_status, authorization_status, code[:80], diagnostic, timestamp, timestamp, tenant_id),
        )
        if authorization_status == "REAUTH_REQUIRED":
            c.execute(
                "UPDATE ctrader_accounts SET authorization_status='REAUTH_REQUIRED',updated_at=? WHERE tenant_id=? AND environment='demo'",
                (timestamp, tenant_id),
            )
        write_audit(c, tenant_id, user_id, "CTRADER_CONNECTION_FAILED", "CtraderConnection", tenant_id, after={"environment": "demo", "error_code": code[:80]})


def _refresh_if_needed(row: dict, cfg: dict) -> dict:
    with db() as c:
        if application_state(c) == 'APP_INACTIVE':
            return {**row, 'authorization_status': 'PENDING_PROVIDER_ACTIVATION',
                    'connection_status': 'DISCONNECTED', 'last_error_code': APP_INACTIVE}
    if row.get("authorization_status") != "AUTHORIZED" or not row.get("access_token"):
        return row
    expires_at = _expiry(row.get("expires_at"))
    if expires_at is None or expires_at > now() + datetime.timedelta(minutes=2):
        return row
    try:
        refresh_token = decrypt_ctrader_token(row["refresh_token"] or "")
        if not refresh_token:
            raise CTraderProviderError("reauthorization_required")
        payload = _refresh(cfg, refresh_token)
        access, refresh, token_type, new_expires = _token_values(payload)
    except (CTraderProviderError, ValueError) as exc:
        code = exc.code if isinstance(exc, CTraderProviderError) else "reauthorization_required"
        if code == APP_INACTIVE:
            _record_failure(row['tenant_id'], row['connected_by'], code)
            return {**row, 'authorization_status': 'PENDING_PROVIDER_ACTIVATION',
                    'connection_status': 'DISCONNECTED', 'last_error_code': APP_INACTIVE}
        status = "REAUTH_REQUIRED" if code in ("invalid_grant", "reauthorization_required", "CH_ACCESS_TOKEN_INVALID") else "PROVIDER_UNAVAILABLE"
        _record_failure(
            row["tenant_id"], row["connected_by"], code, status,
            authorization_status="REAUTH_REQUIRED" if status == "REAUTH_REQUIRED" else None,
        )
        row["authorization_status"] = "REAUTH_REQUIRED" if status == "REAUTH_REQUIRED" else row["authorization_status"]
        row["connection_status"] = status
        row["last_error_code"] = code[:80]
        return row
    timestamp = iso()
    with db() as c:
        c.execute(
            """UPDATE ctrader_connections SET access_token=?,refresh_token=?,token_type=?,expires_at=?,token_key_version=1,
                 authorization_status='AUTHORIZED',last_error_code=NULL,updated_at=? WHERE tenant_id=? AND environment='demo'""",
            (encrypt_ctrader_token(access), encrypt_ctrader_token(refresh), token_type, new_expires, timestamp, row["tenant_id"]),
        )
        write_audit(c, row["tenant_id"], row["connected_by"], "CTRADER_TOKEN_REFRESHED", "CtraderConnection", row["tenant_id"], after={"environment": "demo"})
    row.update({"access_token": encrypt_ctrader_token(access), "refresh_token": encrypt_ctrader_token(refresh), "expires_at": new_expires, "authorization_status": "AUTHORIZED", "last_error_code": None})
    return row


def _consume_state(state: str) -> dict | None:
    with db() as c:
        row = c.execute("SELECT * FROM ctrader_oauth_states WHERE state_hash=?", (token_hash(state),)).fetchone()
        if row is None or row["used_at"] or (_expiry(row["expires_at"]) or now()) <= now():
            return None
        owner = c.execute("SELECT * FROM users WHERE id=? AND status='ACTIVE'", (row["user_id"],)).fetchone()
        if owner is None:
            return None
        try:
            require_permission(c, dict(owner), row["tenant_id"], "connections.manage")
        except HTTPException:
            return None
        updated = c.execute(
            "UPDATE ctrader_oauth_states SET used_at=? WHERE state_hash=? AND used_at IS NULL",
            (iso(), row["state_hash"]),
        )
        if updated.rowcount != 1:
            return None
        return dict(row)


@router.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None, error_description: str | None = None):
    """OAuth redirect target. Authenticated by the one-time state, not by session (it is a top-level redirect)."""
    if not state:
        return _back("invalid_request")
    cfg = ctrader_config()
    if cfg is None:
        return _back("not_configured")
    st = _consume_state(state)
    if st is None:
        return _back("invalid_state")
    if error:
        if provider_error_code(error, error_description or '') == APP_INACTIVE:
            _record_failure(st['tenant_id'], st['user_id'], APP_INACTIVE)
            return _back('app_inactive')
        _record_failure(st["tenant_id"], st["user_id"], "provider_denied", "REAUTH_REQUIRED")
        return _back("denied")
    if not code:
        _record_failure(st["tenant_id"], st["user_id"], "missing_authorization_code")
        return _back("invalid_request")
    try:
        tok = _exchange(cfg, code)
        _persist_tokens(st["tenant_id"], st["user_id"], tok)
    except CTraderProviderError as exc:
        log.warning("cTrader token exchange failed; error_code=%s", exc.code)
        try:
            _record_failure(st["tenant_id"], st["user_id"], exc.code, "REAUTH_REQUIRED", authorization_status="REAUTH_REQUIRED")
        except Exception as audit_exc:
            log.warning("cTrader token exchange failure state could not be recorded; error_type=%s", type(audit_exc).__name__)
        return _back('app_inactive' if exc.code == APP_INACTIVE else "exchange_failed")
    except Exception as exc:
        log.warning("cTrader token persistence failed; error_type=%s", type(exc).__name__)
        try:
            _record_failure(st["tenant_id"], st["user_id"], "token_persistence_failed", "PERSISTENCE_FAILED")
        except Exception as audit_exc:
            log.warning("cTrader persistence failure state could not be recorded; error_type=%s", type(audit_exc).__name__)
        return _back("persistence_failed")
    try:
        accounts = _discover_accounts(tok.get("accessToken") or tok.get("access_token"))
        _persist_accounts(st["tenant_id"], st["user_id"], accounts)
    except CTraderProviderError as exc:
        log.warning("cTrader account discovery failed; error_code=%s", exc.code)
        try:
            _record_failure(st["tenant_id"], st["user_id"], exc.code)
        except Exception as audit_exc:
            log.warning("cTrader discovery failure state could not be recorded; error_type=%s", type(audit_exc).__name__)
        return _back('app_inactive' if exc.code == APP_INACTIVE else "discovery_failed")
    except Exception as exc:
        log.warning("cTrader account persistence failed; error_type=%s", type(exc).__name__)
        try:
            _record_failure(st["tenant_id"], st["user_id"], "account_persistence_failed", "PERSISTENCE_FAILED")
        except Exception as audit_exc:
            log.warning("cTrader account persistence failure state could not be recorded; error_type=%s", type(audit_exc).__name__)
        return _back("discovery_failed")
    return _back("connected")


def _stored_discovery(row) -> dict:
    if row is None:
        return {}
    raw = dict(row).get("last_diagnostic_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {key: parsed.get(key) for key in ("stage", "market_data", "error", "host", "connection_status", "authenticated_accounts", "discovered_accounts")}


def _sync_block(row: dict) -> HTTPException | None:
    attempted = _expiry(row.get("last_attempt_at"))
    if row.get("connection_status") == "DISCOVERING" and attempted and now() - attempted < DISCOVERY_IN_FLIGHT:
        return HTTPException(409, "Account discovery is already running")
    if row.get("last_error_code") in RETRY_LATER and attempted and now() - attempted < DISCOVERY_COOLDOWN:
        remaining = int((DISCOVERY_COOLDOWN - (now() - attempted)).total_seconds())
        return HTTPException(503, _provider_message(row["last_error_code"]), headers={"Retry-After": str(max(remaining, 1))})
    return None


def _begin_discovery(tenant_id: str) -> None:
    timestamp = iso()
    with db() as c:
        c.execute(
            """UPDATE ctrader_connections SET connection_status='DISCOVERING',last_attempt_at=?,updated_at=?
               WHERE tenant_id=? AND environment='demo'""",
            (timestamp, timestamp, tenant_id),
        )


def _sync_authorized_connection(tenant_id: str, user_id: str, row: dict, cfg: dict) -> dict:
    blocked = _sync_block(row)
    if blocked:
        raise blocked
    _begin_discovery(tenant_id)
    row = _refresh_if_needed(row, cfg)
    if row["authorization_status"] != "AUTHORIZED":
        raise HTTPException(409, "cTrader authorization must be renewed")
    try:
        access = decrypt_ctrader_token(row["access_token"])
        accounts = _discover_accounts(access)
        _persist_accounts(tenant_id, user_id, accounts)
    except ValueError:
        _record_failure(tenant_id, user_id, "reauthorization_required", "REAUTH_REQUIRED", authorization_status="REAUTH_REQUIRED")
        raise HTTPException(409, "cTrader authorization must be renewed") from None
    except CTraderProviderError as exc:
        if exc.code == "no_authorized_accounts":
            _record_failure(tenant_id, user_id, exc.code, "NO_ACCOUNTS")
            return {"status": "NO_ACCOUNTS", "accounts_discovered": 0, "connected": False}
        status = "DISCOVERY_FAILED"
        _record_failure(tenant_id, user_id, exc.code, status)
        retry = exc.code in RETRY_LATER
        headers = {"Retry-After": str(int(DISCOVERY_COOLDOWN.total_seconds()))} if retry else None
        raise HTTPException(503, _provider_message(exc.code), headers=headers) from None
    except Exception as exc:
        log.warning("cTrader account sync failed; error_type=%s", type(exc).__name__)
        try:
            _record_failure(tenant_id, user_id, "account_persistence_failed", "PERSISTENCE_FAILED")
        except Exception:
            log.warning("cTrader sync failure state could not be recorded; error_type=%s", type(exc).__name__)
        raise HTTPException(503, "cTrader account discovery could not be saved") from None
    return {
        "status": discovery_connection_status(accounts),
        "accounts_discovered": len(accounts),
        "connected": discovery_connection_status(accounts) == "CONNECTED",
        "market_data": _discovery_diagnostic().get("market_data") or "unverified",
    }


@router.post("/accounts/sync")
def sync_accounts(x: AuthorizeRequest, user=Depends(current_user)):
    cfg = ctrader_config()
    if cfg is None:
        raise HTTPException(503, "cTrader integration is not configured for demo authorization")
    with db() as c:
        require_permission(c, user, x.tenant_id, "connections.manage")
        row = c.execute("SELECT * FROM ctrader_connections WHERE tenant_id=? AND environment='demo'", (x.tenant_id,)).fetchone()
        if row is None or row["authorization_status"] != "AUTHORIZED":
            raise HTTPException(409, "Authorize cTrader before synchronizing accounts")
        row = _encrypt_connection_tokens(c, dict(row))
    return _sync_authorized_connection(x.tenant_id, user["id"], row, cfg)


@router.post("/disconnect")
def disconnect(x: AuthorizeRequest, user=Depends(current_user)):
    with db() as c:
        require_permission(c, user, x.tenant_id, "connections.manage")
        timestamp = iso()
        c.execute(
            "UPDATE ctrader_accounts SET authorization_status='REVOKED',updated_at=? WHERE tenant_id=? AND environment='demo'",
            (timestamp, x.tenant_id),
        )
        c.execute(
            """UPDATE ctrader_connections SET access_token='',refresh_token=NULL,token_type=NULL,expires_at=NULL,
                 authorization_status='REVOKED',connection_status='DISCONNECTED',token_key_version=0,last_error_code=NULL,updated_at=?
               WHERE tenant_id=? AND environment='demo'""",
            (timestamp, x.tenant_id),
        )
        write_audit(c, x.tenant_id, user["id"], "CTRADER_DISCONNECTED", "CtraderConnection", x.tenant_id, after={"environment": "demo"})
    return {"status": "DISCONNECTED"}


@router.get("/jobs/recover")
def recover_connections(authorization: str | None = Header(default=None)):
    """Hourly recovery for authorized connections that are not connected. Does not require a browser session."""
    secret = os.getenv("CRON_SECRET", "").strip()
    if secret and not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "Invalid cron credentials")
    cfg = ctrader_config()
    if cfg is None:
        return {"attempted": 0, "reason": "not_configured"}
    with db() as c:
        rows = c.execute(
            """SELECT * FROM ctrader_connections WHERE environment='demo' AND authorization_status='AUTHORIZED'
               AND connection_status!='CONNECTED' ORDER BY updated_at LIMIT 1"""
        ).fetchall()
    attempted = 0
    for raw in rows:
        row = dict(raw)
        if _sync_block(row):
            return {"attempted": 0, "reason": "cooldown"}
        attempted += 1
        try:
            _sync_authorized_connection(row["tenant_id"], row.get("connected_by") or row["tenant_id"], row, cfg)
        except HTTPException as exc:
            log.warning("cTrader recovery did not connect; status=%s", exc.status_code)
    return {"attempted": attempted}
