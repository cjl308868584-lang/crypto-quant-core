"""Read-only observer for the first natural cohort maintenance run."""

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_cohort_evidence_maintenance_install import (
    ChallengerCohortEvidenceMaintenanceInstallError,
    MaintenanceLaunchctlResult,
    _command_evidence,
    _command_evidence_valid,
    _command_runner,
    _print_bindings_valid,
    load_challenger_cohort_evidence_maintenance_install_receipt,
)
from .challenger_cohort_evidence_maintenance_launchd import (
    ChallengerCohortEvidenceMaintenanceLaunchdError,
    load_challenger_cohort_evidence_maintenance_launchd_contract,
)
from .challenger_first_slot_receipt import _paths
from .challenger_launchd import load_challenger_launchd_contract
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = (
    "challenger-cohort-evidence-maintenance-first-run-receipt-v1.schema.json"
)
_LAUNCHCTL = "/bin/launchctl"
_LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
_DEADLINE = timedelta(minutes=10)
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_INVENTORY_FILES = 10000
_MAX_INVENTORY_BYTES = 64 * 1024 * 1024
_SUCCESS_STATUSES = frozenset(
    {
        "COHORT_EVIDENCE_NO_COMPLETED_EPISODES",
        "COHORT_EVIDENCE_WAITING_ARCHIVES",
        "COHORT_EVIDENCE_MAINTAINED_DESCRIPTIVE_NO_EARLY_SUCCESS",
    }
)
_WARNINGS = (
    "FIRST_NATURAL_MAINTENANCE_RUN_DOES_NOT_PROVE_COHORT_COMPLETENESS",
    "MAINTENANCE_SUMMARY_IS_RESEARCH_EVIDENCE_NOT_PROFITABILITY_PROOF",
    "NO_SYSTEM_PAPER_OR_AI_ADVANTAGE_CLAIM",
)


class ChallengerCohortEvidenceMaintenanceFirstRunError(ValueError):
    """The first natural maintenance observation failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerCohortEvidenceMaintenanceFirstRunError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_TIME_INVALID"
        )
    return converted, rendered


def _file_evidence(path: Path, *, allow_missing: bool) -> Mapping[str, Any]:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_FILE_INVALID"
        )
    try:
        resolved = selected.resolve()
        if not resolved.exists():
            if allow_missing:
                return {"path": str(resolved), "exists": False}
            raise ValueError
        before = resolved.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or before.st_size > _MAX_FILE_BYTES
        ):
            raise ValueError
        body = resolved.read_bytes()
        after = resolved.lstat()
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
        ):
            raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_FILE_INVALID"
        ) from error
    return {
        "path": str(resolved),
        "exists": True,
        "device": after.st_dev,
        "inode": after.st_ino,
        "owner_uid": after.st_uid,
        "mode_octal": f"{stat.S_IMODE(after.st_mode):04o}",
        "link_count": after.st_nlink,
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _inventory(path: Path) -> Mapping[str, Any]:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_INVENTORY_INVALID"
        )
    resolved = selected.resolve()
    if not resolved.exists():
        return {
            "path": str(resolved),
            "exists": False,
            "file_count": 0,
            "total_bytes": 0,
            "files": [],
            "inventory_hash": hashlib.sha256(b"[]").hexdigest(),
        }
    try:
        root_stat = resolved.lstat()
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or stat.S_ISLNK(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
            or stat.S_IMODE(root_stat.st_mode) & 0o022
        ):
            raise ValueError
        entries = []
        total = 0
        for candidate in sorted(resolved.rglob("*")):
            status = candidate.lstat()
            if stat.S_ISDIR(status.st_mode):
                if (
                    stat.S_ISLNK(status.st_mode)
                    or status.st_uid != os.getuid()
                    or stat.S_IMODE(status.st_mode) & 0o022
                ):
                    raise ValueError
                continue
            if (
                not stat.S_ISREG(status.st_mode)
                or stat.S_ISLNK(status.st_mode)
                or status.st_uid != os.getuid()
                or status.st_nlink != 1
                or stat.S_IMODE(status.st_mode) & 0o022
            ):
                raise ValueError
            body = candidate.read_bytes()
            if len(body) != status.st_size:
                raise ValueError
            total += len(body)
            entries.append(
                {
                    "path": candidate.relative_to(resolved).as_posix(),
                    "size_bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            if (
                len(entries) > _MAX_INVENTORY_FILES
                or total > _MAX_INVENTORY_BYTES
            ):
                raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_INVENTORY_INVALID"
        ) from error
    encoded = canonical_json(entries).encode("utf-8")
    return {
        "path": str(resolved),
        "exists": True,
        "file_count": len(entries),
        "total_bytes": total,
        "files": entries,
        "inventory_hash": hashlib.sha256(encoded).hexdigest(),
    }


def _file_prefix_valid(
    observed: Mapping[str, Any],
    path: Path,
) -> bool:
    if observed.get("path") != str(Path(path).expanduser().resolve()):
        return False
    if observed.get("exists") is False:
        return True
    try:
        current = _file_evidence(path, allow_missing=False)
        size = observed["size_bytes"]
        prefix = Path(path).read_bytes()[:size]
        return (
            current["size_bytes"] >= size
            and hashlib.sha256(prefix).hexdigest() == observed["sha256"]
        )
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        KeyError,
        OSError,
        TypeError,
    ):
        return False


def _inventory_prefix_valid(
    observed: Mapping[str, Any],
    path: Path,
) -> bool:
    if observed.get("path") != str(Path(path).expanduser().resolve()):
        return False
    if observed.get("exists") is False:
        return True
    try:
        current = _inventory(path)
        current_by_path = {
            item["path"]: item for item in current["files"]
        }
        return all(
            current_by_path.get(item["path"]) == item
            for item in observed["files"]
        )
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        KeyError,
        TypeError,
    ):
        return False


def _argument_value(arguments: Sequence[str], flag: str) -> Path:
    if list(arguments).count(flag) != 1:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_CONTRACT_INVALID"
        )
    index = list(arguments).index(flag)
    try:
        value = Path(arguments[index + 1])
    except (IndexError, TypeError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_CONTRACT_INVALID"
        ) from error
    if not value.is_absolute():
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_CONTRACT_INVALID"
        )
    return value.resolve()


def _load_sources(
    *,
    install_receipt_path: Path,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    try:
        manifest_file = Path(manifest_path).expanduser().resolve(strict=True)
        manifest = _strict_json_bytes(manifest_file.read_bytes())
        candidate = manifest["install_candidate"]
        contract_path = Path(candidate["contract_path"])
        plist_path = Path(candidate["plist_path"])
        contract = (
            load_challenger_cohort_evidence_maintenance_launchd_contract(
                contract_path=contract_path,
                plist_path=plist_path,
                trusted_attestation_hash=(
                    trusted_candidate_attestation_hash
                ),
            )
        )
        receipt = (
            load_challenger_cohort_evidence_maintenance_install_receipt(
                receipt_path=Path(install_receipt_path),
                manifest_path=manifest_file,
                trusted_source_attestation_hash=(
                    trusted_source_attestation_hash
                ),
                trusted_candidate_attestation_hash=(
                    trusted_candidate_attestation_hash
                ),
            )
        )
    except (
        ChallengerCohortEvidenceMaintenanceInstallError,
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SOURCE_INVALID"
        ) from error
    if (
        receipt["source_deployment"]["manifest_hash"]
        != manifest["manifest_hash"]
        or receipt["source_contract"]["contract_hash"]
        != contract["contract_hash"]
        or contract["cadence"]["run_at_load"] is not False
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SOURCE_INVALID"
        )
    return manifest, contract, receipt


def _schedule(
    receipt: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> Tuple[datetime, str, str]:
    verified, _ = _utc(receipt["verified_at"])
    cadence = contract["cadence"]
    local = verified.astimezone(_LOCAL_ZONE)
    candidate = local.replace(
        hour=cadence["local_launch_hour"],
        minute=cadence["local_launch_minute"],
        second=0,
        microsecond=0,
    )
    if candidate <= local:
        candidate += timedelta(days=1)
    scheduled = candidate.astimezone(timezone.utc)
    deadline = scheduled + _DEADLINE
    return scheduled, utc_datetime(scheduled), utc_datetime(deadline)


def _observation_paths(
    contract: Mapping[str, Any],
) -> Mapping[str, Path]:
    arguments = contract["program_arguments"]
    strategy_contract_path = Path(
        contract["strategy_trust"]["strategy_contract_path"]
    )
    strategy_plist_path = Path(
        contract["strategy_trust"]["strategy_plist_path"]
    )
    try:
        strategy_contract = load_challenger_launchd_contract(
            contract_path=strategy_contract_path,
            plist_path=strategy_plist_path,
        )
        strategy = _paths(strategy_contract)
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_STRATEGY_SOURCE_INVALID"
        ) from error
    return {
        "strategy_state": strategy["state"],
        "strategy_stdout": strategy["stdout"],
        "strategy_stderr": strategy["stderr"],
        "maintenance_stdout": Path(contract["log_paths"]["stdout"]).resolve(),
        "maintenance_stderr": Path(contract["log_paths"]["stderr"]).resolve(),
        "receipt_root": _argument_value(
            arguments, "--episode-receipt-output-root"
        ),
        "archive_root": _argument_value(
            arguments, "--archive-output-root"
        ),
        "result_root": _argument_value(
            arguments, "--result-output-root"
        ),
    }


def _snapshot(paths: Mapping[str, Path]) -> Mapping[str, Any]:
    return {
        "strategy_state": _file_evidence(
            paths["strategy_state"], allow_missing=False
        ),
        "strategy_stdout": _file_evidence(
            paths["strategy_stdout"], allow_missing=False
        ),
        "strategy_stderr": _file_evidence(
            paths["strategy_stderr"], allow_missing=False
        ),
        "maintenance_stdout": _file_evidence(
            paths["maintenance_stdout"], allow_missing=True
        ),
        "maintenance_stderr": _file_evidence(
            paths["maintenance_stderr"], allow_missing=True
        ),
        "receipt_inventory": _inventory(paths["receipt_root"]),
        "archive_inventory": _inventory(paths["archive_root"]),
        "result_inventory": _inventory(paths["result_root"]),
    }


def _launchctl(
    *,
    runner,
    contract: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], int, str, str]:
    argv = (_LAUNCHCTL, "print", receipt["service"])
    try:
        result = runner(argv)
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_LAUNCHCTL_FAILED"
        ) from error
    if not isinstance(result, MaintenanceLaunchctlResult):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_LAUNCHCTL_FAILED"
        )
    evidence = _command_evidence(argv, result)
    text = result.stdout.decode("utf-8")
    runs = re.findall(r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)", text)
    exits = re.findall(
        r"(?:^|\n)[ \t]*last exit code = ([^\n]+)(?:\n|$)", text
    )
    states = re.findall(
        r"(?:^|\n)[ \t]*state = ([^\n]+)(?:\n|$)", text
    )
    if (
        result.returncode != 0
        or len(runs) != 1
        or len(exits) != 1
        or len(states) != 1
        or not _print_bindings_valid(
            result.stdout,
            contract=contract,
            domain=receipt["domain"],
            target=Path(receipt["target_path"]),
        )
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SERVICE_INVALID"
        )
    return (
        evidence,
        int(runs[0]),
        exits[0].strip(),
        states[0].strip(),
    )


def _nonnegative(source: Mapping[str, Any], key: str) -> int:
    value = source.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        )
    return value


def _summary(data: bytes, *, scheduled: datetime, observed: datetime):
    try:
        text = data.decode("utf-8")
        lines = [line for line in text.splitlines() if line]
        if len(lines) != 1:
            raise ValueError
        summary = json.loads(lines[0])
        if not isinstance(summary, Mapping):
            raise ValueError
        summary_time, _ = _utc(summary["observed_at"])
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        KeyError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        ) from error
    if (
        summary.get("status") not in _SUCCESS_STATUSES
        or summary_time < scheduled
        or summary_time > observed
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        )
    for key in (
        "broker_request_count",
        "order_submission_count",
        "strategy_state_write_count",
        "runner_invocation_count",
    ):
        if _nonnegative(summary, key) != 0:
            raise ChallengerCohortEvidenceMaintenanceFirstRunError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
            )
    network = _nonnegative(summary, "network_request_count")
    receipt_stage = summary.get("receipt_stage")
    archive_stage = summary.get("archive_stage")
    result_stage = summary.get("result_stage")
    if not all(
        isinstance(item, Mapping)
        for item in (receipt_stage, archive_stage, result_stage)
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        )
    completed = _nonnegative(receipt_stage, "completed_episode_count")
    created = _nonnegative(receipt_stage, "receipt_created_count")
    required = _nonnegative(archive_stage, "required_day_count")
    verified = _nonnegative(archive_stage, "verified_day_count")
    if (
        receipt_stage.get("executed") is not True
        or archive_stage.get("executed") is not True
        or created > completed
        or verified > required
        or _nonnegative(archive_stage, "network_request_count") != network
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        )
    status = summary["status"]
    if status == "COHORT_EVIDENCE_NO_COMPLETED_EPISODES":
        valid = (
            completed == required == verified == 0
            and archive_stage.get("status")
            == "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES"
            and result_stage
            == {
                "executed": False,
                "status": "NOT_EXECUTED_NO_COMPLETED_EPISODES",
            }
        )
    elif status == "COHORT_EVIDENCE_WAITING_ARCHIVES":
        valid = (
            completed > 0
            and archive_stage.get("status")
            in {
                "COHORT_DAILY_ARCHIVE_PENDING",
                "COHORT_DAILY_ARCHIVE_PARTIAL",
            }
            and result_stage
            == {
                "executed": False,
                "status": "NOT_EXECUTED_ARCHIVES_INCOMPLETE",
            }
        )
    else:
        valid = (
            completed > 0
            and required > 0
            and verified == required
            and archive_stage.get("status")
            == "COHORT_DAILY_ARCHIVE_COMPLETE"
            and result_stage.get("executed") is True
            and result_stage.get("status")
            == "DESCRIPTIVE_NO_EARLY_SUCCESS"
            and _nonnegative(result_stage, "result_count") == completed
            and _nonnegative(result_stage, "index_count") == completed
        )
    if not valid:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_SUMMARY_INVALID"
        )
    return summary


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def maintenance_first_run_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "install_receipt_hash": receipt["install_receipt"]["receipt_hash"],
        "manifest_hash": receipt["deployment"]["manifest_hash"],
        "contract_hash": receipt["contract"]["contract_hash"],
        "scheduled_for": receipt["first_natural_scheduled_for"],
        "observed_at": receipt["observed_at"],
        "launchctl_print_hash": receipt["launchctl_print"][
            "command_evidence_hash"
        ],
        "stdout_hash": receipt["observation"]["maintenance_stdout"][
            "sha256"
        ],
        "receipt_inventory_hash": receipt["observation"][
            "receipt_inventory"
        ]["inventory_hash"],
        "archive_inventory_hash": receipt["observation"][
            "archive_inventory"
        ]["inventory_hash"],
        "result_inventory_hash": receipt["observation"][
            "result_inventory"
        ]["inventory_hash"],
    }


def _publish(receipt: Mapping[str, Any], output_root: Path) -> Path:
    root = Path(output_root).expanduser()
    if not root.is_absolute() or root.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_OUTPUT_INVALID"
        )
    directory = root.resolve() / "maintenance-first-run-receipts"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        status = directory.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) != 0o700
        ):
            raise ValueError
        path = directory / f"{receipt['receipt_id']}.json"
        _publish_exact(path, canonical_json(receipt).encode("utf-8"))
        os.chmod(path, 0o600)
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_OUTPUT_INVALID"
        ) from error
    return path


def observe_challenger_cohort_evidence_maintenance_first_run(
    *,
    install_receipt_path: Path,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    receipt_output_root: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    manifest, contract, install = _load_sources(
        install_receipt_path=install_receipt_path,
        manifest_path=manifest_path,
        trusted_source_attestation_hash=trusted_source_attestation_hash,
        trusted_candidate_attestation_hash=(
            trusted_candidate_attestation_hash
        ),
    )
    scheduled, scheduled_text, deadline_text = _schedule(install, contract)
    observed, observed_text = _utc((clock or _utc_now)())
    paths = _observation_paths(contract)
    before = _snapshot(paths)
    launchctl_print, runs, last_exit, service_state = _launchctl(
        runner=_launchctl_runner or _command_runner,
        contract=contract,
        receipt=install,
    )
    after = _snapshot(paths)
    if before != after:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_OBSERVATION_DRIFT"
        )
    deadline, _ = _utc(deadline_text)
    base = {
        "observed_at": observed_text,
        "first_natural_scheduled_for": scheduled_text,
        "completion_deadline": deadline_text,
        "launchd_runs_observed": runs,
        "last_exit_code_observed": last_exit,
        "service_state_observed": service_state,
        "receipt_published": False,
        "launchctl_print_count": 1,
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "strategy_runner_invocation_count": 0,
        "maintenance_invocation_count": 0,
    }
    if observed < scheduled:
        if (
            runs != 0
            or last_exit != "(never exited)"
            or service_state != "not running"
        ):
            raise ChallengerCohortEvidenceMaintenanceFirstRunError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_EARLY_RUN"
            )
        return {
            "status": "WAITING_BEFORE_FIRST_NATURAL_MAINTENANCE_RUN",
            **base,
        }
    stdout = after["maintenance_stdout"]
    stderr = after["maintenance_stderr"]
    complete = (
        runs >= 1
        and last_exit == "0"
        and service_state == "not running"
        and stdout["exists"]
        and stderr["exists"]
        and stderr["size_bytes"] == 0
    )
    if not complete:
        if runs >= 1 and last_exit not in ("0", "(never exited)"):
            raise ChallengerCohortEvidenceMaintenanceFirstRunError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_FAILED"
            )
        if observed <= deadline:
            return {
                "status": "FIRST_NATURAL_MAINTENANCE_RUN_PENDING",
                **base,
            }
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            (
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_MISSED"
                if runs == 0
                else "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_INCOMPLETE"
            )
        )
    stdout_bytes = paths["maintenance_stdout"].read_bytes()
    summary = _summary(
        stdout_bytes,
        scheduled=scheduled,
        observed=observed,
    )
    receipt = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "receipt_id": (
            "challenger_cohort_evidence_maintenance_first_run_receipt_"
            + "0" * 64
        ),
        "receipt_hash": "0" * 64,
        "observed_at": observed_text,
        "first_natural_scheduled_for": scheduled_text,
        "completion_deadline": deadline_text,
        "deployment": {
            "manifest_id": manifest["manifest_id"],
            "manifest_hash": manifest["manifest_hash"],
            "snapshot_tree_hash": manifest["execution_snapshot"][
                "tree_hash"
            ],
        },
        "contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": trusted_candidate_attestation_hash,
            "launchd_plist_sha256": contract["launchd_plist_sha256"],
        },
        "install_receipt": {
            "receipt_id": install["receipt_id"],
            "receipt_hash": install["receipt_hash"],
            "target_path": install["target_path"],
            "target_sha256": install["target_stat"]["sha256"],
        },
        "launchctl_print": launchctl_print,
        "launchd_runs_observed": runs,
        "last_exit_code_observed": last_exit,
        "service_state_observed": service_state,
        "maintenance_summary": summary,
        "observation": after,
        "observation_unchanged": True,
        "observation_status": (
            "FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED"
        ),
        "security_boundary": {
            "launchctl_print_count": 1,
            "observer_network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "strategy_runner_invocation_count": 0,
            "maintenance_invocation_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
        },
        "eligibility": {
            "maintenance_first_run": "VERIFIED",
            "cohort_completeness": "INELIGIBLE",
            "profitability": "INELIGIBLE",
            "system_paper": "INELIGIBLE",
            "ai_advantage": "INELIGIBLE",
        },
        "warnings": list(_WARNINGS),
    }
    receipt["receipt_id"] = stable_id(
        "challenger_cohort_evidence_maintenance_first_run_receipt",
        _identity(receipt),
    )
    receipt["receipt_hash"] = maintenance_first_run_receipt_hash(receipt)
    if tuple(_validator().iter_errors(receipt)):
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RECEIPT_INVALID"
        )
    receipt_path = _publish(receipt, receipt_output_root)
    return {
        "status": (
            "FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED"
        ),
        **base,
        "receipt_published": True,
        "receipt_path": str(receipt_path),
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "maintenance_status": summary["status"],
        "maintenance_network_request_count": summary[
            "network_request_count"
        ],
    }


def load_challenger_cohort_evidence_maintenance_first_run_receipt(
    *,
    receipt_path: Path,
    install_receipt_path: Path,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
) -> Mapping[str, Any]:
    manifest, contract, install = _load_sources(
        install_receipt_path=install_receipt_path,
        manifest_path=manifest_path,
        trusted_source_attestation_hash=trusted_source_attestation_hash,
        trusted_candidate_attestation_hash=(
            trusted_candidate_attestation_hash
        ),
    )
    try:
        file = Path(receipt_path).expanduser().resolve(strict=True)
        evidence = _file_evidence(file, allow_missing=False)
        if evidence["size_bytes"] > _MAX_FILE_BYTES:
            raise ValueError
        receipt = _strict_json_bytes(file.read_bytes())
        if (
            tuple(_validator().iter_errors(receipt))
            or receipt["receipt_hash"]
            != maintenance_first_run_receipt_hash(receipt)
            or receipt["receipt_id"]
            != stable_id(
                "challenger_cohort_evidence_maintenance_first_run_receipt",
                _identity(receipt),
            )
            or receipt["deployment"]["manifest_hash"]
            != manifest["manifest_hash"]
            or receipt["deployment"]["manifest_id"]
            != manifest["manifest_id"]
            or receipt["deployment"]["snapshot_tree_hash"]
            != manifest["execution_snapshot"]["tree_hash"]
            or receipt["contract"]["contract_hash"]
            != contract["contract_hash"]
            or receipt["contract"]["contract_id"]
            != contract["contract_id"]
            or receipt["contract"]["contract_trust_hash"]
            != trusted_candidate_attestation_hash
            or receipt["contract"]["launchd_plist_sha256"]
            != contract["launchd_plist_sha256"]
            or receipt["install_receipt"]["receipt_hash"]
            != install["receipt_hash"]
            or receipt["install_receipt"]["receipt_id"]
            != install["receipt_id"]
            or receipt["install_receipt"]["target_path"]
            != install["target_path"]
            or receipt["install_receipt"]["target_sha256"]
            != install["target_stat"]["sha256"]
        ):
            raise ValueError
        paths = _observation_paths(contract)
        observation = receipt["observation"]
        if (
            not _file_prefix_valid(
                observation["maintenance_stdout"],
                paths["maintenance_stdout"],
            )
            or not _file_prefix_valid(
                observation["maintenance_stderr"],
                paths["maintenance_stderr"],
            )
            or not _inventory_prefix_valid(
                observation["receipt_inventory"],
                paths["receipt_root"],
            )
            or not _inventory_prefix_valid(
                observation["archive_inventory"],
                paths["archive_root"],
            )
            or not _inventory_prefix_valid(
                observation["result_inventory"],
                paths["result_root"],
            )
        ):
            raise ValueError
        print_argv = (_LAUNCHCTL, "print", install["service"])
        if (
            not _command_evidence_valid(
                receipt["launchctl_print"], print_argv
            )
            or receipt["launchctl_print"]["return_code"] != 0
            or not _print_bindings_valid(
                receipt["launchctl_print"]["stdout_utf8"].encode("utf-8"),
                contract=contract,
                domain=install["domain"],
                target=Path(install["target_path"]),
            )
        ):
            raise ValueError
        print_text = receipt["launchctl_print"]["stdout_utf8"]
        print_runs = re.findall(
            r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)",
            print_text,
        )
        print_exits = re.findall(
            r"(?:^|\n)[ \t]*last exit code = ([^\n]+)(?:\n|$)",
            print_text,
        )
        print_states = re.findall(
            r"(?:^|\n)[ \t]*state = ([^\n]+)(?:\n|$)",
            print_text,
        )
        if (
            len(print_runs) != 1
            or int(print_runs[0]) != receipt["launchd_runs_observed"]
            or len(print_exits) != 1
            or print_exits[0].strip()
            != receipt["last_exit_code_observed"]
            or len(print_states) != 1
            or print_states[0].strip()
            != receipt["service_state_observed"]
        ):
            raise ValueError
        stdout = paths["maintenance_stdout"].read_bytes()[
            : observation["maintenance_stdout"]["size_bytes"]
        ]
        observed, _ = _utc(receipt["observed_at"])
        scheduled, scheduled_text, deadline_text = _schedule(
            install, contract
        )
        if (
            receipt["first_natural_scheduled_for"] != scheduled_text
            or receipt["completion_deadline"] != deadline_text
            or receipt["maintenance_summary"]
            != _summary(stdout, scheduled=scheduled, observed=observed)
        ):
            raise ValueError
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RECEIPT_INVALID"
        ) from error
    return receipt
