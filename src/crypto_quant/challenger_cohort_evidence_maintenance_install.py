"""Restricted installer for the cohort evidence maintenance LaunchAgent."""

import hashlib
import json
import os
import plistlib
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_cohort_evidence_maintenance_deployment import (
    ChallengerCohortEvidenceMaintenanceDeploymentError,
    load_challenger_cohort_evidence_maintenance_deployment,
)
from .challenger_cohort_evidence_maintenance_launchd import (
    ChallengerCohortEvidenceMaintenanceLaunchdError,
    load_challenger_cohort_evidence_maintenance_launchd_contract,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = (
    "challenger-cohort-evidence-maintenance-launchd-install-receipt-v1.schema.json"
)
_LABEL = "local.crypto-quant.challenger-cohort-evidence-maintenance"
_LAUNCHCTL = "/bin/launchctl"
_MAX_COMMAND_OUTPUT_BYTES = 1024 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_WARNINGS = (
    "INSTALLATION_DOES_NOT_PROVE_FIRST_NATURAL_SCHEDULE_RUN",
    "MAINTENANCE_NOT_INVOKED_BY_INSTALLER",
    "COHORT_COMPLETENESS_NOT_PROVEN",
    "NO_PROFITABILITY_CLAIM",
    "NO_SYSTEM_PAPER_OR_AI_ADVANTAGE_CLAIM",
)


class ChallengerCohortEvidenceMaintenanceInstallError(ValueError):
    """The maintenance LaunchAgent install transaction failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class MaintenanceLaunchctlResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TIME_INVALID"
        )
    return rendered


def _secure_file(path: Path, reason: str) -> Path:
    try:
        raw = Path(path).expanduser()
        if not raw.is_absolute() or raw.is_symlink():
            raise ValueError
        resolved = raw.resolve(strict=True)
        status = resolved.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size <= 0
        ):
            raise ValueError
        return resolved
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            reason
        ) from error


def _validate_result(result: object) -> None:
    if (
        not isinstance(result, MaintenanceLaunchctlResult)
        or isinstance(result.returncode, bool)
        or not isinstance(result.returncode, int)
        or not isinstance(result.stdout, bytes)
        or not isinstance(result.stderr, bytes)
        or len(result.stdout) > _MAX_COMMAND_OUTPUT_BYTES
        or len(result.stderr) > _MAX_COMMAND_OUTPUT_BYTES
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_COMMAND_RESULT_INVALID"
        )
    try:
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_COMMAND_RESULT_INVALID"
        ) from error


def _command_runner(
    argv: Sequence[str],
) -> MaintenanceLaunchctlResult:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env={
                "HOME": str(Path.home()),
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            },
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    result = MaintenanceLaunchctlResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    _validate_result(result)
    return result


def _command_evidence(
    argv: Sequence[str],
    result: MaintenanceLaunchctlResult,
) -> Dict[str, Any]:
    _validate_result(result)
    stdout_text = result.stdout.decode("utf-8")
    stderr_text = result.stderr.decode("utf-8")
    evidence = {
        "argv": list(argv),
        "return_code": result.returncode,
        "stdout_utf8": stdout_text,
        "stderr_utf8": stderr_text,
        "stdout_size_bytes": len(result.stdout),
        "stderr_size_bytes": len(result.stderr),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "command_evidence_hash": "0" * 64,
    }
    evidence["command_evidence_hash"] = artifact_self_hash(
        evidence, "command_evidence_hash"
    )
    return evidence


def _command_evidence_valid(
    evidence: Mapping[str, Any],
    expected_argv: Sequence[str],
) -> bool:
    try:
        stdout = evidence["stdout_utf8"].encode("utf-8")
        stderr = evidence["stderr_utf8"].encode("utf-8")
        return (
            evidence["argv"] == list(expected_argv)
            and evidence["stdout_size_bytes"] == len(stdout)
            and evidence["stderr_size_bytes"] == len(stderr)
            and evidence["stdout_sha256"]
            == hashlib.sha256(stdout).hexdigest()
            and evidence["stderr_sha256"]
            == hashlib.sha256(stderr).hexdigest()
            and evidence["command_evidence_hash"]
            == artifact_self_hash(evidence, "command_evidence_hash")
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _home_uid(
    *,
    home_directory: Optional[Path],
    uid: Optional[int],
) -> Tuple[Path, int]:
    selected_home = (
        Path.home() if home_directory is None else Path(home_directory)
    )
    selected_uid = os.getuid() if uid is None else uid
    if (
        not selected_home.is_absolute()
        or selected_home.is_symlink()
        or isinstance(selected_uid, bool)
        or not isinstance(selected_uid, int)
        or selected_uid <= 0
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_USER_INVALID"
        )
    return selected_home.resolve(), selected_uid


def _target(home: Path) -> Path:
    return (
        home
        / "Library"
        / "LaunchAgents"
        / f"{_LABEL}.plist"
    )


def _validate_parent(path: Path, uid: int) -> None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        status = path.parent.lstat()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_PARENT_INVALID"
        ) from error
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != uid
        or stat.S_IMODE(status.st_mode) & 0o022
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_PARENT_INVALID"
        )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_install(path: Path, data: bytes, uid: int) -> bool:
    if path.exists() or path.is_symlink():
        try:
            status = path.lstat()
            existing = path.read_bytes()
        except OSError as error:
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_CONFLICT"
            ) from error
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != uid
            or status.st_nlink != 1
            or existing != data
        ):
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_CONFLICT"
            )
        os.chmod(path, 0o600)
        return False
    descriptor, name = tempfile.mkstemp(
        prefix=".challenger-cohort-maintenance-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(name)
    installed = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_CONFLICT"
            ) from error
        installed = True
        temporary.unlink()
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
        return True
    finally:
        if temporary.exists():
            temporary.unlink()
        if installed:
            os.chmod(path, 0o600)


def _remove_new_target(path: Path) -> None:
    try:
        path.unlink()
        _fsync_directory(path.parent)
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_ROLLBACK_FAILED"
        ) from error


def _target_stat(path: Path, uid: int) -> Dict[str, Any]:
    try:
        status = path.lstat()
        body = path.read_bytes()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_INVALID"
        ) from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != uid
        or status.st_nlink != 1
        or stat.S_IMODE(status.st_mode) != 0o600
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_INVALID"
        )
    return {
        "device": status.st_dev,
        "inode": status.st_ino,
        "owner_uid": status.st_uid,
        "mode_octal": "0600",
        "link_count": status.st_nlink,
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _print_bindings_valid(
    output: bytes,
    *,
    contract: Mapping[str, Any],
    domain: str,
    target: Path,
) -> bool:
    try:
        text = output.decode("utf-8")
    except UnicodeDecodeError:
        return False
    required = (
        f"{domain}/{_LABEL}",
        _LABEL,
        str(target),
        contract["python_executable"],
        contract["repository_root"],
        "crypto_quant.challenger_cohort_evidence_maintenance_cli",
        *contract["program_arguments"][3:],
    )
    return all(value in text for value in required)


def _load_sources(
    *,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    _strategy_loader=None,
) -> Tuple[Path, Mapping[str, Any], Path, Path, Mapping[str, Any], bytes]:
    manifest_file = _secure_file(
        manifest_path,
        "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SOURCE_INVALID",
    )
    try:
        manifest = load_challenger_cohort_evidence_maintenance_deployment(
            manifest_path=manifest_file,
            trusted_source_attestation_hash=(
                trusted_source_attestation_hash
            ),
            trusted_candidate_attestation_hash=(
                trusted_candidate_attestation_hash
            ),
            _strategy_loader=_strategy_loader,
        )
        candidate = manifest["install_candidate"]
        contract_file = _secure_file(
            Path(candidate["contract_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SOURCE_INVALID",
        )
        plist_file = _secure_file(
            Path(candidate["plist_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SOURCE_INVALID",
        )
        contract = (
            load_challenger_cohort_evidence_maintenance_launchd_contract(
                contract_path=contract_file,
                plist_path=plist_file,
                trusted_attestation_hash=(
                    trusted_candidate_attestation_hash
                ),
                _strategy_loader=_strategy_loader,
            )
        )
        plist_bytes = plist_file.read_bytes()
    except (
        ChallengerCohortEvidenceMaintenanceDeploymentError,
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        KeyError,
        OSError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SOURCE_INVALID"
        ) from error
    if (
        contract.get("label") != _LABEL
        or contract.get("installation_status")
        != "NOT_INSTALLED_NO_EXTERNAL_RECEIPT"
        or contract.get("cadence", {}).get("run_at_load") is not False
        or contract.get("repository_root")
        != manifest["execution_snapshot"]["repository_root"]
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SOURCE_INVALID"
        )
    environment = {
        "HOME": str(Path.home()),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(
            Path(contract["repository_root"]) / "src"
        ),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    try:
        preflight = subprocess.run(
            [
                contract["python_executable"],
                "-c",
                (
                    "import jsonschema, crypto_quant, "
                    "crypto_quant."
                    "challenger_cohort_evidence_maintenance_cli"
                ),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PYTHON_PREFLIGHT_FAILED"
        ) from error
    if preflight.returncode != 0:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PYTHON_PREFLIGHT_FAILED"
        )
    return (
        manifest_file,
        manifest,
        contract_file,
        plist_file,
        contract,
        plist_bytes,
    )


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def maintenance_install_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _receipt_identity(
    *,
    manifest_hash: str,
    contract_hash: str,
    target_path: Path,
    target_stat: Mapping[str, Any],
    action: str,
    installed_at: str,
    verified_at: str,
    preflight: Mapping[str, Any],
    bootstrap: Optional[Mapping[str, Any]],
    verified: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "deployment_manifest_hash": manifest_hash,
        "candidate_contract_hash": contract_hash,
        "target_path": str(target_path),
        "target_device": target_stat["device"],
        "target_inode": target_stat["inode"],
        "install_action": action,
        "installed_at": installed_at,
        "verified_at": verified_at,
        "preflight_print_hash": preflight["command_evidence_hash"],
        "bootstrap_hash": (
            None
            if bootstrap is None
            else bootstrap["command_evidence_hash"]
        ),
        "verified_print_hash": verified["command_evidence_hash"],
    }


def maintenance_install_receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    target_path: Path,
    _strategy_loader=None,
) -> Tuple[str, ...]:
    if not isinstance(receipt, Mapping):
        return ("CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_SCHEMA_INVALID"
            )
        if receipt.get("receipt_hash") != maintenance_install_receipt_hash(
            receipt
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_HASH_MISMATCH"
            )
        (
            manifest_file,
            manifest,
            _contract_file,
            _plist_file,
            contract,
            plist_bytes,
        ) = _load_sources(
            manifest_path=manifest_path,
            trusted_source_attestation_hash=(
                trusted_source_attestation_hash
            ),
            trusted_candidate_attestation_hash=(
                trusted_candidate_attestation_hash
            ),
            _strategy_loader=_strategy_loader,
        )
        expected_deployment = {
            "manifest_path": str(manifest_file),
            "manifest_file_sha256": hashlib.sha256(
                manifest_file.read_bytes()
            ).hexdigest(),
            "manifest_id": manifest["manifest_id"],
            "manifest_hash": manifest["manifest_hash"],
        }
        if receipt["source_deployment"] != expected_deployment:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_DEPLOYMENT_MISMATCH"
            )
        expected_contract = {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": trusted_candidate_attestation_hash,
            "launchd_plist_sha256": hashlib.sha256(
                plist_bytes
            ).hexdigest(),
        }
        if receipt["source_contract"] != expected_contract:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_CONTRACT_MISMATCH"
            )
        expected_snapshot = {
            key: manifest["execution_snapshot"][key]
            for key in (
                "repository_root",
                "file_count",
                "total_bytes",
                "tree_hash",
            )
        }
        if receipt["execution_snapshot"] != expected_snapshot:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_SNAPSHOT_MISMATCH"
            )
        uid = receipt["target_stat"]["owner_uid"]
        domain = f"gui/{uid}"
        service = f"{domain}/{_LABEL}"
        target = Path(target_path).expanduser().resolve()
        if (
            receipt["domain"] != domain
            or receipt["service"] != service
            or receipt["target_path"] != str(target)
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_BINDING_MISMATCH"
            )
        actual_stat = _target_stat(target, uid)
        if receipt["target_stat"] != actual_stat:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_STAT_MISMATCH"
            )
        print_argv = (_LAUNCHCTL, "print", service)
        if not _command_evidence_valid(
            receipt["preflight_print"], print_argv
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PREFLIGHT_INVALID"
            )
        verified = receipt["verified_print"]
        if (
            not _command_evidence_valid(verified, print_argv)
            or verified["return_code"] != 0
            or not _print_bindings_valid(
                verified["stdout_utf8"].encode("utf-8"),
                contract=contract,
                domain=domain,
                target=target,
            )
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PRINT_INVALID"
            )
        action = receipt["install_action"]
        bootstrap = receipt["bootstrap_or_null"]
        bootstrap_argv = (
            _LAUNCHCTL,
            "bootstrap",
            domain,
            str(target),
        )
        if action == "ALREADY_INSTALLED_AND_LOADED":
            if bootstrap is not None:
                reasons.append(
                    "CHALLENGER_COHORT_MAINTENANCE_INSTALL_BOOTSTRAP_INVALID"
                )
        elif (
            not isinstance(bootstrap, Mapping)
            or not _command_evidence_valid(bootstrap, bootstrap_argv)
            or bootstrap["return_code"] != 0
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_BOOTSTRAP_INVALID"
            )
        identity = _receipt_identity(
            manifest_hash=manifest["manifest_hash"],
            contract_hash=contract["contract_hash"],
            target_path=target,
            target_stat=actual_stat,
            action=action,
            installed_at=receipt["installed_at"],
            verified_at=receipt["verified_at"],
            preflight=receipt["preflight_print"],
            bootstrap=bootstrap,
            verified=verified,
        )
        if receipt.get("receipt_id") != stable_id(
            "challenger_cohort_evidence_maintenance_install_receipt",
            identity,
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_ID_MISMATCH"
            )
    except (
        ChallengerCohortEvidenceMaintenanceInstallError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_REPLAY_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _publish_receipt(
    receipt: Mapping[str, Any],
    output_root: Path,
) -> Path:
    raw = Path(output_root).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_OUTPUT_INVALID"
        )
    try:
        directory = raw.resolve() / "maintenance-install-receipts"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        status = directory.lstat()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_OUTPUT_INVALID"
        ) from error
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o700
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_OUTPUT_INVALID"
        )
    path = directory / f"{receipt['receipt_id']}.json"
    try:
        _publish_exact(path, canonical_json(receipt).encode("utf-8"))
    except ValueError as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_CONFLICT"
        ) from error
    os.chmod(path, 0o600)
    return path


def install_challenger_cohort_evidence_maintenance_launchd(
    *,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    receipt_output_root: Path,
    clock=None,
    _home_directory: Optional[Path] = None,
    _uid: Optional[int] = None,
    _launchctl_runner=None,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    (
        manifest_file,
        manifest,
        _contract_file,
        _plist_file,
        contract,
        plist_bytes,
    ) = _load_sources(
        manifest_path=manifest_path,
        trusted_source_attestation_hash=trusted_source_attestation_hash,
        trusted_candidate_attestation_hash=(
            trusted_candidate_attestation_hash
        ),
        _strategy_loader=_strategy_loader,
    )
    home, uid = _home_uid(
        home_directory=_home_directory,
        uid=_uid,
    )
    target = _target(home)
    _validate_parent(target, uid)
    domain = f"gui/{uid}"
    service = f"{domain}/{_LABEL}"
    runner = _launchctl_runner or _command_runner
    print_argv = (_LAUNCHCTL, "print", service)
    try:
        preflight_result = runner(print_argv)
        _validate_result(preflight_result)
    except ChallengerCohortEvidenceMaintenanceInstallError:
        raise
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    preflight = _command_evidence(print_argv, preflight_result)
    if preflight_result.returncode not in (0, 113):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PREFLIGHT_FAILED"
        )
    exists = target.exists() or target.is_symlink()
    if preflight_result.returncode == 0:
        if (
            not exists
            or target.read_bytes() != plist_bytes
            or not _print_bindings_valid(
                preflight_result.stdout,
                contract=contract,
                domain=domain,
                target=target,
            )
        ):
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_EXISTING_SERVICE_CONFLICT"
            )
        created = False
        action = "ALREADY_INSTALLED_AND_LOADED"
        bootstrap_evidence = None
    else:
        created = _atomic_install(target, plist_bytes, uid)
        action = (
            "INSTALLED_AND_BOOTSTRAPPED"
            if created
            else "EXISTING_FILE_BOOTSTRAPPED"
        )
        bootstrap_argv = (
            _LAUNCHCTL,
            "bootstrap",
            domain,
            str(target),
        )
        try:
            bootstrap_result = runner(bootstrap_argv)
            _validate_result(bootstrap_result)
        except Exception as error:
            if created:
                _remove_new_target(target)
            if isinstance(
                error,
                ChallengerCohortEvidenceMaintenanceInstallError,
            ):
                raise
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_LAUNCHCTL_FAILED"
            ) from error
        bootstrap_evidence = _command_evidence(
            bootstrap_argv, bootstrap_result
        )
        if bootstrap_result.returncode != 0:
            if created:
                _remove_new_target(target)
            raise ChallengerCohortEvidenceMaintenanceInstallError(
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_BOOTSTRAP_FAILED"
            )
    installed_at = _utc(
        (
            clock
            or (
                lambda: utc_datetime(
                    datetime.now(timezone.utc)
                )
            )
        )()
    )
    try:
        verified_result = runner(print_argv)
        _validate_result(verified_result)
    except Exception as error:
        if isinstance(
            error,
            ChallengerCohortEvidenceMaintenanceInstallError,
        ):
            raise
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    if (
        verified_result.returncode != 0
        or not _print_bindings_valid(
            verified_result.stdout,
            contract=contract,
            domain=domain,
            target=target,
        )
    ):
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PRINT_VERIFY_FAILED"
        )
    verified_at = _utc(
        (
            clock
            or (
                lambda: utc_datetime(
                    datetime.now(timezone.utc)
                )
            )
        )()
    )
    target_stat = _target_stat(target, uid)
    verified = _command_evidence(print_argv, verified_result)
    identity = _receipt_identity(
        manifest_hash=manifest["manifest_hash"],
        contract_hash=contract["contract_hash"],
        target_path=target,
        target_stat=target_stat,
        action=action,
        installed_at=installed_at,
        verified_at=verified_at,
        preflight=preflight,
        bootstrap=bootstrap_evidence,
        verified=verified,
    )
    receipt = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "receipt_id": stable_id(
            "challenger_cohort_evidence_maintenance_install_receipt",
            identity,
        ),
        "receipt_hash": "0" * 64,
        "installed_at": installed_at,
        "verified_at": verified_at,
        "source_deployment": {
            "manifest_path": str(manifest_file),
            "manifest_file_sha256": hashlib.sha256(
                manifest_file.read_bytes()
            ).hexdigest(),
            "manifest_id": manifest["manifest_id"],
            "manifest_hash": manifest["manifest_hash"],
        },
        "source_contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": (
                trusted_candidate_attestation_hash
            ),
            "launchd_plist_sha256": hashlib.sha256(
                plist_bytes
            ).hexdigest(),
        },
        "execution_snapshot": {
            key: manifest["execution_snapshot"][key]
            for key in (
                "repository_root",
                "file_count",
                "total_bytes",
                "tree_hash",
            )
        },
        "domain": domain,
        "service": service,
        "target_path": str(target),
        "target_stat": target_stat,
        "install_action": action,
        "preflight_print": preflight,
        "bootstrap_or_null": bootstrap_evidence,
        "verified_print": verified,
        "installation_status": (
            "INSTALLED_AND_LOADED_WAITING_FOR_NATURAL_SCHEDULE"
        ),
        "run_at_load": False,
        "security_boundary": {
            "credential_count": 0,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "strategy_runner_invocation_count": 0,
            "maintenance_invocation_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "launchctl_command_count": (
                2 if action == "ALREADY_INSTALLED_AND_LOADED" else 3
            ),
        },
        "warnings": list(_WARNINGS),
    }
    receipt["receipt_hash"] = maintenance_install_receipt_hash(receipt)
    reasons = maintenance_install_receipt_reasons(
        receipt,
        manifest_path=manifest_file,
        trusted_source_attestation_hash=(
            trusted_source_attestation_hash
        ),
        trusted_candidate_attestation_hash=(
            trusted_candidate_attestation_hash
        ),
        target_path=target,
        _strategy_loader=_strategy_loader,
    )
    if reasons:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_INVALID"
        )
    receipt_path = _publish_receipt(receipt, receipt_output_root)
    return {
        "outcome": (
            "INSTALLED_AND_LOADED_WAITING_FOR_NATURAL_SCHEDULE"
        ),
        "install_action": action,
        "target_path": str(target),
        "target_sha256": target_stat["sha256"],
        "receipt_path": str(receipt_path),
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "domain": domain,
        "service": service,
        "launchctl_command_count": receipt["security_boundary"][
            "launchctl_command_count"
        ],
        "run_at_load": False,
        "maintenance_invocation_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
    }


def load_challenger_cohort_evidence_maintenance_install_receipt(
    *,
    receipt_path: Path,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    receipt_file = _secure_file(
        receipt_path,
        "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_READ_FAILED",
    )
    try:
        if receipt_file.stat().st_size > _MAX_RECEIPT_BYTES:
            raise ValueError
        receipt = _strict_json_bytes(receipt_file.read_bytes())
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_READ_FAILED"
        ) from error
    reasons = maintenance_install_receipt_reasons(
        receipt,
        manifest_path=manifest_path,
        trusted_source_attestation_hash=(
            trusted_source_attestation_hash
        ),
        trusted_candidate_attestation_hash=(
            trusted_candidate_attestation_hash
        ),
        target_path=Path(receipt["target_path"]),
        _strategy_loader=_strategy_loader,
    )
    if reasons:
        raise ChallengerCohortEvidenceMaintenanceInstallError(
            "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_INVALID"
        )
    return receipt
