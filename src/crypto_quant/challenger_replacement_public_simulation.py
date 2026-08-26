"""Strict self-contained inputs for public-market deterministic simulation."""

import base64
import copy
import hashlib
import json
from datetime import datetime
from decimal import Decimal
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
from .instruments import InstrumentMetadata, MarketType
from .challenger_replacement_simulation import (
    _PUBLIC_PROFILE,
    _simulate_with_stops_impl,
    build_challenger_replacement_genesis_snapshot,
)


_INPUT_SCHEMA = "challenger-replacement-public-simulation-input-v1.schema.json"
_RESULT_SCHEMA = "challenger-replacement-public-simulation-result-v1.schema.json"
_SNAPSHOT_SCHEMA = "challenger-replacement-public-simulation-snapshot-v1.schema.json"
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


@lru_cache(maxsize=1)
def _result_validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _RESULT_SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@lru_cache(maxsize=1)
def _snapshot_validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SNAPSHOT_SCHEMA
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


def _validated_source(
    source, *, plan, public_contract, build_identity
):
    economic_plan = build_challenger_replacement_economic_plan()
    predecessor = build_challenger_replacement_simulation_contract(plan=plan)
    return load_challenger_replacement_public_simulation_input_bytes(
        canonical_json(source).encode("utf-8"),
        plan=plan,
        economic_plan=economic_plan,
        predecessor_contract=predecessor,
        public_contract=public_contract,
        build_identity=build_identity,
        opportunity_id=source["opportunity"]["opportunity_id"],
    )


def _instrument_record(product, rules, model, effective_from):
    market = MarketType.SPOT if product == "spot" else MarketType.USDT_PERP
    metadata = InstrumentMetadata(
        schema_version="1.1.0",
        instrument_id=f"BINANCE:{market.value}:ETHUSDT",
        exchange="BINANCE",
        market_type=market,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        settlement_asset="USDT",
        effective_from=datetime.fromisoformat(effective_from.replace("Z", "+00:00")),
        effective_to_or_null=None,
        price_tick=Decimal(rules["price_tick"]),
        quantity_step=Decimal(rules["quantity_step"]),
        min_quantity=Decimal(rules["min_quantity"]),
        max_quantity=Decimal(rules["max_quantity"]),
        min_notional=Decimal(rules["min_notional"]),
        contract_multiplier=Decimal(
            rules.get("contract_multiplier", model["contract_multiplier"])
        ),
        supported_order_types=("MARKET", "STOP_MARKET"),
        supported_time_in_force=("GTC", "IOC"),
        supports_reduce_only=product == "perpetual",
        supports_stop_market=True,
        maker_fee=Decimal(model[f"{product}_taker_fee"]),
        taker_fee=Decimal(model[f"{product}_taker_fee"]),
        metadata_source="PUBLIC_MARKET_CAPTURE_V2_RULES",
    )
    return {
        "metadata": json.loads(canonical_json(metadata.business_payload())),
        "metadata_hash": metadata.metadata_hash,
    }


def _kernel_source(source, plan, public_contract):
    normalized = source["normalized"]
    effective_from = normalized["bars"][0]["open_time"]
    model = public_contract["model"]
    return {
        "input_hash": source["input_hash"],
        "plan": source["plan"],
        "simulation_contract": source["predecessor_contract"],
        "build_identity": copy.deepcopy(source["build_identity"]),
        "opportunity": copy.deepcopy(source["opportunity"]),
        "bars": copy.deepcopy(normalized["bars"]),
        "quotes": copy.deepcopy(normalized["quotes"]),
        "instruments": {
            product: _instrument_record(
                product,
                normalized["simulation_rules"][product],
                model,
                effective_from,
            )
            for product in ("spot", "perpetual")
        },
        "funding": {"boundary_at_or_null": None, "rate_or_null": None},
        "funding_records": copy.deepcopy(normalized["funding_records"]),
    }


def build_challenger_replacement_public_genesis_snapshot(
    *, plan, public_contract
):
    predecessor = build_challenger_replacement_simulation_contract(plan=plan)
    if public_contract != build_challenger_replacement_public_simulation_contract(
        plan=plan,
        economic_plan=build_challenger_replacement_economic_plan(),
        predecessor_contract=predecessor,
    ):
        _invalid()
    snapshot = build_challenger_replacement_genesis_snapshot(
        plan=plan, contract=predecessor
    )
    if tuple(_snapshot_validator().iter_errors(snapshot)):
        _invalid("PUBLIC_SIMULATION_SNAPSHOT_INVALID")
    return snapshot


def simulate_challenger_replacement_public_opportunity(
    *, source, previous_projection, plan, public_contract, build_identity
):
    try:
        source = _validated_source(
            source,
            plan=plan,
            public_contract=public_contract,
            build_identity=build_identity,
        )
        predecessor = build_challenger_replacement_simulation_contract(plan=plan)
        transition = _simulate_with_stops_impl(
            source=_kernel_source(source, plan, public_contract),
            previous_projection=previous_projection,
            plan=plan,
            contract=predecessor,
            build_identity=build_identity,
            profile=_PUBLIC_PROFILE,
            source_is_validated=True,
        )
        if tuple(_snapshot_validator().iter_errors(transition["next_snapshot"])):
            _invalid("PUBLIC_SIMULATION_SNAPSHOT_INVALID")
        return copy.deepcopy(transition)
    except ChallengerReplacementPublicSimulationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPublicSimulationError(
            "PUBLIC_SIMULATION_TRANSITION_INVALID"
        ) from error


def _result_document(
    *, source, previous_projection, transition, plan, economic_plan,
    public_contract, build_identity, sequence, parent_event_hash
):
    if (
        economic_plan != build_challenger_replacement_economic_plan()
        or not isinstance(sequence, int)
        or isinstance(sequence, bool)
        or sequence < 1
        or sequence > _MAX_SAFE_INTEGER
        or not isinstance(parent_event_hash, str)
        or len(parent_event_hash) != 64
        or any(char not in "0123456789abcdef" for char in parent_event_hash)
    ):
        _invalid("PUBLIC_SIMULATION_RESULT_INVALID")
    expected_transition = simulate_challenger_replacement_public_opportunity(
        source=source,
        previous_projection=previous_projection,
        plan=plan,
        public_contract=public_contract,
        build_identity=build_identity,
    )
    if transition != expected_transition:
        _invalid("PUBLIC_SIMULATION_RESULT_INVALID")
    filled = (
        transition["accounting"]["fill_price"] is not None
        and transition["accounting"]["quantity"] != "0"
    )
    events = (
        ["SIMULATED_ORDER_ACCEPTED", "SIMULATED_FILL_APPLIED"]
        if filled else []
    )
    document = {
        "$schema": "./" + _RESULT_SCHEMA,
        "schema_version": "1.0.0",
        "result_id": "",
        "result_hash": "0" * 64,
        "evidence_qualification": (
            "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
        ),
        "plan": copy.deepcopy(source["plan"]),
        "economic_plan": copy.deepcopy(source["economic_plan"]),
        "public_contract": copy.deepcopy(source["public_contract"]),
        "build_identity": copy.deepcopy(dict(build_identity)),
        "opportunity": copy.deepcopy(source["opportunity"]),
        "sequence": sequence,
        "parent_event_hash": parent_event_hash,
        "source": {
            "input_id": source["input_id"],
            "input_hash": source["input_hash"],
            "capture_hash": source["capture"]["capture_hash"],
            "nested_live_capture_hash": source["capture"][
                "nested_live_capture_hash"
            ],
        },
        "previous_snapshot_hash": previous_projection["snapshot_hash"],
        "decision": copy.deepcopy(transition["decision"]),
        "accounting": copy.deepcopy(transition["accounting"]),
        "next_snapshot": copy.deepcopy(transition["next_snapshot"]),
        "lifecycle": {"events": events, "unresolved_unknown": False},
        "reconciliation": {"status": "MATCHED", "difference_count": 0},
        "authority": {
            "public_network_requests": source["authority"]["public_network_requests"],
            "account_requests": 0,
            "broker_requests": 0,
            "orders_submitted_to_venue": 0,
            "credentials_used": False,
            "production_state_writes": 0,
        },
    }
    identity = {
        "plan": document["plan"],
        "public_contract": document["public_contract"],
        "build_identity": document["build_identity"],
        "opportunity": document["opportunity"],
        "sequence": sequence,
        "parent_event_hash": parent_event_hash,
        "input_hash": document["source"]["input_hash"],
        "previous_snapshot_hash": document["previous_snapshot_hash"],
    }
    document["result_id"] = stable_id(
        "challenger_replacement_public_simulation_result", identity
    )
    document["result_hash"] = artifact_self_hash(document, "result_hash")
    if tuple(_result_validator().iter_errors(document)):
        _invalid("PUBLIC_SIMULATION_RESULT_INVALID")
    return document


def build_challenger_replacement_public_simulation_result(
    *, source, previous_projection, transition, plan, economic_plan,
    public_contract, build_identity, sequence, parent_event_hash
):
    return copy.deepcopy(_result_document(
        source=source,
        previous_projection=previous_projection,
        transition=transition,
        plan=plan,
        economic_plan=economic_plan,
        public_contract=public_contract,
        build_identity=build_identity,
        sequence=sequence,
        parent_event_hash=parent_event_hash,
    ))


def load_challenger_replacement_public_simulation_result_bytes(
    data, *, source, previous_projection, plan, economic_plan,
    public_contract, build_identity, sequence, parent_event_hash
):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_INPUT_BYTES:
        _invalid("PUBLIC_SIMULATION_RESULT_BYTES_INVALID")
    try:
        document = _strict_document(data)
        if data != canonical_json(document).encode("utf-8"):
            _invalid("PUBLIC_SIMULATION_RESULT_BYTES_INVALID")
        transition = simulate_challenger_replacement_public_opportunity(
            source=source,
            previous_projection=previous_projection,
            plan=plan,
            public_contract=public_contract,
            build_identity=build_identity,
        )
        expected = _result_document(
            source=source,
            previous_projection=previous_projection,
            transition=transition,
            plan=plan,
            economic_plan=economic_plan,
            public_contract=public_contract,
            build_identity=build_identity,
            sequence=sequence,
            parent_event_hash=parent_event_hash,
        )
        if document != expected:
            _invalid("PUBLIC_SIMULATION_RESULT_INVALID")
        return copy.deepcopy(document)
    except ChallengerReplacementPublicSimulationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPublicSimulationError(
            "PUBLIC_SIMULATION_RESULT_BYTES_INVALID"
        ) from error
