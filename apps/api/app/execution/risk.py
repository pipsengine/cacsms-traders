"""One risk budget for Mode 1 and Mode 2.

Limits use the current broker equity and the recorded equity baselines.
They do not use a fixed starting deposit. A new entry is refused when any
shared limit is already spent.
"""
from __future__ import annotations

from dataclasses import dataclass

from .money import ZERO, D, money


@dataclass(frozen=True)
class RiskPolicy:
    per_trade_pct: object
    max_positions: int | None = None
    max_aggregate_pct: object | None = None
    max_daily_loss_pct: object | None = None
    max_weekly_loss_pct: object | None = None
    max_drawdown_pct: object | None = None
    max_spread_points: object | None = None
    margin_floor_pct: object | None = None
    emergency_stop: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True)
class Baselines:
    peak_equity: object
    day_start_equity: object
    week_start_equity: object


@dataclass(frozen=True)
class RiskResult:
    ok: bool
    reason: str | None
    stage: str


def _pct(limit) -> object | None:
    if limit is None or str(limit).strip() == "":
        return None
    return D(limit)


def live_submission_allowed(*, environment: str, policy: RiskPolicy, system_mode: str, terminal_mode: str | None) -> tuple[bool, str]:
    mode = (system_mode or "").upper()
    terminal = (terminal_mode or "").upper()
    if policy.emergency_stop or mode in ("EMERGENCY_STOP", "PAUSED"):
        return False, "EMERGENCY_STOP"
    if mode == "DEMO_AUTONOMOUS" and terminal == "DEMO":
        return True, "OK"
    if mode == "LIVE_AUTONOMOUS" and terminal == "LIVE":
        if (environment or "").upper() in ("LIVE", "PROP_FIRM") and not policy.live_trading_enabled:
            return False, "LIVE_TRADING_DISABLED"
        return True, "OK"
    return False, "MODE_MISMATCH"


def _loss_limit(equity, start, limit_pct) -> str | None:
    limit = _pct(limit_pct)
    if limit is None:
        return None
    start_d = D(start)
    if start_d <= 0:
        return "BASELINE_REQUIRED"
    lost = start_d - D(equity)
    if lost > money(start_d * limit / D(100)):
        return "LOSS_LIMIT"
    return None


def evaluate_entry(*, policy: RiskPolicy, equity, free_margin, projected_loss, open_losses, open_positions: int,
                   baselines: Baselines | None, spread_points=None, margin_required=None, connected: bool = True,
                   stale: bool = False) -> RiskResult:
    if policy.emergency_stop:
        return RiskResult(False, "EMERGENCY_STOP", "BROKER_ORDER_CHECK")
    if not connected:
        return RiskResult(False, "DISCONNECTED", "BROKER_ORDER_CHECK")
    if stale:
        return RiskResult(False, "DEGRADED", "BROKER_ORDER_CHECK")
    equity_d = D(equity)
    if equity_d <= 0:
        return RiskResult(False, "NO_EQUITY", "RISK_CALCULATED")
    loss = D(projected_loss)
    per_trade = money(equity_d * D(policy.per_trade_pct) / D(100))
    if loss > per_trade:
        return RiskResult(False, "PER_TRADE_RISK", "RISK_CALCULATED")
    if policy.max_positions is not None and open_positions >= int(policy.max_positions):
        return RiskResult(False, "MAX_POSITIONS", "EXPOSURE_CHECKED")
    aggregate = _pct(policy.max_aggregate_pct)
    spent = sum((D(item) for item in open_losses), ZERO) + loss
    if aggregate is not None and spent > money(equity_d * aggregate / D(100)):
        return RiskResult(False, "AGGREGATE_EXPOSURE", "EXPOSURE_CHECKED")
    if baselines is not None:
        if _loss_limit(equity_d, baselines.day_start_equity, policy.max_daily_loss_pct):
            return RiskResult(False, "DAILY_LOSS", "EXPOSURE_CHECKED")
        if _loss_limit(equity_d, baselines.week_start_equity, policy.max_weekly_loss_pct):
            return RiskResult(False, "WEEKLY_LOSS", "EXPOSURE_CHECKED")
        drawdown = _pct(policy.max_drawdown_pct)
        peak = D(baselines.peak_equity)
        if drawdown is not None:
            if peak <= 0:
                return RiskResult(False, "BASELINE_REQUIRED", "EXPOSURE_CHECKED")
            if peak - equity_d > money(peak * drawdown / D(100)):
                return RiskResult(False, "MAX_DRAWDOWN", "EXPOSURE_CHECKED")
    spread_limit = _pct(policy.max_spread_points)
    if spread_limit is not None and spread_points is not None and D(spread_points) > spread_limit:
        return RiskResult(False, "SPREAD", "VOLUME_VALIDATED")
    required = D(margin_required or 0)
    free = D(free_margin)
    if required > free:
        return RiskResult(False, "MARGIN", "MARGIN_CHECKED")
    floor = _pct(policy.margin_floor_pct)
    if floor is not None and (free - required) < money(equity_d * floor / D(100)):
        return RiskResult(False, "MARGIN_FLOOR", "MARGIN_CHECKED")
    return RiskResult(True, None, "BROKER_ORDER_CHECK")
