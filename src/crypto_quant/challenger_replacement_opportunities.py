"""Schedule and append-only projection for replacement v3 opportunities."""

from copy import deepcopy
from typing import Mapping, Optional, Tuple

from .canonical import business_hash, canonical_json, utc_datetime
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRoot,
    build_challenger_replacement_event,
    publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_opportunity_projection import (
    CADENCE as _CADENCE,
    CLOSE_OFFSET as _CLOSE_OFFSET,
    OPEN_OFFSET as _OPEN_OFFSET,
    PLAN_HASH as _PLAN_HASH,
    PLAN_ID as _PLAN_ID,
    ChallengerReplacementOpportunityError,
    apply_opportunity_event as _apply_opportunity_event,
    canonical_time as _time,
    initial_opportunity_projection as _initial_opportunity_projection,
    invalid as _invalid,
    opportunity_id_for,
    opportunity_window as _window,
    public_opportunity_projection as _public_opportunity_projection,
    validate_build_identity as _build_identity,
)
from .challenger_replacement_plan_v3 import (
    challenger_replacement_plan_v3_reasons,
)

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
        projection = _initial_opportunity_projection(
            plan=self.plan,
            build_identity=self.build_identity,
        )
        projection.update(
            events=replay.events,
            last_event_hash=replay.last_event_hash,
            next_sequence=replay.next_sequence,
            orphan_staging_count=replay.orphan_staging_count,
            orphan_staging_bytes=replay.orphan_staging_bytes,
        )
        for event in replay.events:
            _apply_opportunity_event(
                projection,
                event,
                plan=self.plan,
                build_identity=self.build_identity,
            )
        return projection

    def replay(self):
        return _public_opportunity_projection(self._replay())

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
            _apply_opportunity_event(
                candidate,
                event,
                plan=self.plan,
                build_identity=self.build_identity,
            )
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
