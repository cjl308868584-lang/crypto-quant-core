import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from factories import NOW, make_meta, make_proposal, make_target

from crypto_quant.contracts import Direction
from crypto_quant.errors import ContractError
from crypto_quant.orders import (
    OrderAggregate,
    OrderEventType,
    OrderState,
    PositionExecutor,
    PositionExecutorState,
)


def submitted_order():
    order = OrderAggregate(
        local_order_id="local-1",
        attempt_id="attempt-1",
        client_order_id="client-1",
        requested_quantity=Decimal("0.01"),
    )
    order.apply(event_id="risk", event_type=OrderEventType.RISK_PASS)
    order.apply(event_id="submit", event_type=OrderEventType.SUBMIT_STARTED)
    return order


class OrderStateMachineTests(unittest.TestCase):
    def test_fill_before_ack_and_late_ack_preserve_economic_state(self) -> None:
        order = submitted_order()
        partial = order.apply(
            event_id="fill-1",
            event_type=OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.004"),
        )
        self.assertEqual(partial.new_state, OrderState.PARTIALLY_FILLED)
        late_ack = order.apply(event_id="ack-late", event_type=OrderEventType.ACK)
        self.assertEqual(late_ack.new_state, OrderState.PARTIALLY_FILLED)
        full = order.apply(
            event_id="fill-2",
            event_type=OrderEventType.FULL_FILL,
            cumulative_filled_quantity=Decimal("0.01"),
        )
        self.assertEqual(full.new_state, OrderState.FILLED)
        self.assertEqual(full.remaining_quantity, Decimal("0"))

    def test_cancel_fill_race_keeps_fills_and_can_promote_to_filled(self) -> None:
        order = submitted_order()
        order.apply(event_id="ack", event_type=OrderEventType.ACK)
        order.apply(
            event_id="fill-1",
            event_type=OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.003"),
        )
        order.apply(
            event_id="cancel-request",
            event_type=OrderEventType.CANCEL_REQUESTED,
        )
        during_cancel = order.apply(
            event_id="fill-2",
            event_type=OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.004"),
        )
        self.assertEqual(during_cancel.new_state, OrderState.CANCEL_PENDING)
        canceled = order.apply(
            event_id="cancel-confirm",
            event_type=OrderEventType.CANCEL_CONFIRMED,
        )
        self.assertEqual(canceled.new_state, OrderState.CANCELED)
        late = order.apply(
            event_id="late-fill",
            event_type=OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.006"),
            fill_precedes_cancel_effective=True,
        )
        self.assertEqual(late.new_state, OrderState.CANCELED)
        promoted = order.apply(
            event_id="late-full",
            event_type=OrderEventType.FULL_FILL,
            cumulative_filled_quantity=Decimal("0.01"),
            fill_precedes_cancel_effective=True,
        )
        self.assertEqual(promoted.new_state, OrderState.FILLED)

    def test_timeout_enters_unknown_and_reconciliation_is_mandatory(self) -> None:
        order = submitted_order()
        unknown = order.apply(
            event_id="timeout",
            event_type=OrderEventType.TIMEOUT,
        )
        self.assertEqual(unknown.new_state, OrderState.UNKNOWN)
        self.assertTrue(unknown.risk_lock_required)
        with self.assertRaises(ContractError):
            order.apply(
                event_id="blind-ack",
                event_type=OrderEventType.RECON_ACK,
            )
        unresolved = order.apply(
            event_id="recon-1",
            event_type=OrderEventType.RECON_UNRESOLVED,
            reconciliation_result_id="reconciliation-1",
        )
        self.assertEqual(unresolved.new_state, OrderState.UNKNOWN)
        self.assertTrue(unresolved.risk_lock_required)
        resolved = order.apply(
            event_id="recon-2",
            event_type=OrderEventType.RECON_ACK,
            reconciliation_result_id="reconciliation-2",
        )
        self.assertEqual(resolved.new_state, OrderState.ACKNOWLEDGED)

    def test_unknown_resolves_to_each_exchange_terminal_or_partial_state(self) -> None:
        cases = (
            (OrderEventType.RECON_ACK, None, OrderState.ACKNOWLEDGED),
            (
                OrderEventType.RECON_PARTIAL_FILL,
                Decimal("0.004"),
                OrderState.PARTIALLY_FILLED,
            ),
            (OrderEventType.RECON_FULL_FILL, Decimal("0.01"), OrderState.FILLED),
            (OrderEventType.RECON_CANCELED, None, OrderState.CANCELED),
            (OrderEventType.RECON_REJECTED, None, OrderState.REJECTED),
            (OrderEventType.RECON_EXPIRED, None, OrderState.EXPIRED),
        )
        for index, (event_type, cumulative, expected) in enumerate(cases):
            with self.subTest(event_type=event_type):
                order = submitted_order()
                order.apply(
                    event_id=f"timeout-{index}",
                    event_type=OrderEventType.TIMEOUT,
                )
                transition = order.apply(
                    event_id=f"recon-{index}",
                    event_type=event_type,
                    cumulative_filled_quantity=cumulative,
                    reconciliation_result_id=f"result-{index}",
                )
                self.assertEqual(transition.new_state, expected)

    def test_unknown_from_cancel_pending_returns_to_cancel_pending(self) -> None:
        order = submitted_order()
        order.apply(event_id="ack", event_type=OrderEventType.ACK)
        order.apply(
            event_id="cancel-request",
            event_type=OrderEventType.CANCEL_REQUESTED,
        )
        order.apply(event_id="timeout", event_type=OrderEventType.TIMEOUT)
        reconciled = order.apply(
            event_id="recon",
            event_type=OrderEventType.RECON_PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.002"),
            reconciliation_result_id="result-1",
        )
        self.assertEqual(reconciled.new_state, OrderState.CANCEL_PENDING)

    def test_duplicate_events_are_idempotent_and_conflicts_fail(self) -> None:
        order = OrderAggregate(
            local_order_id="local-1",
            attempt_id="attempt-1",
            client_order_id="client-1",
            requested_quantity=Decimal("0.01"),
        )
        first = order.apply(event_id="risk", event_type=OrderEventType.RISK_PASS)
        duplicate = order.apply(event_id="risk", event_type=OrderEventType.RISK_PASS)
        self.assertFalse(first.duplicate)
        self.assertTrue(duplicate.duplicate)
        with self.assertRaises(ContractError):
            order.apply(event_id="risk", event_type=OrderEventType.RISK_DENY)

    def test_invalid_event_does_not_poison_its_idempotency_key(self) -> None:
        order = OrderAggregate(
            local_order_id="local-1",
            attempt_id="attempt-1",
            client_order_id="client-1",
            requested_quantity=Decimal("0.01"),
        )
        with self.assertRaises(ContractError):
            order.apply(event_id="event-1", event_type=OrderEventType.ACK)
        accepted = order.apply(
            event_id="event-1",
            event_type=OrderEventType.RISK_PASS,
        )
        self.assertEqual(accepted.new_state, OrderState.RISK_APPROVED)

    def test_fill_quantity_is_monotonic_and_bounded(self) -> None:
        order = submitted_order()
        order.apply(
            event_id="fill-1",
            event_type=OrderEventType.PARTIAL_FILL,
            cumulative_filled_quantity=Decimal("0.005"),
        )
        with self.assertRaises(ContractError):
            order.apply(
                event_id="fill-backward",
                event_type=OrderEventType.PARTIAL_FILL,
                cumulative_filled_quantity=Decimal("0.004"),
            )
        with self.assertRaises(ContractError):
            order.apply(
                event_id="fill-too-large",
                event_type=OrderEventType.FULL_FILL,
                cumulative_filled_quantity=Decimal("0.02"),
            )


class PositionExecutorTests(unittest.TestCase):
    def test_new_target_supersedes_and_unknown_blocks_replanning(self) -> None:
        proposal = make_proposal()
        meta = make_meta(proposal)
        first = make_target(proposal, meta)
        executor = PositionExecutor(
            account_id="account-1",
            economic_asset="ETH",
            quantity_step=Decimal("0.001"),
        )
        initial = executor.accept_target(target=first, now=NOW)
        self.assertEqual(initial.state, PositionExecutorState.OPENING_OR_ADJUSTING)
        executor.on_order_state(
            attempt_id="attempt-1",
            order_state=OrderState.ACKNOWLEDGED,
        )
        second = replace(
            first,
            target_sequence=2,
            supersedes_target_id_or_null=first.target_id,
        )
        superseded = executor.accept_target(target=second, now=NOW)
        self.assertTrue(superseded.cancel_active_attempt_required)
        executor.on_order_state(
            attempt_id="attempt-1",
            order_state=OrderState.UNKNOWN,
        )
        third = replace(
            second,
            target_sequence=3,
            supersedes_target_id_or_null=second.target_id,
        )
        blocked = executor.accept_target(target=third, now=NOW)
        self.assertEqual(blocked.state, PositionExecutorState.BLOCKED_UNKNOWN)
        executor.on_order_state(
            attempt_id="attempt-1",
            order_state=OrderState.CANCELED,
        )
        self.assertEqual(executor.state, PositionExecutorState.VERIFYING)

    def test_direction_reversal_waits_for_exchange_confirmed_flat(self) -> None:
        long_proposal = make_proposal()
        long_meta = make_meta(long_proposal)
        long_target = make_target(long_proposal, long_meta)
        executor = PositionExecutor(
            account_id="account-1",
            economic_asset="ETH",
            quantity_step=Decimal("0.001"),
        )
        executor.actual_position = Decimal("0.01")
        executor.accept_target(target=long_target, now=NOW)

        short_proposal = make_proposal(
            direction=Direction.SHORT,
            instrument_id="BINANCE:USDT_PERP:ETHUSDT",
        )
        short_meta = make_meta(short_proposal)
        short_target = make_target(
            short_proposal,
            short_meta,
            sequence=2,
            supersedes=long_target.target_id,
        )
        result = executor.accept_target(target=short_target, now=NOW)
        self.assertEqual(result.state, PositionExecutorState.CLOSING_OPPOSITE)
        with self.assertRaises(ContractError):
            executor.confirm_flat_and_continue()
        executor.update_actual_position(Decimal("0"))
        self.assertEqual(executor.state, PositionExecutorState.WAITING_FLAT)
        executor.confirm_flat_and_continue()
        self.assertEqual(
            executor.state,
            PositionExecutorState.OPENING_OR_ADJUSTING,
        )

    def test_expired_target_cannot_start_new_attempt(self) -> None:
        proposal = make_proposal()
        meta = make_meta(proposal)
        target = make_target(proposal, meta)
        executor = PositionExecutor(
            account_id="account-1",
            economic_asset="ETH",
            quantity_step=Decimal("0.001"),
        )
        result = executor.accept_target(
            target=target,
            now=NOW + timedelta(hours=25),
        )
        self.assertEqual(result.state, PositionExecutorState.EXPIRED)
        self.assertFalse(result.cancel_active_attempt_required)


if __name__ == "__main__":
    unittest.main()
