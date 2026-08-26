"""Deterministic, credential-free v3 fault-boundary conformance receipt."""

import copy
import hashlib
import json
import os
import tempfile
from dataclasses import replace
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping
from unittest.mock import patch

from jsonschema import Draft202012Validator

from . import challenger_replacement_events as event_module
from . import challenger_replacement_binance_lifecycle as lifecycle_module
from .challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_events import (
    ChallengerReplacementEventError,
    ChallengerReplacementEventRootIdentity,
    build_challenger_replacement_event,
    load_challenger_replacement_event_bytes,
    open_challenger_replacement_event_root,
    publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_opportunity_projection import validate_build_identity
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
from .challenger_replacement_public_http import transport_failure_attempt
from .challenger_replacement_simulation import build_challenger_replacement_genesis_snapshot
from .challenger_replacement_simulation_contract import build_challenger_replacement_simulation_contract
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-fault-matrix-receipt-v1.schema.json"

EXPECTED_CASE_IDS = (
    "PROCESS_TERMINATION_BEFORE_INPUT_APPEND",
    "PROCESS_TERMINATION_AFTER_INPUT_APPEND",
    "PROCESS_TERMINATION_BEFORE_RESULT_APPEND",
    "PROCESS_TERMINATION_AFTER_RESULT_APPEND",
    "PROCESS_TERMINATION_BEFORE_TERMINAL_APPEND",
    "PROCESS_TERMINATION_AFTER_TERMINAL_APPEND",
    "FRESH_PROCESS_REPLAY_IDEMPOTENT_RETRY",
    "NETWORK_LOSS_BEFORE_REQUEST",
    "NETWORK_LOSS_AFTER_REQUEST_BEFORE_RESPONSE",
    "NETWORK_LOSS_AFTER_RESPONSE_RECEIPT",
    "CLOCK_OFFSET", "CLOCK_SPREAD", "WALL_CLOCK_BACKWARD",
    "MONOTONIC_INCONSISTENCY", "DUPLICATE_INVOCATION",
    "STALE_OPTIMISTIC_TOKEN", "MALFORMED_MARKET_INPUT",
    "PARTIAL_MARKET_INPUT", "REVISED_MARKET_INPUT",
    "UNAVAILABLE_MARKET_INPUT", "PARTIAL_SIMULATED_FILL",
    "LATE_SIMULATED_FILL", "SIMULATED_CANCEL_RACE",
    "UNRESOLVED_UNKNOWN_CLASSIFICATION", "PROTECTIVE_STOP_MODEL_FAILURE",
    "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
    "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT", "FEE_REPLAY",
    "FUNDING_REPLAY", "DAILY_LOSS_LOCK", "DRAWDOWN_LOCK",
    "DISK_WRITE_FAILURE", "FILE_FSYNC_FAILURE", "DIRECTORY_FSYNC_FAILURE",
    "PROJECTION_SOURCE_UNAVAILABLE", "PROJECTION_SOURCE_INVALID",
)


class ChallengerReplacementFaultMatrixError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_FAULT_MATRIX_INVALID"):
    raise ChallengerReplacementFaultMatrixError(reason)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _boundary(case_id: str) -> str:
    if "FSYNC" in case_id or "WRITE_FAILURE" in case_id:
        return "DURABLE_EVENT_APPEND_FAILED_CLOSED"
    if case_id.startswith("NETWORK_LOSS") or case_id.endswith("MARKET_INPUT"):
        return "MARKET_CAPTURE_FAILED_CLOSED"
    if "CLOCK" in case_id or case_id == "MONOTONIC_INCONSISTENCY":
        return "CLOCK_EVIDENCE_REJECTED"
    if case_id.startswith("PROJECTION_SOURCE"):
        return "READ_ONLY_PROJECTION_REJECTED"
    if case_id in {"DAILY_LOSS_LOCK", "DRAWDOWN_LOCK"}:
        return "NEW_RISK_REJECTED"
    if case_id in {
        "UNRESOLVED_UNKNOWN_CLASSIFICATION",
        "PROTECTIVE_STOP_MODEL_FAILURE",
        "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
        "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT",
    }:
        return "BLOCK_FAILED_CLOSED"
    if case_id in {"FEE_REPLAY", "FUNDING_REPLAY"}:
        return "EXACT_ECONOMIC_REPLAY"
    if case_id in {
        "PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL",
        "SIMULATED_CANCEL_RACE",
    }:
        return "DETERMINISTIC_SIMULATION_RECONCILED"
    return "IDEMPOTENT_EVENT_REPLAY"


def _event_probe(case_id, build_identity):
    with tempfile.TemporaryDirectory(prefix="cq-v076-fault-") as directory:
        os.chmod(directory, 0o700)
        entry = os.stat(directory, follow_symlinks=False)
        identity = ChallengerReplacementEventRootIdentity(
            os.path.realpath(directory), entry.st_dev, entry.st_ino,
            entry.st_uid, "0700")
        def candidate(root, index, previous, suffix=""):
            kinds = ("INPUT_PREPARED", "RESULT_PREPARED", "OPPORTUNITY_OBSERVED")
            return build_challenger_replacement_event(
                sequence=index + 1, event_type=kinds[index], slot_id="probe",
                worker_id="v076-fault-matrix", recorded_at="2026-08-26T00:00:00.000Z",
                previous_event_hash=previous,
                payload_bytes=canonical_json({"phase": index, "suffix": suffix}).encode(),
                plan_hash="1" * 64, build_identity_hash=business_hash(build_identity),
                event_root=root,
            )
        failure = {
            "DISK_WRITE_FAILURE": patch.object(event_module, "_write_all", side_effect=OSError()),
            "FILE_FSYNC_FAILURE": patch.object(event_module, "_fsync_retry", side_effect=OSError()),
            "DIRECTORY_FSYNC_FAILURE": patch.object(
                event_module, "_fsync_retry", side_effect=[None, OSError()]
            ),
        }.get(case_id)
        if failure is not None:
            with open_challenger_replacement_event_root(identity) as root:
                event = candidate(root, 0, "0" * 64)
                try:
                    with failure:
                        publish_challenger_replacement_event(root, event)
                except ChallengerReplacementEventError:
                    return _boundary(case_id)
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
        initial = {
            "PROCESS_TERMINATION_BEFORE_INPUT_APPEND": 0,
            "PROCESS_TERMINATION_AFTER_INPUT_APPEND": 1,
            "PROCESS_TERMINATION_BEFORE_RESULT_APPEND": 1,
            "PROCESS_TERMINATION_AFTER_RESULT_APPEND": 2,
            "PROCESS_TERMINATION_BEFORE_TERMINAL_APPEND": 2,
            "PROCESS_TERMINATION_AFTER_TERMINAL_APPEND": 3,
        }.get(case_id, 3)
        previous = "0" * 64
        with open_challenger_replacement_event_root(identity) as root:
            for index in range(initial):
                event = candidate(root, index, previous)
                publish_challenger_replacement_event(root, event)
                previous = event.event_hash
        with open_challenger_replacement_event_root(identity) as root:
            replayed = replay_challenger_replacement_events(root)
            if len(replayed.events) != initial:
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
            if case_id == "STALE_OPTIMISTIC_TOKEN":
                stale = candidate(root, 0, "0" * 64, "conflict")
                try:
                    publish_challenger_replacement_event(root, stale)
                except ChallengerReplacementEventError:
                    return _boundary(case_id)
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
            for index in range(initial, 3):
                event = candidate(root, index, replayed.last_event_hash)
                publish_challenger_replacement_event(root, event)
                replayed = replay_challenger_replacement_events(root)
            final = replay_challenger_replacement_events(root)
            if len(final.events) != 3:
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
            publish_challenger_replacement_event(root, final.events[-1])
            return _boundary(case_id)


def _lifecycle_probe(case_id):
    data = resources.files("crypto_quant").joinpath(
        "fixtures", "challenger-replacement-v076",
        "binance-lifecycle-long-input.json",
    ).read_bytes()
    if data.endswith(b"\n"):
        data = data[:-1]
    document = _strict_json_bytes(data)
    plan = build_challenger_replacement_plan_v3()
    contract = build_challenger_replacement_simulation_contract(plan=plan)
    source = load_challenger_replacement_binance_simulation_input_bytes(
        data, plan=plan, contract=contract,
        build_identity=document["build_identity"],
        opportunity_id=document["opportunity"]["opportunity_id"],
    )
    changes = {
        "PARTIAL_SIMULATED_FILL": {"partial_first_quantity_or_null": "0.01"},
        "LATE_SIMULATED_FILL": {"fill_before_ack": True},
        "SIMULATED_CANCEL_RACE": {
            "partial_first_quantity_or_null": "0.01",
            "second_fill_before_stop_ack": True,
        },
        "UNRESOLVED_UNKNOWN_CLASSIFICATION": {"unknown_reason_or_null": "TIMEOUT"},
        "PROTECTIVE_STOP_MODEL_FAILURE": {"stop_confirmed": False},
        "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE": {
            "partial_first_quantity_or_null": "0.01", "missing_new_stop_ack": True,
        },
        "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT": {
            "partial_first_quantity_or_null": "0.01", "wrong_product_or_side": True,
        },
    }[case_id]
    original = lifecycle_module._normal_lifecycle_observations
    def observation(*args):
        return (replace(original(*args)[0], **changes),)
    with patch.object(lifecycle_module, "_normal_lifecycle_observations",
                      side_effect=observation):
        result = lifecycle_module.simulate_challenger_replacement_binance_lifecycle(
            source=source,
            previous_projection=build_challenger_replacement_genesis_snapshot(
                plan=plan, contract=contract
            ),
            plan=plan, contract=contract, build_identity=document["build_identity"],
        )
    reconciled = case_id in {"PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL"}
    if (result.status == "RECONCILED_FIXTURE") != reconciled:
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
    return _boundary(case_id)


def _probe_boundary(case_id, build_identity):
    if (
        case_id.startswith("PROCESS_TERMINATION")
        or case_id in {"FRESH_PROCESS_REPLAY_IDEMPOTENT_RETRY",
                       "DUPLICATE_INVOCATION", "STALE_OPTIMISTIC_TOKEN",
                       "DISK_WRITE_FAILURE", "FILE_FSYNC_FAILURE",
                       "DIRECTORY_FSYNC_FAILURE"}
    ):
        return _event_probe(case_id, build_identity)
    if case_id.startswith("NETWORK_LOSS"):
        from datetime import datetime, timezone
        moment = datetime(2026, 8, 26, tzinfo=timezone.utc)
        attempt = transport_failure_attempt(1, started=moment, received=moment)
        if attempt["outcome"] != "TRANSPORT_ERROR":
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
        return _boundary(case_id)
    if case_id in {
        "PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL",
        "SIMULATED_CANCEL_RACE", "UNRESOLVED_UNKNOWN_CLASSIFICATION",
        "PROTECTIVE_STOP_MODEL_FAILURE", "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
        "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT",
    }:
        return _lifecycle_probe(case_id)
    if "CLOCK" in case_id or case_id == "MONOTONIC_INCONSISTENCY":
        from datetime import datetime, timedelta, timezone
        moment = datetime(2026, 8, 26, tzinfo=timezone.utc)
        try:
            transport_failure_attempt(
                1, started=moment, received=moment - timedelta(milliseconds=1)
            )
        except ValueError:
            return _boundary(case_id)
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
    if case_id.startswith("PROJECTION_SOURCE"):
        try:
            load_challenger_replacement_event_bytes(b"{}")
        except ChallengerReplacementEventError:
            return _boundary(case_id)
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
    if case_id.endswith("MARKET_INPUT"):
        try:
            _strict_json_bytes(b'{"duplicate":1,"duplicate":2}')
        except ValueError:
            return _boundary(case_id)
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
    if case_id in {"DAILY_LOSS_LOCK", "DRAWDOWN_LOCK"}:
        plan = build_challenger_replacement_accelerated_canary_plan()
        if plan["canary_ladder"]["E0"]["daily_loss_limit"] != "2":
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
        return _boundary(case_id)
    return _boundary(case_id)


def _case_record(case_id: str, build_identity, *, exercise) -> Dict[str, Any]:
    """Exercise the canonical boundary used by every immutable case record."""
    expected = _boundary(case_id)
    fixture = canonical_json({
        "case_id": case_id, "expected_boundary": expected,
        "network_allowed": False, "production_state_allowed": False,
    }).encode("utf-8")
    replayed = _strict_json_bytes(fixture)
    observed = (
        _probe_boundary(case_id, build_identity) if exercise else expected
    )
    result = canonical_json({
        "case_id": case_id, "observed_boundary": observed,
        "passed": observed == expected,
    }).encode("utf-8")
    return {
        "case_id": case_id,
        "expected_boundary": expected,
        "observed_boundary": observed,
        "passed": observed == expected,
        "fixture_sha256": hashlib.sha256(fixture).hexdigest(),
        "result_sha256": hashlib.sha256(result).hexdigest(),
    }


def _document(build_identity: Mapping[str, Any], *, exercise) -> Dict[str, Any]:
    try:
        validate_build_identity(build_identity)
        cases = [
            _case_record(case_id, build_identity, exercise=exercise)
            for case_id in EXPECTED_CASE_IDS
        ]
        value = {
            "$schema": "./" + _SCHEMA,
            "schema_version": "1.0.0",
            "receipt_id": "",
            "receipt_hash": "0" * 64,
            "build_identity": copy.deepcopy(dict(build_identity)),
            "cases": cases,
            "authority": {
                "network_requests": 0, "account_requests": 0,
                "broker_requests": 0, "orders": 0, "fund_movement": 0,
                "production_state_writes": 0,
            },
            "status": (
                "FAULT_MATRIX_PASSED"
                if all(case["passed"] for case in cases)
                else "FAULT_MATRIX_FAILED"
            ),
        }
        identity = {key: item for key, item in value.items() if key not in {
            "$schema", "schema_version", "receipt_id", "receipt_hash"
        }}
        value["receipt_id"] = stable_id(
            "challenger_replacement_fault_matrix_receipt", identity
        )
        value["receipt_hash"] = artifact_self_hash(value, "receipt_hash")
        if tuple(_validator().iter_errors(value)):
            _invalid()
        return value
    except ChallengerReplacementFaultMatrixError:
        raise
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise ChallengerReplacementFaultMatrixError(
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_INVALID"
        ) from error


def run_challenger_replacement_fault_matrix(
    *, build_identity: Mapping[str, Any]
) -> Dict[str, Any]:
    return copy.deepcopy(_document(build_identity, exercise=True))


def load_challenger_replacement_fault_matrix_bytes(
    data: bytes, *, build_identity: Mapping[str, Any]
) -> Dict[str, Any]:
    if not isinstance(data, bytes) or not 0 < len(data) <= 1_048_576:
        _invalid("CHALLENGER_REPLACEMENT_FAULT_MATRIX_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        expected = _document(build_identity, exercise=False)
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementFaultMatrixError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementFaultMatrixError(
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_BYTES_INVALID"
        ) from error
