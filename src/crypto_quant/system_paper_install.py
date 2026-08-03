"""Preflight-gated atomic installer for the System Paper LaunchAgent."""

import hashlib
import json
import os
import secrets
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .system_paper_evidence import SystemPaperEvidenceError, publish_owner_exact
from .system_paper_launchd import (
    load_system_paper_launchd_contract,
    system_paper_launchd_contract_trust_hash,
)
from .system_paper_preflight import load_system_paper_preflight_receipt


_SCHEMA = "system-paper-install-receipt-v1.schema.json"
_LABEL = "local.crypto-quant.system-paper-v1"
_LAUNCHCTL = "/bin/launchctl"
_MAX_COMMAND_BYTES = 64 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_ACTIVATION_WINDOW_START = timedelta(minutes=30)
_ACTIVATION_WINDOW_END = timedelta(hours=3, minutes=30)
_WARNINGS = (
    "INSTALL_RECEIPT_DOES_NOT_PROVE_FIRST_NATURAL_SLOT",
    "INSTALLER_DOES_NOT_KICKSTART_OR_INVOKE_RUNTIME",
    "PUBLIC_MARKET_DATA_ONLY",
    "NO_LIVE_TRADING_AUTHORITY",
)


class SystemPaperInstallError(ValueError):
    """The preflight, atomic install, OS verification, or receipt failed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class LaunchctlResult:
    returncode: int
    stdout: bytes
    stderr: bytes


def _now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TIME_INVALID")
    text = utc_datetime(parsed)
    if isinstance(value, str) and value != text:
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TIME_INVALID")
    return text


def _activation_window_safe(value: str) -> bool:
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    boundary = instant.replace(
        hour=(instant.hour // 4) * 4,
        minute=0,
        second=0,
        microsecond=0,
    )
    offset = instant - boundary
    return _ACTIVATION_WINDOW_START <= offset <= _ACTIVATION_WINDOW_END


def _default_launchctl_runner(argv: Sequence[str]) -> LaunchctlResult:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    return LaunchctlResult(completed.returncode, completed.stdout, completed.stderr)


def _validate_result(result: object) -> None:
    if (
        not isinstance(result, LaunchctlResult)
        or isinstance(result.returncode, bool)
        or not isinstance(result.returncode, int)
        or not 0 <= result.returncode <= 255
        or not isinstance(result.stdout, bytes)
        or not isinstance(result.stderr, bytes)
        or len(result.stdout) > _MAX_COMMAND_BYTES
        or len(result.stderr) > _MAX_COMMAND_BYTES
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_COMMAND_RESULT_INVALID"
        )
    try:
        result.stdout.decode("utf-8")
        result.stderr.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_COMMAND_RESULT_INVALID"
        ) from error


def _call(runner, argv) -> LaunchctlResult:
    try:
        result = runner(tuple(argv))
    except SystemPaperInstallError:
        raise
    except Exception as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_LAUNCHCTL_FAILED"
        ) from error
    _validate_result(result)
    return result


def _command_evidence(argv, result: LaunchctlResult) -> Dict[str, Any]:
    return {
        "argv": list(argv),
        "returncode": result.returncode,
        "stdout_size_bytes": len(result.stdout),
        "stderr_size_bytes": len(result.stderr),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
    }


def _print_bindings_valid(
    data: bytes,
    *,
    contract: Mapping[str, Any],
    service: str,
    target: Path,
) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    required = (
        service,
        _LABEL,
        str(target),
        contract["python_executable"],
        "crypto_quant.system_paper_runtime_cli",
        contract["program_arguments"][4],
        contract["program_arguments"][6],
        contract["execution_snapshot"]["repository_root"],
    )
    return all(value in text for value in required)


def _secure_home(home: Path, uid: int) -> Path:
    try:
        entry = home.lstat()
        resolved = home.resolve(strict=True)
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_HOME_INVALID"
        ) from error
    if (
        resolved != home
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != uid
        or stat.S_IMODE(entry.st_mode) & 0o022
    ):
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_HOME_INVALID")
    return home


def _ensure_directory(path: Path, uid: int, *, exact_mode: Optional[int]) -> bool:
    created = False
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        created = True
    except FileExistsError:
        pass
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_PARENT_INVALID"
        ) from error
    try:
        entry = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_PARENT_INVALID"
        ) from error
    mode = stat.S_IMODE(entry.st_mode)
    if (
        resolved != path
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != uid
        or (mode != exact_mode if exact_mode is not None else bool(mode & 0o022))
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_PARENT_INVALID"
        )
    return created


def _ensure_target_parent(home: Path, uid: int) -> Path:
    _secure_home(home, uid)
    library = home / "Library"
    _ensure_directory(library, uid, exact_mode=None)
    launch_agents = library / "LaunchAgents"
    _ensure_directory(launch_agents, uid, exact_mode=0o700)
    return launch_agents


def _open_parent(path: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(str(path), flags)
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_PARENT_INVALID"
        ) from error


def _read_fd(descriptor: int, maximum: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = os.read(descriptor, min(65536, maximum + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_TARGET_CONFLICT"
            )


def _target_fd(parent_fd: int, name: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    return os.open(name, flags, dir_fd=parent_fd)


def _existing_target(parent_fd: int, name: str, data: bytes, uid: int):
    try:
        descriptor = _target_fd(parent_fd, name)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_CONFLICT"
        ) from error
    try:
        entry = os.fstat(descriptor)
        existing = _read_fd(descriptor, len(data))
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != uid
        or entry.st_nlink != 1
        or stat.S_IMODE(entry.st_mode) != 0o600
        or existing != data
    ):
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TARGET_CONFLICT")
    return (entry.st_dev, entry.st_ino)


def _atomic_install(path: Path, data: bytes, uid: int):
    parent_fd = _open_parent(path.parent)
    try:
        existing = _existing_target(parent_fd, path.name, data, uid)
        if existing is not None:
            return False, existing
        temporary_name = ".system-paper-" + secrets.token_hex(16) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
        installed = False
        try:
            os.fchmod(descriptor, 0o600)
            view = memoryview(data)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short write")
                view = view[written:]
            os.fsync(descriptor)
            temp_stat = os.fstat(descriptor)
            os.link(
                temporary_name,
                path.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            installed = True
            os.unlink(temporary_name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            target_fd = _target_fd(parent_fd, path.name)
            try:
                target_stat = os.fstat(target_fd)
            finally:
                os.close(target_fd)
            if (target_stat.st_dev, target_stat.st_ino) != (
                temp_stat.st_dev,
                temp_stat.st_ino,
            ):
                raise SystemPaperInstallError(
                    "SYSTEM_PAPER_INSTALL_TARGET_IDENTITY_CHANGED"
                )
            return True, (target_stat.st_dev, target_stat.st_ino)
        except FileExistsError as error:
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_TARGET_CONFLICT"
            ) from error
        except SystemPaperInstallError:
            raise
        except OSError as error:
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_TARGET_WRITE_FAILED"
            ) from error
        finally:
            os.close(descriptor)
            if not installed:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
    finally:
        os.close(parent_fd)


def _rollback_new_target(path: Path, identity) -> None:
    parent_fd = _open_parent(path.parent)
    try:
        try:
            descriptor = _target_fd(parent_fd, path.name)
        except OSError as error:
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_ROLLBACK_FAILED"
            ) from error
        try:
            entry = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if (entry.st_dev, entry.st_ino) != tuple(identity):
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_ROLLBACK_IDENTITY_MISMATCH"
            )
        os.unlink(path.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def _target_stat(path: Path, uid: int) -> Dict[str, Any]:
    parent_fd = _open_parent(path.parent)
    try:
        descriptor = _target_fd(parent_fd, path.name)
        try:
            entry = os.fstat(descriptor)
            data = _read_fd(descriptor, 2 * 1024 * 1024)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_TARGET_INVALID"
        ) from error
    finally:
        os.close(parent_fd)
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != uid
        or entry.st_nlink != 1
        or stat.S_IMODE(entry.st_mode) != 0o600
    ):
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_TARGET_INVALID")
    return {
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "owner_uid": entry.st_uid,
        "mode": stat.S_IMODE(entry.st_mode),
        "link_count": entry.st_nlink,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _receipt_reasons(
    receipt,
    *,
    contract,
    plist_bytes,
    preflight,
    preflight_path,
    target,
):
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append("SYSTEM_PAPER_INSTALL_RECEIPT_SCHEMA_INVALID")
        if receipt["receipt_hash"] != artifact_self_hash(receipt, "receipt_hash"):
            reasons.append("SYSTEM_PAPER_INSTALL_RECEIPT_HASH_MISMATCH")
        expected_source = {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": system_paper_launchd_contract_trust_hash(contract),
            "launchd_plist_sha256": hashlib.sha256(plist_bytes).hexdigest(),
            "release_commit": contract["release"]["release_commit"],
            "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
        }
        expected_preflight = {
            "receipt_id": preflight["receipt_id"],
            "receipt_hash": preflight["receipt_hash"],
            "receipt_path": str(Path(preflight_path)),
            "verified_at": preflight["verified_at"],
            "expires_at": preflight["expires_at_or_null"],
        }
        if receipt["source_contract"] != expected_source:
            reasons.append("SYSTEM_PAPER_INSTALL_SOURCE_MISMATCH")
        if receipt["preflight_receipt"] != expected_preflight:
            reasons.append("SYSTEM_PAPER_INSTALL_PREFLIGHT_BINDING_MISMATCH")
        uid = preflight["machine_identity"]["uid"]
        domain = f"gui/{uid}"
        service = f"{domain}/{_LABEL}"
        expected_target = (
            Path(preflight["machine_identity"]["home"])
            / "Library"
            / "LaunchAgents"
            / f"{_LABEL}.plist"
        )
        if (
            receipt["domain"] != domain
            or receipt["service"] != service
            or receipt["target_path"] != str(target)
            or target != expected_target
        ):
            reasons.append("SYSTEM_PAPER_INSTALL_TARGET_BINDING_MISMATCH")
        actual = _target_stat(target, uid)
        recorded = receipt["target_stat"]
        if any(
            actual[key] != recorded[key]
            for key in ("inode", "owner_uid", "mode", "link_count", "size_bytes", "sha256")
        ):
            reasons.append("SYSTEM_PAPER_INSTALL_TARGET_STAT_MISMATCH")
        print_argv = [_LAUNCHCTL, "print", service]
        bootstrap_argv = [_LAUNCHCTL, "bootstrap", domain, str(target)]
        if receipt["preflight_print"]["argv"] != print_argv:
            reasons.append("SYSTEM_PAPER_INSTALL_COMMAND_EVIDENCE_INVALID")
        if (
            receipt["verified_print"]["argv"] != print_argv
            or receipt["verified_print"]["returncode"] != 0
        ):
            reasons.append("SYSTEM_PAPER_INSTALL_COMMAND_EVIDENCE_INVALID")
        action = receipt["install_action"]
        bootstrap = receipt["bootstrap_or_null"]
        if action == "ALREADY_INSTALLED_AND_LOADED":
            if bootstrap is not None or receipt["preflight_print"]["returncode"] != 0:
                reasons.append("SYSTEM_PAPER_INSTALL_BOOTSTRAP_EVIDENCE_INVALID")
            expected_count = 2
        else:
            if (
                not isinstance(bootstrap, Mapping)
                or bootstrap.get("argv") != bootstrap_argv
                or bootstrap.get("returncode") != 0
                or receipt["preflight_print"]["returncode"] != 113
            ):
                reasons.append("SYSTEM_PAPER_INSTALL_BOOTSTRAP_EVIDENCE_INVALID")
            expected_count = 3
        security = receipt["security_boundary"]
        if security != {
            "production_activation_enabled": False,
            "launchctl_command_count": expected_count,
            "runtime_invocation_count": 0,
            "network_request_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        } or receipt["warnings"] != list(_WARNINGS):
            reasons.append("SYSTEM_PAPER_INSTALL_SECURITY_BOUNDARY_INVALID")
        installed_at = datetime.fromisoformat(
            receipt["installed_at"].replace("Z", "+00:00")
        )
        verified_at = datetime.fromisoformat(
            receipt["verified_at"].replace("Z", "+00:00")
        )
        preflight_verified = datetime.fromisoformat(
            preflight["verified_at"].replace("Z", "+00:00")
        )
        preflight_expires = datetime.fromisoformat(
            preflight["expires_at_or_null"].replace("Z", "+00:00")
        )
        if not (
            preflight_verified <= installed_at <= preflight_expires
            and installed_at <= verified_at
            and _activation_window_safe(receipt["installed_at"])
        ):
            reasons.append("SYSTEM_PAPER_INSTALL_TIME_BINDING_INVALID")
        identity = {
            "contract_hash": contract["contract_hash"],
            "preflight_receipt_hash": preflight["receipt_hash"],
            "target_path": str(target),
            "target_inode": recorded["inode"],
            "install_action": action,
            "installed_at": receipt["installed_at"],
            "verified_at": receipt["verified_at"],
        }
        if receipt["receipt_id"] != stable_id(
            "system_paper_install_receipt", identity
        ):
            reasons.append("SYSTEM_PAPER_INSTALL_RECEIPT_ID_MISMATCH")
    except (KeyError, TypeError, ValueError, SystemPaperInstallError):
        reasons.append("SYSTEM_PAPER_INSTALL_RECEIPT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _load_sources(
    *,
    contract_path,
    plist_path,
    preflight_receipt_path,
    machine_probe,
    filesystem_probe,
    clock,
    allow_expired=False,
):
    contract = load_system_paper_launchd_contract(
        contract_path=Path(contract_path), plist_path=Path(plist_path)
    )
    preflight = load_system_paper_preflight_receipt(
        receipt_path=Path(preflight_receipt_path),
        contract_path=Path(contract_path),
        plist_path=Path(plist_path),
        machine_probe=machine_probe,
        filesystem_probe=filesystem_probe,
        clock=clock,
        _allow_expired_verified=allow_expired,
    )
    if preflight["status"] != "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE":
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_PREFLIGHT_NOT_ELIGIBLE"
        )
    plist_bytes = Path(plist_path).read_bytes()
    return contract, plist_bytes, preflight


def install_system_paper_launchd(
    *,
    contract_path: Path,
    plist_path: Path,
    preflight_receipt_path: Path,
    clock=None,
    _launchctl_runner=None,
    _machine_probe=None,
    _filesystem_probe=None,
) -> Mapping[str, Any]:
    selected_clock = clock or _now
    checked_at = _utc(selected_clock())
    current_clock = lambda: checked_at
    try:
        contract, plist_bytes, preflight = _load_sources(
            contract_path=contract_path,
            plist_path=plist_path,
            preflight_receipt_path=preflight_receipt_path,
            machine_probe=_machine_probe,
            filesystem_probe=_filesystem_probe,
            clock=current_clock,
        )
    except SystemPaperInstallError:
        raise
    except Exception as error:
        reason = (
            "SYSTEM_PAPER_INSTALL_PREFLIGHT_EXPIRED"
            if "EXPIRED" in str(error)
            else "SYSTEM_PAPER_INSTALL_PREFLIGHT_INVALID"
        )
        raise SystemPaperInstallError(reason) from error
    if not _activation_window_safe(checked_at):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_ACTIVATION_WINDOW_UNSAFE"
        )
    uid = preflight["machine_identity"]["uid"]
    home = Path(preflight["machine_identity"]["home"])
    target = home / "Library" / "LaunchAgents" / f"{_LABEL}.plist"
    domain = f"gui/{uid}"
    service = f"{domain}/{_LABEL}"
    runner = _launchctl_runner or _default_launchctl_runner
    print_argv = (_LAUNCHCTL, "print", service)
    first = _call(runner, print_argv)
    if first.returncode not in (0, 113):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_PREFLIGHT_PRINT_FAILED"
        )
    preflight_print = _command_evidence(print_argv, first)

    installed_at = _utc(selected_clock())
    if not _activation_window_safe(installed_at):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_ACTIVATION_WINDOW_UNSAFE"
        )

    # Close the check/use race before the first installation write.
    current_clock = lambda: installed_at
    contract2, plist_bytes2, preflight2 = _load_sources(
        contract_path=contract_path,
        plist_path=plist_path,
        preflight_receipt_path=preflight_receipt_path,
        machine_probe=_machine_probe,
        filesystem_probe=_filesystem_probe,
        clock=current_clock,
    )
    if contract2 != contract or plist_bytes2 != plist_bytes or preflight2 != preflight:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_SOURCE_CHANGED"
        )

    target_exists = target.exists() or target.is_symlink()
    if first.returncode == 0:
        if (
            not target_exists
            or target.is_symlink()
            or target.read_bytes() != plist_bytes
            or not _print_bindings_valid(
                first.stdout, contract=contract, service=service, target=target
            )
        ):
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_EXISTING_SERVICE_CONFLICT"
            )
        action = "ALREADY_INSTALLED_AND_LOADED"
        bootstrap_evidence = None
    else:
        _ensure_target_parent(_secure_home(home, uid), uid)
        created, installed_identity = _atomic_install(target, plist_bytes, uid)
        action = (
            "INSTALLED_AND_BOOTSTRAPPED"
            if created
            else "EXISTING_FILE_BOOTSTRAPPED"
        )
        before_bootstrap = _target_stat(target, uid)
        if (
            (before_bootstrap["device"], before_bootstrap["inode"])
            != tuple(installed_identity)
            or before_bootstrap["sha256"]
            != hashlib.sha256(plist_bytes).hexdigest()
        ):
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_TARGET_IDENTITY_CHANGED"
            )
        bootstrap_argv = (_LAUNCHCTL, "bootstrap", domain, str(target))
        try:
            bootstrap_result = _call(runner, bootstrap_argv)
        except Exception:
            if created:
                _rollback_new_target(target, installed_identity)
            raise
        bootstrap_evidence = _command_evidence(bootstrap_argv, bootstrap_result)
        if bootstrap_result.returncode != 0:
            if created:
                _rollback_new_target(target, installed_identity)
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_BOOTSTRAP_FAILED"
            )

    verified_result = _call(runner, print_argv)
    if (
        verified_result.returncode != 0
        or not _print_bindings_valid(
            verified_result.stdout,
            contract=contract,
            service=service,
            target=target,
        )
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_PRINT_VERIFY_FAILED"
        )
    verified_at = _utc(selected_clock())
    verified_print = _command_evidence(print_argv, verified_result)
    target_stat = _target_stat(target, uid)
    source_contract = {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": system_paper_launchd_contract_trust_hash(contract),
        "launchd_plist_sha256": hashlib.sha256(plist_bytes).hexdigest(),
        "release_commit": contract["release"]["release_commit"],
        "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
    }
    preflight_binding = {
        "receipt_id": preflight["receipt_id"],
        "receipt_hash": preflight["receipt_hash"],
        "receipt_path": str(Path(preflight_receipt_path)),
        "verified_at": preflight["verified_at"],
        "expires_at": preflight["expires_at_or_null"],
    }
    identity = {
        "contract_hash": contract["contract_hash"],
        "preflight_receipt_hash": preflight["receipt_hash"],
        "target_path": str(target),
        "target_inode": target_stat["inode"],
        "install_action": action,
        "installed_at": installed_at,
        "verified_at": verified_at,
    }
    command_count = 2 if bootstrap_evidence is None else 3
    receipt = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "receipt_id": stable_id("system_paper_install_receipt", identity),
        "receipt_hash": "0" * 64,
        "installed_at": installed_at,
        "verified_at": verified_at,
        "source_contract": source_contract,
        "preflight_receipt": preflight_binding,
        "domain": domain,
        "service": service,
        "target_path": str(target),
        "target_stat": target_stat,
        "install_action": action,
        "preflight_print": preflight_print,
        "bootstrap_or_null": bootstrap_evidence,
        "verified_print": verified_print,
        "installation_status": "INSTALLED_AND_LOADED",
        "run_at_load_status": "FIRST_NATURAL_SLOT_NOT_OBSERVED",
        "security_boundary": {
            "production_activation_enabled": False,
            "launchctl_command_count": command_count,
            "runtime_invocation_count": 0,
            "network_request_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        },
        "warnings": list(_WARNINGS),
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if _receipt_reasons(
        receipt,
        contract=contract,
        plist_bytes=plist_bytes,
        preflight=preflight,
        preflight_path=preflight_receipt_path,
        target=target,
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_INVALID"
        )
    output = Path(contract["root_paths"]["install_receipts"])
    output.mkdir(mode=0o700, parents=False, exist_ok=True)
    output_entry = output.lstat()
    if (
        output.resolve(strict=True) != output
        or not stat.S_ISDIR(output_entry.st_mode)
        or output_entry.st_uid != os.getuid()
        or stat.S_IMODE(output_entry.st_mode) != 0o700
    ):
        raise SystemPaperInstallError("SYSTEM_PAPER_INSTALL_OUTPUT_INVALID")
    receipt_path = output / f"{receipt['receipt_id']}.json"
    try:
        publish_owner_exact(receipt_path, canonical_json(receipt).encode("utf-8"))
    except SystemPaperEvidenceError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_CONFLICT"
        ) from error
    return {
        "outcome": "INSTALLED_AND_LOADED",
        "install_action": action,
        "target_path": str(target),
        "target_sha256": target_stat["sha256"],
        "receipt_path": str(receipt_path),
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "launchctl_command_count": command_count,
        "runtime_invocation_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
    }


def load_system_paper_install_receipt(
    *,
    receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    preflight_receipt_path: Path,
    _machine_probe=None,
    _filesystem_probe=None,
) -> Mapping[str, Any]:
    contract, plist_bytes, preflight = _load_sources(
        contract_path=contract_path,
        plist_path=plist_path,
        preflight_receipt_path=preflight_receipt_path,
        machine_probe=_machine_probe,
        filesystem_probe=_filesystem_probe,
        clock=lambda: "1970-01-01T00:00:00.000Z",
        allow_expired=True,
    )
    path = Path(receipt_path)
    try:
        entry = path.lstat()
        data = path.read_bytes()
    except OSError as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_READ_INVALID"
        ) from error
    if (
        path.resolve(strict=True) != path
        or not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != os.getuid()
        or entry.st_nlink != 1
        or stat.S_IMODE(entry.st_mode) != 0o600
        or not 0 < len(data) <= _MAX_RECEIPT_BYTES
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_READ_INVALID"
        )
    try:
        receipt = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_READ_INVALID"
        ) from error
    if canonical_json(receipt).encode("utf-8") != data:
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_READ_INVALID"
        )
    expected_output = Path(contract["root_paths"]["install_receipts"])
    if path.parent != expected_output or path.name != f"{receipt.get('receipt_id')}.json":
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_READ_INVALID"
        )
    for item in expected_output.iterdir():
        if not item.is_file() or not item.name.startswith(
            "system_paper_install_receipt_"
        ) or item.suffix != ".json":
            raise SystemPaperInstallError(
                "SYSTEM_PAPER_INSTALL_OUTPUT_INVENTORY_INVALID"
            )
    target = Path(receipt["target_path"])
    if _receipt_reasons(
        receipt,
        contract=contract,
        plist_bytes=plist_bytes,
        preflight=preflight,
        preflight_path=preflight_receipt_path,
        target=target,
    ):
        raise SystemPaperInstallError(
            "SYSTEM_PAPER_INSTALL_RECEIPT_INVALID"
        )
    return receipt
