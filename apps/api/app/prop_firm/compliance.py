"""Deterministic prop-firm compliance.

A high score cannot pass this gate. Missing rules, a stale observation, or an
unknown remaining-risk figure fail closed and block the new order. A warning
never closes an open position unless the account rule explicitly allows it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class ComplianceError(ValueError):
    pass


DRAWDOWN_METHODS = ("STATIC", "TRAILING", "EOD_TRAILING")
DAILY_REFERENCES = ("BALANCE", "EQUITY")


@dataclass(frozen=True)
class FirmRules:
    daily_loss_pct: float
    max_loss_pct: float
    drawdown_method: str = "STATIC"
    daily_reference: str = "BALANCE"
    reset_timezone: str = "UTC"
    max_positions: int = 5
    max_lot: float = 2.0
    floating_loss_pct: float = 5.0
    news_block_minutes: int = 0
    weekend_holding: bool = False
    automation_permitted: bool = False
    permitted_strategies: tuple[str, ...] = ()
    profit_target_pct: float = 10.0
    slippage_buffer_pct: float = 0.2
    warning_ratio: float = 0.6
    reduced_ratio: float = 0.8
    emergency_close: bool = False
    max_snapshot_age_seconds: int = 30

    @classmethod
    def from_dict(cls, raw: dict | None) -> "FirmRules":
        if not isinstance(raw, dict) or not raw:
            raise ComplianceError("Firm rules are missing")
        method = str(raw.get("drawdown_method") or "STATIC").upper()
        reference = str(raw.get("daily_reference") or "BALANCE").upper()
        if method not in DRAWDOWN_METHODS:
            raise ComplianceError("Drawdown method is not supported")
        if reference not in DAILY_REFERENCES:
            raise ComplianceError("Daily loss reference is not supported")
        try:
            tz = ZoneInfo(str(raw.get("reset_timezone") or "UTC"))
        except Exception as exc:
            raise ComplianceError("Reset timezone is not valid") from exc
        del tz
        strategies = tuple(str(item) for item in (raw.get("permitted_strategies") or []) if str(item).strip())
        return cls(
            daily_loss_pct=float(raw["daily_loss_pct"]),
            max_loss_pct=float(raw["max_loss_pct"]),
            drawdown_method=method,
            daily_reference=reference,
            reset_timezone=str(raw.get("reset_timezone") or "UTC"),
            max_positions=int(raw.get("max_positions") or 0),
            max_lot=float(raw.get("max_lot") or 0),
            floating_loss_pct=float(raw.get("floating_loss_pct") or 0),
            news_block_minutes=int(raw.get("news_block_minutes") or 0),
            weekend_holding=bool(raw.get("weekend_holding")),
            automation_permitted=bool(raw.get("automation_permitted")),
            permitted_strategies=strategies,
            profit_target_pct=float(raw.get("profit_target_pct") or 0),
            slippage_buffer_pct=float(raw.get("slippage_buffer_pct") or 0),
            warning_ratio=float(raw.get("warning_ratio") or 0.6),
            reduced_ratio=float(raw.get("reduced_ratio") or 0.8),
            emergency_close=bool(raw.get("emergency_close")),
            max_snapshot_age_seconds=int(raw.get("max_snapshot_age_seconds") or 30),
        )


@dataclass(frozen=True)
class Observation:
    balance: float
    equity: float
    initial_balance: float
    day_start_balance: float
    day_start_equity: float
    equity_high: float
    eod_equity_high: float
    floating_pnl: float
    commission: float = 0.0
    open_positions: int = 0
    pending_orders: int = 0
    open_risk_pct: float = 0.0
    proposed_lot: float = 0.0
    proposed_risk_pct: float = 0.0
    snapshot_age_seconds: float | None = 0.0
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    news_blackout: bool = False
    news_calendar_available: bool = False
    strategy: str | None = None
    duplicate: bool = False
    automation_confirmed: bool = False
    autonomous: bool = True


@dataclass(frozen=True)
class Decision:
    allow: bool
    protection: str
    daily_drawdown_pct: float | None
    max_drawdown_pct: float | None
    reasons: tuple[str, ...]
    close_positions: bool

    def as_dict(self) -> dict:
        return {
            "allow": self.allow,
            "protection": self.protection,
            "daily_drawdown_pct": self.daily_drawdown_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "reasons": list(self.reasons),
            "close_positions": self.close_positions,
        }


def _local(now: datetime, tz_name: str) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ZoneInfo(tz_name))


def weekend_window(now: datetime, tz_name: str) -> bool:
    local = _local(now, tz_name)
    if local.weekday() >= 5:
        return True
    return local.weekday() == 4 and local.hour >= 21


def _pct(loss: float, base: float) -> float:
    if base <= 0:
        raise ComplianceError("Remaining risk cannot be established")
    return round(100.0 * loss / base, 4)


def evaluate(rules: FirmRules | None, observation: Observation | None) -> Decision:
    reasons: list[str] = []
    if rules is None or observation is None:
        return Decision(False, "SUSPENDED", None, None, ("Compliance rules or account observation are missing",), False)
    try:
        parsed = rules if isinstance(rules, FirmRules) else FirmRules.from_dict(rules)  # type: ignore[arg-type]
    except (ComplianceError, KeyError, TypeError, ValueError) as exc:
        return Decision(False, "SUSPENDED", None, None, (str(exc) or "Firm rules are missing",), False)

    age = observation.snapshot_age_seconds
    if age is None or age > parsed.max_snapshot_age_seconds:
        reasons.append("Broker observation is stale or missing")
    if observation.equity <= 0 or observation.balance <= 0 or observation.initial_balance <= 0:
        reasons.append("Remaining risk cannot be established")

    daily_pct = max_pct = None
    if not any("cannot be established" in item or "stale" in item for item in reasons):
        try:
            reference = observation.day_start_equity if parsed.daily_reference == "EQUITY" else observation.day_start_balance
            daily_loss = max(0.0, reference - observation.equity) + max(0.0, observation.commission)
            daily_loss += observation.equity * parsed.slippage_buffer_pct / 100.0
            daily_pct = _pct(daily_loss, reference)
            if parsed.drawdown_method == "TRAILING":
                base, mark = observation.equity_high, observation.equity_high
            elif parsed.drawdown_method == "EOD_TRAILING":
                base, mark = observation.eod_equity_high, observation.eod_equity_high
            else:
                base, mark = observation.initial_balance, observation.initial_balance
            max_loss = max(0.0, mark - observation.equity) + max(0.0, observation.commission)
            max_loss += observation.equity * parsed.slippage_buffer_pct / 100.0
            max_pct = _pct(max_loss, base)
        except ComplianceError as exc:
            reasons.append(str(exc))

    if daily_pct is not None and parsed.daily_loss_pct > 0 and daily_pct >= parsed.daily_loss_pct:
        reasons.append("Daily loss limit is reached")
    if max_pct is not None and parsed.max_loss_pct > 0 and max_pct >= parsed.max_loss_pct:
        reasons.append("Maximum loss limit is reached")
    floating_pct = 0.0
    if observation.equity > 0 and observation.floating_pnl < 0:
        floating_pct = round(100.0 * abs(observation.floating_pnl) / observation.equity, 4)
    if parsed.floating_loss_pct > 0 and floating_pct >= parsed.floating_loss_pct:
        reasons.append("Floating loss limit is reached")
    if observation.open_positions + observation.pending_orders >= parsed.max_positions:
        reasons.append("Maximum open positions is reached")
    if observation.proposed_lot > parsed.max_lot:
        reasons.append("Order lot is above the firm maximum")
    room = None
    if daily_pct is not None and parsed.daily_loss_pct > 0:
        room = parsed.daily_loss_pct - daily_pct
    if room is not None and observation.proposed_risk_pct > 0 and observation.open_risk_pct + observation.proposed_risk_pct > room:
        reasons.append("Reserved risk exceeds the remaining daily capacity")
    if observation.duplicate:
        reasons.append("A matching order is already reserved")
    if parsed.news_block_minutes > 0 and not observation.news_calendar_available:
        reasons.append("News calendar is not available")
    elif observation.news_blackout:
        reasons.append("News restriction is active")
    if not parsed.weekend_holding and weekend_window(observation.now, parsed.reset_timezone):
        reasons.append("Weekend holding is not permitted")
    if observation.autonomous and not (parsed.automation_permitted and observation.automation_confirmed):
        reasons.append("Automated trading is not confirmed for this firm")
    if observation.strategy and parsed.permitted_strategies and observation.strategy not in parsed.permitted_strategies:
        reasons.append("Strategy is not permitted on this account")

    hard = [item for item in reasons if item]
    util = 0.0
    if daily_pct is not None and parsed.daily_loss_pct > 0:
        util = max(util, daily_pct / parsed.daily_loss_pct)
    if max_pct is not None and parsed.max_loss_pct > 0:
        util = max(util, max_pct / parsed.max_loss_pct)
    if hard:
        protection = "EMERGENCY" if parsed.emergency_close and any("limit is reached" in item for item in hard) else "SUSPENDED"
    elif util >= 1:
        protection = "EMERGENCY" if parsed.emergency_close else "SUSPENDED"
    elif util >= parsed.reduced_ratio:
        protection = "REDUCED"
    elif util >= parsed.warning_ratio:
        protection = "WARNING"
    else:
        protection = "CLEAR"
    close = bool(parsed.emergency_close and protection == "EMERGENCY")
    return Decision(not hard, protection, daily_pct, max_pct, tuple(hard), close)
