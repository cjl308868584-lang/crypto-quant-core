"""Deterministic, non-installing LaunchAgent contract for the live challenger."""

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
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-launchd-contract-v1.schema.json"
_LABEL = "local.crypto-quant.challenger-forward"
_TIMEZONE = "Asia/Shanghai"
_HOURS = (0, 4, 8, 12, 16, 20)
_MINUTE = 2
_ATTESTATION_TYPE = "CHALLENGER_LAUNCHD_CONTRACT_ATTESTATION"
_WARNINGS = (
    "LAUNCHAGENT_NOT_INSTALLED",
    "INSTALLATION_LOAD_AND_RUNTIME_RECEIPTS_REQUIRED",
    "SYSTEM_TIMEZONE_CHANGE_CAN_BREAK_UTC_ALIGNMENT",
    "BINANCE_TIME_RECEIPT_IS_NOT_INDEPENDENT_PUBLICATION",
    "NO_PROFITABILITY_CLAIM",
)


class ChallengerLaunchdError(ValueError):
    """The platform, path, plist, contract, or publication failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerLaunchdError(
                "CHALLENGER_LAUNCHD_TIME_INVALID"
            ) from error
    else:
        raise ChallengerLaunchdError("CHALLENGER_LAUNCHD_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerLaunchdError("CHALLENGER_LAUNCHD_TIME_INVALID")
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerLaunchdError("CHALLENGER_LAUNCHD_TIME_INVALID")
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerLaunchdError("CHALLENGER_LAUNCHD_TIME_INVALID")
    return rendered


def _absolute(
    value: object,
    reason: str,
    *,
    reject_symlink: bool = True,
) -> Path:
    if not isinstance(value, (str, Path)) or "\x00" in str(value):
        raise ChallengerLaunchdError(reason)
    raw = Path(value).expanduser()
    if (
        not raw.is_absolute()
        or (reject_symlink and raw.is_symlink())
    ):
        raise ChallengerLaunchdError(reason)
    return raw.resolve()


def _validate_repository(path: Path) -> None:
    required = (
        path / "pyproject.toml",
        path / "src" / "crypto_quant" / "challenger_forward_runner.py",
        path
        / "src"
        / "crypto_quant"
        / "challenger_forward_runner_cli.py",
    )
    if (
        not path.is_dir()
        or path.is_symlink()
        or not all(item.is_file() for item in required)
    ):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_REPOSITORY_INVALID"
        )


def _validate_python(path: Path) -> None:
    try:
        status = path.stat()
    except OSError as error:
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_PYTHON_INVALID"
        ) from error
    if (
        not stat.S_ISREG(status.st_mode)
        or not os.access(path, os.X_OK)
    ):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_PYTHON_INVALID"
        )


def _timezone_link_target() -> str:
    return os.readlink("/etc/localtime")


def _verify_system_timezone() -> str:
    try:
        target = _timezone_link_target()
        local = time.localtime()
    except OSError as error:
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_TIMEZONE_INVALID"
        ) from error
    if (
        not target.endswith("/" + _TIMEZONE)
        or getattr(local, "tm_gmtoff", None) != 8 * 60 * 60
        or local.tm_isdst != 0
    ):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_TIMEZONE_INVALID"
        )
    return _TIMEZONE


def _program_arguments(
    *,
    python_executable: Path,
    runtime_root: Path,
) -> Tuple[str, ...]:
    return (
        str(python_executable),
        "-m",
        "crypto_quant.challenger_forward_runner_cli",
        "--state-path",
        str(runtime_root / "state" / "challenger-forward.sqlite"),
        "--output-root",
        str(runtime_root / "artifacts"),
    )


def _plist_payload(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
) -> Dict[str, Any]:
    return {
        "Label": _LABEL,
        "ProgramArguments": list(
            _program_arguments(
                python_executable=python_executable,
                runtime_root=runtime_root,
            )
        ),
        "WorkingDirectory": str(repository_root),
        "EnvironmentVariables": {
            "PYTHONPATH": str(repository_root / "src"),
        },
        "StartCalendarInterval": [
            {"Hour": hour, "Minute": _MINUTE} for hour in _HOURS
        ],
        "RunAtLoad": True,
        "ProcessType": "Background",
        "ThrottleInterval": 60,
        "LowPriorityIO": True,
        "AbandonProcessGroup": True,
        "Umask": 0o077,
        "StandardOutPath": str(
            runtime_root / "log" / "challenger-forward.stdout.log"
        ),
        "StandardErrorPath": str(
            runtime_root / "log" / "challenger-forward.stderr.log"
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
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def build_challenger_launchd_contract(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    created_at: object,
) -> Tuple[Dict[str, Any], bytes]:
    repository = _absolute(
        repository_root, "CHALLENGER_LAUNCHD_REPOSITORY_INVALID"
    )
    runtime = _absolute(
        runtime_root, "CHALLENGER_LAUNCHD_RUNTIME_ROOT_INVALID"
    )
    python = _absolute(
        python_executable,
        "CHALLENGER_LAUNCHD_PYTHON_INVALID",
        reject_symlink=False,
    )
    _validate_repository(repository)
    _validate_python(python)
    timezone_name = _verify_system_timezone()
    payload = _plist_payload(
        repository_root=repository,
        runtime_root=runtime,
        python_executable=python,
    )
    body = _plist_bytes(payload)
    plist_hash = hashlib.sha256(body).hexdigest()
    identity = {
        "label": _LABEL,
        "repository_root": str(repository),
        "runtime_root": str(runtime),
        "python_executable": str(python),
        "launchd_plist_sha256": plist_hash,
    }
    contract = {
        "$schema": "./challenger-launchd-contract-v1.schema.json",
        "schema_version": "1.0.0",
        "contract_id": stable_id("challenger_launchd_contract", identity),
        "contract_hash": "0" * 64,
        "created_at": _utc(created_at),
        "platform": "MACOS_LAUNCHD",
        "label": _LABEL,
        "repository_root": str(repository),
        "runtime_root": str(runtime),
        "python_executable": str(python),
        "system_timezone": {
            "iana_name": timezone_name,
            "utc_offset_seconds": 28800,
            "daylight_saving_time_active": False,
        },
        "cadence": {
            "time_basis": "SYSTEM_LOCAL_ASIA_SHANGHAI_UTC_PLUS_08",
            "utc_slot_hours": list(_HOURS),
            "local_launch_hours": list(_HOURS),
            "minute": _MINUTE,
            "run_at_load": True,
        },
        "program_arguments": list(payload["ProgramArguments"]),
        "environment_variable_names": ["PYTHONPATH"],
        "launchd_plist_sha256": plist_hash,
        "installation_status": "NOT_INSTALLED_NO_EXTERNAL_RECEIPT",
        "security_boundary": {
            "credential_paths_present": False,
            "credential_values_present": False,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "launchctl_invoked": False,
            "network_scope": "BINANCE_PUBLIC_DATA_ONLY",
            "broker_access": False,
            "orders_submitted": False,
        },
        "warnings": list(_WARNINGS),
    }
    contract["contract_hash"] = artifact_self_hash(
        contract, "contract_hash"
    )
    if tuple(_validator().iter_errors(contract)):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_CONTRACT_SCHEMA_INVALID"
        )
    return contract, body


def challenger_launchd_contract_trust_hash(
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
                "installation_status": contract["installation_status"],
            }
        )
    except (KeyError, TypeError):
        return ""


def challenger_launchd_contract_reasons(
    contract: Mapping[str, Any],
    plist_bytes: bytes,
    trusted_attestation_hash: str,
) -> Tuple[str, ...]:
    if not isinstance(contract, Mapping):
        return ("CHALLENGER_LAUNCHD_CONTRACT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(contract)):
            reasons.append("CHALLENGER_LAUNCHD_CONTRACT_SCHEMA_INVALID")
        if contract.get("contract_hash") != artifact_self_hash(
            contract, "contract_hash"
        ):
            reasons.append("CHALLENGER_LAUNCHD_CONTRACT_HASH_MISMATCH")
        if (
            challenger_launchd_contract_trust_hash(contract)
            != trusted_attestation_hash
        ):
            reasons.append("CHALLENGER_LAUNCHD_CONTRACT_TRUST_MISMATCH")
        if (
            not isinstance(plist_bytes, bytes)
            or hashlib.sha256(plist_bytes).hexdigest()
            != contract["launchd_plist_sha256"]
        ):
            reasons.append("CHALLENGER_LAUNCHD_PLIST_HASH_MISMATCH")
        expected_id = stable_id(
            "challenger_launchd_contract",
            {
                "label": _LABEL,
                "repository_root": contract["repository_root"],
                "runtime_root": contract["runtime_root"],
                "python_executable": contract["python_executable"],
                "launchd_plist_sha256": contract[
                    "launchd_plist_sha256"
                ],
            },
        )
        if contract.get("contract_id") != expected_id:
            reasons.append("CHALLENGER_LAUNCHD_CONTRACT_ID_MISMATCH")
        expected = _plist_payload(
            repository_root=Path(contract["repository_root"]),
            runtime_root=Path(contract["runtime_root"]),
            python_executable=Path(contract["python_executable"]),
        )
        parsed = plistlib.loads(plist_bytes)
        if parsed != expected or _plist_bytes(expected) != plist_bytes:
            reasons.append("CHALLENGER_LAUNCHD_PLIST_REPLAY_MISMATCH")
        if contract.get("program_arguments") != list(
            expected["ProgramArguments"]
        ):
            reasons.append("CHALLENGER_LAUNCHD_ARGUMENTS_MISMATCH")
    except (
        KeyError,
        TypeError,
        ValueError,
        plistlib.InvalidFileException,
    ):
        reasons.append("CHALLENGER_LAUNCHD_CONTRACT_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))


def publish_challenger_launchd_contract(
    *,
    output_root: Path,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    clock=None,
) -> Mapping[str, Any]:
    created_at = (
        clock
        or (lambda: utc_datetime(datetime.now(timezone.utc)))
    )()
    contract, plist_bytes = build_challenger_launchd_contract(
        repository_root=repository_root,
        runtime_root=runtime_root,
        python_executable=python_executable,
        created_at=created_at,
    )
    trust_hash = challenger_launchd_contract_trust_hash(contract)
    if challenger_launchd_contract_reasons(
        contract, plist_bytes, trust_hash
    ):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_CONTRACT_INVALID"
        )
    runtime = Path(runtime_root).expanduser().resolve()
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(runtime, 0o700)
    for name in ("state", "log", "artifacts"):
        directory = runtime / name
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    requested_output = Path(output_root).expanduser()
    if not requested_output.is_absolute() or requested_output.is_symlink():
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_OUTPUT_INVALID"
        )
    directory = requested_output.resolve() / "challenger-scheduler"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    plist_path = directory / f"{_LABEL}.plist"
    contract_path = directory / "challenger-launchd-contract.json"
    try:
        _publish_exact(plist_path, plist_bytes)
        _publish_exact(
            contract_path, canonical_json(contract).encode("utf-8")
        )
    except ValueError as error:
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_PUBLISH_CONFLICT"
        ) from error
    return {
        "outcome": "GENERATED_NOT_INSTALLED",
        "plist_path": str(plist_path),
        "contract_path": str(contract_path),
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": trust_hash,
        "launchd_plist_sha256": contract["launchd_plist_sha256"],
        "installation_status": contract["installation_status"],
        "launchctl_invoked": False,
    }


def load_challenger_launchd_contract(
    *, contract_path: Path, plist_path: Path
) -> Mapping[str, Any]:
    try:
        contract = _strict_json_bytes(
            Path(contract_path).expanduser().resolve().read_bytes()
        )
        plist_bytes = Path(plist_path).expanduser().resolve().read_bytes()
    except (OSError, ValueError) as error:
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_READ_FAILED"
        ) from error
    trust_hash = challenger_launchd_contract_trust_hash(contract)
    if challenger_launchd_contract_reasons(
        contract, plist_bytes, trust_hash
    ):
        raise ChallengerLaunchdError(
            "CHALLENGER_LAUNCHD_CONTRACT_INVALID"
        )
    return contract
