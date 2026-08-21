"""Pure read-only comparison for the bounded v0.65 Nautilus spike."""

import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import canonical_json
from .nautilus_v065_contract import (
    NautilusV065ContractError,
    _self_hash,
    _verify_request,
    build_nautilus_v065_current_reference,
    verify_nautilus_v065_result,
)
from .nautilus_v065_plan import nautilus_v065_plan_hash
from .nautilus_v065_supply_chain import supply_chain_receipt_hash


_SCHEMA = "nautilus-sandbox-comparison-v2.schema.json"
_ZERO = "0" * 64
_ORDER = (
    "EXACT_MATCH",
    "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE",
    "ROUNDING_POLICY_DIFFERENCE",
    "FILL_MODEL_DIFFERENCE",
    "FEE_MODEL_DIFFERENCE",
    "POSITION_ACCOUNTING_DIFFERENCE",
    "PNL_ACCOUNTING_DIFFERENCE",
    "RESTART_SEMANTICS_DIFFERENCE",
    "UNSUPPORTED_INSTRUMENT_RULE",
    "SUPPLY_CHAIN_OR_LICENSE_FAILURE",
    "SAFETY_BOUNDARY_VIOLATION",
    "INVALID_OR_INCOMPLETE_EVIDENCE",
)
_FIELDS = (
    "status",
    "filled_quantity",
    "average_price",
    "fee_usdt",
    "ending_cash_usdt",
    "ending_position_eth",
    "realized_pnl_usdt",
    "unrealized_pnl_usdt",
    "net_pnl_usdt",
)
_SAFETY_KEYS = {
    "credential_reads", "network_requests", "live_adapter_imports", "broker_requests",
    "real_orders", "production_state_writes", "second_engine_creations",
}
_RUNNER_SAFETY_REASONS = {
    "NAUTILUS_V065_SAFETY_CREDENTIAL_ATTEMPT",
    "NAUTILUS_V065_SAFETY_NETWORK_ATTEMPT",
    "NAUTILUS_V065_SAFETY_SECOND_ENGINE_ATTEMPT",
}


class NautilusV065EvidenceError(ValueError):
    """The evidence comparison failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads(resources.files("crypto_quant").joinpath("schemas", _SCHEMA).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _comparison_hash(value: Mapping[str, Any]) -> str:
    material = copy.deepcopy(dict(value))
    material["comparison_id"] = "nautilus_v065_comparison_" + _ZERO
    material["comparison_hash"] = _ZERO
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _finish(value: Dict[str, Any]) -> Dict[str, Any]:
    digest = _comparison_hash(value)
    value["comparison_id"] = "nautilus_v065_comparison_" + digest
    value["comparison_hash"] = digest
    if tuple(_validator().iter_errors(value)):
        raise NautilusV065EvidenceError("NAUTILUS_V065_COMPARISON_SCHEMA_INVALID")
    return copy.deepcopy(value)


def verify_nautilus_v065_comparison(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay the strict schema and derived identity of a comparison artifact."""

    value = copy.deepcopy(dict(payload))
    try:
        digest = _comparison_hash(value)
        if (
            tuple(_validator().iter_errors(value))
            or value["comparison_hash"] != digest
            or value["comparison_id"] != "nautilus_v065_comparison_" + digest
        ):
            raise NautilusV065EvidenceError("NAUTILUS_V065_COMPARISON_INVALID")
    except NautilusV065EvidenceError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise NautilusV065EvidenceError("NAUTILUS_V065_COMPARISON_INVALID") from error
    return value


def _verify_plan(plan: Mapping[str, Any]) -> None:
    try:
        if (
            plan["status"] != "SPIKE_PLAN_PREREGISTERED_NOT_EXECUTED"
            or plan["plan_hash"] != nautilus_v065_plan_hash(plan)
            or tuple(plan["difference_classes"]) != _ORDER
            or any(plan["authority"].values())
        ):
            raise NautilusV065EvidenceError("NAUTILUS_V065_PLAN_INVALID")
    except (KeyError, TypeError, ValueError) as error:
        raise NautilusV065EvidenceError("NAUTILUS_V065_PLAN_INVALID") from error


def _verify_receipt(plan: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    try:
        digest = supply_chain_receipt_hash(receipt)
        if (
            receipt["status"] != "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY"
            or receipt["plan_id"] != plan["plan_id"]
            or receipt["plan_hash"] != plan["plan_hash"]
            or receipt["receipt_hash"] != digest
            or receipt["receipt_id"] != "nautilus_v065_supply_chain_" + digest
            or not receipt["slsa"]["verified"]
            or receipt["license"]["expression"] != "LGPL-3.0-or-later"
            or any(receipt["authority_counters"].values())
        ):
            raise NautilusV065EvidenceError("NAUTILUS_V065_RECEIPT_INVALID")
    except (KeyError, TypeError, ValueError) as error:
        raise NautilusV065EvidenceError("NAUTILUS_V065_RECEIPT_INVALID") from error


def _rehash_result(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["result_id"] = "nautilus_v065_result_" + _ZERO
    result["result_hash"] = _ZERO
    digest = _self_hash(result, "result_id", "result_hash")
    result["result_id"] = "nautilus_v065_result_" + digest
    result["result_hash"] = digest
    return result


def _verify_engine_result(value: Mapping[str, Any]) -> Tuple[Dict[str, Any], bool]:
    result = copy.deepcopy(dict(value))
    try:
        counters = result["safety_counters"]
        if set(counters) != _SAFETY_KEYS or any(not isinstance(item, int) or item < 0 for item in counters.values()):
            raise NautilusV065EvidenceError("NAUTILUS_V065_RESULT_SAFETY_INVALID")
        safe = not any(counters.values())
        if safe:
            verified = verify_nautilus_v065_result(result)
        else:
            digest = _self_hash(result, "result_id", "result_hash")
            if result["result_hash"] != digest or result["result_id"] != "nautilus_v065_result_" + digest:
                raise NautilusV065EvidenceError("NAUTILUS_V065_RESULT_HASH_INVALID")
            normalized = copy.deepcopy(result)
            normalized["safety_counters"] = {key: 0 for key in sorted(_SAFETY_KEYS)}
            verified_normalized = verify_nautilus_v065_result(_rehash_result(normalized))
            verified = result
            if verified_normalized["engine"] != result["engine"]:
                raise NautilusV065EvidenceError("NAUTILUS_V065_RESULT_INVALID")
        if verified["engine"] != "NAUTILUS_TRADER_1.230.0":
            raise NautilusV065EvidenceError("NAUTILUS_V065_ENGINE_IDENTITY_INVALID")
        return verified, safe
    except (KeyError, TypeError, NautilusV065ContractError) as error:
        raise NautilusV065EvidenceError("NAUTILUS_V065_RESULT_INVALID") from error


def _ordered(classes: List[str]) -> List[str]:
    present = set(classes)
    if len(present) > 1:
        present.discard("EXACT_MATCH")
    return [item for item in _ORDER if item in present]


def _same_decimal(left: str, right: str) -> bool:
    try:
        return Decimal(left) == Decimal(right)
    except (InvalidOperation, TypeError, ValueError):
        return False


def _field_class(field: str, current: str, candidate: str, tick: Decimal) -> str:
    if current == candidate:
        return "EXACT_MATCH"
    if field != "status" and _same_decimal(current, candidate):
        return "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE"
    if field == "status":
        return "UNSUPPORTED_INSTRUMENT_RULE"
    if field == "average_price":
        try:
            if abs(Decimal(current) - Decimal(candidate)) <= tick:
                return "ROUNDING_POLICY_DIFFERENCE"
        except (InvalidOperation, TypeError, ValueError):
            pass
        return "FILL_MODEL_DIFFERENCE"
    if field == "filled_quantity":
        return "FILL_MODEL_DIFFERENCE"
    if field == "fee_usdt":
        return "FEE_MODEL_DIFFERENCE"
    if field in ("ending_cash_usdt", "ending_position_eth"):
        return "POSITION_ACCOUNTING_DIFFERENCE"
    if field in ("realized_pnl_usdt", "unrealized_pnl_usdt", "net_pnl_usdt"):
        return "PNL_ACCOUNTING_DIFFERENCE"
    raise NautilusV065EvidenceError("NAUTILUS_V065_DIFFERENCE_UNCLASSIFIED")


def _scenario_comparison(current: Mapping[str, Any], candidate: Mapping[str, Any], tick: Decimal) -> Dict[str, Any]:
    if candidate.get("scenario") != current.get("scenario") or candidate.get("scenario_hash") != current.get("scenario_hash"):
        raise NautilusV065EvidenceError("NAUTILUS_V065_SCENARIO_BINDING_INVALID")
    differences = []
    classes = []
    for field in _FIELDS:
        left, right = current[field], candidate[field]
        classification = _field_class(field, left, right, tick)
        if classification != "EXACT_MATCH":
            classes.append(classification)
            differences.append({"field": field, "current_value": left, "candidate_value": right, "classification": classification})
    left_events = canonical_json([{key: value for key, value in item.items() if key != "event_hash"} for item in current["events"]])
    right_events = canonical_json([{key: value for key, value in item.items() if key != "event_hash"} for item in candidate["events"]])
    if left_events != right_events:
        classes.append("FILL_MODEL_DIFFERENCE")
        differences.append({
            "field": "events",
            "current_value": hashlib.sha256(left_events.encode()).hexdigest(),
            "candidate_value": hashlib.sha256(right_events.encode()).hexdigest(),
            "classification": "FILL_MODEL_DIFFERENCE",
        })
    ordered = _ordered(classes) or ["EXACT_MATCH"]
    return {
        "scenario": current["scenario"],
        "scenario_hash": current["scenario_hash"],
        "difference_classes": ordered,
        "differences": differences,
    }


def _bindings(
    plan: Mapping[str, Any],
    receipt: Optional[Mapping[str, Any]] = None,
    request: Optional[Mapping[str, Any]] = None,
    current: Optional[Mapping[str, Any]] = None,
    first: Optional[Mapping[str, Any]] = None,
    replay: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"],
        "receipt_id": None if receipt is None else receipt["receipt_id"],
        "receipt_hash": None if receipt is None else receipt["receipt_hash"],
        "request_id": None if request is None else request["request_id"],
        "request_hash": None if request is None else request["request_hash"],
        "current_reference_id": None if current is None else current["result_id"],
        "current_reference_hash": None if current is None else current["result_hash"],
        "first_result_id": None if first is None else first["result_id"],
        "first_result_hash": None if first is None else first["result_hash"],
        "replay_result_id": None if replay is None else replay["result_id"],
        "replay_result_hash": None if replay is None else replay["result_hash"],
    }


def compare_nautilus_v065(
    *,
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
    current_reference: Mapping[str, Any],
    first_result: Mapping[str, Any],
    replay_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Compare two frozen sandbox runs with the immutable current reference."""

    try:
        _verify_plan(plan)
        _verify_receipt(plan, receipt)
        verified_request = _verify_request(dict(request))
        if (
            verified_request["plan_id"] != plan["plan_id"]
            or verified_request["plan_hash"] != plan["plan_hash"]
            or verified_request["supply_chain_receipt_id"] != receipt["receipt_id"]
            or verified_request["supply_chain_receipt_hash"] != receipt["receipt_hash"]
        ):
            raise NautilusV065EvidenceError("NAUTILUS_V065_REQUEST_BINDING_INVALID")
        expected_current = build_nautilus_v065_current_reference(request=verified_request)
        if current_reference != expected_current:
            raise NautilusV065EvidenceError("NAUTILUS_V065_CURRENT_REFERENCE_CHANGED")
        first, first_safe = _verify_engine_result(first_result)
        replay, replay_safe = _verify_engine_result(replay_result)
        if any(item["request_id"] != verified_request["request_id"] or item["request_hash"] != verified_request["request_hash"] for item in (first, replay)):
            raise NautilusV065EvidenceError("NAUTILUS_V065_RESULT_BINDING_INVALID")
    except NautilusV065EvidenceError:
        raise
    except (KeyError, TypeError, ValueError, NautilusV065ContractError) as error:
        raise NautilusV065EvidenceError("NAUTILUS_V065_INVALID_OR_INCOMPLETE_EVIDENCE") from error

    gates = {
        "exact_supply_chain": True,
        "slsa_attestation": True,
        "license_verified": True,
        "golden_scenarios": True,
        "zero_safety_counters": first_safe and replay_safe,
        "fresh_process_replay": first == replay,
        "no_unresolved_economic_difference": False,
        "critical_important_review_zero": True,
    }
    scenarios: List[Dict[str, Any]] = []
    if not gates["zero_safety_counters"]:
        classes = ["SAFETY_BOUNDARY_VIOLATION"]
    elif not gates["fresh_process_replay"]:
        classes = ["RESTART_SEMANTICS_DIFFERENCE"]
    else:
        tick = Decimal(verified_request["instrument"]["price_tick"])
        scenarios = [
            _scenario_comparison(current, candidate, tick)
            for current, candidate in zip(expected_current["scenario_results"], first["scenario_results"])
        ]
        classes = _ordered([item for scenario in scenarios for item in scenario["difference_classes"]])
    allowed = {"EXACT_MATCH", "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE"}
    gates["no_unresolved_economic_difference"] = set(classes).issubset(allowed)
    adopt = all(gates.values())
    conclusion = "ADOPT_FOR_PREREGISTERED_SHADOW" if adopt else "REJECT_KEEP_CURRENT_CORE"
    comparison = {
        "$schema": "./nautilus-sandbox-comparison-v2.schema.json",
        "schema_version": "2.0.0",
        "comparison_id": "nautilus_v065_comparison_" + _ZERO,
        "comparison_hash": _ZERO,
        "mode": "ENGINE_COMPARISON",
        "bindings": _bindings(plan, receipt, verified_request, expected_current, first, replay),
        "scenario_comparisons": scenarios,
        "difference_classes": classes,
        "gates": gates,
        "conclusion": conclusion,
        "reason_code_or_null": None if adopt else "PREREGISTERED_DIFFERENCE_NOT_ADOPTABLE",
        "runner_invocation_count": 2,
        "current_core_effect": "UNCHANGED",
        "status": "FINAL_COMPARISON_ADOPT" if adopt else "FINAL_COMPARISON_REJECT",
    }
    return _finish(comparison)


def build_nautilus_v065_supply_failure_comparison(
    *,
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    reason_code: str,
    runner_invocation_count: int,
) -> Dict[str, Any]:
    """Record an acquisition failure without fabricating engine evidence."""

    _verify_plan(plan)
    try:
        digest = supply_chain_receipt_hash(receipt)
        valid_receipt = (
            receipt["status"] == "SUPPLY_CHAIN_ACQUISITION_FAILED"
            and receipt["plan_id"] == plan["plan_id"]
            and receipt["plan_hash"] == plan["plan_hash"]
            and receipt["receipt_hash"] == digest
            and receipt["receipt_id"] == "nautilus_v065_supply_chain_failure_" + digest
            and receipt["failure"]["reason_code"] == reason_code
            and not any(receipt["authority_counters"].values())
        )
    except (KeyError, TypeError, ValueError):
        valid_receipt = False
    if not valid_receipt or not isinstance(reason_code, str) or not reason_code or runner_invocation_count != 0:
        raise NautilusV065EvidenceError("NAUTILUS_V065_SUPPLY_FAILURE_INVALID")
    comparison = {
        "$schema": "./nautilus-sandbox-comparison-v2.schema.json",
        "schema_version": "2.0.0",
        "comparison_id": "nautilus_v065_comparison_" + _ZERO,
        "comparison_hash": _ZERO,
        "mode": "SUPPLY_CHAIN_FAILURE",
        "bindings": _bindings(plan, receipt),
        "scenario_comparisons": [],
        "difference_classes": ["SUPPLY_CHAIN_OR_LICENSE_FAILURE"],
        "gates": {
            "exact_supply_chain": False,
            "slsa_attestation": False,
            "license_verified": False,
            "golden_scenarios": False,
            "zero_safety_counters": True,
            "fresh_process_replay": False,
            "no_unresolved_economic_difference": False,
            "critical_important_review_zero": True,
        },
        "conclusion": "INCONCLUSIVE_KEEP_CURRENT_CORE",
        "reason_code_or_null": reason_code,
        "runner_invocation_count": 0,
        "current_core_effect": "UNCHANGED",
        "status": "FINAL_COMPARISON_INCONCLUSIVE",
    }
    return _finish(comparison)


def build_nautilus_v065_execution_failure_comparison(
    *,
    plan: Mapping[str, Any],
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
    reason_code: str,
    runner_invocation_count: int,
    first_result: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Freeze incomplete sandbox execution without selecting a replacement run."""

    _verify_plan(plan)
    _verify_receipt(plan, receipt)
    verified_request = _verify_request(dict(request))
    if (
        verified_request["plan_id"] != plan["plan_id"]
        or verified_request["supply_chain_receipt_id"] != receipt["receipt_id"]
        or not isinstance(reason_code, str)
        or not reason_code
        or runner_invocation_count not in (1, 2)
    ):
        raise NautilusV065EvidenceError("NAUTILUS_V065_EXECUTION_FAILURE_INVALID")
    verified_first = None
    if first_result is not None:
        verified_first, safe = _verify_engine_result(first_result)
        if not safe or runner_invocation_count != 2:
            raise NautilusV065EvidenceError("NAUTILUS_V065_EXECUTION_FAILURE_INVALID")
    safety_violation = reason_code in _RUNNER_SAFETY_REASONS
    comparison = {
        "$schema": "./nautilus-sandbox-comparison-v2.schema.json",
        "schema_version": "2.0.0",
        "comparison_id": "nautilus_v065_comparison_" + _ZERO,
        "comparison_hash": _ZERO,
        "mode": "EXECUTION_FAILURE",
        "bindings": _bindings(plan, receipt, verified_request, None, verified_first, None),
        "scenario_comparisons": [],
        "difference_classes": ["SAFETY_BOUNDARY_VIOLATION" if safety_violation else "INVALID_OR_INCOMPLETE_EVIDENCE"],
        "gates": {
            "exact_supply_chain": True,
            "slsa_attestation": True,
            "license_verified": True,
            "golden_scenarios": False,
            "zero_safety_counters": not safety_violation,
            "fresh_process_replay": False,
            "no_unresolved_economic_difference": False,
            "critical_important_review_zero": True,
        },
        "conclusion": "REJECT_KEEP_CURRENT_CORE" if safety_violation else "INCONCLUSIVE_KEEP_CURRENT_CORE",
        "reason_code_or_null": reason_code,
        "runner_invocation_count": runner_invocation_count,
        "current_core_effect": "UNCHANGED",
        "status": "FINAL_COMPARISON_REJECT" if safety_violation else "FINAL_COMPARISON_INCONCLUSIVE",
    }
    return _finish(comparison)
