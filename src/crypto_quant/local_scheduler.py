"""Deterministic, non-installing macOS LaunchAgent contract."""

import hashlib
import json
import os
import plistlib
import stat
import time
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .market_data_cli import _publish_immutable


_LABEL = "local.crypto-quant.context-complete-cycle"
_ATTESTATION_TYPE = "LOCAL_SCHEDULER_CONTRACT_ATTESTATION"
_HOURS = (0, 4, 8, 12, 16, 20)
_MINUTE = 6
_KEY_ENV = "CRYPTO_QUANT_BINANCE_READONLY_API_KEY_FILE"
_SECRET_ENV = "CRYPTO_QUANT_BINANCE_READONLY_API_SECRET_FILE"
_WARNINGS = (
    "LAUNCHAGENT_NOT_INSTALLED",
    "INSTALLATION_AND_LOAD_RECEIPT_REQUIRED",
    "CREDENTIAL_VALUES_NOT_INCLUDED",
    "REAL_CONTEXT_COMPLETE_CYCLE_NOT_YET_PROVEN",
)


class LocalSchedulerError(ValueError):
    """A local scheduler contract failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise LocalSchedulerError(
                "LOCAL_SCHEDULER_TIME_INVALID"
            ) from error
    else:
        raise LocalSchedulerError("LOCAL_SCHEDULER_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalSchedulerError("LOCAL_SCHEDULER_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise LocalSchedulerError("LOCAL_SCHEDULER_TIME_INVALID")
    return utc_datetime(converted)


def _absolute(value: object, reason: str) -> Path:
    if not isinstance(value, (str, Path)) or "\x00" in str(value):
        raise LocalSchedulerError(reason)
    path = Path(value)
    if not path.is_absolute():
        raise LocalSchedulerError(reason)
    return path.resolve()


def _inside(path: Path, boundary: Path) -> bool:
    try:
        path.relative_to(boundary)
        return True
    except ValueError:
        return False


def _credential_path(
    value: object,
    *,
    repository_root: Path,
    runtime_root: Path,
) -> Path:
    raw = Path(value) if isinstance(value, (str, Path)) else Path("")
    if not raw.is_absolute() or raw.is_symlink():
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_CREDENTIAL_PATH_INVALID"
        )
    try:
        entry = raw.lstat()
        path = raw.resolve(strict=True)
    except OSError as error:
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_CREDENTIAL_PATH_INVALID"
        ) from error
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != os.getuid()
        or entry.st_nlink != 1
        or stat.S_IMODE(entry.st_mode) != 0o600
        or not 16 <= entry.st_size <= 512
        or _inside(path, repository_root)
        or _inside(path, runtime_root)
    ):
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_CREDENTIAL_PATH_INVALID"
        )
    return path


def _worker(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 80
        or any(
            character
            not in "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for character in value
        )
    ):
        raise LocalSchedulerError("LOCAL_SCHEDULER_WORKER_INVALID")
    return value


def _validate_repository(path: Path) -> None:
    required = (
        path / "pyproject.toml",
        path
        / "src"
        / "crypto_quant"
        / "context_cycle_orchestrator_cli.py",
    )
    if not path.is_dir() or path.is_symlink() or not all(
        item.is_file() for item in required
    ):
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_REPOSITORY_INVALID"
        )


def _validate_python(path: Path) -> None:
    try:
        status = path.stat()
    except OSError as error:
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_PYTHON_INVALID"
        ) from error
    if not stat.S_ISREG(status.st_mode) or not os.access(path, os.X_OK):
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_PYTHON_INVALID"
        )


def _program_arguments(
    python_executable: Path,
    repository_root: Path,
    runtime_root: Path,
    worker_id: str,
) -> Sequence[str]:
    return (
        str(python_executable),
        "-m",
        "crypto_quant.context_cycle_orchestrator_cli",
        "--orchestration-state-path",
        str(runtime_root / "state" / "orchestration.sqlite"),
        "--paper-state-path",
        str(runtime_root / "state" / "paper.sqlite"),
        "--context-state-path",
        str(runtime_root / "state" / "paper-context.sqlite"),
        "--output-root",
        str(runtime_root / "artifacts"),
        "--worker-id",
        worker_id,
    )


def _plist_payload(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    api_key_file: Path,
    api_secret_file: Path,
    worker_id: str,
) -> Dict[str, Any]:
    return {
        "Label": _LABEL,
        "ProgramArguments": list(
            _program_arguments(
                python_executable,
                repository_root,
                runtime_root,
                worker_id,
            )
        ),
        "WorkingDirectory": str(repository_root),
        "EnvironmentVariables": {
            "PYTHONPATH": str(repository_root / "src"),
            _KEY_ENV: str(api_key_file),
            _SECRET_ENV: str(api_secret_file),
        },
        "StartCalendarInterval": [
            {"Hour": hour, "Minute": _MINUTE} for hour in _HOURS
        ],
        "RunAtLoad": True,
        "ProcessType": "Background",
        "ThrottleInterval": 60,
        "LowPriorityIO": True,
        "AbandonProcessGroup": True,
        "StandardOutPath": str(
            runtime_root / "log" / "context-cycle.stdout.log"
        ),
        "StandardErrorPath": str(
            runtime_root / "log" / "context-cycle.stderr.log"
        ),
    }


def _plist_bytes(payload: Mapping[str, Any]) -> bytes:
    return plistlib.dumps(
        dict(payload),
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath(
        "schemas", "local-scheduler-contract-v1.schema.json"
    )
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_local_scheduler_contract(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    api_key_file: Path,
    api_secret_file: Path,
    worker_id: str,
    created_at: object,
) -> Tuple[Dict[str, Any], bytes]:
    if Path(repository_root).is_symlink():
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_REPOSITORY_INVALID"
        )
    if Path(runtime_root).is_symlink():
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_RUNTIME_ROOT_INVALID"
        )
    repository = _absolute(
        repository_root, "LOCAL_SCHEDULER_REPOSITORY_INVALID"
    )
    runtime = _absolute(
        runtime_root, "LOCAL_SCHEDULER_RUNTIME_ROOT_INVALID"
    )
    python = _absolute(
        python_executable, "LOCAL_SCHEDULER_PYTHON_INVALID"
    )
    _validate_repository(repository)
    _validate_python(python)
    local_time = time.localtime()
    if (
        getattr(local_time, "tm_gmtoff", None) != 8 * 60 * 60
        or local_time.tm_isdst != 0
    ):
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_SYSTEM_TIMEZONE_INVALID"
        )
    worker = _worker(worker_id)
    key_path = _credential_path(
        api_key_file,
        repository_root=repository,
        runtime_root=runtime,
    )
    secret_path = _credential_path(
        api_secret_file,
        repository_root=repository,
        runtime_root=runtime,
    )
    if key_path == secret_path:
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_CREDENTIAL_PATH_INVALID"
        )
    payload = _plist_payload(
        repository_root=repository,
        runtime_root=runtime,
        python_executable=python,
        api_key_file=key_path,
        api_secret_file=secret_path,
        worker_id=worker,
    )
    body = _plist_bytes(payload)
    plist_hash = hashlib.sha256(body).hexdigest()
    identity = {
        "label": _LABEL,
        "repository_root": str(repository),
        "runtime_root": str(runtime),
        "plist_sha256": plist_hash,
    }
    contract = {
        "$schema": "./local-scheduler-contract-v1.schema.json",
        "schema_version": "1.0.0",
        "contract_id": stable_id("local_scheduler_contract", identity),
        "contract_hash": "",
        "created_at": _utc(created_at),
        "platform": "MACOS_LAUNCHD",
        "label": _LABEL,
        "repository_root": str(repository),
        "runtime_root": str(runtime),
        "python_executable": str(python),
        "worker_id": worker,
        "credential_file_paths": {
            "api_key_file": str(key_path),
            "api_secret_file": str(secret_path),
        },
        "cadence": {
            "time_basis": "SYSTEM_LOCAL_ASIA_SHANGHAI_UTC_PLUS_08",
            "utc_slot_hours": list(_HOURS),
            "local_launch_hours": list(_HOURS),
            "minute": _MINUTE,
            "run_at_load": True,
        },
        "program_arguments": list(payload["ProgramArguments"]),
        "environment_variable_names": [
            "PYTHONPATH",
            _KEY_ENV,
            _SECRET_ENV,
        ],
        "launchd_plist_sha256": plist_hash,
        "installation_status": "NOT_INSTALLED_NO_EXTERNAL_RECEIPT",
        "security_boundary": {
            "credential_values_read": False,
            "credential_values_in_plist": False,
            "credential_paths_owner_only_verified": True,
            "system_timezone_utc_plus_08_verified": True,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "launchctl_invoked": False,
            "orders_submitted": False,
        },
        "warnings": list(_WARNINGS),
    }
    contract["contract_hash"] = artifact_self_hash(
        contract, "contract_hash"
    )
    if tuple(_validator().iter_errors(contract)):
        raise LocalSchedulerError(
            "LOCAL_SCHEDULER_CONTRACT_SCHEMA_INVALID"
        )
    return contract, body


def local_scheduler_contract_trust_hash(
    contract: Mapping[str, Any],
) -> str:
    try:
        return business_hash(
            {
                "attestation_type": _ATTESTATION_TYPE,
                "contract_id": contract["contract_id"],
                "contract_hash": contract["contract_hash"],
                "launchd_plist_sha256": contract[
                    "launchd_plist_sha256"
                ],
                "installation_status": contract[
                    "installation_status"
                ],
            }
        )
    except (KeyError, TypeError):
        return ""


def local_scheduler_contract_reasons(
    contract: Mapping[str, Any],
    plist_bytes: bytes,
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(contract, Mapping):
        return ("LOCAL_SCHEDULER_CONTRACT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(contract)):
            reasons.append("LOCAL_SCHEDULER_CONTRACT_SCHEMA_INVALID")
        if artifact_self_hash(
            contract, "contract_hash"
        ) != contract.get("contract_hash"):
            reasons.append("LOCAL_SCHEDULER_CONTRACT_HASH_MISMATCH")
        if (
            local_scheduler_contract_trust_hash(contract)
            != trusted_attestation_hash
        ):
            reasons.append("LOCAL_SCHEDULER_CONTRACT_TRUST_MISMATCH")
        if hashlib.sha256(plist_bytes).hexdigest() != contract.get(
            "launchd_plist_sha256"
        ):
            reasons.append("LOCAL_SCHEDULER_PLIST_HASH_MISMATCH")
        expected_id = stable_id(
            "local_scheduler_contract",
            {
                "label": _LABEL,
                "repository_root": contract["repository_root"],
                "runtime_root": contract["runtime_root"],
                "plist_sha256": contract["launchd_plist_sha256"],
            },
        )
        if contract.get("contract_id") != expected_id:
            reasons.append("LOCAL_SCHEDULER_CONTRACT_ID_MISMATCH")
        parsed = plistlib.loads(plist_bytes)
        expected = _plist_payload(
            repository_root=Path(contract["repository_root"]),
            runtime_root=Path(contract["runtime_root"]),
            python_executable=Path(contract["python_executable"]),
            api_key_file=Path(
                contract["credential_file_paths"]["api_key_file"]
            ),
            api_secret_file=Path(
                contract["credential_file_paths"]["api_secret_file"]
            ),
            worker_id=contract["worker_id"],
        )
        if parsed != expected or _plist_bytes(expected) != plist_bytes:
            reasons.append("LOCAL_SCHEDULER_PLIST_REPLAY_MISMATCH")
        if contract.get("program_arguments") != list(
            expected["ProgramArguments"]
        ):
            reasons.append("LOCAL_SCHEDULER_ARGUMENTS_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        plistlib.InvalidFileException,
    ):
        reasons.append("LOCAL_SCHEDULER_CONTRACT_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))


def publish_local_scheduler_contract(
    *,
    output_root: Path,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    api_key_file: Path,
    api_secret_file: Path,
    worker_id: str,
    clock=None,
) -> Dict[str, Any]:
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    contract, plist_bytes = build_local_scheduler_contract(
        repository_root=repository_root,
        runtime_root=runtime_root,
        python_executable=python_executable,
        api_key_file=api_key_file,
        api_secret_file=api_secret_file,
        worker_id=worker_id,
        created_at=now,
    )
    trust = local_scheduler_contract_trust_hash(contract)
    if local_scheduler_contract_reasons(
        contract, plist_bytes, trust
    ):
        raise LocalSchedulerError("LOCAL_SCHEDULER_CONTRACT_INVALID")
    selected_output = Path(output_root)
    selected_runtime = Path(runtime_root).resolve()
    selected_runtime.mkdir(parents=True, exist_ok=True)
    os.chmod(selected_runtime, 0o700)
    for directory in ("state", "log", "artifacts"):
        path = selected_runtime / directory
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    plist_name = _LABEL + ".plist"
    contract_name = "local-scheduler-contract.json"
    plist_created = _publish_immutable(
        selected_output,
        plist_name,
        plist_bytes,
        output_directory="scheduler",
    )
    contract_bytes = json.dumps(
        contract, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    contract_created = _publish_immutable(
        selected_output,
        contract_name,
        contract_bytes,
        output_directory="scheduler",
    )
    plist_path = (
        selected_output.resolve() / "scheduler" / plist_name
    )
    contract_path = (
        selected_output.resolve() / "scheduler" / contract_name
    )
    os.chmod(plist_path.parent, 0o700)
    os.chmod(plist_path, 0o600)
    os.chmod(contract_path, 0o600)
    return {
        "outcome": "GENERATED_NOT_INSTALLED",
        "plist_path": str(plist_path),
        "plist_created": plist_created,
        "contract_path": str(contract_path),
        "contract_created": contract_created,
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "trust_hash": trust,
        "launchd_plist_sha256": contract["launchd_plist_sha256"],
        "installation_status": contract["installation_status"],
        "launchctl_invoked": False,
    }
