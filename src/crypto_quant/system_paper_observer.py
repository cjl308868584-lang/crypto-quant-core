"""Descriptor-retained, read-only observer for the first System Paper slot."""

import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
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
from .system_paper_launchctl import (
    SystemPaperLaunchctlParseError,
    parse_system_paper_launchctl_print,
)
from .system_paper_launchd import load_system_paper_launchd_contract
from .system_paper_plan import build_system_paper_plan
from .system_paper_runtime import load_system_paper_slot_result_bytes
from .system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    load_system_paper_schedule_event_metadata,
)


_LABEL = "local.crypto-quant.system-paper-v1"
_LAUNCHCTL = "/bin/launchctl"
_MAX_EVIDENCE_BYTES = 32 * 1024 * 1024
_MAX_STATE_EVIDENCE_BYTES = 128 * 1024 * 1024
_MAX_SLOT_EVIDENCE_BYTES = 1024 * 1024
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
    body: Optional[bytes]
    content_sha256: str

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        allow_empty: bool = False,
        maximum_bytes: int = _MAX_EVIDENCE_BYTES,
        retain_body: bool = True,
    ):
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
                or entry.st_size > maximum_bytes
                or (not allow_empty and entry.st_size == 0)
            ):
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_FILE_UNSAFE"
                )
            chunks = []
            digest = hashlib.sha256()
            remaining = maximum_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(65536, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                if retain_body:
                    chunks.append(chunk)
                remaining -= len(chunk)
            bytes_read = maximum_bytes + 1 - remaining
            body = b"".join(chunks) if retain_body else None
            if bytes_read != entry.st_size:
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVIDENCE_FILE_RACE"
                )
            return cls(path, descriptor, entry, body, digest.hexdigest())
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            raise

    @property
    def evidence(self):
        return {
            "path": str(self.path),
            "device": self.before.st_dev,
            "inode": self.before.st_ino,
            "mode": stat.S_IMODE(self.before.st_mode),
            "owner_uid": self.before.st_uid,
            "link_count": self.before.st_nlink,
            "size_bytes": self.before.st_size,
            "mtime_ns": str(self.before.st_mtime_ns),
            "sha256": self.content_sha256,
        }

    def verify_unchanged(self):
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(str(self.path), follow_symlinks=False)
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            offset = 0
            digest = hashlib.sha256()
            while True:
                chunk = os.read(self.descriptor, 65536)
                if not chunk:
                    break
                digest.update(chunk)
                if (
                    self.body is not None
                    and self.body[offset : offset + len(chunk)] != chunk
                ):
                    raise SystemPaperObserverError(
                        "SYSTEM_PAPER_OBSERVER_EVIDENCE_CHANGED"
                    )
                offset += len(chunk)
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
            or offset != self.before.st_size
            or digest.hexdigest() != self.content_sha256
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

    def capture_file(
        self,
        path: Path,
        *,
        optional=False,
        allow_empty=False,
        maximum_bytes=_MAX_EVIDENCE_BYTES,
        retain_body=True,
    ):
        if not path.exists() and not path.is_symlink():
            if optional:
                self.absent.append(path)
                return None
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_EVIDENCE_MISSING"
            )
        retained = _RetainedFile.open(
            path,
            allow_empty=allow_empty,
            maximum_bytes=maximum_bytes,
            retain_body=retain_body,
        )
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
    *,
    expected_slot_id: str,
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
            os.lseek(retained.descriptor, 0, os.SEEK_SET)
            with target.open("xb") as handle:
                while True:
                    chunk = os.read(retained.descriptor, 65536)
                    if not chunk:
                        break
                    handle.write(chunk)
            target.chmod(0o600)
        replay = load_system_paper_schedule_event_metadata(copy_path, policy)
        connection = sqlite3.connect(str(copy_path), timeout=0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only = ON")
            prepared_inputs = {}
            for row in connection.execute(
                "SELECT slot_id, input_bytes, input_sha256 "
                "FROM prepared_inputs ORDER BY slot_id"
            ):
                body = row["input_bytes"]
                if (
                    not isinstance(body, bytes)
                    or hashlib.sha256(body).hexdigest()
                    != row["input_sha256"]
                ):
                    raise SystemPaperObserverError(
                        "SYSTEM_PAPER_OBSERVER_PREPARED_EVIDENCE_INVALID"
                    )
                if row["slot_id"] == expected_slot_id:
                    prepared_inputs[row["slot_id"]] = {
                        "input_bytes": row["input_bytes"],
                        "input_sha256": row["input_sha256"],
                    }
            prepared_results = {}
            for row in connection.execute(
                "SELECT slot_id, result_bytes, result_sha256 "
                "FROM prepared_results ORDER BY slot_id"
            ):
                body = row["result_bytes"]
                if (
                    not isinstance(body, bytes)
                    or hashlib.sha256(body).hexdigest()
                    != row["result_sha256"]
                ):
                    raise SystemPaperObserverError(
                        "SYSTEM_PAPER_OBSERVER_PREPARED_EVIDENCE_INVALID"
                    )
                if row["slot_id"] == expected_slot_id:
                    prepared_results[row["slot_id"]] = {
                        "result_bytes": row["result_bytes"],
                        "result_sha256": row["result_sha256"],
                    }
        finally:
            connection.close()
    return {
        "events": replay["events"],
        "projection": replay["projection"],
        "event_chain_end_hash": replay["event_chain_end_hash"],
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
        snapshot = parse_system_paper_launchctl_print(result.stdout)
    except SystemPaperLaunchctlParseError as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_LAUNCHCTL_INVALID"
        ) from error
    repository_root = contract["execution_snapshot"]["repository_root"]
    expected_static = {
        "label": _LABEL,
        "service": install["service"],
        "path": install["target_path"],
        "program": contract["python_executable"],
        "arguments": list(contract["program_arguments"]),
        "working_directory": repository_root,
        "environment": {
            "PYTHONPATH": str(Path(repository_root) / "src"),
            "XPC_SERVICE_NAME": _LABEL,
        },
        "state": "not running",
    }
    if any(snapshot[key] != value for key, value in expected_static.items()):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_SERVICE_BINDING_INVALID"
        )
    run_count = snapshot["runs"]
    last_exit = snapshot["last_exit_status"]
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
        "service_snapshot": snapshot,
        "stdout_size_bytes": len(result.stdout),
        "stderr_size_bytes": len(result.stderr),
        "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(result.stderr).hexdigest(),
        "stdout_base64": base64.b64encode(result.stdout).decode("ascii"),
        "stderr_base64": base64.b64encode(result.stderr).decode("ascii"),
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


def _runner_summary_line(
    body: bytes,
    expected_result_path: Path,
    expected_result_body: bytes,
    result,
):
    try:
        text = body.decode("utf-8")
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


def _runner_log_summary(
    stdout: _RetainedFile,
    expected_result_path: Path,
    expected_result_body: bytes,
    result,
):
    return _runner_summary_line(
        stdout.body, expected_result_path, expected_result_body, result
    )


def _stable_evidence_matches(
    recorded: Mapping[str, Any], retained: _RetainedFile, expected_path: Path
) -> bool:
    current = retained.evidence
    return recorded.get("path") == str(expected_path) and all(
        recorded.get(key) == current[key]
        for key in (
            "device",
            "inode",
            "mode",
            "owner_uid",
            "link_count",
        )
    )


def _replay_stored_launchd(
    launchd: Mapping[str, Any], *, contract, install
) -> Mapping[str, Any]:
    try:
        stdout = base64.b64decode(launchd["stdout_base64"], validate=True)
        stderr = base64.b64decode(launchd["stderr_base64"], validate=True)
    except (KeyError, TypeError, ValueError, binascii.Error) as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STORED_LAUNCHCTL_INVALID"
        ) from error
    if (
        len(stdout) != launchd.get("stdout_size_bytes")
        or len(stderr) != launchd.get("stderr_size_bytes")
        or hashlib.sha256(stdout).hexdigest() != launchd.get("stdout_sha256")
        or hashlib.sha256(stderr).hexdigest() != launchd.get("stderr_sha256")
    ):
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STORED_LAUNCHCTL_INVALID"
        )
    replayed = _validate_launchctl_result(
        LaunchctlResult(0, stdout, stderr),
        contract=contract,
        install=install,
        success_count=1,
    )
    if replayed != launchd:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_STORED_LAUNCHCTL_INVALID"
        )
    return replayed


def replay_system_paper_first_slot_evidence(
    *, observation: Mapping[str, Any], contract: Mapping[str, Any], install
) -> Mapping[str, Any]:
    """Purely reconstruct the immutable first-slot prefix without commands."""

    evidence = _EvidenceSet()
    try:
        state_path = Path(contract["root_paths"]["state"]) / "system-paper.sqlite"
        stdout_path = (
            Path(contract["root_paths"]["log"]) / "system-paper.stdout.log"
        )
        stderr_path = (
            Path(contract["root_paths"]["log"]) / "system-paper.stderr.log"
        )
        recorded_state = observation["state_evidence"]
        state_files = {
            "main": evidence.capture_file(
                state_path,
                maximum_bytes=_MAX_STATE_EVIDENCE_BYTES,
                retain_body=False,
            ),
            "-wal": evidence.capture_file(
                Path(str(state_path) + "-wal"),
                optional=True,
                allow_empty=True,
                maximum_bytes=_MAX_STATE_EVIDENCE_BYTES,
                retain_body=False,
            ),
            "-shm": evidence.capture_file(
                Path(str(state_path) + "-shm"),
                optional=True,
                allow_empty=True,
                maximum_bytes=_MAX_STATE_EVIDENCE_BYTES,
                retain_body=False,
            ),
        }
        for suffix, retained in state_files.items():
            recorded = recorded_state[suffix]
            expected_path = (
                state_path if suffix == "main" else Path(str(state_path) + suffix)
            )
            if (recorded is None) != (retained is None) or (
                recorded is not None
                and not _stable_evidence_matches(
                    recorded, retained, expected_path
                )
            ):
                raise SystemPaperObserverError(
                    "SYSTEM_PAPER_OBSERVER_EVOLVING_STATE_INVALID"
                )

        first_recorded = observation["first_slot"]
        first_slot_id = first_recorded["slot_id"]
        artifact_path = (
            Path(contract["root_paths"]["artifacts"])
            / "system-paper-slots"
            / f"{first_slot_id}.json"
        )
        artifact = evidence.capture_file(
            artifact_path, maximum_bytes=_MAX_SLOT_EVIDENCE_BYTES
        )
        stdout = evidence.capture_file(stdout_path, allow_empty=False)
        stderr = evidence.capture_file(stderr_path, allow_empty=True)
        if artifact.evidence != first_recorded["artifact_evidence"]:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_ARTIFACT_CHANGED"
            )
        if not _stable_evidence_matches(
            first_recorded["stdout_evidence"], stdout, stdout_path
        ) or not _stable_evidence_matches(
            first_recorded["stderr_evidence"], stderr, stderr_path
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_LOG_IDENTITY_INVALID"
            )
        if stderr.body:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_STDERR_INVALID"
            )

        replay = _copy_state_and_replay(
            state_files, expected_slot_id=first_slot_id
        )
        events = replay["events"]
        succeeded = [
            event for event in events if event["event_type"] == "SUCCEEDED"
        ]
        if not succeeded:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_PREFIX_INVALID"
            )
        terminal = succeeded[0]
        prefix = tuple(
            event for event in events if event["sequence"] <= terminal["sequence"]
        )
        if (
            terminal["slot_id"] != first_slot_id
            or any(
                event["event_type"] in ("FAILED", "MISSED", "EXPIRED")
                for event in prefix
            )
            or sum(event["event_type"] == "SUCCEEDED" for event in prefix) != 1
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_PREFIX_INVALID"
            )
        prepared_input = replay["prepared_inputs"].get(first_slot_id)
        prepared_result = replay["prepared_results"].get(first_slot_id)
        if prepared_input is None or prepared_result is None:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_PREPARED_EVIDENCE_MISSING"
            )
        if prepared_result["result_bytes"] != artifact.body:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_PREPARED_RESULT_MISMATCH"
            )
        result = load_system_paper_slot_result_bytes(artifact.body)
        first_line_end = stdout.body.find(b"\n")
        if first_line_end < 0:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_STDOUT_INVALID"
            )
        first_line = stdout.body[: first_line_end + 1]
        runner_summary = _runner_summary_line(
            first_line, artifact.path, artifact.body, result
        )
        recorded_stdout = first_recorded["stdout_evidence"]
        if (
            recorded_stdout.get("size_bytes") != len(first_line)
            or recorded_stdout.get("sha256")
            != hashlib.sha256(first_line).hexdigest()
            or not stdout.body.startswith(first_line)
            or first_recorded["stderr_evidence"].get("size_bytes") != 0
            or first_recorded["stderr_evidence"].get("sha256")
            != hashlib.sha256(b"").hexdigest()
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_LOG_PREFIX_INVALID"
            )

        policy = SystemPaperSchedulePolicy.create(build_system_paper_plan())
        eligible = _first_slot_after_install(install["installed_at"], policy)
        if eligible.slot_id != first_slot_id:
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_IDENTITY_MISMATCH"
            )
        launchd = _replay_stored_launchd(
            observation["launchd"], contract=contract, install=install
        )
        replayed_first = {
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
            "event_chain_end_hash": terminal["event_hash"],
            "artifact_evidence": artifact.evidence,
            "stdout_evidence": dict(recorded_stdout),
            "stderr_evidence": dict(first_recorded["stderr_evidence"]),
            "runner_summary": runner_summary,
        }
        evidence.verify_unchanged()
        return {
            "status": "FIRST_NATURAL_SLOT_VERIFIED",
            "first_eligible_slot": {
                "slot_id": eligible.slot_id,
                "scheduled_for": eligible.scheduled_for,
                "due_at": eligible.due_at,
                "expires_at": eligible.expires_at,
            },
            "successful_slot_count": 1,
            "terminal_slot_count": 1,
            "first_slot": replayed_first,
            "launchd": launchd,
        }
    except SystemPaperObserverError:
        raise
    except Exception as error:
        raise SystemPaperObserverError(
            "SYSTEM_PAPER_OBSERVER_FIRST_SLOT_REPLAY_INVALID"
        ) from error
    finally:
        evidence.close()


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
    contract = load_system_paper_launchd_contract(
        contract_path=Path(contract_path), plist_path=Path(plist_path)
    )
    install = load_system_paper_install_receipt(
        receipt_path=Path(install_receipt_path),
        contract_path=Path(contract_path),
        plist_path=Path(plist_path),
        preflight_receipt_path=Path(preflight_receipt_path),
        _machine_probe=_machine_probe,
        _filesystem_probe=_filesystem_probe,
    )
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
        if source_files["contract"].body != canonical_json(contract).encode(
            "utf-8"
        ):
            raise SystemPaperObserverError(
                "SYSTEM_PAPER_OBSERVER_SOURCE_CHANGED"
            )
        state_files = {
            "main": evidence.capture_file(
                state_path, optional=True, retain_body=False
            ),
            "-wal": evidence.capture_file(
                Path(str(state_path) + "-wal"),
                optional=True,
                allow_empty=True,
                retain_body=False,
            ),
            "-shm": evidence.capture_file(
                Path(str(state_path) + "-shm"),
                optional=True,
                allow_empty=True,
                retain_body=False,
            ),
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
            artifacts[name] = evidence.capture_file(
                slots_directory / name,
                maximum_bytes=_MAX_SLOT_EVIDENCE_BYTES,
            )

        replay = _copy_state_and_replay(
            state_files, expected_slot_id=first_slot.slot_id
        )
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
        evidence.verify_unchanged()
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
