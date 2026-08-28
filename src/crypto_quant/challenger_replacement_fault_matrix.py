"""Deterministic, credential-free v3 fault-boundary conformance receipt."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request

from jsonschema import Draft202012Validator

from . import challenger_replacement_events as event_module
from . import challenger_replacement_binance_lifecycle as lifecycle_module
from . import challenger_replacement_simulation as simulation_module
from . import challenger_replacement_public_http as http_module
from . import challenger_replacement_public_market_capture as capture_module
from . import challenger_replacement_v3_observer as observer_module
from . import operations_projection_v3 as projection_module
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
    open_challenger_replacement_event_root,
    publish_challenger_replacement_event,
    replay_challenger_replacement_events,
)
from .challenger_replacement_opportunity_projection import validate_build_identity
from .challenger_replacement_plan import _strict_json_bytes
from .challenger_replacement_plan_v3 import build_challenger_replacement_plan_v3
from .challenger_replacement_simulation import build_challenger_replacement_genesis_snapshot
from .challenger_replacement_simulation_contract import build_challenger_replacement_simulation_contract
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-fault-matrix-receipt-v1.schema.json"
_DEPLOYMENT_ARTIFACT = (
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-deployment-v0.76.0.json"
)

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
    if case_id == "NETWORK_LOSS_AFTER_RESPONSE_RECEIPT":
        return "RESPONSE_RECEIPT_REPLAYED"
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


def _event_candidate(root, build_identity, index, previous, suffix=""):
    kinds = ("INPUT_PREPARED", "RESULT_PREPARED", "OPPORTUNITY_OBSERVED")
    return build_challenger_replacement_event(
        sequence=index + 1, event_type=kinds[index], slot_id="probe",
        worker_id="v076-fault-matrix", recorded_at="2026-08-26T00:00:00.000Z",
        previous_event_hash=previous,
        payload_bytes=canonical_json({"phase": index, "suffix": suffix}).encode(),
        plan_hash="1" * 64, build_identity_hash=business_hash(build_identity),
        event_root=root,
    )


def _event_child_cli(arguments):
    identity = ChallengerReplacementEventRootIdentity(
        arguments[0], *(int(value) for value in arguments[1:4]), "0700"
    )
    build_identity = _strict_json_bytes(bytes.fromhex(arguments[4]))
    previous = "0" * 64
    with open_challenger_replacement_event_root(identity) as root:
        for index in range(int(arguments[5])):
            event = _event_candidate(root, build_identity, index, previous)
            publish_challenger_replacement_event(root, event)
            previous = event.event_hash
    os._exit(73)


def _run_event_child(identity, build_identity, initial):
    code = (
        "import sys; from crypto_quant.challenger_replacement_fault_matrix "
        "import _event_child_cli; _event_child_cli(sys.argv[1:])"
    )
    process = subprocess.Popen([
        sys.executable, "-c", code, identity.absolute_path,
        str(identity.device), str(identity.inode), str(identity.uid),
        canonical_json(build_identity).encode().hex(), str(initial),
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL, close_fds=True)
    if process.wait() != 73 or process.pid == os.getpid():
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")


def _event_probe(case_id, build_identity):
    with tempfile.TemporaryDirectory(prefix="cq-v076-fault-") as directory:
        os.chmod(directory, 0o700)
        entry = os.stat(directory, follow_symlinks=False)
        identity = ChallengerReplacementEventRootIdentity(
            os.path.realpath(directory), entry.st_dev, entry.st_ino,
            entry.st_uid, "0700")
        failure = {
            "DISK_WRITE_FAILURE": patch.object(event_module, "_write_all", side_effect=OSError()),
            "FILE_FSYNC_FAILURE": patch.object(event_module, "_fsync_retry", side_effect=OSError()),
            "DIRECTORY_FSYNC_FAILURE": patch.object(
                event_module, "_fsync_retry", side_effect=[None, OSError()]
            ),
        }.get(case_id)
        if failure is not None:
            with open_challenger_replacement_event_root(identity) as root:
                event = _event_candidate(root, build_identity, 0, "0" * 64)
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
        process_case = case_id.startswith("PROCESS_TERMINATION") or case_id == (
            "FRESH_PROCESS_REPLAY_IDEMPOTENT_RETRY"
        )
        if process_case:
            _run_event_child(identity, build_identity, initial)
        else:
            with open_challenger_replacement_event_root(identity) as root:
                for index in range(initial):
                    event = _event_candidate(
                        root, build_identity, index, previous
                    )
                    publish_challenger_replacement_event(root, event)
                    previous = event.event_hash
        with open_challenger_replacement_event_root(identity) as root:
            replayed = replay_challenger_replacement_events(root)
            if len(replayed.events) != initial:
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
            if case_id == "STALE_OPTIMISTIC_TOKEN":
                stale = _event_candidate(
                    root, build_identity, 0, "0" * 64, "conflict"
                )
                try:
                    publish_challenger_replacement_event(root, stale)
                except ChallengerReplacementEventError:
                    return _boundary(case_id)
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
            for index in range(initial, 3):
                event = _event_candidate(
                    root, build_identity, index, replayed.last_event_hash
                )
                publish_challenger_replacement_event(root, event)
                replayed = replay_challenger_replacement_events(root)
            final = replay_challenger_replacement_events(root)
            if len(final.events) != 3:
                _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
            publish_challenger_replacement_event(root, final.events[-1])
            return _boundary(case_id)


def _fixture_context():
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
    previous = build_challenger_replacement_genesis_snapshot(
        plan=plan, contract=contract
    )
    return document, source, previous, plan, contract


def _lifecycle_probe(case_id):
    document, source, previous, plan, contract = _fixture_context()
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
            source=source, previous_projection=previous,
            plan=plan, contract=contract, build_identity=document["build_identity"],
        )
    reconciled = case_id in {"PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL"}
    if (result.status == "RECONCILED_FIXTURE") != reconciled:
        _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
    return _boundary(case_id)


def _economic_probe(case_id):
    document, source, previous, plan, contract = _fixture_context()
    if case_id == "FEE_REPLAY":
        result = lifecycle_module.simulate_challenger_replacement_binance_lifecycle(
            source=source, previous_projection=previous, plan=plan,
            contract=contract, build_identity=document["build_identity"],
        )
        fills = (json.loads(event.payload_bytes)["fee"] for event in
                 result.lifecycle_events if event.event_type == "FILL_OBSERVED_FIXTURE")
        if sum(map(Decimal, fills), Decimal("0")) != Decimal(
            json.loads(result.accounting_bytes)["fee"]
        ):
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
    elif case_id == "FUNDING_REPLAY":
        snapshot = copy.deepcopy(previous)
        snapshot.update(position_state="PERP_SHORT", signed_quantity="-0.01",
                        entry_price_or_null="2000", isolated_margin="10",
                        contract_multiplier="1")
        source = copy.deepcopy(source)
        source["funding"] = {"boundary_at_or_null": source["opportunity"]["scheduled_for"],
                             "rate_or_null": "0.001"}
        funding, _cashflows, _daily, _drawdown = simulation_module._prepare_boundary(
            snapshot, source
        )
        if funding != Decimal("0.0199925"):
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
    else:
        snapshot = copy.deepcopy(previous)
        snapshot["day_start_date_or_null"] = source["opportunity"]["scheduled_for"][:10]
        if case_id == "DAILY_LOSS_LOCK":
            snapshot["day_start_equity"] = "103"
        else:
            snapshot["peak_equity"] = "106"
        simulation_module._risk(snapshot, source)
        expected = "STOP_NEW_RISK" if case_id == "DAILY_LOSS_LOCK" else "STAGE_FAILED_LOCKED"
        if snapshot["risk_state"] != expected:
            _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_INVALID")
    return _boundary(case_id)


class _ProbeResponse:
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self, _limit): return b"{}"
    def getcode(self): return 200
    def geturl(self): return "https://data-api.binance.vision/api/v3/time"
    headers = {"Content-Type": "application/json"}


class _ProbeOpener:
    def __init__(self, *, failure=False): self.failure = failure
    def open(self, *_args, **_kwargs):
        if self.failure:
            raise URLError("offline fault probe")
        return _ProbeResponse()


def _network_probe(case_id):
    url = "https://data-api.binance.vision/api/v3/time"
    moment = datetime(2026, 8, 26, tzinfo=timezone.utc)
    if case_id == "NETWORK_LOSS_BEFORE_REQUEST":
        with patch.object(http_module, "build_opener", side_effect=URLError("before dispatch")):
            try:
                http_module.open_fixed_public_request(Request(url), max_body_bytes=1024)
            except http_module.PublicHttpError:
                return _boundary(case_id)
    elif case_id == "NETWORK_LOSS_AFTER_REQUEST_BEFORE_RESPONSE":
        with patch.object(http_module, "build_opener", return_value=_ProbeOpener(failure=True)):
            try:
                http_module.open_fixed_public_request(Request(url), max_body_bytes=1024)
            except http_module.PublicHttpError:
                return _boundary(case_id)
    else:
        with patch.object(http_module, "build_opener", return_value=_ProbeOpener()), \
             patch.object(http_module, "_wall_now", side_effect=(moment, moment)), \
             patch.object(http_module, "_monotonic", side_effect=(1, 2)):
            response = http_module.open_fixed_public_request(
                Request(url), max_body_bytes=1024
            )
        attempt = http_module.attempt_document(response, 1)
        receipt_hash = hashlib.sha256(canonical_json(attempt).encode()).hexdigest()
        with tempfile.TemporaryDirectory(prefix="cq-v076-network-receipt-") as directory:
            os.chmod(directory, 0o700)
            entry = os.stat(directory, follow_symlinks=False)
            identity = ChallengerReplacementEventRootIdentity(
                os.path.realpath(directory), entry.st_dev, entry.st_ino,
                entry.st_uid, "0700")
            with open_challenger_replacement_event_root(identity) as root:
                event = _event_candidate(
                    root, {"receipt": receipt_hash}, 0, "0" * 64,
                    receipt_hash,
                )
                publish_challenger_replacement_event(root, event)
            with patch.object(
                http_module, "build_opener", return_value=_ProbeOpener(failure=True)
            ):
                try:
                    http_module.open_fixed_public_request(
                        Request(url), max_body_bytes=1024
                    )
                except http_module.PublicHttpError:
                    pass
                else:
                    _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")
            with open_challenger_replacement_event_root(identity) as root:
                replayed = replay_challenger_replacement_events(root)
                if (
                    len(replayed.events) == 1
                    and replayed.events[0].event_hash == event.event_hash
                    and attempt["outcome"] == "HTTP_RESPONSE"
                ):
                    return _boundary(case_id)
    _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")


def _attempt_entry(*, started, received):
    body = b"{}"
    kind, url, limit = capture_module._REQUESTS[0]
    return ({
        "request": {
            "request_id": stable_id("challenger_replacement_public_market_request", {
                "request_kind": kind, "method": "GET", "url": url,
                "max_body_bytes": limit,
            }),
            "request_kind": kind, "method": "GET", "url": url,
            "max_body_bytes": limit,
        },
        "attempts": [{
            "sequence": 1, "outcome": "HTTP_RESPONSE",
            "error_reason_or_null": None, "request_started_at": started,
            "response_received_at": received, "status": 200, "final_url": url,
            "selected_headers": {"content_type_or_null": "application/json",
                "http_date_or_null": None, "etag_or_null": None,
                "last_modified_or_null": None, "retry_after_or_null": None},
            "body_size_bytes": len(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
            "response_body_base64": "e30=",
        }],
        "selected_success_attempt_index": 0,
    }, capture_module._REQUESTS[0])


def _clock_probe(case_id):
    scheduled = datetime(2026, 8, 26, tzinfo=timezone.utc)
    captured = scheduled + timedelta(minutes=10)
    started, received = scheduled, scheduled + timedelta(seconds=1)
    if case_id == "CLOCK_OFFSET": started = scheduled - timedelta(milliseconds=1)
    elif case_id == "CLOCK_SPREAD": received = captured + timedelta(milliseconds=1)
    elif case_id == "WALL_CLOCK_BACKWARD": received = started - timedelta(milliseconds=1)
    entry, expected = _attempt_entry(
        started=started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        received=received.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    )
    try:
        capture_module._selected_payload(entry, expected, scheduled, captured)
        if case_id == "MONOTONIC_INCONSISTENCY":
            with patch.object(http_module, "build_opener", return_value=_ProbeOpener()), \
                 patch.object(http_module, "_wall_now", side_effect=(scheduled, scheduled)), \
                 patch.object(http_module, "_monotonic", side_effect=(2, 1)):
                http_module.open_fixed_public_request(
                    Request("https://data-api.binance.vision/api/v3/time"),
                    max_body_bytes=1024,
                )
    except (capture_module.ChallengerReplacementPublicMarketCaptureError,
            http_module.PublicHttpError):
        return _boundary(case_id)
    _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")


def _market_probe(case_id):
    samples = {
        "MALFORMED_MARKET_INPUT": b"{",
        "PARTIAL_MARKET_INPUT": b"{}",
        "REVISED_MARKET_INPUT": b'{"revision":"untrusted"}',
        "UNAVAILABLE_MARKET_INPUT": b"",
    }
    try:
        capture_module._strict_document(samples[case_id])
    except capture_module.ChallengerReplacementPublicMarketCaptureError:
        return _boundary(case_id)
    _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")


def _projection_probe(case_id):
    if case_id == "PROJECTION_SOURCE_UNAVAILABLE":
        value = observer_module.observe_challenger_replacement_v3()
        if value.evidence_health == "NOT_INSTALLED":
            return _boundary(case_id)
    else:
        try:
            projection_module.load_operations_projection_v3_bytes(b"{}")
        except projection_module.OperationsProjectionV3Error:
            return _boundary(case_id)
    _invalid("CHALLENGER_REPLACEMENT_FAULT_PROBE_DID_NOT_FAIL")


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
        return _network_probe(case_id)
    if case_id in {
        "PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL",
        "SIMULATED_CANCEL_RACE", "UNRESOLVED_UNKNOWN_CLASSIFICATION",
        "PROTECTIVE_STOP_MODEL_FAILURE", "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
        "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT",
    }:
        return _lifecycle_probe(case_id)
    if "CLOCK" in case_id or case_id == "MONOTONIC_INCONSISTENCY":
        return _clock_probe(case_id)
    if case_id.startswith("PROJECTION_SOURCE"):
        return _projection_probe(case_id)
    if case_id.endswith("MARKET_INPUT"):
        return _market_probe(case_id)
    if case_id in {"FEE_REPLAY", "FUNDING_REPLAY", "DAILY_LOSS_LOCK", "DRAWDOWN_LOCK"}:
        return _economic_probe(case_id)
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


def _document(build_identity: Mapping[str, Any], runtime_core_identity, *, exercise):
    try:
        validate_build_identity(build_identity)
        if (
            not isinstance(runtime_core_identity, Mapping)
            or not runtime_core_identity
            or any(
                not isinstance(path, str)
                or not (
                    path == _DEPLOYMENT_ARTIFACT
                    or path == "artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json"
                    or (path.startswith("src/crypto_quant/")
                        and path.endswith((".py", ".json")))
                )
                or not isinstance(digest, str)
                or len(digest) != 64
                or set(digest) - set("0123456789abcdef")
                for path, digest in runtime_core_identity.items()
            )
        ):
            _invalid()
        core = dict(sorted(runtime_core_identity.items()))
        executable = {key: value for key, value in core.items()
                      if key != _DEPLOYMENT_ARTIFACT}
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
            "runtime_core_identity": core,
            "runtime_core_hash": business_hash(core),
            "executable_core_hash": business_hash(executable),
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
    *, build_identity: Mapping[str, Any], runtime_core_identity: Mapping[str, str]
) -> Dict[str, Any]:
    return copy.deepcopy(_document(
        build_identity, runtime_core_identity, exercise=True
    ))


def load_challenger_replacement_fault_matrix_bytes(
    data: bytes, *, build_identity: Mapping[str, Any],
    runtime_core_identity: Mapping[str, str]
) -> Dict[str, Any]:
    if not isinstance(data, bytes) or not 0 < len(data) <= 1_048_576:
        _invalid("CHALLENGER_REPLACEMENT_FAULT_MATRIX_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        expected = _document(build_identity, runtime_core_identity, exercise=False)
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementFaultMatrixError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementFaultMatrixError(
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_BYTES_INVALID"
        ) from error
