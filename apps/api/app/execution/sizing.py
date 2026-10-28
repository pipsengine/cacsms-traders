"""Position size from broker contract data, in the account currency.

Tick value must already be expressed in the account currency. A USD pip value
is not reused as an NGN amount. Volume is rounded down, and a minimum lot that
would spend more than the risk budget is rejected.
"""
from __future__ import annotations

from dataclasses import dataclass

from .money import ZERO, D, floor_to_step, money


@dataclass(frozen=True)
class SizeResult:
    ok: bool
    volume: object
    risk_amount: object
    projected_loss: object
    reason: str | None


def tick_value_from_move(profit, steps: int):
    """One-tick value in account currency, from the profit of several ticks on one lot."""
    if profit is None or steps <= 0:
        return None
    try:
        value = abs(D(profit) / D(steps))
    except (ArithmeticError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def account_tick_value(*, account_currency: str, tick_value, tick_value_currency: str, profit_tick_value=None,
                       profit_currency: str | None = None, conversion_rate=None, conversion_from: str | None = None,
                       conversion_to: str | None = None) -> tuple[object, str | None]:
    """Return a tick value in the account currency, or a reason it cannot be used."""
    account = (account_currency or "").upper()
    reported = (tick_value_currency or "").upper()
    if tick_value is not None and reported == account and D(tick_value) > 0:
        return D(tick_value), None
    profit_ccy = (profit_currency or "").upper()
    if profit_tick_value is not None and profit_ccy == account and D(profit_tick_value) > 0:
        return D(profit_tick_value), None
    if (profit_tick_value is not None and conversion_rate is not None and profit_ccy
            and (conversion_from or "").upper() == profit_ccy and (conversion_to or "").upper() == account
            and D(conversion_rate) > 0):
        return D(profit_tick_value) * D(conversion_rate), None
    return None, "PROFIT_CURRENCY_UNCONVERTED"


def size_position(*, equity, risk_pct, price, stop, tick_size, tick_value, volume_min, volume_max, volume_step,
                  commission_per_lot=0, spread_cost_per_lot=0, stops_distance=0) -> SizeResult:
    equity_d = D(equity)
    risk = D(risk_pct)
    if equity_d <= 0 or risk <= 0:
        return SizeResult(False, None, ZERO, None, "NO_RISK_BUDGET")
    risk_amount = money(equity_d * risk / D(100))
    distance = abs(D(price) - D(stop))
    tick = D(tick_size)
    value = D(tick_value)
    step = D(volume_step)
    minimum = D(volume_min)
    maximum = D(volume_max)
    if distance <= 0 or tick <= 0 or value <= 0 or step <= 0 or minimum <= 0:
        return SizeResult(False, None, risk_amount, None, "CONTRACT_SPEC_INCOMPLETE")
    if D(stops_distance) > 0 and distance < D(stops_distance):
        return SizeResult(False, None, risk_amount, None, "STOPS_LEVEL")
    cost = D(commission_per_lot) + D(spread_cost_per_lot)
    loss_per_lot = (distance / tick) * value + cost
    if loss_per_lot <= 0:
        return SizeResult(False, None, risk_amount, None, "CONTRACT_SPEC_INCOMPLETE")
    raw = risk_amount / loss_per_lot
    volume = floor_to_step(raw, step)
    if maximum > 0 and volume > maximum:
        volume = floor_to_step(maximum, step)
    if volume < minimum:
        return SizeResult(False, None, risk_amount, money(minimum * loss_per_lot), "MINIMUM_EXCEEDS_BUDGET")
    projected = money(volume * loss_per_lot)
    if projected > risk_amount:
        return SizeResult(False, None, risk_amount, projected, "MINIMUM_EXCEEDS_BUDGET")
    return SizeResult(True, volume, risk_amount, projected, None)
