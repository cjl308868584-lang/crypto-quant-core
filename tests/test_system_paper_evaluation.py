"""Fixed-tail System Paper evaluation authority tests."""

import hashlib
import json
import os
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_broker import (
    FillScenario,
    fill_scenario_payload,
)
from crypto_quant.system_paper_evaluation import (
    SystemPaperEvaluationError,
    _SystemPaperCohortSlot,
    _evaluate_complete_system_paper_cohort,
    _maximum_drawdown,
    _three_block_statistics,
    evaluate_system_paper,
    load_system_paper_evaluation,
    observe_system_paper_evaluation_readiness,
)
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)
from crypto_quant.system_paper_runtime import (
    SystemPaperSlotInputs,
    load_system_paper_slot_result_bytes,
    run_system_paper_slot,
)
from crypto_quant.system_paper_start_receipt import (
    SystemPaperStartReceiptError,
    load_system_paper_start_receipt,
    publish_system_paper_start_receipt,
)
import tests.test_system_paper_observer as observer_helpers
import tests.test_system_paper_start_receipt as start_helpers
from tests.test_system_paper_runtime import make_bundle


class SystemPaperEvaluationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.start = start_helpers.SystemPaperStartReceiptTests()
        self.start.setUp()
        self.addCleanup(self.start.doCleanups)
        self.start.observer.create_success()
        published = publish_system_paper_start_receipt(
            **self.start.values(
                observer_helpers.ObserverLaunchctl(
                    self.start.observer.install, runs=1
                ),
                "2026-08-04T08:10:00.000Z",
            )
        )
        self.start_receipt_path = Path(published["receipt_path"])
        preflight = self.start.observer.install.preflight
        self.contract_path = preflight.contract_path
        self.install_receipt_path = self.start.observer.install_receipt_path
        self.runtime_root = preflight.runtime_root
        self.slot_root = self.runtime_root / "artifacts" / "system-paper-slots"
        self.output_root = self.runtime_root / "evaluations"
        self.plan_path = self.runtime_root / "system-paper-plan.json"
        self.plan_path.write_bytes(
            canonical_json(build_system_paper_plan()).encode("utf-8")
        )
        self.plan_path.chmod(0o600)

    def values(self, **overrides):
        values = {
            "plan_path": self.plan_path,
            "start_receipt_path": self.start_receipt_path,
            "install_receipt_path": self.install_receipt_path,
            "contract_path": self.contract_path,
            "slot_root": self.slot_root,
            "runtime_root": self.runtime_root,
            "output_root": self.output_root,
            "_clock": lambda: "2026-08-05T08:10:00.000Z",
            "_machine_probe": self.start.observer.install.preflight.machine,
            "_filesystem_probe": (
                self.start.observer.install.preflight.filesystem
            ),
        }
        values.update(overrides)
        return values

    def mutate_state_metadata(self, table, column, value):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            connection.execute(
                "UPDATE " + table + " SET " + column + "=?",
                (value,),
            )
            for _name, sql in triggers:
                connection.execute(sql)

    def remove_result_constraints_and_duplicate_row(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            connection.execute(
                "ALTER TABLE prepared_results RENAME TO old_prepared_results"
            )
            connection.execute(
                "CREATE TABLE prepared_results ("
                "source_event_id TEXT, slot_id TEXT, result_bytes BLOB, "
                "result_sha256 TEXT, slot_hash TEXT, runtime_snapshot_hash TEXT, "
                "parent_slot_hash TEXT, output_root_hash TEXT)"
            )
            columns = (
                "source_event_id, slot_id, result_bytes, result_sha256, "
                "slot_hash, runtime_snapshot_hash, parent_slot_hash, "
                "output_root_hash"
            )
            connection.execute(
                "INSERT INTO prepared_results (" + columns + ") SELECT "
                + columns
                + " FROM old_prepared_results"
            )
            connection.execute(
                "INSERT INTO prepared_results (" + columns + ") SELECT "
                + columns
                + " FROM old_prepared_results"
            )
            connection.execute("DROP TABLE old_prepared_results")
            for _name, sql in triggers:
                connection.execute(sql)

    @staticmethod
    def utc_text(value):
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def extend_to_complete_cohort(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        start_receipt = json.loads(self.start_receipt_path.read_bytes())
        started = datetime.fromisoformat(
            start_receipt["cohort_started_at"].replace("Z", "+00:00")
        )
        first_path = Path(start_receipt["first_slot"]["result_path"])
        first_body = first_path.read_bytes()
        previous_result = load_system_paper_slot_result_bytes(first_body)
        previous_snapshot = previous_result["runtime_snapshot"]
        output_root = self.slot_root.parent
        output_root_hash = business_hash(
            {
                "purpose": "SYSTEM_PAPER_IMMUTABLE_OUTPUT_ROOT",
                "resolved_path": str(output_root.resolve()),
            }
        )
        scenario = FillScenario.immediate_full()
        scenario_payload = fill_scenario_payload(scenario)
        request_families = [
            "SPOT_AGG_TRADE",
            "SPOT_BBO",
            "SPOT_EXCHANGE_INFO",
            "SPOT_KLINE_4H_WARMUP",
        ]
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            last = connection.execute(
                "SELECT sequence, event_hash FROM schedule_events "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = int(last["sequence"])
            previous_event_hash = last["event_hash"]

            def append_event(event_type, slot, event_time, payload):
                nonlocal sequence, previous_event_hash
                sequence += 1
                normalized = json.loads(canonical_json(payload))
                payload_hash = business_hash(normalized)
                identity = {
                    "sequence": sequence,
                    "event_type": event_type,
                    "slot_id": slot.slot_id,
                    "event_time": event_time,
                    "payload_hash": payload_hash,
                    "previous_event_hash": previous_event_hash,
                }
                event_id = stable_id("system_paper_schedule_event", identity)
                body = {
                    "sequence": sequence,
                    "event_id": event_id,
                    "event_type": event_type,
                    "slot_id": slot.slot_id,
                    "event_time": event_time,
                    "payload": normalized,
                    "payload_hash": payload_hash,
                    "previous_event_hash": previous_event_hash,
                }
                event_hash = business_hash(body)
                connection.execute(
                    "INSERT INTO schedule_events (event_id, event_type, slot_id, "
                    "event_time, payload_json, payload_hash, previous_event_hash, "
                    "event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_id,
                        event_type,
                        slot.slot_id,
                        event_time,
                        canonical_json(normalized),
                        payload_hash,
                        previous_event_hash,
                        event_hash,
                    ),
                )
                previous_event_hash = event_hash
                return event_id

            for index in range(1, 540):
                scheduled = started + timedelta(hours=4 * index)
                scheduled_for = self.utc_text(scheduled)
                slot = policy.slot_from_scheduled(scheduled_for)
                sampled = scheduled + timedelta(minutes=5, seconds=11)
                sampled_at = self.utc_text(sampled)
                captured_at = self.utc_text(sampled + timedelta(seconds=1))
                lease_expires_at = self.utc_text(sampled + timedelta(minutes=15))
                bundle = make_bundle(
                    scheduled_for=scheduled_for,
                    captured_at=captured_at,
                )
                slot_core = {
                    "plan_hash": policy.plan_hash,
                    "schedule_policy_hash": policy.schedule_policy_hash,
                    "scheduled_for": slot.scheduled_for,
                    "due_at": slot.due_at,
                    "expires_at": slot.expires_at,
                }
                worker_id = "observer-fixture-worker"
                append_event(
                    "CLAIMED",
                    slot,
                    sampled_at,
                    {
                        **slot_core,
                        "worker_id": worker_id,
                        "attempt": 1,
                        "lease_expires_at": lease_expires_at,
                    },
                )
                capture_payload = {
                    "public_market_bundle": bundle,
                    "capture_attempt_id": "capture-" + slot.slot_id[-12:],
                    "captured_at": captured_at,
                    "request_families": request_families,
                    "network_request_count": 4,
                }
                envelope = {
                    "schema_version": "1.0.0",
                    "slot_id": slot.slot_id,
                    "schedule_policy_hash": policy.schedule_policy_hash,
                    "plan": plan,
                    "scheduled_for": scheduled_for,
                    "capture": capture_payload,
                    "previous_runtime_snapshot": previous_snapshot,
                    "fill_scenario": scenario_payload,
                    "output_root_hash": output_root_hash,
                }
                input_bytes = canonical_json(envelope).encode("utf-8")
                input_sha256 = hashlib.sha256(input_bytes).hexdigest()
                input_hashes = {
                    "plan_hash": plan["plan_hash"],
                    "market_bundle_hash": bundle["bundle_hash"],
                    "previous_snapshot_hash": previous_snapshot["snapshot_hash"],
                    "fill_scenario_hash": business_hash(scenario_payload),
                    "output_root_hash": output_root_hash,
                }
                input_event_id = append_event(
                    "INPUT_PREPARED",
                    slot,
                    sampled_at,
                    {
                        **slot_core,
                        "worker_id": worker_id,
                        "attempt": 1,
                        "input_sha256": input_sha256,
                        **input_hashes,
                    },
                )
                connection.execute(
                    "INSERT INTO prepared_inputs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        input_event_id,
                        slot.slot_id,
                        input_bytes,
                        input_sha256,
                        input_hashes["plan_hash"],
                        input_hashes["market_bundle_hash"],
                        input_hashes["previous_snapshot_hash"],
                        input_hashes["fill_scenario_hash"],
                        output_root_hash,
                    ),
                )
                result = run_system_paper_slot(
                    SystemPaperSlotInputs(
                        plan=plan,
                        scheduled_for=scheduled_for,
                        public_market_bundle=bundle,
                        previous_runtime_snapshot=previous_snapshot,
                        fill_scenario=scenario,
                    )
                )
                result_bytes = canonical_json(result).encode("utf-8")
                result_sha256 = hashlib.sha256(result_bytes).hexdigest()
                parent_hash = result["parent_slot_hash_or_null"] or "0" * 64
                result_hashes = {
                    "result_sha256": result_sha256,
                    "slot_hash": result["slot_hash"],
                    "runtime_snapshot_hash": result["runtime_snapshot"][
                        "snapshot_hash"
                    ],
                    "parent_slot_hash": parent_hash,
                    "output_root_hash": output_root_hash,
                }
                result_event_id = append_event(
                    "RESULT_PREPARED",
                    slot,
                    sampled_at,
                    {
                        **slot_core,
                        "worker_id": worker_id,
                        "attempt": 1,
                        **result_hashes,
                    },
                )
                connection.execute(
                    "INSERT INTO prepared_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        result_event_id,
                        slot.slot_id,
                        result_bytes,
                        result_sha256,
                        result_hashes["slot_hash"],
                        result_hashes["runtime_snapshot_hash"],
                        parent_hash,
                        output_root_hash,
                    ),
                )
                artifact_path = self.slot_root / (slot.slot_id + ".json")
                artifact_path.write_bytes(result_bytes)
                artifact_path.chmod(0o600)
                append_event(
                    "SUCCEEDED",
                    slot,
                    sampled_at,
                    {
                        **slot_core,
                        "worker_id": worker_id,
                        "attempt": 1,
                        "result_sha256": result_sha256,
                        "runtime_snapshot_hash": result_hashes[
                            "runtime_snapshot_hash"
                        ],
                        "output_root_hash": output_root_hash,
                    },
                )
                previous_result = result
                previous_snapshot = result["runtime_snapshot"]
        for path in state_path.parent.glob(state_path.name + "*"):
            path.chmod(0o600)
        self.assertEqual(len(tuple(self.slot_root.iterdir())), 540)
        return previous_result

    def cohort_slot(self, index):
        start_receipt = json.loads(self.start_receipt_path.read_bytes())
        started = datetime.fromisoformat(
            start_receipt["cohort_started_at"].replace("Z", "+00:00")
        )
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        return policy.slot_from_scheduled(
            self.utc_text(started + timedelta(hours=4 * index))
        )

    def assert_post_tail_incomplete(self):
        result = observe_system_paper_evaluation_readiness(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        self.assertEqual(
            result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        )
        self.assertEqual(
            result["reason_code"],
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
        )
        self.assertEqual(result["expected_slot_count"], 540)
        return result

    def mutate_prepared_bytes(self, table, column, slot_index, body):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            connection.execute(
                "UPDATE " + table + " SET " + column + "=? WHERE slot_id=?",
                (body, self.cohort_slot(slot_index).slot_id),
            )
            for _name, sql in triggers:
                connection.execute(sql)

    def mutate_slot_artifact(self, slot_index, transform):
        path = self.slot_root / (self.cohort_slot(slot_index).slot_id + ".json")
        value = json.loads(path.read_bytes())
        transform(value)
        path.write_bytes(canonical_json(value).encode("utf-8"))
        path.chmod(0o600)

    def assert_post_tail_replay_invalid(self):
        result = observe_system_paper_evaluation_readiness(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        self.assertEqual(
            result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        )
        self.assertEqual(
            result["reason_code"],
            "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID",
        )
        self.assertEqual(result["expected_slot_count"], 540)
        return result

    def assert_post_tail_authority_invalid(self):
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "AUTHORITY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )

    def economic_cohort(self, *, block_return="0.01", mutate=None):
        rate = Decimal(block_return)
        first = Decimal("1000") * (Decimal("1") + rate)
        second = first * (Decimal("1") + rate)
        third = second * (Decimal("1") + rate)
        equities = [first] * 180 + [second] * 180 + [third] * 180
        cohort = []
        previous_position = "0"
        previous_active = None
        for index, equity in enumerate(equities):
            slot_id = "slot-" + str(index)
            scheduled_for = self.utc_text(
                datetime(2026, 8, 4, 8, tzinfo=timezone.utc)
                + timedelta(hours=4 * index)
            )
            result = {
                "slot_id": slot_id,
                "scheduled_for": scheduled_for,
                "market_bundle_hash": "bundle-" + str(index),
                "signal": {"decision_hash": "decision-" + str(index)},
                "risk": {
                    "state": "NORMAL",
                    "drawdown_state": "NORMAL",
                },
                "order": None,
                "ledger": {
                    "entries": [],
                    "balanced": True,
                    "debits_usdt": "0",
                    "credits_usdt": "0",
                },
                "reconciliation": {
                    "unexplained_position_difference": "0",
                    "ledger_imbalance_usdt": "0",
                    "status": "RECONCILED",
                },
                "runtime_snapshot": {
                    "marked_equity_usdt": str(equity),
                    "position_quantity": previous_position,
                    "active_order_or_null": previous_active,
                    "risk_state": "NORMAL",
                },
                "replay_inputs": {
                    "previous_runtime_snapshot": {
                        "position_quantity": previous_position,
                        "active_order_or_null": previous_active,
                    },
                    "public_market_bundle": {
                        "bundle_hash": "bundle-" + str(index),
                        "bbo": {
                            "bid_price": "100.1",
                            "ask_price": "99.9",
                        },
                    },
                },
                "replay": {
                    "decision_hash_match": True,
                    "market_bundle_hash_match": True,
                    "full_slot_hash_match": True,
                },
                "safety_counts": {
                    "credential_reads": 0,
                    "account_requests": 0,
                    "real_broker_calls": 0,
                    "real_order_writes": 0,
                },
            }
            if mutate is not None:
                mutate(index, result)
            previous_position = result["runtime_snapshot"]["position_quantity"]
            previous_active = result["runtime_snapshot"][
                "active_order_or_null"
            ]
            envelope = {
                "capture": {
                    "public_market_bundle": result["replay_inputs"][
                        "public_market_bundle"
                    ]
                }
            }
            cohort.append(
                _SystemPaperCohortSlot(
                    slot_id=slot_id,
                    scheduled_for=scheduled_for,
                    artifact_path="/tmp/" + slot_id + ".json",
                    artifact_sha256="0" * 64,
                    input_bytes=canonical_json(envelope).encode("utf-8"),
                    result_bytes=canonical_json(result).encode("utf-8"),
                    slot_hash="1" * 64,
                    runtime_snapshot_hash="2" * 64,
                )
            )
        return tuple(cohort)

    @staticmethod
    def add_synthetic_fill(
        result,
        *,
        event_id,
        side="BUY",
        fill_price="100",
        fee="0",
        recorded=True,
    ):
        result["order"] = {
            "local_order_id": "order-" + event_id,
            "side": side,
            "filled_quantity": "1",
            "average_fill_price_or_null": fill_price,
            "fee_usdt": fee,
            "event_ids": [event_id],
        }
        result["ledger"]["entries"] = (
            [{"entry_id": "ledger-" + event_id}] if recorded else []
        )
        result["runtime_snapshot"]["position_quantity"] = (
            "1" if side == "BUY" else "0"
        )

    def test_pre_tail_observation_is_allowlisted_and_reads_no_slot_economics(self):
        forbidden = AssertionError("pre-tail economic or publication path called")
        with patch(
            "crypto_quant.system_paper_scheduler."
            "load_system_paper_slot_result_bytes",
            side_effect=forbidden,
        ), patch(
            "crypto_quant.system_paper_start_receipt."
            "replay_system_paper_first_slot_evidence",
            side_effect=forbidden,
        ) as start_replay, patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            side_effect=forbidden,
        ) as economic, patch(
            "crypto_quant.system_paper_evaluation.publish_owner_exact",
            side_effect=forbidden,
        ) as publisher:
            result = observe_system_paper_evaluation_readiness(**self.values())

        self.assertEqual(
            set(result),
            {
                "status",
                "observed_at",
                "cohort_started_at",
                "tail_end",
                "elapsed_days",
                "verified_terminal_slot_count",
                "incident_count",
                "next_required_slot",
                "evidence_health",
            },
        )
        self.assertEqual(
            result["status"], "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL"
        )
        self.assertEqual(result["elapsed_days"], 1)
        self.assertEqual(result["verified_terminal_slot_count"], 1)
        self.assertEqual(result["incident_count"], 0)
        self.assertEqual(result["evidence_health"], "VERIFIED")
        self.assertFalse(self.output_root.exists())
        start_replay.assert_not_called()
        economic.assert_not_called()
        publisher.assert_not_called()
        encoded = canonical_json(result).lower()
        for forbidden_name in (
            "pnl",
            "return",
            "win_rate",
            "drawdown",
            "cost",
            "profit",
            "confidence",
        ):
            self.assertNotIn(forbidden_name, encoded)

    def test_absent_state_sidecar_appearing_during_replay_fails_closed(self):
        from crypto_quant import system_paper_evaluation as module

        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        wal_path = Path(str(state_path) + "-wal")
        shm_path = Path(str(state_path) + "-shm")
        for path in (wal_path, shm_path):
            if path.exists():
                path.unlink()
        original = module._copy_event_metadata

        def replay_then_create(*args, **kwargs):
            replay = original(*args, **kwargs)
            wal_path.write_bytes(b"appeared-during-replay")
            wal_path.chmod(0o600)
            return replay

        with patch.object(
            module, "_copy_event_metadata", side_effect=replay_then_create
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_sidecar_created_between_file_open_and_absence_capture_fails_closed(self):
        from crypto_quant import system_paper_evaluation as module

        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        wal_path = Path(str(state_path) + "-wal")
        shm_path = Path(str(state_path) + "-shm")
        for path in (wal_path, shm_path):
            if path.exists():
                path.unlink()
        original_open = module._RetainedAuthorityFile.open
        created = {"done": False}

        def open_then_create(path, **kwargs):
            if Path(path) == wal_path and not created["done"]:
                created["done"] = True
                wal_path.write_bytes(b"appeared-before-absence-capture")
                wal_path.chmod(0o600)
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return original_open(path, **kwargs)

        with patch.object(
            module._RetainedAuthorityFile,
            "open",
            side_effect=open_then_create,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_coordinated_prepared_input_metadata_mutation(self):
        self.mutate_state_metadata("prepared_inputs", "plan_hash", "0" * 64)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_coordinated_prepared_result_metadata_mutation(self):
        self.mutate_state_metadata("prepared_results", "slot_hash", "0" * 64)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_removed_constraints_and_duplicate_prepared_rows(self):
        self.remove_result_constraints_and_duplicate_row()
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_incident_count_includes_failed_attempt_events(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with SystemPaperScheduleState(state_path, policy) as state:
            slot = policy.slot_from_scheduled("2026-08-04T12:00:00.000Z")
            claim = state.claim(
                slot,
                worker_id="failed-attempt-test",
                claimed_at="2026-08-04T12:05:01.000Z",
            )
            state.fail(
                claim,
                reason_code="SYSTEM_PAPER_RUNTIME_INTERRUPTED",
                failed_at="2026-08-04T12:05:02.000Z",
            )
        result = observe_system_paper_evaluation_readiness(**self.values())
        self.assertEqual(result["verified_terminal_slot_count"], 1)
        self.assertEqual(result["incident_count"], 1)
        self.assertEqual(result["evidence_health"], "INCIDENT_DETECTED")

    def test_all_seven_authority_paths_must_be_absolute_and_exact(self):
        path_names = (
            "plan_path",
            "start_receipt_path",
            "install_receipt_path",
            "contract_path",
            "slot_root",
            "runtime_root",
            "output_root",
        )
        for name in path_names:
            with self.subTest(name=name), self.assertRaisesRegex(
                SystemPaperEvaluationError, "PATH_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(**{name: Path("relative")})
                )
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "ROOT_MISMATCH"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(runtime_root=self.runtime_root / "other")
            )
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "ROOT_MISMATCH"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(slot_root=self.runtime_root / "artifacts")
            )

    def test_install_preview_is_bounded_before_json_parse(self):
        oversized = self.runtime_root / "oversized-install.json"
        with oversized.open("wb") as handle:
            handle.truncate(2 * 1024 * 1024 + 1)
        oversized.chmod(0o600)
        original_read_bytes = Path.read_bytes
        calls = {"oversized": 0}

        def reject_path_read(candidate):
            if candidate == oversized:
                calls["oversized"] += 1
                raise AssertionError("oversized install preview was read")
            return original_read_bytes(candidate)

        with patch.object(Path, "read_bytes", reject_path_read):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "INSTALL_PREVIEW_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(install_receipt_path=oversized)
                )
        self.assertEqual(calls["oversized"], 0)

    def test_install_preview_rejects_noncanonical_bytes_before_strict_loader(self):
        noncanonical = self.runtime_root / "noncanonical-install.json"
        noncanonical.write_bytes(b'{"preflight_receipt": {"receipt_path": "/x"}}\n')
        noncanonical.chmod(0o600)
        with patch(
            "crypto_quant.system_paper_evaluation."
            "load_system_paper_install_receipt",
            side_effect=AssertionError("strict loader reached"),
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "INSTALL_PREVIEW_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(install_receipt_path=noncanonical)
                )

    def test_install_preview_cannot_redirect_derived_authority(self):
        original_bytes = self.install_receipt_path.read_bytes()
        forged = json.loads(original_bytes)
        redirected_target = Path(
            json.loads(self.start_receipt_path.read_bytes())["first_slot"][
                "result_path"
            ]
        )
        forged["target_path"] = str(redirected_target)
        identity = {
            "contract_hash": forged["source_contract"]["contract_hash"],
            "preflight_receipt_hash": forged["preflight_receipt"]["receipt_hash"],
            "target_path": forged["target_path"],
            "target_inode": forged["target_stat"]["inode"],
            "install_action": forged["install_action"],
            "installed_at": forged["installed_at"],
            "verified_at": forged["verified_at"],
            "installation_status": forged["installation_status"],
        }
        forged["receipt_id"] = stable_id(
            "system_paper_install_receipt", identity
        )
        forged["receipt_hash"] = artifact_self_hash(forged, "receipt_hash")
        original_stash = self.runtime_root / "original-install-receipt.json"
        self.install_receipt_path.rename(original_stash)
        forged_path = self.install_receipt_path.parent / (
            forged["receipt_id"] + ".json"
        )
        forged_path.write_bytes(canonical_json(forged).encode("utf-8"))
        forged_path.chmod(0o600)
        from crypto_quant import system_paper_install as install_module

        original_target_stat = install_module._target_stat
        redirected_reads = {"count": 0}

        def reject_redirected_target(path, *args, **kwargs):
            if Path(path) == redirected_target:
                redirected_reads["count"] += 1
                raise AssertionError("redirected target was opened")
            return original_target_stat(path, *args, **kwargs)

        try:
            with patch.object(
                install_module,
                "_target_stat",
                side_effect=reject_redirected_target,
            ):
                with self.assertRaises(SystemPaperEvaluationError):
                    observe_system_paper_evaluation_readiness(
                        **self.values(install_receipt_path=forged_path)
                    )
        finally:
            if forged_path.exists():
                forged_path.unlink()
            original_stash.rename(self.install_receipt_path)
            self.install_receipt_path.write_bytes(original_bytes)
            self.install_receipt_path.chmod(0o600)
        self.assertEqual(redirected_reads["count"], 0)

    def test_source_replacement_after_capture_fails_before_return(self):
        from crypto_quant import system_paper_evaluation as module

        original_open = module._RetainedAuthorityFile.open
        captured = {"plan": 0}
        plan_bytes = self.plan_path.read_bytes()
        original_inode = self.plan_path.stat().st_ino

        def retain_then_replace(path, **kwargs):
            retained = original_open(path, **kwargs)
            if Path(path) == self.plan_path and captured["plan"] == 0:
                captured["plan"] += 1
                moved = self.plan_path.with_suffix(".retained-original")
                self.plan_path.rename(moved)
                self.plan_path.write_bytes(plan_bytes)
                self.plan_path.chmod(0o600)
                self.assertNotEqual(self.plan_path.stat().st_ino, original_inode)
            return retained

        with patch.object(
            module._RetainedAuthorityFile,
            "open",
            side_effect=retain_then_replace,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_installed_target_is_retained_through_state_replay(self):
        from crypto_quant import system_paper_evaluation as module

        install = json.loads(self.install_receipt_path.read_bytes())
        target_path = Path(install["target_path"])
        target_bytes = target_path.read_bytes()
        original = module._copy_event_metadata

        def replay_then_replace(*args, **kwargs):
            replay = original(*args, **kwargs)
            retained_name = target_path.with_suffix(".evaluation-retained")
            target_path.rename(retained_name)
            target_path.write_bytes(target_bytes)
            target_path.chmod(0o600)
            return replay

        with patch.object(
            module, "_copy_event_metadata", side_effect=replay_then_replace
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_post_tail_result_reverifies_all_retained_sources_before_return(self):
        self.extend_to_complete_cohort()
        plan_bytes = self.plan_path.read_bytes()

        def mutate_then_return(**_kwargs):
            retained_name = self.plan_path.with_suffix(".post-tail-retained")
            self.plan_path.rename(retained_name)
            self.plan_path.write_bytes(plan_bytes)
            self.plan_path.chmod(0o600)
            return {"status": "POST_TAIL_TEST_RESULT"}

        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            new=mutate_then_return,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(
                        _clock=lambda: "2026-11-02T08:05:00.000Z"
                    )
                )

    def test_post_tail_incomplete_cohort_stops_before_economic_evaluation(self):
        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            side_effect=AssertionError("economic evaluation reached"),
        ):
            result = observe_system_paper_evaluation_readiness(
                **self.values(
                    _clock=lambda: "2026-11-02T08:05:00.000Z"
                )
            )
        self.assertEqual(
            result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        )
        self.assertEqual(
            result["reason_code"],
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
        )

    def test_post_tail_failed_attempt_is_incomplete(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        with SystemPaperScheduleState(state_path, policy) as state:
            slot = self.cohort_slot(1)
            claim = state.claim(
                slot,
                worker_id="failed-cohort-test",
                claimed_at="2026-08-04T12:05:01.000Z",
            )
            state.fail(
                claim,
                reason_code="SYSTEM_PAPER_RUNTIME_INTERRUPTED",
                failed_at="2026-08-04T12:05:02.000Z",
            )
        self.assert_post_tail_incomplete()

    def test_post_tail_missed_slot_is_incomplete(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        with SystemPaperScheduleState(state_path, policy) as state:
            state.record_gaps(
                self.cohort_slot(2),
                recorded_at="2026-08-04T16:05:01.000Z",
            )
        self.assert_post_tail_incomplete()

    def test_post_tail_expired_slot_is_incomplete(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        with SystemPaperScheduleState(state_path, policy) as state:
            state.claim(
                self.cohort_slot(1),
                worker_id="expired-cohort-test",
                claimed_at="2026-08-04T12:05:01.000Z",
            )
            state.record_gaps(
                self.cohort_slot(2),
                recorded_at="2026-08-04T16:05:01.000Z",
            )
        self.assert_post_tail_incomplete()

    def test_post_tail_nonterminal_slot_is_incomplete(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        with SystemPaperScheduleState(state_path, policy) as state:
            state.claim(
                self.cohort_slot(1),
                worker_id="nonterminal-cohort-test",
                claimed_at="2026-08-04T12:05:01.000Z",
            )
        self.assert_post_tail_incomplete()

    def test_post_tail_complete_cohort_replays_before_economic_evaluation(self):
        self.extend_to_complete_cohort()

        def summarize_cohort(**kwargs):
            cohort = kwargs["cohort"]
            self.assertEqual(len(cohort), 540)
            self.assertTrue(all(hasattr(item, "result_bytes") for item in cohort))
            return {
                "status": "TASK_2_COHORT_REPLAYED",
                "slot_count": len(cohort),
                "first_slot_id": cohort[0].slot_id,
                "last_slot_id": cohort[-1].slot_id,
            }

        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            new=summarize_cohort,
        ):
            result = observe_system_paper_evaluation_readiness(
                **self.values(
                    _clock=lambda: "2026-11-02T08:05:00.000Z"
                )
            )
        self.assertEqual(result["slot_count"], 540)
        self.assertEqual(
            result["first_slot_id"],
            json.loads(self.start_receipt_path.read_bytes())["first_slot"][
                "slot_id"
            ],
        )

    def test_post_tail_real_cohort_reaches_one_truthful_gate_result(self):
        self.extend_to_complete_cohort()
        result = observe_system_paper_evaluation_readiness(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        self.assertIn(
            result["status"],
            ("SYSTEM_PAPER_GATE_PASS", "SYSTEM_PAPER_GATE_DID_NOT_PASS"),
        )
        self.assertEqual(result["slot_count"], 540)
        self.assertEqual(
            set(result["gates"]),
            {"safety", "cost", "drawdown", "block_return"},
        )

    def test_final_evaluation_is_immutable_and_loader_replays_original_inputs(self):
        """Removing the full replay, or binding the id to the call clock, breaks this."""
        self.extend_to_complete_cohort()
        first = evaluate_system_paper(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        second = evaluate_system_paper(
            **self.values(_clock=lambda: "2026-11-03T08:05:00.000Z")
        )
        self.assertEqual(first, second)
        self.assertIn(
            first["status"],
            ("SYSTEM_PAPER_GATE_PASS", "SYSTEM_PAPER_GATE_DID_NOT_PASS"),
        )
        result_path = self.output_root / (first["result_id"] + ".json")
        self.assertEqual(
            load_system_paper_evaluation(
                evaluation_path=result_path,
                _machine_probe=self.start.observer.install.preflight.machine,
                _filesystem_probe=self.start.observer.install.preflight.filesystem,
            ),
            first,
        )
        forged = json.loads(result_path.read_text())
        forged["gates"]["cost"]["passed"] = not forged["gates"]["cost"]["passed"]
        forged["result_hash"] = artifact_self_hash(forged, "result_hash")
        result_path.unlink()
        result_path.write_bytes(canonical_json(forged).encode("utf-8"))
        result_path.chmod(0o600)
        with self.assertRaisesRegex(SystemPaperEvaluationError, "RESULT_INVALID"):
            load_system_paper_evaluation(
                evaluation_path=result_path,
                _machine_probe=self.start.observer.install.preflight.machine,
                _filesystem_probe=self.start.observer.install.preflight.filesystem,
            )

    def test_final_schema_rejects_float_unknown_field_bad_gate_and_claim_inflation(self):
        """A permissive Schema would admit altered final research claims."""
        from crypto_quant.system_paper_evaluation import _evaluation_validator

        self.extend_to_complete_cohort()
        artifact = evaluate_system_paper(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        cases = []
        unknown = json.loads(canonical_json(artifact))
        unknown["unreviewed_claim"] = True
        cases.append(unknown)
        floating = json.loads(canonical_json(artifact))
        floating["gates"]["cost"]["maximum_effective_fee_rate"] = 0.0001
        cases.append(floating)
        malformed_gate = json.loads(canonical_json(artifact))
        del malformed_gate["gates"]["drawdown"]["passed"]
        cases.append(malformed_gate)
        inflated = json.loads(canonical_json(artifact))
        inflated["security_counts"]["real_order_writes"] = 1
        cases.append(inflated)
        for forged in cases:
            with self.subTest(forged=forged):
                self.assertTrue(tuple(_evaluation_validator().iter_errors(forged)))

    def test_loader_replay_has_no_publication_side_effect(self):
        """A loader must be able to verify an artifact while publication is forbidden."""
        self.extend_to_complete_cohort()
        artifact = evaluate_system_paper(
            **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
        )
        path = self.output_root / (artifact["result_id"] + ".json")
        with patch(
            "crypto_quant.system_paper_evaluation.publish_owner_exact",
            side_effect=AssertionError("loader published"),
        ), patch(
            "crypto_quant.system_paper_evaluation._secure_output_root",
            side_effect=AssertionError("loader created output root"),
        ):
            self.assertEqual(
                load_system_paper_evaluation(
                    evaluation_path=path,
                    _machine_probe=self.start.observer.install.preflight.machine,
                    _filesystem_probe=self.start.observer.install.preflight.filesystem,
                ),
                artifact,
            )

    def test_post_tail_tampered_artifact_stops_before_economic_evaluation(self):
        self.extend_to_complete_cohort()
        middle = sorted(self.slot_root.iterdir())[270]
        middle.write_bytes(b"{}")
        middle.chmod(0o600)
        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            side_effect=AssertionError("economic evaluation reached"),
        ):
            result = observe_system_paper_evaluation_readiness(
                **self.values(
                    _clock=lambda: "2026-11-02T08:05:00.000Z"
                )
            )
        self.assertEqual(
            result["status"], "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        )
        self.assertIn(
            result["reason_code"],
            (
                "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
                "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID",
            ),
        )

    def test_post_tail_prepared_input_byte_mutation_fails_authority(self):
        self.extend_to_complete_cohort()
        self.mutate_prepared_bytes(
            "prepared_inputs", "input_bytes", 270, b"{}"
        )
        self.assert_post_tail_authority_invalid()

    def test_start_loader_rejects_later_prepared_blob_mutation(self):
        self.extend_to_complete_cohort()
        self.mutate_prepared_bytes(
            "prepared_inputs", "input_bytes", 270, b"{}"
        )
        preflight = self.start.observer.install.preflight
        with self.assertRaises(SystemPaperStartReceiptError):
            load_system_paper_start_receipt(
                receipt_path=self.start_receipt_path,
                contract_path=self.contract_path,
                plist_path=preflight.plist_path,
                preflight_receipt_path=self.start.observer.preflight_path,
                install_receipt_path=self.install_receipt_path,
                _machine_probe=preflight.machine,
                _filesystem_probe=preflight.filesystem,
            )

    def test_post_tail_prepared_result_byte_mutation_fails_authority(self):
        self.extend_to_complete_cohort()
        self.mutate_prepared_bytes(
            "prepared_results", "result_bytes", 270, b"{}"
        )
        self.assert_post_tail_authority_invalid()

    def test_post_tail_output_root_identity_mutation_fails_authority(self):
        self.extend_to_complete_cohort()
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        slot_id = self.cohort_slot(270).slot_id
        with sqlite3.connect(str(state_path)) as connection:
            body = connection.execute(
                "SELECT input_bytes FROM prepared_inputs WHERE slot_id=?",
                (slot_id,),
            ).fetchone()[0]
        envelope = json.loads(body)
        envelope["output_root_hash"] = "0" * 64
        self.mutate_prepared_bytes(
            "prepared_inputs",
            "input_bytes",
            270,
            canonical_json(envelope).encode("utf-8"),
        )
        self.assert_post_tail_authority_invalid()

    def test_post_tail_snapshot_prefix_mutation_fails_replay(self):
        self.extend_to_complete_cohort()

        def remove_prefix_item(value):
            value["runtime_snapshot"]["processed_slot_ids"].pop()

        self.mutate_slot_artifact(270, remove_prefix_item)
        self.assert_post_tail_replay_invalid()

    def test_post_tail_parent_mismatch_fails_replay(self):
        self.extend_to_complete_cohort()

        def break_parent(value):
            value["parent_slot_hash_or_null"] = "0" * 64

        self.mutate_slot_artifact(270, break_parent)
        self.assert_post_tail_replay_invalid()

    def test_post_tail_event_hash_mutation_fails_state_replay(self):
        self.extend_to_complete_cohort()
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            sequence = connection.execute(
                "SELECT sequence FROM schedule_events ORDER BY sequence "
                "LIMIT 1 OFFSET 1000"
            ).fetchone()[0]
            connection.execute(
                "UPDATE schedule_events SET event_hash=? WHERE sequence=?",
                ("0" * 64, sequence),
            )
            for _name, sql in triggers:
                connection.execute(sql)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )

    def test_post_tail_wrong_first_receipt_fails_before_cohort(self):
        receipt = json.loads(self.start_receipt_path.read_bytes())
        receipt["first_slot"]["result_sha256"] = "0" * 64
        receipt["observation"]["first_slot"]["result_sha256"] = "0" * 64
        receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
        self.start_receipt_path.write_bytes(
            canonical_json(receipt).encode("utf-8")
        )
        self.start_receipt_path.chmod(0o600)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "AUTHORITY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )

    def test_post_tail_misaligned_cohort_start_fails_authority(self):
        receipt = json.loads(self.start_receipt_path.read_bytes())
        receipt["cohort_started_at"] = "2026-08-04T09:00:00.000Z"
        receipt["cohort_tail_end"] = "2026-11-02T09:00:00.000Z"
        receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
        self.start_receipt_path.write_bytes(
            canonical_json(receipt).encode("utf-8")
        )
        self.start_receipt_path.chmod(0o600)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "AUTHORITY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T09:05:00.000Z")
            )

    def test_post_tail_non_owner_only_artifact_fails_closed(self):
        self.extend_to_complete_cohort()
        path = self.slot_root / (self.cohort_slot(270).slot_id + ".json")
        path.chmod(0o640)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "SOURCE_CHANGED"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )

    def test_post_tail_symlinked_artifact_fails_closed(self):
        self.extend_to_complete_cohort()
        path = self.slot_root / (self.cohort_slot(270).slot_id + ".json")
        retained = self.runtime_root / "symlink-target.json"
        path.rename(retained)
        path.symlink_to(retained)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "SOURCE_CHANGED"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )

    def test_post_tail_oversized_artifact_is_rejected_before_read(self):
        from crypto_quant import system_paper_evaluation as module

        self.extend_to_complete_cohort()
        path = self.slot_root / (self.cohort_slot(270).slot_id + ".json")
        with path.open("wb") as handle:
            handle.truncate(1024 * 1024 + 1)
        path.chmod(0o600)
        original_read = module._RetainedAuthorityFile._read
        oversized_reads = {"count": 0}

        def reject_oversized_read(descriptor, maximum_bytes):
            if os.fstat(descriptor).st_size > 1024 * 1024:
                oversized_reads["count"] += 1
                raise AssertionError("oversized artifact body was read")
            return original_read(descriptor, maximum_bytes)

        with patch.object(
            module._RetainedAuthorityFile,
            "_read",
            side_effect=reject_oversized_read,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(
                        _clock=lambda: "2026-11-02T08:05:00.000Z"
                    )
                )
        self.assertEqual(oversized_reads["count"], 0)

    def test_first_artifact_uses_runtime_limit_before_observer_read(self):
        from crypto_quant import system_paper_observer as observer_module

        receipt = json.loads(self.start_receipt_path.read_bytes())
        path = Path(receipt["first_slot"]["result_path"])
        with path.open("wb") as handle:
            handle.truncate(1024 * 1024 + 1)
        path.chmod(0o600)
        original_read = observer_module.os.read
        oversized_reads = {"count": 0}

        def reject_oversized_read(descriptor, count):
            if os.fstat(descriptor).st_size > 1024 * 1024:
                oversized_reads["count"] += 1
                raise AssertionError("oversized first artifact was read")
            return original_read(descriptor, count)

        with patch.object(
            observer_module.os,
            "read",
            side_effect=reject_oversized_read,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "AUTHORITY_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(
                        _clock=lambda: "2026-11-02T08:05:00.000Z"
                    )
                )
        self.assertEqual(oversized_reads["count"], 0)

    def test_full_state_rows_do_not_call_fetchall(self):
        from crypto_quant import system_paper_evaluation as module

        class StreamingCursor:
            def __iter__(self):
                return iter(({"slot_id": "slot-a"}, {"slot_id": "slot-b"}))

            def fetchall(self):
                raise AssertionError("prepared rows were materialized twice")

        self.assertEqual(
            module._stream_row_dicts(StreamingCursor()),
            ({"slot_id": "slot-a"}, {"slot_id": "slot-b"}),
        )

    def test_maximum_drawdown_strict_boundary(self):
        cases = (
            ((Decimal("1000"), Decimal("900.001")), Decimal("0.099999")),
            ((Decimal("1000"), Decimal("900")), Decimal("0.10")),
            ((Decimal("1000"), Decimal("899.999")), Decimal("0.100001")),
        )
        for equities, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(_maximum_drawdown(equities), expected)

    def test_three_block_lcb_below_equal_above_zero_and_repeatable(self):
        cases = (
            (Decimal("-0.001"), False),
            (Decimal("0"), False),
            (Decimal("0.001"), True),
        )
        for block_return, expected_passed in cases:
            with self.subTest(block_return=block_return):
                first = Decimal("1000") * (Decimal("1") + block_return)
                second = first * (Decimal("1") + block_return)
                third = second * (Decimal("1") + block_return)
                equities = []
                for end in (first, second, third):
                    equities.extend([end] * 180)
                result = _three_block_statistics(tuple(equities))
                self.assertEqual(result["block_returns"], (block_return,) * 3)
                self.assertEqual(result["lcb"], block_return)
                self.assertEqual(result["passed"], expected_passed)
                self.assertTrue(
                    all(
                        _three_block_statistics(tuple(equities)) == result
                        for _ in range(100)
                    )
                )

    def test_complete_economic_cohort_can_pass_all_frozen_gates(self):
        result = _evaluate_complete_system_paper_cohort(
            self.economic_cohort()
        )
        self.assertEqual(result["status"], "SYSTEM_PAPER_GATE_PASS")
        self.assertTrue(all(gate["passed"] for gate in result["gates"].values()))

    def test_each_safety_violation_fails_the_research_gate(self):
        def duplicate(index, result):
            if index in (0, 1):
                self.add_synthetic_fill(result, event_id="duplicate")

        def unrecorded(index, result):
            if index == 0:
                self.add_synthetic_fill(
                    result, event_id="unrecorded", recorded=False
                )

        def hard_risk(index, result):
            if index == 0:
                self.add_synthetic_fill(result, event_id="hard-risk")
                result["risk"]["state"] = "LOCKED"

        def reconciliation_increase(index, result):
            if index == 0:
                result["replay_inputs"]["previous_runtime_snapshot"] = {
                    "position_quantity": "1",
                    "active_order_or_null": {"state": "UNKNOWN"},
                }
                result["runtime_snapshot"]["position_quantity"] = "2"

        def final_active(index, result):
            if index == 539:
                result["runtime_snapshot"]["active_order_or_null"] = {
                    "state": "UNKNOWN"
                }

        def final_risk_locked(index, result):
            if index == 539:
                result["runtime_snapshot"]["risk_state"] = "LOCKED"

        def traceability(index, result):
            if index == 270:
                result["market_bundle_hash"] = "different-bundle"

        def full_replay(index, result):
            if index == 270:
                result["replay"]["full_slot_hash_match"] = False

        def forbidden_activity(index, result):
            if index == 270:
                result["safety_counts"]["real_order_writes"] = 1

        cases = {
            "duplicate_order_events": duplicate,
            "unrecorded_fills": unrecorded,
            "hard_risk_violations": hard_risk,
            "reconciliation_exposure_increases": reconciliation_increase,
            "final_active_order": final_active,
            "final_risk_locked": final_risk_locked,
            "traceability_ratio": traceability,
            "full_replay_ratio": full_replay,
            "forbidden_activity_count": forbidden_activity,
        }
        for metric, mutate in cases.items():
            with self.subTest(metric=metric):
                result = _evaluate_complete_system_paper_cohort(
                    self.economic_cohort(mutate=mutate)
                )
                self.assertEqual(
                    result["status"], "SYSTEM_PAPER_GATE_DID_NOT_PASS"
                )
                safety = result["gates"]["safety"]
                self.assertFalse(safety["passed"])
                if metric in ("final_active_order", "final_risk_locked"):
                    self.assertTrue(safety[metric])
                else:
                    self.assertGreater(safety[metric], 0)

    def test_fee_rate_boundaries_are_decimal_and_inclusive(self):
        for fee, expected in (
            ("0.1499", True),
            ("0.15", True),
            ("0.1501", False),
        ):
            def fill(index, result, fee=fee):
                if index == 0:
                    self.add_synthetic_fill(
                        result,
                        event_id="fee-" + fee,
                        fill_price="100",
                        fee=fee,
                    )
                    result["replay_inputs"]["public_market_bundle"]["bbo"][
                        "ask_price"
                    ] = "100"

            with self.subTest(fee=fee):
                gate = _evaluate_complete_system_paper_cohort(
                    self.economic_cohort(mutate=fill)
                )["gates"]["cost"]
                self.assertEqual(gate["passed"], expected)
                self.assertEqual(
                    gate["maximum_effective_fee_rate"], Decimal(fee) / 100
                )

    def test_slippage_and_aggregate_cost_boundaries_are_inclusive(self):
        for ask, fee, expected, expected_slippage in (
            ("99.9001", "0", True, Decimal("0.000999")),
            ("99.9", "0.15", True, Decimal("0.001")),
            ("99.8999", "0", False, Decimal("0.001001")),
            ("99.9", "0.1501", False, Decimal("0.001")),
        ):
            def fill(index, result, ask=ask, fee=fee):
                if index == 0:
                    self.add_synthetic_fill(
                        result,
                        event_id="cost-" + ask + "-" + fee,
                        fill_price="100",
                        fee=fee,
                    )
                    result["replay_inputs"]["public_market_bundle"]["bbo"][
                        "ask_price"
                    ] = ask

            with self.subTest(ask=ask, fee=fee):
                gate = _evaluate_complete_system_paper_cohort(
                    self.economic_cohort(mutate=fill)
                )["gates"]["cost"]
                self.assertEqual(gate["passed"], expected)
                self.assertEqual(
                    gate["maximum_effective_slippage_rate"],
                    expected_slippage,
                )
                if ask == "99.9" and fee == "0.15":
                    self.assertEqual(
                        gate["modeled_execution_cost_usdt"], Decimal("0.25")
                    )
                    self.assertEqual(
                        gate["aggregate_cost_limit_usdt"], Decimal("0.25")
                    )

    def test_sell_slippage_uses_frozen_bid_touch(self):
        def sell(index, result):
            if index == 0:
                self.add_synthetic_fill(
                    result,
                    event_id="sell-cost",
                    side="SELL",
                    fill_price="100",
                    fee="0",
                )
                result["replay_inputs"]["public_market_bundle"]["bbo"][
                    "bid_price"
                ] = "100.1"

        gate = _evaluate_complete_system_paper_cohort(
            self.economic_cohort(mutate=sell)
        )["gates"]["cost"]
        self.assertEqual(
            gate["maximum_effective_slippage_rate"], Decimal("0.001")
        )
        self.assertTrue(gate["passed"])

    def test_complete_cohort_drawdown_strict_boundary(self):
        cases = (
            ("909.00101", Decimal("0.099999"), True),
            ("909", Decimal("0.10"), False),
            ("908.99899", Decimal("0.100001"), False),
        )
        for low, expected_drawdown, expected_passed in cases:
            def dip(index, result, low=low):
                if index == 50:
                    result["runtime_snapshot"]["marked_equity_usdt"] = low

            with self.subTest(low=low):
                gate = _evaluate_complete_system_paper_cohort(
                    self.economic_cohort(mutate=dip)
                )["gates"]["drawdown"]
                self.assertEqual(gate["maximum_drawdown"], expected_drawdown)
                self.assertEqual(gate["passed"], expected_passed)

    def test_complete_cohort_lcb_strict_boundary(self):
        for block_return, expected in (
            ("-0.001", False),
            ("0", False),
            ("0.001", True),
        ):
            with self.subTest(block_return=block_return):
                gate = _evaluate_complete_system_paper_cohort(
                    self.economic_cohort(block_return=block_return)
                )["gates"]["block_return"]
                self.assertEqual(gate["lcb"], Decimal(block_return))
                self.assertEqual(gate["passed"], expected)

    def test_nonzero_sample_deviation_uses_frozen_student_t_constant(self):
        returns = (Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))
        first = Decimal("1000") * (Decimal("1") + returns[0])
        second = first * (Decimal("1") + returns[1])
        third = second * (Decimal("1") + returns[2])
        equities = tuple(
            [first] * 180 + [second] * 180 + [third] * 180
        )
        result = _three_block_statistics(equities)
        self.assertEqual(result["mean"], Decimal("0.02"))
        self.assertEqual(result["sample_sd"], Decimal("0.01"))
        self.assertEqual(
            result["lcb"],
            Decimal(
                "0.003141455391529541448190553574375229610963609334968"
            ),
        )

    def test_incomplete_evidence_is_not_a_complete_gate_failure(self):
        complete_failure = _evaluate_complete_system_paper_cohort(
            self.economic_cohort(block_return="0")
        )
        self.assertEqual(
            complete_failure["status"], "SYSTEM_PAPER_GATE_DID_NOT_PASS"
        )
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "COHORT_INCOMPLETE"
        ):
            _evaluate_complete_system_paper_cohort(
                self.economic_cohort()[:-1]
            )

    def test_economic_result_is_independent_of_global_decimal_context(self):
        def fill(index, result):
            if index == 0:
                self.add_synthetic_fill(
                    result,
                    event_id="decimal-context",
                    fill_price="3",
                    fee="0.01",
                )
                result["replay_inputs"]["public_market_bundle"]["bbo"][
                    "ask_price"
                ] = "2.99"

        cohort = self.economic_cohort(mutate=fill)
        with localcontext() as context:
            context.prec = 12
            low_precision = _evaluate_complete_system_paper_cohort(cohort)
        with localcontext() as context:
            context.prec = 50
            high_precision = _evaluate_complete_system_paper_cohort(cohort)
        self.assertEqual(low_precision, high_precision)

    def test_post_tail_artifact_replacement_during_evaluation_fails_closed(self):
        self.extend_to_complete_cohort()
        path = self.slot_root / (self.cohort_slot(270).slot_id + ".json")
        body = path.read_bytes()

        def replace_artifact(**_kwargs):
            path.rename(path.with_suffix(".retained-original"))
            path.write_bytes(body)
            path.chmod(0o600)
            return {"status": "UNREACHABLE_TEST_RESULT"}

        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            new=replace_artifact,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(
                        _clock=lambda: "2026-11-02T08:05:00.000Z"
                    )
                )

    def test_post_tail_missing_artifact_is_incomplete(self):
        self.extend_to_complete_cohort()
        sorted(self.slot_root.iterdir())[-1].unlink()
        self.assert_post_tail_incomplete()

    def test_post_tail_extra_artifact_is_incomplete(self):
        self.extend_to_complete_cohort()
        extra = self.slot_root / "unexpected.json"
        extra.write_bytes(b"{}")
        extra.chmod(0o600)
        self.assert_post_tail_incomplete()

    def test_post_tail_hardlinked_artifact_fails_closed(self):
        self.extend_to_complete_cohort()
        artifact = sorted(self.slot_root.iterdir())[100]
        os.link(artifact, self.runtime_root / "artifact-hardlink")
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "SOURCE_CHANGED"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(_clock=lambda: "2026-11-02T08:05:00.000Z")
            )


if __name__ == "__main__":
    unittest.main()
