import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from crypto_quant.canonical import stable_id
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_scheduler import (
    SystemPaperScheduleError,
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)


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
            with self.assertRaisesRegex(
                SystemPaperScheduleError, "SYSTEM_PAPER_SCHEDULE_EVENT_TIME_ORDER_INVALID"
            ):
                state.record_gaps(
                    self.policy.current_slot("2026-08-02T20:05:11.000Z"),
                    recorded_at="2026-08-02T12:05:10.000Z",
                )

    def test_event_payload_or_hash_tampering_is_detected(self):
        self.claim("worker-a", self.now)
        connection = sqlite3.connect(str(self.state_path))
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute("UPDATE schedule_events SET payload_json='{}' WHERE sequence=1")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(SystemPaperScheduleError, "PAYLOAD_HASH_MISMATCH"):
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
