"""Three-stage event projection for the isolated replacement Challenger."""

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping

from .canonical import business_hash, canonical_json, utc_datetime
from .challenger_replacement_decision import (
    build_challenger_replacement_cohort_decision,
    build_challenger_replacement_decision,
    load_challenger_replacement_cohort_decision_bytes,
    load_challenger_replacement_decision_bytes,
)
from .challenger_replacement_evidence import (
    _build_identity,
    _strict_json_bytes,
    build_challenger_replacement_cohort_source_bundle,
    build_challenger_replacement_source_bundle,
    load_challenger_replacement_cohort_source_bundle_bytes,
    load_challenger_replacement_source_bundle_bytes,
)
from .challenger_replacement_live_input import ChallengerReplacementLiveCapture
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRoot,
    build_challenger_replacement_event,
    publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_plan_v2 import challenger_replacement_plan_v2_reasons


_ZERO_HASH = "0" * 64
_HASH = set("0123456789abcdef")
_SUCCESS_STAGES = {"INPUT_PREPARED", "RESULT_PREPARED", "SLOT_SUCCEEDED"}
_FAILURE = "SLOT_FAILED_PERMANENT"


class ChallengerReplacementRuntimeError(ValueError):
    """The replacement runtime projection failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid():
    raise ChallengerReplacementRuntimeError("CHALLENGER_REPLACEMENT_STATE_EVENT_INVALID")


def _hash_valid(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HASH


def _runtime_build_identity(value):
    try:
        return _build_identity(value)
    except ValueError:
        keys = {
            "release_tag", "peeled_commit", "package_version", "manifest_version",
            "build_input_tree_hash", "manifest_hash", "manifest_file_sha256",
        }
        if (
            not isinstance(value, Mapping)
            or set(value) != keys
            or value.get("release_tag") != "v0.67.0"
            or value.get("package_version") != "0.67.0"
            or value.get("manifest_version") != "1.61.0"
            or not isinstance(value.get("peeled_commit"), str)
            or len(value["peeled_commit"]) != 40
            or set(value["peeled_commit"]) - _HASH
            or any(
                not _hash_valid(value[name])
                for name in (
                    "build_input_tree_hash", "manifest_hash", "manifest_file_sha256"
                )
            )
        ):
            raise
        return dict(value)


def _time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _utc_now():
    return utc_datetime(datetime.now(timezone.utc))


def _stage_time(durable_boundary):
    now = _utc_now()
    return durable_boundary if _time(now) < _time(durable_boundary) else now


def _payload(event):
    try:
        document = json.loads(event.final_bytes.decode("utf-8"))
        encoded = document["payload_bytes_base64"]
        body = base64.b64decode(encoded, validate=True)
        if hashlib.sha256(body).hexdigest() != document["payload_sha256"]:
            _invalid()
        return document, _strict_json_bytes(body)
    except ChallengerReplacementRuntimeError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_STATE_EVENT_INVALID"
        ) from error


def _decode_exact(value, expected_sha):
    if not isinstance(value, str) or not _hash_valid(expected_sha):
        _invalid()
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as error:
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_STATE_EVENT_INVALID"
        ) from error
    if hashlib.sha256(data).hexdigest() != expected_sha:
        _invalid()
    return data


def _new_projection(replay):
    return {
        "events": replay.events,
        "slots": {},
        "last_event_hash": replay.last_event_hash,
        "next_sequence": replay.next_sequence,
        "active_slot_id": None,
        "completed_slot_count": 0,
        "failed_slot_count": 0,
        "next_required_slot": {"sequence": 1, "scheduled_for": None},
        "orphan_staging_count": replay.orphan_staging_count,
        "orphan_staging_bytes": replay.orphan_staging_bytes,
        "_previous_source_bundle": None,
        "_previous_decision": None,
        "_terminal_slots": set(),
    }


def _require_exact(payload, keys):
    if not isinstance(payload, Mapping) or set(payload) != set(keys):
        _invalid()


def _apply_event(projection, event, plan, build_identity):
    header, payload = _payload(event)
    event_type = header["event_type"]
    slot_id = header["slot_id"]
    if (
        header["plan_hash"] != plan["plan_hash"]
        or header["build_identity_hash"] != business_hash(build_identity)
        or slot_id in projection["_terminal_slots"]
        or event_type not in _SUCCESS_STAGES | {_FAILURE}
    ):
        _invalid()
    if event_type == "INPUT_PREPARED":
        _require_exact(payload, (
            "capture_sha256", "source_bundle_bytes_base64", "source_bundle_sha256",
        ))
        if (
            projection["active_slot_id"] is not None
            or projection["failed_slot_count"]
            or not _hash_valid(payload["capture_sha256"])
        ):
            _invalid()
        source_bytes = _decode_exact(
            payload["source_bundle_bytes_base64"], payload["source_bundle_sha256"])
        try:
            source_document = _strict_json_bytes(source_bytes)
            if (
                source_document.get("$schema")
                == "./challenger-replacement-source-bundle-v2.schema.json"
            ):
                source = load_challenger_replacement_cohort_source_bundle_bytes(
                    source_bytes, plan=plan, build_identity=build_identity,
                    previous_source_bundle=projection["_previous_source_bundle"],
                    previous_decision=projection["_previous_decision"])
            else:
                source = load_challenger_replacement_source_bundle_bytes(
                    source_bytes, plan=plan, build_identity=build_identity,
                    previous_source_bundle=projection["_previous_source_bundle"],
                    previous_decision=projection["_previous_decision"])
        except ValueError as error:
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_STATE_EVENT_INVALID") from error
        if source["slot"]["slot_id"] != slot_id or source["slot"]["captured_at"] != header["recorded_at"]:
            _invalid()
        projection["slots"][slot_id] = {
            "stage": event_type, "source_bundle": source,
            "source_bundle_bytes": source_bytes,
            "source_bundle_sha256": payload["source_bundle_sha256"],
            "input_event_hash": event.event_hash, "input_event_sequence": event.sequence,
            "input_recorded_at": header["recorded_at"],
        }
        projection["active_slot_id"] = slot_id
        return
    if projection["active_slot_id"] != slot_id or slot_id not in projection["slots"]:
        _invalid()
    slot = projection["slots"][slot_id]
    if event_type == "RESULT_PREPARED":
        _require_exact(payload, (
            "input_event_hash", "input_event_sequence", "source_bundle_sha256",
            "decision_bytes_base64", "decision_sha256", "previous_decision_hash_or_null",
        ))
        expected_previous = (
            None if projection["_previous_decision"] is None
            else projection["_previous_decision"]["decision_hash"])
        if (
            slot["stage"] != "INPUT_PREPARED"
            or payload["input_event_hash"] != slot["input_event_hash"]
            or payload["input_event_sequence"] != slot["input_event_sequence"]
            or payload["source_bundle_sha256"] != slot["source_bundle_sha256"]
            or payload["previous_decision_hash_or_null"] != expected_previous
            or _time(header["recorded_at"]) < _time(slot["input_recorded_at"])
        ):
            _invalid()
        decision_bytes = _decode_exact(
            payload["decision_bytes_base64"], payload["decision_sha256"])
        try:
            decision_document = _strict_json_bytes(decision_bytes)
            if (
                decision_document.get("$schema")
                == "./challenger-replacement-decision-v2.schema.json"
            ):
                decision = load_challenger_replacement_cohort_decision_bytes(
                    decision_bytes, plan=plan, source_bundle=slot["source_bundle"],
                    previous_decision=projection["_previous_decision"])
            else:
                decision = load_challenger_replacement_decision_bytes(
                    decision_bytes, plan=plan, source_bundle=slot["source_bundle"],
                    previous_decision=projection["_previous_decision"])
        except ValueError as error:
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_STATE_EVENT_INVALID") from error
        slot.update(stage=event_type, decision=decision,
                    decision_bytes=decision_bytes,
                    decision_sha256=payload["decision_sha256"],
                    result_event_hash=event.event_hash,
                    result_event_sequence=event.sequence,
                    result_recorded_at=header["recorded_at"])
        return
    if event_type == "SLOT_SUCCEEDED":
        _require_exact(payload, (
            "input_event_hash", "input_event_sequence", "result_event_hash",
            "result_event_sequence", "source_bundle_sha256", "decision_sha256",
        ))
        expected = {
            "input_event_hash": slot.get("input_event_hash"),
            "input_event_sequence": slot.get("input_event_sequence"),
            "result_event_hash": slot.get("result_event_hash"),
            "result_event_sequence": slot.get("result_event_sequence"),
            "source_bundle_sha256": slot.get("source_bundle_sha256"),
            "decision_sha256": slot.get("decision_sha256"),
        }
        if (
            slot["stage"] != "RESULT_PREPARED"
            or dict(payload) != expected
            or _time(header["recorded_at"]) < _time(slot["result_recorded_at"])
        ):
            _invalid()
        slot["stage"] = event_type
        projection["active_slot_id"] = None
        projection["completed_slot_count"] += 1
        projection["_terminal_slots"].add(slot_id)
        projection["_previous_source_bundle"] = slot["source_bundle"]
        projection["_previous_decision"] = slot["decision"]
        projection["next_required_slot"] = {
            "sequence": slot["source_bundle"]["slot"]["sequence"] + 1,
            "scheduled_for": utc_datetime(
                datetime.fromisoformat(
                    slot["source_bundle"]["slot"]["scheduled_for"].replace(
                        "Z", "+00:00")
                ).astimezone(timezone.utc) + timedelta(hours=4)
            ),
        }
        return
    _require_exact(payload, ("failed_after_event_hash", "failed_stage", "reason_code"))
    boundary_time = (
        slot["input_recorded_at"]
        if slot["stage"] == "INPUT_PREPARED"
        else slot.get("result_recorded_at")
    )
    if (
        slot["stage"] not in {"INPUT_PREPARED", "RESULT_PREPARED"}
        or payload["failed_stage"] != slot["stage"]
        or payload["failed_after_event_hash"] != event.previous_event_hash
        or not isinstance(payload["reason_code"], str)
        or not payload["reason_code"]
        or boundary_time is None
        or _time(header["recorded_at"]) < _time(boundary_time)
    ):
        _invalid()
    slot["stage"] = _FAILURE
    slot["reason_code"] = payload["reason_code"]
    projection["active_slot_id"] = None
    projection["failed_slot_count"] += 1
    projection["_terminal_slots"].add(slot_id)
    projection["next_required_slot"] = None


def _public_projection(projection):
    return {key: value for key, value in projection.items() if not key.startswith("_")}


class ChallengerReplacementRuntimeState:
    """Project and append against one retained canonical event capability."""

    def __init__(self, *, event_root, plan, build_identity):
        if not isinstance(event_root, ChallengerReplacementEventRoot):
            raise ChallengerReplacementRuntimeError("CHALLENGER_REPLACEMENT_STATE_ROOT_INVALID")
        reasons = challenger_replacement_plan_v2_reasons(plan) if isinstance(plan, Mapping) else ("invalid",)
        try:
            identity = _runtime_build_identity(build_identity)
        except ValueError:
            identity = None
        if reasons or identity is None:
            raise ChallengerReplacementRuntimeError("CHALLENGER_REPLACEMENT_STATE_IDENTITY_INVALID")
        self.event_root = event_root
        self.plan = dict(plan)
        self.build_identity = identity

    def _replay(self):
        try:
            replay = replay_challenger_replacement_events(self.event_root)
        except ChallengerReplacementEventError as error:
            raise ChallengerReplacementRuntimeError(error.reason_code) from error
        projection = _new_projection(replay)
        for event in replay.events:
            _apply_event(projection, event, self.plan, self.build_identity)
        return projection

    def replay(self):
        return _public_projection(self._replay())

    def append(self, *, event_type, slot_id, worker_id, recorded_at,
               payload, expected_last_event_hash):
        projection = self._replay()
        if projection["last_event_hash"] != expected_last_event_hash:
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT")
        if not isinstance(payload, Mapping):
            _invalid()
        try:
            event = build_challenger_replacement_event(
                sequence=projection["next_sequence"], event_type=event_type,
                slot_id=slot_id, worker_id=worker_id, recorded_at=recorded_at,
                previous_event_hash=projection["last_event_hash"],
                payload_bytes=canonical_json(dict(payload)).encode("utf-8"),
                plan_hash=self.plan["plan_hash"],
                build_identity_hash=business_hash(self.build_identity),
                event_root=self.event_root)
            candidate = deepcopy(projection)
            _apply_event(candidate, event, self.plan, self.build_identity)
            publish_challenger_replacement_event(self.event_root, event)
            return event
        except ChallengerReplacementRuntimeError:
            raise
        except ChallengerReplacementEventError as error:
            raise ChallengerReplacementRuntimeError(error.reason_code) from error


def _runtime_input_invalid():
    raise ChallengerReplacementRuntimeError(
        "CHALLENGER_REPLACEMENT_RUNTIME_INPUT_INVALID")


def _slot_result(slot):
    return {
        key: value for key, value in slot.items()
        if key not in {"source_bundle_bytes", "decision_bytes"}
    }


def run_challenger_replacement_slot(*, state, capture, observed_at, worker_id):
    if (
        not isinstance(state, ChallengerReplacementRuntimeState)
        or not isinstance(capture, Mapping)
        or not isinstance(capture.get("slot_id"), str)
        or not capture.get("slot_id")
        or not isinstance(observed_at, str)
        or not observed_at
        or not isinstance(worker_id, str)
        or not worker_id
    ):
        _runtime_input_invalid()
    return _run_challenger_replacement_slot(
        state=state,
        slot_id=capture["slot_id"],
        observed_at=observed_at,
        worker_id=worker_id,
        fixture_capture=capture,
        live_capture=None,
    )


def run_challenger_replacement_cohort_slot(*, state, live_capture, worker_id):
    """Advance one adapter-derived cohort slot through three durable stages."""

    if (
        not isinstance(state, ChallengerReplacementRuntimeState)
        or not isinstance(live_capture, ChallengerReplacementLiveCapture)
        or not isinstance(worker_id, str)
        or not worker_id
    ):
        _runtime_input_invalid()
    receipt = live_capture.document
    try:
        slot_id = receipt["slot"]["slot_id"]
        observed_at = receipt["slot"]["captured_at"]
    except (KeyError, TypeError) as error:
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_RUNTIME_INPUT_INVALID"
        ) from error
    return _run_challenger_replacement_slot(
        state=state,
        slot_id=slot_id,
        observed_at=observed_at,
        worker_id=worker_id,
        fixture_capture=None,
        live_capture=live_capture,
    )


def resume_challenger_replacement_slot(*, state, worker_id):
    """Continue only the durable slot already embedded in the event log."""

    if (
        not isinstance(state, ChallengerReplacementRuntimeState)
        or not isinstance(worker_id, str)
        or not worker_id
    ):
        _runtime_input_invalid()
    projection = state._replay()
    slot_id = projection["active_slot_id"]
    if slot_id is None:
        completed = [
            (slot["source_bundle"]["slot"]["sequence"], slot_id, slot)
            for slot_id, slot in projection["slots"].items()
            if slot["stage"] == "SLOT_SUCCEEDED"
        ]
        if not completed:
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_RUNTIME_RESUME_UNAVAILABLE"
            )
        return _slot_result(max(completed)[2])
    slot = projection["slots"][slot_id]
    return _run_challenger_replacement_slot(
        state=state,
        slot_id=slot_id,
        observed_at=slot["input_recorded_at"],
        worker_id=worker_id,
        fixture_capture=None,
        live_capture=None,
    )


def _run_challenger_replacement_slot(
    *, state, slot_id, observed_at, worker_id, fixture_capture, live_capture
):
    """Share only the fixed event append/recovery engine."""

    projection = state._replay()
    existing = projection["slots"].get(slot_id)
    if existing is not None and existing["stage"] == "SLOT_SUCCEEDED":
        return _slot_result(existing)
    if projection["active_slot_id"] not in (None, slot_id):
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_ACTIVE_SLOT_CONFLICT")
    if existing is None:
        try:
            if live_capture is None:
                source = build_challenger_replacement_source_bundle(
                    plan=state.plan, build_identity=state.build_identity,
                    capture=fixture_capture, observed_at=observed_at,
                    previous_source_bundle=projection["_previous_source_bundle"],
                    previous_decision=projection["_previous_decision"])
                capture_bytes = canonical_json(dict(fixture_capture)).encode("utf-8")
            else:
                source = build_challenger_replacement_cohort_source_bundle(
                    plan=state.plan, build_identity=state.build_identity,
                    live_capture=live_capture,
                    previous_source_bundle=projection["_previous_source_bundle"],
                    previous_decision=projection["_previous_decision"])
                capture_bytes = live_capture.canonical_bytes
        except ValueError as error:
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_SOURCE_BUILD_FAILED") from error
        source_bytes = canonical_json(source).encode("utf-8")
        state.append(
            event_type="INPUT_PREPARED", slot_id=slot_id, worker_id=worker_id,
            recorded_at=observed_at,
            payload={
                "capture_sha256": hashlib.sha256(capture_bytes).hexdigest(),
                "source_bundle_bytes_base64": base64.b64encode(source_bytes).decode("ascii"),
                "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            }, expected_last_event_hash=projection["last_event_hash"])
        projection = state._replay()
        existing = projection["slots"][slot_id]
    if existing["stage"] == "INPUT_PREPARED":
        try:
            if (
                existing["source_bundle"].get("$schema")
                == "./challenger-replacement-source-bundle-v2.schema.json"
            ):
                decision = build_challenger_replacement_cohort_decision(
                    plan=state.plan, source_bundle=existing["source_bundle"],
                    recorded_at=existing["input_recorded_at"],
                    previous_decision=projection["_previous_decision"])
            else:
                decision = build_challenger_replacement_decision(
                    plan=state.plan, source_bundle=existing["source_bundle"],
                    recorded_at=existing["input_recorded_at"],
                    previous_decision=projection["_previous_decision"])
        except ValueError as error:
            token = projection["last_event_hash"]
            state.append(
                event_type=_FAILURE, slot_id=slot_id, worker_id=worker_id,
                recorded_at=_stage_time(existing["input_recorded_at"]),
                payload={"failed_after_event_hash": token,
                         "failed_stage": "INPUT_PREPARED",
                         "reason_code": "CHALLENGER_REPLACEMENT_DECISION_BUILD_FAILED"},
                expected_last_event_hash=token)
            raise ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_DECISION_BUILD_FAILED") from error
        decision_bytes = canonical_json(decision).encode("utf-8")
        state.append(
            event_type="RESULT_PREPARED", slot_id=slot_id, worker_id=worker_id,
            recorded_at=_stage_time(existing["input_recorded_at"]),
            payload={
                "input_event_hash": existing["input_event_hash"],
                "input_event_sequence": existing["input_event_sequence"],
                "source_bundle_sha256": existing["source_bundle_sha256"],
                "decision_bytes_base64": base64.b64encode(decision_bytes).decode("ascii"),
                "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
                "previous_decision_hash_or_null": (
                    None if projection["_previous_decision"] is None
                    else projection["_previous_decision"]["decision_hash"]),
            }, expected_last_event_hash=projection["last_event_hash"])
        projection = state._replay()
        existing = projection["slots"][slot_id]
    if existing["stage"] == "RESULT_PREPARED":
        state.append(
            event_type="SLOT_SUCCEEDED", slot_id=slot_id, worker_id=worker_id,
            recorded_at=_stage_time(existing["result_recorded_at"]),
            payload={
                "input_event_hash": existing["input_event_hash"],
                "input_event_sequence": existing["input_event_sequence"],
                "result_event_hash": existing["result_event_hash"],
                "result_event_sequence": existing["result_event_sequence"],
                "source_bundle_sha256": existing["source_bundle_sha256"],
                "decision_sha256": existing["decision_sha256"],
            }, expected_last_event_hash=projection["last_event_hash"])
        projection = state._replay()
        existing = projection["slots"][slot_id]
    if existing["stage"] != "SLOT_SUCCEEDED":
        raise ChallengerReplacementRuntimeError(
            "CHALLENGER_REPLACEMENT_SLOT_TERMINAL_FAILURE")
    return _slot_result(existing)
