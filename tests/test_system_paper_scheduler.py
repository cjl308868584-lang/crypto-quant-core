import json
import hashlib
import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from crypto_quant.canonical import business_hash, stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_runtime import (
    build_initial_system_paper_runtime_snapshot,
)
from crypto_quant.system_paper_scheduler import (
    SystemPaperInputCapture,
    SystemPaperInputRequest,
    SystemPaperScheduleError,
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)
from tests.test_system_paper_runtime import make_bundle


class SystemPaperSchedulePolicyTests(unittest.TestCase):
    def test_policy_is_fixed_and_slot_identity_matches_runtime(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        slot = policy.current_slot("2026-08-02T12:05:11.000Z")
        self.assertEqual(policy.cadence_seconds, 14_400)
        self.assertEqual(policy.close_delay_seconds, 300)
        self.assertEqual(policy.lease_seconds, 900)
        self.assertFalse(policy.historical_backfill_allowed)
        self.assertEqual(
            slot.slot_id,
            stable_id(
                "system_paper_slot",
                {
                    "plan_hash": plan["plan_hash"],
                    "scheduled_for": "2026-08-02T12:00:00.000Z",
                },
            ),
        )

    def test_policy_rejects_direct_construction_and_plan_override(self):
        with self.assertRaises(TypeError):
            SystemPaperSchedulePolicy()
        changed = deepcopy(build_system_paper_plan())
        changed["scope"]["symbol"] = "BTCUSDT"
        with self.assertRaises(SystemPaperScheduleError):
            SystemPaperSchedulePolicy.create(changed)

    def test_slot_from_scheduled_rejects_non_boundary_times(self):
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        for scheduled_for in (
            "2026-08-02T12:00:00",
            "2026-08-02T12:01:00.000Z",
            "2026-08-02T13:00:00.000Z",
        ):
            with self.subTest(scheduled_for=scheduled_for):
                with self.assertRaises(SystemPaperScheduleError):
                    policy.slot_from_scheduled(scheduled_for)


class SystemPaperScheduleStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "state.sqlite"
        self.policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        self.now = "2026-08-02T12:05:11.000Z"
        self.slot = self.policy.current_slot(self.now)

    def tearDown(self):
        self.temp.cleanup()

    def claim(self, worker_id, claimed_at):
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            return state.claim(self.slot, worker_id=worker_id, claimed_at=claimed_at)

    def event_payload(self, slot, **extra):
        return {
            "plan_hash": self.policy.plan_hash,
            "schedule_policy_hash": self.policy.schedule_policy_hash,
            "scheduled_for": slot.scheduled_for,
            "due_at": slot.due_at,
            "expires_at": slot.expires_at,
            **extra,
        }

    def test_state_is_wal_full_sync_and_all_tables_are_immutable(self):
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            claim = state.claim(self.slot, worker_id="worker-a", claimed_at=self.now)
            self.assertEqual(claim.outcome, "CLAIMED")
            self.assertEqual(
                state.connection.execute("PRAGMA journal_mode").fetchone()[0], "wal"
            )
            self.assertEqual(
                state.connection.execute("PRAGMA synchronous").fetchone()[0], 2
            )
            trigger_names = {
                row[0]
                for row in state.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                ).fetchall()
            }
            self.assertEqual(trigger_names, {
                "schedule_events_no_update", "schedule_events_no_delete",
                "prepared_inputs_no_update", "prepared_inputs_no_delete",
                "prepared_results_no_update", "prepared_results_no_delete",
            })
            with self.assertRaises(sqlite3.DatabaseError):
                state.connection.execute("DELETE FROM schedule_events")

    def test_live_lease_is_busy_and_stale_lease_is_reclaimed(self):
        first = self.claim("worker-a", "2026-08-02T12:05:11.000Z")
        busy = self.claim("worker-b", "2026-08-02T12:10:00.000Z")
        reclaimed = self.claim("worker-b", "2026-08-02T12:21:00.000Z")
        self.assertEqual((first.attempt, busy.outcome, reclaimed.attempt), (1, "BUSY", 2))

    def test_two_connections_observe_the_same_live_lease(self):
        with SystemPaperScheduleState(self.state_path, self.policy) as first:
            first.claim(self.slot, worker_id="worker-a", claimed_at=self.now)
            with SystemPaperScheduleState(self.state_path, self.policy) as second:
                busy = second.claim(
                    self.slot,
                    worker_id="worker-b",
                    claimed_at="2026-08-02T12:10:00.000Z",
                )
        self.assertEqual(busy.outcome, "BUSY")

    def test_first_boot_does_not_backfill_and_later_unknown_slots_are_missed(self):
        first = self.policy.current_slot("2026-08-02T04:05:11.000Z")
        later = self.policy.current_slot("2026-08-02T16:05:11.000Z")
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.record_gaps(first, recorded_at="2026-08-02T04:05:11.000Z")
            state.claim(first, worker_id="worker-a", claimed_at="2026-08-02T04:05:11.000Z")
            self.assertEqual({row["slot_id"] for row in state.events()}, {first.slot_id})
            state.record_gaps(later, recorded_at="2026-08-02T16:05:11.000Z")
            missed = [
                item for item in state.slot_projection().values()
                if item["terminal_state"] == "MISSED"
            ]
        self.assertEqual([item["scheduled_for"] for item in missed], [
            "2026-08-02T08:00:00.000Z",
            "2026-08-02T12:00:00.000Z",
        ])

    def test_event_time_must_not_go_backwards(self):
        self.claim("worker-a", self.now)
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.connection.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(
                SystemPaperScheduleError, "SYSTEM_PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID"
            ):
                state._append_locked(
                    "MISSED",
                    self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z"),
                    "2026-08-02T12:05:10.000Z",
                    self.event_payload(
                        self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z"),
                        reason_code="MISSED_NO_CONTEMPORANEOUS_CAPTURE",
                    ),
                )
            state.connection.rollback()

    def test_record_gaps_rejects_a_future_slot_before_appending_events(self):
        first = self.policy.current_slot("2026-08-02T04:05:11.000Z")
        future = self.policy.current_slot("2026-08-02T16:05:11.000Z")
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.claim(first, worker_id="worker-a", claimed_at="2026-08-02T04:05:11.000Z")
            before = state.events()
            with self.assertRaisesRegex(
                SystemPaperScheduleError, "SYSTEM_PAPER_SCHEDULE_CURRENT_SLOT_MISMATCH"
            ):
                state.record_gaps(future, recorded_at=self.now)
            self.assertEqual(state.events(), before)

    def test_event_payload_or_hash_tampering_is_detected(self):
        self.claim("worker-a", self.now)
        connection = sqlite3.connect(str(self.state_path))
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute("UPDATE schedule_events SET payload_json='{}' WHERE sequence=1")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(SystemPaperScheduleError, "PAYLOAD_HASH_MISMATCH"):
            SystemPaperScheduleState(self.state_path, self.policy)

    def test_semantically_identical_noncanonical_payload_json_is_detected(self):
        self.claim("worker-a", self.now)
        connection = sqlite3.connect(str(self.state_path))
        payload_json = connection.execute(
            "SELECT payload_json FROM schedule_events WHERE sequence=1"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute(
            "UPDATE schedule_events SET payload_json=? WHERE sequence=1",
            (
                json.dumps(
                    json.loads(payload_json), sort_keys=True, separators=(", ", ": ")
                ),
            ),
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(SystemPaperScheduleError, "PAYLOAD_CANONICAL"):
            SystemPaperScheduleState(self.state_path, self.policy)

    def test_tampered_event_id_is_detected_even_with_a_matching_event_hash(self):
        self.claim("worker-a", self.now)
        connection = sqlite3.connect(str(self.state_path))
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM schedule_events WHERE sequence=1"
        ).fetchone()
        payload = json.loads(row["payload_json"])
        tampered_id = "system_paper_schedule_event_" + "f" * 64
        event_hash = business_hash(
            {
                "sequence": row["sequence"],
                "event_id": tampered_id,
                "event_type": row["event_type"],
                "slot_id": row["slot_id"],
                "event_time": row["event_time"],
                "payload": payload,
                "payload_hash": row["payload_hash"],
                "previous_event_hash": row["previous_event_hash"],
            }
        )
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute(
            "UPDATE schedule_events SET event_id=?, event_hash=? WHERE sequence=1",
            (tampered_id, event_hash),
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(SystemPaperScheduleError, "EVENT_ID_MISMATCH"):
            SystemPaperScheduleState(self.state_path, self.policy)

    def test_symlink_and_hardlinked_state_paths_are_rejected(self):
        target = Path(self.temp.name) / "target.sqlite"
        target.touch()
        link = Path(self.temp.name) / "linked.sqlite"
        link.symlink_to(target)
        with self.assertRaises(SystemPaperScheduleError):
            SystemPaperScheduleState(link, self.policy)
        linked = Path(self.temp.name) / "hardlinked.sqlite"
        os.link(target, linked)
        with self.assertRaises(SystemPaperScheduleError):
            SystemPaperScheduleState(linked, self.policy)

    def test_failed_current_slot_can_retry_with_a_new_attempt(self):
        first = self.claim("worker-a", self.now)
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.connection.execute("BEGIN IMMEDIATE")
            state._append_locked(
                "FAILED",
                self.slot,
                "2026-08-02T12:06:00.000Z",
                self.event_payload(
                    self.slot,
                    worker_id=first.worker_id,
                    attempt=first.attempt,
                    reason_code="SYSTEM_PAPER_INPUT_INVALID",
                ),
            )
            state.connection.commit()
            retry = state.claim(
                self.slot,
                worker_id="worker-b",
                claimed_at="2026-08-02T12:07:00.000Z",
            )
        self.assertEqual((retry.outcome, retry.attempt), ("CLAIMED", 2))

    def test_known_unprepared_slot_becomes_expired_and_is_terminal(self):
        old = self.policy.current_slot("2026-08-02T04:05:11.000Z")
        current = self.policy.current_slot("2026-08-02T16:05:11.000Z")
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.claim(old, worker_id="worker-a", claimed_at="2026-08-02T04:05:11.000Z")
            state.record_gaps(current, recorded_at="2026-08-02T16:05:11.000Z")
            terminal = state.claim(
                old,
                worker_id="worker-b",
                claimed_at="2026-08-02T16:05:11.000Z",
            )
        self.assertEqual(terminal.outcome, "TERMINAL_INELIGIBLE")

    def test_terminal_missed_and_expired_events_cannot_be_followed_by_a_claim(self):
        first = self.policy.current_slot("2026-08-02T04:05:11.000Z")
        later = self.policy.current_slot("2026-08-02T16:05:11.000Z")
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.claim(first, worker_id="worker-a", claimed_at="2026-08-02T04:05:11.000Z")
            state.record_gaps(later, recorded_at="2026-08-02T16:05:11.000Z")
            missed = self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z")
            state.connection.execute("BEGIN IMMEDIATE")
            state._append_locked(
                "CLAIMED",
                missed,
                "2026-08-02T16:05:11.000Z",
                self.event_payload(
                    missed,
                    worker_id="worker-b",
                    attempt=1,
                    lease_expires_at="2026-08-02T16:20:11.000Z",
                ),
            )
            state.connection.commit()
            with self.assertRaisesRegex(SystemPaperScheduleError, "TERMINAL_SLOT_MUTATED"):
                state.verify_integrity()

    def test_terminal_succeeded_event_cannot_be_followed_by_a_claim(self):
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            claim = state.claim(self.slot, worker_id="worker-a", claimed_at=self.now)
            state.connection.execute("BEGIN IMMEDIATE")
            state._append_locked(
                "INPUT_PREPARED",
                self.slot,
                "2026-08-02T12:06:00.000Z",
                self.event_payload(
                    self.slot,
                    worker_id=claim.worker_id,
                    attempt=claim.attempt,
                    input_sha256="a" * 64,
                ),
            )
            state._append_locked(
                "RESULT_PREPARED",
                self.slot,
                "2026-08-02T12:07:00.000Z",
                self.event_payload(
                    self.slot,
                    worker_id=claim.worker_id,
                    attempt=claim.attempt,
                    result_sha256="b" * 64,
                ),
            )
            state._append_locked(
                "SUCCEEDED",
                self.slot,
                "2026-08-02T12:08:00.000Z",
                self.event_payload(
                    self.slot, worker_id=claim.worker_id, attempt=claim.attempt
                ),
            )
            state._append_locked(
                "CLAIMED",
                self.slot,
                "2026-08-02T12:21:00.000Z",
                self.event_payload(
                    self.slot,
                    worker_id="worker-b",
                    attempt=2,
                    lease_expires_at="2026-08-02T12:36:00.000Z",
                ),
            )
            state.connection.commit()
            with self.assertRaisesRegex(SystemPaperScheduleError, "TERMINAL_SLOT_MUTATED"):
                state.verify_integrity()

    def test_illegal_failed_transition_without_an_active_claim_is_rejected(self):
        with SystemPaperScheduleState(self.state_path, self.policy) as state:
            state.connection.execute("BEGIN IMMEDIATE")
            state._append_locked(
                "FAILED",
                self.slot,
                self.now,
                self.event_payload(
                    self.slot,
                    worker_id="worker-a",
                    attempt=1,
                    reason_code="SYSTEM_PAPER_INPUT_INVALID",
                ),
            )
            state.connection.commit()
            with self.assertRaisesRegex(SystemPaperScheduleError, "TRANSITION_INVALID"):
                state.verify_integrity()


class SystemPaperPreparedInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.plan = build_system_paper_plan()
        self.policy = SystemPaperSchedulePolicy.create(self.plan)
        self.state = SystemPaperScheduleState(
            Path(self.temp.name) / "state.sqlite", self.policy
        )
        self.now = "2026-08-02T12:05:11.000Z"
        self.slot = self.policy.current_slot(self.now)
        self.market_bundle = make_bundle(observed_at=self.slot.scheduled_for)
        self.output_root_hash = "f" * 64

    def tearDown(self) -> None:
        self.state.close()
        self.temp.cleanup()

    def claim_current(self, worker_id="worker-a", claimed_at=None):
        return self.state.claim(
            self.slot,
            worker_id=worker_id,
            claimed_at=claimed_at or self.now,
        )

    def capture(self, **overrides):
        values = {
            "public_market_bundle": self.market_bundle,
            "capture_attempt_id": "capture-20260802t120511z",
            "captured_at": self.now,
            "request_families": (
                "SPOT_AGG_TRADE",
                "SPOT_BBO",
                "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ),
            "network_request_count": 4,
        }
        values.update(overrides)
        return SystemPaperInputCapture(**values)

    def prepare(self, claim, **overrides):
        values = {
            "plan": self.plan,
            "capture": self.capture(),
            "previous_runtime_snapshot": build_initial_system_paper_runtime_snapshot(
                self.plan
            ),
            "fill_scenario": FillScenario.immediate_full(),
            "output_root_hash": self.output_root_hash,
            "prepared_at": self.now,
        }
        values.update(overrides)
        return self.state.prepare_input(claim, **values)

    def test_input_prepare_is_atomic_exact_and_allowlisted(self):
        claim = self.claim_current()
        prepared = self.prepare(claim)

        loaded = self.state.load_prepared_input(claim.slot)
        envelope = json.loads(loaded["input_bytes"])
        self.assertEqual(
            hashlib.sha256(loaded["input_bytes"]).hexdigest(),
            prepared["input_sha256"],
        )
        self.assertEqual(envelope["slot_id"], claim.slot.slot_id)
        self.assertEqual(envelope["scheduled_for"], "2026-08-02T12:00:00.000Z")
        self.assertEqual(
            envelope["capture"]["request_families"],
            [
                "SPOT_AGG_TRADE",
                "SPOT_BBO",
                "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ],
        )
        self.assertEqual(
            self.state.slot_projection()[claim.slot.slot_id]["durable_stage"], "INPUT"
        )
        self.assertEqual(
            self.state.connection.execute("SELECT COUNT(*) FROM prepared_inputs").fetchone()[0],
            1,
        )

    def test_input_request_is_credential_and_path_free(self):
        request = SystemPaperInputRequest.for_slot(self.policy, self.slot)

        self.assertEqual(request.plan_hash, self.plan["plan_hash"])
        self.assertEqual(request.capture_deadline, self.slot.expires_at)
        self.assertEqual(
            request.request_families,
            (
                "SPOT_AGG_TRADE",
                "SPOT_BBO",
                "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ),
        )

    def test_input_prepare_rejects_non_allowlisted_capture_boundaries(self):
        cases = (
            self.capture(request_families=("SPOT_BBO", "SPOT_EXCHANGE_INFO", "SPOT_KLINE_4H_WARMUP")),
            self.capture(request_families=("SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_BBO", "SPOT_KLINE_4H_WARMUP")),
            self.capture(request_families=("SPOT_BBO", "SPOT_AGG_TRADE", "SPOT_EXCHANGE_INFO", "SPOT_KLINE_4H_WARMUP")),
            self.capture(request_families=("SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_EXCHANGE_INFO", "SPOT_KLINE_4H_WARMUP", "SPOT_ACCOUNT")),
            self.capture(request_families=("SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_EXCHANGE_INFO", "BROKER_ORDER")),
            self.capture(network_request_count=3),
            self.capture(network_request_count=5),
        )
        claim = self.claim_current()
        for index, capture in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(SystemPaperScheduleError):
                    self.prepare(claim, capture=capture)
                self.assertEqual(
                    self.state.connection.execute("SELECT COUNT(*) FROM prepared_inputs").fetchone()[0],
                    0,
                )

    def test_input_prepare_rejects_stale_or_mismatched_capture(self):
        stale = self.capture(captured_at="2026-08-02T16:00:00.000Z")
        changed_bundle = dict(self.market_bundle)
        changed_bundle["observed_at"] = "2026-08-02T08:00:00.000Z"
        changed_bundle["bundle_hash"] = artifact_self_hash(changed_bundle, "bundle_hash")
        mismatched = self.capture(public_market_bundle=changed_bundle)
        claim = self.claim_current()
        for index, capture in enumerate((stale, mismatched)):
            with self.subTest(index=index):
                with self.assertRaises(SystemPaperScheduleError):
                    self.prepare(claim, capture=capture)

    def test_load_prepared_input_rejects_binary_float_envelopes(self):
        claim = self.claim_current()
        self.prepare(claim)
        self.state.connection.execute("DROP TRIGGER prepared_inputs_no_update")
        binary_float = b'{"schema_version":"1.0.0","slot_id":"tampered","number":1.0}'
        self.state.connection.execute(
            "UPDATE prepared_inputs SET input_bytes=?, input_sha256=?",
            (binary_float, hashlib.sha256(binary_float).hexdigest()),
        )
        with self.assertRaisesRegex(SystemPaperScheduleError, "INPUT_CANONICAL"):
            self.state.load_prepared_input(claim.slot)

    def test_load_prepared_input_rejects_changed_component_hashes(self):
        claim = self.claim_current()
        self.prepare(claim)
        self.state.connection.execute("DROP TRIGGER prepared_inputs_no_update")
        for column in (
            "plan_hash",
            "market_bundle_hash",
            "previous_snapshot_hash",
            "fill_scenario_hash",
            "output_root_hash",
        ):
            original = self.state.connection.execute(
                f"SELECT {column} FROM prepared_inputs"
            ).fetchone()[0]
            changed = "0" * 64 if original != "0" * 64 else "1" * 64
            self.state.connection.execute(
                f"UPDATE prepared_inputs SET {column}=?", (changed,)
            )
            with self.subTest(column=column):
                with self.assertRaisesRegex(SystemPaperScheduleError, "INPUT_HASH_MISMATCH"):
                    self.state.load_prepared_input(claim.slot)
            self.state.connection.execute(
                f"UPDATE prepared_inputs SET {column}=?", (original,)
            )

    def test_prepared_input_is_immutable_and_resumes_after_failure_or_expired_lease(self):
        first = self.claim_current()
        prepared = self.prepare(first)
        original = self.state.load_prepared_input(first.slot)["input_bytes"]
        with self.assertRaises(SystemPaperScheduleError):
            self.prepare(first)
        with self.assertRaises(sqlite3.DatabaseError):
            self.state.connection.execute("UPDATE prepared_inputs SET input_sha256='0'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.state.connection.execute("DELETE FROM prepared_inputs")
        self.state.connection.rollback()
        self.state.connection.execute("BEGIN IMMEDIATE")
        self.state._append_locked(
            "FAILED",
            first.slot,
            "2026-08-02T12:06:00.000Z",
            {
                "plan_hash": self.policy.plan_hash,
                "schedule_policy_hash": self.policy.schedule_policy_hash,
                "scheduled_for": first.slot.scheduled_for,
                "due_at": first.slot.due_at,
                "expires_at": first.slot.expires_at,
                "worker_id": first.worker_id,
                "attempt": first.attempt,
                "reason_code": "SYSTEM_PAPER_RUNTIME_INTERRUPTED",
            },
        )
        self.state.connection.commit()
        after_failure = self.claim_current("worker-b", "2026-08-02T12:07:00.000Z")
        self.assertEqual(after_failure.outcome, "RESUME_INPUT")
        after_expiry = self.claim_current("worker-c", "2026-08-02T12:23:00.000Z")
        self.assertEqual(after_expiry.outcome, "RESUME_INPUT")
        after_window = self.claim_current("worker-d", "2026-08-02T16:05:11.000Z")
        self.assertEqual(after_window.outcome, "RESUME_INPUT")
        self.assertEqual(self.state.load_prepared_input(first.slot)["input_bytes"], original)
        self.assertEqual(prepared["input_sha256"], hashlib.sha256(original).hexdigest())
