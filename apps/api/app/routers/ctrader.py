"""cTrader Open API account authorization (OAuth authorization-code flow).

Credentials come only from server-side environment variables (CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET,
CTRADER_REDIRECT_URI, CTRADER_ENVIRONMENT). Neither they nor the issued tokens are ever returned or logged.
"""
from __future__ import annotations

import datetime
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

from fastapi import APIRouter, Depends, HTTPException, Query
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
    APP_INACTIVE, INACTIVE_MESSAGE, application_state, diagnostic_state,
    provider_error_code, record_application_state,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/connections/ctrader", tags=["cTrader"])

AUTHORIZE_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
STATE_TTL = datetime.timedelta(minutes=10)
REGISTERED_REDIRECT_URI = "https://cacsms-traders.vercel.app/api/connections/ctrader/callback"
APP_RETURN = "/?ctrader={result}#/system-control/mt5"
ACCOUNT_DISCOVERY_TIMEOUT = 22


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


@router.get("/status")
def status(tenant_id: str = Query(...), user=Depends(current_user)):
    cfg = ctrader_config()
    can_manage = False
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
            "FROM ctrader_accounts WHERE tenant_id=? AND environment='demo' ORDER BY broker_name,trader_login",
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
            "environment": "demo",
            "currency": account["currency_code"],
            "authorization": (
                row["authorization_status"]
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
    connected = cfg is not None and app_state not in ('APP_INACTIVE', 'AUTHORIZING') and authorized and row["connection_status"] == "CONNECTED" and bool(safe_accounts)
    provider_status = diagnostic_state(cfg is not None, app_state, dict(row) if row else None, connected)
    inactive = provider_status == 'APP_INACTIVE'
    if inactive:
        for account in safe_accounts:
            account['authorization'] = 'PENDING_PROVIDER_ACTIVATION'
    return {
        "configured": cfg is not None,
        "can_manage": can_manage,
        "configuration_error": None if cfg else _configuration_error(),
        "provider": "cTrader",
        "environment": "demo",
        "connected": bool(connected),
        "provider_status": provider_status,
        "application_status": app_state,
        "message": INACTIVE_MESSAGE if inactive else None,
        "authorization_status": 'PENDING_PROVIDER_ACTIVATION' if inactive else row["authorization_status"] if row else "NOT_AUTHORIZED",
        "connection_status": 'DISCONNECTED' if inactive else row["connection_status"] if row else "DISCONNECTED",
        "last_successful_connection_at": row["last_successful_connection_at"] if row else None,
        "last_sync_at": row["last_sync_at"] if row else None,
        "last_error_code": APP_INACTIVE if inactive else row["last_error_code"] if row else None,
        "accounts": safe_accounts,
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


def _discover_accounts(access_token: str) -> list[dict]:
    worker = Path(ctrader_discovery_worker.__file__).resolve()
    try:
        result = subprocess.run(
            [sys.executable, str(worker)],
            input=json.dumps({"environment": "demo", "access_token": access_token}),
            capture_output=True,
            text=True,
            timeout=ACCOUNT_DISCOVERY_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise CTraderProviderError("provider_timeout") from None
    except OSError:
        raise CTraderProviderError("provider_unavailable") from None
    marker = next((line[len("CTRADER_RESULT:"):] for line in reversed(result.stdout.splitlines()) if line.startswith("CTRADER_RESULT:")), None)
    if marker is None:
        raise CTraderProviderError("provider_unavailable")
    try:
        payload = json.loads(marker)
    except ValueError:
        raise CTraderProviderError("invalid_provider_response") from None
    if result.returncode or payload.get("error"):
        raise CTraderProviderError(str(payload.get("error") or "provider_unavailable"))
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise CTraderProviderError("no_demo_accounts")
    if any(account.get("environment") != "demo" or not account.get("ctid_trader_account_id") for account in accounts):
        raise CTraderProviderError("invalid_provider_response")
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


def _persist_accounts(tenant_id: str, user_id: str, accounts: list[dict]) -> None:
    timestamp = iso()
    with db() as c:
        record_application_state(c, 'ACTIVE')
        c.execute(
            "UPDATE ctrader_accounts SET authorization_status='NOT_AUTHORIZED',updated_at=? WHERE tenant_id=? AND environment='demo'",
            (timestamp, tenant_id),
        )
        for account in accounts:
            c.execute(
                """INSERT INTO ctrader_accounts(
                     tenant_id,ctid_trader_account_id,trader_login,broker_name,account_type,environment,currency_code,
                     authorization_status,last_synced_at,created_at,updated_at)
                   VALUES(?,?,?,?,?, 'demo',?,'AUTHORIZED',?,?,?)
                   ON CONFLICT(tenant_id,ctid_trader_account_id) DO UPDATE SET
                     trader_login=excluded.trader_login,broker_name=excluded.broker_name,account_type=excluded.account_type,
                     environment='demo',currency_code=excluded.currency_code,authorization_status='AUTHORIZED',
                     last_synced_at=excluded.last_synced_at,updated_at=excluded.updated_at""",
                (
                    tenant_id, str(account["ctid_trader_account_id"]), account.get("trader_login"), account.get("broker_name"),
                    account.get("account_type"), account.get("currency_code"), timestamp, timestamp, timestamp,
                ),
            )
            write_audit(
                c,
                tenant_id,
                user_id,
                "CTRADER_ACCOUNT_DISCOVERED",
                "CtraderAccount",
                tenant_id,
                after={"environment": "demo", "broker": account.get("broker_name"), "account_type": account.get("account_type")},
            )
        c.execute(
            """UPDATE ctrader_connections SET authorization_status='AUTHORIZED',connection_status='CONNECTED',
                 permission_scope='accounts',last_successful_connection_at=?,last_sync_at=?,last_error_code=NULL,updated_at=?
               WHERE tenant_id=? AND environment='demo'""",
            (timestamp, timestamp, timestamp, tenant_id),
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
        c.execute(
            """UPDATE ctrader_connections SET connection_status=?,authorization_status=COALESCE(?,authorization_status),
                 last_error_code=?,updated_at=? WHERE tenant_id=? AND environment='demo'""",
            (connection_status, authorization_status, code[:80], timestamp, tenant_id),
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
        with db() as c:
            inactive = exc.code == APP_INACTIVE or application_state(c) == 'APP_INACTIVE'
        return _back('app_inactive' if inactive else "discovery_failed")
    except Exception as exc:
        log.warning("cTrader account persistence failed; error_type=%s", type(exc).__name__)
        try:
            _record_failure(st["tenant_id"], st["user_id"], "account_persistence_failed", "PERSISTENCE_FAILED")
        except Exception as audit_exc:
            log.warning("cTrader account persistence failure state could not be recorded; error_type=%s", type(audit_exc).__name__)
        return _back("discovery_failed")
    return _back("connected")


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
    row = _refresh_if_needed(row, cfg)
    if row["authorization_status"] != "AUTHORIZED":
        raise HTTPException(503, "cTrader authorization must be renewed")
    try:
        access = decrypt_ctrader_token(row["access_token"])
        accounts = _discover_accounts(access)
        _persist_accounts(x.tenant_id, user["id"], accounts)
    except ValueError:
        _record_failure(
            x.tenant_id, user["id"], "reauthorization_required", "REAUTH_REQUIRED",
            authorization_status="REAUTH_REQUIRED",
        )
        raise HTTPException(409, "cTrader authorization must be renewed") from None
    except CTraderProviderError as exc:
        _record_failure(x.tenant_id, user["id"], exc.code)
        raise HTTPException(503, "cTrader account discovery is temporarily unavailable") from None
    return {"status": "CONNECTED", "accounts_discovered": len(accounts)}


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
