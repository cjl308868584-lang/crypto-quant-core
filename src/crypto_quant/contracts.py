"""Core serializable contracts for the decision-to-execution chain."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .decimal_math import RiskRatio, as_decimal
from .errors import ContractError


class Direction(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class MetaAction(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REDUCE = "REDUCE"


class RiskAction(str, Enum):
    APPROVE = "APPROVE"
    REDUCE = "REDUCE"
    FREEZE_INCREASES = "FREEZE_INCREASES"
    FLATTEN = "FLATTEN"
    HALT = "HALT"


@dataclass(frozen=True)
class MetaDecision:
    schema_version: str
    recipe_release_id: str
    proposal_id: str
    decision_time: datetime
    direction: Direction
    action: MetaAction
    risk_bucket: RiskRatio
    reason_code: str

    def __post_init__(self) -> None:
        if self.action is MetaAction.REJECT and self.risk_bucket.value != 0:
            raise ContractError("REJECT must carry a zero risk bucket")
        if self.direction is Direction.FLAT and self.risk_bucket.value != 0:
            raise ContractError("FLAT must carry a zero risk bucket")
        allowed = {
            Decimal("0"),
            Decimal("0.25"),
            Decimal("0.5"),
            Decimal("0.75"),
            Decimal("1"),
        }
        if self.risk_bucket.value not in allowed:
            raise ContractError("risk bucket must be one of 0/0.25/0.5/0.75/1")

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "recipe_release_id": self.recipe_release_id,
            "proposal_id": self.proposal_id,
            "decision_time": utc_datetime(self.decision_time),
            "direction": self.direction.value,
            "action": self.action.value,
            "risk_bucket": str(self.risk_bucket),
            "reason_code": self.reason_code,
        }

    @property
    def decision_id(self) -> str:
        return stable_id("meta", self.business_payload())

    @property
    def payload_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class TargetPosition:
    schema_version: str
    meta_decision_id: str
    instrument_id: str
    target_sequence: int
    decision_time: datetime
    direction: Direction
    target_quantity: Decimal
    approved_capital_usdt: Decimal
    risk_bucket: RiskRatio

    def __post_init__(self) -> None:
        quantity = as_decimal(self.target_quantity)
        capital = as_decimal(self.approved_capital_usdt)
        if self.target_sequence < 0:
            raise ContractError("target_sequence cannot be negative")
        if capital <= 0:
            raise ContractError("approved capital must be positive")
        if self.direction is Direction.FLAT and quantity != 0:
            raise ContractError("FLAT target quantity must be zero")
        if self.direction is Direction.LONG and quantity < 0:
            raise ContractError("LONG target quantity cannot be negative")
        if self.direction is Direction.SHORT and quantity > 0:
            raise ContractError("SHORT target quantity cannot be positive")
        object.__setattr__(self, "target_quantity", quantity)
        object.__setattr__(self, "approved_capital_usdt", capital)

    def business_payload(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "meta_decision_id": self.meta_decision_id,
            "instrument_id": self.instrument_id,
            "target_sequence": self.target_sequence,
            "decision_time": utc_datetime(self.decision_time),
            "direction": self.direction.value,
            "target_quantity": canonical_decimal(self.target_quantity),
            "approved_capital_usdt": canonical_decimal(self.approved_capital_usdt),
            "risk_bucket": str(self.risk_bucket),
        }

    @property
    def target_id(self) -> str:
        return stable_id("target", self.business_payload())

    @property
    def payload_hash(self) -> str:
        return business_hash(self.business_payload())


@dataclass(frozen=True)
class PortfolioRiskSnapshot:
    schema_version: str
    snapshot_time: datetime
    marked_equity_usdt: Decimal
    current_signed_exposure_usdt: Decimal
    active_order_worst_case_exposure_usdt: Decimal
    deployment_stage_cap: RiskRatio
    drawdown_ratio: RiskRatio
    unresolved_order_count: int
    reconciliation_clean: bool

    def __post_init__(self) -> None:
        equity = as_decimal(self.marked_equity_usdt)
        active = as_decimal(self.active_order_worst_case_exposure_usdt)
        if equity <= 0:
            raise ContractError("marked equity must be positive")
        if active < 0 or self.unresolved_order_count < 0:
            raise ContractError("risk snapshot counts and magnitudes cannot be negative")
        object.__setattr__(self, "marked_equity_usdt", equity)
        object.__setattr__(
            self,
            "current_signed_exposure_usdt",
            as_decimal(self.current_signed_exposure_usdt),
        )
        object.__setattr__(self, "active_order_worst_case_exposure_usdt", active)


@dataclass(frozen=True)
class EventEnvelope:
    schema_version: str
    event_id: str
    trace_id: str
    correlation_id: str
    causation_id: Optional[str]
    run_id: str
    event_time: datetime
    available_at: datetime
    ingested_at: datetime
    recorded_at: datetime
    source: str
    payload_hash: str
    event_hash: str
    ordering_exception_reason: Optional[str] = None

    @classmethod
    def create(
        cls,
        *,
        schema_version: str,
        event_id: str,
        trace_id: str,
        correlation_id: str,
        causation_id: Optional[str],
        run_id: str,
        event_time: datetime,
        available_at: datetime,
        ingested_at: datetime,
        recorded_at: datetime,
        source: str,
        payload: Dict[str, Any],
        ordering_exception_reason: Optional[str] = None,
    ) -> "EventEnvelope":
        payload_digest = business_hash(payload)
        values = {
            "schema_version": schema_version,
            "event_id": event_id,
            "trace_id": trace_id,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
            "run_id": run_id,
            "event_time": event_time,
            "available_at": available_at,
            "ingested_at": ingested_at,
            "recorded_at": recorded_at,
            "source": source,
            "payload_hash": payload_digest,
            "ordering_exception_reason": ordering_exception_reason,
        }
        body = {
            **values,
            "event_time": utc_datetime(event_time),
            "available_at": utc_datetime(available_at),
            "ingested_at": utc_datetime(ingested_at),
            "recorded_at": utc_datetime(recorded_at),
        }
        envelope = cls(event_hash=business_hash(body), **values)
        envelope.validate(payload)
        return envelope

    def body_for_hash(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "run_id": self.run_id,
            "event_time": utc_datetime(self.event_time),
            "available_at": utc_datetime(self.available_at),
            "ingested_at": utc_datetime(self.ingested_at),
            "recorded_at": utc_datetime(self.recorded_at),
            "source": self.source,
            "payload_hash": self.payload_hash,
            "ordering_exception_reason": self.ordering_exception_reason,
        }

    def validate(self, payload: Dict[str, Any]) -> None:
        if business_hash(payload) != self.payload_hash:
            raise ContractError("payload hash mismatch")
        if business_hash(self.body_for_hash()) != self.event_hash:
            raise ContractError("event hash mismatch")
        ordered = self.event_time <= self.available_at <= self.ingested_at <= self.recorded_at
        if not ordered and not self.ordering_exception_reason:
            raise ContractError("event timestamps are out of order without a reason code")
