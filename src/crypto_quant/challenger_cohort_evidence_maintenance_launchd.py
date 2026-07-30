"""Deterministic, non-installing LaunchAgent for cohort evidence maintenance."""

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
from xml.parsers.expat import ExpatError

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_cohort_economic_results import read_exact_economic_plan
from .challenger_cohort_episode_receipt import _read_exact_plan
from .challenger_launchd import (
    challenger_launchd_contract_trust_hash,
    load_challenger_launchd_contract,
)
from .challenger_launchd_install import load_challenger_install_receipt
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = (
    "challenger-cohort-evidence-maintenance-launchd-contract-v1.schema.json"
)
_LABEL = "local.crypto-quant.challenger-cohort-evidence-maintenance"
_TIMEZONE = "Asia/Shanghai"
_HOUR = 8
_MINUTE = 10
_ATTESTATION_TYPE = (
    "CHALLENGER_COHORT_EVIDENCE_MAINTENANCE_LAUNCHD_"
    "CONTRACT_ATTESTATION"
)
_OUTPUT_DIRECTORY = "challenger-cohort-evidence-maintenance-scheduler"
_COHORT_PLAN = (
    "artifacts/challenger-forward/"
    "challenger-episode-cohort-plan-v0.43.0.json"
)
_ECONOMIC_PLAN = (
    "artifacts/challenger-forward/"
    "challenger-episode-economic-plan-v0.37.0.json"
)
_WARNINGS = (
    "LAUNCHAGENT_NOT_INSTALLED",
    "INSTALLATION_PRIVATE_SNAPSHOT_AND_RUNTIME_RECEIPTS_REQUIRED",
    "SYSTEM_TIMEZONE_CHANGE_CAN_BREAK_UTC_ALIGNMENT",
    "MAINTENANCE_RUN_DOES_NOT_TRIGGER_STRATEGY_RUNNER",
    "NO_PROFITABILITY_CLAIM",
    "NO_SYSTEM_PAPER_OR_AI_ADVANTAGE_CLAIM",
)


class ChallengerCohortEvidenceMaintenanceLaunchdError(ValueError):
    """The maintenance LaunchAgent contract failed closed."""

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
            raise ChallengerCohortEvidenceMaintenanceLaunchdError(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIME_INVALID"
        )
    return rendered


def _absolute(
    value: object,
    reason: str,
    *,
    reject_symlink: bool = True,
) -> Path:
    if not isinstance(value, (str, Path)) or "\x00" in str(value):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(reason)
    raw = Path(value).expanduser()
    if not raw.is_absolute() or (reject_symlink and raw.is_symlink()):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(reason)
    return raw.resolve()


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
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            reason
        ) from error


def _validate_repository(path: Path) -> Tuple[Path, Path, str, str]:
    cohort_plan = path / _COHORT_PLAN
    economic_plan = path / _ECONOMIC_PLAN
    required = (
        path / "pyproject.toml",
        path
        / "src"
        / "crypto_quant"
        / "challenger_cohort_evidence_maintenance.py",
        path
        / "src"
        / "crypto_quant"
        / "challenger_cohort_evidence_maintenance_cli.py",
        cohort_plan,
        economic_plan,
    )
    if (
        not path.is_dir()
        or path.is_symlink()
        or not all(item.is_file() and not item.is_symlink() for item in required)
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_REPOSITORY_INVALID"
        )
    try:
        _cohort, cohort_sha = _read_exact_plan(cohort_plan)
        _economic, economic_sha = read_exact_economic_plan(economic_plan)
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PLAN_INVALID"
        ) from error
    return cohort_plan, economic_plan, cohort_sha, economic_sha


def _validate_runtime(path: Path) -> None:
    if not path.is_dir() or path.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_RUNTIME_INVALID"
        )
    status = path.stat()
    if (
        status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) not in (0o700, 0o755)
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_RUNTIME_INVALID"
        )


def _validate_python(path: Path) -> None:
    try:
        status = path.stat()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PYTHON_INVALID"
        ) from error
    if not stat.S_ISREG(status.st_mode) or not os.access(path, os.X_OK):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PYTHON_INVALID"
        )


def _timezone_link_target() -> str:
    return os.readlink("/etc/localtime")


def _verify_system_timezone() -> str:
    try:
        target = _timezone_link_target()
        local = time.localtime()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIMEZONE_INVALID"
        ) from error
    if (
        not target.endswith("/" + _TIMEZONE)
        or getattr(local, "tm_gmtoff", None) != 8 * 60 * 60
        or local.tm_isdst != 0
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIMEZONE_INVALID"
        )
    return _TIMEZONE


def _trusted_strategy(
    *,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    loader=None,
) -> Mapping[str, Any]:
    install_path = _secure_file(
        install_receipt_path,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TRUST_INVALID",
    )
    strategy_contract_path = _secure_file(
        contract_path,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TRUST_INVALID",
    )
    strategy_plist_path = _secure_file(
        plist_path,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TRUST_INVALID",
    )
    try:
        if loader is None:
            contract = load_challenger_launchd_contract(
                contract_path=strategy_contract_path,
                plist_path=strategy_plist_path,
            )
            receipt = load_challenger_install_receipt(
                receipt_path=install_path,
                contract_path=strategy_contract_path,
                plist_path=strategy_plist_path,
            )
        else:
            contract, receipt = loader(
                install_receipt_path=install_path,
                contract_path=strategy_contract_path,
                plist_path=strategy_plist_path,
            )
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TRUST_INVALID"
        ) from error
    return {
        "install_receipt_path": str(install_path),
        "install_receipt_file_sha256": hashlib.sha256(
            install_path.read_bytes()
        ).hexdigest(),
        "install_receipt_id": receipt["receipt_id"],
        "install_receipt_hash": receipt["receipt_hash"],
        "strategy_contract_path": str(strategy_contract_path),
        "strategy_contract_file_sha256": hashlib.sha256(
            strategy_contract_path.read_bytes()
        ).hexdigest(),
        "strategy_contract_id": contract["contract_id"],
        "strategy_contract_hash": contract["contract_hash"],
        "strategy_contract_trust_hash": (
            challenger_launchd_contract_trust_hash(contract)
        ),
        "strategy_plist_path": str(strategy_plist_path),
        "strategy_plist_file_sha256": hashlib.sha256(
            strategy_plist_path.read_bytes()
        ).hexdigest(),
    }


def _program_arguments(
    *,
    python_executable: Path,
    cohort_plan_path: Path,
    economic_plan_path: Path,
    runtime_root: Path,
    strategy_trust: Mapping[str, Any],
) -> Tuple[str, ...]:
    return (
        str(python_executable),
        "-m",
        "crypto_quant.challenger_cohort_evidence_maintenance_cli",
        "--cohort-plan-path",
        str(cohort_plan_path),
        "--economic-plan-path",
        str(economic_plan_path),
        "--episode-receipt-output-root",
        str(runtime_root / "cohort-receipts"),
        "--install-receipt-path",
        strategy_trust["install_receipt_path"],
        "--contract-path",
        strategy_trust["strategy_contract_path"],
        "--plist-path",
        strategy_trust["strategy_plist_path"],
        "--archive-output-root",
        str(runtime_root / "cohort-archives"),
        "--result-output-root",
        str(runtime_root / "cohort-results"),
    )


def _plist_payload(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    cohort_plan_path: Path,
    economic_plan_path: Path,
    strategy_trust: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "Label": _LABEL,
        "ProgramArguments": list(
            _program_arguments(
                python_executable=python_executable,
                cohort_plan_path=cohort_plan_path,
                economic_plan_path=economic_plan_path,
                runtime_root=runtime_root,
                strategy_trust=strategy_trust,
            )
        ),
        "WorkingDirectory": str(repository_root),
        "EnvironmentVariables": {
            "PYTHONPATH": str(repository_root / "src"),
        },
        "StartCalendarInterval": [{"Hour": _HOUR, "Minute": _MINUTE}],
        "RunAtLoad": False,
        "ProcessType": "Background",
        "ThrottleInterval": 60,
        "LowPriorityIO": True,
        "AbandonProcessGroup": True,
        "Umask": 0o077,
        "StandardOutPath": str(
            runtime_root
            / "log"
            / "challenger-cohort-evidence-maintenance.stdout.log"
        ),
        "StandardErrorPath": str(
            runtime_root
            / "log"
            / "challenger-cohort-evidence-maintenance.stderr.log"
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


def build_challenger_cohort_evidence_maintenance_launchd_contract(
    *,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    created_at: object,
    _strategy_loader=None,
) -> Tuple[Dict[str, Any], bytes]:
    repository = _absolute(
        repository_root,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_REPOSITORY_INVALID",
    )
    runtime = _absolute(
        runtime_root,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_RUNTIME_INVALID",
    )
    python = _absolute(
        python_executable,
        "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PYTHON_INVALID",
        reject_symlink=False,
    )
    cohort_plan, economic_plan, cohort_sha, economic_sha = (
        _validate_repository(repository)
    )
    _validate_runtime(runtime)
    _validate_python(python)
    timezone_name = _verify_system_timezone()
    strategy_trust = _trusted_strategy(
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        loader=_strategy_loader,
    )
    payload = _plist_payload(
        repository_root=repository,
        runtime_root=runtime,
        python_executable=python,
        cohort_plan_path=cohort_plan,
        economic_plan_path=economic_plan,
        strategy_trust=strategy_trust,
    )
    body = _plist_bytes(payload)
    plist_hash = hashlib.sha256(body).hexdigest()
    plans = {
        "cohort_plan_path": str(cohort_plan),
        "cohort_plan_file_sha256": cohort_sha,
        "economic_plan_path": str(economic_plan),
        "economic_plan_file_sha256": economic_sha,
    }
    identity = {
        "label": _LABEL,
        "repository_root": str(repository),
        "runtime_root": str(runtime),
        "python_executable": str(python),
        "plans": plans,
        "strategy_trust": strategy_trust,
        "launchd_plist_sha256": plist_hash,
    }
    contract = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "contract_id": stable_id(
            "challenger_cohort_evidence_maintenance_launchd_contract",
            identity,
        ),
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
            "local_launch_hour": _HOUR,
            "local_launch_minute": _MINUTE,
            "utc_launch_hour": 0,
            "utc_launch_minute": _MINUTE,
            "run_at_load": False,
        },
        "plans": plans,
        "strategy_trust": strategy_trust,
        "program_arguments": list(payload["ProgramArguments"]),
        "environment_variable_names": ["PYTHONPATH"],
        "log_paths": {
            "stdout": payload["StandardOutPath"],
            "stderr": payload["StandardErrorPath"],
        },
        "launchd_plist_sha256": plist_hash,
        "installation_status": "NOT_INSTALLED_NO_EXTERNAL_RECEIPT",
        "security_boundary": {
            "credential_paths_present": False,
            "credential_values_present": False,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "launchctl_invoked": False,
            "render_network_request_count": 0,
            "maintenance_network_scope": (
                "BINANCE_OFFICIAL_DAILY_ARCHIVES_TIME_GATED_ONLY"
            ),
            "broker_access": False,
            "orders_submitted": False,
            "strategy_state_write_count": 0,
            "runner_invocation_count": 0,
            "cumulative_evaluation_invocation_count": 0,
        },
        "warnings": list(_WARNINGS),
    }
    contract["contract_hash"] = artifact_self_hash(
        contract, "contract_hash"
    )
    if tuple(_validator().iter_errors(contract)):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_SCHEMA_INVALID"
        )
    return contract, body


def challenger_cohort_evidence_maintenance_launchd_trust_hash(
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


def challenger_cohort_evidence_maintenance_launchd_reasons(
    contract: Mapping[str, Any],
    plist_bytes: bytes,
    trusted_attestation_hash: str,
    *,
    _strategy_loader=None,
) -> Tuple[str, ...]:
    if not isinstance(contract, Mapping):
        return ("CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(contract)):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_SCHEMA_INVALID"
            )
        if contract.get("contract_hash") != artifact_self_hash(
            contract, "contract_hash"
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_HASH_MISMATCH"
            )
        if (
            challenger_cohort_evidence_maintenance_launchd_trust_hash(
                contract
            )
            != trusted_attestation_hash
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TRUST_MISMATCH"
            )
        if (
            not isinstance(plist_bytes, bytes)
            or hashlib.sha256(plist_bytes).hexdigest()
            != contract["launchd_plist_sha256"]
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PLIST_HASH_MISMATCH"
            )
        repository = Path(contract["repository_root"])
        runtime = Path(contract["runtime_root"])
        python = Path(contract["python_executable"])
        _validate_runtime(runtime)
        _validate_python(python)
        timezone_name = _verify_system_timezone()
        if contract.get("system_timezone") != {
            "iana_name": timezone_name,
            "utc_offset_seconds": 28800,
            "daylight_saving_time_active": False,
        }:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_TIMEZONE_MISMATCH"
            )
        cohort_plan, economic_plan, cohort_sha, economic_sha = (
            _validate_repository(repository)
        )
        strategy_trust = _trusted_strategy(
            install_receipt_path=Path(
                contract["strategy_trust"]["install_receipt_path"]
            ),
            contract_path=Path(
                contract["strategy_trust"]["strategy_contract_path"]
            ),
            plist_path=Path(
                contract["strategy_trust"]["strategy_plist_path"]
            ),
            loader=_strategy_loader,
        )
        plans = {
            "cohort_plan_path": str(cohort_plan),
            "cohort_plan_file_sha256": cohort_sha,
            "economic_plan_path": str(economic_plan),
            "economic_plan_file_sha256": economic_sha,
        }
        expected_payload = _plist_payload(
            repository_root=repository,
            runtime_root=runtime,
            python_executable=python,
            cohort_plan_path=cohort_plan,
            economic_plan_path=economic_plan,
            strategy_trust=strategy_trust,
        )
        expected_id = stable_id(
            "challenger_cohort_evidence_maintenance_launchd_contract",
            {
                "label": _LABEL,
                "repository_root": str(repository),
                "runtime_root": str(runtime),
                "python_executable": str(python),
                "plans": plans,
                "strategy_trust": strategy_trust,
                "launchd_plist_sha256": contract[
                    "launchd_plist_sha256"
                ],
            },
        )
        if contract.get("contract_id") != expected_id:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_ID_MISMATCH"
            )
        if contract.get("plans") != plans:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PLAN_MISMATCH"
            )
        if contract.get("strategy_trust") != strategy_trust:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_SOURCE_MISMATCH"
            )
        parsed = plistlib.loads(plist_bytes)
        if (
            parsed != expected_payload
            or _plist_bytes(expected_payload) != plist_bytes
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PLIST_REPLAY_MISMATCH"
            )
        if contract.get("program_arguments") != list(
            expected_payload["ProgramArguments"]
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_ARGUMENTS_MISMATCH"
            )
        if contract.get("log_paths") != {
            "stdout": expected_payload["StandardOutPath"],
            "stderr": expected_payload["StandardErrorPath"],
        }:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_LOG_MISMATCH"
            )
    except (
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        KeyError,
        TypeError,
        ValueError,
        ExpatError,
        plistlib.InvalidFileException,
    ):
        reasons.append(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_REPLAY_INVALID"
        )
    return tuple(sorted(set(reasons)))


def publish_challenger_cohort_evidence_maintenance_launchd_contract(
    *,
    output_root: Path,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    clock=None,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    created_at = (
        clock
        or (lambda: utc_datetime(datetime.now(timezone.utc)))
    )()
    contract, plist_bytes = (
        build_challenger_cohort_evidence_maintenance_launchd_contract(
            repository_root=repository_root,
            runtime_root=runtime_root,
            python_executable=python_executable,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            created_at=created_at,
            _strategy_loader=_strategy_loader,
        )
    )
    trust_hash = (
        challenger_cohort_evidence_maintenance_launchd_trust_hash(contract)
    )
    if challenger_cohort_evidence_maintenance_launchd_reasons(
        contract,
        plist_bytes,
        trust_hash,
        _strategy_loader=_strategy_loader,
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_INVALID"
        )
    runtime = Path(runtime_root).expanduser().resolve()
    log_root = runtime / "log"
    log_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(log_root, 0o700)
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_OUTPUT_INVALID"
        )
    requested.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(requested, 0o700)
    requested_status = requested.lstat()
    if (
        not stat.S_ISDIR(requested_status.st_mode)
        or stat.S_ISLNK(requested_status.st_mode)
        or requested_status.st_uid != os.getuid()
        or stat.S_IMODE(requested_status.st_mode) != 0o700
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_OUTPUT_INVALID"
        )
    directory = requested.resolve(strict=True) / _OUTPUT_DIRECTORY
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    plist_output = directory / f"{_LABEL}.plist"
    contract_output = directory / "maintenance-launchd-contract.json"
    expected = {plist_output.name, contract_output.name}
    if any(path.name not in expected for path in directory.iterdir()):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_INVENTORY_INVALID"
        )
    try:
        _publish_exact(plist_output, plist_bytes)
        _publish_exact(
            contract_output, canonical_json(contract).encode("utf-8")
        )
    except ValueError as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_PUBLISH_CONFLICT"
        ) from error
    for path in (plist_output, contract_output):
        os.chmod(path, 0o600)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
        ):
            raise ChallengerCohortEvidenceMaintenanceLaunchdError(
                "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_OUTPUT_INVALID"
            )
    return {
        "outcome": "GENERATED_NOT_INSTALLED",
        "plist_path": str(plist_output),
        "contract_path": str(contract_output),
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": trust_hash,
        "launchd_plist_sha256": contract["launchd_plist_sha256"],
        "installation_status": contract["installation_status"],
        "render_network_request_count": 0,
        "launchctl_invoked": False,
    }


def load_challenger_cohort_evidence_maintenance_launchd_contract(
    *,
    contract_path: Path,
    plist_path: Path,
    trusted_attestation_hash: str,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    try:
        contract_file = _secure_file(
            contract_path,
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_READ_FAILED",
        )
        plist_file = _secure_file(
            plist_path,
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_READ_FAILED",
        )
        contract = _strict_json_bytes(contract_file.read_bytes())
        plist_bytes = plist_file.read_bytes()
    except (
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        OSError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_READ_FAILED"
        ) from error
    if challenger_cohort_evidence_maintenance_launchd_reasons(
        contract,
        plist_bytes,
        trusted_attestation_hash,
        _strategy_loader=_strategy_loader,
    ):
        raise ChallengerCohortEvidenceMaintenanceLaunchdError(
            "CHALLENGER_COHORT_MAINTENANCE_LAUNCHD_INVALID"
        )
    return contract
