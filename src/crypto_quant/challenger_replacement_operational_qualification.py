"""Pure 72-hour continuous public-simulation qualification state machine."""

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_fault_matrix import (
    load_challenger_replacement_fault_matrix_bytes,
)
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-operational-qualification-v1.schema.json"
_PUBLIC = (
    "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER"
)
_HARD_STOPS = {
    "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN", "VENUE_LOCAL_POSITION_MISMATCH",
    "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
    "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
}


class ChallengerReplacementOperationalQualificationError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_OPERATIONAL_QUALIFICATION_INVALID"):
    raise ChallengerReplacementOperationalQualificationError(reason)


@dataclass(frozen=True)
class OperationalQualificationFacts:
    start_receipt: Mapping[str, Any]
    terminal_opportunities: Tuple[Mapping[str, Any], ...]
    observed_at: str
    position_state: str
    reconciliation_status: str
    hard_stop_reason_codes: Tuple[str, ...]


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ChallengerReplacementOperationalQualificationError(
            "CHALLENGER_REPLACEMENT_OPERATIONAL_QUALIFICATION_INVALID"
        ) from error
    if parsed.utcoffset() is None:
        _invalid()
    return parsed


def _validated_inputs(facts, plan, fault):
    if not isinstance(facts, OperationalQualificationFacts):
        _invalid()
    expected_plan = build_challenger_replacement_accelerated_canary_plan()
    if plan != expected_plan:
        _invalid("CHALLENGER_REPLACEMENT_OPERATIONAL_POLICY_MISMATCH")
    try:
        load_challenger_replacement_fault_matrix_bytes(
            canonical_json(fault).encode("utf-8"),
            build_identity=fault["build_identity"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementOperationalQualificationError(
            "CHALLENGER_REPLACEMENT_FAULT_MATRIX_NOT_PASSED"
        ) from error
    if fault.get("status") != "FAULT_MATRIX_PASSED":
        _invalid("CHALLENGER_REPLACEMENT_FAULT_MATRIX_NOT_PASSED")
    return expected_plan


def _evaluate(facts, plan, fault):
    _validated_inputs(facts, plan, fault)
    if not facts.start_receipt:
        return "NOT_STARTED", 0, ("START_RECEIPT_ABSENT",), None
    try:
        start = _time(facts.start_receipt["operational_start"]["observed_at"])
        if facts.start_receipt["status"] != (
            "V3_FIRST_NATURAL_OBSERVED_BOUND_NOT_ACTIVATED"
        ):
            _invalid()
        observed = _time(facts.observed_at)
    except (KeyError, TypeError):
        _invalid()
    if observed < start:
        _invalid()
    if (
        not isinstance(facts.position_state, str)
        or not isinstance(facts.reconciliation_status, str)
        or not isinstance(facts.terminal_opportunities, tuple)
        or not isinstance(facts.hard_stop_reason_codes, tuple)
        or any(reason not in _HARD_STOPS for reason in facts.hard_stop_reason_codes)
    ):
        _invalid()
    reasons = list(facts.hard_stop_reason_codes)
    if facts.reconciliation_status != "MATCHED":
        reasons.append("VENUE_LOCAL_POSITION_MISMATCH")
    active_start = start
    final_segment = None
    incomplete = False
    interrupted = False
    previous_time = None
    cadence = plan["simulation_qualification"]["cadence_seconds"]
    next_due = start
    for item in facts.terminal_opportunities:
        required = {
            "opportunity_id", "scheduled_for", "observed_at", "segment_id",
            "outcome", "evidence_qualification", "clock_status",
            "simulated_stop_status", "terminal_coverage_complete",
        }
        if not isinstance(item, Mapping) or set(item) != required:
            _invalid()
        at = _time(item["observed_at"])
        scheduled = _time(item["scheduled_for"])
        if at < start or (previous_time is not None and at < previous_time):
            _invalid()
        previous_time = at
        if scheduled != next_due:
            incomplete = True
            interrupted = True
        next_due = scheduled + timedelta(seconds=cadence)
        if item["evidence_qualification"] != _PUBLIC:
            reasons.append("UNTRUSTED_EVIDENCE_QUALIFICATION")
        if item["clock_status"] != "HEALTHY_ALIGNED":
            reasons.append("UNTRUSTED_CLOCK")
        if not item["terminal_coverage_complete"]:
            incomplete = True
        if item["outcome"] == "MISSED":
            active_start = None
            final_segment = None
            incomplete = True
            interrupted = True
            continue
        if item["outcome"] != "OBSERVED":
            _invalid()
        if active_start is None or final_segment != item["segment_id"]:
            if final_segment is not None:
                interrupted = True
            active_start = at
        final_segment = item["segment_id"]
        if (
            facts.position_state != "FLAT"
            and item["simulated_stop_status"]
            != "SIMULATED_PROTECTIVE_STOP_ACTIVE"
        ):
            reasons.append("PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP")
    if any(reason in _HARD_STOPS or reason.startswith("UNTRUSTED_") for reason in reasons):
        return "BLOCK_FAILED", 0, tuple(sorted(set(reasons))), final_segment
    if next_due <= observed:
        incomplete = True
        interrupted = True
    elapsed = 0 if active_start is None else max(
        0, int((observed - active_start).total_seconds())
    )
    if incomplete:
        reasons.append("FLAT_MISSED_OPPORTUNITY" if any(
            item["outcome"] == "MISSED" for item in facts.terminal_opportunities
        ) else "TERMINAL_COVERAGE_INCOMPLETE")
        return "INTERRUPTED_RECOVERABLE", elapsed, tuple(sorted(set(reasons))), final_segment
    required_seconds = plan["simulation_qualification"][
        "minimum_continuous_seconds"
    ]
    if interrupted and elapsed < required_seconds:
        reasons.append("SAFE_DISCONNECTION")
    return (
        "QUALIFIED" if elapsed >= required_seconds else (
            "INTERRUPTED_RECOVERABLE" if interrupted else "ACTIVE"
        ),
        elapsed, tuple(sorted(set(reasons))), final_segment,
    )


def _document(facts, plan, fault):
    status, elapsed, reasons, segment = _evaluate(facts, plan, fault)
    fact_value = {
        "start_receipt": copy.deepcopy(dict(facts.start_receipt)),
        "terminal_opportunities": [
            copy.deepcopy(dict(item)) for item in facts.terminal_opportunities
        ],
        "observed_at": facts.observed_at,
        "position_state": facts.position_state,
        "reconciliation_status": facts.reconciliation_status,
        "hard_stop_reason_codes": list(facts.hard_stop_reason_codes),
    }
    value = {
        "$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "result_id": "", "result_hash": "0" * 64,
        "status": status, "eligible_continuous_seconds": elapsed,
        "final_segment_id_or_null": segment,
        "reason_codes": list(reasons),
        "bindings": {
            "accelerated_plan_id": plan["plan_id"],
            "accelerated_plan_hash": plan["plan_hash"],
            "fault_receipt_id": fault["receipt_id"],
            "fault_receipt_hash": fault["receipt_hash"],
            "facts_hash": business_hash(fact_value),
            "start_receipt_id_or_null": facts.start_receipt.get("receipt_id"),
            "start_receipt_hash_or_null": facts.start_receipt.get("receipt_hash"),
        },
        "authority": {"production_activation": False, "orders": 0,
                      "fund_movement": 0, "production_state_writes": 0},
    }
    identity = {key: item for key, item in value.items() if key not in {
        "$schema", "schema_version", "result_id", "result_hash"
    }}
    value["result_id"] = stable_id(
        "challenger_replacement_operational_qualification", identity
    )
    value["result_hash"] = artifact_self_hash(value, "result_hash")
    if tuple(_validator().iter_errors(value)):
        _invalid()
    return value


def evaluate_challenger_replacement_operational_qualification(
    facts: OperationalQualificationFacts, *, accelerated_plan: Mapping[str, Any],
    fault_receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    return copy.deepcopy(_document(facts, accelerated_plan, fault_receipt))


def load_challenger_replacement_operational_qualification_bytes(
    data: bytes, *, facts: OperationalQualificationFacts,
    accelerated_plan: Mapping[str, Any], fault_receipt: Mapping[str, Any]
) -> Dict[str, Any]:
    if not isinstance(data, bytes) or not 0 < len(data) <= 262_144:
        _invalid("CHALLENGER_REPLACEMENT_OPERATIONAL_QUALIFICATION_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        expected = _document(facts, accelerated_plan, fault_receipt)
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementOperationalQualificationError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementOperationalQualificationError(
            "CHALLENGER_REPLACEMENT_OPERATIONAL_QUALIFICATION_BYTES_INVALID"
        ) from error
