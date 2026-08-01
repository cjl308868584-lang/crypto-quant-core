"""Fail-closed evidence for a permanently missed Challenger cohort slot."""

import hashlib
import ctypes
import json
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_cohort_cumulative_evaluation import (
    _read_exact_evaluation_plan,
)
from .challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
    _partition,
    _read_exact_plan,
    _slot_summary,
)
from .challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptError,
    _bundle_evidence,
    _trusted_sources,
)
from .challenger_first_slot_receipt import (
    ChallengerFirstSlotReceiptError,
    _log_lines,
    _read_state,
    _secure_file,
)
from .challenger_launchd import challenger_launchd_contract_trust_hash
from .challenger_launchd_install import (
    LaunchctlResult,
    _command_evidence,
    _command_evidence_valid,
    _command_runner,
    _print_bindings_valid,
)
from .evidence import artifact_self_hash
from .research_corpus import _strict_json_bytes


_CADENCE = timedelta(hours=4)
_LAUNCHCTL = "/bin/launchctl"
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024
_MAX_LOG_BYTES = 64 * 1024 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024
_MISSED_SLOT_STDERR = b'{"error":"CHALLENGER_RUNNER_MISSED_SLOT"}\n'
_OUTPUT_DIRECTORY = "challenger-cohort-failure-receipts"
_SCHEMA = "challenger-cohort-failure-receipt-v1.schema.json"
_V048_EVALUATOR_COMMIT = "09b81b9f3a670a20301d4b1090bb4293afc5bc7c"


class ChallengerCohortFailureError(ValueError):
    """The missed-slot observation or immutable receipt failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and value != rendered:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_TIME_INVALID"
        )
    return converted, rendered


def _current_slot(observed: datetime) -> datetime:
    return observed.replace(
        hour=observed.hour - observed.hour % 4,
        minute=0,
        second=0,
        microsecond=0,
    )


def _optional_file(path: Path, *, maximum_bytes: int) -> Mapping[str, Any]:
    try:
        path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "exists": False}
    except OSError as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_SOURCE_INVALID"
        ) from error
    file_stat, _body = _secure_file(
        path,
        maximum_bytes=maximum_bytes,
        allow_empty=True,
        reason_code="CHALLENGER_COHORT_FAILURE_SOURCE_INVALID",
    )
    return {"path": str(path), "exists": True, "file_stat": file_stat}


def _bundle_inventory(directory: Path) -> Mapping[str, Any]:
    try:
        paths = sorted(directory.glob("*.json"))
    except OSError as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_BUNDLE_INVALID"
        ) from error
    entries = []
    for path in paths:
        try:
            file_stat, _body = _secure_file(
                path,
                maximum_bytes=_MAX_BUNDLE_BYTES,
                allow_empty=False,
                reason_code="CHALLENGER_COHORT_FAILURE_BUNDLE_INVALID",
            )
        except ChallengerFirstSlotReceiptError as error:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_BUNDLE_INVALID"
            ) from error
        entries.append({"path": str(path.resolve()), "file_stat": file_stat})
    return {
        "directory": str(directory),
        "count": len(entries),
        "entries": entries,
        "inventory_hash": business_hash(entries),
    }


def _snapshot(paths: Mapping[str, Path]) -> Mapping[str, Any]:
    try:
        state = _optional_file(paths["state"], maximum_bytes=64 * 1024 * 1024)
        wal = _optional_file(
            Path(f"{paths['state']}-wal"), maximum_bytes=64 * 1024 * 1024
        )
        shm = _optional_file(
            Path(f"{paths['state']}-shm"), maximum_bytes=64 * 1024 * 1024
        )
        stdout = _optional_file(paths["stdout"], maximum_bytes=_MAX_LOG_BYTES)
        stderr = _optional_file(paths["stderr"], maximum_bytes=_MAX_LOG_BYTES)
        bundles = _bundle_inventory(paths["bundle_directory"])
    except (KeyError, ChallengerFirstSlotReceiptError) as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_SOURCE_INVALID"
        ) from error
    return {
        "state": state,
        "wal": wal,
        "shm": shm,
        "stdout": stdout,
        "stderr": stderr,
        "source_bundles": bundles,
    }


def _failure_logs(
    *,
    stdout_path: Path,
    stderr_path: Path,
    decisions: Sequence[Mapping[str, Any]],
    bundles: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    try:
        stdout_stat, stdout_bytes = _secure_file(
            stdout_path,
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_COHORT_FAILURE_STDOUT_INVALID",
        )
        stderr_stat, stderr_bytes = _secure_file(
            stderr_path,
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_COHORT_FAILURE_STDERR_INVALID",
        )
        records = _log_lines(stdout_bytes)
    except ChallengerFirstSlotReceiptError as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_LOG_INVALID"
        ) from error
    if stderr_bytes != _MISSED_SLOT_STDERR:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_STDERR_INVALID"
        )
    matched = []
    for decision, bundle in zip(decisions, bundles):
        matches = []
        for line_number, record in enumerate(records, 1):
            if (
                record.get("status") == "RECORDED"
                and record.get("decision_count") == decision["sequence"]
                and record.get("decision_id") == decision["decision_id"]
                and record.get("decision_hash") == decision["decision_hash"]
                and record.get("source_bundle_path") == bundle["path"]
                and record.get("source_bundle_hash") == bundle["bundle_hash"]
                and record.get("server_time_request_count") == 3
                and record.get("kline_request_count") == 1
                and record.get("broker_request_count") == 0
                and record.get("order_submission_count") == 0
            ):
                matches.append((line_number, record))
        if len(matches) != 1:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_LOG_MATCH_INVALID"
            )
        line_number, record = matches[0]
        matched.append(
            {
                "sequence": decision["sequence"],
                "line_number": line_number,
                "record": dict(record),
                "record_hash": hashlib.sha256(
                    canonical_json(record).encode("utf-8")
                ).hexdigest(),
            }
        )
    return {
        "stdout": {
            "path": str(stdout_path),
            "observed_stat": stdout_stat,
            "matched_records": matched,
        },
        "stderr": {
            "path": str(stderr_path),
            "observed_stat": stderr_stat,
            "exact_utf8": stderr_bytes.decode("utf-8"),
        },
    }


def _failed_service_evidence(
    *,
    runner,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Tuple[Mapping[str, Any], int]:
    argv = (_LAUNCHCTL, "print", install_receipt["service"])
    try:
        result = runner(argv)
        if not isinstance(result, LaunchctlResult):
            raise TypeError
        evidence = _command_evidence(argv, result)
        text = result.stdout.decode("utf-8")
        runs = re.findall(r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)", text)
        valid = (
            result.returncode == 0
            and result.stderr == b""
            and _print_bindings_valid(
                result.stdout,
                contract=contract,
                domain=install_receipt["domain"],
                target=Path(install_receipt["target_path"]),
            )
            and str(paths["stdout"]) in text
            and str(paths["stderr"]) in text
            and "state = not running" in text
            and "last exit code = 1" in text
            and len(runs) == 1
            and int(runs[0]) >= 1
        )
    except Exception as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_LAUNCHCTL_INVALID"
        ) from error
    if not valid:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_SERVICE_INVALID"
        )
    return evidence, int(runs[0])


def _stored_failed_service_valid(
    evidence: Mapping[str, Any],
    *,
    launchd_runs: object,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> bool:
    try:
        argv = (_LAUNCHCTL, "print", install_receipt["service"])
        text = evidence["stdout_utf8"]
        body = text.encode("utf-8")
        runs = re.findall(
            r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)", text
        )
        return (
            _command_evidence_valid(evidence, argv)
            and evidence["return_code"] == 0
            and evidence["stderr_utf8"] == ""
            and _print_bindings_valid(
                body,
                contract=contract,
                domain=install_receipt["domain"],
                target=Path(install_receipt["target_path"]),
            )
            and str(paths["stdout"]) in text
            and str(paths["stderr"]) in text
            and "state = not running" in text
            and "last exit code = 1" in text
            and len(runs) == 1
            and isinstance(launchd_runs, int)
            and not isinstance(launchd_runs, bool)
            and int(runs[0]) == launchd_runs
            and launchd_runs >= 1
        )
    except (KeyError, TypeError, UnicodeError, ValueError):
        return False


def challenger_cohort_failure_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": receipt["sources"]["cohort_plan"]["plan_hash"],
        "evaluation_plan_hash": receipt["sources"]["evaluation_plan"][
            "plan_hash"
        ],
        "state_file_sha256": receipt["evidence_after"]["state"]["file_stat"][
            "sha256"
        ],
        "stderr_sha256": receipt["evidence_after"]["stderr"]["file_stat"][
            "sha256"
        ],
        "next_required_slot": receipt["failure"]["next_required_slot"],
        "current_slot": receipt["failure"]["current_slot"],
        "observed_at": receipt["observed_at"],
    }


def _validate_output_root(output_root: Path) -> Path:
    root = Path(output_root).expanduser()
    if (
        not root.is_absolute()
        or root.is_symlink()
        or root.resolve() != root.absolute()
    ):
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_OUTPUT_INVALID"
        )
    if root.exists():
        root_stat = root.lstat()
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_OUTPUT_INVALID"
            )
    return root.resolve()


def _receipt_path(output_root: Path, receipt_id: str) -> Path:
    root = _validate_output_root(output_root)
    return root / _OUTPUT_DIRECTORY / f"{receipt_id}.json"


def _validate_output_disjoint(
    output_root: Path, paths: Mapping[str, Path]
) -> None:
    selected = output_root.resolve()
    protected = (
        paths["state"].parent.resolve(),
        paths["output"].resolve(),
        paths["bundle_directory"].resolve(),
        paths["stdout"].parent.resolve(),
        paths["stderr"].parent.resolve(),
    )
    for candidate in protected:
        if (
            selected == candidate
            or selected in candidate.parents
            or candidate in selected.parents
        ):
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_OUTPUT_INVALID"
            )


def _open_owned_directory(path: Path, *, mode: Optional[int]) -> int:
    before = path.lstat()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(str(path), flags)
    after = os.fstat(descriptor)
    valid = (
        stat.S_ISDIR(before.st_mode)
        and not stat.S_ISLNK(before.st_mode)
        and before.st_uid == os.getuid()
        and (mode is None or stat.S_IMODE(before.st_mode) == mode)
        and (before.st_dev, before.st_ino)
        == (after.st_dev, after.st_ino)
        and stat.S_ISDIR(after.st_mode)
        and after.st_uid == os.getuid()
        and (mode is None or stat.S_IMODE(after.st_mode) == mode)
    )
    if not valid:
        os.close(descriptor)
        raise ValueError
    return descriptor


def _read_owned_child(directory_fd: int, name: str) -> bytes:
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
    ):
        raise ValueError
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd
    )
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
        if (
            opened.st_dev,
            opened.st_ino,
            opened.st_mode,
            opened.st_uid,
            opened.st_nlink,
            opened.st_size,
            opened.st_mtime_ns,
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
        body = b"".join(chunks)
        if len(body) != after.st_size:
            raise ValueError
        return body
    finally:
        os.close(descriptor)


def _publish_owner_only_exact(
    *,
    output_root: Path,
    directory_name: str,
    filename: str,
    body: bytes,
) -> Path:
    root = _validate_output_root(Path(output_root))
    if (
        not directory_name
        or Path(directory_name).name != directory_name
        or not filename.endswith(".json")
        or Path(filename).name != filename
    ):
        raise ValueError
    parent_fd = _open_owned_directory(root.parent, mode=None)
    try:
        try:
            os.mkdir(root.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            pass
        root_fd = os.open(
            root.name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)
    try:
        root_stat = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != os.getuid()
            or stat.S_IMODE(root_stat.st_mode) != 0o700
        ):
            raise ValueError
        try:
            os.mkdir(directory_name, mode=0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        except FileExistsError:
            pass
        directory_fd = os.open(
            directory_name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_fd,
        )
    finally:
        os.close(root_fd)
    try:
        directory_stat = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != os.getuid()
            or stat.S_IMODE(directory_stat.st_mode) != 0o700
        ):
            raise ValueError
        try:
            existing = _read_owned_child(directory_fd, filename)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != body:
                raise ValueError
            return root / directory_name / filename

        temporary_name = f".receipt-{secrets.token_hex(16)}.tmp"
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            view = memoryview(body)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short receipt write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        try:
            os.link(
                temporary_name,
                filename,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            if _read_owned_child(directory_fd, filename) != body:
                raise ValueError
        finally:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        os.fsync(directory_fd)
        if _read_owned_child(directory_fd, filename) != body:
            raise ValueError
        return root / directory_name / filename
    finally:
        os.close(directory_fd)


def _source_bindings(
    *,
    plan: Mapping[str, Any],
    plan_sha256: str,
    evaluation_plan: Mapping[str, Any],
    evaluation_sha256: str,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    install_stat, _install_body = _secure_file(
        Path(install_receipt_path),
        maximum_bytes=2 * 1024 * 1024,
        allow_empty=False,
        reason_code="CHALLENGER_COHORT_FAILURE_SOURCE_INVALID",
    )
    contract_stat, _contract_body = _secure_file(
        Path(contract_path),
        maximum_bytes=2 * 1024 * 1024,
        allow_empty=False,
        reason_code="CHALLENGER_COHORT_FAILURE_SOURCE_INVALID",
    )
    return {
        "cohort_plan": {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "file_sha256": plan_sha256,
        },
        "evaluation_plan": {
            "plan_id": evaluation_plan["plan_id"],
            "plan_hash": evaluation_plan["plan_hash"],
            "file_sha256": evaluation_sha256,
        },
        "install_receipt": {
            "receipt_id": install_receipt["receipt_id"],
            "receipt_hash": install_receipt["receipt_hash"],
            "file_sha256": install_stat["sha256"],
        },
        "contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": challenger_launchd_contract_trust_hash(
                contract
            ),
            "file_sha256": contract_stat["sha256"],
        },
        "plist": {
            "path": str(Path(plist_path).resolve(strict=True)),
            "sha256": contract["launchd_plist_sha256"],
        },
        "v0_48_evaluator_commit": _V048_EVALUATOR_COMMIT,
    }


def _system_boot_time() -> Optional[datetime]:
    try:
        if sys.platform == "darwin":
            class Timeval(ctypes.Structure):
                _fields_ = [
                    ("tv_sec", ctypes.c_long),
                    ("tv_usec", ctypes.c_int),
                ]

            value = Timeval()
            size = ctypes.c_size_t(ctypes.sizeof(value))
            libc = ctypes.CDLL(None, use_errno=True)
            result = libc.sysctlbyname(
                b"kern.boottime",
                ctypes.byref(value),
                ctypes.byref(size),
                None,
                0,
            )
            if result != 0:
                return None
            return datetime.fromtimestamp(
                value.tv_sec + value.tv_usec / 1_000_000,
                tz=timezone.utc,
            )
        proc_stat = Path("/proc/stat")
        if proc_stat.is_file():
            for line in proc_stat.read_text(encoding="ascii").splitlines():
                if line.startswith("btime "):
                    return datetime.fromtimestamp(
                        int(line.split()[1]), tz=timezone.utc
                    )
    except (OSError, TypeError, ValueError):
        return None
    return None


def _root_cause_evidence(next_required: datetime) -> Mapping[str, Any]:
    boot = _system_boot_time()
    return {
        "system_boot_time_or_null": (
            utc_datetime(boot) if boot is not None else None
        ),
        "boot_after_next_required_slot_or_null": (
            boot > next_required if boot is not None else None
        ),
        "required_for_failure": False,
    }


def _root_cause_valid(
    evidence: Mapping[str, Any], *, next_required: datetime
) -> bool:
    try:
        if set(evidence) != {
            "system_boot_time_or_null",
            "boot_after_next_required_slot_or_null",
            "required_for_failure",
        } or evidence["required_for_failure"] is not False:
            return False
        boot_value = evidence["system_boot_time_or_null"]
        relation = evidence["boot_after_next_required_slot_or_null"]
        if boot_value is None:
            return relation is None
        boot = _utc(boot_value)[0]
        return isinstance(relation, bool) and relation == (
            boot > next_required
        )
    except (KeyError, TypeError, ValueError):
        return False


def observe_challenger_cohort_missed_slot_failure(
    *,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    failure_output_root: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    validated_output_root = _validate_output_root(Path(failure_output_root))
    try:
        plan, plan_sha256 = _read_exact_plan(Path(cohort_plan_path))
        evaluation_plan, evaluation_sha256 = _read_exact_evaluation_plan(
            Path(evaluation_plan_path),
            cohort_plan=plan,
            cohort_plan_file_sha256=plan_sha256,
        )
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        _validate_output_disjoint(validated_output_root, paths)
        before = _snapshot(paths)
        state_evidence, decisions = _read_state(paths["state"])
        observed, observed_at = _utc(
            (clock or (lambda: utc_datetime(datetime.now(timezone.utc))))()
        )
        if not decisions:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_STATE_INVALID"
            )
        last_scheduled, _rendered = _utc(decisions[-1]["scheduled_for"])
        cohort, completed, active, next_required = _partition(
            decisions, observed=last_scheduled
        )
        if not cohort or next_required is None:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_SLOT_INVALID"
            )
        current_slot = _current_slot(observed)
        if current_slot <= next_required:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_NOT_LATE"
            )
        bundles = _bundle_evidence(
            bundle_directory=paths["bundle_directory"], decisions=cohort
        )
        logs = _failure_logs(
            stdout_path=paths["stdout"],
            stderr_path=paths["stderr"],
            decisions=cohort,
            bundles=bundles,
        )
        launchctl_print, launchd_runs = _failed_service_evidence(
            runner=_launchctl_runner or _command_runner,
            contract=contract,
            install_receipt=install_receipt,
            paths=paths,
        )
        after = _snapshot(paths)
        if before != after:
            raise ChallengerCohortFailureError(
                "CHALLENGER_COHORT_FAILURE_SOURCE_MUTATED"
            )
    except ChallengerCohortFailureError:
        raise
    except (
        ChallengerCohortEpisodeReceiptError,
        ChallengerFirstEpisodeReceiptError,
        ChallengerFirstSlotReceiptError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_SOURCE_INVALID"
        ) from error

    completed_ids = [
        cohort[start]["state_after"]["episode_id_or_null"]
        for start, _end in completed
    ]
    active_id: Optional[str] = (
        cohort[active[0]]["state_after"]["episode_id_or_null"]
        if active is not None
        else None
    )
    receipt: Dict[str, Any] = {
        "schema_version": "challenger-cohort-failure-receipt-v1",
        "receipt_id": "",
        "receipt_hash": "0" * 64,
        "observation_status": "COHORT_MISSED_SLOT_FAILURE_VERIFIED",
        "observed_at": observed_at,
        "sources": _source_bindings(
            plan=plan,
            plan_sha256=plan_sha256,
            evaluation_plan=evaluation_plan,
            evaluation_sha256=evaluation_sha256,
            contract=contract,
            install_receipt=install_receipt,
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        ),
        "failure": {
            "reason_code": "CHALLENGER_RUNNER_MISSED_SLOT",
            "equivalent_evaluator_status": "FAILED_CLOSED_NO_BACKFILL",
            "equivalent_evaluator_reason": (
                "CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID"
            ),
            "last_trusted_slot": cohort[-1]["scheduled_for"],
            "next_required_slot": utc_datetime(next_required),
            "current_slot": utc_datetime(current_slot),
            "historical_backfill_allowed": False,
            "continuity_repair_allowed": False,
        },
        "root_cause": _root_cause_evidence(next_required),
        "state": {
            "path": state_evidence["path"],
            "metadata": state_evidence["metadata"],
            "total_decision_count": len(decisions),
            "cohort_slot_count": len(cohort),
            "cohort_slots": [_slot_summary(item) for item in cohort],
            "cohort_slots_root_hash": business_hash(
                [_slot_summary(item) for item in cohort]
            ),
            "completed_episode_count": len(completed_ids),
            "completed_episode_ids": completed_ids,
            "active_episode_id_or_null": active_id,
        },
        "source_bundles": list(bundles),
        "logs": logs,
        "launchctl_print": launchctl_print,
        "launchd_runs_observed": launchd_runs,
        "evidence_before": before,
        "evidence_after": after,
        "security_boundary": {
            "launchctl_print_count": 1,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "maintenance_invocation_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
        },
        "eligibility": {
            "old_cohort": "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
            "replacement_cohort": "NOT_STARTED",
            "system_paper": "NOT_STARTED",
            "canary": "NOT_AUTHORIZED",
            "profitability": "INELIGIBLE_FAILED_COHORT",
        },
        "warnings": [
            "NO_BACKFILL",
            "NO_PROFITABILITY_CLAIM",
            "NOT_SYSTEM_PAPER_EVIDENCE",
            "NOT_CANARY_AUTHORIZATION",
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_cohort_failure_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_cohort_failure_receipt_hash(receipt)
    body = canonical_json(receipt).encode("utf-8")
    path = _receipt_path(validated_output_root, receipt["receipt_id"])
    try:
        path = _publish_owner_only_exact(
            output_root=validated_output_root,
            directory_name=_OUTPUT_DIRECTORY,
            filename=path.name,
            body=body,
        )
    except Exception as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_PUBLISH_FAILED"
        ) from error
    loaded = load_challenger_cohort_failure_receipt(
        receipt_path=path,
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
        "last_trusted_slot": loaded["failure"]["last_trusted_slot"],
        "next_required_slot": loaded["failure"]["next_required_slot"],
        "current_slot": loaded["failure"]["current_slot"],
        "market_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
        "maintenance_invocation_count": 0,
    }


def _read_receipt(path: Path) -> Tuple[Mapping[str, Any], bytes]:
    try:
        requested = Path(path).expanduser()
        file_stat = requested.lstat()
        if (
            not requested.is_absolute()
            or stat.S_ISLNK(file_stat.st_mode)
            or not stat.S_ISREG(file_stat.st_mode)
            or file_stat.st_uid != os.getuid()
            or file_stat.st_nlink != 1
            or stat.S_IMODE(file_stat.st_mode) not in (0o600, 0o644)
            or file_stat.st_size <= 0
            or file_stat.st_size > _MAX_RECEIPT_BYTES
            or requested.resolve(strict=True) != requested.absolute()
        ):
            raise ValueError
        body = requested.read_bytes()
        after = requested.lstat()
        if (
            file_stat.st_dev,
            file_stat.st_ino,
            file_stat.st_size,
            file_stat.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError
        receipt = _strict_json_bytes(body)
        if not isinstance(receipt, Mapping):
            raise ValueError
        return receipt, body
    except Exception as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_RECEIPT_INVALID"
        ) from error


def load_challenger_cohort_failure_receipt(
    *,
    receipt_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    receipt, body = _read_receipt(Path(receipt_path))
    try:
        plan, plan_sha256 = _read_exact_plan(Path(cohort_plan_path))
        evaluation_plan, evaluation_sha256 = _read_exact_evaluation_plan(
            Path(evaluation_plan_path),
            cohort_plan=plan,
            cohort_plan_file_sha256=plan_sha256,
        )
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        expected_sources = _source_bindings(
            plan=plan,
            plan_sha256=plan_sha256,
            evaluation_plan=evaluation_plan,
            evaluation_sha256=evaluation_sha256,
            contract=contract,
            install_receipt=install_receipt,
            install_receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        current = _snapshot(paths)
        state_evidence, decisions = _read_state(paths["state"])
        if not decisions:
            raise ValueError
        last_scheduled = _utc(decisions[-1]["scheduled_for"])[0]
        cohort, completed, active, next_required = _partition(
            decisions, observed=last_scheduled
        )
        if not cohort or next_required is None:
            raise ValueError
        bundles = _bundle_evidence(
            bundle_directory=paths["bundle_directory"], decisions=cohort
        )
        logs = _failure_logs(
            stdout_path=paths["stdout"],
            stderr_path=paths["stderr"],
            decisions=cohort,
            bundles=bundles,
        )
        completed_ids = [
            cohort[start]["state_after"]["episode_id_or_null"]
            for start, _end in completed
        ]
        active_id = (
            cohort[active[0]]["state_after"]["episode_id_or_null"]
            if active is not None
            else None
        )
        summaries = [_slot_summary(item) for item in cohort]
        expected_state = {
            "path": state_evidence["path"],
            "metadata": state_evidence["metadata"],
            "total_decision_count": len(decisions),
            "cohort_slot_count": len(cohort),
            "cohort_slots": summaries,
            "cohort_slots_root_hash": business_hash(summaries),
            "completed_episode_count": len(completed_ids),
            "completed_episode_ids": completed_ids,
            "active_episode_id_or_null": active_id,
        }
        valid = (
            body == canonical_json(receipt).encode("utf-8")
            and not tuple(_validator().iter_errors(receipt))
            and receipt.get("schema_version")
            == "challenger-cohort-failure-receipt-v1"
            and receipt.get("receipt_hash")
            == challenger_cohort_failure_receipt_hash(receipt)
            and receipt.get("receipt_id")
            == stable_id("challenger_cohort_failure_receipt", _identity(receipt))
            and receipt.get("observation_status")
            == "COHORT_MISSED_SLOT_FAILURE_VERIFIED"
            and receipt.get("sources") == expected_sources
            and receipt.get("state") == expected_state
            and receipt.get("source_bundles") == list(bundles)
            and receipt.get("logs") == logs
            and _stored_failed_service_valid(
                receipt["launchctl_print"],
                launchd_runs=receipt["launchd_runs_observed"],
                contract=contract,
                install_receipt=install_receipt,
                paths=paths,
            )
            and receipt["failure"]["reason_code"]
            == "CHALLENGER_RUNNER_MISSED_SLOT"
            and receipt["failure"]["equivalent_evaluator_status"]
            == "FAILED_CLOSED_NO_BACKFILL"
            and receipt["failure"]["equivalent_evaluator_reason"]
            == "CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID"
            and receipt["failure"]["last_trusted_slot"]
            == cohort[-1]["scheduled_for"]
            and receipt["failure"]["next_required_slot"]
            == utc_datetime(next_required)
            and not receipt["failure"]["historical_backfill_allowed"]
            and not receipt["failure"]["continuity_repair_allowed"]
            and _current_slot(_utc(receipt["observed_at"])[0])
            == _utc(receipt["failure"]["current_slot"])[0]
            and _utc(receipt["failure"]["current_slot"])[0]
            > _utc(receipt["failure"]["next_required_slot"])[0]
            and _root_cause_valid(
                receipt["root_cause"], next_required=next_required
            )
            and receipt["logs"]["stderr"]["exact_utf8"]
            == _MISSED_SLOT_STDERR.decode("utf-8")
            and receipt["evidence_before"] == receipt["evidence_after"]
            and current == receipt["evidence_after"]
            and receipt["eligibility"]["old_cohort"]
            == "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP"
            and receipt["security_boundary"]
            == {
                "launchctl_print_count": 1,
                "market_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "runner_invocation_count": 0,
                "maintenance_invocation_count": 0,
                "shell_invoked": False,
                "arbitrary_command_allowed": False,
            }
        )
    except Exception as error:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_RECEIPT_INVALID"
        ) from error
    if not valid:
        raise ChallengerCohortFailureError(
            "CHALLENGER_COHORT_FAILURE_RECEIPT_INVALID"
        )
    return receipt
