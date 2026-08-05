"""One-way canonical contracts for the offline NautilusTrader sandbox."""

import copy
import json
import os
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .evidence import artifact_self_hash


_REQUEST_SCHEMA = "nautilus-sandbox-request-v1.schema.json"
_RESULT_SCHEMA = "nautilus-sandbox-result-v1.schema.json"
_MAX_BYTES = 2 * 1024 * 1024
_ZERO_HASH = "0" * 64


class NautilusSandboxContractError(ValueError):
    """The one-way sandbox contract failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=2)
def _validator(schema_name: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", schema_name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _expected_fixture() -> Dict[str, Any]:
    fixture: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "fixture_id": "nautilus_sandbox_fixture_ethusdt_4h_v1",
        "fixture_hash": _ZERO_HASH,
        "instrument": {
            "instrument_id": "ETHUSDT.BINANCE",
            "venue": "BINANCE",
            "market": "SPOT",
            "base_currency": "ETH",
            "quote_currency": "USDT",
            "interval": "4h",
            "price_precision": 2,
            "size_precision": 4,
            "tick_size": "0.01",
            "step_size": "0.0001",
            "minimum_quantity": "0.0001",
            "maximum_quantity": "9000",
            "minimum_notional": "10",
        },
        "starting_cash": "1000",
        "costs": {
            "taker_fee_rate": "0.0015",
            "maker_fee_rate": "0.001",
            "funding_rate": "0",
        },
        "bar": {
            "open_time": "2026-08-05T00:00:00.000Z",
            "close_time": "2026-08-05T04:00:00.000Z",
            "open": "1980.00",
            "high": "2010.00",
            "low": "1970.00",
            "close": "2000.00",
            "volume": "100.0000",
        },
        "scenarios": [
            {
                "scenario_id": "IMMEDIATE_FULL_FILL",
                "authorized_quantity": "0.0100",
                "quotes": [
                    {
                        "timestamp": "2026-08-05T04:00:00.000Z",
                        "bid_price": "1999.99",
                        "ask_price": "2000.00",
                        "bid_size": "1.0000",
                        "ask_size": "1.0000",
                    }
                ],
                "expected_terminal": "FILLED",
            },
            {
                "scenario_id": "PARTIAL_THEN_FULL_FILL",
                "authorized_quantity": "0.0200",
                "quotes": [
                    {
                        "timestamp": "2026-08-05T04:00:00.000Z",
                        "bid_price": "1999.99",
                        "ask_price": "2000.00",
                        "bid_size": "1.0000",
                        "ask_size": "0.0050",
                    },
                    {
                        "timestamp": "2026-08-05T04:00:01.000Z",
                        "bid_price": "2000.09",
                        "ask_price": "2000.10",
                        "bid_size": "1.0000",
                        "ask_size": "0.0150",
                    },
                ],
                "expected_terminal": "FILLED",
            },
            {
                "scenario_id": "BELOW_MINIMUM_REJECTION",
                "authorized_quantity": "0.0010",
                "quotes": [
                    {
                        "timestamp": "2026-08-05T04:00:00.000Z",
                        "bid_price": "1999.99",
                        "ask_price": "2000.00",
                        "bid_size": "1.0000",
                        "ask_size": "1.0000",
                    }
                ],
                "expected_terminal": "REJECTED_MIN_NOTIONAL",
            },
            {
                "scenario_id": "FRESH_PROCESS_REPLAY",
                "authorized_quantity": "0.0100",
                "quotes": [
                    {
                        "timestamp": "2026-08-05T04:00:00.000Z",
                        "bid_price": "1999.99",
                        "ask_price": "2000.00",
                        "bid_size": "1.0000",
                        "ask_size": "1.0000",
                    }
                ],
                "expected_terminal": "FILLED",
            },
        ],
        "authority": {
            "source": "COMMITTED_OFFLINE_FIXTURE",
            "live_data_allowed": False,
            "historical_download_allowed": False,
            "market_request_count": 0,
            "credential_access_count": 0,
            "production_state_write_count": 0,
        },
    }
    fixture["fixture_hash"] = artifact_self_hash(fixture, "fixture_hash")
    return fixture


def _verified_fixture(fixture: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(fixture, Mapping) or dict(fixture) != _expected_fixture():
        raise NautilusSandboxContractError("SANDBOX_FIXTURE_SEMANTIC_MISMATCH")
    return copy.deepcopy(dict(fixture))


def build_nautilus_current_reference(*, fixture: Mapping[str, Any]) -> Dict[str, Any]:
    """Build the current core's immutable Decision/Target/Risk fact source."""

    verified = _verified_fixture(fixture)
    reference: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "reference_id": "nautilus_current_reference_" + _ZERO_HASH,
        "reference_hash": _ZERO_HASH,
        "fixture_hash": verified["fixture_hash"],
        "authority": "CURRENT_CORE_FACT_SOURCE",
        "decision": {
            "decision_id": "decision_ethusdt_4h_enter_long_v1",
            "instrument_id": "ETHUSDT.BINANCE",
            "scheduled_for": "2026-08-05T04:00:00.000Z",
            "action": "ENTER_LONG",
            "strategy_policy_id": "FIXED_ETHUSDT_4H_COMPATIBILITY_V1",
        },
        "target": {
            "side": "BUY",
            "order_type": "MARKET",
            "time_in_force": "GTC",
            "position_mode": "NETTING",
            "cash_account": True,
        },
        "risk_authorization": {
            "maximum_notional": "40",
            "maximum_position": "0.02",
            "leverage": "1",
            "short_allowed": False,
            "override_allowed": False,
            "below_minimum_scenario_is_negative_test": True,
        },
        "scenario_authorizations": [
            {
                "scenario_id": scenario["scenario_id"],
                "authorized_quantity": scenario["authorized_quantity"],
                "expected_terminal": scenario["expected_terminal"],
            }
            for scenario in verified["scenarios"]
        ],
        "runtime_counters": {
            "network_request_count": 0,
            "credential_access_count": 0,
            "broker_request_count": 0,
            "real_order_count": 0,
            "production_state_write_count": 0,
        },
        "status": "CURRENT_REFERENCE_FROZEN_NO_RUNTIME_AUTHORITY",
    }
    reference["reference_id"] = stable_id(
        "nautilus_current_reference",
        {key: value for key, value in reference.items() if key not in {"reference_id", "reference_hash"}},
    )
    reference["reference_hash"] = artifact_self_hash(reference, "reference_hash")
    return reference


def _request_identity(request: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: value for key, value in request.items() if key not in {"request_id", "request_hash"}}


def build_nautilus_sandbox_request(
    *,
    dependency_lock: Mapping[str, Any],
    fixture: Mapping[str, Any],
    current_reference: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the sole directional request accepted by the isolated sidecar."""

    verified_fixture = _verified_fixture(fixture)
    expected_reference = build_nautilus_current_reference(fixture=verified_fixture)
    if dict(current_reference) != expected_reference:
        raise NautilusSandboxContractError("SANDBOX_REFERENCE_SEMANTIC_MISMATCH")
    lock_hash = dependency_lock.get("dependency_lock_hash")
    if not isinstance(lock_hash, str) or len(lock_hash) != 64:
        raise NautilusSandboxContractError("SANDBOX_DEPENDENCY_LOCK_INVALID")
    request: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-request-v1.schema.json",
        "schema_version": "1.0.0",
        "request_id": "nautilus_sandbox_request_" + _ZERO_HASH,
        "request_hash": _ZERO_HASH,
        "dependency_lock_hash": lock_hash,
        "fixture_hash": verified_fixture["fixture_hash"],
        "current_reference_hash": expected_reference["reference_hash"],
        "authority": "CURRENT_CORE_TO_SANDBOX_ONE_WAY",
        "engine_count": 1,
        "engine_api": "LOW_LEVEL_BACKTEST_ENGINE",
        "runtime_network_allowed": False,
        "live_adapter_allowed": False,
        "fixture": verified_fixture,
        "current_reference": expected_reference,
        "scenario_ids": [
            scenario["scenario_id"] for scenario in verified_fixture["scenarios"]
        ],
        "status": "SANDBOX_REQUEST_FROZEN_OFFLINE_ONLY",
    }
    request["request_id"] = stable_id("nautilus_sandbox_request", _request_identity(request))
    request["request_hash"] = artifact_self_hash(request, "request_hash")
    errors = sorted(_validator(_REQUEST_SCHEMA).iter_errors(request), key=lambda error: list(error.path))
    if errors:
        raise NautilusSandboxContractError("SANDBOX_REQUEST_SCHEMA_INVALID")
    return request


def _load_owner_canonical(path: Path) -> Dict[str, Any]:
    requested = Path(path)
    if not requested.is_absolute() or requested.is_symlink():
        raise NautilusSandboxContractError("SANDBOX_CONTRACT_UNSAFE_FILE")
    try:
        status = os.stat(requested, follow_symlinks=False)
    except OSError as exc:
        raise NautilusSandboxContractError("SANDBOX_CONTRACT_UNSAFE_FILE") from exc
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_nlink != 1
        or stat.S_IMODE(status.st_mode) & 0o077
        or status.st_size <= 0
        or status.st_size > _MAX_BYTES
    ):
        raise NautilusSandboxContractError("SANDBOX_CONTRACT_UNSAFE_FILE")
    raw = requested.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NautilusSandboxContractError("SANDBOX_CONTRACT_JSON_INVALID") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload).encode("utf-8"):
        raise NautilusSandboxContractError("SANDBOX_CONTRACT_NOT_CANONICAL")
    return payload


def load_nautilus_sandbox_request(path: Path) -> Dict[str, Any]:
    payload = _load_owner_canonical(path)
    errors = sorted(_validator(_REQUEST_SCHEMA).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise NautilusSandboxContractError("SANDBOX_REQUEST_SCHEMA_INVALID")
    if payload["request_hash"] != artifact_self_hash(payload, "request_hash"):
        raise NautilusSandboxContractError("SANDBOX_REQUEST_HASH_MISMATCH")
    if payload["request_id"] != stable_id("nautilus_sandbox_request", _request_identity(payload)):
        raise NautilusSandboxContractError("SANDBOX_REQUEST_ID_MISMATCH")
    expected = build_nautilus_sandbox_request(
        dependency_lock={"dependency_lock_hash": payload["dependency_lock_hash"]},
        fixture=payload["fixture"],
        current_reference=payload["current_reference"],
    )
    if payload != expected:
        raise NautilusSandboxContractError("SANDBOX_REQUEST_SEMANTIC_MISMATCH")
    return payload


def _result_identity(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: value for key, value in result.items() if key not in {"result_id", "result_hash"}}


def load_nautilus_sandbox_result(path: Path) -> Dict[str, Any]:
    payload = _load_owner_canonical(path)
    errors = sorted(_validator(_RESULT_SCHEMA).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise NautilusSandboxContractError("SANDBOX_RESULT_SCHEMA_INVALID")
    if payload["result_hash"] != artifact_self_hash(payload, "result_hash"):
        raise NautilusSandboxContractError("SANDBOX_RESULT_HASH_MISMATCH")
    if payload["result_id"] != stable_id("nautilus_sandbox_result", _result_identity(payload)):
        raise NautilusSandboxContractError("SANDBOX_RESULT_ID_MISMATCH")
    return payload
