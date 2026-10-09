"""Repository-backed FX basket readiness (authoritative for N/28 display)."""
from __future__ import annotations

from datetime import datetime, timezone

from .constants import FX_PAIRS_28
from .csm_service import CurrencyStrengthMatrixService
from .repository import MarketRepository


def repository_basket_status(
    conn,
    *,
    provider: str | None = None,
    snapshot_id: str | None = None,
    account_id: str | None = None,
) -> dict:
    repo = MarketRepository(conn, provider=provider, snapshot_id=snapshot_id)
    if account_id:
        repo.account_id = account_id
    svc = CurrencyStrengthMatrixService(repo)
    try:
        as_of = datetime.now(timezone.utc)
        pair_data = svc.build_pair_closes_by_tf(as_of)
        missing = svc.missing_pairs(pair_data)
        loaded = len(FX_PAIRS_28) - len(missing)
    except Exception as exc:
        return {
            "pairs_loaded": 0,
            "pairs_total": len(FX_PAIRS_28),
            "missing_pairs": list(FX_PAIRS_28),
            "repository_ready": False,
            "repository_error": str(exc),
        }
    return {
        "pairs_loaded": loaded,
        "pairs_total": len(FX_PAIRS_28),
        "missing_pairs": missing,
        "repository_ready": loaded > 0,
        "repository_error": None,
    }
