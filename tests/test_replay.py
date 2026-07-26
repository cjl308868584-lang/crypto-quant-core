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
    "db5c86ade60add594b5af276c2c4d939ae51a0bf9887469eb8bc70027e621dd8"
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
                7,
            )
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


if __name__ == "__main__":
    unittest.main()
