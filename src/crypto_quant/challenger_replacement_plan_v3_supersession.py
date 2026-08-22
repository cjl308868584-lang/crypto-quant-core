"""Strict governance evidence for replacement v3 pre-start supersession.

These loaders validate canonical structure, hashes, claims, and bindings. They
cannot prove that an unpatched process collected evidence or that an owner
attestation is historically true.
"""

import base64
import binascii
import copy
import hashlib
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
)
from .challenger_replacement_plan_v3 import (
    ChallengerReplacementPlanV3Error,
    build_challenger_replacement_plan_v3,
    challenger_replacement_plan_v3_reasons,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


REAL_V3_EVIDENCE_QUALIFICATION = "REAL_PRE_START_V3_SUPERSESSION_EVIDENCE"
ACCOUNTABLE_OWNER_DECLARATION_V3 = (
    "I attest that before the bound machine-evidence collection time the "
    "replacement-v3 service had never been installed or started, no "
    "replacement start receipt or canonical production opportunity event "
    "had been created, and no real order had been submitted by this "
    "replacement path. I understand this is an accountable governance "
    "statement, not a fact that code or an OS snapshot can prove, and that "
    "supersession is forbidden after the first v3 start receipt or canonical "
    "production opportunity event."
)
_DECLARATION_SHA256 = hashlib.sha256(
    ACCOUNTABLE_OWNER_DECLARATION_V3.encode("utf-8")
).hexdigest()

_MACHINE_SCHEMA = (
    "challenger-replacement-v3-supersession-machine-evidence-v1.schema.json"
)
_ATTESTATION_SCHEMA = "challenger-replacement-v3-owner-attestation-v1.schema.json"
_RECORD_SCHEMA = "challenger-replacement-plan-v3-supersession-v1.schema.json"
_ZERO_HASH = "0" * 64
_PREVIOUS_PLAN = {
    "release_tag": "v0.64.0",
    "path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.64.0.json"
    ),
    "file_sha256": (
        "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
    ),
    "plan_id": (
        "challenger_replacement_plan_"
        "65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
    ),
    "plan_hash": (
        "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
    ),
}
_MACHINE_PATH = (
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json"
)
_ATTESTATION_PATH = (
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-owner-attestation-v0.69.0.json"
)
_PLAN_PATH = (
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.69.0.json"
)


class ChallengerReplacementPlanV3SupersessionError(ValueError):
    """A v3 supersession artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=None)
def _validator(schema_name: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", schema_name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def v3_supersession_artifact_hash(
    artifact: Mapping[str, Any], hash_field: str
) -> str:
    """Return an artifact hash excluding exactly its self-hash field."""

    return artifact_self_hash(artifact, hash_field)


def _canonical_file_sha(value: Mapping[str, Any]) -> str:
    body = canonical_json(value).encode("utf-8") + b"\n"
    return hashlib.sha256(body).hexdigest()


def _plan_binding(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "path": _PLAN_PATH,
        "file_sha256": _canonical_file_sha(plan),
        "plan_id": plan["plan_id"],
        "plan_hash": plan["plan_hash"],
    }


def _machine_binding(machine: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "path": _MACHINE_PATH,
        "file_sha256": _canonical_file_sha(machine),
        "evidence_id": machine["evidence_id"],
        "evidence_hash": machine["evidence_hash"],
        "git_history_evidence_hash": machine["git_history_evidence_hash"],
        "collected_at": machine["collected_at"],
    }


def _owner_binding(attestation: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "path": _ATTESTATION_PATH,
        "file_sha256": _canonical_file_sha(attestation),
        "attestation_id": attestation["attestation_id"],
        "attestation_hash": attestation["attestation_hash"],
        "signed_at": attestation["signed_at"],
        "signer_uid": attestation["signer"]["uid"],
    }


def _machine_identity(machine: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "collected_at": machine["collected_at"],
        "v3_plan": machine["release_history"]["v3_plan"],
        "git_history_evidence_hash": machine["git_history_evidence_hash"],
        "observation": machine["current_observation"]["observation"],
    }


def _attestation_identity(attestation: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "signed_at": attestation["signed_at"],
        "signer": attestation["signer"],
        "declaration_sha256": attestation["declaration_sha256"],
        "previous_plan": attestation["previous_plan"],
        "v3_plan": attestation["v3_plan"],
        "machine_evidence": attestation["machine_evidence"],
    }


def _record_identity(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "reason": record["reason"],
        "previous_plan": record["previous_plan"],
        "superseding_plan": record["superseding_plan"],
        "v068_foundation": record["v068_foundation"],
        "machine_evidence": record["machine_evidence"],
        "owner_attestation": record["owner_attestation"],
        "semantic_diff_hash": record["semantic_diff_hash"],
        "prohibition": record["prohibition"],
    }


def _decode_and_hash(value: object, claimed_hash: object) -> bool:
    if not isinstance(value, str) or not isinstance(claimed_hash, str):
        return False
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return False
    return hashlib.sha256(decoded).hexdigest() == claimed_hash


def _git_history_hash(machine: Mapping[str, Any]) -> str:
    return business_hash(
        {
            "repository": machine["repository"],
            "release_history": machine["release_history"],
            "transcript_hashes": [
                item["stdout_sha256"] for item in machine["transcripts"]
            ],
        }
    )

def _machine_reasons(machine: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_MACHINE_SCHEMA).iter_errors(machine)):
            reasons.append("CHALLENGER_REPLACEMENT_V3_MACHINE_SCHEMA_INVALID")
        for transcript in machine["transcripts"]:
            if not _decode_and_hash(
                transcript["stdout_base64"], transcript["stdout_sha256"]
            ) or not _decode_and_hash(
                transcript["stderr_base64"], transcript["stderr_sha256"]
            ):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_V3_MACHINE_TRANSCRIPT_INVALID"
                )
        if machine.get("git_history_evidence_hash") != _git_history_hash(machine):
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_MACHINE_GIT_HISTORY_HASH_MISMATCH"
            )
        if machine.get("evidence_id") != stable_id(
            "challenger_replacement_v3_machine_evidence",
            _machine_identity(machine),
        ):
            reasons.append("CHALLENGER_REPLACEMENT_V3_MACHINE_ID_MISMATCH")
        if machine.get("evidence_hash") != v3_supersession_artifact_hash(
            machine, "evidence_hash"
        ):
            reasons.append("CHALLENGER_REPLACEMENT_V3_MACHINE_HASH_MISMATCH")
        plan = build_challenger_replacement_plan_v3()
        if machine["release_history"]["previous_plan"] != _PREVIOUS_PLAN:
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_MACHINE_PREVIOUS_PLAN_MISMATCH"
            )
        if machine["release_history"]["v3_plan"] != _plan_binding(plan):
            reasons.append("CHALLENGER_REPLACEMENT_V3_MACHINE_PLAN_MISMATCH")
    except (
        CanonicalizationError,
        ChallengerReplacementPlanV3Error,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_V3_MACHINE_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _attestation_reasons(attestation: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_ATTESTATION_SCHEMA).iter_errors(attestation)):
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_ATTESTATION_SCHEMA_INVALID"
            )
        if (
            attestation.get("declaration") != ACCOUNTABLE_OWNER_DECLARATION_V3
            or attestation.get("declaration_sha256") != _DECLARATION_SHA256
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_ATTESTATION_DECLARATION_MISMATCH"
            )
        plan = build_challenger_replacement_plan_v3()
        if attestation.get("previous_plan") != _PREVIOUS_PLAN:
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_ATTESTATION_PREVIOUS_PLAN_MISMATCH"
            )
        if attestation.get("v068_foundation") != plan["foundation"]:
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_ATTESTATION_FOUNDATION_MISMATCH"
            )
        if attestation.get("v3_plan") != _plan_binding(plan):
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_ATTESTATION_PLAN_MISMATCH"
            )
        if attestation.get("attestation_id") != stable_id(
            "challenger_replacement_v3_owner_attestation",
            _attestation_identity(attestation),
        ):
            reasons.append("CHALLENGER_REPLACEMENT_V3_ATTESTATION_ID_MISMATCH")
        if attestation.get(
            "attestation_hash"
        ) != v3_supersession_artifact_hash(attestation, "attestation_hash"):
            reasons.append("CHALLENGER_REPLACEMENT_V3_ATTESTATION_HASH_MISMATCH")
    except (
        CanonicalizationError,
        ChallengerReplacementPlanV3Error,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_V3_ATTESTATION_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _record_reasons(record: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_RECORD_SCHEMA).iter_errors(record)):
            reasons.append("CHALLENGER_REPLACEMENT_V3_RECORD_SCHEMA_INVALID")
        plan = build_challenger_replacement_plan_v3()
        if record.get("previous_plan") != _PREVIOUS_PLAN:
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_RECORD_PREVIOUS_PLAN_MISMATCH"
            )
        if record.get("superseding_plan") != _plan_binding(plan):
            reasons.append("CHALLENGER_REPLACEMENT_V3_RECORD_PLAN_MISMATCH")
        if record.get("v068_foundation") != plan["foundation"]:
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_RECORD_FOUNDATION_MISMATCH"
            )
        if record.get("semantic_diff_hash") != business_hash(
            plan["supersession"]["semantic_changes"]
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_V3_RECORD_SEMANTIC_DIFF_MISMATCH"
            )
        if record.get("record_id") != stable_id(
            "challenger_replacement_plan_v3_supersession",
            _record_identity(record),
        ):
            reasons.append("CHALLENGER_REPLACEMENT_V3_RECORD_ID_MISMATCH")
        if record.get("record_hash") != v3_supersession_artifact_hash(
            record, "record_hash"
        ):
            reasons.append("CHALLENGER_REPLACEMENT_V3_RECORD_HASH_MISMATCH")
    except (
        CanonicalizationError,
        ChallengerReplacementPlanV3Error,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_V3_RECORD_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _mapped_json_reason(error: ChallengerReplacementPlanError, prefix: str) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return prefix + "_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return prefix + "_JSON_FLOAT_FORBIDDEN"
    return prefix + "_JSON_INVALID"


def _load_canonical(
    path: Path,
    *,
    prefix: str,
    reasons,
) -> Dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        raise ChallengerReplacementPlanV3SupersessionError(
            prefix + "_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(artifact_path)
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV3SupersessionError(
            prefix + "_PATH_INVALID"
        ) from error
    try:
        artifact = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV3SupersessionError(
            _mapped_json_reason(error, prefix)
        ) from error
    try:
        canonical = canonical_json(artifact).encode("utf-8")
    except (CanonicalizationError, RecursionError) as error:
        raise ChallengerReplacementPlanV3SupersessionError(
            prefix + "_JSON_INVALID"
        ) from error
    if body not in (canonical, canonical + b"\n"):
        raise ChallengerReplacementPlanV3SupersessionError(
            prefix + "_CANONICAL_BYTES_REQUIRED"
        )
    failures = reasons(artifact)
    if failures:
        raise ChallengerReplacementPlanV3SupersessionError(failures[0])
    return copy.deepcopy(artifact)


def load_challenger_replacement_v3_machine_evidence(
    path: Path,
) -> Dict[str, Any]:
    return _load_canonical(
        path,
        prefix="CHALLENGER_REPLACEMENT_V3_MACHINE",
        reasons=_machine_reasons,
    )


def load_challenger_replacement_v3_owner_attestation(
    path: Path,
) -> Dict[str, Any]:
    return _load_canonical(
        path,
        prefix="CHALLENGER_REPLACEMENT_V3_ATTESTATION",
        reasons=_attestation_reasons,
    )


def build_challenger_replacement_v3_supersession_record(
    plan: Mapping[str, Any],
    machine: Mapping[str, Any],
    attestation: Mapping[str, Any],
) -> Dict[str, Any]:
    """Bind the exact v3 plan, machine evidence, and owner attestation."""

    if challenger_replacement_plan_v3_reasons(plan):
        raise ChallengerReplacementPlanV3SupersessionError(
            "CHALLENGER_REPLACEMENT_V3_RECORD_PLAN_INVALID"
        )
    machine_failures = _machine_reasons(machine)
    if machine_failures:
        raise ChallengerReplacementPlanV3SupersessionError(machine_failures[0])
    attestation_failures = _attestation_reasons(attestation)
    if attestation_failures:
        raise ChallengerReplacementPlanV3SupersessionError(
            attestation_failures[0]
        )
    if attestation["machine_evidence"] != _machine_binding(machine):
        raise ChallengerReplacementPlanV3SupersessionError(
            "CHALLENGER_REPLACEMENT_V3_RECORD_MACHINE_BINDING_MISMATCH"
        )
    if attestation["v3_plan"] != _plan_binding(plan):
        raise ChallengerReplacementPlanV3SupersessionError(
            "CHALLENGER_REPLACEMENT_V3_RECORD_PLAN_BINDING_MISMATCH"
        )
    if attestation["signed_at"] < machine["collected_at"]:
        raise ChallengerReplacementPlanV3SupersessionError(
            "CHALLENGER_REPLACEMENT_V3_RECORD_TIME_ORDER_INVALID"
        )

    record: Dict[str, Any] = {
        "$schema": "./challenger-replacement-plan-v3-supersession-v1.schema.json",
        "schema_version": "1.0.0",
        "record_id": (
            "challenger_replacement_plan_v3_supersession_" + _ZERO_HASH
        ),
        "record_hash": _ZERO_HASH,
        "reason": (
            "SUPERSEDED_PRE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE"
        ),
        "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
        "superseding_plan": _plan_binding(plan),
        "v068_foundation": copy.deepcopy(plan["foundation"]),
        "machine_evidence": _machine_binding(machine),
        "owner_attestation": _owner_binding(attestation),
        "semantic_diff_hash": business_hash(
            plan["supersession"]["semantic_changes"]
        ),
        "prohibition": {
            "supersession_forbidden_after": (
                "FIRST_V3_START_RECEIPT_OR_CANONICAL_PRODUCTION_"
                "OPPORTUNITY_EVENT"
            ),
            "old_artifacts_mutable": False,
            "post_start_reset_allowed": False,
        },
        "authority": {
            "credentials_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
        },
        "status": "PLAN_V3_SUPERSESSION_RECORDED_PRE_START",
        "warnings": [
            "MACHINE_OBSERVATION_IS_CURRENT_NOT_HISTORICAL_PROOF",
            "OWNER_ATTESTATION_IS_ACCOUNTABLE_GOVERNANCE_CLAIM",
            "NO_INSTALL_START_CREDENTIAL_ORDER_FUND_OR_CANARY_AUTHORITY",
        ],
    }
    record["record_id"] = stable_id(
        "challenger_replacement_plan_v3_supersession",
        _record_identity(record),
    )
    record["record_hash"] = v3_supersession_artifact_hash(
        record, "record_hash"
    )
    failures = _record_reasons(record)
    if failures:
        raise ChallengerReplacementPlanV3SupersessionError(failures[0])
    return copy.deepcopy(record)


def load_challenger_replacement_v3_supersession_record(
    path: Path,
) -> Dict[str, Any]:
    return _load_canonical(
        path,
        prefix="CHALLENGER_REPLACEMENT_V3_RECORD",
        reasons=_record_reasons,
    )
