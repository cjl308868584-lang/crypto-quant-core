"""Pure deterministic Broker used only by the credential-free System Paper."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Tuple

from .canonical import business_hash, canonical_decimal, stable_id, utc_datetime
from .decimal_math import (
    as_decimal,
    round_down_to_step,
    round_price_down,
    round_price_up,
)
from .errors import ContractError
from .instruments import (
    InstrumentMetadata,
    OrderPlanStatus,
    OrderSide,
    RoundedOrderPlan,
    plan_order,
)
from .orders import OrderAggregate, OrderEventType, OrderState


_FROZEN_SLIPPAGE_PER_SIDE = Decimal("0.001")
_FROZEN_TAKER_FEE_PER_SIDE = Decimal("0.0015")


class FillScenarioKind(str, Enum):
    PARTIAL_THEN_FULL = "PARTIAL_THEN_FULL"
    DISCONNECT_AFTER_SUBMIT = "DISCONNECT_AFTER_SUBMIT"
    REJECTED = "REJECTED"
    CANCEL_BEFORE_FILL = "CANCEL_BEFORE_FILL"
    FILL_BEFORE_CANCEL = "FILL_BEFORE_CANCEL"
    FILL_BEFORE_ACK_WITH_DUPLICATE = "FILL_BEFORE_ACK_WITH_DUPLICATE"
    TIMEOUT_AFTER_ACK = "TIMEOUT_AFTER_ACK"
    IMPOSSIBLE_OVERFILL = "IMPOSSIBLE_OVERFILL"


@dataclass(frozen=True, init=False)
class FillScenario:
    """A frozen event recipe; it never reads time, random state, files or network."""

    kind: FillScenarioKind
    partial_fill_ratio_or_null: Optional[Decimal]

    def __init__(self) -> None:
        raise TypeError("FillScenario must be created by a validated factory")

    @classmethod
    def partial_then_full(cls, partial_fill_ratio: object) -> "FillScenario":
        ratio = as_decimal(partial_fill_ratio)
        if not Decimal("0") < ratio < Decimal("1"):
            raise ContractError("partial fill ratio must be strictly between zero and one")
        instance = object.__new__(cls)
        object.__setattr__(instance, "kind", FillScenarioKind.PARTIAL_THEN_FULL)
        object.__setattr__(instance, "partial_fill_ratio_or_null", ratio)
        return instance

    @classmethod
    def disconnect_after_submit(cls) -> "FillScenario":
        return cls._without_ratio(FillScenarioKind.DISCONNECT_AFTER_SUBMIT)

    @classmethod
    def rejected(cls) -> "FillScenario":
        return cls._without_ratio(FillScenarioKind.REJECTED)

    @classmethod
    def cancel_before_fill(cls) -> "FillScenario":
        return cls._without_ratio(FillScenarioKind.CANCEL_BEFORE_FILL)

    @classmethod
    def fill_before_cancel(cls, partial_fill_ratio: object) -> "FillScenario":
        return cls._with_ratio(
            FillScenarioKind.FILL_BEFORE_CANCEL,
            partial_fill_ratio,
        )

    @classmethod
    def fill_before_ack_with_duplicate(
        cls,
        partial_fill_ratio: object,
    ) -> "FillScenario":
        return cls._with_ratio(
            FillScenarioKind.FILL_BEFORE_ACK_WITH_DUPLICATE,
            partial_fill_ratio,
        )

    @classmethod
    def timeout_after_ack(cls) -> "FillScenario":
        return cls._without_ratio(FillScenarioKind.TIMEOUT_AFTER_ACK)

    @classmethod
    def impossible_overfill(cls) -> "FillScenario":
        return cls._without_ratio(FillScenarioKind.IMPOSSIBLE_OVERFILL)

    @classmethod
    def _without_ratio(cls, kind: FillScenarioKind) -> "FillScenario":
        instance = object.__new__(cls)
        object.__setattr__(instance, "kind", kind)
        object.__setattr__(instance, "partial_fill_ratio_or_null", None)
        return instance

    @classmethod
    def _with_ratio(
        cls,
        kind: FillScenarioKind,
        partial_fill_ratio: object,
    ) -> "FillScenario":
        ratio = as_decimal(partial_fill_ratio)
        if not Decimal("0") < ratio < Decimal("1"):
            raise ContractError("partial fill ratio must be strictly between zero and one")
        instance = object.__new__(cls)
        object.__setattr__(instance, "kind", kind)
        object.__setattr__(instance, "partial_fill_ratio_or_null", ratio)
        return instance


@dataclass(frozen=True)
class SimulatedOrderCommand:
    scheduled_for: datetime
    instrument_id: str
    side: OrderSide
    order_type: str
    time_in_force_or_null: Optional[str]
    requested_quantity: Decimal
    requested_price_or_null: Optional[Decimal]
    risk_increasing: bool
    reduce_only: bool
    approved_notional_usdt_or_null: Optional[Decimal]
    risk_approved: bool

    def __post_init__(self) -> None:
        utc_datetime(self.scheduled_for)
        if not isinstance(self.instrument_id, str) or not self.instrument_id:
            raise ContractError("instrument_id must be a non-empty string")
        if not isinstance(self.side, OrderSide):
            raise ContractError("side must use the frozen OrderSide enum")
        if not isinstance(self.risk_increasing, bool):
            raise ContractError("risk_increasing must be boolean")
        if not isinstance(self.reduce_only, bool):
            raise ContractError("reduce_only must be boolean")
        if not isinstance(self.risk_approved, bool):
            raise ContractError("risk_approved must be boolean")
        object.__setattr__(
            self,
            "requested_quantity",
            as_decimal(self.requested_quantity),
        )
        object.__setattr__(
            self,
            "requested_price_or_null",
            None
            if self.requested_price_or_null is None
            else as_decimal(self.requested_price_or_null),
        )
        object.__setattr__(
            self,
            "approved_notional_usdt_or_null",
            None
            if self.approved_notional_usdt_or_null is None
            else as_decimal(self.approved_notional_usdt_or_null),
        )


@dataclass(frozen=True)
class SimulatedMarketEvidence:
    observed_at: datetime
    instrument_metadata: InstrumentMetadata
    best_bid_price: Decimal
    best_ask_price: Decimal
    last_trade_price: Decimal
    market_bundle_hash: str

    def __post_init__(self) -> None:
        utc_datetime(self.observed_at)
        if not isinstance(self.instrument_metadata, InstrumentMetadata):
            raise ContractError("market evidence requires InstrumentMetadata")
        for field_name in (
            "best_bid_price",
            "best_ask_price",
            "last_trade_price",
        ):
            value = as_decimal(getattr(self, field_name))
            if value <= 0:
                raise ContractError("market prices must be positive")
            object.__setattr__(self, field_name, value)
        if self.best_bid_price > self.best_ask_price:
            raise ContractError("best bid cannot exceed best ask")
        if len(self.market_bundle_hash) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.market_bundle_hash
        ):
            raise ContractError("market_bundle_hash must be a lowercase SHA-256 digest")


@dataclass(frozen=True)
class SimulatedOrderResult:
    local_order_id: str
    state: OrderState
    requested_quantity: Decimal
    cumulative_filled_quantity: Decimal
    average_fill_price: Optional[Decimal]
    fee_usdt: Decimal
    event_ids: Tuple[str, ...]
    risk_lock_required: bool
    result_hash: str


@dataclass
class _OrderRecord:
    aggregate: OrderAggregate
    command: SimulatedOrderCommand
    market: SimulatedMarketEvidence
    rounded_plan: RoundedOrderPlan
    event_ids: Tuple[str, ...]
    reconcile_completed: bool


class SimulatedBroker:
    """In-memory deterministic event source backed by the production order aggregate."""

    def __init__(self, scenario: FillScenario) -> None:
        if not isinstance(scenario, FillScenario):
            raise ContractError("SimulatedBroker requires a frozen FillScenario")
        self._scenario = scenario
        self._orders: Dict[str, _OrderRecord] = {}

    def submit(
        self,
        command: SimulatedOrderCommand,
        market: SimulatedMarketEvidence,
    ) -> SimulatedOrderResult:
        if command.instrument_id != market.instrument_metadata.instrument_id:
            raise ContractError("command and market instrument identities differ")
        rounded = plan_order(
            metadata=market.instrument_metadata,
            decision_time=command.scheduled_for,
            side=command.side,
            order_type=command.order_type,
            time_in_force_or_null=command.time_in_force_or_null,
            requested_quantity=command.requested_quantity,
            requested_price_or_null=command.requested_price_or_null,
            notional_reference_price=market.last_trade_price,
            risk_increasing=command.risk_increasing,
            reduce_only=command.reduce_only,
            approved_notional_usdt_or_null=command.approved_notional_usdt_or_null,
        )
        identity = {
            "command": command,
            "market": market,
            "rounded_plan_hash": rounded.plan_hash,
            "scenario": self._scenario,
        }
        local_order_id = stable_id("paper_order", identity)
        existing = self._orders.get(local_order_id)
        if existing is not None:
            return self._result(existing)
        requested_quantity = (
            rounded.rounded_quantity
            if rounded.status is OrderPlanStatus.READY
            else command.requested_quantity
        )
        aggregate = OrderAggregate(
            local_order_id=local_order_id,
            attempt_id=stable_id("paper_attempt", identity),
            client_order_id=stable_id("paper_client", identity),
            requested_quantity=requested_quantity,
        )
        record = _OrderRecord(
            aggregate=aggregate,
            command=command,
            market=market,
            rounded_plan=rounded,
            event_ids=(),
            reconcile_completed=False,
        )
        self._orders[local_order_id] = record
        self._apply(record, "risk", OrderEventType.RISK_PASS if command.risk_approved else OrderEventType.RISK_DENY)
        if not command.risk_approved:
            return self._result(record)
        if rounded.status is not OrderPlanStatus.READY:
            self._apply(record, "validation", OrderEventType.LOCAL_VALIDATION_FAILED)
            return self._result(record)
        self._apply(record, "submit", OrderEventType.SUBMIT_STARTED)
        if rounded.order_type == "LIMIT" and not self._is_marketable(
            rounded,
            market,
        ):
            self._apply(record, "ack", OrderEventType.ACK)
            self._apply(record, "expired", OrderEventType.VENUE_EXPIRED)
            return self._result(record)
        if self._scenario.kind is FillScenarioKind.DISCONNECT_AFTER_SUBMIT:
            self._apply(record, "disconnect", OrderEventType.DISCONNECT)
            return self._result(record)
        if self._scenario.kind is FillScenarioKind.REJECTED:
            self._apply(record, "reject", OrderEventType.REJECT)
            return self._result(record)
        if self._scenario.kind is FillScenarioKind.CANCEL_BEFORE_FILL:
            self._apply(record, "ack", OrderEventType.ACK)
            self._apply(record, "cancel_requested", OrderEventType.CANCEL_REQUESTED)
            self._apply(record, "cancel_confirmed", OrderEventType.CANCEL_CONFIRMED)
            return self._result(record)
        if self._scenario.kind is FillScenarioKind.TIMEOUT_AFTER_ACK:
            self._apply(record, "ack", OrderEventType.ACK)
            self._apply(record, "timeout", OrderEventType.TIMEOUT)
            return self._result(record)
        if self._scenario.kind is FillScenarioKind.IMPOSSIBLE_OVERFILL:
            self._apply(record, "ack", OrderEventType.ACK)
            try:
                self._apply(
                    record,
                    "overfill",
                    OrderEventType.FULL_FILL,
                    cumulative_filled_quantity=(
                        rounded.rounded_quantity
                        + market.instrument_metadata.quantity_step
                    ),
                )
            except Exception:
                del self._orders[local_order_id]
                raise
            raise ContractError("impossible overfill scenario did not fail closed")
        ratio = self._scenario.partial_fill_ratio_or_null
        if ratio is None:
            raise ContractError("partial fill scenario is missing its ratio")
        partial_quantity = round_down_to_step(
            rounded.rounded_quantity * ratio,
            market.instrument_metadata.quantity_step,
        )
        if partial_quantity <= 0 or partial_quantity >= rounded.rounded_quantity:
            raise ContractError("partial fill ratio is not executable at quantity step")
        if self._scenario.kind is FillScenarioKind.FILL_BEFORE_ACK_WITH_DUPLICATE:
            self._apply(
                record,
                "partial",
                OrderEventType.PARTIAL_FILL,
                cumulative_filled_quantity=partial_quantity,
            )
            self._apply(
                record,
                "partial",
                OrderEventType.PARTIAL_FILL,
                cumulative_filled_quantity=partial_quantity,
            )
            self._apply(record, "ack", OrderEventType.ACK)
            return self._result(record)
        self._apply(record, "ack", OrderEventType.ACK)
        self._apply(
            record,
            "partial",
            OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=partial_quantity,
        )
        if self._scenario.kind is FillScenarioKind.FILL_BEFORE_CANCEL:
            self._apply(record, "cancel_requested", OrderEventType.CANCEL_REQUESTED)
            self._apply(record, "cancel_confirmed", OrderEventType.CANCEL_CONFIRMED)
        return self._result(record)

    @staticmethod
    def _is_marketable(
        rounded_plan: RoundedOrderPlan,
        market: SimulatedMarketEvidence,
    ) -> bool:
        limit_price = rounded_plan.rounded_price_or_null
        if limit_price is None:
            return True
        execution_price = SimulatedBroker._execution_price(
            rounded_plan.side,
            market,
        )
        if rounded_plan.side is OrderSide.BUY:
            return limit_price >= execution_price
        return limit_price <= execution_price

    @staticmethod
    def _execution_price(
        side: OrderSide,
        market: SimulatedMarketEvidence,
    ) -> Decimal:
        if side is OrderSide.BUY:
            return round_price_up(
                market.best_ask_price
                * (Decimal("1") + _FROZEN_SLIPPAGE_PER_SIDE),
                market.instrument_metadata.price_tick,
            )
        return round_price_down(
            market.best_bid_price
            * (Decimal("1") - _FROZEN_SLIPPAGE_PER_SIDE),
            market.instrument_metadata.price_tick,
        )

    def reconcile(self, local_order_id: str) -> SimulatedOrderResult:
        try:
            record = self._orders[local_order_id]
        except KeyError as exc:
            raise ContractError("unknown simulated local_order_id") from exc
        if record.reconcile_completed:
            return self._result(record)
        if record.aggregate.state is OrderState.UNKNOWN:
            reconciliation_result_id = stable_id(
                "paper_reconciliation",
                {
                    "local_order_id": local_order_id,
                    "outcome": "UNRESOLVED",
                },
            )
            self._apply(
                record,
                "reconcile_unresolved",
                OrderEventType.RECON_UNRESOLVED,
                reconciliation_result_id=reconciliation_result_id,
            )
        elif self._scenario.kind is FillScenarioKind.PARTIAL_THEN_FULL:
            self._apply(
                record,
                "full",
                OrderEventType.FULL_FILL,
                cumulative_filled_quantity=record.rounded_plan.rounded_quantity,
            )
        record.reconcile_completed = True
        return self._result(record)

    def _apply(
        self,
        record: _OrderRecord,
        event_name: str,
        event_type: OrderEventType,
        *,
        cumulative_filled_quantity: Optional[Decimal] = None,
        reconciliation_result_id: Optional[str] = None,
    ) -> None:
        event_id = stable_id(
            "paper_event",
            {
                "local_order_id": record.aggregate.local_order_id,
                "event_name": event_name,
            },
        )
        record.aggregate.apply(
            event_id=event_id,
            event_type=event_type,
            cumulative_filled_quantity=cumulative_filled_quantity,
            reconciliation_result_id=reconciliation_result_id,
        )
        if event_id not in record.event_ids:
            record.event_ids += (event_id,)

    def _result(self, record: _OrderRecord) -> SimulatedOrderResult:
        quantity = record.aggregate.cumulative_filled_quantity
        fill_price = self._execution_price(
            record.command.side,
            record.market,
        )
        average_fill_price = None if quantity == 0 else fill_price
        fee = (
            Decimal("0")
            if average_fill_price is None
            else quantity
            * average_fill_price
            * record.market.instrument_metadata.contract_multiplier
            * _FROZEN_TAKER_FEE_PER_SIDE
        )
        payload = {
            "local_order_id": record.aggregate.local_order_id,
            "state": record.aggregate.state.value,
            "requested_quantity": canonical_decimal(
                record.aggregate.requested_quantity
            ),
            "cumulative_filled_quantity": canonical_decimal(quantity),
            "average_fill_price": (
                None
                if average_fill_price is None
                else canonical_decimal(average_fill_price)
            ),
            "fee_usdt": canonical_decimal(fee),
            "event_ids": record.event_ids,
            "risk_lock_required": record.aggregate.unknown,
        }
        return SimulatedOrderResult(
            local_order_id=record.aggregate.local_order_id,
            state=record.aggregate.state,
            requested_quantity=record.aggregate.requested_quantity,
            cumulative_filled_quantity=quantity,
            average_fill_price=average_fill_price,
            fee_usdt=fee,
            event_ids=record.event_ids,
            risk_lock_required=record.aggregate.unknown,
            result_hash=business_hash(payload),
        )
