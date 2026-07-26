import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from crypto_quant.contracts import EventEnvelope
from crypto_quant.errors import LedgerConflictError
from crypto_quant.ledger import EventLedger

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_envelope(payload, event_id):
    return EventEnvelope.create(
        schema_version="1.1.0",
        event_id=event_id,
        trace_id="trace-1",
        correlation_id="corr-1",
        causation_id=None,
        run_id="run-1",
        event_time=NOW,
        available_at=NOW,
        ingested_at=NOW,
        recorded_at=NOW,
        source="REPLAY",
        payload=payload,
    )


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "ledger.sqlite"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_append_is_idempotent_and_projections_are_exactly_once(self) -> None:
        cost = {"category": "DATA", "amount_usdt": Decimal("3.50")}
        cash = {"flow_type": "DEPOSIT", "signed_amount_usdt": Decimal("500")}
        with EventLedger(self.path) as ledger:
            first = ledger.append(
                "OperatingCostRecorded",
                make_envelope(cost, "cost-1"),
                cost,
            )
            duplicate = ledger.append(
                "OperatingCostRecorded",
                make_envelope(cost, "cost-1"),
                cost,
            )
            ledger.append(
                "ExternalCashFlowRecorded",
                make_envelope(cash, "cash-1"),
                cash,
            )
            self.assertTrue(first.inserted)
            self.assertFalse(duplicate.inserted)
            self.assertEqual(ledger.projection_totals(), (Decimal("3.5"), Decimal("500")))
            end_hash = ledger.verify_integrity()

        with EventLedger(self.path) as replayed:
            self.assertEqual(replayed.verify_integrity(), end_hash)
            replayed.connection.execute("DELETE FROM operating_costs_projection")
            replayed.connection.execute("DELETE FROM external_cash_flows_projection")
            replayed.connection.commit()
            self.assertEqual(replayed.projection_totals(), (Decimal("0"), Decimal("0")))
            replayed.rebuild_projections()
            self.assertEqual(replayed.projection_totals(), (Decimal("3.5"), Decimal("500")))

    def test_same_event_id_with_different_content_is_rejected(self) -> None:
        original = {"category": "DATA", "amount_usdt": Decimal("1")}
        changed = {"category": "DATA", "amount_usdt": Decimal("2")}
        with EventLedger(self.path) as ledger:
            ledger.append(
                "OperatingCostRecorded",
                make_envelope(original, "cost-1"),
                original,
            )
            with self.assertRaises(LedgerConflictError):
                ledger.append(
                    "OperatingCostRecorded",
                    make_envelope(changed, "cost-1"),
                    changed,
                )
            with self.assertRaises(LedgerConflictError):
                ledger.append(
                    "DifferentEconomicEvent",
                    make_envelope(original, "cost-1"),
                    original,
                )

    def test_outbox_is_persisted_before_any_external_side_effect(self) -> None:
        payload = {"intent_id": "intent-1", "target_id": "target-1"}
        command = {"symbol": "ETHUSDT", "side": "BUY", "quantity": Decimal("0.01")}
        envelope = make_envelope(payload, "intent-event-1")
        with EventLedger(self.path) as ledger:
            first = ledger.enqueue_outbox(
                event_type="ExecutionIntentCreated",
                envelope=envelope,
                payload=payload,
                outbox_id="outbox-1",
                intent_id="intent-1",
                command=command,
            )
            duplicate = ledger.enqueue_outbox(
                event_type="ExecutionIntentCreated",
                envelope=envelope,
                payload=payload,
                outbox_id="outbox-1",
                intent_id="intent-1",
                command=command,
            )
            rows = list(ledger.pending_outbox())
            self.assertTrue(first.inserted)
            self.assertFalse(duplicate.inserted)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "PENDING")
            self.assertFalse(hasattr(ledger, "submit_order"))

    def test_events_table_is_immutable(self) -> None:
        payload = {"category": "DATA", "amount_usdt": Decimal("1")}
        with EventLedger(self.path) as ledger:
            ledger.append(
                "OperatingCostRecorded",
                make_envelope(payload, "cost-1"),
                payload,
            )
            with self.assertRaises(sqlite3.DatabaseError):
                ledger.connection.execute(
                    "UPDATE events SET event_type = 'Tampered' WHERE event_id = 'cost-1'"
                )


if __name__ == "__main__":
    unittest.main()
