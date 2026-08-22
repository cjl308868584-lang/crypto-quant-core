import base64
import hashlib
import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_replacement_events import (
    build_challenger_replacement_event,
    open_challenger_replacement_event_root,
    publish_challenger_replacement_event,
)
from crypto_quant.challenger_replacement_evidence import build_challenger_replacement_source_bundle
from crypto_quant.challenger_replacement_decision import build_challenger_replacement_decision
from crypto_quant.challenger_replacement_runtime import (
    ChallengerReplacementRuntimeError,
    ChallengerReplacementRuntimeState,
    run_challenger_replacement_slot,
)
import crypto_quant.challenger_replacement_runtime as runtime_module
from tests.challenger_replacement_v2_fixtures import (
    fixture_build_identity, fixture_capture, fixture_plan,
)
from tests.test_challenger_replacement_events import EventWorkspace


ZERO = "0" * 64


class RuntimeWorkspace:
    def __init__(self):
        self.files = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.files.identity())
        self.plan = fixture_plan()
        self.build = fixture_build_identity()
        capture = fixture_capture()
        self.source = build_challenger_replacement_source_bundle(
            plan=self.plan, capture=capture, observed_at=capture["captured_at"],
            build_identity=self.build, previous_source_bundle=None,
            previous_decision=None)
        self.decision = build_challenger_replacement_decision(
            plan=self.plan, source_bundle=self.source,
            recorded_at=self.source["slot"]["captured_at"], previous_decision=None)
        self.slot_id = self.source["slot"]["slot_id"]

    def close(self):
        self.root.close(); self.files.close()

    def payloads(self):
        source_bytes = canonical_json(self.source).encode()
        decision_bytes = canonical_json(self.decision).encode()
        capture_bytes = canonical_json(fixture_capture()).encode()
        input_payload = {
            "capture_sha256": hashlib.sha256(capture_bytes).hexdigest(),
            "source_bundle_bytes_base64": base64.b64encode(source_bytes).decode(),
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
        }
        return input_payload, source_bytes, decision_bytes

    def raw_append(self, event_type, payload, *, slot_id=None,
                   recorded_at="2026-08-22T04:05:00.000Z"):
        replay = ChallengerReplacementRuntimeState(
            event_root=self.root, plan=self.plan, build_identity=self.build).replay()
        event = build_challenger_replacement_event(
            sequence=replay["next_sequence"], event_type=event_type,
            slot_id=slot_id or self.slot_id, worker_id="fixture-worker",
            recorded_at=recorded_at,
            previous_event_hash=replay["last_event_hash"],
            payload_bytes=canonical_json(payload).encode(), plan_hash=self.plan["plan_hash"],
            build_identity_hash=business_hash(self.build), event_root=self.root)
        publish_challenger_replacement_event(self.root, event)
        return event


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.ws = RuntimeWorkspace()

    def tearDown(self):
        self.ws.close()

    def _state(self):
        return ChallengerReplacementRuntimeState(
            event_root=self.ws.root, plan=self.ws.plan, build_identity=self.ws.build)

    def test_replays_empty_input_result_and_success(self):
        projection = self._state().replay()
        self.assertEqual((projection["next_sequence"], projection["active_slot_id"]), (1, None))
        input_payload, source_bytes, decision_bytes = self.ws.payloads()
        input_event = self.ws.raw_append("INPUT_PREPARED", input_payload)
        projection = self._state().replay()
        self.assertEqual(projection["active_slot_id"], self.ws.slot_id)
        result_payload = {
            "input_event_hash": input_event.event_hash, "input_event_sequence": 1,
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "decision_bytes_base64": base64.b64encode(decision_bytes).decode(),
            "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
            "previous_decision_hash_or_null": None,
        }
        result_event = self.ws.raw_append("RESULT_PREPARED", result_payload)
        self.assertEqual(self._state().replay()["slots"][self.ws.slot_id]["stage"], "RESULT_PREPARED")
        success = {
            "input_event_hash": input_event.event_hash, "input_event_sequence": 1,
            "result_event_hash": result_event.event_hash, "result_event_sequence": 2,
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        }
        self.ws.raw_append("SLOT_SUCCEEDED", success)
        projection = self._state().replay()
        self.assertEqual((projection["active_slot_id"], projection["completed_slot_count"]), (None, 1))
        self.assertEqual(projection["next_required_slot"], {
            "sequence": 2, "scheduled_for": "2026-08-22T08:00:00.000Z"})

    def test_empty_root_rejects_wrong_build_identity(self):
        wrong = dict(self.ws.build); wrong["manifest_hash"] = "not-a-hash"
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_IDENTITY_INVALID"):
            ChallengerReplacementRuntimeState(
                event_root=self.ws.root, plan=self.ws.plan, build_identity=wrong)

    def test_rejects_unknown_stage_and_two_active_slots(self):
        input_payload, _, _ = self.ws.payloads()
        self.ws.raw_append("SOURCE_BUNDLE_PUBLISHED", input_payload)
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()

    def test_rejects_two_active_slots(self):
        input_payload, _, _ = self.ws.payloads()
        self.ws.raw_append("INPUT_PREPARED", input_payload)
        self.ws.raw_append("INPUT_PREPARED", input_payload, slot_id="other-slot")
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()

    def test_rejects_mismatched_success_and_terminal_followup(self):
        input_payload, source_bytes, decision_bytes = self.ws.payloads()
        input_event = self.ws.raw_append("INPUT_PREPARED", input_payload)
        bad = {
            "input_event_hash": input_event.event_hash, "input_event_sequence": 1,
            "result_event_hash": "f" * 64, "result_event_sequence": 2,
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
        }
        self.ws.raw_append("SLOT_SUCCEEDED", bad)
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()

    def test_result_timestamp_cannot_precede_input_boundary(self):
        input_payload, source_bytes, decision_bytes = self.ws.payloads()
        input_event = self.ws.raw_append("INPUT_PREPARED", input_payload)
        result = {
            "input_event_hash": input_event.event_hash, "input_event_sequence": 1,
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "decision_bytes_base64": base64.b64encode(decision_bytes).decode(),
            "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
            "previous_decision_hash_or_null": None,
        }
        self.ws.raw_append(
            "RESULT_PREPARED", result,
            recorded_at="2026-08-22T04:04:59.999Z")
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()

    def test_failure_timestamp_cannot_precede_durable_boundary(self):
        input_payload, _, _ = self.ws.payloads()
        input_event = self.ws.raw_append("INPUT_PREPARED", input_payload)
        self.ws.raw_append(
            "SLOT_FAILED_PERMANENT",
            {"failed_after_event_hash": input_event.event_hash,
             "failed_stage": "INPUT_PREPARED", "reason_code": "FIXTURE_FAILURE"},
            recorded_at="2026-08-22T04:04:59.999Z")
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()

    def test_accepts_failure_then_rejects_followup(self):
        input_payload, source_bytes, decision_bytes = self.ws.payloads()
        input_event = self.ws.raw_append("INPUT_PREPARED", input_payload)
        failed = {
            "failed_after_event_hash": input_event.event_hash,
            "failed_stage": "INPUT_PREPARED", "reason_code": "FIXTURE_FAILURE",
        }
        self.ws.raw_append("SLOT_FAILED_PERMANENT", failed)
        projection = self._state().replay()
        self.assertEqual((projection["active_slot_id"], projection["failed_slot_count"]), (None, 1))
        result = {
            "input_event_hash": input_event.event_hash, "input_event_sequence": 1,
            "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "decision_bytes_base64": base64.b64encode(decision_bytes).decode(),
            "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
            "previous_decision_hash_or_null": None,
        }
        self.ws.raw_append("RESULT_PREPARED", result)
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            self._state().replay()


class OptimisticAppendTests(unittest.TestCase):
    def setUp(self):
        self.ws = RuntimeWorkspace()

    def tearDown(self):
        self.ws.close()

    def test_stale_projection_token_conflicts_before_event_construction(self):
        first = ChallengerReplacementRuntimeState(
            event_root=self.ws.root, plan=self.ws.plan, build_identity=self.ws.build)
        second = ChallengerReplacementRuntimeState(
            event_root=self.ws.root, plan=self.ws.plan, build_identity=self.ws.build)
        token = first.replay()["last_event_hash"]
        payload, _, _ = self.ws.payloads()
        first.append(event_type="INPUT_PREPARED", slot_id=self.ws.slot_id,
                     worker_id="worker-a", recorded_at="2026-08-22T04:05:00.000Z",
                     payload=payload, expected_last_event_hash=token)
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "EVENT_SEQUENCE_CONFLICT"):
            second.append(event_type="INPUT_PREPARED", slot_id=self.ws.slot_id,
                          worker_id="worker-b", recorded_at="2026-08-22T04:05:00.000Z",
                          payload=payload, expected_last_event_hash=token)
        self.assertEqual(len(first.replay()["events"]), 1)


class SlotRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.ws = RuntimeWorkspace()
        self.state = ChallengerReplacementRuntimeState(
            event_root=self.ws.root, plan=self.ws.plan, build_identity=self.ws.build)

    def tearDown(self):
        self.ws.close()

    def test_genesis_and_successor_finish_exact_three_stages(self):
        capture = fixture_capture()
        result = run_challenger_replacement_slot(
            state=self.state, capture=capture,
            observed_at=capture["captured_at"], worker_id="worker-a")
        self.assertEqual((result["stage"], len(self.state.replay()["events"])),
                         ("SLOT_SUCCEEDED", 3))
        previous_source = self.state.replay()["slots"][capture["slot_id"]]["source_bundle"]
        successor = fixture_capture(
            sequence=2, scheduled_for="2026-08-22T08:00:00.000Z",
            captured_at="2026-08-22T08:05:00.000Z", latest="102")
        successor["klines"] = deepcopy(previous_source["klines"][1:]) + [successor["klines"][-1]]
        with patch.object(runtime_module, "build_challenger_replacement_decision",
                          wraps=runtime_module.build_challenger_replacement_decision) as build_decision, \
             patch.object(runtime_module, "_utc_now", side_effect=(
                 "2026-08-22T08:05:00.001Z", "2026-08-22T08:05:00.002Z")):
            second = run_challenger_replacement_slot(
                state=self.state, capture=successor,
                observed_at=successor["captured_at"], worker_id="worker-b")
        self.assertIsNotNone(build_decision.call_args.kwargs["previous_decision"])
        self.assertEqual((second["stage"], len(self.state.replay()["events"])),
                         ("SLOT_SUCCEEDED", 6))

    def test_each_stage_records_its_first_canonical_publication_time(self):
        capture = fixture_capture()
        stage_times = iter((
            "2026-08-22T04:05:00.001Z",
            "2026-08-22T04:05:00.002Z",
        ))
        with patch.object(runtime_module, "_utc_now", side_effect=stage_times):
            run_challenger_replacement_slot(
                state=self.state, capture=capture,
                observed_at=capture["captured_at"], worker_id="worker")
        headers = [json.loads(event.final_bytes) for event in self.state.replay()["events"]]
        self.assertEqual(
            [header["recorded_at"] for header in headers],
            [capture["captured_at"], "2026-08-22T04:05:00.001Z",
             "2026-08-22T04:05:00.002Z"],
        )

    def test_invalid_unbound_capture_writes_nothing(self):
        with self.assertRaises(ChallengerReplacementRuntimeError):
            run_challenger_replacement_slot(
                state=self.state, capture=None,
                observed_at="2026-08-22T04:05:00.000Z", worker_id="worker")
        self.assertEqual(len(self.state.replay()["events"]), 0)

    def test_other_slot_cannot_pollute_existing_active_slot(self):
        capture = fixture_capture()
        real_append = self.state.append

        def stop_after_input(**kwargs):
            event = real_append(**kwargs)
            if kwargs["event_type"] == "INPUT_PREPARED":
                raise SystemExit("test-only pause")
            return event

        with patch.object(self.state, "append", side_effect=stop_after_input), \
             self.assertRaises(SystemExit):
            run_challenger_replacement_slot(
                state=self.state, capture=capture,
                observed_at=capture["captured_at"], worker_id="worker-a")
        before = tuple(self.state.replay()["events"])
        other = fixture_capture(
            scheduled_for="2026-08-22T08:00:00.000Z",
            captured_at="2026-08-22T08:05:00.000Z", sequence=2)
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "ACTIVE_SLOT_CONFLICT"):
            run_challenger_replacement_slot(
                state=self.state, capture=other,
                observed_at=other["captured_at"], worker_id="worker-b")
        self.assertEqual(tuple(self.state.replay()["events"]), before)

    def test_bound_decision_failure_gets_one_permanent_terminal(self):
        capture = fixture_capture()
        with patch.object(runtime_module, "build_challenger_replacement_decision",
                          side_effect=ValueError("fixture failure")), \
             self.assertRaisesRegex(ChallengerReplacementRuntimeError, "DECISION_BUILD_FAILED"):
            run_challenger_replacement_slot(
                state=self.state, capture=capture,
                observed_at=capture["captured_at"], worker_id="worker")
        projection = self.state.replay()
        self.assertEqual((len(projection["events"]), projection["failed_slot_count"]), (2, 1))
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "SLOT_TERMINAL_FAILURE"):
            run_challenger_replacement_slot(
                state=self.state, capture=capture,
                observed_at=capture["captured_at"], worker_id="retry")
        self.assertEqual(len(self.state.replay()["events"]), 2)

    def test_permanent_failure_freezes_stream_against_new_genesis(self):
        capture = fixture_capture()
        with patch.object(runtime_module, "build_challenger_replacement_decision",
                          side_effect=ValueError("fixture failure")), \
             self.assertRaises(ChallengerReplacementRuntimeError):
            run_challenger_replacement_slot(
                state=self.state, capture=capture,
                observed_at=capture["captured_at"], worker_id="worker")
        before = tuple(self.state.replay()["events"])
        self.assertIsNone(self.state.replay()["next_required_slot"])
        later_genesis = fixture_capture(
            sequence=1, scheduled_for="2026-08-22T12:00:00.000Z",
            captured_at="2026-08-22T12:05:00.000Z")
        with self.assertRaisesRegex(ChallengerReplacementRuntimeError, "STATE_EVENT_INVALID"):
            run_challenger_replacement_slot(
                state=self.state, capture=later_genesis,
                observed_at=later_genesis["captured_at"], worker_id="reset-worker")
        self.assertEqual(tuple(self.state.replay()["events"]), before)


class CrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.ws = RuntimeWorkspace()
        self.capture = fixture_capture()

    def tearDown(self):
        self.ws.close()

    def _state(self):
        return ChallengerReplacementRuntimeState(
            event_root=self.ws.root, plan=self.ws.plan, build_identity=self.ws.build)

    def _crash_after(self, event_type):
        state = self._state(); real_append = state.append

        def append_then_crash(**kwargs):
            result = real_append(**kwargs)
            if kwargs["event_type"] == event_type:
                raise SystemExit("test-only crash")
            return result

        with patch.object(state, "append", side_effect=append_then_crash):
            with self.assertRaises(SystemExit):
                run_challenger_replacement_slot(
                    state=state, capture=self.capture,
                    observed_at=self.capture["captured_at"], worker_id="crash-worker")

    def test_fresh_retry_after_input_does_not_rebuild_source(self):
        self._crash_after("INPUT_PREPARED")
        with patch.object(runtime_module, "build_challenger_replacement_source_bundle",
                          wraps=runtime_module.build_challenger_replacement_source_bundle) as source_build, \
             patch.object(runtime_module, "build_challenger_replacement_decision",
                          wraps=runtime_module.build_challenger_replacement_decision) as decision_build:
            result = run_challenger_replacement_slot(
                state=self._state(), capture=self.capture,
                observed_at=self.capture["captured_at"], worker_id="retry-worker")
        self.assertEqual((source_build.call_count, decision_build.call_count), (0, 1))
        self.assertEqual(result["stage"], "SLOT_SUCCEEDED")

    def test_fresh_retry_after_result_recomputes_nothing(self):
        self._crash_after("RESULT_PREPARED")
        with patch.object(runtime_module, "build_challenger_replacement_source_bundle",
                          wraps=runtime_module.build_challenger_replacement_source_bundle) as source_build, \
             patch.object(runtime_module, "build_challenger_replacement_decision",
                          wraps=runtime_module.build_challenger_replacement_decision) as decision_build:
            result = run_challenger_replacement_slot(
                state=self._state(), capture=self.capture,
                observed_at=self.capture["captured_at"], worker_id="retry-worker")
        self.assertEqual((source_build.call_count, decision_build.call_count), (0, 0))
        self.assertEqual(result["stage"], "SLOT_SUCCEEDED")

    def test_success_retry_is_replay_only(self):
        state = self._state()
        run_challenger_replacement_slot(
            state=state, capture=self.capture,
            observed_at=self.capture["captured_at"], worker_id="worker")
        before = len(state.replay()["events"])
        with patch.object(runtime_module, "build_challenger_replacement_source_bundle") as source_build, \
             patch.object(runtime_module, "build_challenger_replacement_decision") as decision_build, \
             patch.object(state, "append", wraps=state.append) as append:
            result = run_challenger_replacement_slot(
                state=state, capture=self.capture,
                observed_at="2099-01-01T00:00:00.000Z", worker_id="new-worker")
        self.assertEqual((source_build.call_count, decision_build.call_count, append.call_count), (0, 0, 0))
        self.assertEqual((result["stage"], len(state.replay()["events"])),
                         ("SLOT_SUCCEEDED", before))


if __name__ == "__main__":
    unittest.main()
