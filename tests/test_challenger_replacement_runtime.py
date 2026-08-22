import base64
import hashlib
import unittest

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
)
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

    def raw_append(self, event_type, payload, *, slot_id=None):
        replay = ChallengerReplacementRuntimeState(
            event_root=self.root, plan=self.plan, build_identity=self.build).replay()
        event = build_challenger_replacement_event(
            sequence=replay["next_sequence"], event_type=event_type,
            slot_id=slot_id or self.slot_id, worker_id="fixture-worker",
            recorded_at="2026-08-22T04:05:00.000Z",
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


if __name__ == "__main__":
    unittest.main()
