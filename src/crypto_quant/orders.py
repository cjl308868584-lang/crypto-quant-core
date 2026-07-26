"""Order and PositionExecutor state machines with explicit UNKNOWN semantics."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Set, Tuple

from .canonical import business_hash
from .contracts import Direction, TargetAction, TargetPosition
from .decimal_math import as_decimal
from .errors import ContractError
from .execution import TargetAcceptance, TargetBook


class OrderState(str, Enum):
    CREATED = "CREATED"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_DENIED = "RISK_DENIED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED_PRE_SUBMIT = "FAILED_PRE_SUBMIT"
    UNKNOWN = "UNKNOWN"


class OrderEventType(str, Enum):
    RISK_PASS = "RISK_PASS"
    RISK_DENY = "RISK_DENY"
    SUBMIT_STARTED = "SUBMIT_STARTED"
    LOCAL_VALIDATION_FAILED = "LOCAL_VALIDATION_FAILED"
    ACK = "ACK"
    REJECT = "REJECT"
    PARTIAL_FILL = "PARTIAL_FILL"
    FULL_FILL = "FULL_FILL"
    VENUE_EXPIRED = "VENUE_EXPIRED"
    VENUE_CANCEL_CONFIRMED = "VENUE_CANCEL_CONFIRMED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    TIMEOUT = "TIMEOUT"
    DISCONNECT = "DISCONNECT"
    UNPARSEABLE = "UNPARSEABLE"
    RECON_ACK = "RECON_ACK"
    RECON_PARTIAL_FILL = "RECON_PARTIAL_FILL"
    RECON_FULL_FILL = "RECON_FULL_FILL"
    RECON_CANCELED = "RECON_CANCELED"
    RECON_REJECTED = "RECON_REJECTED"
    RECON_EXPIRED = "RECON_EXPIRED"
    RECON_UNRESOLVED = "RECON_UNRESOLVED"


class PositionExecutorState(str, Enum):
    PLANNED = "PLANNED"
    CLOSING_OPPOSITE = "CLOSING_OPPOSITE"
    WAITING_FLAT = "WAITING_FLAT"
    OPENING_OR_ADJUSTING = "OPENING_OR_ADJUSTING"
    VERIFYING = "VERIFYING"
    SATISFIED = "SATISFIED"
    BLOCKED_UNKNOWN = "BLOCKED_UNKNOWN"
    ABORTED_BY_RISK = "ABORTED_BY_RISK"
    EXPIRED = "EXPIRED"
    FAILED_PRE_SUBMIT = "FAILED_PRE_SUBMIT"


_TERMINAL_ORDER_STATES = {
    OrderState.RISK_DENIED,
    OrderState.FILLED,
    OrderState.CANCELED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
    OrderState.FAILED_PRE_SUBMIT,
}
_MAY_HAVE_LEFT_PROCESS = {
    OrderState.SUBMITTING,
    OrderState.ACKNOWLEDGED,
    OrderState.PARTIALLY_FILLED,
    OrderState.CANCEL_PENDING,
}
_UNCERTAIN_EVENTS = {
    OrderEventType.TIMEOUT,
    OrderEventType.DISCONNECT,
    OrderEventType.UNPARSEABLE,
}
_RECON_EVENTS = {
    OrderEventType.RECON_ACK,
    OrderEventType.RECON_PARTIAL_FILL,
    OrderEventType.RECON_FULL_FILL,
    OrderEventType.RECON_CANCELED,
    OrderEventType.RECON_REJECTED,
    OrderEventType.RECON_EXPIRED,
    OrderEventType.RECON_UNRESOLVED,
}
_FILL_EVENTS = {
    OrderEventType.PARTIAL_FILL,
    OrderEventType.FULL_FILL,
    OrderEventType.RECON_PARTIAL_FILL,
    OrderEventType.RECON_FULL_FILL,
}


@dataclass(frozen=True)
class OrderTransition:
    previous_state: OrderState
    new_state: OrderState
    cumulative_filled_quantity: Decimal
    remaining_quantity: Decimal
    duplicate: bool
    risk_lock_required: bool


class OrderAggregate:
    """Normalize REST/WS events while preserving fill-first economic truth."""

    def __init__(
        self,
        *,
        local_order_id: str,
        attempt_id: str,
        client_order_id: str,
        requested_quantity: Decimal,
    ) -> None:
        quantity = as_decimal(requested_quantity)
        if quantity <= 0:
            raise ContractError("requested order quantity must be positive")
        self.local_order_id = local_order_id
        self.attempt_id = attempt_id
        self.client_order_id = client_order_id
        self.requested_quantity = quantity
        self.state = OrderState.CREATED
        self.cumulative_filled_quantity = Decimal("0")
        self._state_before_unknown: Optional[OrderState] = None
        self._processed_events: Dict[str, str] = {}
        self.reconciliation_result_ids: Tuple[str, ...] = ()

    @property
    def remaining_quantity(self) -> Decimal:
        return self.requested_quantity - self.cumulative_filled_quantity

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_ORDER_STATES

    @property
    def unknown(self) -> bool:
        return self.state is OrderState.UNKNOWN

    def _record_event(
        self,
        *,
        event_id: str,
        event_type: OrderEventType,
        cumulative_filled_quantity: Optional[Decimal],
        reconciliation_result_id: Optional[str],
        fill_precedes_cancel_effective: bool,
        cancel_still_pending: bool,
    ) -> bool:
        event_hash = business_hash(
            {
                "event_id": event_id,
                "event_type": event_type.value,
                "cumulative_filled_quantity": (
                    None
                    if cumulative_filled_quantity is None
                    else str(cumulative_filled_quantity)
                ),
                "reconciliation_result_id": reconciliation_result_id,
                "fill_precedes_cancel_effective": fill_precedes_cancel_effective,
                "cancel_still_pending": cancel_still_pending,
            }
        )
        existing = self._processed_events.get(event_id)
        if existing is not None:
            if existing != event_hash:
                raise ContractError("order event_id reused with different content")
            return True
        self._processed_events[event_id] = event_hash
        return False

    def _apply_fill(
        self,
        event_type: OrderEventType,
        cumulative: Optional[Decimal],
    ) -> None:
        if cumulative is None:
            raise ContractError("fill event requires cumulative filled quantity")
        parsed = as_decimal(cumulative)
        if parsed < self.cumulative_filled_quantity:
            raise ContractError("cumulative fill quantity cannot decrease")
        if parsed > self.requested_quantity:
            raise ContractError("cumulative fill quantity cannot exceed requested quantity")
        if event_type in (
            OrderEventType.PARTIAL_FILL,
            OrderEventType.RECON_PARTIAL_FILL,
        ) and parsed >= self.requested_quantity:
            raise ContractError("PARTIAL_FILL must remain below requested quantity")
        if event_type in (
            OrderEventType.FULL_FILL,
            OrderEventType.RECON_FULL_FILL,
        ) and parsed != self.requested_quantity:
            raise ContractError("FULL_FILL must equal requested quantity")
        self.cumulative_filled_quantity = parsed

    def apply(
        self,
        *,
        event_id: str,
        event_type: OrderEventType,
        cumulative_filled_quantity: Optional[Decimal] = None,
        reconciliation_result_id: Optional[str] = None,
        fill_precedes_cancel_effective: bool = False,
        cancel_still_pending: bool = False,
    ) -> OrderTransition:
        snapshot = (
            self.state,
            self.cumulative_filled_quantity,
            self._state_before_unknown,
            dict(self._processed_events),
            self.reconciliation_result_ids,
        )
        try:
            return self._apply_unchecked(
                event_id=event_id,
                event_type=event_type,
                cumulative_filled_quantity=cumulative_filled_quantity,
                reconciliation_result_id=reconciliation_result_id,
                fill_precedes_cancel_effective=fill_precedes_cancel_effective,
                cancel_still_pending=cancel_still_pending,
            )
        except Exception:
            (
                self.state,
                self.cumulative_filled_quantity,
                self._state_before_unknown,
                self._processed_events,
                self.reconciliation_result_ids,
            ) = snapshot
            raise

    def _apply_unchecked(
        self,
        *,
        event_id: str,
        event_type: OrderEventType,
        cumulative_filled_quantity: Optional[Decimal] = None,
        reconciliation_result_id: Optional[str] = None,
        fill_precedes_cancel_effective: bool = False,
        cancel_still_pending: bool = False,
    ) -> OrderTransition:
        previous = self.state
        parsed_fill = (
            None
            if cumulative_filled_quantity is None
            else as_decimal(cumulative_filled_quantity)
        )
        duplicate = self._record_event(
            event_id=event_id,
            event_type=event_type,
            cumulative_filled_quantity=parsed_fill,
            reconciliation_result_id=reconciliation_result_id,
            fill_precedes_cancel_effective=fill_precedes_cancel_effective,
            cancel_still_pending=cancel_still_pending,
        )
        if duplicate:
            return self._transition(previous, duplicate=True)

        if event_type in _RECON_EVENTS:
            if self.state is not OrderState.UNKNOWN:
                raise ContractError("reconciliation transition requires UNKNOWN state")
            if not reconciliation_result_id:
                raise ContractError("UNKNOWN resolution requires ReconciliationResult evidence")
            self.reconciliation_result_ids += (reconciliation_result_id,)
        elif reconciliation_result_id is not None:
            raise ContractError("reconciliation evidence is only valid for RECON events")

        if self.state is OrderState.FILLED:
            if parsed_fill is not None and parsed_fill != self.requested_quantity:
                raise ContractError("late event conflicts with FILLED quantity")
            return self._transition(previous)

        if self.state is OrderState.CANCELED and event_type in (
            OrderEventType.PARTIAL_FILL,
            OrderEventType.FULL_FILL,
        ):
            if not fill_precedes_cancel_effective:
                raise ContractError("late fill after CANCELED requires exchange-time evidence")
            self._apply_fill(event_type, parsed_fill)
            if self.cumulative_filled_quantity == self.requested_quantity:
                self.state = OrderState.FILLED
            return self._transition(previous)

        if event_type in _FILL_EVENTS:
            self._apply_fill(event_type, parsed_fill)

        if event_type in _UNCERTAIN_EVENTS:
            if self.state not in _MAY_HAVE_LEFT_PROCESS:
                raise ContractError("only a possibly external request may enter UNKNOWN")
            self._state_before_unknown = self.state
            self.state = OrderState.UNKNOWN
            return self._transition(previous, risk_lock_required=True)

        if self.state is OrderState.UNKNOWN:
            mapping = {
                OrderEventType.RECON_ACK: OrderState.ACKNOWLEDGED,
                OrderEventType.RECON_FULL_FILL: OrderState.FILLED,
                OrderEventType.RECON_CANCELED: OrderState.CANCELED,
                OrderEventType.RECON_REJECTED: OrderState.REJECTED,
                OrderEventType.RECON_EXPIRED: OrderState.EXPIRED,
                OrderEventType.RECON_UNRESOLVED: OrderState.UNKNOWN,
            }
            if event_type is OrderEventType.RECON_PARTIAL_FILL:
                self.state = (
                    OrderState.CANCEL_PENDING
                    if cancel_still_pending
                    or self._state_before_unknown is OrderState.CANCEL_PENDING
                    else OrderState.PARTIALLY_FILLED
                )
            elif event_type in mapping:
                self.state = mapping[event_type]
            else:
                raise ContractError("UNKNOWN can only transition through reconciliation")
            return self._transition(
                previous,
                risk_lock_required=self.state is OrderState.UNKNOWN,
            )

        transitions = {
            (OrderState.CREATED, OrderEventType.RISK_PASS): OrderState.RISK_APPROVED,
            (OrderState.CREATED, OrderEventType.RISK_DENY): OrderState.RISK_DENIED,
            (
                OrderState.RISK_APPROVED,
                OrderEventType.SUBMIT_STARTED,
            ): OrderState.SUBMITTING,
            (
                OrderState.RISK_APPROVED,
                OrderEventType.LOCAL_VALIDATION_FAILED,
            ): OrderState.FAILED_PRE_SUBMIT,
            (OrderState.SUBMITTING, OrderEventType.ACK): OrderState.ACKNOWLEDGED,
            (OrderState.SUBMITTING, OrderEventType.REJECT): OrderState.REJECTED,
            (
                OrderState.SUBMITTING,
                OrderEventType.PARTIAL_FILL,
            ): OrderState.PARTIALLY_FILLED,
            (OrderState.SUBMITTING, OrderEventType.FULL_FILL): OrderState.FILLED,
            (
                OrderState.ACKNOWLEDGED,
                OrderEventType.PARTIAL_FILL,
            ): OrderState.PARTIALLY_FILLED,
            (OrderState.ACKNOWLEDGED, OrderEventType.FULL_FILL): OrderState.FILLED,
            (
                OrderState.PARTIALLY_FILLED,
                OrderEventType.PARTIAL_FILL,
            ): OrderState.PARTIALLY_FILLED,
            (
                OrderState.PARTIALLY_FILLED,
                OrderEventType.FULL_FILL,
            ): OrderState.FILLED,
            (
                OrderState.ACKNOWLEDGED,
                OrderEventType.CANCEL_REQUESTED,
            ): OrderState.CANCEL_PENDING,
            (
                OrderState.PARTIALLY_FILLED,
                OrderEventType.CANCEL_REQUESTED,
            ): OrderState.CANCEL_PENDING,
            (
                OrderState.ACKNOWLEDGED,
                OrderEventType.VENUE_EXPIRED,
            ): OrderState.EXPIRED,
            (
                OrderState.PARTIALLY_FILLED,
                OrderEventType.VENUE_EXPIRED,
            ): OrderState.EXPIRED,
            (
                OrderState.ACKNOWLEDGED,
                OrderEventType.VENUE_CANCEL_CONFIRMED,
            ): OrderState.CANCELED,
            (
                OrderState.PARTIALLY_FILLED,
                OrderEventType.VENUE_CANCEL_CONFIRMED,
            ): OrderState.CANCELED,
            (
                OrderState.CANCEL_PENDING,
                OrderEventType.PARTIAL_FILL,
            ): OrderState.CANCEL_PENDING,
            (
                OrderState.CANCEL_PENDING,
                OrderEventType.FULL_FILL,
            ): OrderState.FILLED,
            (
                OrderState.CANCEL_PENDING,
                OrderEventType.CANCEL_CONFIRMED,
            ): OrderState.CANCELED,
        }
        if (
            self.state is OrderState.PARTIALLY_FILLED
            and event_type is OrderEventType.ACK
        ):
            return self._transition(previous)
        new_state = transitions.get((self.state, event_type))
        if new_state is None:
            raise ContractError(f"invalid order transition: {self.state} + {event_type}")
        self.state = new_state
        return self._transition(previous)

    def _transition(
        self,
        previous: OrderState,
        *,
        duplicate: bool = False,
        risk_lock_required: bool = False,
    ) -> OrderTransition:
        return OrderTransition(
            previous_state=previous,
            new_state=self.state,
            cumulative_filled_quantity=self.cumulative_filled_quantity,
            remaining_quantity=self.remaining_quantity,
            duplicate=duplicate,
            risk_lock_required=risk_lock_required,
        )


@dataclass(frozen=True)
class ExecutorTargetResult:
    acceptance: TargetAcceptance
    state: PositionExecutorState
    cancel_active_attempt_required: bool


class PositionExecutor:
    """One active executor per account and economic instrument."""

    def __init__(
        self,
        *,
        account_id: str,
        economic_asset: str,
        quantity_step: Decimal,
    ) -> None:
        self.account_id = account_id
        self.economic_asset = economic_asset
        self.quantity_step = as_decimal(quantity_step)
        if self.quantity_step <= 0:
            raise ContractError("executor quantity step must be positive")
        self.state = PositionExecutorState.PLANNED
        self.actual_position = Decimal("0")
        self.current_target: Optional[TargetPosition] = None
        self._targets = TargetBook()
        self._unknown_attempt_ids: Set[str] = set()
        self.active_order_state: Optional[OrderState] = None

    def accept_target(
        self,
        *,
        target: TargetPosition,
        now,
    ) -> ExecutorTargetResult:
        if (
            target.account_id != self.account_id
            or target.economic_asset != self.economic_asset
        ):
            raise ContractError("target is outside this executor scope")
        acceptance = self._targets.accept(target)
        if acceptance in (
            TargetAcceptance.DUPLICATE,
            TargetAcceptance.IGNORED_STALE,
        ):
            return ExecutorTargetResult(acceptance, self.state, False)
        self.current_target = target
        if now >= target.valid_until:
            self.state = PositionExecutorState.EXPIRED
            return ExecutorTargetResult(acceptance, self.state, False)
        if self._unknown_attempt_ids:
            self.state = PositionExecutorState.BLOCKED_UNKNOWN
            return ExecutorTargetResult(acceptance, self.state, False)

        cancel_required = (
            self.active_order_state is not None
            and self.active_order_state not in _TERMINAL_ORDER_STATES
        )
        current_direction = (
            Direction.FLAT
            if self.actual_position == 0
            else Direction.SHORT
            if self.actual_position < 0
            else Direction.LONG
        )
        if target.target_action is TargetAction.FLATTEN:
            self.state = (
                PositionExecutorState.SATISFIED
                if current_direction is Direction.FLAT
                else PositionExecutorState.CLOSING_OPPOSITE
            )
        elif (
            current_direction is not Direction.FLAT
            and target.direction is not current_direction
        ):
            self.state = PositionExecutorState.CLOSING_OPPOSITE
        elif target.target_action in (
            TargetAction.NO_DECISION,
            TargetAction.HOLD_CURRENT,
            TargetAction.FREEZE_INCREASES,
        ):
            self.state = PositionExecutorState.SATISFIED
        else:
            self.state = PositionExecutorState.OPENING_OR_ADJUSTING
        return ExecutorTargetResult(acceptance, self.state, cancel_required)

    def on_order_state(self, *, attempt_id: str, order_state: OrderState) -> None:
        self.active_order_state = order_state
        if order_state is OrderState.UNKNOWN:
            self._unknown_attempt_ids.add(attempt_id)
            self.state = PositionExecutorState.BLOCKED_UNKNOWN
        elif attempt_id in self._unknown_attempt_ids:
            self._unknown_attempt_ids.remove(attempt_id)
            if not self._unknown_attempt_ids:
                self.state = PositionExecutorState.VERIFYING

    def update_actual_position(self, quantity: Decimal) -> None:
        self.actual_position = as_decimal(quantity)
        if self.state is PositionExecutorState.CLOSING_OPPOSITE and self.actual_position == 0:
            self.state = PositionExecutorState.WAITING_FLAT

    def confirm_flat_and_continue(self) -> None:
        if self.state is not PositionExecutorState.WAITING_FLAT:
            raise ContractError("executor is not waiting for flat confirmation")
        if self.actual_position != 0:
            raise ContractError("exchange position is not flat")
        if self.current_target is None:
            raise ContractError("executor has no current target")
        if self.current_target.target_action is TargetAction.FLATTEN:
            self.state = PositionExecutorState.SATISFIED
        else:
            self.state = PositionExecutorState.OPENING_OR_ADJUSTING

    def verify_satisfied(self, desired_position: Decimal) -> bool:
        desired = as_decimal(desired_position)
        within_step = abs(self.actual_position - desired) <= self.quantity_step
        self.state = (
            PositionExecutorState.SATISFIED
            if within_step
            else PositionExecutorState.VERIFYING
        )
        return within_step

    def abort_by_risk(self) -> None:
        self.state = PositionExecutorState.ABORTED_BY_RISK

    def fail_pre_submit(self) -> None:
        self.state = PositionExecutorState.FAILED_PRE_SUBMIT
