"""Receipt-first controlled decommission of the failed Challenger service."""

import hashlib
import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_cohort_failure import (
    ChallengerCohortFailureError,
    _read_receipt,
    _snapshot,
    _stored_failed_service_valid,
    _trusted_sources,
    _validate_output_disjoint,
    _validate_output_root,
    load_challenger_cohort_failure_receipt,
)
from .challenger_launchd_install import (
    LaunchctlResult,
    _command_evidence,
    _command_evidence_valid,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact


_OLD_SERVICE = "gui/501/local.crypto-quant.challenger-forward"
_OLD_LABEL = "local.crypto-quant.challenger-forward"
_MAINTENANCE_LABEL = (
    "local.crypto-quant.challenger-cohort-evidence-maintenance"
)
_PRINT_ARGV = ("/bin/launchctl", "print", _OLD_SERVICE)
_DOMAIN_PRINT_ARGV = ("/bin/launchctl", "print", "gui/501")
_BOOTOUT_ARGV = ("/bin/launchctl", "bootout", _OLD_SERVICE)
_NOT_FOUND_STDERR = (
    b'Bad request.\nCould not find service '
    b'"local.crypto-quant.challenger-forward" '
    b'in domain for user gui: 501\n'
)
_OUTPUT_DIRECTORY = "challenger-cohort-decommission-receipts"
_SCHEMA = "challenger-cohort-decommission-receipt-v1.schema.json"
_MAX_COMMAND_BYTES = 4 * 1024 * 1024
_MAX_INPUT_BYTES = 64 * 1024 * 1024


class ChallengerCohortDecommissionError(ValueError):
    """A decommission preflight, operation, or receipt failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@dataclass(frozen=True)
class DecommissionCommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _default_command_runner(
    argv: Sequence[str],
) -> DecommissionCommandResult:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
            shell=False,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_COMMAND_FAILED"
        ) from error
    return DecommissionCommandResult(
        completed.returncode, completed.stdout, completed.stderr
    )


def _run(runner, argv: Tuple[str, ...]) -> DecommissionCommandResult:
    try:
        result = runner(argv)
        if (
            not isinstance(result, DecommissionCommandResult)
            or isinstance(result.returncode, bool)
            or not isinstance(result.returncode, int)
            or not isinstance(result.stdout, bytes)
            or not isinstance(result.stderr, bytes)
            or len(result.stdout) > _MAX_COMMAND_BYTES
            or len(result.stderr) > _MAX_COMMAND_BYTES
        ):
            raise ValueError
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
        return result
    except ChallengerCohortDecommissionError:
        raise
    except Exception as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_COMMAND_FAILED"
        ) from error


def _evidence(
    argv: Tuple[str, ...], result: DecommissionCommandResult
) -> Mapping[str, Any]:
    return _command_evidence(
        argv, LaunchctlResult(result.returncode, result.stdout, result.stderr)
    )


def _file_evidence(path: Path) -> Mapping[str, Any]:
    try:
        selected = Path(path).expanduser()
        before = selected.lstat()
        if (
            not selected.is_absolute()
            or selected.is_symlink()
            or selected.resolve(strict=True) != selected.absolute()
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAX_INPUT_BYTES
        ):
            raise ValueError
        body = selected.read_bytes()
        after = selected.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        ) or len(body) != before.st_size:
            raise ValueError
        return {
            "path": str(selected),
            "device": after.st_dev,
            "inode": after.st_ino,
            "owner_uid": after.st_uid,
            "mode_octal": f"{stat.S_IMODE(after.st_mode):04o}",
            "link_count": after.st_nlink,
            "size_bytes": len(body),
            "mtime_ns_decimal": str(after.st_mtime_ns),
            "sha256": hashlib.sha256(body).hexdigest(),
        }
    except Exception as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_SOURCE_INVALID"
        ) from error


def _protected_snapshot(
    *,
    paths: Mapping[str, Path],
    failure_receipt_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    return {
        "runtime": _snapshot(paths),
        "trusted_files": {
            "failure_receipt": _file_evidence(failure_receipt_path),
            "cohort_plan": _file_evidence(cohort_plan_path),
            "evaluation_plan": _file_evidence(evaluation_plan_path),
            "install_receipt": _file_evidence(install_receipt_path),
            "contract": _file_evidence(contract_path),
            "plist": _file_evidence(plist_path),
        },
    }


def _domain_labels(result: DecommissionCommandResult) -> Tuple[str, ...]:
    if result.returncode != 0 or result.stderr != b"":
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_REPLACEMENT_PRESENT"
        )
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_REPLACEMENT_PRESENT"
        ) from error
    return tuple(
        sorted(
            set(
                re.findall(
                    r"local\.crypto-quant\.[A-Za-z0-9._-]+", text
                )
            )
        )
    )


def _domain_is_clear(result: DecommissionCommandResult) -> bool:
    try:
        labels = set(_domain_labels(result))
    except ChallengerCohortDecommissionError:
        return False
    allowed = {_OLD_LABEL, _MAINTENANCE_LABEL}
    return labels <= allowed and not any(
        label.startswith("local.crypto-quant.system-paper")
        for label in labels
    )


def _domain_evidence(
    result: DecommissionCommandResult,
) -> Mapping[str, Any]:
    labels = list(_domain_labels(result))
    disallowed = [
        label
        for label in labels
        if label not in {_OLD_LABEL, _MAINTENANCE_LABEL}
        or label.startswith("local.crypto-quant.system-paper")
    ]
    evidence: Dict[str, Any] = {
        "argv": list(_DOMAIN_PRINT_ARGV),
        "return_code": result.returncode,
        "stdout_size_bytes": len(result.stdout),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_size_bytes": len(result.stderr),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "crypto_quant_labels": labels,
        "disallowed_labels": disallowed,
        "raw_stdout_persisted": False,
        "command_evidence_hash": "0" * 64,
    }
    evidence["command_evidence_hash"] = artifact_self_hash(
        evidence, "command_evidence_hash"
    )
    return evidence


def _not_found(result: DecommissionCommandResult) -> bool:
    return (
        result.returncode == 113
        and result.stdout == b""
        and result.stderr == _NOT_FOUND_STDERR
    )


def _observed_at(clock) -> str:
    value = (clock or (
        lambda: utc_datetime(datetime.now(timezone.utc))
    ))()
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value.endswith("Z"):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        converted = parsed.astimezone(timezone.utc)
        if converted.microsecond % 1000:
            raise ValueError
        rendered = utc_datetime(converted)
        if isinstance(value, str) and value != rendered:
            raise ValueError
        return rendered
    except (TypeError, ValueError) as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_TIME_INVALID"
        ) from error


def challenger_cohort_decommission_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "failure_receipt_file_sha256": receipt["failure_receipt"][
            "file_sha256"
        ],
        "bootout_command_hash": receipt["commands"]["bootout"][
            "command_evidence_hash"
        ],
        "after_print_hash": receipt["commands"]["after_print"][
            "command_evidence_hash"
        ],
        "observed_at": receipt["observed_at"],
    }


def _receipt_path(output_root: Path, receipt_id: str) -> Path:
    return (
        _validate_output_root(output_root)
        / _OUTPUT_DIRECTORY
        / f"{receipt_id}.json"
    )


def decommission_failed_challenger_cohort(
    *,
    failure_receipt_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    failure_output_root: Path,
    clock=None,
    _command_runner=None,
) -> Mapping[str, Any]:
    observed_at = _observed_at(clock)
    try:
        output_root = _validate_output_root(Path(failure_output_root))
        failure_receipt = load_challenger_cohort_failure_receipt(
            receipt_path=Path(failure_receipt_path),
            cohort_plan_path=Path(cohort_plan_path),
            evaluation_plan_path=Path(evaluation_plan_path),
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        if install_receipt["service"] != _OLD_SERVICE:
            raise ValueError
        _validate_output_disjoint(output_root, paths)
        snapshot_arguments = {
            "paths": paths,
            "failure_receipt_path": Path(failure_receipt_path),
            "cohort_plan_path": Path(cohort_plan_path),
            "evaluation_plan_path": Path(evaluation_plan_path),
            "install_receipt_path": Path(install_receipt_path),
            "contract_path": Path(contract_path),
            "plist_path": Path(plist_path),
        }
        before = _protected_snapshot(**snapshot_arguments)
        if before["runtime"] != failure_receipt["evidence_after"]:
            raise ValueError
    except Exception as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID"
        ) from error

    runner = _command_runner or _default_command_runner
    before_result = _run(runner, _PRINT_ARGV)
    before_evidence = _evidence(_PRINT_ARGV, before_result)
    if not _stored_failed_service_valid(
        before_evidence,
        launchd_runs=failure_receipt["launchd_runs_observed"],
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID"
        )
    domain_result = _run(runner, _DOMAIN_PRINT_ARGV)
    if not _domain_is_clear(domain_result):
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_REPLACEMENT_PRESENT"
        )
    domain_evidence = _domain_evidence(domain_result)
    immediately_before = _protected_snapshot(**snapshot_arguments)
    if immediately_before != before:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_SOURCE_MUTATED"
        )

    bootout_result = _run(runner, _BOOTOUT_ARGV)
    bootout_evidence = _evidence(_BOOTOUT_ARGV, bootout_result)
    if (
        bootout_result.returncode != 0
        or bootout_result.stdout != b""
        or bootout_result.stderr != b""
    ):
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_BOOTOUT_FAILED"
        )
    after_result = _run(runner, _PRINT_ARGV)
    after_evidence = _evidence(_PRINT_ARGV, after_result)
    if not _not_found(after_result):
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_POSTCONDITION_INVALID"
        )
    after = _protected_snapshot(**snapshot_arguments)
    if after != before:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_SOURCE_MUTATED"
        )

    failure_body = Path(failure_receipt_path).read_bytes()
    receipt: Dict[str, Any] = {
        "schema_version": "challenger-cohort-decommission-receipt-v1",
        "receipt_id": "",
        "receipt_hash": "0" * 64,
        "observation_status": "FAILED_COHORT_DECOMMISSIONED_VERIFIED",
        "observed_at": observed_at,
        "failure_receipt": {
            "path": str(Path(failure_receipt_path).resolve(strict=True)),
            "receipt_id": failure_receipt["receipt_id"],
            "receipt_hash": failure_receipt["receipt_hash"],
            "file_sha256": hashlib.sha256(failure_body).hexdigest(),
            "size_bytes": len(failure_body),
        },
        "sources": failure_receipt["sources"],
        "service": {
            "identity": _OLD_SERVICE,
            "label": _OLD_LABEL,
            "state_before": "NOT_RUNNING_FAILED",
            "state_after": "NOT_LOADED",
        },
        "commands": {
            "before_print": before_evidence,
            "domain_print": domain_evidence,
            "bootout": bootout_evidence,
            "after_print": after_evidence,
        },
        "preserved_evidence_before": before,
        "preserved_evidence_after": after,
        "security_boundary": {
            "launchctl_command_count": 4,
            "launchctl_print_count": 3,
            "bootout_count": 1,
            "shell_invoked": False,
            "delete_count": 0,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "maintenance_invocation_count": 0,
        },
        "eligibility": {
            "old_cohort": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
            "service": "DECOMMISSIONED",
            "replacement_cohort": "NOT_STARTED",
            "system_paper": "NOT_STARTED",
            "canary": "NOT_AUTHORIZED",
        },
        "warnings": [
            "NO_BACKFILL",
            "PRESERVE_ALL_FAILURE_EVIDENCE",
            "NO_PROFITABILITY_CLAIM",
            "NOT_CANARY_AUTHORIZATION",
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_cohort_decommission_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_cohort_decommission_receipt_hash(
        receipt
    )
    body = canonical_json(receipt).encode("utf-8")
    path = _receipt_path(output_root, receipt["receipt_id"])
    try:
        _publish_exact(path, body)
        os.chmod(path, 0o600)
    except Exception as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_PUBLISH_FAILED"
        ) from error
    loaded = load_challenger_cohort_decommission_receipt(
        receipt_path=path,
        failure_receipt_path=Path(failure_receipt_path),
        cohort_plan_path=Path(cohort_plan_path),
        evaluation_plan_path=Path(evaluation_plan_path),
        install_receipt_path=Path(install_receipt_path),
        contract_path=Path(contract_path),
        plist_path=Path(plist_path),
    )
    return {
        "status": loaded["observation_status"],
        "receipt_id": loaded["receipt_id"],
        "receipt_hash": loaded["receipt_hash"],
        "receipt_path": str(path),
        "receipt_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bootout_count": 1,
        "launchctl_command_count": 4,
        "market_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
        "maintenance_invocation_count": 0,
    }


def _stored_domain_valid(evidence: Mapping[str, Any]) -> bool:
    try:
        labels = evidence["crypto_quant_labels"]
        return (
            set(evidence)
            == {
                "argv",
                "return_code",
                "stdout_size_bytes",
                "stdout_sha256",
                "stderr_size_bytes",
                "stderr_sha256",
                "crypto_quant_labels",
                "disallowed_labels",
                "raw_stdout_persisted",
                "command_evidence_hash",
            }
            and evidence["argv"] == list(_DOMAIN_PRINT_ARGV)
            and evidence["return_code"] == 0
            and isinstance(evidence["stdout_size_bytes"], int)
            and evidence["stdout_size_bytes"] > 0
            and re.fullmatch(r"[0-9a-f]{64}", evidence["stdout_sha256"])
            is not None
            and evidence["stderr_size_bytes"] == 0
            and evidence["stderr_sha256"]
            == hashlib.sha256(b"").hexdigest()
            and isinstance(labels, list)
            and labels == sorted(set(labels))
            and set(labels) <= {_OLD_LABEL, _MAINTENANCE_LABEL}
            and evidence["disallowed_labels"] == []
            and evidence["raw_stdout_persisted"] is False
            and evidence["command_evidence_hash"]
            == artifact_self_hash(evidence, "command_evidence_hash")
        )
    except (KeyError, TypeError, ValueError):
        return False


def load_challenger_cohort_decommission_receipt(
    *,
    receipt_path: Path,
    failure_receipt_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    try:
        receipt, body = _read_receipt(Path(receipt_path))
        failure_receipt = load_challenger_cohort_failure_receipt(
            receipt_path=Path(failure_receipt_path),
            cohort_plan_path=Path(cohort_plan_path),
            evaluation_plan_path=Path(evaluation_plan_path),
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        current = _protected_snapshot(
            paths=paths,
            failure_receipt_path=Path(failure_receipt_path),
            cohort_plan_path=Path(cohort_plan_path),
            evaluation_plan_path=Path(evaluation_plan_path),
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        failure_body = Path(failure_receipt_path).read_bytes()
        before_print = receipt["commands"]["before_print"]
        after_print = receipt["commands"]["after_print"]
        after_result = DecommissionCommandResult(
            after_print["return_code"],
            after_print["stdout_utf8"].encode("utf-8"),
            after_print["stderr_utf8"].encode("utf-8"),
        )
        valid = (
            body == canonical_json(receipt).encode("utf-8")
            and not tuple(_validator().iter_errors(receipt))
            and receipt.get("schema_version")
            == "challenger-cohort-decommission-receipt-v1"
            and receipt.get("receipt_hash")
            == challenger_cohort_decommission_receipt_hash(receipt)
            and receipt.get("receipt_id")
            == stable_id(
                "challenger_cohort_decommission_receipt", _identity(receipt)
            )
            and receipt.get("observation_status")
            == "FAILED_COHORT_DECOMMISSIONED_VERIFIED"
            and receipt["failure_receipt"]
            == {
                "path": str(Path(failure_receipt_path).resolve(strict=True)),
                "receipt_id": failure_receipt["receipt_id"],
                "receipt_hash": failure_receipt["receipt_hash"],
                "file_sha256": hashlib.sha256(failure_body).hexdigest(),
                "size_bytes": len(failure_body),
            }
            and receipt["sources"] == failure_receipt["sources"]
            and receipt["service"]
            == {
                "identity": _OLD_SERVICE,
                "label": _OLD_LABEL,
                "state_before": "NOT_RUNNING_FAILED",
                "state_after": "NOT_LOADED",
            }
            and _stored_failed_service_valid(
                before_print,
                launchd_runs=failure_receipt["launchd_runs_observed"],
                contract=contract,
                install_receipt=install_receipt,
                paths=paths,
            )
            and _stored_domain_valid(receipt["commands"]["domain_print"])
            and _command_evidence_valid(
                receipt["commands"]["bootout"], _BOOTOUT_ARGV
            )
            and receipt["commands"]["bootout"]["return_code"] == 0
            and receipt["commands"]["bootout"]["stdout_utf8"] == ""
            and receipt["commands"]["bootout"]["stderr_utf8"] == ""
            and _command_evidence_valid(after_print, _PRINT_ARGV)
            and _not_found(after_result)
            and receipt["preserved_evidence_before"]
            == receipt["preserved_evidence_after"]
            and current == receipt["preserved_evidence_after"]
            and receipt["eligibility"]
            == {
                "old_cohort": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
                "service": "DECOMMISSIONED",
                "replacement_cohort": "NOT_STARTED",
                "system_paper": "NOT_STARTED",
                "canary": "NOT_AUTHORIZED",
            }
            and receipt["security_boundary"]
            == {
                "launchctl_command_count": 4,
                "launchctl_print_count": 3,
                "bootout_count": 1,
                "shell_invoked": False,
                "delete_count": 0,
                "market_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "runner_invocation_count": 0,
                "maintenance_invocation_count": 0,
            }
        )
    except Exception as error:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_RECEIPT_INVALID"
        ) from error
    if not valid:
        raise ChallengerCohortDecommissionError(
            "CHALLENGER_COHORT_DECOMMISSION_RECEIPT_INVALID"
        )
    return receipt
