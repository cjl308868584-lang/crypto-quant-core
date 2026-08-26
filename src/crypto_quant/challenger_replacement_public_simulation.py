"""Strict self-contained inputs for public-market deterministic simulation."""

import base64
import copy
import hashlib
import json
from functools import lru_cache
from importlib import resources
from typing import Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_public_market_capture import (
    ChallengerReplacementPublicMarketCapture,
    load_challenger_replacement_public_market_capture_bytes,
)
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .evidence import artifact_self_hash


_INPUT_SCHEMA = "challenger-replacement-public-simulation-input-v1.schema.json"
_MAX_INPUT_BYTES = 24 * 1024 * 1024
_MAX_SAFE_INTEGER = (1 << 53) - 1
_MAX_JSON_CONTAINER_DEPTH = 64


class ChallengerReplacementPublicSimulationError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="PUBLIC_SIMULATION_INPUT_INVALID"):
    raise ChallengerReplacementPublicSimulationError(reason)


def _strict_document(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_INPUT_BYTES:
        _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if not isinstance(key, str) or not key.isascii() or key in result:
                _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
            result[key] = value
        return result

    def reject_number(_value):
        _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")

    def parse_integer(value):
        parsed = int(value)
        if abs(parsed) > _MAX_SAFE_INTEGER:
            _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
        return parsed

    try:
        document = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_int=parse_integer,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except ChallengerReplacementPublicSimulationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ChallengerReplacementPublicSimulationError(
            "PUBLIC_SIMULATION_INPUT_BYTES_INVALID"
        ) from error
    if not isinstance(document, Mapping):
        _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
    pending = [(document, 1)]
    while pending:
        candidate, depth = pending.pop()
        if isinstance(candidate, (Mapping, list)):
            if depth > _MAX_JSON_CONTAINER_DEPTH:
                _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
            values = candidate.values() if isinstance(candidate, Mapping) else candidate
            pending.extend(
                (value, depth + 1)
                for value in values
                if isinstance(value, (Mapping, list))
            )
    return document


@lru_cache(maxsize=1)
def _input_validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _INPUT_SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _bindings(plan, economic_plan, predecessor_contract, public_contract):
    if (
        economic_plan != build_challenger_replacement_economic_plan()
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


def _document(
    capture, *, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    if not isinstance(capture, ChallengerReplacementPublicMarketCapture):
        _invalid()
    _bindings(plan, economic_plan, predecessor_contract, public_contract)
    capture_document = capture.document
    if capture_document["build_identity"] != dict(build_identity):
        _invalid()
    response_hashes = {}
    for ledger in capture_document["requests"]:
        selected = ledger["selected_success_attempt_index"]
        response_hashes[ledger["request"]["request_kind"]] = ledger["attempts"][
            selected
        ]["body_sha256"]
    document = {
        "$schema": "./" + _INPUT_SCHEMA,
        "schema_version": "1.0.0",
        "input_id": "",
        "input_hash": "0" * 64,
        "evidence_qualification": (
            "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
        ),
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "economic_plan": {
            "plan_id": economic_plan["plan_id"],
            "plan_hash": economic_plan["plan_hash"],
        },
        "predecessor_contract": {
            "contract_id": predecessor_contract["contract_id"],
            "contract_hash": predecessor_contract["contract_hash"],
        },
        "public_contract": {
            "contract_id": public_contract["contract_id"],
            "contract_hash": public_contract["contract_hash"],
        },
        "build_identity": copy.deepcopy(dict(build_identity)),
        "opportunity": copy.deepcopy(capture_document["opportunity"]),
        "capture": {
            "canonical_base64": base64.b64encode(capture.canonical_bytes).decode("ascii"),
            "sha256": hashlib.sha256(capture.canonical_bytes).hexdigest(),
            "capture_id": capture_document["capture_id"],
            "capture_hash": capture_document["capture_hash"],
            "nested_live_capture_hash": capture_document[
                "nested_live_capture"
            ]["capture_hash"],
        },
        "public_profile": copy.deepcopy(public_contract["public_profile"]),
        "normalized": copy.deepcopy(capture_document["normalized"]),
        "rule_response_hashes": response_hashes,
        "authority": {
            "public_network_requests": capture_document["authority"][
                "network_request_count"
            ],
            "account_requests": 0,
            "broker_requests": 0,
            "orders_submitted_to_venue": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        },
    }
    identity = {
        "plan": document["plan"],
        "economic_plan": document["economic_plan"],
        "public_contract": document["public_contract"],
        "build_identity": document["build_identity"],
        "opportunity": document["opportunity"],
        "capture_hash": document["capture"]["capture_hash"],
    }
    document["input_id"] = stable_id(
        "challenger_replacement_public_simulation_input", identity
    )
    document["input_hash"] = artifact_self_hash(document, "input_hash")
    if tuple(_input_validator().iter_errors(document)):
        _invalid()
    return document


def build_challenger_replacement_public_simulation_input(
    capture, *, plan, economic_plan, predecessor_contract,
    public_contract, build_identity
):
    return copy.deepcopy(_document(
        capture,
        plan=plan,
        economic_plan=economic_plan,
        predecessor_contract=predecessor_contract,
        public_contract=public_contract,
        build_identity=build_identity,
    ))


def load_challenger_replacement_public_simulation_input_bytes(
    data, *, plan, economic_plan, predecessor_contract,
    public_contract, build_identity, opportunity_id
):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_INPUT_BYTES:
        _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
    try:
        document = _strict_document(data)
        if data != canonical_json(document).encode("utf-8"):
            _invalid("PUBLIC_SIMULATION_INPUT_BYTES_INVALID")
        encoded = document["capture"]["canonical_base64"]
        capture_bytes = base64.b64decode(encoded, validate=True)
        if encoded != base64.b64encode(capture_bytes).decode("ascii"):
            _invalid()
        capture = load_challenger_replacement_public_market_capture_bytes(
            capture_bytes,
            plan=plan,
            build_identity=build_identity,
            previous_source_bundle=None,
        )
        expected = _document(
            capture,
            plan=plan,
            economic_plan=economic_plan,
            predecessor_contract=predecessor_contract,
            public_contract=public_contract,
            build_identity=build_identity,
        )
        if (
            document != expected
            or document["opportunity"]["opportunity_id"] != opportunity_id
            or document["input_hash"] != artifact_self_hash(document, "input_hash")
        ):
            _invalid()
        return copy.deepcopy(dict(document))
    except ChallengerReplacementPublicSimulationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPublicSimulationError(
            "PUBLIC_SIMULATION_INPUT_BYTES_INVALID"
        ) from error
