"""Schedule and append-only projection for replacement v3 opportunities."""

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional, Tuple

from .canonical import business_hash, canonical_json, utc_datetime
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRoot,
    build_challenger_replacement_event,
    publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_opportunity_evidence import (
    ChallengerReplacementOpportunityEvidenceError,
    load_challenger_replacement_fixture_result_evidence_bytes,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .challenger_replacement_plan_v3 import (
    challenger_replacement_plan_v3_reasons,
)


_CADENCE = timedelta(hours=4)
_OPEN_OFFSET = timedelta(seconds=120)
_CLOSE_OFFSET = timedelta(seconds=600)
_ZERO_HASH = "0" * 64
_HASH_CHARS = frozenset("0123456789abcdef")
_PLAN_ID = (
    "challenger_replacement_plan_v3_"
    "e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
)
_PLAN_HASH = "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
_EVENT_TYPES = {
    "INPUT_PREPARED",
    "RESULT_PREPARED",
    "OPPORTUNITY_OBSERVED",
    "OPPORTUNITY_MISSED",
}


class ChallengerReplacementOpportunityError(ValueError):
    """DecisionOpportunity semantics failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"):
    raise ChallengerReplacementOpportunityError(reason)


def _time(value, *, grid=False):
    if not isinstance(value, str):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"
        ) from error
    parsed = parsed.astimezone(timezone.utc)
    if (
        parsed.microsecond % 1000
        or utc_datetime(parsed) != value
        or (
            grid
            and (
                parsed.hour % 4
                or parsed.minute
                or parsed.second
                or parsed.microsecond
            )
        )
    ):
        _invalid()
    return parsed


def opportunity_id_for(scheduled_for: str) -> str:
    """Derive the only v3 opportunity identifier from a UTC grid time."""

    _time(scheduled_for, grid=True)
    return "ETHUSDT@" + scheduled_for


def _window(scheduled):
    return scheduled + _OPEN_OFFSET, scheduled + _CLOSE_OFFSET


def _candidate(scheduled, detected):
    opened, closed = _window(scheduled)
    if detected < opened:
        status = "NOT_OPEN"
    elif detected <= closed:
        status = "ELIGIBLE_WINDOW"
    else:
        status = "EXPIRED"
    scheduled_text = utc_datetime(scheduled)
    return {
        "opportunity_id": opportunity_id_for(scheduled_text),
        "scheduled_for": scheduled_text,
        "capture_open": utc_datetime(opened),
        "capture_close": utc_datetime(closed),
        "status": status,
    }


def _schedule_count(start, detected):
    return int((detected - start).total_seconds() // int(_CADENCE.total_seconds())) + 1


def derive_due_opportunities(
    *, start_scheduled_for: str, detected_at: str,
    terminal_scheduled_for: Tuple[str, ...]
):
    """Return missing due opportunities from explicit fixture boundaries."""

    start = _time(start_scheduled_for, grid=True)
    detected = _time(detected_at)
    if detected < start or not isinstance(terminal_scheduled_for, tuple):
        _invalid()
    count = _schedule_count(start, detected)
    if count > 1_000_000 or len(terminal_scheduled_for) > count:
        _invalid()
    for index, value in enumerate(terminal_scheduled_for):
        expected = start + index * _CADENCE
        if _time(value, grid=True) != expected:
            _invalid()
    return tuple(
        _candidate(start + index * _CADENCE, detected)
        for index in range(len(terminal_scheduled_for), count)
    )


def opportunity_coverage(observed_count: int, due_count: int):
    """Return exact coverage without Decimal or binary floating point."""

    if (
        isinstance(observed_count, bool)
        or not isinstance(observed_count, int)
        or isinstance(due_count, bool)
        or not isinstance(due_count, int)
        or observed_count < 0
        or due_count < 0
        or observed_count > due_count
    ):
        _invalid()
    return {
        "coverage_numerator": observed_count,
        "coverage_denominator": due_count,
        "meets_minimum_observed_coverage": (
            None if due_count == 0 else observed_count * 100 >= due_count * 95
        ),
    }


def opportunity_health(
    *, projection: Mapping, start_scheduled_for: Optional[str], detected_at: str
):
    """Overlay explicit fixture boundaries on a boundary-free replay."""

    _time(detected_at)
    if not isinstance(projection, Mapping):
        _invalid()
    if start_scheduled_for is None:
        coverage = opportunity_coverage(0, 0)
        return {
            "due_opportunity_count": 0,
            **coverage,
            "eligibility_status": "NOT_STARTED_NO_START_BOUNDARY",
        }
    terminal = projection.get("terminal_scheduled_for")
    observed = projection.get("observed_opportunity_count")
    if not isinstance(terminal, tuple):
        _invalid()
    start = _time(start_scheduled_for, grid=True)
    detected = _time(detected_at)
    if detected < start:
        _invalid()
    due = _schedule_count(start, detected)
    derive_due_opportunities(
        start_scheduled_for=start_scheduled_for,
        detected_at=detected_at,
        terminal_scheduled_for=terminal,
    )
    if len(terminal) > due:
        _invalid()
    coverage = opportunity_coverage(observed, due)
    status = (
        "BLOCKED_LIFECYCLE_EVIDENCE_NOT_IMPLEMENTED"
        if coverage["meets_minimum_observed_coverage"]
        else "PRE_TAIL_ELIGIBILITY_ONLY"
    )
    return {
        "due_opportunity_count": due,
        **coverage,
        "eligibility_status": status,
    }


def _hash_valid(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and not set(value) - _HASH_CHARS
    )


def _build_identity(value):
    keys = {
        "release_tag",
        "peeled_commit",
        "package_version",
        "manifest_version",
        "build_input_tree_hash",
        "manifest_hash",
        "manifest_file_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != keys
        or value["release_tag"] not in {"v0.70.0", "v0.70.0-fixture"}
        or value["package_version"] != "0.70.0"
        or value["manifest_version"] != "1.64.0"
        or not isinstance(value["peeled_commit"], str)
        or len(value["peeled_commit"]) != 40
        or set(value["peeled_commit"]) - _HASH_CHARS
        or not all(
            _hash_valid(value[name])
            for name in (
                "build_input_tree_hash",
                "manifest_hash",
                "manifest_file_sha256",
            )
        )
    ):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
    return dict(value)


def _decode_canonical(value, claimed_hash):
    if not isinstance(value, str) or not _hash_valid(claimed_hash):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    try:
        data = base64.b64decode(value, validate=True)
        document = _strict_json_bytes(data)
        if canonical_json(document).encode("utf-8") != data:
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    except ChallengerReplacementOpportunityError:
        raise
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
        ) from error
    if not data or hashlib.sha256(data).hexdigest() != claimed_hash:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    return data


def _payload(event):
    try:
        header = json.loads(event.final_bytes.decode("utf-8"))
        payload_bytes = base64.b64decode(
            header["payload_bytes_base64"], validate=True
        )
        payload = _strict_json_bytes(payload_bytes)
    except (ChallengerReplacementPlanError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
        ) from error
    if not isinstance(payload, Mapping):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    return header, payload


def _exact(payload, keys):
    if set(payload) != set(keys):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")


def _new_projection(replay):
    return {
        "events": replay.events,
        "opportunities": {},
        "active_opportunity_id": None,
        "first_scheduled_for": None,
        "last_terminal_scheduled_for": None,
        "next_required_opportunity": None,
        "terminal_scheduled_for": (),
        "terminal_opportunity_count": 0,
        "observed_opportunity_count": 0,
        "missed_opportunity_count": 0,
        "current_consecutive_missed": 0,
        "maximum_consecutive_missed": 0,
        "missed_reason_counts": {},
        "maximum_detection_delay_seconds": 0,
        "last_event_hash": replay.last_event_hash,
        "next_sequence": replay.next_sequence,
        "orphan_staging_count": replay.orphan_staging_count,
        "orphan_staging_bytes": replay.orphan_staging_bytes,
        "_previous_observed_source_bytes": None,
        "_previous_observed_decision_bytes": None,
        "_previous_observed_decision_hash": None,
        "_terminal_ids": set(),
    }


def _expected_scheduled(projection):
    previous = projection["last_terminal_scheduled_for"]
    if previous is None:
        return None
    return utc_datetime(_time(previous, grid=True) + _CADENCE)


def _validate_schedule(projection, opportunity_id, scheduled_for):
    if opportunity_id_for(scheduled_for) != opportunity_id:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    expected = _expected_scheduled(projection)
    if expected is not None and scheduled_for != expected:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")


def _apply_event(projection, event, plan, build_identity):
    header, payload = _payload(event)
    event_type = header.get("event_type")
    opportunity_id = header.get("slot_id")
    if (
        event_type not in _EVENT_TYPES
        or header.get("plan_hash") != _PLAN_HASH
        or header.get("build_identity_hash") != business_hash(build_identity)
        or opportunity_id in projection["_terminal_ids"]
        or not isinstance(opportunity_id, str)
        or payload.get("opportunity_id") != opportunity_id
    ):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    scheduled_for = payload.get("scheduled_for")
    _validate_schedule(projection, opportunity_id, scheduled_for)

    if event_type == "INPUT_PREPARED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "capture_open", "capture_close",
            "source_bundle_bytes_base64", "source_bundle_sha256",
        ))
        if (
            projection["active_opportunity_id"] is not None
            or opportunity_id in projection["opportunities"]
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        scheduled = _time(scheduled_for, grid=True)
        opened, closed = _window(scheduled)
        recorded = _time(header.get("recorded_at"))
        if (
            payload["capture_open"] != utc_datetime(opened)
            or payload["capture_close"] != utc_datetime(closed)
            or not opened <= recorded <= closed
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        source_bytes = _decode_canonical(
            payload["source_bundle_bytes_base64"],
            payload["source_bundle_sha256"],
        )
        projection["opportunities"][opportunity_id] = {
            "stage": event_type,
            "outcome": None,
            "scheduled_for": scheduled_for,
            "capture_open": payload["capture_open"],
            "capture_close": payload["capture_close"],
            "source_bundle_bytes": source_bytes,
            "source_bundle_sha256": payload["source_bundle_sha256"],
            "input_event_hash": event.event_hash,
            "input_event_sequence": event.sequence,
            "input_recorded_at": header["recorded_at"],
        }
        projection["active_opportunity_id"] = opportunity_id
        if projection["first_scheduled_for"] is None:
            projection["first_scheduled_for"] = scheduled_for
        return

    if event_type == "OPPORTUNITY_MISSED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "detected_at",
            "missed_after_event_hash_or_null", "missed_after_stage_or_null",
            "reason_code",
        ))
        detected = _time(payload["detected_at"])
        _, closed = _window(_time(scheduled_for, grid=True))
        if (
            header.get("recorded_at") != payload["detected_at"]
            or detected <= closed
            or payload["reason_code"]
            not in plan["opportunity_policy"]["missed_reason_codes"]
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        active = projection["active_opportunity_id"]
        if active is None:
            if (
                payload["missed_after_event_hash_or_null"] is not None
                or payload["missed_after_stage_or_null"] is not None
                or opportunity_id in projection["opportunities"]
            ):
                _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot = {
                "stage": event_type,
                "outcome": "MISSED",
                "scheduled_for": scheduled_for,
            }
            projection["opportunities"][opportunity_id] = slot
            if projection["first_scheduled_for"] is None:
                projection["first_scheduled_for"] = scheduled_for
        else:
            if active != opportunity_id:
                _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot = projection["opportunities"][opportunity_id]
            if (
                slot["stage"] not in {"INPUT_PREPARED", "RESULT_PREPARED"}
                or payload["missed_after_stage_or_null"] != slot["stage"]
                or payload["missed_after_event_hash_or_null"]
                != event.previous_event_hash
            ):
                _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
            slot.update(stage=event_type, outcome="MISSED")
        slot["reason_code"] = payload["reason_code"]
        slot["detected_at"] = payload["detected_at"]
        delay = int((detected - _time(scheduled_for, grid=True)).total_seconds())
        projection["maximum_detection_delay_seconds"] = max(
            projection["maximum_detection_delay_seconds"], delay
        )
        projection["missed_opportunity_count"] += 1
        projection["current_consecutive_missed"] += 1
        projection["maximum_consecutive_missed"] = max(
            projection["maximum_consecutive_missed"],
            projection["current_consecutive_missed"],
        )
        reasons = projection["missed_reason_counts"]
        reasons[payload["reason_code"]] = reasons.get(payload["reason_code"], 0) + 1
        _terminalize(projection, opportunity_id, scheduled_for)
        return

    if projection["active_opportunity_id"] != opportunity_id:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    slot = projection["opportunities"].get(opportunity_id)
    if slot is None:
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")

    if event_type == "RESULT_PREPARED":
        _exact(payload, (
            "opportunity_id", "scheduled_for", "input_event_hash",
            "input_event_sequence", "source_bundle_sha256",
            "decision_bytes_base64", "decision_sha256",
            "result_evidence_bytes_base64", "result_evidence_sha256",
            "previous_observed_decision_hash_or_null",
        ))
        if (
            slot["stage"] != "INPUT_PREPARED"
            or payload["input_event_hash"] != slot["input_event_hash"]
            or payload["input_event_sequence"] != slot["input_event_sequence"]
            or payload["source_bundle_sha256"] != slot["source_bundle_sha256"]
            or payload["previous_observed_decision_hash_or_null"]
            != projection["_previous_observed_decision_hash"]
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        decision_bytes = _decode_canonical(
            payload["decision_bytes_base64"], payload["decision_sha256"]
        )
        evidence_bytes = _decode_canonical(
            payload["result_evidence_bytes_base64"],
            payload["result_evidence_sha256"],
        )
        try:
            evidence = load_challenger_replacement_fixture_result_evidence_bytes(
                evidence_bytes,
                opportunity_id=opportunity_id,
                scheduled_for=scheduled_for,
                observed_at=json.loads(evidence_bytes)["observed_at"],
                source_bundle_sha256=slot["source_bundle_sha256"],
                decision_sha256=payload["decision_sha256"],
            )
        except (ChallengerReplacementOpportunityEvidenceError, KeyError) as error:
            raise ChallengerReplacementOpportunityError(
                "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID"
            ) from error
        if (
            header["recorded_at"] != evidence["observed_at"]
            or _time(header["recorded_at"]) < _time(slot["input_recorded_at"])
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
        slot.update(
            stage=event_type,
            decision_bytes=decision_bytes,
            decision_sha256=payload["decision_sha256"],
            result_evidence=evidence,
            result_evidence_sha256=payload["result_evidence_sha256"],
            result_event_hash=event.event_hash,
            result_event_sequence=event.sequence,
            result_recorded_at=header["recorded_at"],
        )
        return

    _exact(payload, (
        "opportunity_id", "scheduled_for", "input_event_hash",
        "input_event_sequence", "result_event_hash", "result_event_sequence",
        "source_bundle_sha256", "decision_sha256",
        "result_evidence_sha256", "observed_at",
    ))
    expected = {
        "opportunity_id": opportunity_id,
        "scheduled_for": scheduled_for,
        "input_event_hash": slot.get("input_event_hash"),
        "input_event_sequence": slot.get("input_event_sequence"),
        "result_event_hash": slot.get("result_event_hash"),
        "result_event_sequence": slot.get("result_event_sequence"),
        "source_bundle_sha256": slot.get("source_bundle_sha256"),
        "decision_sha256": slot.get("decision_sha256"),
        "result_evidence_sha256": slot.get("result_evidence_sha256"),
        "observed_at": slot.get("result_evidence", {}).get("observed_at"),
    }
    if (
        slot["stage"] != "RESULT_PREPARED"
        or dict(payload) != expected
        or header.get("recorded_at") != payload["observed_at"]
        or _time(header["recorded_at"]) < _time(slot["result_recorded_at"])
    ):
        _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_INVALID")
    slot.update(stage=event_type, outcome="OBSERVED")
    projection["observed_opportunity_count"] += 1
    projection["current_consecutive_missed"] = 0
    projection["_previous_observed_source_bytes"] = slot["source_bundle_bytes"]
    projection["_previous_observed_decision_bytes"] = slot["decision_bytes"]
    projection["_previous_observed_decision_hash"] = slot["decision_sha256"]
    _terminalize(projection, opportunity_id, scheduled_for)


def _terminalize(projection, opportunity_id, scheduled_for):
    projection["active_opportunity_id"] = None
    projection["terminal_opportunity_count"] += 1
    projection["last_terminal_scheduled_for"] = scheduled_for
    projection["terminal_scheduled_for"] = (
        *projection["terminal_scheduled_for"], scheduled_for
    )
    projection["_terminal_ids"].add(opportunity_id)
    next_scheduled = utc_datetime(_time(scheduled_for, grid=True) + _CADENCE)
    projection["next_required_opportunity"] = {
        "opportunity_id": opportunity_id_for(next_scheduled),
        "scheduled_for": next_scheduled,
    }


def _public_projection(projection):
    return {
        key: value
        for key, value in projection.items()
        if not key.startswith("_")
    }


class ChallengerReplacementOpportunityState:
    """Project and append v3 events against one retained capability."""

    def __init__(self, *, event_root, plan, build_identity):
        if not isinstance(event_root, ChallengerReplacementEventRoot):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
        if (
            not isinstance(plan, Mapping)
            or plan.get("plan_id") != _PLAN_ID
            or plan.get("plan_hash") != _PLAN_HASH
            or challenger_replacement_plan_v3_reasons(plan)
        ):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_IDENTITY_INVALID")
        self.event_root = event_root
        self.plan = deepcopy(dict(plan))
        self.build_identity = _build_identity(build_identity)

    def _replay(self):
        try:
            replay = replay_challenger_replacement_events(self.event_root)
        except ChallengerReplacementEventError as error:
            raise ChallengerReplacementOpportunityError(error.reason_code) from error
        projection = _new_projection(replay)
        for event in replay.events:
            _apply_event(projection, event, self.plan, self.build_identity)
        return projection

    def replay(self):
        return _public_projection(self._replay())

    def append(
        self, *, event_type, opportunity_id, worker_id, recorded_at,
        payload, expected_last_event_hash
    ):
        projection = self._replay()
        if (
            not isinstance(payload, Mapping)
            or not isinstance(worker_id, str)
            or not worker_id
        ):
            _invalid()
        try:
            retry = projection["last_event_hash"] != expected_last_event_hash
            events = projection["events"]
            if retry and (
                not events
                or events[-1].previous_event_hash != expected_last_event_hash
            ):
                _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT")
            event = build_challenger_replacement_event(
                sequence=(
                    events[-1].sequence if retry else projection["next_sequence"]
                ),
                event_type=event_type,
                slot_id=opportunity_id,
                worker_id=worker_id,
                recorded_at=recorded_at,
                previous_event_hash=expected_last_event_hash,
                payload_bytes=canonical_json(dict(payload)).encode("utf-8"),
                plan_hash=_PLAN_HASH,
                build_identity_hash=business_hash(self.build_identity),
                event_root=self.event_root,
            )
            if retry:
                if event.final_bytes != events[-1].final_bytes:
                    _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT")
                return publish_challenger_replacement_event(self.event_root, event)
            candidate = deepcopy(projection)
            _apply_event(candidate, event, self.plan, self.build_identity)
            return publish_challenger_replacement_event(self.event_root, event)
        except ChallengerReplacementOpportunityError:
            raise
        except ChallengerReplacementEventError as error:
            reason = error.reason_code
            if reason == "CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT":
                reason = "CHALLENGER_REPLACEMENT_OPPORTUNITY_SEQUENCE_CONFLICT"
            raise ChallengerReplacementOpportunityError(reason) from error


def catch_up_missed_opportunities(
    *, state, start_scheduled_for, detected_at, worker_id, reason_code
):
    """Append only expired MISSED facts from explicit fixture boundaries."""

    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(start_scheduled_for, str)
        or not isinstance(worker_id, str)
        or not worker_id
        or reason_code
        not in state.plan["opportunity_policy"]["missed_reason_codes"]
    ):
        _invalid()
    projection = state.replay()
    eligible = None
    for candidate in derive_due_opportunities(
        start_scheduled_for=start_scheduled_for,
        detected_at=detected_at,
        terminal_scheduled_for=projection["terminal_scheduled_for"],
    ):
        if candidate["status"] != "EXPIRED":
            eligible = (
                candidate if candidate["status"] == "ELIGIBLE_WINDOW" else None
            )
            break
        active = projection["active_opportunity_id"]
        if active not in (None, candidate["opportunity_id"]):
            _invalid("CHALLENGER_REPLACEMENT_OPPORTUNITY_ACTIVE_CONFLICT")
        if active is None:
            boundary_hash = None
            boundary_stage = None
        else:
            slot = projection["opportunities"][active]
            boundary_hash = projection["last_event_hash"]
            boundary_stage = slot["stage"]
        state.append(
            event_type="OPPORTUNITY_MISSED",
            opportunity_id=candidate["opportunity_id"],
            worker_id=worker_id,
            recorded_at=detected_at,
            payload={
                "opportunity_id": candidate["opportunity_id"],
                "scheduled_for": candidate["scheduled_for"],
                "detected_at": detected_at,
                "missed_after_event_hash_or_null": boundary_hash,
                "missed_after_stage_or_null": boundary_stage,
                "reason_code": reason_code,
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = state.replay()
    return {"projection": projection, "eligible_opportunity": eligible}
