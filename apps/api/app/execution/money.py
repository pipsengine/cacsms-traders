"""Exact decimal amounts. Financial rows store these strings, not binary floats."""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN

MONEY = Decimal("0.01")
ZERO = Decimal("0")


def D(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or value is None:
        raise ValueError("missing amount")
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value).strip())


def money(value) -> Decimal:
    return D(value).quantize(MONEY, rounding=ROUND_HALF_EVEN)


def text(value: Decimal) -> str:
    return format(value, "f")


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    step = D(step)
    if step <= 0:
        raise ValueError("lot step must be positive")
    units = (D(value) / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step
