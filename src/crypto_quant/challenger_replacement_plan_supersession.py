"""Strict contracts for a pre-start replacement-plan supersession.

These loaders validate structure, hashes, claims, and cross-artifact bindings.
They do not prove collection provenance or the truth of the owner declaration.
"""

import base64
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
from .challenger_replacement_plan_v2 import (
    load_challenger_replacement_plan_v2,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_MACHINE_SCHEMA = (
    "challenger-replacement-supersession-machine-evidence-v1.schema.json"
)
_ATTESTATION_SCHEMA = "challenger-replacement-owner-attestation-v1.schema.json"
_RECORD_SCHEMA = "challenger-replacement-plan-supersession-v1.schema.json"

REAL_EVIDENCE_QUALIFICATION = (
    "REAL_MACHINE_READ_ONLY_SUPERSESSION_PRECONDITION"
)
TEST_EVIDENCE_QUALIFICATION = "TEST_FIXTURE_ONLY_NOT_SUPERSESSION_EVIDENCE"

_SERVICE_IDENTITY = "gui/501/local.crypto-quant.challenger-replacement-v1"
_RUNTIME_ROOT = (
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-v1"
)

_PREVIOUS_PLAN = {
    "release_tag": "v0.62.0",
    "peeled_commit": "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a",
    "path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.62.0.json"
    ),
    "file_sha256": "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734",
    "plan_id": "challenger_replacement_plan_d4a542c1566f7a90466ca4d5301b81847f5b5eba93c7a00903d2d95331bc23a2",
    "plan_hash": "95f395b17d9c09d325c58391542ce5f3d9df5ce6a706b1bba8ffcb62dc6c883c",
    "service_identity": _SERVICE_IDENTITY,
    "runtime_root": _RUNTIME_ROOT,
}

ACCOUNTABLE_OWNER_DECLARATION = (
    "I attest that, before the signed_at timestamp in this object and before "
    "the linked machine observation, the replacement Challenger "
    "service_identity and runtime_root bound by previous_plan and "
    "superseding_plan in this object had never been installed or started and "
    "had produced no start receipt, canonical event, real slot, or production "
    "state write. I accept accountability for this historical declaration and "
    "understand that it is not proved by the collector, loader, Git history, "
    "or operating-system snapshot."
)

_PROHIBITION = {
    "reason": "SUPERSEDED_PRE_START_STORAGE_SAFETY_CORRECTION",
    "supersession_forbidden_after": (
        "PLAN_SUPERSESSION_FORBIDDEN_AFTER_FIRST_START_RECEIPT_OR_"
        "CANONICAL_EVENT"
    ),
}

_AUTHORITY = {
    "credentials_allowed": False,
    "account_requests_allowed": False,
    "broker_requests_allowed": False,
    "real_orders_allowed": False,
    "production_activation": False,
    "runtime_install_authorized": False,
    "replacement_start_authorized": False,
    "runner_invocation_count": 0,
    "market_request_count": 0,
    "state_write_count": 0,
}


class ChallengerReplacementPlanSupersessionError(ValueError):
    """A supersession governance artifact failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=3)
def _validator(schema_name: str) -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", schema_name)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def supersession_artifact_hash(
    value: Mapping[str, Any], hash_field: str
) -> str:
    """Hash a supersession artifact while excluding its sole self-hash."""

    return artifact_self_hash(value, hash_field)


def _artifact_id(
    value: Mapping[str, Any], *, id_field: str, hash_field: str, prefix: str
) -> str:
    return stable_id(
        prefix,
        {
            key: item
            for key, item in value.items()
            if key not in (id_field, hash_field)
        },
    )


def _file_sha256(path: Path) -> str:
    try:
        body = _read_owner_controlled_regular_file(Path(path))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_PATH_INVALID"
        ) from error
    return hashlib.sha256(body).hexdigest()


def _mapped_json_reason(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_JSON_FLOAT_FORBIDDEN"
    return "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_JSON_INVALID"


def _load_canonical_mapping(path: Path) -> Dict[str, Any]:
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(artifact_path)
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_PATH_INVALID"
        ) from error
    try:
        value = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanSupersessionError(
            _mapped_json_reason(error)
        ) from error
    try:
        canonical = canonical_json(value).encode("utf-8")
    except (CanonicalizationError, RecursionError) as error:
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_JSON_INVALID"
        ) from error
    if body not in (canonical, canonical + b"\n"):
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_CANONICAL_BYTES_REQUIRED"
        )
    return value


def _decode_transcript_stream(value: str, claimed_hash: str) -> bool:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError):
        return False
    return hashlib.sha256(decoded).hexdigest() == claimed_hash


def _transcript_valid(transcript: Mapping[str, Any]) -> bool:
    return _decode_transcript_stream(
        transcript["stdout_base64"], transcript["stdout_sha256"]
    ) and _decode_transcript_stream(
        transcript["stderr_base64"], transcript["stderr_sha256"]
    )


def _machine_reasons(machine: Mapping[str, Any]) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_MACHINE_SCHEMA).iter_errors(machine)):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_MACHINE_SCHEMA_INVALID"
            )
        if machine.get("evidence_qualification") != REAL_EVIDENCE_QUALIFICATION:
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_EVIDENCE_QUALIFICATION_INVALID"
            )
        if machine.get("evidence_hash") != supersession_artifact_hash(
            machine, "evidence_hash"
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_MACHINE_HASH_MISMATCH"
            )
        if machine.get("evidence_id") != _artifact_id(
            machine,
            id_field="evidence_id",
            hash_field="evidence_hash",
            prefix="challenger_replacement_supersession_machine_evidence",
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_MACHINE_ID_MISMATCH"
            )
        transcripts = [machine["launchctl_transcript"]]
        transcripts.extend(machine["git_history"]["transcripts"])
        if not all(_transcript_valid(item) for item in transcripts):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_TRANSCRIPT_HASH_MISMATCH"
            )
        names = [item["name"] for item in machine["git_history"]["transcripts"]]
        if len(names) != len(set(names)):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_HISTORY_AMBIGUOUS"
            )
        git_history = machine["git_history"]
        if git_history.get("git_history_evidence_hash") != (
            supersession_artifact_hash(
                git_history, "git_history_evidence_hash"
            )
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_HISTORY_HASH_MISMATCH"
            )
    except (CanonicalizationError, KeyError, TypeError, ValueError):
        reasons.append(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_MACHINE_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def load_challenger_replacement_supersession_machine_evidence(
    path: Path,
) -> Dict[str, Any]:
    """Load formally qualified current-machine and Git evidence."""

    machine = _load_canonical_mapping(path)
    reasons = _machine_reasons(machine)
    if reasons:
        raise ChallengerReplacementPlanSupersessionError(reasons[0])
    return copy.deepcopy(machine)


def _superseding_plan_binding(
    v2_plan_path: Path, v2_plan: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.64.0.json"
        ),
        "file_sha256": _file_sha256(v2_plan_path),
        "plan_id": v2_plan["plan_id"],
        "plan_hash": v2_plan["plan_hash"],
        "foundation": copy.deepcopy(v2_plan["foundation"]),
        "service_identity": v2_plan["isolation_policy"]["service_identity"],
        "runtime_root": v2_plan["isolation_policy"]["runtime_root"],
    }


def _machine_binding(
    machine_evidence_path: Path, machine: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-supersession-machine-evidence-v0.64.0.json"
        ),
        "file_sha256": _file_sha256(machine_evidence_path),
        "evidence_id": machine["evidence_id"],
        "evidence_hash": machine["evidence_hash"],
        "git_history_evidence_hash": machine["git_history"][
            "git_history_evidence_hash"
        ],
    }


def _attestation_reasons(
    attestation: Mapping[str, Any],
    *,
    v2_plan_path: Path,
    machine_evidence_path: Path,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator(_ATTESTATION_SCHEMA).iter_errors(attestation)):
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_SCHEMA_INVALID"
            )
        if (
            attestation.get("evidence_qualification")
            != REAL_EVIDENCE_QUALIFICATION
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_EVIDENCE_QUALIFICATION_INVALID"
            )
        if attestation.get("attestation_hash") != supersession_artifact_hash(
            attestation, "attestation_hash"
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_HASH_MISMATCH"
            )
        if attestation.get("attestation_id") != _artifact_id(
            attestation,
            id_field="attestation_id",
            hash_field="attestation_hash",
            prefix="challenger_replacement_owner_attestation",
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_ID_MISMATCH"
            )
        v2_plan = load_challenger_replacement_plan_v2(Path(v2_plan_path))
        machine = load_challenger_replacement_supersession_machine_evidence(
            Path(machine_evidence_path)
        )
        if attestation.get("previous_plan") != _PREVIOUS_PLAN:
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_V1_BINDING_MISMATCH"
            )
        if attestation.get("superseding_plan") != _superseding_plan_binding(
            Path(v2_plan_path), v2_plan
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_V2_BINDING_MISMATCH"
            )
        if attestation.get("machine_evidence_binding") != _machine_binding(
            Path(machine_evidence_path), machine
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_EVIDENCE_BINDING_MISMATCH"
            )
    except (
        CanonicalizationError,
        ChallengerReplacementPlanSupersessionError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_REPLACEMENT_OWNER_ATTESTATION_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def load_challenger_replacement_owner_attestation(
    path: Path, *, v2_plan_path: Path, machine_evidence_path: Path
) -> Dict[str, Any]:
    """Load the accountable declaration and verify all exact bindings."""

    attestation = _load_canonical_mapping(path)
    reasons = _attestation_reasons(
        attestation,
        v2_plan_path=Path(v2_plan_path),
        machine_evidence_path=Path(machine_evidence_path),
    )
    if reasons:
        raise ChallengerReplacementPlanSupersessionError(reasons[0])
    return copy.deepcopy(attestation)


def _record_machine_binding(
    machine_evidence_path: Path, machine: Mapping[str, Any]
) -> Dict[str, Any]:
    binding = _machine_binding(machine_evidence_path, machine)
    binding.update(
        {
            "evidence_qualification": machine["evidence_qualification"],
            "observation": machine["observation"],
        }
    )
    return binding


def _owner_binding(
    owner_attestation_path: Path, attestation: Mapping[str, Any]
) -> Dict[str, Any]:
    return {
        "path": (
            "artifacts/challenger-replacement/"
            "challenger-replacement-owner-attestation-v0.64.0.json"
        ),
        "file_sha256": _file_sha256(owner_attestation_path),
        "attestation_id": attestation["attestation_id"],
        "attestation_hash": attestation["attestation_hash"],
        "attestation_type": attestation["attestation_type"],
        "signer_github_login": attestation["signer_github_login"],
        "signer_os_username": attestation["signer_os_username"],
        "signer_uid": attestation["signer_uid"],
    }


def _record_identity(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "previous_plan": record["previous_plan"],
        "superseding_plan": record["superseding_plan"],
        "machine_evidence_file_sha256": record["machine_evidence_binding"][
            "file_sha256"
        ],
        "machine_evidence_hash": record["machine_evidence_binding"][
            "evidence_hash"
        ],
        "git_history_evidence_hash": record["machine_evidence_binding"][
            "git_history_evidence_hash"
        ],
        "owner_attestation_file_sha256": record["owner_attestation_binding"][
            "file_sha256"
        ],
        "owner_attestation_hash": record["owner_attestation_binding"][
            "attestation_hash"
        ],
        "reason": record["prohibition"]["reason"],
        "supersession_forbidden_after": record["prohibition"][
            "supersession_forbidden_after"
        ],
    }


def build_challenger_replacement_plan_supersession_record(
    *,
    v2_plan_path: Path,
    machine_evidence_path: Path,
    owner_attestation_path: Path,
) -> Dict[str, Any]:
    """Build the one record from three already validated exact artifacts."""

    v2_path = Path(v2_plan_path)
    machine_path = Path(machine_evidence_path)
    attestation_path = Path(owner_attestation_path)
    v2_plan = load_challenger_replacement_plan_v2(v2_path)
    machine = load_challenger_replacement_supersession_machine_evidence(
        machine_path
    )
    attestation = load_challenger_replacement_owner_attestation(
        attestation_path,
        v2_plan_path=v2_path,
        machine_evidence_path=machine_path,
    )
    record: Dict[str, Any] = {
        "$schema": "./challenger-replacement-plan-supersession-v1.schema.json",
        "schema_version": "1.0.0",
        "record_id": "challenger_replacement_plan_supersession_" + "0" * 64,
        "record_hash": "0" * 64,
        "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
        "superseding_plan": _superseding_plan_binding(v2_path, v2_plan),
        "machine_evidence_binding": _record_machine_binding(
            machine_path, machine
        ),
        "owner_attestation_binding": _owner_binding(
            attestation_path, attestation
        ),
        "prohibition": copy.deepcopy(_PROHIBITION),
        "authority": copy.deepcopy(_AUTHORITY),
        "status": "PLAN_SUPERSESSION_RECORDED_PRE_START",
        "warnings": [
            "OWNER_ATTESTATION_IS_GOVERNANCE_CLAIM_NOT_MACHINE_PROOF",
            "NO_RUNTIME_OR_START_AUTHORITY",
        ],
    }
    record["record_id"] = stable_id(
        "challenger_replacement_plan_supersession", _record_identity(record)
    )
    record["record_hash"] = supersession_artifact_hash(record, "record_hash")
    if tuple(_validator(_RECORD_SCHEMA).iter_errors(record)):
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_SCHEMA_INVALID"
        )
    return copy.deepcopy(record)


def load_challenger_replacement_plan_supersession_record(
    path: Path,
    *,
    v2_plan_path: Path,
    machine_evidence_path: Path,
    owner_attestation_path: Path,
) -> Dict[str, Any]:
    """Load the exact record and rebuild it from its three authorities."""

    record = _load_canonical_mapping(path)
    try:
        if tuple(_validator(_RECORD_SCHEMA).iter_errors(record)):
            raise ChallengerReplacementPlanSupersessionError(
                "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_SCHEMA_INVALID"
            )
        if record.get("record_hash") != supersession_artifact_hash(
            record, "record_hash"
        ):
            raise ChallengerReplacementPlanSupersessionError(
                "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_HASH_MISMATCH"
            )
        if record.get("record_id") != stable_id(
            "challenger_replacement_plan_supersession", _record_identity(record)
        ):
            raise ChallengerReplacementPlanSupersessionError(
                "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_ID_MISMATCH"
            )
        expected = build_challenger_replacement_plan_supersession_record(
            v2_plan_path=Path(v2_plan_path),
            machine_evidence_path=Path(machine_evidence_path),
            owner_attestation_path=Path(owner_attestation_path),
        )
        if business_hash(record) != business_hash(expected):
            raise ChallengerReplacementPlanSupersessionError(
                "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_BINDING_MISMATCH"
            )
    except ChallengerReplacementPlanSupersessionError:
        raise
    except (CanonicalizationError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPlanSupersessionError(
            "CHALLENGER_REPLACEMENT_PLAN_SUPERSESSION_RECORD_SEMANTIC_INVALID"
        ) from error
    return copy.deepcopy(record)
