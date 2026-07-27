import copy
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import (
    business_hash,
    canonical_json,
    utc_datetime,
)
from crypto_quant.challenger_forward import (
    ChallengerForwardError,
    ChallengerForwardState,
    build_challenger_forward_decision,
    build_challenger_prequential_snapshot,
    challenger_decision_hash,
    challenger_forward_policy,
    challenger_snapshot_hash,
    challenger_snapshot_reasons,
    load_challenger_prequential_snapshot,
    publish_challenger_prequential_snapshot,
)


START = datetime(2026, 7, 29, tzinfo=timezone.utc)


def stream_rows(closes):
    first_open = START - timedelta(hours=4 * 21)
    rows = []
    for index, close in enumerate(closes):
        opened = first_open + timedelta(hours=4 * index)
        closed = opened + timedelta(hours=4) - timedelta(milliseconds=1)
        row = {
            "provider": "BINANCE_PUBLIC_DATA",
            "market": "SPOT",
            "data_family": "KLINES",
            "symbol": "ETHUSDT",
            "interval": "4h",
            "open_time": utc_datetime(opened),
            "close_time": utc_datetime(closed),
            "available_at": utc_datetime(closed + timedelta(milliseconds=1)),
            "open": str(close),
            "high": str(close + 1),
            "low": str(close - 1),
            "close": str(close),
        }
        row["source_row_hash"] = business_hash(row)
        rows.append(row)
    return rows


def build_at(sequence, rows, previous=None, delay_minutes=1):
    scheduled = START + timedelta(hours=4 * (sequence - 1))
    return build_challenger_forward_decision(
        klines=rows[-21:],
        scheduled_for=utc_datetime(scheduled),
        recorded_at=utc_datetime(scheduled + timedelta(minutes=delay_minutes)),
        previous_decision=previous,
    )


class ChallengerForwardTests(unittest.TestCase):
    def test_policy_registration_and_rejection_then_entry_are_frozen(self):
        policy = challenger_forward_policy()
        self.assertEqual(
            policy["challenger_policy_id"],
            "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2",
        )
        self.assertFalse(policy["broker_access"])
        rows = stream_rows([100] * 21)
        rejected = build_at(1, rows)
        self.assertEqual(rejected["action"], "REJECT_ENTRY")
        self.assertEqual(rejected["state_after"]["position_state"], "FLAT")
        rows.extend(stream_rows([100] * 21 + [102])[-1:])
        entered = build_at(2, rows, rejected)
        self.assertEqual(entered["action"], "ENTER_LONG")
        self.assertEqual(entered["state_before"]["position_state"], "FLAT")
        self.assertEqual(entered["state_after"]["position_state"], "LONG")
        self.assertEqual(
            entered["broker_eligibility"],
            "INELIGIBLE_NO_BROKER_ACCESS",
        )

    def test_minimum_hold_then_sma_exit(self):
        rows = stream_rows([100] * 21)
        first = build_at(1, rows)
        rows.append(stream_rows([100] * 21 + [102])[-1])
        entered = build_at(2, rows, first)
        rows.append(stream_rows([100] * 21 + [102, 101])[-1])
        minimum = build_at(3, rows, entered)
        self.assertEqual(minimum["action"], "HOLD_LONG_MINIMUM")
        rows.append(stream_rows([100] * 21 + [102, 101, 99])[-1])
        exited = build_at(4, rows, minimum)
        self.assertEqual(exited["action"], "EXIT_LONG_SMA20")
        self.assertEqual(exited["state_after"]["position_state"], "FLAT")

    def test_vertical_exit_occurs_at_24_hours(self):
        rows = stream_rows([100] * 20 + [102])
        decision = build_at(1, rows)
        self.assertEqual(decision["action"], "ENTER_LONG")
        for sequence, close in enumerate((103, 104, 105, 106, 107, 108), 2):
            rows.append(
                stream_rows([100] * 20 + [102, 103, 104, 105, 106, 107, 108])[
                    19 + sequence
                ]
            )
            decision = build_at(sequence, rows, decision)
        self.assertEqual(decision["action"], "EXIT_LONG_VERTICAL_24H")
        self.assertEqual(decision["scheduled_for"], "2026-07-30T00:00:00.000Z")

    def test_determinism_and_input_revision_fail_closed(self):
        rows = stream_rows([100] * 21)
        expected = build_at(1, rows)
        for _ in range(100):
            self.assertEqual(build_at(1, rows), expected)
        rows.append(stream_rows([100] * 21 + [102])[-1])
        revised = copy.deepcopy(rows[-21:])
        revised[0]["close"] = "101"
        revised[0]["source_row_hash"] = business_hash(
            {key: value for key, value in revised[0].items() if key != "source_row_hash"}
        )
        with self.assertRaisesRegex(
            ChallengerForwardError,
            "CHALLENGER_FORWARD_INPUT_REVISION",
        ):
            build_challenger_forward_decision(
                klines=revised,
                scheduled_for="2026-07-29T04:00:00.000Z",
                recorded_at="2026-07-29T04:01:00.000Z",
                previous_decision=expected,
            )

    def test_slot_deadline_availability_and_continuity_fail_closed(self):
        rows = stream_rows([100] * 21)
        with self.assertRaisesRegex(
            ChallengerForwardError,
            "CHALLENGER_FORWARD_GENESIS_SLOT_INVALID",
        ):
            build_at(2, rows)
        late = copy.deepcopy(rows)
        late[-1]["available_at"] = "2026-07-29T00:02:00.000Z"
        with self.assertRaisesRegex(
            ChallengerForwardError,
            "CHALLENGER_FORWARD_KLINES_INVALID",
        ):
            build_at(1, late)
        with self.assertRaisesRegex(
            ChallengerForwardError,
            "CHALLENGER_FORWARD_SLOT_INVALID",
        ):
            build_at(1, rows, delay_minutes=240)
        first = build_at(1, rows)
        skipped_rows = stream_rows([100] * 23)[-21:]
        with self.assertRaisesRegex(
            ChallengerForwardError,
            "CHALLENGER_FORWARD_CONTINUITY_INVALID",
        ):
            build_challenger_forward_decision(
                klines=skipped_rows,
                scheduled_for="2026-07-29T08:00:00.000Z",
                recorded_at="2026-07-29T08:01:00.000Z",
                previous_decision=first,
            )

    def test_append_only_state_exact_retry_conflict_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "forward.sqlite"
            rows = stream_rows([100] * 21)
            with ChallengerForwardState(path) as state:
                first = state.append(
                    klines=rows,
                    scheduled_for="2026-07-29T00:00:00.000Z",
                    recorded_at="2026-07-29T00:01:00.000Z",
                )
                retry = state.append(
                    klines=rows,
                    scheduled_for="2026-07-29T00:00:00.000Z",
                    recorded_at="2026-07-29T00:01:00.000Z",
                )
                self.assertEqual(retry, first)
                with self.assertRaisesRegex(
                    ChallengerForwardError,
                    "CHALLENGER_FORWARD_SLOT_CONFLICT",
                ):
                    state.append(
                        klines=rows,
                        scheduled_for="2026-07-29T00:00:00.000Z",
                        recorded_at="2026-07-29T00:02:00.000Z",
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    state._connection.execute(
                        "UPDATE decisions SET decision_hash=? WHERE sequence=1",
                        ("f" * 64,),
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    state._connection.execute(
                        "DELETE FROM decisions WHERE sequence=1"
                    )
                state._connection.rollback()
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            raw = sqlite3.connect(path)
            raw.execute("DROP TRIGGER decisions_no_update")
            raw.execute(
                "UPDATE decisions SET decision_bytes=? WHERE sequence=1",
                (b'{"tampered":true}',),
            )
            raw.commit()
            raw.close()
            with self.assertRaisesRegex(
                ChallengerForwardError,
                "CHALLENGER_FORWARD_STATE_CORRUPT",
            ):
                ChallengerForwardState(path)

    def test_snapshot_schema_semantics_publish_and_mirror(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state" / "forward.sqlite"
            rows = stream_rows([100] * 21)
            with ChallengerForwardState(state_path) as state:
                state.append(
                    klines=rows,
                    scheduled_for="2026-07-29T00:00:00.000Z",
                    recorded_at="2026-07-29T00:01:00.000Z",
                )
                snapshot = build_challenger_prequential_snapshot(
                    state=state,
                    recorded_at="2026-07-29T00:02:00.000Z",
                )
            self.assertEqual(challenger_snapshot_reasons(snapshot), ())
            output = root / "evidence" / "snapshot.json"
            publish_challenger_prequential_snapshot(
                snapshot=snapshot,
                output_path=output,
            )
            self.assertEqual(load_challenger_prequential_snapshot(output), snapshot)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            tampered = copy.deepcopy(snapshot)
            tampered["decisions"][0]["action"] = "ENTER_LONG"
            tampered["decisions"][0]["decision_hash"] = challenger_decision_hash(
                tampered["decisions"][0]
            )
            tampered["decisions_root_hash"] = business_hash(tampered["decisions"])
            tampered["decision_chain_end_hash"] = tampered["decisions"][0][
                "decision_hash"
            ]
            tampered["snapshot_hash"] = challenger_snapshot_hash(tampered)
            self.assertIn(
                "CHALLENGER_FORWARD_DECISION_SEMANTIC_MISMATCH",
                challenger_snapshot_reasons(tampered),
            )
        repository = Path(__file__).resolve().parents[1]
        self.assertEqual(
            (repository / "config" / "challenger-prequential-snapshot-v1.schema.json").read_bytes(),
            (
                repository
                / "src"
                / "crypto_quant"
                / "schemas"
                / "challenger-prequential-snapshot-v1.schema.json"
            ).read_bytes(),
        )

    def test_empty_state_does_not_fabricate_snapshot_and_has_no_broker_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            with ChallengerForwardState(Path(directory) / "forward.sqlite") as state:
                with self.assertRaisesRegex(
                    ChallengerForwardError,
                    "CHALLENGER_FORWARD_NO_DECISIONS",
                ):
                    build_challenger_prequential_snapshot(
                        state=state,
                        recorded_at="2026-07-29T00:00:00.000Z",
                    )
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "crypto_quant"
            / "challenger_forward.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from .orders", source)
        self.assertNotIn("from .execution", source)
        self.assertNotIn("Broker(", source)


if __name__ == "__main__":
    unittest.main()
