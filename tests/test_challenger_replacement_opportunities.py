import decimal
import base64
import copy
import hashlib
import json
import multiprocessing
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant import challenger_replacement_opportunities as opportunity_module
from crypto_quant.challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from crypto_quant import challenger_replacement_events as event_module
from crypto_quant.challenger_replacement_opportunity_evidence import (
    build_challenger_replacement_fixture_result_evidence,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    ChallengerReplacementOpportunityState,
    catch_up_missed_opportunities,
    derive_due_opportunities,
    opportunity_coverage,
    opportunity_health,
    opportunity_id_for,
)
from crypto_quant.challenger_replacement_opportunity_projection import (
    apply_opportunity_event,
    initial_opportunity_projection,
)
from tests.challenger_replacement_v3_fixtures import (
    DEFAULT_OBSERVED_AT,
    DEFAULT_SCHEDULED_FOR,
    fixture_opportunity_id,
    fixture_v070_build_identity,
    fixture_v3_plan,
)
from tests.test_challenger_replacement_events import EventWorkspace


V070_SEMANTIC_PROJECTION_BYTES = (
    b'{"active_opportunity_id":null,"current_consecutive_missed":1,'
    b'"first_scheduled_for":"2026-08-24T00:00:00.000Z",'
    b'"last_terminal_scheduled_for":"2026-08-24T04:00:00.000Z",'
    b'"maximum_consecutive_missed":1,"maximum_detection_delay_seconds":660,'
    b'"missed_opportunity_count":1,"missed_reason_counts":'
    b'{"PROCESS_NOT_RUNNING":1},"next_required_opportunity":'
    b'{"opportunity_id":"ETHUSDT@2026-08-24T08:00:00.000Z",'
    b'"scheduled_for":"2026-08-24T08:00:00.000Z"},'
    b'"observed_opportunity_count":1,"opportunities":'
    b'{"ETHUSDT@2026-08-24T00:00:00.000Z":'
    b'{"capture_close":"2026-08-24T00:10:00.000Z",'
    b'"capture_open":"2026-08-24T00:02:00.000Z",'
    b'"decision_sha256":"730db15b20d3c9eb273861fd788d13f5424623a5aec9df334c05ac4593600844",'
    b'"outcome":"OBSERVED","result_evidence_sha256":'
    b'"3b218612b5e9d86dfca13b614e97910d1098280117acd3862ee63b29b68282ec",'
    b'"scheduled_for":"2026-08-24T00:00:00.000Z",'
    b'"source_bundle_sha256":"6ceda47dac352d9f81a563f3c33dfef60b2a652f9e4107eff080cac9b7a71214",'
    b'"stage":"OPPORTUNITY_OBSERVED"},'
    b'"ETHUSDT@2026-08-24T04:00:00.000Z":'
    b'{"detected_at":"2026-08-24T04:11:00.000Z","outcome":"MISSED",'
    b'"reason_code":"PROCESS_NOT_RUNNING",'
    b'"scheduled_for":"2026-08-24T04:00:00.000Z",'
    b'"stage":"OPPORTUNITY_MISSED"}},"terminal_opportunity_count":2,'
    b'"terminal_scheduled_for":["2026-08-24T00:00:00.000Z",'
    b'"2026-08-24T04:00:00.000Z"]}'
)
V070_SEMANTIC_PROJECTION_SHA256 = (
    "b0f887adcea10275688ab6fe68feb2f55bf8a4bc49eff9a574dae35c9b51979a"
)
V070_PUBLIC_API_NAMES = {
    "ChallengerReplacementOpportunityError",
    "ChallengerReplacementOpportunityState",
    "catch_up_missed_opportunities",
    "derive_due_opportunities",
    "opportunity_coverage",
    "opportunity_health",
    "opportunity_id_for",
}


def v070_semantic_projection(projection):
    slot_keys = (
        "stage",
        "outcome",
        "scheduled_for",
        "capture_open",
        "capture_close",
        "source_bundle_sha256",
        "decision_sha256",
        "result_evidence_sha256",
        "reason_code",
        "detected_at",
    )
    return {
        "active_opportunity_id": projection["active_opportunity_id"],
        "first_scheduled_for": projection["first_scheduled_for"],
        "last_terminal_scheduled_for": projection["last_terminal_scheduled_for"],
        "next_required_opportunity": projection["next_required_opportunity"],
        "terminal_scheduled_for": projection["terminal_scheduled_for"],
        "terminal_opportunity_count": projection["terminal_opportunity_count"],
        "observed_opportunity_count": projection["observed_opportunity_count"],
        "missed_opportunity_count": projection["missed_opportunity_count"],
        "current_consecutive_missed": projection["current_consecutive_missed"],
        "maximum_consecutive_missed": projection["maximum_consecutive_missed"],
        "missed_reason_counts": projection["missed_reason_counts"],
        "maximum_detection_delay_seconds": projection[
            "maximum_detection_delay_seconds"
        ],
        "opportunities": {
            opportunity_id: {
                key: slot[key] for key in slot_keys if key in slot
            }
            for opportunity_id, slot in sorted(projection["opportunities"].items())
        },
    }


def _opportunity_race_worker(identity_values, worker_id, barrier, queue):
    identity = ChallengerReplacementEventRootIdentity(**identity_values)
    original = event_module._rename_noreplace

    def synchronized_rename(*args, **kwargs):
        barrier.wait(timeout=10)
        return original(*args, **kwargs)

    opportunity_id = fixture_opportunity_id()
    source_bytes = canonical_json({
        "$schema": "fixture-source-v1",
        "opportunity_id": opportunity_id,
    }).encode("utf-8")
    try:
        with open_challenger_replacement_event_root(identity) as root, patch.object(
            event_module, "_rename_noreplace", synchronized_rename
        ):
            publication = ChallengerReplacementOpportunityState(
                event_root=root,
                plan=fixture_v3_plan(),
                build_identity=fixture_v070_build_identity(),
            ).append(
                event_type="INPUT_PREPARED",
                opportunity_id=opportunity_id,
                worker_id=worker_id,
                recorded_at=DEFAULT_OBSERVED_AT,
                payload={
                    "opportunity_id": opportunity_id,
                    "scheduled_for": DEFAULT_SCHEDULED_FOR,
                    "capture_open": "2026-08-24T00:02:00.000Z",
                    "capture_close": "2026-08-24T00:10:00.000Z",
                    "source_bundle_bytes_base64": base64.b64encode(
                        source_bytes
                    ).decode("ascii"),
                    "source_bundle_sha256": hashlib.sha256(
                        source_bytes
                    ).hexdigest(),
                },
                expected_last_event_hash="0" * 64,
            )
        queue.put(publication.outcome)
    except ChallengerReplacementOpportunityError as error:
        queue.put(error.reason_code)


class OpportunityScheduleTests(unittest.TestCase):
    def test_opportunity_id_accepts_only_canonical_four_hour_grid(self):
        for hour in ("00", "04", "08", "12", "16", "20"):
            scheduled = "2026-08-24T%s:00:00.000Z" % hour
            self.assertEqual(
                opportunity_id_for(scheduled), "ETHUSDT@" + scheduled
            )
        for invalid in (
            "2026-08-24T01:00:00.000Z",
            "2026-08-24T04:00:00Z",
            "2026-08-24T04:00:00.000+00:00",
            "not-time",
            "",
            None,
            True,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ChallengerReplacementOpportunityError):
                    opportunity_id_for(invalid)

    def test_due_opportunities_have_deterministic_windows_and_statuses(self):
        due = derive_due_opportunities(
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T12:11:00.000Z",
            terminal_scheduled_for=("2026-08-24T00:00:00.000Z",),
        )
        self.assertEqual(
            tuple(item["scheduled_for"] for item in due),
            (
                "2026-08-24T04:00:00.000Z",
                "2026-08-24T08:00:00.000Z",
                "2026-08-24T12:00:00.000Z",
            ),
        )
        self.assertEqual({item["status"] for item in due}, {"EXPIRED"})
        self.assertEqual(
            due[-1],
            {
                "opportunity_id": "ETHUSDT@2026-08-24T12:00:00.000Z",
                "scheduled_for": "2026-08-24T12:00:00.000Z",
                "capture_open": "2026-08-24T12:02:00.000Z",
                "capture_close": "2026-08-24T12:10:00.000Z",
                "status": "EXPIRED",
            },
        )

    def test_capture_window_is_closed_and_preopen_is_not_eligible(self):
        cases = (
            ("2026-08-24T00:01:59.999Z", "NOT_OPEN"),
            ("2026-08-24T00:02:00.000Z", "ELIGIBLE_WINDOW"),
            ("2026-08-24T00:10:00.000Z", "ELIGIBLE_WINDOW"),
            ("2026-08-24T00:10:00.001Z", "EXPIRED"),
        )
        for detected_at, status in cases:
            with self.subTest(detected_at=detected_at):
                due = derive_due_opportunities(
                    start_scheduled_for="2026-08-24T00:00:00.000Z",
                    detected_at=detected_at,
                    terminal_scheduled_for=(),
                )
                self.assertEqual(due[0]["status"], status)

    def test_schedule_handles_year_rollover(self):
        due = derive_due_opportunities(
            start_scheduled_for="2026-12-31T20:00:00.000Z",
            detected_at="2027-01-01T04:11:00.000Z",
            terminal_scheduled_for=("2026-12-31T20:00:00.000Z",),
        )
        self.assertEqual(
            tuple(item["scheduled_for"] for item in due),
            (
                "2027-01-01T00:00:00.000Z",
                "2027-01-01T04:00:00.000Z",
            ),
        )

    def test_schedule_rejects_invalid_boundaries_and_terminal_history(self):
        cases = (
            {
                "start_scheduled_for": "2026-08-24T01:00:00.000Z",
                "detected_at": "2026-08-24T04:00:00.000Z",
                "terminal_scheduled_for": (),
            },
            {
                "start_scheduled_for": "2026-08-24T04:00:00.000Z",
                "detected_at": "2026-08-24T00:00:00.000Z",
                "terminal_scheduled_for": (),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T04:00:00.000Z",
                    "2026-08-24T00:00:00.000Z",
                ),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T00:00:00.000Z",
                    "2026-08-24T00:00:00.000Z",
                ),
            },
            {
                "start_scheduled_for": "2026-08-24T00:00:00.000Z",
                "detected_at": "2026-08-24T08:00:00.000Z",
                "terminal_scheduled_for": (
                    "2026-08-24T00:00:00.000Z",
                    "2026-08-24T08:00:00.000Z",
                ),
            },
        )
        for arguments in cases:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ChallengerReplacementOpportunityError):
                    derive_due_opportunities(**arguments)


class OpportunityHealthTests(unittest.TestCase):
    def test_no_start_boundary_is_not_started(self):
        health = opportunity_health(
            projection={
                "terminal_scheduled_for": (),
                "observed_opportunity_count": 0,
            },
            start_scheduled_for=None,
            detected_at="2026-08-24T00:00:00.000Z",
        )
        self.assertEqual(
            health,
            {
                "due_opportunity_count": 0,
                "coverage_numerator": 0,
                "coverage_denominator": 0,
                "meets_minimum_observed_coverage": None,
                "eligibility_status": "NOT_STARTED_NO_START_BOUNDARY",
            },
        )

    def test_health_uses_exact_integer_threshold(self):
        cases = (
            (1, 1, True, "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"),
            (19, 20, True, "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"),
            (18, 20, False, "PRE_TAIL_ELIGIBILITY_ONLY"),
        )
        original = decimal.getcontext().copy()
        try:
            for precision in (2, 7, 28):
                decimal.getcontext().prec = precision
                for observed, due, meets, status in cases:
                    with self.subTest(
                        precision=precision, observed=observed, due=due
                    ):
                        start = datetime(
                            2026, 8, 1, tzinfo=timezone.utc
                        )
                        terminal = tuple(
                            (start + timedelta(hours=4 * index)).isoformat(
                                timespec="milliseconds"
                            ).replace("+00:00", "Z")
                            for index in range(due)
                        )
                        projection = {
                            "terminal_scheduled_for": terminal,
                            "observed_opportunity_count": observed,
                        }
                        health = opportunity_health(
                            projection=projection,
                            start_scheduled_for="2026-08-01T00:00:00.000Z",
                            detected_at=terminal[-1],
                        )
                        self.assertEqual(
                            (
                                health["coverage_numerator"],
                                health["coverage_denominator"],
                                health["meets_minimum_observed_coverage"],
                                health["eligibility_status"],
                            ),
                            (observed, due, meets, status),
                        )
        finally:
            decimal.setcontext(original)


class OpportunityStateWorkspace:
    def __init__(self):
        self.files = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.files.identity())
        self.plan = fixture_v3_plan()
        self.build = fixture_v070_build_identity()
        self.opportunity_id = fixture_opportunity_id()
        self.source_bytes = canonical_json({
            "$schema": "fixture-source-v1",
            "opportunity_id": self.opportunity_id,
        }).encode("utf-8")
        self.decision_bytes = canonical_json({
            "$schema": "fixture-decision-v1",
            "opportunity_id": self.opportunity_id,
            "action": "HOLD_FLAT_FIXTURE_NO_STRATEGY_CLAIM",
        }).encode("utf-8")
        self.source_hash = hashlib.sha256(self.source_bytes).hexdigest()
        self.decision_hash = hashlib.sha256(self.decision_bytes).hexdigest()
        self.evidence = build_challenger_replacement_fixture_result_evidence(
            opportunity_id=self.opportunity_id,
            scheduled_for=DEFAULT_SCHEDULED_FOR,
            observed_at=DEFAULT_OBSERVED_AT,
            source_bundle_sha256=self.source_hash,
            decision_sha256=self.decision_hash,
        )
        self.evidence_bytes = canonical_json(self.evidence).encode("utf-8")
        self.evidence_hash = hashlib.sha256(self.evidence_bytes).hexdigest()

    def close(self):
        self.root.close()
        self.files.close()

    def state(self):
        return ChallengerReplacementOpportunityState(
            event_root=self.root,
            plan=self.plan,
            build_identity=self.build,
        )

    def input_payload(self):
        return {
            "opportunity_id": self.opportunity_id,
            "scheduled_for": DEFAULT_SCHEDULED_FOR,
            "capture_open": "2026-08-24T00:02:00.000Z",
            "capture_close": "2026-08-24T00:10:00.000Z",
            "source_bundle_bytes_base64": base64.b64encode(
                self.source_bytes
            ).decode("ascii"),
            "source_bundle_sha256": self.source_hash,
        }


class OpportunityStateTests(unittest.TestCase):
    def setUp(self):
        self.ws = OpportunityStateWorkspace()
        self.state = self.ws.state()

    def tearDown(self):
        self.ws.close()

    def _append_input(self):
        projection = self.state.replay()
        return self.state.append(
            event_type="INPUT_PREPARED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload=self.ws.input_payload(),
            expected_last_event_hash=projection["last_event_hash"],
        )

    def _append_result(self, input_event):
        projection = self.state.replay()
        return self.state.append(
            event_type="RESULT_PREPARED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload={
                "opportunity_id": self.ws.opportunity_id,
                "scheduled_for": DEFAULT_SCHEDULED_FOR,
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "source_bundle_sha256": self.ws.source_hash,
                "decision_bytes_base64": base64.b64encode(
                    self.ws.decision_bytes
                ).decode("ascii"),
                "decision_sha256": self.ws.decision_hash,
                "result_evidence_bytes_base64": base64.b64encode(
                    self.ws.evidence_bytes
                ).decode("ascii"),
                "result_evidence_sha256": self.ws.evidence_hash,
                "previous_observed_decision_hash_or_null": None,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )

    def test_canary_companion_event_is_validated_without_mutating_projection(self):
        before = self.state.replay()
        payload = {"event_type": "CANARY_AUTHORITY_ARTIFACT_PUBLISHED",
                   "block_id": "e0-block", "occurred_at": DEFAULT_OBSERVED_AT,
                   "artifact_kind": "ACTIVATION", "artifact_id": "activation",
                   "artifact_bytes_base64": "e30=", "artifact_sha256": hashlib.sha256(b"{}").hexdigest()}
        event = event_module.build_challenger_replacement_event(
            sequence=1, event_type=payload["event_type"], slot_id=payload["block_id"],
            worker_id="canary-companion-fixture", recorded_at=payload["occurred_at"],
            previous_event_hash=before["last_event_hash"],
            payload_bytes=canonical_json(payload).encode(),
            plan_hash=self.ws.plan["plan_hash"],
            build_identity_hash=business_hash(self.ws.build), event_root=self.ws.root,
        )
        event_module.publish_challenger_replacement_event(self.ws.root, event)
        after = self.state.replay()
        self.assertEqual(after["terminal_opportunity_count"], 0)
        self.assertEqual(after["last_event_hash"], event.event_hash)

    def test_replays_input_result_and_observed(self):
        empty = self.state.replay()
        self.assertEqual(
            (empty["next_sequence"], empty["active_opportunity_id"]),
            (1, None),
        )
        input_event = self._append_input()
        result_event = self._append_result(input_event)
        projection = self.state.replay()
        self.state.append(
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload={
                "opportunity_id": self.ws.opportunity_id,
                "scheduled_for": DEFAULT_SCHEDULED_FOR,
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "result_event_hash": result_event.event_hash,
                "result_event_sequence": result_event.sequence,
                "source_bundle_sha256": self.ws.source_hash,
                "decision_sha256": self.ws.decision_hash,
                "result_evidence_sha256": self.ws.evidence_hash,
                "observed_at": DEFAULT_OBSERVED_AT,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        self.assertEqual(projection["observed_opportunity_count"], 1)
        self.assertEqual(projection["missed_opportunity_count"], 0)
        self.assertIsNone(projection["active_opportunity_id"])
        self.assertEqual(
            projection["terminal_scheduled_for"],
            (DEFAULT_SCHEDULED_FOR,),
        )
        self.assertEqual(
            projection["opportunities"][self.ws.opportunity_id]["outcome"],
            "OBSERVED",
        )

    def test_extracted_projection_replays_committed_v070_bytes_exactly(self):
        self.assertTrue(callable(initial_opportunity_projection))
        self.assertTrue(callable(apply_opportunity_event))
        input_event = self._append_input()
        result_event = self._append_result(input_event)
        projection = self.state.replay()
        self.state.append(
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at=DEFAULT_OBSERVED_AT,
            payload={
                "opportunity_id": self.ws.opportunity_id,
                "scheduled_for": DEFAULT_SCHEDULED_FOR,
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "result_event_hash": result_event.event_hash,
                "result_event_sequence": result_event.sequence,
                "source_bundle_sha256": self.ws.source_hash,
                "decision_sha256": self.ws.decision_hash,
                "result_evidence_sha256": self.ws.evidence_hash,
                "observed_at": DEFAULT_OBSERVED_AT,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for=DEFAULT_SCHEDULED_FOR,
            detected_at="2026-08-24T04:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        actual = canonical_json(
            v070_semantic_projection(self.state.replay())
        ).encode("utf-8")
        self.assertEqual(actual, V070_SEMANTIC_PROJECTION_BYTES)
        self.assertEqual(
            hashlib.sha256(actual).hexdigest(),
            V070_SEMANTIC_PROJECTION_SHA256,
        )

    def test_facade_does_not_duplicate_extracted_projection_state_machine(self):
        facade = Path(
            __file__
        ).resolve().parents[1] / "src/crypto_quant/challenger_replacement_opportunities.py"
        source = facade.read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 696)
        self.assertNotIn("def _apply_event(", source)
        self.assertTrue(V070_PUBLIC_API_NAMES <= set(dir(opportunity_module)))

    def test_replays_direct_missed_without_active_opportunity(self):
        projection = self.state.replay()
        self.state.append(
            event_type="OPPORTUNITY_MISSED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at="2026-08-24T00:11:00.000Z",
            payload={
                "opportunity_id": self.ws.opportunity_id,
                "scheduled_for": DEFAULT_SCHEDULED_FOR,
                "detected_at": "2026-08-24T00:11:00.000Z",
                "missed_after_event_hash_or_null": None,
                "missed_after_stage_or_null": None,
                "reason_code": "PROCESS_NOT_RUNNING",
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        self.assertEqual(projection["observed_opportunity_count"], 0)
        self.assertEqual(projection["missed_opportunity_count"], 1)
        self.assertEqual(projection["current_consecutive_missed"], 1)
        self.assertEqual(projection["maximum_consecutive_missed"], 1)
        self.assertEqual(
            projection["missed_reason_counts"], {"PROCESS_NOT_RUNNING": 1}
        )

    def test_stale_optimistic_token_conflicts_before_publish(self):
        token = self.state.replay()["last_event_hash"]
        self._append_input()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT",
        ):
            self.state.append(
                event_type="OPPORTUNITY_MISSED",
                opportunity_id=self.ws.opportunity_id,
                worker_id="fixture-worker-2",
                recorded_at="2026-08-24T00:11:00.000Z",
                payload={
                    "opportunity_id": self.ws.opportunity_id,
                    "scheduled_for": DEFAULT_SCHEDULED_FOR,
                    "detected_at": "2026-08-24T00:11:00.000Z",
                    "missed_after_event_hash_or_null": None,
                    "missed_after_stage_or_null": None,
                    "reason_code": "PROCESS_NOT_RUNNING",
                },
                expected_last_event_hash=token,
            )
        self.assertEqual(len(self.state.replay()["events"]), 1)

    def test_immediate_exact_append_retry_is_already_committed(self):
        token = self.state.replay()["last_event_hash"]
        arguments = {
            "event_type": "INPUT_PREPARED",
            "opportunity_id": self.ws.opportunity_id,
            "worker_id": "fixture-worker",
            "recorded_at": DEFAULT_OBSERVED_AT,
            "payload": self.ws.input_payload(),
            "expected_last_event_hash": token,
        }
        first = self.state.append(**arguments)
        second = self.state.append(**arguments)
        self.assertEqual((first.outcome, second.outcome), (
            "COMMITTED", "ALREADY_COMMITTED"
        ))
        self.assertEqual(first.event_hash, second.event_hash)
        self.assertEqual(len(self.state.replay()["events"]), 1)

    def test_different_event_true_process_race_maps_opportunity_conflict(self):
        identity = self.ws.files.identity()
        values = {
            "absolute_path": identity.absolute_path,
            "device": identity.device,
            "inode": identity.inode,
            "uid": identity.uid,
            "mode_octal": identity.mode_octal,
        }
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        queue = context.Queue()
        processes = [
            context.Process(
                target=_opportunity_race_worker,
                args=(values, "fixture-worker-%s" % index, barrier, queue),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            if process.is_alive():
                process.terminate()
                process.join()
                self.fail("opportunity publisher hung at rename barrier")
            self.assertEqual(process.exitcode, 0)
        self.assertCountEqual(
            [queue.get(timeout=2) for _ in processes],
            [
                "COMMITTED",
                "CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT",
            ],
        )
        self.assertEqual(len(self.state.replay()["events"]), 1)

    def test_input_and_result_can_terminalize_as_missed(self):
        for after_result in (False, True):
            with self.subTest(after_result=after_result):
                self.tearDown()
                self.setUp()
                input_event = self._append_input()
                if after_result:
                    boundary = self._append_result(input_event)
                    stage = "RESULT_PREPARED"
                else:
                    boundary = input_event
                    stage = "INPUT_PREPARED"
                projection = self.state.replay()
                self.state.append(
                    event_type="OPPORTUNITY_MISSED",
                    opportunity_id=self.ws.opportunity_id,
                    worker_id="fixture-worker",
                    recorded_at="2026-08-24T00:11:00.000Z",
                    payload={
                        "opportunity_id": self.ws.opportunity_id,
                        "scheduled_for": DEFAULT_SCHEDULED_FOR,
                        "detected_at": "2026-08-24T00:11:00.000Z",
                        "missed_after_event_hash_or_null": boundary.event_hash,
                        "missed_after_stage_or_null": stage,
                        "reason_code": "CAPTURE_WINDOW_EXPIRED",
                    },
                    expected_last_event_hash=projection["last_event_hash"],
                )
                result = self.state.replay()
                self.assertEqual(result["missed_opportunity_count"], 1)
                self.assertIsNone(result["active_opportunity_id"])

    def test_identity_event_type_and_active_invariants_fail_closed(self):
        changed_plan = copy.deepcopy(self.ws.plan)
        changed_plan["authority"]["real_orders_allowed"] = True
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "IDENTITY_INVALID"
        ):
            ChallengerReplacementOpportunityState(
                event_root=self.ws.root,
                plan=changed_plan,
                build_identity=self.ws.build,
            )
        changed_build = dict(self.ws.build)
        changed_build["manifest_hash"] = "not-a-hash"
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "IDENTITY_INVALID"
        ):
            ChallengerReplacementOpportunityState(
                event_root=self.ws.root,
                plan=self.ws.plan,
                build_identity=changed_build,
            )
        projection = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self.state.append(
                event_type="SLOT_SUCCEEDED",
                opportunity_id=self.ws.opportunity_id,
                worker_id="fixture-worker",
                recorded_at=DEFAULT_OBSERVED_AT,
                payload={"opportunity_id": self.ws.opportunity_id,
                         "scheduled_for": DEFAULT_SCHEDULED_FOR},
                expected_last_event_hash=projection["last_event_hash"],
            )
        self._append_input()
        second_id = fixture_opportunity_id("2026-08-24T04:00:00.000Z")
        changed = self.ws.input_payload()
        changed.update(
            opportunity_id=second_id,
            scheduled_for="2026-08-24T04:00:00.000Z",
            capture_open="2026-08-24T04:02:00.000Z",
            capture_close="2026-08-24T04:10:00.000Z",
        )
        projection = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self.state.append(
                event_type="INPUT_PREPARED",
                opportunity_id=second_id,
                worker_id="fixture-worker",
                recorded_at="2026-08-24T04:05:00.000Z",
                payload=changed,
                expected_last_event_hash=projection["last_event_hash"],
            )

    def test_missed_reason_and_terminal_outcome_are_immutable(self):
        projection = self.state.replay()
        payload = {
            "opportunity_id": self.ws.opportunity_id,
            "scheduled_for": DEFAULT_SCHEDULED_FOR,
            "detected_at": "2026-08-24T00:11:00.000Z",
            "missed_after_event_hash_or_null": None,
            "missed_after_stage_or_null": None,
            "reason_code": "NOT_ALLOWLISTED",
        }
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self.state.append(
                event_type="OPPORTUNITY_MISSED",
                opportunity_id=self.ws.opportunity_id,
                worker_id="fixture-worker",
                recorded_at=payload["detected_at"],
                payload=payload,
                expected_last_event_hash=projection["last_event_hash"],
            )
        payload["reason_code"] = "PROCESS_NOT_RUNNING"
        self.state.append(
            event_type="OPPORTUNITY_MISSED",
            opportunity_id=self.ws.opportunity_id,
            worker_id="fixture-worker",
            recorded_at=payload["detected_at"],
            payload=payload,
            expected_last_event_hash=projection["last_event_hash"],
        )
        current = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self.state.append(
                event_type="OPPORTUNITY_MISSED",
                opportunity_id=self.ws.opportunity_id,
                worker_id="fixture-worker",
                recorded_at=payload["detected_at"],
                payload=payload,
                expected_last_event_hash=current["last_event_hash"],
            )
        self.assertEqual(len(self.state.replay()["events"]), 1)

    def test_result_evidence_must_bind_source_and_decision_hashes(self):
        input_event = self._append_input()
        self.ws.evidence["source_bundle_sha256"] = "f" * 64
        self.ws.evidence_bytes = canonical_json(self.ws.evidence).encode("utf-8")
        self.ws.evidence_hash = hashlib.sha256(
            self.ws.evidence_bytes
        ).hexdigest()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self._append_result(input_event)
        projection = self.state.replay()
        self.assertEqual(len(projection["events"]), 1)
        self.assertEqual(
            projection["opportunities"][self.ws.opportunity_id]["stage"],
            "INPUT_PREPARED",
        )

    def test_result_recorded_at_must_equal_bound_evidence_time(self):
        input_event = self._append_input()
        projection = self.state.replay()
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError, "EVENT_INVALID"
        ):
            self.state.append(
                event_type="RESULT_PREPARED",
                opportunity_id=self.ws.opportunity_id,
                worker_id="fixture-worker",
                recorded_at="2026-08-24T00:20:00.000Z",
                payload={
                    "opportunity_id": self.ws.opportunity_id,
                    "scheduled_for": DEFAULT_SCHEDULED_FOR,
                    "input_event_hash": input_event.event_hash,
                    "input_event_sequence": input_event.sequence,
                    "source_bundle_sha256": self.ws.source_hash,
                    "decision_bytes_base64": base64.b64encode(
                        self.ws.decision_bytes
                    ).decode("ascii"),
                    "decision_sha256": self.ws.decision_hash,
                    "result_evidence_bytes_base64": base64.b64encode(
                        self.ws.evidence_bytes
                    ).decode("ascii"),
                    "result_evidence_sha256": self.ws.evidence_hash,
                    "previous_observed_decision_hash_or_null": None,
                },
                expected_last_event_hash=projection["last_event_hash"],
            )
        self.assertEqual(len(self.state.replay()["events"]), 1)

    def test_large_coverage_is_exact_and_context_independent(self):
        observed = 9_500_000_000_000_001
        due = 10_000_000_000_000_001
        original = decimal.getcontext().copy()
        try:
            for precision in (2, 7, 28):
                decimal.getcontext().prec = precision
                self.assertEqual(
                    opportunity_coverage(observed, due),
                    {
                        "coverage_numerator": observed,
                        "coverage_denominator": due,
                        "meets_minimum_observed_coverage": True,
                    },
                )
        finally:
            decimal.setcontext(original)


class OpportunityCatchUpTests(unittest.TestCase):
    def setUp(self):
        self.ws = OpportunityStateWorkspace()
        self.state = self.ws.state()

    def tearDown(self):
        self.ws.close()

    def test_preopen_opportunity_is_not_returned_as_eligible(self):
        result = catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for=DEFAULT_SCHEDULED_FOR,
            detected_at="2026-08-24T00:01:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        self.assertIsNone(result["eligible_opportunity"])
        self.assertEqual(result["projection"]["events"], ())

    def test_expired_opportunities_become_ordered_missed_facts(self):
        with patch(
            "crypto_quant.challenger_replacement_opportunity_evidence."
            "build_challenger_replacement_fixture_result_evidence",
            side_effect=AssertionError("catch-up must not build evidence"),
        ), patch("socket.socket", side_effect=AssertionError("no network")):
            result = catch_up_missed_opportunities(
                state=self.state,
                start_scheduled_for="2026-08-24T00:00:00.000Z",
                detected_at="2026-08-24T12:11:00.000Z",
                worker_id="fixture-worker",
                reason_code="PROCESS_NOT_RUNNING",
            )
        projection = result["projection"]
        self.assertIsNone(result["eligible_opportunity"])
        self.assertEqual(projection["missed_opportunity_count"], 4)
        self.assertEqual(
            projection["terminal_scheduled_for"],
            (
                "2026-08-24T00:00:00.000Z",
                "2026-08-24T04:00:00.000Z",
                "2026-08-24T08:00:00.000Z",
                "2026-08-24T12:00:00.000Z",
            ),
        )
        self.assertTrue(all(
            opportunity["outcome"] == "MISSED"
            for opportunity in projection["opportunities"].values()
        ))
        later = catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T16:05:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        self.assertEqual(
            later["eligible_opportunity"]["opportunity_id"],
            "ETHUSDT@2026-08-24T16:00:00.000Z",
        )
        self.assertEqual(
            later["projection"]["missed_opportunity_count"], 4
        )

    def test_later_fixture_observed_recovers_without_rewriting_misses(self):
        catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for=DEFAULT_SCHEDULED_FOR,
            detected_at="2026-08-24T12:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        opportunity_id = fixture_opportunity_id(
            "2026-08-24T16:00:00.000Z"
        )
        observed_at = "2026-08-24T16:05:00.000Z"
        evidence = build_challenger_replacement_fixture_result_evidence(
            opportunity_id=opportunity_id,
            scheduled_for="2026-08-24T16:00:00.000Z",
            observed_at=observed_at,
            source_bundle_sha256=self.ws.source_hash,
            decision_sha256=self.ws.decision_hash,
        )
        evidence_bytes = canonical_json(evidence).encode("utf-8")
        projection = self.state.replay()
        input_event = self.state.append(
            event_type="INPUT_PREPARED",
            opportunity_id=opportunity_id,
            worker_id="fixture-worker",
            recorded_at=observed_at,
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": "2026-08-24T16:00:00.000Z",
                "capture_open": "2026-08-24T16:02:00.000Z",
                "capture_close": "2026-08-24T16:10:00.000Z",
                "source_bundle_bytes_base64": base64.b64encode(
                    self.ws.source_bytes
                ).decode("ascii"),
                "source_bundle_sha256": self.ws.source_hash,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        result_event = self.state.append(
            event_type="RESULT_PREPARED",
            opportunity_id=opportunity_id,
            worker_id="fixture-worker",
            recorded_at=observed_at,
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": "2026-08-24T16:00:00.000Z",
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "source_bundle_sha256": self.ws.source_hash,
                "decision_bytes_base64": base64.b64encode(
                    self.ws.decision_bytes
                ).decode("ascii"),
                "decision_sha256": self.ws.decision_hash,
                "result_evidence_bytes_base64": base64.b64encode(
                    evidence_bytes
                ).decode("ascii"),
                "result_evidence_sha256": hashlib.sha256(
                    evidence_bytes
                ).hexdigest(),
                "previous_observed_decision_hash_or_null": None,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = self.state.replay()
        self.state.append(
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=opportunity_id,
            worker_id="fixture-worker",
            recorded_at=observed_at,
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": "2026-08-24T16:00:00.000Z",
                "input_event_hash": input_event.event_hash,
                "input_event_sequence": input_event.sequence,
                "result_event_hash": result_event.event_hash,
                "result_event_sequence": result_event.sequence,
                "source_bundle_sha256": self.ws.source_hash,
                "decision_sha256": self.ws.decision_hash,
                "result_evidence_sha256": hashlib.sha256(
                    evidence_bytes
                ).hexdigest(),
                "observed_at": observed_at,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        final = self.state.replay()
        self.assertEqual(final["missed_opportunity_count"], 4)
        self.assertEqual(final["observed_opportunity_count"], 1)
        self.assertEqual(final["current_consecutive_missed"], 0)
        self.assertEqual(final["maximum_consecutive_missed"], 4)

    def test_partial_input_is_missed_without_rebuilding_source(self):
        input_event = OpportunityStateTests._append_input(self)
        with patch(
            "crypto_quant.challenger_replacement_opportunity_evidence."
            "build_challenger_replacement_fixture_result_evidence",
            side_effect=AssertionError("must not rebuild"),
        ):
            catch_up_missed_opportunities(
                state=self.state,
                start_scheduled_for=DEFAULT_SCHEDULED_FOR,
                detected_at="2026-08-24T00:11:00.000Z",
                worker_id="fixture-worker",
                reason_code="CAPTURE_WINDOW_EXPIRED",
            )
        slot = self.state.replay()["opportunities"][self.ws.opportunity_id]
        self.assertEqual(slot["outcome"], "MISSED")
        self.assertEqual(slot["stage"], "OPPORTUNITY_MISSED")
        self.assertEqual(len(self.state.replay()["events"]), 2)
        self.assertEqual(input_event.event_hash, slot["input_event_hash"])

    def test_exact_retry_adds_no_events(self):
        arguments = {
            "state": self.state,
            "start_scheduled_for": DEFAULT_SCHEDULED_FOR,
            "detected_at": "2026-08-24T00:11:00.000Z",
            "worker_id": "fixture-worker",
            "reason_code": "PRECONDITION_FAILED_CLOSED",
        }
        catch_up_missed_opportunities(**arguments)
        before = self.state.replay()
        catch_up_missed_opportunities(**arguments)
        after = self.state.replay()
        self.assertEqual(len(after["events"]), len(before["events"]))
        self.assertEqual(after["last_event_hash"], before["last_event_hash"])

    def test_invalid_reason_and_missing_start_fail_without_events(self):
        for start, reason in (
            (None, "PROCESS_NOT_RUNNING"),
            (DEFAULT_SCHEDULED_FOR, "NOT_ALLOWLISTED"),
        ):
            with self.subTest(start=start, reason=reason):
                with self.assertRaises(ChallengerReplacementOpportunityError):
                    catch_up_missed_opportunities(
                        state=self.state,
                        start_scheduled_for=start,
                        detected_at="2026-08-24T00:11:00.000Z",
                        worker_id="fixture-worker",
                        reason_code=reason,
                    )
        self.assertEqual(len(self.state.replay()["events"]), 0)


class OpportunitySemanticRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.ws = OpportunityStateWorkspace()
        self.state = self.ws.state()

    def tearDown(self):
        self.ws.close()

    def _fresh_process_projection(self):
        identity = self.ws.files.identity()
        values = {
            "absolute_path": identity.absolute_path,
            "device": identity.device,
            "inode": identity.inode,
            "uid": identity.uid,
            "mode_octal": identity.mode_octal,
        }
        script = r'''
import json, sys
from crypto_quant.challenger_replacement_events import (
    ChallengerReplacementEventRootIdentity,
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from tests.challenger_replacement_v3_fixtures import (
    fixture_v070_build_identity, fixture_v3_plan,
)
identity = ChallengerReplacementEventRootIdentity(**json.loads(sys.argv[1]))
with open_challenger_replacement_event_root(identity) as root:
    projection = ChallengerReplacementOpportunityState(
        event_root=root, plan=fixture_v3_plan(),
        build_identity=fixture_v070_build_identity(),
    ).replay()
print(json.dumps({
    "active": projection["active_opportunity_id"],
    "events": len(projection["events"]),
    "observed": projection["observed_opportunity_count"],
    "missed": projection["missed_opportunity_count"],
}, sort_keys=True))
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = "src"
        result = subprocess.run(
            [sys.executable, "-c", script, json.dumps(values)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return json.loads(result.stdout)

    def test_fresh_interpreter_replays_each_durable_semantic_boundary(self):
        input_event = OpportunityStateTests._append_input(self)
        self.assertEqual(
            self._fresh_process_projection(),
            {
                "active": self.ws.opportunity_id,
                "events": 1,
                "missed": 0,
                "observed": 0,
            },
        )
        OpportunityStateTests._append_result(self, input_event)
        self.assertEqual(self._fresh_process_projection()["events"], 2)
        catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for=DEFAULT_SCHEDULED_FOR,
            detected_at="2026-08-24T00:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="CAPTURE_WINDOW_EXPIRED",
        )
        self.assertEqual(
            self._fresh_process_projection(),
            {"active": None, "events": 3, "missed": 1, "observed": 0},
        )

    def test_replaced_root_propagates_fixed_event_failure_without_append(self):
        displaced = self.ws.files.base / "retained-events"
        self.ws.files.event_root.rename(displaced)
        self.ws.files.event_root.mkdir(mode=0o700)
        with self.assertRaisesRegex(
            ChallengerReplacementOpportunityError,
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED",
        ):
            self.state.replay()
        self.assertEqual(list(self.ws.files.event_root.iterdir()), [])
        self.assertEqual(list(displaced.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
