"""Read-only classification for the isolated Nautilus supply-chain preflight."""

import copy
import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import stable_id
from .evidence import artifact_self_hash
from .nautilus_sandbox_dependency import (
    NautilusSandboxDependencyError,
    verify_nautilus_sandbox_dependency_lock,
)


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


def build_nautilus_supply_chain_fetch_attestation() -> Dict[str, Any]:
    """Describe the bounded session observation without claiming replayable proof."""

    attestation: Dict[str, Any] = {
        "attestation_id": "nautilus_supply_chain_fetch_attestation_" + _ZERO_HASH,
        "attestation_hash": _ZERO_HASH,
        "reason_code": "SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE",
        "official_source": "https://files.pythonhosted.org",
        "locked_package": "nautilus_trader==1.227.0",
        "observed_tool": "uv 0.11.7",
        "observed_python": "CPython 3.12.13",
        "attempt_count": 2,
        "attempts": [
            {
                "attempt": 1,
                "policy": "UV_FROZEN_DEFAULT_RETRY_POLICY",
                "observed_outcome": "UV_RETRIES_EXHAUSTED_TIMEOUT",
                "observed_exit_code": 1,
            },
            {
                "attempt": 2,
                "policy": "UV_FROZEN_SAME_SOURCE_EXTENDED_READ_TIMEOUT",
                "observed_outcome": "BOUNDED_RECOVERY_ABORTED_NO_PROGRESS",
                "observed_exit_code": 130,
            },
        ],
        "exact_transcript_bytes_available": False,
        "external_attestation_available": False,
        "machine_replayable": False,
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
        "status": "SESSION_ATTESTATION_NOT_MACHINE_REPLAYABLE",
    }
    identity = {
        key: value
        for key, value in attestation.items()
        if key not in {"attestation_id", "attestation_hash"}
    }
    attestation["attestation_id"] = stable_id(
        "nautilus_supply_chain_fetch_attestation", identity
    )
    attestation["attestation_hash"] = artifact_self_hash(
        attestation, "attestation_hash"
    )
    return attestation


def _comparison_identity(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in {"comparison_id", "comparison_hash"}
    }


def compare_nautilus_sandbox(
    *,
    dependency_lock: Mapping[str, Any],
    workspace_root: Path,
    failure_attestation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind the full lock and classify only the evidence actually obtained."""

    try:
        verified_lock = verify_nautilus_sandbox_dependency_lock(
            dependency_lock,
            workspace_root=Path(workspace_root),
            check_platform=False,
        )
    except (NautilusSandboxDependencyError, TypeError, ValueError) as exc:
        raise NautilusEvidenceAdapterError("DEPENDENCY_LOCK_EVIDENCE_INVALID") from exc
    expected_attestation = build_nautilus_supply_chain_fetch_attestation()
    if dict(failure_attestation) != expected_attestation:
        raise NautilusEvidenceAdapterError("SUPPLY_CHAIN_ATTESTATION_MISMATCH")

    comparison: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-comparison-v1.schema.json",
        "schema_version": "1.0.0",
        "comparison_id": "nautilus_sandbox_comparison_" + _ZERO_HASH,
        "comparison_hash": _ZERO_HASH,
        "authority": "READ_ONLY_EVIDENCE_ADAPTER",
        "dependency_lock_id": verified_lock["dependency_lock_id"],
        "dependency_lock_hash": verified_lock["dependency_lock_hash"],
        "classification": "SUPPLY_CHAIN_EVIDENCE_INCOMPLETE",
        "reason_codes": ["SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE"],
        "gates": {
            "exact_dependency_metadata": True,
            "wheel_locally_verified": False,
            "license_bytes_locally_verified": False,
            "compatibility_request_frozen": False,
            "sandbox_result_available": False,
            "golden_scenarios_executed": False,
            "runtime_failure_suite_executed": False,
            "static_blocked_path_tests_executed": True,
            "fresh_process_replay_verified": False,
            "future_shadow_eligible": False,
        },
        "supply_chain_fetch_attestation": copy.deepcopy(expected_attestation),
        "conclusion": "INCONCLUSIVE_BLOCKED",
        "current_core_effect": "NONE_KEEP_CURRENT_CORE",
        "status": "ADOPTION_REPORT_INCONCLUSIVE_NO_RETRY_V0_63",
    }
    comparison["comparison_id"] = stable_id(
        "nautilus_sandbox_comparison", _comparison_identity(comparison)
    )
    comparison["comparison_hash"] = artifact_self_hash(
        comparison, "comparison_hash"
    )
    errors = sorted(_validator().iter_errors(comparison), key=lambda error: list(error.path))
    if errors:
        raise NautilusEvidenceAdapterError("COMPARISON_SCHEMA_INVALID")
    return comparison
