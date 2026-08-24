"""Thin fixture-only v0.72 opportunity orchestrator with zero authority."""

import base64
from copy import deepcopy
import hashlib

from .canonical import canonical_json
from .challenger_replacement_binance_lifecycle import (
    simulate_challenger_replacement_binance_lifecycle,
)
from .challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from .challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
    ChallengerReplacementOpportunityError,
)
from .challenger_replacement_opportunity_evidence import (
    build_challenger_replacement_simulation_result_evidence,
    load_challenger_replacement_simulation_result_evidence_bytes,
)
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_simulation import (
    build_challenger_replacement_genesis_snapshot,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)


def _invalid():
    raise ChallengerReplacementOpportunityError(
        "CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"
    )


def _source(state, input_bytes):
    if not isinstance(input_bytes, bytes) or not input_bytes:
        _invalid()
    try:
        header = _strict_json_bytes(input_bytes)
        opportunity_id = header["opportunity"]["opportunity_id"]
        contract = build_challenger_replacement_simulation_contract(plan=state.plan)
        source = load_challenger_replacement_binance_simulation_input_bytes(
            input_bytes,
            plan=state.plan,
            contract=contract,
            build_identity=state.build_identity,
            opportunity_id=opportunity_id,
        )
        return source, contract
    except ChallengerReplacementOpportunityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_INPUT_INVALID"
        ) from error


def _terminal_result(state, projection, opportunity_id, input_bytes, contract):
    slot = projection["opportunities"].get(opportunity_id)
    if slot is None or slot.get("outcome") != "OBSERVED":
        return None
    if slot.get("source_bundle_bytes") != input_bytes:
        _invalid()
    evidence_bytes = canonical_json(slot["result_evidence"]).encode("utf-8")
    return load_challenger_replacement_simulation_result_evidence_bytes(
        evidence_bytes,
        plan=state.plan,
        contract=contract,
        build_identity=state.build_identity,
    )


def run_challenger_replacement_fixture_simulation_opportunity(
    *, state: ChallengerReplacementOpportunityState, input_bytes: bytes,
    worker_id: str
) -> dict:
    """Run or recover one deterministic fixture opportunity."""

    if (
        not isinstance(state, ChallengerReplacementOpportunityState)
        or not isinstance(worker_id, str)
        or not worker_id
        or state.build_identity["package_version"] != "0.72.0"
    ):
        _invalid()
    source, contract = _source(state, input_bytes)
    opportunity = source["opportunity"]
    opportunity_id = opportunity["opportunity_id"]
    recorded_at = opportunity["observed_at"]
    projection = state._replay()
    terminal = _terminal_result(state, projection, opportunity_id, input_bytes, contract)
    if terminal is not None:
        return terminal
    active = projection["active_opportunity_id"]
    if active not in (None, opportunity_id):
        raise ChallengerReplacementOpportunityError(
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_ACTIVE_CONFLICT"
        )
    slot = projection["opportunities"].get(opportunity_id)
    if slot is None:
        state.append(
            event_type="INPUT_PREPARED",
            opportunity_id=opportunity_id,
            worker_id=worker_id,
            recorded_at=recorded_at,
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": opportunity["scheduled_for"],
                "capture_open": opportunity["capture_open"],
                "capture_close": opportunity["capture_close"],
                "source_bundle_bytes_base64": base64.b64encode(input_bytes).decode("ascii"),
                "source_bundle_sha256": hashlib.sha256(input_bytes).hexdigest(),
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
        projection = state._replay()
        slot = projection["opportunities"][opportunity_id]
    if slot["source_bundle_bytes"] != input_bytes:
        _invalid()
    if slot["stage"] == "INPUT_PREPARED":
        previous = projection["_latest_next_snapshot"]
        if previous is None:
            previous = build_challenger_replacement_genesis_snapshot(
                plan=state.plan, contract=contract
            )
        lifecycle = simulate_challenger_replacement_binance_lifecycle(
            source=source,
            previous_projection=previous,
            plan=state.plan,
            contract=contract,
            build_identity=state.build_identity,
        )
        evidence = build_challenger_replacement_simulation_result_evidence(
            lifecycle_result=lifecycle
        )
        decision_bytes = lifecycle.decision_bytes
        evidence_bytes = canonical_json(evidence).encode("utf-8")
        state.append(
            event_type="RESULT_PREPARED",
            opportunity_id=opportunity_id,
            worker_id=worker_id,
            recorded_at=recorded_at,
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": opportunity["scheduled_for"],
                "input_event_hash": slot["input_event_hash"],
                "input_event_sequence": slot["input_event_sequence"],
                "source_bundle_sha256": slot["source_bundle_sha256"],
                "decision_bytes_base64": base64.b64encode(decision_bytes).decode("ascii"),
                "decision_sha256": hashlib.sha256(decision_bytes).hexdigest(),
                "result_evidence_bytes_base64": base64.b64encode(evidence_bytes).decode("ascii"),
                "result_evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
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
        state.append(
            event_type="OPPORTUNITY_OBSERVED",
            opportunity_id=opportunity_id,
            worker_id=worker_id,
            recorded_at=evidence["opportunity"]["observed_at"],
            payload={
                "opportunity_id": opportunity_id,
                "scheduled_for": opportunity["scheduled_for"],
                "input_event_hash": slot["input_event_hash"],
                "input_event_sequence": slot["input_event_sequence"],
                "result_event_hash": slot["result_event_hash"],
                "result_event_sequence": slot["result_event_sequence"],
                "source_bundle_sha256": slot["source_bundle_sha256"],
                "decision_sha256": slot["decision_sha256"],
                "result_evidence_sha256": slot["result_evidence_sha256"],
                "observed_at": evidence["opportunity"]["observed_at"],
            },
            expected_last_event_hash=projection["last_event_hash"],
        )
    final = state._replay()
    result = _terminal_result(state, final, opportunity_id, input_bytes, contract)
    if result is None:
        _invalid()
    return deepcopy(result)
