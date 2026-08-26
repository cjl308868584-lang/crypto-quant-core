"""Replay-first composition of one public v3 DecisionOpportunity."""

import base64
import fcntl
import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .canonical import canonical_json, utc_datetime
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_events import ChallengerReplacementEventRoot
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    ChallengerReplacementOpportunityState,
    catch_up_missed_opportunities,
)
from .challenger_replacement_opportunity_projection import canonical_time
from .challenger_replacement_public_market_capture import (
    ChallengerReplacementPublicMarketCaptureError,
    acquire_challenger_replacement_public_market_capture,
    load_challenger_replacement_public_market_capture_bytes,
)
from .challenger_replacement_public_simulation import (
    build_challenger_replacement_public_simulation_input,
    build_challenger_replacement_public_simulation_result,
    simulate_challenger_replacement_public_opportunity,
)
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)


_WORKER_ID = "challenger-replacement-v3-public-runtime"


def _invalid(reason="CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"):
    raise ChallengerReplacementOpportunityError(reason)


def _acquire(state):
    return acquire_challenger_replacement_public_market_capture(state=state)


def _append(state, **kwargs):
    return state.append(**kwargs)


def _wall_now():
    return datetime.now(timezone.utc)


def _validate(
    state, event_root, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(event_root, ChallengerReplacementEventRoot)
        or state.event_root is not event_root
        or state.plan != dict(plan)
        or state.build_identity != dict(build_identity)
        or economic_plan != build_challenger_replacement_economic_plan()
        or predecessor_contract
        != build_challenger_replacement_simulation_contract(plan=plan)
        or public_contract
        != build_challenger_replacement_public_simulation_contract(
            plan=plan,
            economic_plan=economic_plan,
            predecessor_contract=predecessor_contract,
        )
    ):
        _invalid()


def _terminal(projection):
    if not projection["terminal_scheduled_for"]:
        return None
    opportunity_id = "ETHUSDT@" + projection["terminal_scheduled_for"][-1]
    slot = projection["opportunities"][opportunity_id]
    if slot.get("outcome") != "OBSERVED":
        return None
    return {
        "status": "ALREADY_TERMINAL",
        "opportunity_id": opportunity_id,
        "result": deepcopy(slot["result_evidence"]),
    }


def _source_from_capture(
    capture_bytes, projection, *, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    previous_bytes = projection["_previous_observed_source_bytes"]
    previous = None
    if previous_bytes is not None:
        previous_capture = load_challenger_replacement_public_market_capture_bytes(
            previous_bytes,
            plan=plan,
            build_identity=build_identity,
            previous_source_bundle=None,
        )
        previous = {"klines": previous_capture.document["normalized"]["bars"]}
    capture = load_challenger_replacement_public_market_capture_bytes(
        capture_bytes,
        plan=plan,
        build_identity=build_identity,
        previous_source_bundle=previous,
    )
    return build_challenger_replacement_public_simulation_input(
        capture,
        plan=plan,
        economic_plan=economic_plan,
        predecessor_contract=predecessor_contract,
        public_contract=public_contract,
        build_identity=build_identity,
    )


def _run_locked(
    *, state, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    """Acquire or replay exactly one natural public opportunity."""
    projection = state._replay()
    terminal = _terminal(projection)
    if terminal is not None and projection["active_opportunity_id"] is None:
        next_required = projection["next_required_opportunity"]
        now = _wall_now().astimezone(timezone.utc)
        next_scheduled = canonical_time(next_required["scheduled_for"], grid=True)
        if now < next_scheduled + timedelta(minutes=2):
            return terminal
        caught_up = catch_up_missed_opportunities(
            state=state,
            start_scheduled_for=projection["first_scheduled_for"],
            detected_at=utc_datetime(now),
            worker_id=_WORKER_ID,
            reason_code="CAPTURE_WINDOW_EXPIRED",
        )
        projection = state._replay()
        if caught_up["eligible_opportunity"] is None:
            return {
                "status": "MISSED",
                "opportunity_id": (
                    "ETHUSDT@" + projection["terminal_scheduled_for"][-1]
                ),
                "result": None,
            }
    if projection["active_opportunity_id"] is not None:
        opportunity_id = projection["active_opportunity_id"]
        slot = projection["opportunities"][opportunity_id]
    else:
        try:
            capture = _acquire(state)
        except ChallengerReplacementPublicMarketCaptureError as error:
            raise ChallengerReplacementOpportunityError(
                error.reason_code
            ) from error
        opportunity = capture.document["opportunity"]
        scheduled = canonical_time(opportunity["scheduled_for"], grid=True)
        source_bytes = bytes(capture.canonical_bytes)
        _append(state,
            event_type="INPUT_PREPARED",
            opportunity_id=opportunity["opportunity_id"],
            worker_id=_WORKER_ID,
            recorded_at=opportunity["captured_at"],
            payload={
                "opportunity_id": opportunity["opportunity_id"],
                "scheduled_for": opportunity["scheduled_for"],
                "capture_open": utc_datetime(scheduled + timedelta(minutes=2)),
                "capture_close": utc_datetime(scheduled + timedelta(minutes=10)),
                "source_bundle_bytes_base64": base64.b64encode(
                    source_bytes
                ).decode("ascii"),
                "source_bundle_sha256": hashlib.sha256(source_bytes).hexdigest(),
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = state._replay()
        opportunity_id = opportunity["opportunity_id"]
        slot = projection["opportunities"][opportunity_id]
    if slot["stage"] == "INPUT_PREPARED":
        source = _source_from_capture(
            slot["source_bundle_bytes"],
            projection,
            plan=plan,
            economic_plan=economic_plan,
            predecessor_contract=predecessor_contract,
            public_contract=public_contract,
            build_identity=build_identity,
        )
        previous = projection["_latest_next_snapshot"]
        transition = simulate_challenger_replacement_public_opportunity(
            source=source,
            previous_projection=previous,
            plan=plan,
            public_contract=public_contract,
            build_identity=build_identity,
        )
        result = build_challenger_replacement_public_simulation_result(
            source=source,
            previous_projection=previous,
            transition=transition,
            plan=plan,
            economic_plan=economic_plan,
            public_contract=public_contract,
            build_identity=build_identity,
            sequence=projection["next_sequence"],
            parent_event_hash=projection["last_event_hash"],
        )
        decision_bytes = canonical_json(transition["decision"]).encode("utf-8")
        result_bytes = canonical_json(result).encode("utf-8")
        _append(state,
            event_type="RESULT_PREPARED",
            opportunity_id=opportunity_id,
            worker_id=_WORKER_ID,
            recorded_at=source["opportunity"]["captured_at"],
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": source["opportunity"]["scheduled_for"],
                "input_event_hash": slot["input_event_hash"],
                "input_event_sequence": slot["input_event_sequence"],
                "source_bundle_sha256": slot["source_bundle_sha256"],
                "decision_bytes_base64": base64.b64encode(decision_bytes).decode("ascii"),
                "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
                "result_evidence_bytes_base64": base64.b64encode(result_bytes).decode("ascii"),
                "result_evidence_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "previous_observed_decision_hash_or_null": projection[
                    "_previous_observed_decision_hash"
                ],
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = state._replay()
        slot = projection["opportunities"][opportunity_id]
    if slot["stage"] == "RESULT_PREPARED":
        evidence = slot["result_evidence"]
        _append(state,
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=opportunity_id,
            worker_id=_WORKER_ID,
            recorded_at=evidence["opportunity"]["captured_at"],
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": slot["scheduled_for"],
                "input_event_hash": slot["input_event_hash"],
                "input_event_sequence": slot["input_event_sequence"],
                "result_event_hash": slot["result_event_hash"],
                "result_event_sequence": slot["result_event_sequence"],
                "source_bundle_sha256": slot["source_bundle_sha256"],
                "decision_sha256": slot["decision_sha256"],
                "result_evidence_sha256": slot["result_evidence_sha256"],
                "observed_at": evidence["opportunity"]["captured_at"],
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
    final = state._replay()
    terminal = _terminal(final)
    if terminal is None:
        _invalid()
    terminal["status"] = "OBSERVED"
    return terminal


def run_challenger_replacement_v3_opportunity(
    *, state, event_root, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    """Serialize one replay/advance transaction on the retained root."""

    _validate(
        state, event_root, plan, economic_plan, predecessor_contract,
        public_contract, build_identity
    )
    try:
        fcntl.flock(event_root.descriptor, fcntl.LOCK_EX)
    except OSError as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_ROOT_CHANGED"
        ) from error
    primary_error = None
    try:
        return _run_locked(
            state=state,
            plan=plan,
            economic_plan=economic_plan,
            predecessor_contract=predecessor_contract,
            public_contract=public_contract,
            build_identity=build_identity,
        )
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            fcntl.flock(event_root.descriptor, fcntl.LOCK_UN)
        except OSError as error:
            reason = "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_ROOT_CHANGED"
            if primary_error is not None:
                try:
                    primary_error.unlock_failure_reason_code = reason
                except (AttributeError, TypeError):
                    pass
            else:
                raise ChallengerReplacementOpportunityError(reason) from error
