"""Fail-closed drawdown classification and target capping."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from .decimal_math import as_decimal
from .errors import ContractError


class DrawdownState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    REDUCE = "REDUCE"
    HALT = "HALT"
    HARD_BOUNDARY = "HARD_BOUNDARY"


@dataclass(frozen=True)
class DrawdownBand:
    lower: Decimal
    upper: Decimal
    state: DrawdownState


class DrawdownPolicy:
    """Load the authoritative 10/12/15/20% policy from ReleaseGatePolicy."""

    def __init__(self, bands: Iterable[DrawdownBand]) -> None:
        self._bands = tuple(sorted(bands, key=lambda item: item.lower))
        expected = (
            (Decimal("0.10"), Decimal("0.12"), DrawdownState.WARNING),
            (Decimal("0.12"), Decimal("0.15"), DrawdownState.REDUCE),
            (Decimal("0.15"), Decimal("0.20"), DrawdownState.HALT),
            (Decimal("0.20"), Decimal("Infinity"), DrawdownState.HARD_BOUNDARY),
        )
        actual = tuple((band.lower, band.upper, band.state) for band in self._bands)
        if actual != expected:
            raise ContractError("drawdown policy must match frozen 10/12/15/20% bands")

    @classmethod
    def from_release_policy(cls, policy: Mapping[str, Any]) -> "DrawdownPolicy":
        bands = []
        for item in policy["risk_thresholds"]["drawdown"]:
            upper = (
                Decimal("Infinity")
                if item["upper_bound"] is None
                else as_decimal(item["upper_bound"])
            )
            bands.append(
                DrawdownBand(
                    lower=as_decimal(item["lower_bound"]),
                    upper=upper,
                    state=DrawdownState(item["state"]),
                )
            )
        return cls(bands)

    def classify(self, drawdown_ratio: Any) -> DrawdownState:
        drawdown = as_decimal(drawdown_ratio)
        if drawdown < 0:
            raise ContractError("drawdown ratio cannot be negative")
        for band in self._bands:
            if band.lower <= drawdown < band.upper:
                return band.state
        return DrawdownState.NORMAL

    @staticmethod
    def cap_signed_target(
        *,
        state: DrawdownState,
        current_signed_exposure: Any,
        requested_signed_exposure: Any,
        original_approved_abs_exposure: Any,
    ) -> Decimal:
        """Apply the frozen state semantics without increasing or reversing risk."""

        current = as_decimal(current_signed_exposure)
        requested = as_decimal(requested_signed_exposure)
        approved = as_decimal(original_approved_abs_exposure)
        if approved < 0:
            raise ContractError("approved exposure cannot be negative")
        if state in (DrawdownState.HALT, DrawdownState.HARD_BOUNDARY):
            return Decimal("0")
        if state is DrawdownState.NORMAL:
            magnitude = min(abs(requested), approved)
            return magnitude.copy_sign(requested)

        cap = min(abs(current), approved)
        if state is DrawdownState.REDUCE:
            cap = min(cap, approved * Decimal("0.5"))
        if current == 0 or requested == 0:
            return Decimal("0")
        if current.is_signed() != requested.is_signed():
            return Decimal("0")
        magnitude = min(abs(requested), cap)
        return magnitude.copy_sign(current)
