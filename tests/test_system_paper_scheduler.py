import json
import hashlib
import os
import sqlite3
import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from crypto_quant.canonical import business_hash, canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_runtime import (
    SystemPaperSlotInputs,
    build_initial_system_paper_runtime_snapshot,
    run_system_paper_slot,
    system_paper_slot_hash,
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

    def test_input_prepare_rejects_rehashed_nonpublic_bundle_semantics(self):
        unknown = dict(self.market_bundle)
        unknown["credential"] = "must-not-persist"
        unknown["bundle_hash"] = artifact_self_hash(unknown, "bundle_hash")
        wrong_provider = dict(self.market_bundle)
        wrong_provider["provider"] = "PRIVATE_MARKET_DATA"
        wrong_provider["bundle_hash"] = artifact_self_hash(
            wrong_provider, "bundle_hash"
        )
        malformed_receipts = dict(self.market_bundle)
        malformed_receipts["source_receipt_hashes"] = ["a" * 64]
        malformed_receipts["bundle_hash"] = artifact_self_hash(
            malformed_receipts, "bundle_hash"
        )
        for name, bundle in (
            ("unknown", unknown),
            ("wrong_provider", wrong_provider),
            ("malformed_receipts", malformed_receipts),
        ):
            with self.subTest(name=name):
                with SystemPaperScheduleState(
                    Path(self.temp.name) / f"{name}.sqlite", self.policy
                ) as state:
                    claim = state.claim(
                        self.slot,
                        worker_id="worker-a",
                        claimed_at=self.now,
                    )
                    with self.assertRaisesRegex(
                        SystemPaperScheduleError,
                        "INPUT_BUNDLE_SEMANTIC_INVALID",
                    ):
                        state.prepare_input(
                            claim,
                            plan=self.plan,
                            capture=self.capture(public_market_bundle=bundle),
                            previous_runtime_snapshot=(
                                build_initial_system_paper_runtime_snapshot(self.plan)
                            ),
                            fill_scenario=FillScenario.immediate_full(),
                            output_root_hash=self.output_root_hash,
                            prepared_at=self.now,
                        )

    def test_input_prepare_rejects_rehashed_invalid_runtime_snapshot(self):
        invalid_snapshot = build_initial_system_paper_runtime_snapshot(self.plan)
        invalid_snapshot["cash_usdt"] = "not-a-decimal"
        invalid_snapshot["snapshot_hash"] = artifact_self_hash(
            invalid_snapshot, "snapshot_hash"
        )

        with self.assertRaisesRegex(
            SystemPaperScheduleError,
            "INPUT_SNAPSHOT_SEMANTIC_INVALID",
        ):
            self.prepare(
                self.claim_current(),
                previous_runtime_snapshot=invalid_snapshot,
            )

    def test_input_prepare_rejects_the_claim_lease_expiry_boundary(self):
        claim = self.claim_current()
        expiry = "2026-08-02T12:20:11.000Z"

        with self.assertRaisesRegex(
            SystemPaperScheduleError,
            "INPUT_CLAIM_LEASE_EXPIRED",
        ):
            self.prepare(
                claim,
                capture=self.capture(captured_at=expiry),
                prepared_at=expiry,
            )
        self.assertEqual(
            self.state.connection.execute("SELECT COUNT(*) FROM prepared_inputs").fetchone()[0],
            0,
        )

    def test_replay_rejects_input_event_at_claim_lease_expiry(self):
        claim = self.claim_current()
        self.state.connection.execute("BEGIN IMMEDIATE")
        self.state._append_locked(
            "INPUT_PREPARED",
            claim.slot,
            claim.lease_expires_at,
            {
                "plan_hash": self.policy.plan_hash,
                "schedule_policy_hash": self.policy.schedule_policy_hash,
                "scheduled_for": claim.slot.scheduled_for,
                "due_at": claim.slot.due_at,
                "expires_at": claim.slot.expires_at,
                "worker_id": claim.worker_id,
                "attempt": claim.attempt,
                "input_sha256": "a" * 64,
            },
        )
        self.state.connection.commit()

        with self.assertRaisesRegex(
            SystemPaperScheduleError,
            "INPUT_CLAIM_LEASE_EXPIRED",
        ):
            self.state.slot_projection()

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
        prepared = self.prepare(claim)
        self.state.connection.execute("DROP TRIGGER prepared_inputs_no_update")
        changed_envelope = deepcopy(prepared["payload"])
        changed_envelope["output_root_hash"] = "0" * 64
        changed_bytes = canonical_json(changed_envelope).encode("utf-8")
        self.state.connection.execute(
            "UPDATE prepared_inputs SET input_bytes=?, input_sha256=?",
            (changed_bytes, hashlib.sha256(changed_bytes).hexdigest()),
        )
        with self.assertRaisesRegex(SystemPaperScheduleError, "INPUT_HASH_MISMATCH"):
            self.state.load_prepared_input(claim.slot)
        self.state.connection.execute(
            "UPDATE prepared_inputs SET input_bytes=?, input_sha256=?",
            (prepared["input_bytes"], prepared["input_sha256"]),
        )
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


class SystemPaperPreparedResultTests(unittest.TestCase):
    """Behavior tests for binding result bytes to durable scheduler inputs."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.plan = build_system_paper_plan()
        self.policy = SystemPaperSchedulePolicy.create(self.plan)
        self.state = SystemPaperScheduleState(
            Path(self.temp.name) / "state.sqlite", self.policy
        )
        self.output_root = Path(self.temp.name) / "results"
        self.output_root.mkdir(mode=0o700)
        os.chmod(self.output_root, 0o700)
        self.output_root_hash = business_hash(
            {
                "purpose": "SYSTEM_PAPER_IMMUTABLE_OUTPUT_ROOT",
                "resolved_path": str(self.output_root.resolve()),
            }
        )

    def tearDown(self) -> None:
        self.state.close()
        self.temp.cleanup()

    def write_result_artifact(self, slot, result_bytes):
        directory = self.output_root / "system-paper-slots"
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        path = directory / f"{slot.slot_id}.json"
        path.write_bytes(result_bytes)
        os.chmod(path, 0o600)
        return path

    def prepare_slot(self, scheduled_for, previous_snapshot):
        slot = self.policy.slot_from_scheduled(scheduled_for)
        claimed_at = slot.due_at
        claim = self.state.claim(slot, worker_id="worker-a", claimed_at=claimed_at)
        input_record = self.state.prepare_input(
            claim,
            plan=self.plan,
            capture=SystemPaperInputCapture(
                public_market_bundle=make_bundle(observed_at=scheduled_for, long_signal=False),
                capture_attempt_id="capture-" + scheduled_for.replace(":", ""),
                captured_at=claimed_at,
                request_families=(
                    "SPOT_AGG_TRADE",
                    "SPOT_BBO",
                    "SPOT_EXCHANGE_INFO",
                    "SPOT_KLINE_4H_WARMUP",
                ),
                network_request_count=4,
            ),
            previous_runtime_snapshot=previous_snapshot,
            fill_scenario=FillScenario.immediate_full(),
            output_root_hash=self.output_root_hash,
            prepared_at=claimed_at,
        )
        payload = input_record["payload"]
        result = run_system_paper_slot(
            SystemPaperSlotInputs(
                plan=payload["plan"],
                scheduled_for=payload["scheduled_for"],
                public_market_bundle=payload["capture"]["public_market_bundle"],
                previous_runtime_snapshot=payload["previous_runtime_snapshot"],
                fill_scenario=FillScenario.immediate_full(),
            )
        )
        return claim, input_record, result

    def test_result_prepare_replays_input_and_full_parent_chain(self):
        # Catches accepting result bytes because their outer hash is self-consistent.
        slot = self.policy.slot_from_scheduled("2026-08-02T12:00:00.000Z")
        claim, _input_record, result = self.prepare_slot(
            slot.scheduled_for,
            build_initial_system_paper_runtime_snapshot(self.plan),
        )

        record = self.state.prepare_result(
            claim,
            result_bytes=canonical_json(result).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=claim.claimed_at,
        )

        self.assertEqual(record["slot_hash"], result["slot_hash"])
        self.assertEqual(
            self.state.slot_projection()[claim.slot.slot_id]["durable_stage"], "RESULT"
        )
        self.assertEqual(self.state.load_prepared_result(claim.slot)["result_bytes"], record["result_bytes"])

    def test_result_prepare_rejects_a_valid_result_from_different_persisted_input(self):
        # Catches loading candidate bytes without binding replay inputs to durable input.
        slot = self.policy.slot_from_scheduled("2026-08-02T12:00:00.000Z")
        claim, _input_record, _result = self.prepare_slot(
            slot.scheduled_for,
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        other = run_system_paper_slot(
            SystemPaperSlotInputs(
                plan=self.plan,
                scheduled_for=slot.scheduled_for,
                public_market_bundle=make_bundle(observed_at=slot.scheduled_for),
                previous_runtime_snapshot=build_initial_system_paper_runtime_snapshot(
                    self.plan
                ),
                fill_scenario=FillScenario.immediate_full(),
            )
        )

        with self.assertRaises(SystemPaperScheduleError):
            self.state.prepare_result(
                claim,
                result_bytes=canonical_json(other).encode("utf-8"),
                parent_result_bodies=(),
                prepared_at=claim.claimed_at,
            )
        self.assertEqual(
            self.state.connection.execute("SELECT COUNT(*) FROM prepared_results").fetchone()[0],
            0,
        )

    def test_successful_parent_chain_rejects_missing_published_artifact(self):
        # Catches deriving parent bodies only from SQLite after publication is lost.
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        self.write_result_artifact(first_claim.slot, first_record["result_bytes"])
        second_claim, _second_input, second = self.prepare_slot(
            "2026-08-02T04:00:00.000Z", first["runtime_snapshot"]
        )
        self.state.prepare_result(
            second_claim,
            result_bytes=canonical_json(second).encode("utf-8"),
            parent_result_bodies=(first_record["result_bytes"],),
            prepared_at=second_claim.claimed_at,
        )
        self.succeed_prepared(second_claim)

        with self.assertRaisesRegex(SystemPaperScheduleError, "RESULT_ARTIFACT_MISSING"):
            self.state.successful_parent_result_bodies(
                self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z"),
                output_root=self.output_root,
            )

    def succeed_prepared(self, claim):
        self.state.connection.execute("BEGIN IMMEDIATE")
        self.state._append_locked(
            "SUCCEEDED",
            claim.slot,
            claim.slot.expires_at,
            {
                "plan_hash": self.policy.plan_hash,
                "schedule_policy_hash": self.policy.schedule_policy_hash,
                "scheduled_for": claim.slot.scheduled_for,
                "due_at": claim.slot.due_at,
                "expires_at": claim.slot.expires_at,
                "worker_id": claim.worker_id,
                "attempt": claim.attempt,
            },
        )
        self.state.connection.commit()

    def prepare_successful_parent_pair(self):
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        first_path = self.write_result_artifact(
            first_claim.slot, first_record["result_bytes"]
        )
        second_claim, _second_input, second = self.prepare_slot(
            "2026-08-02T04:00:00.000Z", first["runtime_snapshot"]
        )
        second_record = self.state.prepare_result(
            second_claim,
            result_bytes=canonical_json(second).encode("utf-8"),
            parent_result_bodies=(first_record["result_bytes"],),
            prepared_at=second_claim.claimed_at,
        )
        self.succeed_prepared(second_claim)
        second_path = self.write_result_artifact(
            second_claim.slot, second_record["result_bytes"]
        )
        return (
            self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z"),
            first_record,
            second_record,
            first_path,
            second_path,
        )

    def test_parent_chain_rejects_replaced_or_unsafe_artifacts(self):
        # Catches accepting mutable, linked, or owner-unsafe published parents.
        target, first, second, first_path, second_path = self.prepare_successful_parent_pair()

        first_path.write_bytes(b"tampered")
        os.chmod(first_path, 0o600)
        with self.assertRaisesRegex(SystemPaperScheduleError, "ARTIFACT_MISMATCH"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        first_path.write_bytes(first["result_bytes"])
        os.chmod(first_path, 0o600)

        second_path.unlink()
        second_path.symlink_to(first_path)
        with self.assertRaisesRegex(SystemPaperScheduleError, "ARTIFACT_UNSAFE"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        second_path.unlink()
        second_path.write_bytes(second["result_bytes"])
        os.chmod(second_path, 0o600)

        second_path.unlink()
        os.link(first_path, second_path)
        with self.assertRaisesRegex(SystemPaperScheduleError, "ARTIFACT_UNSAFE"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        second_path.unlink()
        second_path.write_bytes(second["result_bytes"])
        os.chmod(second_path, 0o600)

        os.chmod(self.output_root, 0o755)
        with self.assertRaisesRegex(SystemPaperScheduleError, "OUTPUT_ROOT_UNSAFE"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        os.chmod(self.output_root, 0o700)
        linked_root = Path(self.temp.name) / "linked-results"
        linked_root.symlink_to(self.output_root, target_is_directory=True)
        with self.assertRaisesRegex(SystemPaperScheduleError, "OUTPUT_ROOT_INVALID"):
            self.state.successful_parent_result_bodies(
                target, output_root=linked_root
            )

    def test_result_prepare_rejects_expired_or_forged_claim_ownership(self):
        # Catches accepting a result after lease loss or from a stale attempt.
        claim, _input, result = self.prepare_slot(
            "2026-08-02T12:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        body = canonical_json(result).encode("utf-8")

        with self.assertRaisesRegex(SystemPaperScheduleError, "RESULT_CLAIM_LEASE_EXPIRED"):
            self.state.prepare_result(
                claim,
                result_bytes=body,
                parent_result_bodies=(),
                prepared_at=claim.lease_expires_at,
            )
        forged = replace(claim, attempt=claim.attempt + 1)
        with self.assertRaisesRegex(SystemPaperScheduleError, "RESULT_CLAIM_INVALID"):
            self.state.prepare_result(
                forged,
                result_bytes=body,
                parent_result_bodies=(),
                prepared_at=claim.claimed_at,
            )
        self.assertEqual(
            self.state.connection.execute("SELECT COUNT(*) FROM prepared_results").fetchone()[0],
            0,
        )

    def test_result_prepare_rolls_back_event_when_result_insert_fails(self):
        # Catches an orphan RESULT_PREPARED event after an atomic insert failure.
        claim, _input, result = self.prepare_slot(
            "2026-08-02T12:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        self.state.connection.execute(
            """
            CREATE TRIGGER fail_prepared_result_insert
            BEFORE INSERT ON prepared_results
            BEGIN SELECT RAISE(ABORT, 'injected result insert failure'); END;
            """
        )

        with self.assertRaises(sqlite3.DatabaseError):
            self.state.prepare_result(
                claim,
                result_bytes=canonical_json(result).encode("utf-8"),
                parent_result_bodies=(),
                prepared_at=claim.claimed_at,
            )
        self.assertEqual(
            self.state.connection.execute(
                "SELECT COUNT(*) FROM schedule_events WHERE event_type='RESULT_PREPARED'"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.state.connection.execute("SELECT COUNT(*) FROM prepared_results").fetchone()[0],
            0,
        )

    def test_result_prepare_rejects_rehashed_unbalanced_candidate(self):
        # Catches trusting recomputed outer hashes without full ledger replay.
        claim, _input, result = self.prepare_slot(
            "2026-08-02T12:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        forged = deepcopy(result)
        forged["ledger"]["credits_usdt"] = "1"
        forged["slot_hash"] = "0" * 64
        forged["runtime_snapshot"]["snapshot_hash"] = "0" * 64
        forged["runtime_snapshot"]["last_slot_hash_or_null"] = "0" * 64
        forged["slot_hash"] = system_paper_slot_hash(forged)
        forged["runtime_snapshot"]["last_slot_hash_or_null"] = forged["slot_hash"]
        forged["runtime_snapshot"]["snapshot_hash"] = artifact_self_hash(
            forged["runtime_snapshot"], "snapshot_hash"
        )

        with self.assertRaisesRegex(SystemPaperScheduleError, "PREPARED_RESULT_INVALID"):
            self.state.prepare_result(
                claim,
                result_bytes=canonical_json(forged).encode("utf-8"),
                parent_result_bodies=(),
                prepared_at=claim.claimed_at,
            )

    def test_unknown_result_persists_only_with_locked_risk_and_active_order(self):
        # Catches loss of UNKNOWN safety invariants across durable preparation.
        slot = self.policy.slot_from_scheduled("2026-08-02T12:00:00.000Z")
        claim = self.state.claim(slot, worker_id="worker-a", claimed_at=slot.due_at)
        input_record = self.state.prepare_input(
            claim,
            plan=self.plan,
            capture=SystemPaperInputCapture(
                public_market_bundle=make_bundle(
                    observed_at=slot.scheduled_for, long_signal=True
                ),
                capture_attempt_id="unknown-capture",
                captured_at=slot.due_at,
                request_families=(
                    "SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_EXCHANGE_INFO",
                    "SPOT_KLINE_4H_WARMUP",
                ),
                network_request_count=4,
            ),
            previous_runtime_snapshot=build_initial_system_paper_runtime_snapshot(self.plan),
            fill_scenario=FillScenario.disconnect_after_submit(),
            output_root_hash=self.output_root_hash,
            prepared_at=slot.due_at,
        )
        payload = input_record["payload"]
        result = run_system_paper_slot(
            SystemPaperSlotInputs(
                plan=payload["plan"],
                scheduled_for=payload["scheduled_for"],
                public_market_bundle=payload["capture"]["public_market_bundle"],
                previous_runtime_snapshot=payload["previous_runtime_snapshot"],
                fill_scenario=FillScenario.disconnect_after_submit(),
            )
        )
        self.assertEqual(result["order"]["state"], "UNKNOWN")
        self.assertEqual(result["runtime_snapshot"]["risk_state"], "LOCKED")
        self.assertIsNotNone(result["runtime_snapshot"]["active_order_or_null"])

        self.state.prepare_result(
            claim,
            result_bytes=canonical_json(result).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=claim.claimed_at,
        )

    def test_successful_parent_bodies_require_complete_adjacent_immutable_chain(self):
        # Catches deriving continuity from a partial chain, non-success, or mutable rows.
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        self.write_result_artifact(first_claim.slot, first_record["result_bytes"])
        second_claim, _second_input, second = self.prepare_slot(
            "2026-08-02T04:00:00.000Z", first["runtime_snapshot"]
        )
        with self.assertRaisesRegex(SystemPaperScheduleError, "PARENT_CHAIN_INVALID"):
            self.state.prepare_result(
                second_claim,
                result_bytes=canonical_json(second).encode("utf-8"),
                parent_result_bodies=(first_record["result_bytes"] + b"\n",),
                prepared_at=second_claim.claimed_at,
            )
        second_record = self.state.prepare_result(
            second_claim,
            result_bytes=canonical_json(second).encode("utf-8"),
            parent_result_bodies=(first_record["result_bytes"],),
            prepared_at=second_claim.claimed_at,
        )
        self.succeed_prepared(second_claim)
        self.write_result_artifact(second_claim.slot, second_record["result_bytes"])
        target = self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z")

        self.assertEqual(
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            ),
            (first_record["result_bytes"], second_record["result_bytes"]),
        )
        with self.assertRaises(sqlite3.DatabaseError):
            self.state.connection.execute(
                "UPDATE prepared_results SET result_sha256='0'"
            )
        with self.assertRaises(sqlite3.DatabaseError):
            self.state.connection.execute("DELETE FROM prepared_results")
        self.state.connection.rollback()

        third_claim, _third_input, third = self.prepare_slot(
            "2026-08-02T08:00:00.000Z", second["runtime_snapshot"]
        )
        third_record = self.state.prepare_result(
            third_claim,
            result_bytes=canonical_json(third).encode("utf-8"),
            parent_result_bodies=(
                first_record["result_bytes"],
                second_record["result_bytes"],
            ),
            prepared_at=third_claim.claimed_at,
        )
        self.succeed_prepared(third_claim)
        self.write_result_artifact(third_claim.slot, third_record["result_bytes"])
        self.assertEqual(
            self.state.successful_parent_result_bodies(
                self.policy.slot_from_scheduled("2026-08-02T12:00:00.000Z"),
                output_root=self.output_root,
            ),
            (
                first_record["result_bytes"],
                second_record["result_bytes"],
                third_record["result_bytes"],
            ),
        )
        with self.assertRaises(SystemPaperScheduleError):
            self.state.successful_parent_result_bodies(
                target, output_root=Path(self.temp.name) / "other-root"
            )
        self.state.connection.execute("DROP TRIGGER prepared_results_no_delete")
        self.state.connection.execute(
            "DELETE FROM prepared_results WHERE slot_id=?", (second_claim.slot.slot_id,)
        )
        with self.assertRaises(SystemPaperScheduleError):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )

    def test_parent_derivation_blocks_missing_and_missed_natural_slots(self):
        # Catches treating merely earlier success as a continuous 4-hour lineage.
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        self.write_result_artifact(first_claim.slot, first_record["result_bytes"])
        target = self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z")

        with self.assertRaisesRegex(SystemPaperScheduleError, "PARENT_CHAIN_INVALID"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        self.state.record_gaps(target, recorded_at=target.due_at)
        with self.assertRaisesRegex(SystemPaperScheduleError, "PARENT_NOT_SUCCEEDED"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )
        self.assertEqual(
            self.state.connection.execute("SELECT result_bytes FROM prepared_results").fetchone()[0],
            first_record["result_bytes"],
        )

    def test_parent_derivation_blocks_expired_predecessor(self):
        # Catches accepting a known-but-expired predecessor as a replay parent.
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        self.write_result_artifact(first_claim.slot, first_record["result_bytes"])
        predecessor = self.policy.slot_from_scheduled("2026-08-02T04:00:00.000Z")
        self.state.claim(
            predecessor, worker_id="worker-a", claimed_at=predecessor.due_at
        )
        target = self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z")
        self.state.record_gaps(target, recorded_at=target.due_at)

        with self.assertRaisesRegex(SystemPaperScheduleError, "PARENT_NOT_SUCCEEDED"):
            self.state.successful_parent_result_bodies(
                target, output_root=self.output_root
            )

    def test_parent_derivation_blocks_failed_predecessor(self):
        # Catches treating a failed attempt as a usable continuity parent.
        first_claim, _first_input, first = self.prepare_slot(
            "2026-08-02T00:00:00.000Z",
            build_initial_system_paper_runtime_snapshot(self.plan),
        )
        first_record = self.state.prepare_result(
            first_claim,
            result_bytes=canonical_json(first).encode("utf-8"),
            parent_result_bodies=(),
            prepared_at=first_claim.claimed_at,
        )
        self.succeed_prepared(first_claim)
        self.write_result_artifact(first_claim.slot, first_record["result_bytes"])
        predecessor = self.policy.slot_from_scheduled("2026-08-02T04:00:00.000Z")
        failed = self.state.claim(
            predecessor, worker_id="worker-a", claimed_at=predecessor.due_at
        )
        self.state.connection.execute("BEGIN IMMEDIATE")
        self.state._append_locked(
            "FAILED",
            predecessor,
            predecessor.due_at,
            {
                "plan_hash": self.policy.plan_hash,
                "schedule_policy_hash": self.policy.schedule_policy_hash,
                "scheduled_for": predecessor.scheduled_for,
                "due_at": predecessor.due_at,
                "expires_at": predecessor.expires_at,
                "worker_id": failed.worker_id,
                "attempt": failed.attempt,
                "reason_code": "SYSTEM_PAPER_RUNTIME_INTERRUPTED",
            },
        )
        self.state.connection.commit()

        with self.assertRaisesRegex(SystemPaperScheduleError, "PARENT_NOT_SUCCEEDED"):
            self.state.successful_parent_result_bodies(
                self.policy.slot_from_scheduled("2026-08-02T08:00:00.000Z"),
                output_root=self.output_root,
            )
