"""Fixed-path pre-start supersession ceremony for replacement v3."""

import base64
import copy
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan_supersession_cli import (
    _validate_reviewed_repo_root,
)
from .challenger_replacement_plan_v3 import (
    load_challenger_replacement_plan_v3,
)
from .challenger_replacement_plan_v3_supersession import (
    ACCOUNTABLE_OWNER_DECLARATION_V3,
    REAL_V3_EVIDENCE_QUALIFICATION,
    _PREVIOUS_PLAN,
    _attestation_identity,
    _machine_binding,
    _machine_identity,
    _plan_binding,
    build_challenger_replacement_v3_supersession_record,
    load_challenger_replacement_v3_machine_evidence,
    load_challenger_replacement_v3_owner_attestation,
    v3_supersession_artifact_hash,
)
from .challenger_replacement_supersession_publish import (
    _require_empty_protocol_staging,
    publish_challenger_replacement_v3_machine_evidence_bytes,
    publish_challenger_replacement_v3_owner_attestation_bytes,
    publish_challenger_replacement_v3_supersession_record_bytes,
)


COMMANDS = (
    "collect-machine-evidence",
    "record-owner-attestation",
    "assemble-record",
)
_SERVICE = "gui/501/local.crypto-quant.challenger-replacement-v1"
_RUNTIME_ROOT = Path(
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-v1"
)
_PLIST = Path(
    "/Users/chenm4/Library/LaunchAgents/"
    "local.crypto-quant.challenger-replacement-v1.plist"
)
_PLAN_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.69.0.json"
)
_MACHINE_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-supersession-machine-evidence-v0.69.0.json"
)
_ATTESTATION_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-v3-owner-attestation-v0.69.0.json"
)
_RECORD_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v3-supersession-v0.69.0.json"
)
_V064_PEELED = "c4f6ea213077850a8fc8b9bd3392f1a4bac466f9"
_V068_PEELED = "1371997d61679609804d58753ae79147d60e1c01"
_ACKNOWLEDGEMENT = (
    "I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_V3_DECLARATION"
)
_MISSING_SERVICE_ERROR = (
    'Bad request.\nCould not find service "'
    'local.crypto-quant.challenger-replacement-v1'
    '" in domain for user gui: 501\n'
).encode("utf-8")
_PROCESS_ENV = {
    "HOME": "/var/empty",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


class V3SupersessionCommandError(RuntimeError):
    """A fixed v3 ceremony command failed closed."""


def _repository_root() -> Path:
    module_path = Path(__file__)
    if not module_path.is_absolute():
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_REPOSITORY_INVALID"
        )
    root = module_path.parents[2]
    _validate_reviewed_repo_root(root)
    return root


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json(value).encode("utf-8") + b"\n"


def _transcript(
    name: str, argv: Sequence[str], result: subprocess.CompletedProcess
) -> Dict[str, Any]:
    stdout = bytes(result.stdout)
    stderr = bytes(result.stderr)
    return {
        "name": name,
        "argv": list(argv),
        "exit_code": result.returncode,
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }


def _collection_argv(root: Path) -> Tuple[Tuple[str, ...], ...]:
    reviewed = str(root)
    return (
        ("/usr/bin/git", "-C", reviewed, "rev-parse", "v0.64.0^{}"),
        ("/usr/bin/git", "-C", reviewed, "rev-parse", "v0.68.0^{}"),
        ("/usr/bin/git", "-C", reviewed, "rev-parse", "origin/main"),
        ("/usr/bin/git", "-C", reviewed, "rev-parse", "HEAD"),
        (
            "/usr/bin/git",
            "-C",
            reviewed,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        ("/usr/bin/git", "-C", reviewed, "cat-file", "-t", "v0.68.0"),
        ("/bin/launchctl", "print-disabled", "gui/501"),
        ("/bin/launchctl", "print", _SERVICE),
    )


def _run(argv: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            tuple(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_PROCESS_ENV,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_TRANSCRIPT_FAILED"
        ) from error
    if result.returncode < 0 or result.returncode > 255:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_TRANSCRIPT_FAILED"
        )
    return result


def _stdout_line(result: subprocess.CompletedProcess) -> str:
    try:
        return bytes(result.stdout).decode("ascii").strip()
    except UnicodeError as error:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_TRANSCRIPT_FAILED"
        ) from error


def _validate_collection_results(
    results: Sequence[subprocess.CompletedProcess],
) -> None:
    if (
        len(results) != 8
        or any(result.returncode != 0 for result in results[:7])
        or results[7].returncode != 113
        or bytes(results[7].stdout) != b""
        or bytes(results[7].stderr) != _MISSING_SERVICE_ERROR
        or _stdout_line(results[0]) != _V064_PEELED
        or _stdout_line(results[1]) != _V068_PEELED
        or _stdout_line(results[2]) != _V068_PEELED
        or len(_stdout_line(results[3])) != 40
        or any(
            character not in "0123456789abcdef"
            for character in _stdout_line(results[3])
        )
        or _stdout_line(results[4]) != ""
        or _stdout_line(results[5]) != "tag"
    ):
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_FOUNDATION_INVALID"
        )


def _build_machine_evidence(
    *,
    collected_at: str,
    repository: Mapping[str, Any],
    transcripts: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "$schema": (
            "./challenger-replacement-v3-supersession-"
            "machine-evidence-v1.schema.json"
        ),
        "schema_version": "1.0.0",
        "evidence_id": "challenger_replacement_v3_machine_evidence_" + "0" * 64,
        "evidence_hash": "0" * 64,
        "evidence_qualification": REAL_V3_EVIDENCE_QUALIFICATION,
        "collected_at": collected_at,
        "repository": copy.deepcopy(dict(repository)),
        "release_history": {
            "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
            "v068_release_tag": "v0.68.0",
            "v068_peeled_commit": _V068_PEELED,
            "v3_plan": _plan_binding(plan),
        },
        "current_observation": {
            "observation": "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
            "runtime_root": "ABSENT",
            "target_plist": "ABSENT",
            "service": "NOT_LOADED",
            "start_receipt_count": 0,
            "canonical_event_count": 0,
        },
        "transcripts": [copy.deepcopy(dict(item)) for item in transcripts],
        "collector_authority": {
            "collector_state_write_count": 0,
            "market_request_count": 0,
            "account_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "production_root_write_count": 0,
        },
        "warnings": [
            "CURRENT_OBSERVATION_DOES_NOT_PROVE_HISTORICAL_NONEXISTENCE",
            "OWNER_ATTESTATION_REQUIRED_FOR_HISTORICAL_PRE_START_CLAIM",
        ],
    }
    value["git_history_evidence_hash"] = business_hash(
        {
            "repository": value["repository"],
            "release_history": value["release_history"],
            "transcript_hashes": [
                item["stdout_sha256"] for item in value["transcripts"]
            ],
        }
    )
    value["evidence_id"] = stable_id(
        "challenger_replacement_v3_machine_evidence",
        _machine_identity(value),
    )
    value["evidence_hash"] = v3_supersession_artifact_hash(
        value, "evidence_hash"
    )
    return value


def _build_owner_attestation(
    *,
    signed_at: str,
    plan: Mapping[str, Any],
    machine: Mapping[str, Any],
) -> Dict[str, Any]:
    value: Dict[str, Any] = {
        "$schema": "./challenger-replacement-v3-owner-attestation-v1.schema.json",
        "schema_version": "1.0.0",
        "attestation_id": "challenger_replacement_v3_owner_attestation_" + "0" * 64,
        "attestation_hash": "0" * 64,
        "evidence_qualification": REAL_V3_EVIDENCE_QUALIFICATION,
        "attestation_type": "ACCOUNTABLE_OWNER_PRE_START_V3_ATTESTATION",
        "signed_at": signed_at,
        "signer": {
            "github_login": "cjl308868584-lang",
            "os_username": "chenm4",
            "uid": 501,
        },
        "declaration": ACCOUNTABLE_OWNER_DECLARATION_V3,
        "declaration_sha256": hashlib.sha256(
            ACCOUNTABLE_OWNER_DECLARATION_V3.encode("utf-8")
        ).hexdigest(),
        "owner_acknowledgement": _ACKNOWLEDGEMENT,
        "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
        "v068_foundation": copy.deepcopy(plan["foundation"]),
        "v3_plan": _plan_binding(plan),
        "machine_evidence": _machine_binding(machine),
    }
    value["attestation_id"] = stable_id(
        "challenger_replacement_v3_owner_attestation",
        _attestation_identity(value),
    )
    value["attestation_hash"] = v3_supersession_artifact_hash(
        value, "attestation_hash"
    )
    return value


def _require_status(root: Path, expected: Tuple[str, ...]) -> None:
    result = _run(
        (
            "/usr/bin/git",
            "-C",
            str(root),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        )
    )
    if result.returncode != 0:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_CANDIDATE_STATE_INVALID"
        )
    actual = tuple(sorted(bytes(result.stdout).decode("utf-8").splitlines()))
    if actual != tuple(sorted(expected)):
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_CANDIDATE_STATE_INVALID"
        )


def _require_absent(path: Path) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_CURRENT_STATE_AMBIGUOUS"
        ) from error
    raise V3SupersessionCommandError(
        "CHALLENGER_REPLACEMENT_V3_CURRENT_STATE_PRESENT"
    )


def _require_pre_start_state() -> None:
    _require_absent(_RUNTIME_ROOT)
    _require_absent(_PLIST)
    result = _run(("/bin/launchctl", "print", _SERVICE))
    if (
        result.returncode == 113
        and bytes(result.stdout) == b""
        and bytes(result.stderr) == _MISSING_SERVICE_ERROR
    ):
        return
    if result.returncode == 0:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_CURRENT_STATE_PRESENT"
        )
    raise V3SupersessionCommandError(
        "CHALLENGER_REPLACEMENT_V3_CURRENT_STATE_AMBIGUOUS"
    )


def _collect_machine_evidence() -> Dict[str, Any]:
    if os.geteuid() != 501:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_UID_INVALID"
        )
    root = _repository_root()
    plan = load_challenger_replacement_plan_v3(root / _PLAN_RELATIVE)
    _require_status(root, ())
    _require_empty_protocol_staging()
    for path in (_MACHINE_RELATIVE, _ATTESTATION_RELATIVE, _RECORD_RELATIVE):
        _require_absent(root / path)
    _require_pre_start_state()
    commands = _collection_argv(root)
    names = (
        "git_v064_peeled",
        "git_v068_peeled",
        "git_origin_main",
        "git_head",
        "git_status_pre_collection",
        "git_v068_type",
        "launchctl_print_disabled",
        "launchctl_service",
    )
    results = tuple(_run(argv) for argv in commands)
    _validate_collection_results(results)
    _require_pre_start_state()
    transcripts = [
        _transcript(name, argv, result)
        for name, argv, result in zip(names, commands, results)
    ]
    return _build_machine_evidence(
        collected_at=_timestamp(),
        repository={
            "root": str(root),
            "head": _stdout_line(results[3]),
            "worktree_state": "CLEAN_PRE_ARTIFACT_HEAD",
        },
        transcripts=transcripts,
        plan=plan,
    )


def _collect_command() -> int:
    root = _repository_root()
    value = _collect_machine_evidence()
    _require_status(root, ())
    _require_empty_protocol_staging()
    _require_pre_start_state()
    publish_challenger_replacement_v3_machine_evidence_bytes(
        _canonical_bytes(value)
    )
    _require_status(root, ("?? " + _MACHINE_RELATIVE.as_posix(),))
    _require_empty_protocol_staging()
    return 0


def _attestation_command() -> int:
    root = _repository_root()
    _require_status(root, ("?? " + _MACHINE_RELATIVE.as_posix(),))
    _require_empty_protocol_staging()
    plan = load_challenger_replacement_plan_v3(root / _PLAN_RELATIVE)
    machine = load_challenger_replacement_v3_machine_evidence(
        root / _MACHINE_RELATIVE
    )
    value = _build_owner_attestation(
        signed_at=_timestamp(), plan=plan, machine=machine
    )
    declaration_sha = hashlib.sha256(
        ACCOUNTABLE_OWNER_DECLARATION_V3.encode("utf-8")
    ).hexdigest()
    binding_sha = hashlib.sha256(
        canonical_json(
            {
                "previous_plan": value["previous_plan"],
                "v068_foundation": value["v068_foundation"],
                "v3_plan": value["v3_plan"],
                "machine_evidence": value["machine_evidence"],
                "signer": value["signer"],
                "signed_at": value["signed_at"],
            }
        ).encode("utf-8")
    ).hexdigest()
    print(ACCOUNTABLE_OWNER_DECLARATION_V3)
    print("declaration_sha256=" + declaration_sha)
    print("binding_sha256=" + binding_sha)
    print("signed_at=" + value["signed_at"])
    print("machine_evidence_hash=" + machine["evidence_hash"])
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_OWNER_INTERACTIVE_TTY_REQUIRED"
        )
    if input("acknowledgement: ") != _ACKNOWLEDGEMENT:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_OWNER_ACKNOWLEDGEMENT_REQUIRED"
        )
    _require_status(root, ("?? " + _MACHINE_RELATIVE.as_posix(),))
    replayed_plan = load_challenger_replacement_plan_v3(root / _PLAN_RELATIVE)
    replayed_machine = load_challenger_replacement_v3_machine_evidence(
        root / _MACHINE_RELATIVE
    )
    if _build_owner_attestation(
        signed_at=value["signed_at"],
        plan=replayed_plan,
        machine=replayed_machine,
    ) != value:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_PRECONDITION_CHANGED"
        )
    publish_challenger_replacement_v3_owner_attestation_bytes(
        _canonical_bytes(value)
    )
    _require_status(
        root,
        (
            "?? " + _ATTESTATION_RELATIVE.as_posix(),
            "?? " + _MACHINE_RELATIVE.as_posix(),
        ),
    )
    _require_empty_protocol_staging()
    return 0


def _assemble_command() -> int:
    root = _repository_root()
    expected = (
        "?? " + _ATTESTATION_RELATIVE.as_posix(),
        "?? " + _MACHINE_RELATIVE.as_posix(),
    )
    _require_status(root, expected)
    _require_empty_protocol_staging()
    _require_pre_start_state()
    plan = load_challenger_replacement_plan_v3(root / _PLAN_RELATIVE)
    machine = load_challenger_replacement_v3_machine_evidence(
        root / _MACHINE_RELATIVE
    )
    attestation = load_challenger_replacement_v3_owner_attestation(
        root / _ATTESTATION_RELATIVE
    )
    record = build_challenger_replacement_v3_supersession_record(
        plan, machine, attestation
    )
    _require_status(root, expected)
    replayed_record = build_challenger_replacement_v3_supersession_record(
        load_challenger_replacement_plan_v3(root / _PLAN_RELATIVE),
        load_challenger_replacement_v3_machine_evidence(
            root / _MACHINE_RELATIVE
        ),
        load_challenger_replacement_v3_owner_attestation(
            root / _ATTESTATION_RELATIVE
        ),
    )
    if replayed_record != record:
        raise V3SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_V3_PRECONDITION_CHANGED"
        )
    _require_pre_start_state()
    publish_challenger_replacement_v3_supersession_record_bytes(
        _canonical_bytes(record)
    )
    _require_status(
        root,
        (
            "?? " + _ATTESTATION_RELATIVE.as_posix(),
            "?? " + _MACHINE_RELATIVE.as_posix(),
            "?? " + _RECORD_RELATIVE.as_posix(),
        ),
    )
    _require_empty_protocol_staging()
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit(2)
    return {
        "collect-machine-evidence": _collect_command,
        "record-owner-attestation": _attestation_command,
        "assemble-record": _assemble_command,
    }[sys.argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main())
