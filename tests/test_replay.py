import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from crypto_quant.contracts import EventEnvelope
from crypto_quant.errors import LedgerConflictError, LedgerIntegrityError
from crypto_quant.ledger import EventLedger

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH_A = "a" * 64
GOLDEN_PROJECTION_HASH = (
    "eeeb20f66a72bb148146732ece4d724172b2db20d758ee6cb5235b89dfd511b0"
)


def make_envelope(payload, event_id):
    return EventEnvelope.create(
        schema_version="1.1.0",
        event_id=event_id,
        trace_id="trace-execution-1",
        correlation_id="decision-1",
        causation_id=None,
        run_id="replay-golden-1",
        event_time=NOW,
        available_at=NOW,
        ingested_at=NOW,
        recorded_at=NOW,
        source="REPLAY",
        payload=payload,
    )


def execution_facts():
    return (
        (
            "ExecutionIntentStateRecorded",
            "intent-state-1",
            {
                "intent_id": "intent-1",
                "entity_version": 1,
                "state": "ACTIVE",
                "risk_decision_id": "risk-1",
                "target_id": "target-1",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "intent_hash": HASH_A,
            },
        ),
        (
            "ChildOrderAttemptStateRecorded",
            "attempt-state-1",
            {
                "attempt_id": "attempt-1",
                "entity_version": 1,
                "state": "ACTIVE",
                "intent_id": "intent-1",
                "attempt_no": 1,
                "client_order_id": "cq-order-1",
                "attempt_hash": HASH_A,
            },
        ),
        (
            "OrderStateRecorded",
            "order-state-2",
            {
                "order_id": "order-1",
                "entity_version": 2,
                "state": "UNKNOWN",
                "attempt_id": "attempt-1",
                "intent_id": "intent-1",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "client_order_id": "cq-order-1",
                "requested_quantity": Decimal("0.01"),
                "cumulative_filled_quantity": Decimal("0.004"),
            },
        ),
        (
            "OrderStateRecorded",
            "order-state-1-late",
            {
                "order_id": "order-1",
                "entity_version": 1,
                "state": "SUBMITTING",
                "attempt_id": "attempt-1",
                "intent_id": "intent-1",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "client_order_id": "cq-order-1",
                "requested_quantity": Decimal("0.01"),
                "cumulative_filled_quantity": Decimal("0"),
            },
        ),
        (
            "PositionStateRecorded",
            "position-state-1",
            {
                "position_id": "account-1:BINANCE:SPOT:ETHUSDT",
                "entity_version": 1,
                "state": "OBSERVED",
                "account_id": "account-1",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "signed_quantity": Decimal("0.004"),
                "instrument_metadata_hash": HASH_A,
            },
        ),
        (
            "RiskLockStateRecorded",
            "risk-lock-state-1",
            {
                "lock_id": "lock-1",
                "entity_version": 1,
                "state": "ACTIVE",
                "lock_type": "ORDER_UNKNOWN",
                "scope": "ACCOUNT",
                "scope_id": "account-1",
            },
        ),
        (
            "DeploymentStateRecorded",
            "deployment-state-1",
            {
                "deployment_line_id": "line-1",
                "entity_version": 1,
                "state": "ACTIVE",
                "stage": "CANARY_25",
                "authoritative_stage_multiplier": Decimal("0.25"),
                "record_hash": HASH_A,
            },
        ),
        (
            "PositionExecutorStateRecorded",
            "executor-state-2",
            {
                "executor_id": "account-1:ETH",
                "entity_version": 2,
                "state": "BLOCKED_UNKNOWN",
                "account_id": "account-1",
                "economic_asset": "ETH",
                "current_target_id_or_null": "target-1",
                "active_intent_id_or_null": "intent-1",
            },
        ),
        (
            "PositionExecutorStateRecorded",
            "executor-state-1-late",
            {
                "executor_id": "account-1:ETH",
                "entity_version": 1,
                "state": "OPENING_OR_ADJUSTING",
                "account_id": "account-1",
                "economic_asset": "ETH",
                "current_target_id_or_null": "target-1",
                "active_intent_id_or_null": "intent-1",
            },
        ),
        (
            "BalanceStateRecorded",
            "balance-state-1",
            {
                "balance_id": "account-1:USDT",
                "entity_version": 1,
                "state": "OBSERVED",
                "account_id": "account-1",
                "asset": "USDT",
                "total_balance": Decimal("500"),
                "available_balance": Decimal("480"),
                "locked_balance": Decimal("20"),
                "borrowed_balance": Decimal("0"),
                "interest_accrued": Decimal("0"),
                "exchange_snapshot_time": "2026-01-01T00:00:00.000Z",
                "source_snapshot_hash": HASH_A,
            },
        ),
        (
            "ProtectiveOrderStateRecorded",
            "protective-state-1",
            {
                "protective_order_id": "protective-1",
                "entity_version": 1,
                "state": "ACTIVE",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "position_id": "account-1:BINANCE:SPOT:ETHUSDT",
                "risk_decision_id": "risk-1",
                "execution_intent_id": "intent-1",
                "attempt_id": "attempt-1",
                "local_order_id": "order-protective-1",
                "role": "DISASTER_STOP",
                "side": "SELL",
                "trigger_price": Decimal("1600"),
                "limit_price_or_null": None,
                "covered_quantity": Decimal("0.004"),
                "reduce_only_or_spot_sell": "SPOT_SELL",
                "venue_order_id_or_null": "venue-protective-1",
                "replacement_of_or_null": None,
                "unprotected_window_started_at_or_null": None,
                "replacement_deadline_at_or_null": None,
                "effective_at_or_null": "2026-01-01T00:00:00.000Z",
                "risk_policy_id": "release-gates-v1.1#risk_thresholds",
                "risk_policy_hash": HASH_A,
                "policy_version": "1.1.2",
            },
        ),
        (
            "FillRecorded",
            "fill-event-1",
            {
                "fill_id": "fill-1",
                "account_id": "account-1",
                "market_scope": "BINANCE:SPOT",
                "exchange_trade_id": "trade-1",
                "local_order_id": "order-1",
                "venue_order_id": "venue-order-1",
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "side": "BUY",
                "quantity": Decimal("0.004"),
                "price": Decimal("1800"),
                "decision_reference_price": Decimal("1799"),
                "liquidity_role": "TAKER",
                "fee_amount": Decimal("0.000004"),
                "fee_asset": "ETH",
                "fee_value_usdt": Decimal("0.0072"),
                "fee_fx_rate_id_or_null": "fx-eth-usdt-1",
                "implementation_shortfall_usdt": Decimal("0.004"),
                "exchange_event_time": "2026-01-01T00:00:00.000Z",
                "raw_payload_hash": HASH_A,
            },
        ),
    )


class ReplayGoldenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "replay.sqlite"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def append_facts(self, ledger):
        for event_type, event_id, payload in execution_facts():
            ledger.append(
                event_type,
                make_envelope(payload, event_id),
                payload,
            )
        covered = ledger.connection.execute(
            """
            SELECT sequence, ledger_hash
            FROM events ORDER BY sequence DESC LIMIT 1
            """
        ).fetchone()
        checkpoint = {
            "checkpoint_id": "checkpoint-1",
            "covered_event_sequence": covered["sequence"],
            "covered_ledger_hash": covered["ledger_hash"],
            "covered_projection_hash": ledger.state_projection_hash(),
            "code_commit": "GOLDEN_TEST_COMMIT",
            "policy_bundle_hash": HASH_A,
            "created_at": "2026-01-01T00:00:00.000Z",
        }
        ledger.append(
            "CheckpointRecorded",
            make_envelope(checkpoint, "checkpoint-event-1"),
            checkpoint,
        )

    def test_complete_execution_projection_rebuild_matches_golden_hash(self) -> None:
        with EventLedger(self.path) as ledger:
            self.append_facts(ledger)
            event_type, event_id, payload = execution_facts()[2]
            duplicate = ledger.append(
                event_type,
                make_envelope(payload, event_id),
                payload,
            )
            self.assertFalse(duplicate.inserted)
            live_snapshot = ledger.projection_snapshot()
            live_hash = ledger.projection_hash()
            self.assertEqual(live_hash, GOLDEN_PROJECTION_HASH)
            self.assertEqual(
                live_snapshot["orders_projection"][0]["state"],
                "UNKNOWN",
            )
            self.assertEqual(
                live_snapshot["position_executors_projection"][0]["state"],
                "BLOCKED_UNKNOWN",
            )
            self.assertEqual(
                len(
                    [
                        table
                        for table, rows in live_snapshot.items()
                        if table.endswith("_projection") and rows
                    ]
                ),
                10,
            )
            self.assertEqual(len(live_snapshot["checkpoints"]), 1)
            ledger.rebuild_projections()
            self.assertEqual(ledger.projection_snapshot(), live_snapshot)
            self.assertEqual(ledger.projection_hash(), live_hash)
            end_hash = ledger.verify_integrity()

        with EventLedger(self.path) as reopened:
            self.assertEqual(reopened.verify_integrity(), end_hash)
            self.assertEqual(reopened.projection_hash(), GOLDEN_PROJECTION_HASH)
            reopened.rebuild_projections()
            self.assertEqual(reopened.projection_hash(), GOLDEN_PROJECTION_HASH)

    def test_same_entity_version_conflict_rolls_back_event(self) -> None:
        with EventLedger(self.path) as ledger:
            event_type, event_id, payload = execution_facts()[2]
            ledger.append(
                event_type,
                make_envelope(payload, event_id),
                payload,
            )
            conflicting = dict(payload)
            conflicting["state"] = "FILLED"
            conflicting["cumulative_filled_quantity"] = Decimal("0.01")
            with self.assertRaises(LedgerConflictError):
                ledger.append(
                    event_type,
                    make_envelope(conflicting, "order-state-2-conflict"),
                    conflicting,
                )
            count = ledger.connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            self.assertEqual(count, 1)
            self.assertEqual(
                ledger.projection_snapshot()["orders_projection"][0]["state"],
                "UNKNOWN",
            )

    def test_invalid_projection_fact_is_not_committed(self) -> None:
        invalid = {
            "order_id": "order-1",
            "entity_version": 1,
            "state": "PARTIALLY_FILLED",
            "attempt_id": "attempt-1",
            "intent_id": "intent-1",
            "instrument_id": "BINANCE:SPOT:ETHUSDT",
            "client_order_id": "cq-order-1",
            "requested_quantity": Decimal("0.01"),
            "cumulative_filled_quantity": Decimal("0.02"),
        }
        with EventLedger(self.path) as ledger:
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "OrderStateRecorded",
                    make_envelope(invalid, "invalid-order-fact"),
                    invalid,
                )
            count = ledger.connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            self.assertEqual(count, 0)
            self.assertEqual(
                ledger.projection_snapshot()["orders_projection"],
                [],
            )

    def test_projection_tampering_is_detected_and_rebuild_repairs_it(self) -> None:
        with EventLedger(self.path) as ledger:
            self.append_facts(ledger)
            expected = ledger.projection_hash()
            ledger.connection.execute(
                """
                UPDATE orders_projection
                SET state = 'FILLED'
                WHERE entity_id = 'order-1'
                """
            )
            ledger.connection.commit()
            with self.assertRaises(LedgerIntegrityError):
                ledger.verify_projection_integrity()
            with self.assertRaises(LedgerIntegrityError):
                ledger.projection_hash()
            ledger.rebuild_projections()
            ledger.verify_projection_integrity()
            self.assertEqual(ledger.projection_hash(), expected)

    def test_exchange_trade_id_is_exactly_once_and_conflicts_roll_back(self) -> None:
        event_type, event_id, fill = execution_facts()[-1]
        with EventLedger(self.path) as ledger:
            ledger.append(
                event_type,
                make_envelope(fill, event_id),
                fill,
            )
            duplicate = ledger.append(
                event_type,
                make_envelope(fill, "fill-event-duplicate"),
                fill,
            )
            self.assertTrue(duplicate.inserted)
            self.assertEqual(
                len(ledger.projection_snapshot()["fills_projection"]),
                1,
            )
            conflict = dict(fill)
            conflict["quantity"] = Decimal("0.005")
            with self.assertRaises(LedgerConflictError):
                ledger.append(
                    event_type,
                    make_envelope(conflict, "fill-event-conflict"),
                    conflict,
                )
            event_count = ledger.connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            self.assertEqual(event_count, 2)

    def test_balance_protection_and_checkpoint_invariants_fail_closed(self) -> None:
        facts = {
            event_type: (event_id, payload)
            for event_type, event_id, payload in execution_facts()
        }
        with EventLedger(self.path) as ledger:
            balance_id, balance = facts["BalanceStateRecorded"]
            invalid_balance = dict(balance)
            invalid_balance["available_balance"] = Decimal("600")
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "BalanceStateRecorded",
                    make_envelope(invalid_balance, balance_id),
                    invalid_balance,
                )

            protective_id, protective = facts["ProtectiveOrderStateRecorded"]
            invalid_protective = dict(protective)
            invalid_protective["unprotected_window_started_at_or_null"] = (
                "2026-01-01T00:00:00.000Z"
            )
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "ProtectiveOrderStateRecorded",
                    make_envelope(invalid_protective, protective_id),
                    invalid_protective,
                )

            intent_type, intent_id, intent = execution_facts()[0]
            ledger.append(
                intent_type,
                make_envelope(intent, intent_id),
                intent,
            )
            covered = ledger.connection.execute(
                """
                SELECT sequence, ledger_hash
                FROM events ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            bad_checkpoint = {
                "checkpoint_id": "checkpoint-bad",
                "covered_event_sequence": covered["sequence"],
                "covered_ledger_hash": covered["ledger_hash"],
                "covered_projection_hash": HASH_A,
                "code_commit": "GOLDEN_TEST_COMMIT",
                "policy_bundle_hash": HASH_A,
                "created_at": "2026-01-01T00:00:00.000Z",
            }
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "CheckpointRecorded",
                    make_envelope(bad_checkpoint, "checkpoint-event-bad"),
                    bad_checkpoint,
                )
            event_count = ledger.connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            self.assertEqual(event_count, 1)

    def test_checkpoint_refuses_unreconciled_order_and_fill_totals(self) -> None:
        event_type, event_id, order = execution_facts()[2]
        with EventLedger(self.path) as ledger:
            ledger.append(
                event_type,
                make_envelope(order, event_id),
                order,
            )
            covered = ledger.connection.execute(
                """
                SELECT sequence, ledger_hash
                FROM events ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            checkpoint = {
                "checkpoint_id": "checkpoint-unreconciled",
                "covered_event_sequence": covered["sequence"],
                "covered_ledger_hash": covered["ledger_hash"],
                "covered_projection_hash": ledger.state_projection_hash(),
                "code_commit": "GOLDEN_TEST_COMMIT",
                "policy_bundle_hash": HASH_A,
                "created_at": "2026-01-01T00:00:00.000Z",
            }
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "CheckpointRecorded",
                    make_envelope(
                        checkpoint,
                        "checkpoint-event-unreconciled",
                    ),
                    checkpoint,
                )
            event_count = ledger.connection.execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            self.assertEqual(event_count, 1)

    def test_checkpoint_refuses_undercovered_actual_position(self) -> None:
        facts = {
            event_type: (event_id, payload)
            for event_type, event_id, payload in execution_facts()
        }
        position_id, position = facts["PositionStateRecorded"]
        protective_id, protective = facts["ProtectiveOrderStateRecorded"]
        undercovered = dict(protective)
        undercovered["covered_quantity"] = Decimal("0.003")
        with EventLedger(self.path) as ledger:
            ledger.append(
                "PositionStateRecorded",
                make_envelope(position, position_id),
                position,
            )
            ledger.append(
                "ProtectiveOrderStateRecorded",
                make_envelope(undercovered, protective_id),
                undercovered,
            )
            covered = ledger.connection.execute(
                """
                SELECT sequence, ledger_hash
                FROM events ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            checkpoint = {
                "checkpoint_id": "checkpoint-undercovered",
                "covered_event_sequence": covered["sequence"],
                "covered_ledger_hash": covered["ledger_hash"],
                "covered_projection_hash": ledger.state_projection_hash(),
                "code_commit": "GOLDEN_TEST_COMMIT",
                "policy_bundle_hash": HASH_A,
                "created_at": "2026-01-01T00:00:00.000Z",
            }
            with self.assertRaises(LedgerIntegrityError):
                ledger.append(
                    "CheckpointRecorded",
                    make_envelope(
                        checkpoint,
                        "checkpoint-event-undercovered",
                    ),
                    checkpoint,
                )


if __name__ == "__main__":
    unittest.main()
