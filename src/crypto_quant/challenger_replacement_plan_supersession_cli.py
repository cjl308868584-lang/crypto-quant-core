"""Parameterless fixed-path commands for replacement plan supersession."""

import base64
import copy
import hashlib
import os
import subprocess
import sys
import time
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .canonical import canonical_json
from .challenger_replacement_plan_supersession import (
    ACCOUNTABLE_OWNER_DECLARATION,
    REAL_EVIDENCE_QUALIFICATION,
    _PREVIOUS_PLAN,
    _artifact_id,
    _machine_binding,
    _superseding_plan_binding,
    build_challenger_replacement_plan_supersession_record,
    load_challenger_replacement_supersession_machine_evidence,
    supersession_artifact_hash,
)
from .challenger_replacement_plan_v2 import (
    load_challenger_replacement_plan_v2,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _read_owner_controlled_regular_file,
)
from .challenger_replacement_supersession_publish import (
    _snapshot_fixed_artifact,
    publish_challenger_replacement_machine_evidence_bytes,
    publish_challenger_replacement_owner_attestation_bytes,
    publish_challenger_replacement_supersession_record_bytes,
    _require_empty_protocol_staging,
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
_ACKNOWLEDGEMENT = "I_SIGN_AND_ACCEPT_ACCOUNTABILITY_FOR_THE_EXACT_DECLARATION"
_V062_TAG_OBJECT = "b33c0cf58a954f548f76792f0b7cf989dcf0900c"
_V063_TAG_OBJECT = "a142927d96c4e6d52df22f79e929e679a219e82e"
_V062_PEELED = "e0a9b3eb6a3f385ea259722e6613df8708e8fe5a"
_V063_PEELED = "df91e19240df14839125608422489adf3b902e76"
_V062_PLAN_SHA = "d450d1e9f8dc422eb5a93beb8a5ffbb1746a4a6d1facb3c5a20a76f4bd527734"
_PROCESS_ENV = {
    "HOME": "/var/empty",
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}

_MACHINE_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-supersession-machine-evidence-v0.64.0.json"
)
_ATTESTATION_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-owner-attestation-v0.64.0.json"
)
_RECORD_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-supersession-v0.64.0.json"
)
_PLAN_RELATIVE = Path(
    "artifacts/challenger-replacement/"
    "challenger-replacement-plan-v0.64.0.json"
)


class SupersessionCommandError(RuntimeError):
    """A fixed supersession ceremony command failed closed."""


def _repository_root() -> Path:
    module_path = Path(__file__)
    if not module_path.is_absolute():
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        )
    current = Path(module_path.anchor)
    try:
        for part in module_path.parts[1:]:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise SupersessionCommandError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
                )
    except OSError as error:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        ) from error
    return module_path.parents[2]


def _git_argv(reviewed_repo_root: Path) -> Tuple[Tuple[str, ...], ...]:
    root = str(reviewed_repo_root)
    return (
        ("/usr/bin/git", "-C", root, "rev-parse", "v0.62.0"),
        ("/usr/bin/git", "-C", root, "cat-file", "-t", "v0.62.0"),
        ("/usr/bin/git", "-C", root, "rev-parse", "v0.62.0^{}"),
        ("/usr/bin/git", "-C", root, "rev-parse", "v0.63.0"),
        ("/usr/bin/git", "-C", root, "cat-file", "-t", "v0.63.0"),
        ("/usr/bin/git", "-C", root, "rev-parse", "v0.63.0^{}"),
        ("/usr/bin/git", "-C", root, "rev-parse", "HEAD"),
        (
            "/usr/bin/git", "-C", root, "merge-base", "--is-ancestor",
            "v0.63.0", "HEAD",
        ),
        (
            "/usr/bin/git", "-C", root, "status", "--porcelain=v1",
            "--untracked-files=all",
        ),
        (
            "/usr/bin/git", "-C", root, "status", "--porcelain=v1",
            "--untracked-files=all", "--ignored=matching", "--",
            "artifacts/challenger-replacement/",
        ),
        (
            "/usr/bin/git", "-C", root, "show",
            "v0.62.0:artifacts/challenger-replacement/"
            "challenger-replacement-plan-v0.62.0.json",
        ),
        (
            "/usr/bin/git", "-C", root, "log", "--all", "--full-history",
            "--format=%H", "--", "artifacts/challenger-replacement/",
            "docs/adr/0062-replacement-challenger-preregistration-isolation.md",
            "docs/implementation-status-v0.62.0.md",
        ),
    )


def _validate_reviewed_repo_root(root: Path) -> None:
    candidate = Path(root)
    if not candidate.is_absolute() or candidate.resolve() != candidate:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        )
    try:
        marker = (candidate / ".git").lstat()
    except OSError as error:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        ) from error
    if (
        marker.st_uid != os.geteuid()
        or stat.S_ISLNK(marker.st_mode)
        or not (stat.S_ISREG(marker.st_mode) or stat.S_ISDIR(marker.st_mode))
    ):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        )
    if stat.S_ISDIR(marker.st_mode):
        if stat.S_IMODE(marker.st_mode) & 0o022:
            raise SupersessionCommandError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
            )
        return
    try:
        marker_bytes = _read_owner_controlled_regular_file(candidate / ".git")
        prefix = b"gitdir: "
        if (
            not marker_bytes.startswith(prefix)
            or marker_bytes.count(b"\n") != 1
            or not marker_bytes.endswith(b"\n")
        ):
            raise ValueError("invalid gitdir marker")
        raw_target = marker_bytes[len(prefix):-1].decode("utf-8")
        target = Path(raw_target)
        if not target.is_absolute():
            target = candidate / target
        target = target.resolve(strict=True)
        target_stat = target.lstat()
        if (
            not stat.S_ISDIR(target_stat.st_mode)
            or target_stat.st_uid != os.geteuid()
            or stat.S_IMODE(target_stat.st_mode) & 0o022
        ):
            raise ValueError("invalid gitdir target")
        reciprocal = _read_owner_controlled_regular_file(target / "gitdir")
        if reciprocal != (str(candidate / ".git") + "\n").encode("utf-8"):
            raise ValueError("gitdir does not point back to reviewed root")
    except (
        ChallengerReplacementPlanError,
        OSError,
        UnicodeError,
        ValueError,
    ) as error:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_REPOSITORY_INVALID"
        ) from error


def _timestamp() -> str:
    value = datetime.now(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _transcript(name: str, argv: Sequence[str], result: Any) -> Dict[str, Any]:
    stdout = bytes(result.stdout)
    stderr = bytes(result.stderr)
    return {
        "name": name,
        "argv": list(argv),
        "exit_code": int(result.returncode),
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }


def _run(argv: Sequence[str]) -> Any:
    return subprocess.run(
        tuple(argv),
        capture_output=True,
        check=False,
        env=copy.deepcopy(_PROCESS_ENV),
    )


def _run_git_observations(root: Path) -> Tuple[Tuple[Any, ...], Tuple[Dict[str, Any], ...]]:
    _validate_reviewed_repo_root(root)
    results = tuple(_run(argv) for argv in _git_argv(root))
    names = (
        "v0_62_tag_object", "v0_62_tag_type", "v0_62_peeled_commit",
        "v0_63_tag_object", "v0_63_tag_type", "v0_63_peeled_commit",
        "candidate_head", "v0_63_ancestor_of_candidate", "candidate_status",
        "artifact_namespace_status", "v0_62_plan_bytes", "relevant_git_history",
    )
    return results, tuple(
        _transcript(name, argv, result)
        for name, argv, result in zip(names, _git_argv(root), results)
    )


def _stdout_line(result: Any) -> str:
    try:
        return bytes(result.stdout).decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_INVALID"
        ) from error


def _validate_git_collection(
    results: Sequence[Any], *, expected_status: Tuple[str, ...] = ()
) -> None:
    if len(results) != 12:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_INVALID"
        )
    if any(result.returncode != 0 for result in results):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_INVALID"
        )
    if any(bytes(result.stderr) != b"" for result in results):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_INVALID"
        )
    fixed_stdout = {
        0: (_V062_TAG_OBJECT + "\n").encode("ascii"),
        1: b"tag\n",
        2: (_V062_PEELED + "\n").encode("ascii"),
        3: (_V063_TAG_OBJECT + "\n").encode("ascii"),
        4: b"tag\n",
        5: (_V063_PEELED + "\n").encode("ascii"),
        7: b"",
    }
    if any(bytes(results[index].stdout) != expected for index, expected in fixed_stdout.items()):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_INVALID"
        )
    if _stdout_line(results[1]) != "tag" or _stdout_line(results[4]) != "tag":
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_TAG_INVALID"
        )
    if (
        _stdout_line(results[0]) != _V062_TAG_OBJECT
        or _stdout_line(results[3]) != _V063_TAG_OBJECT
    ):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_TAG_IDENTITY_INVALID"
        )
    if _stdout_line(results[2]) != _V062_PEELED or _stdout_line(results[5]) != _V063_PEELED:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_RELEASE_IDENTITY_INVALID"
        )
    head = _stdout_line(results[6])
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_HEAD_INVALID"
        )
    expected_raw_status = b"".join(
        (line + "\n").encode("utf-8") for line in sorted(expected_status)
    )
    if any(bytes(results[index].stdout) != expected_raw_status for index in (8, 9)):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_CANDIDATE_STATE_INVALID"
        )
    if hashlib.sha256(bytes(results[10].stdout)).hexdigest() != _V062_PLAN_SHA:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_V062_PLAN_INVALID"
        )
    try:
        history = bytes(results[11].stdout).decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_HISTORY_INVALID"
        ) from error
    if (
        not history
        or _V062_PEELED not in history
        or len(history) != len(set(history))
        or any(
            len(value) != 40
            or any(character not in "0123456789abcdef" for character in value)
            for value in history
        )
    ):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_GIT_HISTORY_INVALID"
        )


def _require_absent(path: Path, reason: str) -> None:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError as error:
        raise SupersessionCommandError(reason) from error
    raise SupersessionCommandError(reason)


def _collect_machine_evidence() -> Dict[str, Any]:
    if os.geteuid() != 501:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_UID_INVALID"
        )
    _require_absent(_RUNTIME_ROOT, "CHALLENGER_REPLACEMENT_RUNTIME_ROOT_PRESENT")
    _require_absent(_PLIST, "CHALLENGER_REPLACEMENT_PLIST_PRESENT")
    launch_argv = ("/bin/launchctl", "print", _SERVICE)
    launch = _run(launch_argv)
    expected_launch_error = (
        'Bad request.\nCould not find service "'
        + "local.crypto-quant.challenger-replacement-v1"
        + '" in domain for user gui: 501\n'
    ).encode("utf-8")
    if (
        launch.returncode != 113
        or bytes(launch.stdout) != b""
        or bytes(launch.stderr) != expected_launch_error
    ):
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_SERVICE_STATE_AMBIGUOUS"
        )
    root = _repository_root()
    results, transcripts = _run_git_observations(root)
    _validate_git_collection(results)
    git_history: Dict[str, Any] = {
        "v0_62_tag_type": "tag",
        "v0_62_peeled_commit": _V062_PEELED,
        "v0_62_plan_path": _PREVIOUS_PLAN["path"],
        "v0_62_plan_file_sha256": _PREVIOUS_PLAN["file_sha256"],
        "v0_62_plan_id": _PREVIOUS_PLAN["plan_id"],
        "v0_62_plan_hash": _PREVIOUS_PLAN["plan_hash"],
        "v0_63_tag_type": "tag",
        "v0_63_peeled_commit": _V063_PEELED,
        "candidate_head": _stdout_line(results[6]),
        "v0_63_ancestor_of_candidate": True,
        "candidate_status_porcelain_base64": "",
        "candidate_status_porcelain_sha256": hashlib.sha256(b"").hexdigest(),
        "transcripts": list(transcripts),
        "git_history_evidence_hash": "0" * 64,
    }
    git_history["git_history_evidence_hash"] = supersession_artifact_hash(
        git_history, "git_history_evidence_hash"
    )
    timezone_name = time.tzname[0] if time.tzname else "UNKNOWN"
    offset_seconds = int(datetime.now().astimezone().utcoffset().total_seconds())
    evidence: Dict[str, Any] = {
        "$schema": "./challenger-replacement-supersession-machine-evidence-v1.schema.json",
        "schema_version": "1.0.0",
        "evidence_id": "challenger_replacement_supersession_machine_evidence_" + "0" * 64,
        "evidence_hash": "0" * 64,
        "evidence_qualification": REAL_EVIDENCE_QUALIFICATION,
        "observed_at": _timestamp(),
        "system_timezone": f"{timezone_name};utc_offset_seconds={offset_seconds}",
        "effective_uid": 501,
        "observation": "NO_OBSERVABLE_REPLACEMENT_STATE_AT_COLLECTION",
        "service_identity": _SERVICE,
        "runtime_root": str(_RUNTIME_ROOT),
        "target_plist": str(_PLIST),
        "current_observations": {
            "runtime_root_lstat": "ENOENT",
            "target_plist_lstat": "ENOENT",
            "service_state": "NOT_LOADED",
            "start_receipt_root_state": "ABSENT_DERIVED_FROM_RUNTIME_ROOT_ABSENT",
            "start_receipt_count": 0,
            "state_event_root_state": "ABSENT_DERIVED_FROM_RUNTIME_ROOT_ABSENT",
            "state_event_count": 0,
            "canonical_event_count": 0,
        },
        "collector_actions": {
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_count": 0,
        },
        "launchctl_transcript": _transcript(
            "replacement_service_state", launch_argv, launch
        ),
        "git_history": git_history,
    }
    evidence["evidence_id"] = _artifact_id(
        evidence,
        id_field="evidence_id",
        hash_field="evidence_hash",
        prefix="challenger_replacement_supersession_machine_evidence",
    )
    evidence["evidence_hash"] = supersession_artifact_hash(
        evidence, "evidence_hash"
    )
    return evidence


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return canonical_json(value).encode("utf-8") + b"\n"


def _final_snapshot(relative_path: Path) -> Dict[str, Any]:
    body, value = _snapshot_fixed_artifact(relative_path.name)
    return {
        "path": relative_path.as_posix(),
        "file_sha256": hashlib.sha256(body).hexdigest(),
        "device_decimal": str(value.st_dev),
        "inode_decimal": str(value.st_ino),
        "mode_octal": format(stat.S_IMODE(value.st_mode), "04o"),
        "nlink": value.st_nlink,
        "size": value.st_size,
        "mtime_ns_decimal": str(value.st_mtime_ns),
        "ctime_ns_decimal": str(value.st_ctime_ns),
    }


def _capture_ceremony_precondition(
    *, state: str, expected_status: Tuple[str, ...], finals: Tuple[Path, ...]
) -> Tuple[Dict[str, Any], Tuple[Any, ...]]:
    root = _repository_root()
    results, transcripts = _run_git_observations(root)
    _validate_git_collection(results, expected_status=expected_status)
    _require_original_candidate_head(root, results)
    _require_empty_protocol_staging()
    precondition = {
        "state": state,
        "candidate_head": _stdout_line(results[6]),
        "head_transcript": copy.deepcopy(transcripts[6]),
        "status_transcript": copy.deepcopy(transcripts[8]),
        "allowlisted_finals": [
            _final_snapshot(path) for path in sorted(finals)
        ],
        "staging_inventory": [],
    }
    return precondition, results


def _require_original_candidate_head(
    root: Path, results: Sequence[Any]
) -> Dict[str, Any]:
    machine = load_challenger_replacement_supersession_machine_evidence(
        root / _MACHINE_RELATIVE
    )
    if _stdout_line(results[6]) != machine["git_history"]["candidate_head"]:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_HEAD_CHANGED"
        )
    return machine


def _collect_command() -> int:
    root = _repository_root()
    load_challenger_replacement_plan_v2(root / _PLAN_RELATIVE)
    _require_empty_protocol_staging()
    value = _collect_machine_evidence()
    publish_challenger_replacement_machine_evidence_bytes(_canonical_bytes(value))
    _capture_ceremony_precondition(
        state="C1_EVIDENCE_ONLY",
        expected_status=("?? " + _MACHINE_RELATIVE.as_posix(),),
        finals=(_MACHINE_RELATIVE,),
    )
    return 0


def _owner_attestation(
    signed_at: str, ceremony_precondition: Mapping[str, Any]
) -> Dict[str, Any]:
    root = _repository_root()
    plan_path = root / _PLAN_RELATIVE
    machine_path = root / _MACHINE_RELATIVE
    plan = load_challenger_replacement_plan_v2(plan_path)
    machine = load_challenger_replacement_supersession_machine_evidence(machine_path)
    value: Dict[str, Any] = {
        "$schema": "./challenger-replacement-owner-attestation-v1.schema.json",
        "schema_version": "1.0.0",
        "attestation_id": "challenger_replacement_owner_attestation_" + "0" * 64,
        "attestation_hash": "0" * 64,
        "evidence_qualification": REAL_EVIDENCE_QUALIFICATION,
        "attestation_type": "ACCOUNTABLE_OWNER_PRE_START_HISTORY_ATTESTATION_V1",
        "signed_at": signed_at,
        "signer_github_login": "cjl308868584-lang",
        "signer_os_username": "chenm4",
        "signer_uid": 501,
        "declaration": ACCOUNTABLE_OWNER_DECLARATION,
        "owner_acknowledgement": _ACKNOWLEDGEMENT,
        "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
        "superseding_plan": _superseding_plan_binding(plan_path, plan),
        "machine_evidence_binding": _machine_binding(machine_path, machine),
        "ceremony_precondition": copy.deepcopy(ceremony_precondition),
    }
    value["attestation_id"] = _artifact_id(
        value,
        id_field="attestation_id",
        hash_field="attestation_hash",
        prefix="challenger_replacement_owner_attestation",
    )
    value["attestation_hash"] = supersession_artifact_hash(
        value, "attestation_hash"
    )
    return value


def _attestation_command() -> int:
    root = _repository_root()
    expected_status = ("?? " + _MACHINE_RELATIVE.as_posix(),)
    precondition, unused_results = _capture_ceremony_precondition(
        state="C1_EVIDENCE_ONLY",
        expected_status=expected_status,
        finals=(_MACHINE_RELATIVE,),
    )
    signed_at = _timestamp()
    value = _owner_attestation(signed_at, precondition)
    declaration_hash = hashlib.sha256(
        ACCOUNTABLE_OWNER_DECLARATION.encode("utf-8")
    ).hexdigest()
    binding_hash = hashlib.sha256(
        canonical_json(
            {
                "previous_plan": value["previous_plan"],
                "superseding_plan": value["superseding_plan"],
                "machine_evidence_binding": value["machine_evidence_binding"],
                "ceremony_precondition": value["ceremony_precondition"],
            }
        ).encode("utf-8")
    ).hexdigest()
    print("signed_at=" + value["signed_at"])
    print(ACCOUNTABLE_OWNER_DECLARATION)
    print("declaration_sha256=" + declaration_hash)
    print("binding_sha256=" + binding_hash)
    print(
        "ceremony_precondition_sha256="
        + hashlib.sha256(
            canonical_json(value["ceremony_precondition"]).encode("utf-8")
        ).hexdigest()
    )
    print("v0_62_plan_id=" + value["previous_plan"]["plan_id"])
    print("v0_62_plan_hash=" + value["previous_plan"]["plan_hash"])
    print("v0_62_plan_file_sha256=" + value["previous_plan"]["file_sha256"])
    print("v0_64_plan_id=" + value["superseding_plan"]["plan_id"])
    print("v0_64_plan_hash=" + value["superseding_plan"]["plan_hash"])
    print("v0_64_plan_file_sha256=" + value["superseding_plan"]["file_sha256"])
    print("machine_evidence_hash=" + value["machine_evidence_binding"]["evidence_hash"])
    print(
        "git_history_evidence_hash="
        + value["machine_evidence_binding"]["git_history_evidence_hash"]
    )
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_OWNER_INTERACTIVE_TTY_REQUIRED"
        )
    if input("acknowledgement: ") != _ACKNOWLEDGEMENT:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_OWNER_ACKNOWLEDGEMENT_REQUIRED"
        )
    replayed_precondition, unused_results = _capture_ceremony_precondition(
        state="C1_EVIDENCE_ONLY",
        expected_status=expected_status,
        finals=(_MACHINE_RELATIVE,),
    )
    if replayed_precondition != precondition:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PRECONDITION_CHANGED"
        )
    if _owner_attestation(signed_at, replayed_precondition) != value:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PRECONDITION_CHANGED"
        )
    publish_challenger_replacement_owner_attestation_bytes(_canonical_bytes(value))
    _capture_ceremony_precondition(
        state="C2_EVIDENCE_ATTESTATION_ONLY",
        expected_status=(
            "?? " + _ATTESTATION_RELATIVE.as_posix(),
            "?? " + _MACHINE_RELATIVE.as_posix(),
        ),
        finals=(_ATTESTATION_RELATIVE, _MACHINE_RELATIVE),
    )
    return 0


def _assemble_command() -> int:
    root = _repository_root()
    expected_status = (
            "?? " + _ATTESTATION_RELATIVE.as_posix(),
            "?? " + _MACHINE_RELATIVE.as_posix(),
    )
    precondition, unused_results = _capture_ceremony_precondition(
        state="C2_EVIDENCE_ATTESTATION_ONLY",
        expected_status=expected_status,
        finals=(_ATTESTATION_RELATIVE, _MACHINE_RELATIVE),
    )
    record = build_challenger_replacement_plan_supersession_record(
        v2_plan_path=root / _PLAN_RELATIVE,
        machine_evidence_path=root / _MACHINE_RELATIVE,
        owner_attestation_path=root / _ATTESTATION_RELATIVE,
        ceremony_precondition=precondition,
    )
    replayed_precondition, unused_results = _capture_ceremony_precondition(
        state="C2_EVIDENCE_ATTESTATION_ONLY",
        expected_status=expected_status,
        finals=(_ATTESTATION_RELATIVE, _MACHINE_RELATIVE),
    )
    if replayed_precondition != precondition:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PRECONDITION_CHANGED"
        )
    replayed_record = build_challenger_replacement_plan_supersession_record(
        v2_plan_path=root / _PLAN_RELATIVE,
        machine_evidence_path=root / _MACHINE_RELATIVE,
        owner_attestation_path=root / _ATTESTATION_RELATIVE,
        ceremony_precondition=replayed_precondition,
    )
    if replayed_record != record:
        raise SupersessionCommandError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PRECONDITION_CHANGED"
        )
    publish_challenger_replacement_supersession_record_bytes(
        _canonical_bytes(record)
    )
    _capture_ceremony_precondition(
        state="C3_THREE_FINALS_UNCOMMITTED",
        expected_status=(
            "?? " + _ATTESTATION_RELATIVE.as_posix(),
            "?? " + _MACHINE_RELATIVE.as_posix(),
            "?? " + _RECORD_RELATIVE.as_posix(),
        ),
        finals=(
            _ATTESTATION_RELATIVE,
            _MACHINE_RELATIVE,
            _RECORD_RELATIVE,
        ),
    )
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
