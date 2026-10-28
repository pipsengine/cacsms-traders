"""Cacsms Engine API — read campaigns and retry execution after retriable errors."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..autonomous.store import AERepository
from ..autonomous.engine import _mode
from ..cacsms_engine.advance import advance_authorised_outlooks
from ..cacsms_engine.load import assemble, detail_for
from ..cacsms_engine.retry import reset_execution_retries
from ..core.database import db
from ..deps import current_user
from ..market.outlook.store import OutlookRepository
from ..market.strength_intel_store import active_scope
from ..services.access import require_permission

router = APIRouter(prefix="/api/cacsms-engine", tags=["Cacsms Engine"])
log = logging.getLogger("cacsms.engine_ui")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scope(conn, user) -> tuple[str, str]:
    scope = active_scope(conn)
    if not scope[0]:
        raise HTTPException(503, "No market-data tenant configured")
    if not user["is_platform_admin"]:
        require_permission(conn, user, scope[0], "system.read")
    return scope


def _opportunities(repo: AERepository) -> list[dict]:
    try:
        return repo.active_opportunities()
    except Exception:
        log.warning("Autonomous opportunities could not be read", exc_info=True)
        return []


@router.get("/overview")
def overview(user=Depends(current_user), tenant_id: str | None = Query(default=None)):
    """Tenant id on the query string is ignored. Scope comes from the authenticated session."""
    del tenant_id
    with db() as conn:
        scope = _scope(conn, user)
        store = OutlookRepository(conn, scope)
        try:
            return assemble(conn, store, _opportunities(AERepository(conn, scope)), _now())
        except HTTPException:
            raise
        except Exception:
            log.exception("Cacsms Engine overview failed")
            raise HTTPException(503, "Cacsms Engine could not read persisted outlook records") from None


@router.post("/retry-execution")
def retry_execution(user=Depends(current_user), tenant_id: str | None = Query(default=None)):
    """Clear retriable broker/sizing errors (e.g. MINIMUM_EXCEEDS_BUDGET) and run one outlook advance pass."""
    del tenant_id
    with db() as conn:
        scope = _scope(conn, user)
        if not user["is_platform_admin"]:
            require_permission(conn, user, scope[0], "system.manage")
        cleared = reset_execution_retries(conn, scope[0], scope[1])
        mode = _mode(conn)
        advanced = advance_authorised_outlooks(conn, scope[0], scope[1], mode, _now(), wait=False)
        conn.commit()
        return {"cleared": cleared, "advance": advanced}


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, user=Depends(current_user), tenant_id: str | None = Query(default=None)):
    del tenant_id
    with db() as conn:
        scope = _scope(conn, user)
        store = OutlookRepository(conn, scope)
        try:
            row = detail_for(conn, store, _opportunities(AERepository(conn, scope)), campaign_id, _now())
        except HTTPException:
            raise
        except Exception:
            log.exception("Cacsms Engine campaign detail failed")
            raise HTTPException(503, "Cacsms Engine could not read persisted outlook records") from None
    if row is None:
        raise HTTPException(404, "Campaign not found")
    return row
