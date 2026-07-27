import json
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from importlib import resources

from jsonschema import Draft202012Validator

from crypto_quant.offline_paper import PublicPaperHttpResponse
from crypto_quant.paper_scheduler import (
    PaperScheduleError,
    PaperSchedulePolicy,
    PaperScheduleState,
    build_schedule_snapshot,
    run_due_paper_cycle,
    schedule_snapshot_reasons,
    schedule_snapshot_trust_hash,
)
from tests.test_offline_paper import FakeTransport, valid_capture


UTC = timezone.utc


def iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def paper_transport():
    capture, _ = valid_capture()
    base = datetime(2026, 7, 27, 12, 5, 10, tzinfo=UTC)
    responses = []
    for index, receipt in enumerate(capture.receipts):
        start = base + timedelta(milliseconds=index * 100)
        received = start + timedelta(milliseconds=50)
        responses.append(
            PublicPaperHttpResponse(
                status=200,
                final_url=receipt["final_url"],
                headers={"Date": "Mon, 27 Jul 2026 12:05:10 GMT"},
                body=receipt["response_body_utf8"].encode(),
                request_started_at=iso(start),
                response_received_at=iso(received),
            )
        )
    return FakeTransport(responses)


class BombTransport:
    def __init__(self):
        self.calls = 0

    def get(self, _request):
        self.calls += 1
        raise AssertionError("transport must not be called")


class PaperSlotPolicyTests(unittest.TestCase):
    def test_slot_starts_five_minutes_after_each_utc_4h_close(self):
        policy = PaperSchedulePolicy.create()
        before = policy.current_slot("2026-07-27T12:04:59.999Z")
        after = policy.current_slot("2026-07-27T12:05:00.000Z")
        self.assertEqual(before.scheduled_for, "2026-07-27T08:00:00.000Z")
        self.assertEqual(before.due_at, "2026-07-27T08:05:00.000Z")
        self.assertEqual(after.scheduled_for, "2026-07-27T12:00:00.000Z")
        self.assertEqual(after.due_at, "2026-07-27T12:05:00.000Z")
        self.assertEqual(after.expires_at, "2026-07-27T16:05:00.000Z")
        self.assertEqual(after.slot_id, "ETHUSDT_20260727T120000Z")

    def test_slot_policy_rejects_naive_time_and_direct_construction(self):
        with self.assertRaises(TypeError):
            PaperSchedulePolicy()
        with self.assertRaises(PaperScheduleError):
            PaperSchedulePolicy.create(symbol="BTCUSDT")
        with self.assertRaises(PaperScheduleError):
            PaperSchedulePolicy.create().current_slot("2026-07-27T12:05:00")


class PaperScheduleStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.sqlite"
        self.policy = PaperSchedulePolicy.create()
        self.slot = self.policy.current_slot("2026-07-27T12:06:00.000Z")

    def tearDown(self):
        self.temp.cleanup()

    def test_state_is_wal_full_sync_and_append_only(self):
        with PaperScheduleState(self.path, self.policy) as state:
            claim = state.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
            self.assertEqual(claim.outcome, "CLAIMED")
            self.assertEqual(
                state.connection.execute("PRAGMA journal_mode").fetchone()[0],
                "wal",
            )
            self.assertEqual(
                state.connection.execute("PRAGMA synchronous").fetchone()[0],
                2,
            )
            with self.assertRaises(sqlite3.DatabaseError):
                state.connection.execute(
                    "UPDATE schedule_events SET event_type='RUN_SUCCEEDED'"
                )
            with self.assertRaises(sqlite3.DatabaseError):
                state.connection.execute("DELETE FROM schedule_events")

    def test_first_boot_records_only_current_slot(self):
        with PaperScheduleState(self.path, self.policy) as state:
            state.record_gaps(
                self.slot,
                recorded_at="2026-07-27T12:06:00.000Z",
            )
            state.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
            events = state.events()
        self.assertEqual({item["slot_id"] for item in events}, {self.slot.slot_id})
        self.assertFalse(any(item["event_type"] == "SLOT_MISSED" for item in events))

    def test_live_lease_is_busy_and_expired_lease_is_reclaimed(self):
        with PaperScheduleState(self.path, self.policy) as state:
            first = state.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
            busy = state.claim(
                self.slot,
                worker_id="worker-b",
                claimed_at="2026-07-27T12:10:00.000Z",
            )
            reclaimed = state.claim(
                self.slot,
                worker_id="worker-b",
                claimed_at="2026-07-27T12:21:00.000Z",
            )
        self.assertEqual(first.attempt, 1)
        self.assertEqual(busy.outcome, "BUSY")
        self.assertEqual(reclaimed.outcome, "CLAIMED")
        self.assertEqual(reclaimed.attempt, 2)

    def test_two_connections_observe_the_same_live_lease(self):
        with PaperScheduleState(self.path, self.policy) as first:
            first.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
            with PaperScheduleState(self.path, self.policy) as second:
                result = second.claim(
                    self.slot,
                    worker_id="worker-b",
                    claimed_at="2026-07-27T12:07:00.000Z",
                )
        self.assertEqual(result.outcome, "BUSY")

    def test_symlink_state_file_is_rejected(self):
        target = Path(self.temp.name) / "target.sqlite"
        target.touch()
        link = Path(self.temp.name) / "linked.sqlite"
        link.symlink_to(target)
        with self.assertRaisesRegex(
            PaperScheduleError, "PAPER_SCHEDULE_STATE_PATH_INVALID"
        ):
            PaperScheduleState(link, self.policy)

    def test_failed_current_slot_can_retry_but_old_slot_expires(self):
        with PaperScheduleState(self.path, self.policy) as state:
            claim = state.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
            state.fail(
                claim,
                reason_code="PAPER_TRANSPORT_FAILURE",
                failed_at="2026-07-27T12:07:00.000Z",
            )
            retry = state.claim(
                self.slot,
                worker_id="worker-b",
                claimed_at="2026-07-27T12:08:00.000Z",
            )
            self.assertEqual(retry.attempt, 2)
            next_slot = self.policy.current_slot("2026-07-27T16:06:00.000Z")
            state.record_gaps(
                next_slot,
                recorded_at="2026-07-27T16:06:00.000Z",
            )
            projection = state.slot_projection()
        self.assertEqual(projection[self.slot.slot_id]["status"], "EXPIRED")

    def test_unknown_intermediate_slots_are_missed_and_never_claimable(self):
        first = self.policy.current_slot("2026-07-27T04:06:00.000Z")
        current = self.policy.current_slot("2026-07-27T16:06:00.000Z")
        with PaperScheduleState(self.path, self.policy) as state:
            claim = state.claim(
                first,
                worker_id="worker-a",
                claimed_at="2026-07-27T04:06:00.000Z",
            )
            state.fail(
                claim,
                reason_code="PAPER_TRANSPORT_FAILURE",
                failed_at="2026-07-27T04:07:00.000Z",
            )
            state.record_gaps(
                current,
                recorded_at="2026-07-27T16:06:00.000Z",
            )
            projection = state.slot_projection()
            missed = self.policy.slot_from_scheduled(
                "2026-07-27T08:00:00.000Z"
            )
            terminal = state.claim(
                missed,
                worker_id="worker-b",
                claimed_at="2026-07-27T16:06:00.000Z",
            )
        self.assertEqual(projection[first.slot_id]["status"], "EXPIRED")
        self.assertEqual(
            projection["ETHUSDT_20260727T080000Z"]["status"], "MISSED"
        )
        self.assertEqual(
            projection["ETHUSDT_20260727T120000Z"]["status"], "MISSED"
        )
        self.assertEqual(terminal.outcome, "TERMINAL_INELIGIBLE")

    def test_event_or_blob_tampering_is_detected(self):
        with PaperScheduleState(self.path, self.policy) as state:
            state.claim(
                self.slot,
                worker_id="worker-a",
                claimed_at="2026-07-27T12:06:00.000Z",
            )
        connection = sqlite3.connect(str(self.path))
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute(
            "UPDATE schedule_events SET payload_json='{}' WHERE sequence=1"
        )
        connection.commit()
        connection.close()
        with self.assertRaises(PaperScheduleError):
            with PaperScheduleState(self.path, self.policy) as state:
                state.verify_integrity()


class PaperScheduleRunnerTests(unittest.TestCase):
    def test_end_to_end_run_then_same_slot_is_zero_network_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runtime" / "paper.sqlite"
            output = root / "artifacts"
            clock = lambda: "2026-07-27T12:05:11.000Z"
            transport = paper_transport()
            first = run_due_paper_cycle(
                state_path=state_path,
                output_root=output,
                worker_id="worker-a",
                transport=transport,
                clock=clock,
            )
            self.assertEqual(first["outcome"], "EXECUTED")
            self.assertEqual(len(transport.requests), 4)
            self.assertTrue(Path(first["artifact_path"]).is_file())
            self.assertTrue(Path(first["schedule_snapshot_path"]).is_file())

            bomb = BombTransport()
            second = run_due_paper_cycle(
                state_path=state_path,
                output_root=output,
                worker_id="worker-b",
                transport=bomb,
                clock=clock,
            )
            self.assertEqual(second["outcome"], "ALREADY_SUCCEEDED")
            self.assertEqual(second["network_request_count"], 0)
            self.assertEqual(bomb.calls, 0)
            self.assertEqual(first["cycle_run_hash"], second["cycle_run_hash"])

    def test_prepared_crash_resumes_exact_bytes_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runtime" / "paper.sqlite"
            output = root / "artifacts"
            clock = lambda: "2026-07-27T12:05:11.000Z"
            with self.assertRaisesRegex(
                PaperScheduleError, "INJECTED_AFTER_PREPARE"
            ):
                run_due_paper_cycle(
                    state_path=state_path,
                    output_root=output,
                    worker_id="worker-a",
                    transport=paper_transport(),
                    clock=clock,
                    fault_after_prepare=True,
                )
            self.assertFalse((output / "paper").exists())

            bomb = BombTransport()
            resumed = run_due_paper_cycle(
                state_path=state_path,
                output_root=output,
                worker_id="worker-b",
                transport=bomb,
                clock=lambda: "2026-07-27T12:21:00.000Z",
            )
            self.assertEqual(resumed["outcome"], "RESUMED_PREPARED")
            self.assertEqual(resumed["network_request_count"], 0)
            self.assertEqual(bomb.calls, 0)
            run = json.loads(Path(resumed["artifact_path"]).read_text())
            self.assertEqual(run["run_hash"], resumed["cycle_run_hash"])

    def test_published_before_success_crash_is_adopted_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "runtime" / "paper.sqlite"
            output = root / "artifacts"
            with self.assertRaisesRegex(
                PaperScheduleError, "INJECTED_AFTER_PUBLISH"
            ):
                run_due_paper_cycle(
                    state_path=state_path,
                    output_root=output,
                    worker_id="worker-a",
                    transport=paper_transport(),
                    clock=lambda: "2026-07-27T12:05:11.000Z",
                    fault_after_publish=True,
                )
            artifact = (
                output
                / "paper"
                / "paper-slot-ethusdt_20260727t120000z.json"
            )
            original = artifact.read_bytes()
            resumed = run_due_paper_cycle(
                state_path=state_path,
                output_root=output,
                worker_id="worker-b",
                transport=BombTransport(),
                clock=lambda: "2026-07-27T12:21:00.000Z",
            )
            self.assertEqual(resumed["outcome"], "RESUMED_PREPARED")
            self.assertFalse(resumed["artifact_created"])
            self.assertEqual(artifact.read_bytes(), original)

    def test_schedule_snapshot_replays_events_and_requires_external_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "paper.sqlite"
            result = run_due_paper_cycle(
                state_path=state_path,
                output_root=root / "artifacts",
                worker_id="worker-a",
                transport=paper_transport(),
                clock=lambda: "2026-07-27T12:05:11.000Z",
            )
            snapshot = result["schedule_snapshot"]
            trust = schedule_snapshot_trust_hash(snapshot)
            self.assertEqual(schedule_snapshot_reasons(snapshot, trust), ())
            self.assertEqual(snapshot["summary"]["succeeded_slot_count"], 1)
            self.assertEqual(snapshot["summary"]["observed_calendar_days"], 1)
            self.assertFalse(snapshot["summary"]["ninety_day_complete"])
            self.assertEqual(
                snapshot["paper_eligibility"],
                "LONGITUDINAL_COLLECTION_IN_PROGRESS",
            )

            changed = deepcopy(snapshot)
            changed["summary"]["succeeded_slot_count"] = 99
            self.assertIn(
                "PAPER_SCHEDULE_SELF_HASH_MISMATCH",
                schedule_snapshot_reasons(changed, trust),
            )

    def test_prepared_output_root_is_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "paper.sqlite"
            with self.assertRaises(PaperScheduleError):
                run_due_paper_cycle(
                    state_path=state_path,
                    output_root=root / "one",
                    worker_id="worker-a",
                    transport=paper_transport(),
                    clock=lambda: "2026-07-27T12:05:11.000Z",
                    fault_after_prepare=True,
                )
            with self.assertRaisesRegex(
                PaperScheduleError, "PAPER_SCHEDULE_OUTPUT_ROOT_MISMATCH"
            ):
                run_due_paper_cycle(
                    state_path=state_path,
                    output_root=root / "two",
                    worker_id="worker-b",
                    transport=BombTransport(),
                    clock=lambda: "2026-07-27T12:21:00.000Z",
                )

    def test_schedule_schema_is_packaged_and_rejects_unreviewed_claims(self):
        root = Path(__file__).resolve().parents[1]
        governance = (
            root / "config" / "paper-schedule-snapshot-v1.schema.json"
        ).read_bytes()
        packaged = resources.files("crypto_quant").joinpath(
            "schemas", "paper-schedule-snapshot-v1.schema.json"
        ).read_bytes()
        self.assertEqual(governance, packaged)
        schema = json.loads(governance)
        Draft202012Validator.check_schema(schema)
        with tempfile.TemporaryDirectory() as directory:
            result = run_due_paper_cycle(
                state_path=Path(directory) / "paper.sqlite",
                output_root=Path(directory) / "artifacts",
                worker_id="worker-a",
                transport=paper_transport(),
                clock=lambda: "2026-07-27T12:05:11.000Z",
            )
        changed = deepcopy(result["schedule_snapshot"])
        changed["profitable"] = True
        self.assertTrue(
            tuple(Draft202012Validator(schema).iter_errors(changed))
        )


if __name__ == "__main__":
    unittest.main()
