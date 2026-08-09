"""Superseding preregistration for replacement Challenger storage safety.

Building or loading this plan grants no runtime authority and performs no
production-path inspection, network request, process invocation, or state write.
"""

import copy
import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _read_owner_controlled_regular_file,
    _strict_json_bytes,
    load_challenger_replacement_plan,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-plan-v2.schema.json"
_ZERO_HASH = "0" * 64
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_V1_PLAN_PATH = (
    _REPOSITORY_ROOT
    / "artifacts"
    / "challenger-replacement"
    / "challenger-replacement-plan-v0.62.0.json"
)

_V2_FOUNDATION = {
    "release_tag": "v0.63.0",
    "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
    "package_version": "0.63.0",
    "manifest_version": "1.57.0",
    "build_input_tree_hash": "7fdfd6c69f1342892b222882b76ee4988487a482c958a9cdacf00461b2fd8f19",
    "manifest_hash": "f4a74896a6d7b2166adba86075ef06b8d7986f900a086d04ee2f03754baded4b",
    "manifest_file_sha256": "13bea4bfcf633e767eed73d431e57d496dcee47820aacf92e7b61b0efed5c546",
}

_RELATIVE_PATHS = {
    "state_events": "state/challenger-replacement-events-v1",
    "non_authoritative_exports": "exports",
    "stdout": "log/challenger-replacement.stdout.log",
    "stderr": "log/challenger-replacement.stderr.log",
    "deployment_contract": "deployment/contract.json",
    "deployment_plist": "deployment/local.crypto-quant.challenger-replacement-v1.plist",
    "preflight_receipts": "preflight-receipts",
    "install_receipts": "install-receipts",
    "start_receipts": "start-receipts",
    "episode_receipts": "episode-receipts",
    "archives": "archives",
    "results": "results",
    "indexes": "indexes",
    "evaluations": "evaluations",
}

_STORAGE_AUTHORITY = {
    "authoritative_state_kind": "APPEND_ONLY_CANONICAL_EVENT_LOG",
    "authoritative_relative_path": "state/challenger-replacement-events-v1",
    "runner_authority_source": "CANONICAL_EVENT_LOG_ONLY",
    "observer_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "evaluator_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
    "exports_authoritative": False,
    "exports_required_for_slot_success": False,
    "exports_required_for_evaluation": False,
    "exports_reconstructible": True,
    "source_bundle_export_subdirectory": "source-bundles",
    "decision_export_subdirectory": "decisions",
}

_SUPERSESSION = {
    "previous_plan_release_tag": "v0.62.0",
    "previous_plan_peeled_commit": "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a",
    "previous_plan_path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.62.0.json"
    ),
    "previous_plan_file_sha256": "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734",
    "previous_plan_id": "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2",
    "previous_plan_hash": "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c",
    "reason": "SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
    "previous_plan_state": "PLAN_FROZEN_REPLACEMENT_NOT_STARTED",
    "previous_plan_disposition": "SUPERSEDED_BEFORE_START_NO_COHORT_EVIDENCE",
    "supersession_forbidden_after": "FIRST_START_RECEIPT_OR_CANONICAL_EVENT",
}

_WARNING = "V0_62_SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION"


class ChallengerReplacementPlanV2Error(ValueError):
    """The replacement Challenger v2 plan failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _with_policy_hash(policy: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(policy)
    result["policy_hash"] = business_hash(policy)
    return result


def challenger_replacement_plan_v2_hash(plan: Mapping[str, Any]) -> str:
    """Hash the v2 plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    supersession = plan["supersession"]
    return {
        "previous_plan_file_sha256": supersession["previous_plan_file_sha256"],
        "previous_plan_id": supersession["previous_plan_id"],
        "previous_plan_hash": supersession["previous_plan_hash"],
        "previous_plan_peeled_commit": supersession[
            "previous_plan_peeled_commit"
        ],
        "foundation": plan["foundation"],
        "scope_policy_hash": plan["scope"]["policy_hash"],
        "decision_policy_hash": plan["decision_policy"]["policy_hash"],
        "cohort_policy_hash": plan["cohort_policy"]["policy_hash"],
        "isolation_policy_hash": plan["isolation_policy"]["policy_hash"],
        "evidence_policy_hash": plan["evidence_policy"]["policy_hash"],
        "storage_authority_policy_hash": plan["storage_authority"][
            "policy_hash"
        ],
    }


def build_challenger_replacement_plan_v2() -> Dict[str, Any]:
    """Build the sole superseding v2 plan without runtime side effects."""

    previous = load_challenger_replacement_plan(_V1_PLAN_PATH)
    isolation = copy.deepcopy(previous["isolation_policy"])
    isolation["relative_paths"] = copy.deepcopy(_RELATIVE_PATHS)
    isolation.pop("policy_hash")
    isolation = _with_policy_hash(isolation)
    storage_authority = _with_policy_hash(_STORAGE_AUTHORITY)

    plan: Dict[str, Any] = {
        "$schema": "./challenger-replacement-plan-v2.schema.json",
        "schema_version": "2.0.0",
        "plan_id": "challenger_replacement_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "foundation": copy.deepcopy(_V2_FOUNDATION),
        "predecessor": copy.deepcopy(previous["predecessor"]),
        "scope": copy.deepcopy(previous["scope"]),
        "decision_policy": copy.deepcopy(previous["decision_policy"]),
        "cohort_policy": copy.deepcopy(previous["cohort_policy"]),
        "isolation_policy": isolation,
        "evidence_policy": copy.deepcopy(previous["evidence_policy"]),
        "storage_authority": storage_authority,
        "supersession": copy.deepcopy(_SUPERSESSION),
        "authority": copy.deepcopy(previous["authority"]),
        "status": "PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED",
        "eligibility": copy.deepcopy(previous["eligibility"]),
        "warnings": list(previous["warnings"]) + [_WARNING],
    }
    plan["plan_id"] = stable_id("challenger_replacement_plan", _identity(plan))
    plan["plan_hash"] = challenger_replacement_plan_v2_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerReplacementPlanV2Error(
            "CHALLENGER_REPLACEMENT_PLAN_V2_SCHEMA_INVALID"
        )
    return copy.deepcopy(plan)


def challenger_replacement_plan_v2_reasons(
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return deterministic fail-closed reason codes for v2 semantics."""

    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V2_SCHEMA_INVALID")
        if plan.get("plan_hash") != challenger_replacement_plan_v2_hash(plan):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V2_HASH_MISMATCH")
        for section_name in (
            "scope",
            "decision_policy",
            "cohort_policy",
            "isolation_policy",
            "evidence_policy",
            "storage_authority",
        ):
            section = dict(plan[section_name])
            claimed = section.pop("policy_hash")
            if claimed != business_hash(section):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_PLAN_V2_POLICY_HASH_MISMATCH"
                )
        if plan.get("plan_id") != stable_id(
            "challenger_replacement_plan", _identity(plan)
        ):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V2_ID_MISMATCH")
        if business_hash(plan) != business_hash(
            build_challenger_replacement_plan_v2()
        ):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V2_SEMANTIC_MISMATCH")
    except (
        CanonicalizationError,
        ChallengerReplacementPlanError,
        ChallengerReplacementPlanV2Error,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_PLAN_V2_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return "CHALLENGER_REPLACEMENT_PLAN_V2_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return "CHALLENGER_REPLACEMENT_PLAN_V2_JSON_FLOAT_FORBIDDEN"
    return "CHALLENGER_REPLACEMENT_PLAN_V2_JSON_INVALID"


def load_challenger_replacement_plan_v2(path: Path) -> Dict[str, Any]:
    """Load owner-controlled canonical bytes for the one frozen v2 plan."""

    plan_path = Path(path)
    if not plan_path.is_absolute():
        raise ChallengerReplacementPlanV2Error(
            "CHALLENGER_REPLACEMENT_PLAN_V2_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(plan_path)
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV2Error(
            "CHALLENGER_REPLACEMENT_PLAN_V2_PATH_INVALID"
        ) from error
    try:
        plan = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV2Error(
            _mapped_json_error(error)
        ) from error
    try:
        canonical = canonical_json(plan).encode("utf-8")
    except (CanonicalizationError, RecursionError) as error:
        raise ChallengerReplacementPlanV2Error(
            "CHALLENGER_REPLACEMENT_PLAN_V2_JSON_INVALID"
        ) from error
    if body not in (canonical, canonical + b"\n"):
        raise ChallengerReplacementPlanV2Error(
            "CHALLENGER_REPLACEMENT_PLAN_V2_CANONICAL_BYTES_REQUIRED"
        )
    reasons = challenger_replacement_plan_v2_reasons(plan)
    if reasons:
        raise ChallengerReplacementPlanV2Error(reasons[0])
    return copy.deepcopy(plan)
