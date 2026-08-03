"""Descriptor-retained, read-only observer for the first System Paper slot."""

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .canonical import canonical_json, utc_datetime
from .system_paper_install import (
    LaunchctlResult,
    load_system_paper_install_receipt,
)
from .system_paper_plan import build_system_paper_plan
from .system_paper_runtime import load_system_paper_slot_result_bytes
from .system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)


_LABEL = "local.crypto-quant.system-paper-v1"
_LAUNCHCTL = "/bin/launchctl"
_MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
_MAX_COMMAND_BYTES = 64 * 1024


class SystemPaperObserverError(ValueError):
    """The read-only first-slot observation failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_TIME_INVALID")
    text = utc_datetime(parsed)
    if isinstance(value, str) and value != text:
        raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_TIME_INVALID")
    return parsed, text


def _now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _stat_payload(entry: os.stat_result, body: bytes) -> Dict[str, Any]:
    return {
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "mode": stat.S_IMODE(entry.st_mode),
        "owner_uid": entry.st_uid,
        "link_count": entry.st_nlink,
        "size_bytes": entry.st_size,
        "mtime_ns": str(entry.st_mtime_ns),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


@dataclass
class _RetainedFile:
    path: Path
    descriptor: int
    before: os.stat_result
    body: bytes

    @classmethod
    def open(cls, path: Path, *, allow_empty: bool = False):
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = None
        try:
            descriptor = os.open(str(path), flags)
            entry = os.fstat(descriptor)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != os.getuid()
                or entry.st_nlink != 1
                or stat.S_IMODE(entry.st_mode) != 0o600
                or entry.st_size > _MAX_EVIDENCE_BYTES
                or (not allow_empty and entry.st_size == 0)
            ):
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_FILE_UNSAFE"
                )
            chunks = []
            remaining = _MAX_EVIDENCE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            body = b"".join(chunks)
            if len(body) != entry.st_size:
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_FILE_RACE"
                )
            return cls(path, descriptor, entry, body)
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            raise

    @property
    def evidence(self):
        return {"path": str(self.path), **_stat_payload(self.before, self.body)}

    def verify_unchanged(self):
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(str(self.path), follow_symlinks=False)
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            chunks = []
            while True:
                chunk = os.read(self.descriptor, 65536)
                if not chunk:
                    break
                chunks.append(chunk)
            body = b"".join(chunks)
        except OSError as error:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
            ) from error
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
        )
        if (
            any(getattr(retained, name) != getattr(self.before, name) for name in fields)
            or any(getattr(current, name) != getattr(self.before, name) for name in fields)
            or body != self.body
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
            )

    def close(self):
        os.close(self.descriptor)


class _EvidenceSet:
    def __init__(self):
        self.files = []
        self.absent = []
        self.directories = []

    def capture_file(self, path: Path, *, optional=False, allow_empty=False):
        if not path.exists() and not path.is_symlink():
            if optional:
                self.absent.append(path)
                return None
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_EVIDENCE_MISSING"
            )
        retained = _RetainedFile.open(path, allow_empty=allow_empty)
        self.files.append(retained)
        return retained

    def capture_directory(self, path: Path):
        try:
            entry = path.lstat()
            names = tuple(sorted(item.name for item in path.iterdir()))
        except OSError as error:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_ARTIFACT_INVENTORY_INVALID"
            ) from error
        if (
            not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o700
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_ARTIFACT_INVENTORY_INVALID"
            )
        self.directories.append((path, entry, names))
        return names

    def verify_unchanged(self):
        for retained in self.files:
            retained.verify_unchanged()
        for path in self.absent:
            if path.exists() or path.is_symlink():
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
                )
        for path, before, names in self.directories:
            try:
                current = path.lstat()
                current_names = tuple(sorted(item.name for item in path.iterdir()))
            except OSError as error:
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
                ) from error
            if (
                (current.st_dev, current.st_ino, current.st_mode, current.st_uid)
                != (before.st_dev, before.st_ino, before.st_mode, before.st_uid)
                or current_names != names
            ):
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
                )

    def close(self):
        for retained in self.files:
            retained.close()


def _copy_state_and_replay(
    state_files: Mapping[str, Optional[_RetainedFile]],
):
    main = state_files["main"]
    if main is None:
        return {
            "events": (),
            "projection": {},
            "event_chain_end_hash": "0" * 64,
            "prepared_inputs": {},
            "prepared_results": {},
        }
    plan = build_system_paper_plan()
    policy = SystemPaperSchedulePolicy.create(plan)
    with tempfile.TemporaryDirectory(prefix="system-paper-observer-") as directory:
        root = Path(directory)
        os.chmod(root, 0o700)
        copy_path = root / "system-paper.sqlite"
        for suffix, retained in state_files.items():
            if retained is None:
                continue
            target = copy_path if suffix == "main" else Path(str(copy_path) + suffix)
            target.write_bytes(retained.body)
            target.chmod(0o600)
        with SystemPaperScheduleState(copy_path, policy) as state:
            chain_end = state.verify_integrity()
            events = state.events()
            projection = state.slot_projection()
            prepared_inputs = {}
            prepared_results = {}
            for value in projection.values():
                slot = policy.slot_from_scheduled(value["scheduled_for"])
                if value["input_event_id"] is not None:
                    record = state.load_prepared_input(slot)
                    prepared_inputs[slot.slot_id] = record
                if value["result_event_id"] is not None:
                    record = state.load_prepared_result(slot)
                    prepared_results[slot.slot_id] = record
    return {
        "events": events,
        "projection": projection,
        "event_chain_end_hash": chain_end,
        "prepared_inputs": prepared_inputs,
        "prepared_results": prepared_results,
    }


def _first_slot_after_install(installed_at: str, policy: SystemPaperSchedulePolicy):
    installed, _ = _utc(installed_at)
    boundary = installed.replace(minute=0, second=0, microsecond=0)
    remainder = boundary.hour % 4
    boundary -= timedelta(hours=remainder)
    if boundary <= installed:
        boundary += timedelta(hours=4)
    return policy.slot_from_scheduled(boundary)


def _validate_launchctl_result(result, *, contract, install, success_count):
    if (
        not isinstance(result, LaunchctlResult)
        or result.returncode != 0
        or not isinstance(result.stdout, bytes)
        or not isinstance(result.stderr, bytes)
        or result.stderr
        or len(result.stdout) > _MAX_COMMAND_BYTES
    ):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_INVALID"
        )
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_INVALID"
        ) from error
    required = (
        install["service"],
        _LABEL,
        install["target_path"],
        contract["python_executable"],
        "crypto_quant.system_paper_runtime_cli",
        contract["program_arguments"][4],
        contract["program_arguments"][6],
        contract["execution_snapshot"]["repository_root"],
    )
    if not all(value in text for value in required):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_SERVICE_BINDING_INVALID"
        )
    runs = re.search(r"(?m)^\s*runs\s*=\s*(\d+)\s*$", text)
    exit_code = re.search(r"(?m)^\s*last exit code\s*=\s*(-?\d+)\s*$", text)
    if runs is None:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_INVALID"
        )
    run_count = int(runs.group(1))
    last_exit = None if exit_code is None else int(exit_code.group(1))
    if last_exit not in (None, 0) or (run_count > 0 and last_exit is None):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_NONZERO_EXIT"
        )
    if run_count != success_count:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_RUN_COUNT_MISMATCH"
        )
    return {
        "service": install["service"],
        "run_count": run_count,
        "last_exit_code": last_exit,
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
    }


def _default_launchctl_runner(argv: Sequence[str]) -> LaunchctlResult:
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
            env={
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_FAILED"
        ) from error
    return LaunchctlResult(
        completed.returncode, completed.stdout, completed.stderr
    )


def _runner_log_summary(
    stdout: _RetainedFile,
    expected_result_path: Path,
    expected_result_body: bytes,
    result,
):
    try:
        text = stdout.body.decode("utf-8")
        if not text.endswith("\n") or "\n" in text[:-1]:
            raise ValueError
        value = json.loads(text[:-1])
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STDOUT_INVALID"
        ) from error
    if canonical_json(value) + "\n" != text:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STDOUT_INVALID"
        )
    expected = {
        "slot_id": result["slot_id"],
        "result_path_or_null": str(expected_result_path),
        "result_sha256_or_null": hashlib.sha256(expected_result_body).hexdigest(),
        "slot_hash_or_null": result["slot_hash"],
        "runtime_snapshot_hash_or_null": result["runtime_snapshot"]["snapshot_hash"],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STDOUT_MISMATCH"
        )
    if (
        value.get("outcome") not in ("EXECUTED", "RESUMED_INPUT", "RESUMED_RESULT")
        or value.get("loader_replay_count") != 1
        or value.get("safety_counts")
        != {
            "credential_reads": 0,
            "account_requests": 0,
            "real_broker_calls": 0,
            "real_order_writes": 0,
        }
    ):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STDOUT_MISMATCH"
        )
    return value


def observe_system_paper_first_slot(
    *,
    contract_path: Path,
    plist_path: Path,
    preflight_receipt_path: Path,
    install_receipt_path: Path,
    _launchctl_runner=None,
    _machine_probe=None,
    _filesystem_probe=None,
    _clock=None,
) -> Mapping[str, Any]:
    observed_dt, observed_at = _utc((_clock or _now)())
    install = load_system_paper_install_receipt(
        receipt_path=Path(install_receipt_path),
        contract_path=Path(contract_path),
        plist_path=Path(plist_path),
        preflight_receipt_path=Path(preflight_receipt_path),
        _machine_probe=_machine_probe,
        _filesystem_probe=_filesystem_probe,
    )
    contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
    first_slot = _first_slot_after_install(install["installed_at"], policy)
    state_path = Path(contract["root_paths"]["state"]) / "system-paper.sqlite"
    stdout_path = Path(contract["root_paths"]["log"]) / "system-paper.stdout.log"
    stderr_path = Path(contract["root_paths"]["log"]) / "system-paper.stderr.log"
    slots_directory = Path(contract["root_paths"]["artifacts"]) / "system-paper-slots"
    evidence = _EvidenceSet()
    try:
        source_files = {
            "contract": evidence.capture_file(Path(contract_path)),
            "plist": evidence.capture_file(Path(plist_path)),
            "preflight_receipt": evidence.capture_file(
                Path(preflight_receipt_path)
            ),
            "install_receipt": evidence.capture_file(
                Path(install_receipt_path)
            ),
            "installed_target": evidence.capture_file(
                Path(install["target_path"])
            ),
        }
        state_files = {
            "main": evidence.capture_file(state_path, optional=True),
            "-wal": evidence.capture_file(Path(str(state_path) + "-wal"), optional=True, allow_empty=True),
            "-shm": evidence.capture_file(Path(str(state_path) + "-shm"), optional=True, allow_empty=True),
        }
        stdout = evidence.capture_file(stdout_path, optional=True, allow_empty=True)
        stderr = evidence.capture_file(stderr_path, optional=True, allow_empty=True)
        if slots_directory.exists() or slots_directory.is_symlink():
            artifact_names = evidence.capture_directory(slots_directory)
        else:
            evidence.absent.append(slots_directory)
            artifact_names = ()
        artifacts = {}
        for name in artifact_names:
            if not re.fullmatch(r"system_paper_slot_[0-9a-f]{64}\.json", name):
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_ARTIFACT_INVENTORY_INVALID"
                )
            artifacts[name] = evidence.capture_file(slots_directory / name)

        replay = _copy_state_and_replay(state_files)
        events = replay["events"]
        failed_runtime = any(
            item["event_type"] in ("FAILED", "MISSED", "EXPIRED")
            for item in events
        )
        successes = sorted(
            (
                value
                for value in replay["projection"].values()
                if value["terminal_state"] == "SUCCEEDED"
            ),
            key=lambda value: value["scheduled_for"],
        )
        terminals = [
            value
            for value in replay["projection"].values()
            if value["terminal_state"] is not None
        ]
        service_argv = (_LAUNCHCTL, "print", install["service"])
        runner = _launchctl_runner or _default_launchctl_runner
        try:
            launchctl_result = runner(service_argv)
        except Exception as error:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_FAILED"
            ) from error
        launchd = _validate_launchctl_result(
            launchctl_result,
            contract=contract,
            install=install,
            success_count=len(successes),
        )
        evidence.verify_unchanged()
        replayed_install = load_system_paper_install_receipt(
            receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
            preflight_receipt_path=Path(preflight_receipt_path),
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        if replayed_install != install:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_SOURCE_CHANGED"
            )
        if failed_runtime:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FAILED_CLOSED"
            )
        if len(successes) > 1:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_OBSERVATION_WINDOW_MISSED"
            )
        if successes and successes[0]["slot_id"] != first_slot.slot_id:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_IDENTITY_MISMATCH"
            )

        security = {
            "launchctl_read_count": 1,
            "network_request_count": 0,
            "runtime_invocation_count": 0,
            "scheduler_invocation_count": 0,
            "state_write_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        }
        state_evidence = {
            name: None if retained is None else retained.evidence
            for name, retained in state_files.items()
        }
        if not successes:
            if artifact_names or stdout is not None or stderr is not None:
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_UNEXPECTED_RUNTIME_EVIDENCE"
                )
            status_value = (
                "WAITING_BEFORE_FIRST_NATURAL_SLOT"
                if observed_dt < _utc(first_slot.due_at)[0]
                else "WAITING_FOR_FIRST_NATURAL_SLOT"
            )
            return {
                "status": status_value,
                "observed_at": observed_at,
                "first_eligible_slot": {
                    "slot_id": first_slot.slot_id,
                    "scheduled_for": first_slot.scheduled_for,
                    "due_at": first_slot.due_at,
                    "expires_at": first_slot.expires_at,
                },
                "successful_slot_count": 0,
                "terminal_slot_count": len(terminals),
                "first_slot": None,
                "source_evidence": {
                    name: retained.evidence
                    for name, retained in source_files.items()
                },
                "state_evidence": state_evidence,
                "launchd": launchd,
                "security_boundary": security,
            }

        success = successes[0]
        if len(artifacts) != 1:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_ARTIFACT_INVENTORY_INVALID"
            )
        artifact = next(iter(artifacts.values()))
        expected_name = success["slot_id"] + ".json"
        if artifact.path.name != expected_name:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_ARTIFACT_INVENTORY_INVALID"
            )
        prepared_input = replay["prepared_inputs"].get(success["slot_id"])
        prepared_result = replay["prepared_results"].get(success["slot_id"])
        if prepared_input is None or prepared_result is None:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_PREPARED_EVIDENCE_MISSING"
            )
        if prepared_result["result_bytes"] != artifact.body:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_PREPARED_RESULT_MISMATCH"
            )
        result = load_system_paper_slot_result_bytes(artifact.body)
        if result["slot_id"] != success["slot_id"]:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_RESULT_SLOT_MISMATCH"
            )
        if stdout is None:
            raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_STDOUT_MISSING")
        if stderr is None or stderr.body:
            raise SystemPaperObserverError("SYSTEM_PAPER_OBSERVER_STDERR_INVALID")
        log_summary = _runner_log_summary(
            stdout, artifact.path, artifact.body, result
        )
        return {
            "status": "FIRST_NATURAL_SLOT_VERIFIED",
            "observed_at": observed_at,
            "first_eligible_slot": {
                "slot_id": first_slot.slot_id,
                "scheduled_for": first_slot.scheduled_for,
                "due_at": first_slot.due_at,
                "expires_at": first_slot.expires_at,
            },
            "successful_slot_count": 1,
            "terminal_slot_count": len(terminals),
            "first_slot": {
                "slot_id": result["slot_id"],
                "scheduled_for": result["scheduled_for"],
                "result_path": str(artifact.path),
                "result_sha256": hashlib.sha256(artifact.body).hexdigest(),
                "slot_hash": result["slot_hash"],
                "runtime_snapshot_hash": result["runtime_snapshot"]["snapshot_hash"],
                "prepared_input_sha256": hashlib.sha256(
                    prepared_input["input_bytes"]
                ).hexdigest(),
                "prepared_result_sha256": hashlib.sha256(
                    prepared_result["result_bytes"]
                ).hexdigest(),
                "event_chain_end_hash": replay["event_chain_end_hash"],
                "artifact_evidence": artifact.evidence,
                "stdout_evidence": stdout.evidence,
                "stderr_evidence": stderr.evidence,
                "runner_summary": log_summary,
            },
            "source_evidence": {
                name: retained.evidence
                for name, retained in source_files.items()
            },
            "state_evidence": state_evidence,
            "launchd": launchd,
            "security_boundary": security,
        }
    except SystemPaperObserverError:
        raise
    except Exception as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_FAILED_CLOSED"
        ) from error
    finally:
        evidence.close()
