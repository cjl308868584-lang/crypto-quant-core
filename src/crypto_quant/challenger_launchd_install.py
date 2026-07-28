"""Restricted user-domain installer and receipt for the challenger LaunchAgent."""

import hashlib
import json
import os
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

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_launchd import (
    ChallengerLaunchdError,
    challenger_launchd_contract_reasons,
    challenger_launchd_contract_trust_hash,
    load_challenger_launchd_contract,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-launchd-install-receipt-v1.schema.json"
_LABEL = "local.crypto-quant.challenger-forward"
_LAUNCHCTL = "/bin/launchctl"
_MAX_COMMAND_OUTPUT_BYTES = 1024 * 1024
_MAX_RECEIPT_BYTES = 2 * 1024 * 1024
_MAX_EXECUTION_FILE_BYTES = 4 * 1024 * 1024
_MAX_EXECUTION_TREE_BYTES = 32 * 1024 * 1024
_MAX_EXECUTION_FILES = 1000


class ChallengerLaunchdInstallError(ValueError):
    """The preflight, install transaction, OS verification, or receipt failed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LaunchctlResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_TIME_INVALID"
            ) from error
    else:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TIME_INVALID"
        )
    return rendered


def _command_runner(argv: Sequence[str]) -> LaunchctlResult:
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
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    result = LaunchctlResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    _validate_command_result(result)
    return result


def _validate_command_result(result: object) -> None:
    if (
        not isinstance(result, LaunchctlResult)
        or isinstance(result.returncode, bool)
        or not isinstance(result.returncode, int)
        or not isinstance(result.stdout, bytes)
        or not isinstance(result.stderr, bytes)
        or len(result.stdout) > _MAX_COMMAND_OUTPUT_BYTES
        or len(result.stderr) > _MAX_COMMAND_OUTPUT_BYTES
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_COMMAND_RESULT_INVALID"
        )
    try:
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_COMMAND_RESULT_INVALID"
        ) from error


def _command_evidence(
    argv: Sequence[str], result: LaunchctlResult
) -> Dict[str, Any]:
    _validate_command_result(result)
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


def _home_and_uid(
    *,
    home_directory: Optional[Path],
    uid: Optional[int],
) -> Tuple[Path, int]:
    selected_uid = os.getuid() if uid is None else uid
    selected_home = (
        Path.home() if home_directory is None else Path(home_directory)
    )
    if (
        isinstance(selected_uid, bool)
        or not isinstance(selected_uid, int)
        or selected_uid <= 0
        or not selected_home.is_absolute()
        or selected_home.is_symlink()
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_USER_INVALID"
        )
    return selected_home.resolve(), selected_uid


def _target_path(home: Path) -> Path:
    return home / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _validate_parent(path: Path, uid: int) -> None:
    parent = path.parent
    if not parent.exists():
        parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        status = parent.lstat()
    except OSError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TARGET_PARENT_INVALID"
        ) from error
    if (
        stat.S_ISLNK(status.st_mode)
        or not stat.S_ISDIR(status.st_mode)
        or status.st_uid != uid
        or stat.S_IMODE(status.st_mode) & 0o022
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TARGET_PARENT_INVALID"
        )


def _source_preflight(
    *,
    contract_path: Path,
    plist_path: Path,
) -> Tuple[Mapping[str, Any], bytes, Mapping[str, Any]]:
    try:
        source_contract_path = Path(contract_path).expanduser().resolve(
            strict=True
        )
        source_plist_path = Path(plist_path).expanduser().resolve(
            strict=True
        )
        contract = load_challenger_launchd_contract(
            contract_path=source_contract_path,
            plist_path=source_plist_path,
        )
        plist_bytes = source_plist_path.read_bytes()
        plist_status = source_plist_path.stat()
    except (OSError, ChallengerLaunchdError) as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_SOURCE_INVALID"
        ) from error
    trust_hash = challenger_launchd_contract_trust_hash(contract)
    if (
        challenger_launchd_contract_reasons(
            contract, plist_bytes, trust_hash
        )
        or contract.get("label") != _LABEL
        or contract.get("installation_status")
        != "NOT_INSTALLED_NO_EXTERNAL_RECEIPT"
        or stat.S_IMODE(plist_status.st_mode) != 0o600
        or plist_status.st_nlink != 1
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_SOURCE_INVALID"
        )
    for name in ("repository_root", "runtime_root", "python_executable"):
        value = Path(contract[name])
        if not value.is_absolute() or not value.exists():
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_SOURCE_BINDING_INVALID"
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
        check = subprocess.run(
            [
                contract["python_executable"],
                "-c",
                "import jsonschema, crypto_quant",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_PYTHON_PREFLIGHT_FAILED"
        ) from error
    if check.returncode != 0:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_PYTHON_PREFLIGHT_FAILED"
        )
    return contract, plist_bytes, _execution_snapshot(contract)


def _execution_snapshot(
    contract: Mapping[str, Any],
) -> Mapping[str, Any]:
    try:
        repository = Path(contract["repository_root"]).resolve(strict=True)
        runtime = Path(contract["runtime_root"]).resolve(strict=True)
        deployment_parent = (runtime / "deployment").resolve(strict=True)
        relative_root = repository.relative_to(deployment_parent)
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
        ) from error
    if not relative_root.parts:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
        )
    files = []
    total_bytes = 0
    owner_uid = os.getuid()
    try:
        repository_status = repository.lstat()
        if (
            not stat.S_ISDIR(repository_status.st_mode)
            or stat.S_ISLNK(repository_status.st_mode)
            or repository_status.st_uid != owner_uid
            or stat.S_IMODE(repository_status.st_mode) & 0o077
        ):
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
            )
        entries = sorted(
            repository.rglob("*"),
            key=lambda item: item.relative_to(repository).as_posix(),
        )
        for entry in entries:
            status = entry.lstat()
            mode = stat.S_IMODE(status.st_mode)
            if (
                stat.S_ISLNK(status.st_mode)
                or status.st_uid != owner_uid
                or mode & 0o077
            ):
                raise ChallengerLaunchdInstallError(
                    "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
                )
            if stat.S_ISDIR(status.st_mode):
                continue
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_size > _MAX_EXECUTION_FILE_BYTES
            ):
                raise ChallengerLaunchdInstallError(
                    "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
                )
            data = entry.read_bytes()
            total_bytes += len(data)
            files.append(
                {
                    "path": entry.relative_to(repository).as_posix(),
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            if (
                len(files) > _MAX_EXECUTION_FILES
                or total_bytes > _MAX_EXECUTION_TREE_BYTES
            ):
                raise ChallengerLaunchdInstallError(
                    "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
                )
    except OSError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
        ) from error
    required = {
        "pyproject.toml",
        "src/crypto_quant/__init__.py",
        "src/crypto_quant/challenger_forward_runner.py",
        "src/crypto_quant/challenger_forward_runner_cli.py",
    }
    if not required.issubset({item["path"] for item in files}):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID"
        )
    return {
        "repository_root": str(repository),
        "file_count": len(files),
        "total_bytes": total_bytes,
        "tree_hash": business_hash({"files": files}),
    }


def _atomic_install(path: Path, data: bytes, uid: int) -> bool:
    if path.exists() or path.is_symlink():
        try:
            status = path.lstat()
            existing = path.read_bytes()
        except OSError as error:
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_TARGET_CONFLICT"
            ) from error
        if (
            stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != uid
            or status.st_nlink != 1
            or existing != data
        ):
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_TARGET_CONFLICT"
            )
        os.chmod(path, 0o600)
        return False
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".challenger-launchd-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
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
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_TARGET_CONFLICT"
            ) from error
        installed = True
        temporary.unlink()
        directory_descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        return True
    finally:
        if temporary.exists():
            temporary.unlink()
        if installed:
            os.chmod(path, 0o600)


def _remove_own_install(path: Path) -> None:
    try:
        path.unlink()
        descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_ROLLBACK_FAILED"
        ) from error


def _target_stat(path: Path, uid: int) -> Dict[str, Any]:
    try:
        status = path.lstat()
        data = path.read_bytes()
    except OSError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TARGET_INVALID"
        ) from error
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != uid
        or status.st_nlink != 1
        or stat.S_IMODE(status.st_mode) != 0o600
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_TARGET_INVALID"
        )
    return {
        "device": status.st_dev,
        "inode": status.st_ino,
        "owner_uid": status.st_uid,
        "mode_octal": "0600",
        "link_count": status.st_nlink,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
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
        "crypto_quant.challenger_forward_runner_cli",
        contract["program_arguments"][4],
        contract["program_arguments"][6],
    )
    return all(value in text for value in required)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_install_receipt_hash(receipt: Mapping[str, Any]) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _receipt_identity(
    *,
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
        "source_contract_hash": contract_hash,
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


def _command_evidence_valid(
    evidence: Mapping[str, Any], expected_argv: Sequence[str]
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
            == artifact_self_hash(
                evidence, "command_evidence_hash"
            )
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def challenger_install_receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    plist_bytes: bytes,
    target_path: Path,
) -> Tuple[str, ...]:
    if not isinstance(receipt, Mapping):
        return ("CHALLENGER_INSTALL_RECEIPT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append("CHALLENGER_INSTALL_RECEIPT_SCHEMA_INVALID")
        if receipt.get("receipt_hash") != challenger_install_receipt_hash(
            receipt
        ):
            reasons.append("CHALLENGER_INSTALL_RECEIPT_HASH_MISMATCH")
        trust_hash = challenger_launchd_contract_trust_hash(contract)
        execution_snapshot = _execution_snapshot(contract)
        expected_source = {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": trust_hash,
            "launchd_plist_sha256": hashlib.sha256(
                plist_bytes
            ).hexdigest(),
            "execution_snapshot": execution_snapshot,
        }
        if receipt["source_contract"] != expected_source:
            reasons.append("CHALLENGER_INSTALL_SOURCE_MISMATCH")
        domain = receipt["domain"]
        uid = receipt["target_stat"]["owner_uid"]
        expected_domain = f"gui/{uid}"
        service = f"{expected_domain}/{_LABEL}"
        target = Path(target_path).expanduser().resolve()
        if (
            domain != expected_domain
            or receipt["service"] != service
            or receipt["target_path"] != str(target)
        ):
            reasons.append("CHALLENGER_INSTALL_TARGET_BINDING_MISMATCH")
        actual_stat = _target_stat(target, uid)
        if receipt["target_stat"] != actual_stat:
            reasons.append("CHALLENGER_INSTALL_TARGET_STAT_MISMATCH")
        print_argv = (_LAUNCHCTL, "print", service)
        if not _command_evidence_valid(
            receipt["preflight_print"], print_argv
        ):
            reasons.append("CHALLENGER_INSTALL_PREFLIGHT_EVIDENCE_INVALID")
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
            reasons.append("CHALLENGER_INSTALL_PRINT_EVIDENCE_INVALID")
        bootstrap_argv = (
            _LAUNCHCTL,
            "bootstrap",
            domain,
            str(target),
        )
        action = receipt["install_action"]
        bootstrap = receipt["bootstrap_or_null"]
        if action == "ALREADY_INSTALLED_AND_LOADED":
            if bootstrap is not None:
                reasons.append(
                    "CHALLENGER_INSTALL_BOOTSTRAP_EVIDENCE_INVALID"
                )
        elif (
            not isinstance(bootstrap, Mapping)
            or not _command_evidence_valid(bootstrap, bootstrap_argv)
            or bootstrap["return_code"] != 0
        ):
            reasons.append("CHALLENGER_INSTALL_BOOTSTRAP_EVIDENCE_INVALID")
        identity = _receipt_identity(
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
        if receipt["receipt_id"] != stable_id(
            "challenger_launchd_install_receipt", identity
        ):
            reasons.append("CHALLENGER_INSTALL_RECEIPT_ID_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        ChallengerLaunchdInstallError,
    ):
        reasons.append("CHALLENGER_INSTALL_RECEIPT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _publish_receipt(
    *,
    receipt: Mapping[str, Any],
    output_root: Path,
) -> Path:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_OUTPUT_INVALID"
        )
    directory = requested.resolve() / "challenger-install-receipts"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / f"{receipt['receipt_id']}.json"
    try:
        _publish_exact(path, canonical_json(receipt).encode("utf-8"))
    except ValueError as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_RECEIPT_CONFLICT"
        ) from error
    return path


def install_challenger_launchd(
    *,
    contract_path: Path,
    plist_path: Path,
    receipt_output_root: Path,
    clock=None,
    _home_directory: Optional[Path] = None,
    _uid: Optional[int] = None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    contract, plist_bytes, execution_snapshot = _source_preflight(
        contract_path=contract_path,
        plist_path=plist_path,
    )
    home, uid = _home_and_uid(
        home_directory=_home_directory,
        uid=_uid,
    )
    target = _target_path(home)
    _validate_parent(target, uid)
    domain = f"gui/{uid}"
    service = f"{domain}/{_LABEL}"
    runner = _launchctl_runner or _command_runner
    print_argv = (_LAUNCHCTL, "print", service)
    try:
        preflight_result = runner(print_argv)
    except ChallengerLaunchdInstallError:
        raise
    except Exception as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    _validate_command_result(preflight_result)
    preflight = _command_evidence(print_argv, preflight_result)
    target_exists = target.exists() or target.is_symlink()
    if preflight_result.returncode == 0:
        if (
            not target_exists
            or target.read_bytes() != plist_bytes
            or not _print_bindings_valid(
                preflight_result.stdout,
                contract=contract,
                domain=domain,
                target=target,
            )
        ):
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_EXISTING_SERVICE_CONFLICT"
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
            _validate_command_result(bootstrap_result)
        except Exception as error:
            if created:
                _remove_own_install(target)
            if isinstance(error, ChallengerLaunchdInstallError):
                raise
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_LAUNCHCTL_FAILED"
            ) from error
        bootstrap_evidence = _command_evidence(
            bootstrap_argv, bootstrap_result
        )
        if bootstrap_result.returncode != 0:
            if created:
                _remove_own_install(target)
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_BOOTSTRAP_FAILED"
            )
    installed_at = _utc((clock or _utc_now)())
    try:
        verified_result = runner(print_argv)
        _validate_command_result(verified_result)
    except Exception as error:
        if isinstance(error, ChallengerLaunchdInstallError):
            raise
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_LAUNCHCTL_FAILED"
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
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_PRINT_VERIFY_FAILED"
        )
    verified_at = _utc((clock or _utc_now)())
    target_stat = _target_stat(target, uid)
    verified = _command_evidence(print_argv, verified_result)
    identity = _receipt_identity(
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
        "$schema": "./challenger-launchd-install-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": stable_id(
            "challenger_launchd_install_receipt", identity
        ),
        "receipt_hash": "0" * 64,
        "installed_at": installed_at,
        "verified_at": verified_at,
        "source_contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": challenger_launchd_contract_trust_hash(
                contract
            ),
            "launchd_plist_sha256": hashlib.sha256(
                plist_bytes
            ).hexdigest(),
            "execution_snapshot": execution_snapshot,
        },
        "domain": domain,
        "service": service,
        "target_path": str(target),
        "target_stat": target_stat,
        "install_action": action,
        "preflight_print": preflight,
        "bootstrap_or_null": bootstrap_evidence,
        "verified_print": verified,
        "installation_status": "INSTALLED_AND_LOADED",
        "run_at_load_status": "NOT_OBSERVED_BY_INSTALL_RECEIPT",
        "security_boundary": {
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "launchctl_command_count": (
                2 if action == "ALREADY_INSTALLED_AND_LOADED" else 3
            ),
        },
        "warnings": [
            "INSTALLATION_RECEIPT_DOES_NOT_PROVE_RUN_AT_LOAD_SUCCESS",
            "RUNNER_HAS_PUBLIC_MARKET_DATA_ACCESS_ONLY",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    receipt["receipt_hash"] = challenger_install_receipt_hash(receipt)
    if challenger_install_receipt_reasons(
        receipt,
        contract=contract,
        plist_bytes=plist_bytes,
        target_path=target,
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_RECEIPT_INVALID"
        )
    receipt_path = _publish_receipt(
        receipt=receipt,
        output_root=receipt_output_root,
    )
    return {
        "outcome": "INSTALLED_AND_LOADED",
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
        "run_at_load_status": receipt["run_at_load_status"],
        "broker_request_count": 0,
        "order_submission_count": 0,
    }


def load_challenger_install_receipt(
    *,
    receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    try:
        resolved = Path(receipt_path).expanduser().resolve(strict=True)
        if resolved.stat().st_size > _MAX_RECEIPT_BYTES:
            raise ChallengerLaunchdInstallError(
                "CHALLENGER_INSTALL_RECEIPT_READ_FAILED"
            )
        receipt = _strict_json_bytes(resolved.read_bytes())
        contract, plist_bytes, _execution_snapshot_value = _source_preflight(
            contract_path=contract_path,
            plist_path=plist_path,
        )
    except (OSError, ValueError, ChallengerLaunchdInstallError) as error:
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_RECEIPT_READ_FAILED"
        ) from error
    if challenger_install_receipt_reasons(
        receipt,
        contract=contract,
        plist_bytes=plist_bytes,
        target_path=Path(receipt["target_path"]),
    ):
        raise ChallengerLaunchdInstallError(
            "CHALLENGER_INSTALL_RECEIPT_INVALID"
        )
    return receipt
