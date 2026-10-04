"""cTrader Open API account authorization (OAuth authorization-code flow).

Credentials come only from server-side environment variables (CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET,
CTRADER_REDIRECT_URI, CTRADER_ENVIRONMENT). Neither they nor the issued tokens are ever returned or logged.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..core.audit import write_audit
from ..core.database import db
from ..core.security import iso, now, token_hash
from ..deps import current_user
from ..services.access import require_permission

log = logging.getLogger(__name__)
router = APIRouter(prefix="/connections/ctrader", tags=["cTrader"])

AUTHORIZE_URL = "https://id.ctrader.com/my/settings/openapi/grantingaccess/"
TOKEN_URL = "https://openapi.ctrader.com/apps/token"
STATE_TTL = datetime.timedelta(minutes=10)
ENVIRONMENTS = ("demo", "live")
APP_RETURN = "/?ctrader={result}#/system-control/mt5"


def ctrader_config() -> dict | None:
    cid = os.getenv("CTRADER_CLIENT_ID", "").strip()
    secret = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
    redirect = os.getenv("CTRADER_REDIRECT_URI", "").strip()
    env = os.getenv("CTRADER_ENVIRONMENT", "demo").strip().lower()
    if not (cid and secret and redirect):
        return None
    return {"client_id": cid, "client_secret": secret, "redirect_uri": redirect, "environment": env if env in ENVIRONMENTS else "demo"}


class AuthorizeRequest(BaseModel):
    tenant_id: str


@router.get("/status")
def status(tenant_id: str = Query(...), user=Depends(current_user)):
    cfg = ctrader_config()
    with db() as c:
        require_permission(c, user, tenant_id, "connections.read")
        row = c.execute(
            "SELECT environment, expires_at, updated_at FROM ctrader_connections WHERE tenant_id=? ORDER BY updated_at DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
    return {
        "configured": cfg is not None,
        "environment": cfg["environment"] if cfg else None,
        "connected": row is not None,
        "connection": None if row is None else {"environment": row["environment"], "expires_at": row["expires_at"], "connected_at": row["updated_at"]},
    }


@router.post("/authorize")
def authorize(x: AuthorizeRequest, user=Depends(current_user)):
    cfg = ctrader_config()
    if cfg is None:
        raise HTTPException(503, "cTrader integration is not configured on the server")
    state = secrets.token_urlsafe(32)
    with db() as c:
        require_permission(c, user, x.tenant_id, "connections.manage")
        c.execute(
            "INSERT INTO ctrader_oauth_states(state_hash,tenant_id,user_id,environment,expires_at,created_at) VALUES(?,?,?,?,?,?)",
            (token_hash(state), x.tenant_id, user["id"], cfg["environment"], iso(now() + STATE_TTL), iso()),
        )
    query = urllib.parse.urlencode(
        {"client_id": cfg["client_id"], "redirect_uri": cfg["redirect_uri"], "scope": "trading", "product": "web", "state": state}
    )
    return {"authorize_url": f"{AUTHORIZE_URL}?{query}"}


def _back(result: str) -> RedirectResponse:
    return RedirectResponse(APP_RETURN.format(result=urllib.parse.quote(result)), status_code=303)


def _exchange(cfg: dict, code: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg["redirect_uri"],
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        }
    )
    req = urllib.request.Request(f"{TOKEN_URL}?{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


@router.get("/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """OAuth redirect target. Authenticated by the one-time state, not by session (it is a top-level redirect)."""
    if error:
        return _back("denied")
    if not code or not state:
        return _back("invalid_request")
    cfg = ctrader_config()
    if cfg is None:
        return _back("not_configured")
    with db() as c:
        st = c.execute("SELECT * FROM ctrader_oauth_states WHERE state_hash=?", (token_hash(state),)).fetchone()
        if st is None or st["used_at"] or st["expires_at"] < iso():
            return _back("invalid_state")
        c.execute("UPDATE ctrader_oauth_states SET used_at=? WHERE state_hash=?", (iso(), st["state_hash"]))
    try:
        tok = _exchange(cfg, code)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        log.warning("cTrader token exchange failed: %s", type(exc).__name__)
        return _back("exchange_failed")
    access = tok.get("accessToken") or tok.get("access_token")
    if tok.get("errorCode") or not access:
        log.warning("cTrader token exchange rejected: %s", tok.get("errorCode") or "no access token")
        return _back("exchange_failed")
    expires_in = tok.get("expiresIn") or tok.get("expires_in")
    expires_at = iso(now() + datetime.timedelta(seconds=int(expires_in))) if expires_in else None
    ts = iso()
    with db() as c:
        c.execute(
            """INSERT INTO ctrader_connections(id,tenant_id,environment,access_token,refresh_token,token_type,expires_at,connected_by,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(tenant_id,environment) DO UPDATE SET access_token=excluded.access_token,refresh_token=excluded.refresh_token,
                 token_type=excluded.token_type,expires_at=excluded.expires_at,connected_by=excluded.connected_by,updated_at=excluded.updated_at""",
            (
                str(uuid.uuid4()),
                st["tenant_id"],
                st["environment"],
                access,
                tok.get("refreshToken") or tok.get("refresh_token"),
                tok.get("tokenType") or tok.get("token_type"),
                expires_at,
                st["user_id"],
                ts,
                ts,
            ),
        )
        write_audit(c, st["tenant_id"], st["user_id"], "CTRADER_CONNECTED", "CtraderConnection", st["tenant_id"], after={"environment": st["environment"]})
    return _back("connected")
