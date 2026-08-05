"""Read-only evidence comparison for the isolated Nautilus sandbox."""

import copy
import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping, Optional

from jsonschema import Draft202012Validator

from .canonical import stable_id
from .evidence import artifact_self_hash
from .nautilus_sandbox_contract import build_nautilus_current_reference


_SCHEMA = "nautilus-sandbox-comparison-v1.schema.json"
_ZERO_HASH = "0" * 64


class NautilusEvidenceAdapterError(ValueError):
    """Sandbox evidence could not be classified without ambiguity."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_nautilus_supply_chain_fetch_failure() -> Dict[str, Any]:
    """Return the exact bounded v0.63 official-source fetch failure evidence."""

    failure: Dict[str, Any] = {
        "failure_id": "nautilus_supply_chain_failure_" + _ZERO_HASH,
        "failure_hash": _ZERO_HASH,
        "reason_code": "SUPPLY_CHAIN_FETCH_BLOCKED",
        "official_source": "https://files.pythonhosted.org",
        "locked_package": "nautilus_trader==1.227.0",
        "attempt_count": 2,
        "attempts": [
            {
                "attempt": 1,
                "policy": "UV_FROZEN_DEFAULT_RETRY_POLICY",
                "outcome": "UV_RETRIES_EXHAUSTED_TIMEOUT",
                "blocked_distribution": "numpy==2.5.1",
                "exit_code": 1,
            },
            {
                "attempt": 2,
                "policy": "UV_FROZEN_SAME_SOURCE_EXTENDED_READ_TIMEOUT",
                "outcome": "BOUNDED_RECOVERY_ABORTED_NO_PROGRESS",
                "blocked_distribution": "FROZEN_ENVIRONMENT_INCOMPLETE",
                "exit_code": 130,
            },
        ],
        "source_change_count": 0,
        "version_change_count": 0,
        "hash_relaxation_count": 0,
        "sandbox_runner_invocation_count": 0,
        "sandbox_engine_creation_count": 0,
        "market_request_count": 0,
        "credential_access_count": 0,
        "broker_request_count": 0,
        "real_order_count": 0,
        "production_state_write_count": 0,
        "result_published": False,
        "retry_allowed_within_v0_63": False,
    }
    failure["failure_id"] = stable_id(
        "nautilus_supply_chain_failure",
        {key: value for key, value in failure.items() if key not in {"failure_id", "failure_hash"}},
    )
    failure["failure_hash"] = artifact_self_hash(failure, "failure_hash")
    return failure


def _comparison_identity(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return {key: item for key, item in value.items() if key not in {"comparison_id", "comparison_hash"}}


def compare_nautilus_sandbox(
    *,
    dependency_lock: Mapping[str, Any],
    fixture: Mapping[str, Any],
    current_reference: Mapping[str, Any],
    result: Optional[Mapping[str, Any]],
    failure_evidence: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Classify the exact observation without changing either fact source."""

    if result is not None and failure_evidence is not None:
        raise NautilusEvidenceAdapterError("SANDBOX_RESULT_AND_FAILURE_CONFLICT")
    if result is not None:
        raise NautilusEvidenceAdapterError("SANDBOX_RESULT_COMPARISON_NOT_AVAILABLE")
    expected_failure = build_nautilus_supply_chain_fetch_failure()
    if failure_evidence is None or dict(failure_evidence) != expected_failure:
        raise NautilusEvidenceAdapterError("SUPPLY_CHAIN_FAILURE_EVIDENCE_MISMATCH")
    expected_reference = build_nautilus_current_reference(fixture=fixture)
    if dict(current_reference) != expected_reference:
        raise NautilusEvidenceAdapterError("CURRENT_REFERENCE_MISMATCH")
    lock_hash = dependency_lock.get("dependency_lock_hash")
    fixture_hash = fixture.get("fixture_hash")
    reference_hash = current_reference.get("reference_hash")
    if not all(isinstance(value, str) and len(value) == 64 for value in (lock_hash, fixture_hash, reference_hash)):
        raise NautilusEvidenceAdapterError("COMPARISON_BINDING_INVALID")
    comparison: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-comparison-v1.schema.json",
        "schema_version": "1.0.0",
        "comparison_id": "nautilus_sandbox_comparison_" + _ZERO_HASH,
        "comparison_hash": _ZERO_HASH,
        "authority": "READ_ONLY_EVIDENCE_ADAPTER",
        "dependency_lock_hash": lock_hash,
        "fixture_hash": fixture_hash,
        "current_reference_hash": reference_hash,
        "failure_hash": expected_failure["failure_hash"],
        "sandbox_result_available": False,
        "sandbox_result_hash_or_null": None,
        "classification": "SUPPLY_CHAIN_OR_LICENSE_FAILURE",
        "reason_codes": ["SUPPLY_CHAIN_FETCH_BLOCKED"],
        "gates": {
            "exact_dependency_metadata": True,
            "wheel_locally_verified": False,
            "license_bytes_locally_verified": False,
            "golden_scenarios_executed": False,
            "failure_suite_executed": True,
            "fresh_process_replay_verified": False,
            "safety_zero_counters_verified": True,
            "future_shadow_eligible": False,
        },
        "failure_evidence": copy.deepcopy(expected_failure),
        "conclusion": "INCONCLUSIVE_BLOCKED",
        "current_core_effect": "NONE_KEEP_CURRENT_CORE",
        "status": "ADOPTION_REPORT_FINAL_NO_RETRY_V0_63",
    }
    comparison["comparison_id"] = stable_id(
        "nautilus_sandbox_comparison", _comparison_identity(comparison)
    )
    comparison["comparison_hash"] = artifact_self_hash(comparison, "comparison_hash")
    errors = sorted(_validator().iter_errors(comparison), key=lambda error: list(error.path))
    if errors:
        raise NautilusEvidenceAdapterError("COMPARISON_SCHEMA_INVALID")
    return comparison
