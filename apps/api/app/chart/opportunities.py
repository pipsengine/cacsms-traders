"""Manual chart opportunities — drafts only; engine stages must confirm before execution."""
from __future__ import annotations

import json
import uuid

from ..core.security import iso

_STRATEGY = {
    "Trend-in-Trend": "TIT",
    "Channel Continuation": "CONTINUATION",
    "Breakout–Retest": "P2_BREAKOUT_RETEST",
    "Breakout-Retest": "P2_BREAKOUT_RETEST",
}


def create_draft(
    conn,
    *,
    tenant_id: str,
    user_id: str,
    account_id: str,
    symbol: str,
    timeframe: str,
    direction: str,
    strategy: str,
    notes: str,
    analysis_id: str | None,
) -> dict:
    draft_id = str(uuid.uuid4())
    ae_id = str(uuid.uuid4())
    now = iso()
    opp_type = _STRATEGY.get(strategy, "MANUAL_CHART")
    family = f"chart-{draft_id}"
    evidence = {
        "source": "advanced_chart_analysis",
        "chart_analysis_id": analysis_id,
        "timeframe": timeframe,
        "notes": notes,
        "draft_only": True,
    }
    conn.execute(
        "INSERT INTO chart_opportunity_drafts(id, tenant_id, user_id, account_id, symbol, timeframe, direction, strategy, notes, analysis_id, created_at, status, ae_opportunity_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (draft_id, tenant_id, user_id, account_id, symbol, timeframe, direction, strategy, notes, analysis_id, now, "DRAFT_REQUIRES_REVIEW", ae_id),
    )
    ae_row = (
        ae_id,
        tenant_id,
        account_id,
        family,
        symbol.upper(),
        direction,
        opp_type,
        None,
        timeframe,
        timeframe,
        "OPPORTUNITY",
        "DRAFT_REQUIRES_REVIEW",
        "INACTIVE",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "Chart manual draft — requires Stage 2 confirmation",
        "CHART_DRAFT",
        None,
        None,
        json.dumps(evidence),
        json.dumps(["Awaiting qualification review"]),
        now,
        now,
        now,
        now,
        now,
        None,
    )
    conn.execute(
        "INSERT INTO ae_opportunity(id, tenant_id, trading_account_id, family_key, symbol, direction, opp_type, tit_level, parent_tf, trigger_tf, "
        "stage, state, status, outcome, entry_lo, entry_hi, invalidation, target_1, target_2, current_price, price_at, confidence, quality, "
        "reward_risk, next_condition, reason_code, provider, snapshot_id, evidence_json, blockers_json, origin_at, stage_entered_at, evaluated_through, created_at, updated_at, closed_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ae_row,
    )
    conn.execute(
        "INSERT INTO ce_opportunity(id, tenant_id, trading_account_id, symbol, source_mode, strategy_type, outlook_horizon, analysis_id, scenario_id, "
        "direction, evidence_score, entry_zone, stop_loss, targets_json, invalidation, confirmation_requirements, lifecycle_status, stage, conflict, linked_json, "
        "campaign_id, next_action, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            draft_id,
            tenant_id,
            account_id,
            symbol.upper(),
            "CHART_DRAFT",
            strategy,
            None,
            analysis_id or ae_id,
            family,
            direction,
            0.0,
            None,
            None,
            "[]",
            None,
            "Stage 2 confirmation required before risk or execution",
            "DRAFT_REQUIRES_REVIEW",
            "QUALIFICATION",
            None,
            json.dumps([ae_id]),
            ae_id,
            "Review in Trading Opportunities / Cacsms Engine — no order submitted from chart",
            now,
            now,
        ),
    )
    return {"id": draft_id, "status": "DRAFT_REQUIRES_REVIEW", "ae_opportunity_id": ae_id}
