"""Decimal and tick/step operations at accounting and order boundaries."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR, Decimal
from typing import Any

from .canonical import canonical_decimal
from .errors import ContractError


def as_decimal(value: Any) -> Decimal:
    """Parse a canonical Decimal-compatible input while rejecting floats."""

    return Decimal(canonical_decimal(value))


def _positive_quantum(quantum: Any) -> Decimal:
    parsed = as_decimal(quantum)
    if parsed <= 0:
        raise ContractError("tick/step must be greater than zero")
    return parsed


def round_down_to_step(value: Any, step: Any) -> Decimal:
    """Round a non-negative quantity down to a valid step."""

    number = as_decimal(value)
    quantum = _positive_quantum(step)
    if number < 0:
        raise ContractError("quantity cannot be negative")
    units = (number / quantum).to_integral_value(rounding=ROUND_FLOOR)
    return units * quantum


def round_signed_exposure_toward_zero(value: Any, step: Any) -> Decimal:
    """Reduce the absolute magnitude of a signed target to a valid step."""

    number = as_decimal(value)
    quantum = _positive_quantum(step)
    units = (number / quantum).to_integral_value(rounding=ROUND_DOWN)
    return units * quantum


def round_price_down(value: Any, tick: Any) -> Decimal:
    number = as_decimal(value)
    quantum = _positive_quantum(tick)
    if number <= 0:
        raise ContractError("price must be greater than zero")
    return (number / quantum).to_integral_value(rounding=ROUND_FLOOR) * quantum


def round_price_up(value: Any, tick: Any) -> Decimal:
    number = as_decimal(value)
    quantum = _positive_quantum(tick)
    if number <= 0:
        raise ContractError("price must be greater than zero")
    return (number / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum


@dataclass(frozen=True)
class RiskRatio:
    """A unit ratio in [0, 1]; integer percentages such as 25 are invalid."""

    value: Decimal

    def __init__(self, value: Any) -> None:
        parsed = as_decimal(value)
        if parsed < 0 or parsed > 1:
            raise ContractError("risk ratio must be in [0, 1]")
        object.__setattr__(self, "value", parsed)

    def multiply(self, other: "RiskRatio") -> "RiskRatio":
        return RiskRatio(self.value * other.value)

    def __str__(self) -> str:
        return canonical_decimal(self.value)
