"""Tail-blind authority and fixed-tail evaluation for System Paper."""

import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .canonical import business_hash, canonical_json, utc_datetime
from .system_paper_evidence import publish_owner_exact
from .system_paper_install import load_system_paper_install_receipt
from .system_paper_launchd import load_system_paper_launchd_contract
from .system_paper_plan import load_system_paper_plan
from .system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    load_system_paper_schedule_event_metadata,
)
from .system_paper_runtime import (
    SystemPaperRuntimeError,
    load_system_paper_slot_result_bytes,
)
from .system_paper_start_receipt import (
    load_system_paper_start_receipt,
    load_system_paper_start_receipt_metadata,
)


_MAX_INSTALL_PREVIEW_BYTES = 2 * 1024 * 1024
_MAX_AUTHORITY_BYTES = 32 * 1024 * 1024
_MAX_STATE_BYTES = 128 * 1024 * 1024
_MAX_SLOT_ARTIFACT_BYTES = 1024 * 1024
_PRIVATE_TMP = Path("/private/tmp")
_TAIL_SETTLE_DELAY = timedelta(minutes=5)


class SystemPaperEvaluationError(ValueError):
    """The evaluator failed closed before producing a research claim."""

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
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    text = utc_datetime(parsed)
    if isinstance(value, str) and value != text:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    return parsed, text


def _now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _stat_identity(entry: os.stat_result) -> Tuple[int, ...]:
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_uid,
        entry.st_nlink,
        entry.st_size,
        entry.st_mtime_ns,
        entry.st_ctime_ns,
    )


class _RetainedAuthorityFile:
    """One no-follow owner-only file retained through the full observation."""

    def __init__(
        self,
        path,
        descriptor,
        entry,
        body,
        maximum_bytes,
        content_sha256,
    ):
        self.path = path
        self.descriptor = descriptor
        self.entry = entry
        self.body = body
        self.maximum_bytes = maximum_bytes
        self.content_sha256 = content_sha256

    @staticmethod
    def _read(descriptor: int, maximum_bytes: int) -> bytes:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks = []
        total = 0
        while total <= maximum_bytes:
            chunk = os.read(
                descriptor, min(64 * 1024, maximum_bytes + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        maximum_bytes: int = _MAX_AUTHORITY_BYTES,
        allow_empty: bool = False,
        retain_body: bool = True,
    ) -> "_RetainedAuthorityFile":
        path = Path(path)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path, flags)
            entry = os.fstat(descriptor)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != os.getuid()
                or entry.st_nlink != 1
                or stat.S_IMODE(entry.st_mode) != 0o600
                or entry.st_size > maximum_bytes
                or (entry.st_size == 0 and not allow_empty)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            if retain_body:
                body = cls._read(descriptor, maximum_bytes)
                bytes_read = len(body)
                content_sha256 = hashlib.sha256(body).hexdigest()
            else:
                os.lseek(descriptor, 0, os.SEEK_SET)
                digest = hashlib.sha256()
                bytes_read = 0
                while bytes_read <= maximum_bytes:
                    chunk = os.read(
                        descriptor,
                        min(
                            64 * 1024,
                            maximum_bytes + 1 - bytes_read,
                        ),
                    )
                    if not chunk:
                        break
                    digest.update(chunk)
                    bytes_read += len(chunk)
                body = None
                content_sha256 = digest.hexdigest()
            retained = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                bytes_read != entry.st_size
                or bytes_read > maximum_bytes
                or _stat_identity(entry) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return cls(
                path,
                descriptor,
                entry,
                body,
                maximum_bytes,
                content_sha256,
            )
        except SystemPaperEvaluationError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error

    def verify(self) -> None:
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path, follow_symlinks=False)
            os.lseek(self.descriptor, 0, os.SEEK_SET)
            offset = 0
            digest = hashlib.sha256()
            while offset <= self.maximum_bytes:
                chunk = os.read(
                    self.descriptor,
                    min(64 * 1024, self.maximum_bytes + 1 - offset),
                )
                if not chunk:
                    break
                digest.update(chunk)
                if (
                    self.body is not None
                    and self.body[offset : offset + len(chunk)] != chunk
                ):
                    raise SystemPaperEvaluationError(
                        "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                    )
                offset += len(chunk)
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            offset != self.entry.st_size
            or digest.hexdigest() != self.content_sha256
            or _stat_identity(self.entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        os.close(self.descriptor)


class _RetainedAuthorityAbsence:
    """Retain a directory attachment and prove one child stays absent."""

    def __init__(self, path, descriptor, parent_entry):
        self.path = path
        self.descriptor = descriptor
        self.parent_entry = parent_entry

    @classmethod
    def open(cls, path: Path) -> "_RetainedAuthorityAbsence":
        path = Path(path)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path.parent, flags)
            before = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o700
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            try:
                os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            retained = os.fstat(descriptor)
            current = os.stat(path.parent, follow_symlinks=False)
            if (
                _stat_identity(before) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return cls(path, descriptor, before)
        except SystemPaperEvaluationError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error

    def verify(self) -> None:
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path.parent, follow_symlinks=False)
            try:
                os.stat(
                    self.path.name,
                    dir_fd=self.descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
        except SystemPaperEvaluationError:
            raise
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            _stat_identity(self.parent_entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        os.close(self.descriptor)


class _RetainedAuthoritySet:
    def __init__(self):
        self.files = []

    def capture(self, path: Path, **kwargs) -> _RetainedAuthorityFile:
        retained = _RetainedAuthorityFile.open(path, **kwargs)
        self.files.append(retained)
        return retained

    def capture_absent(self, path: Path) -> None:
        retained = _RetainedAuthorityAbsence.open(path)
        self.files.append(retained)

    def capture_optional(
        self, path: Path, **kwargs
    ) -> Optional[_RetainedAuthorityFile]:
        try:
            return self.capture(path, **kwargs)
        except SystemPaperEvaluationError:
            self.capture_absent(path)
            return None

    def verify(self) -> None:
        for retained in self.files:
            retained.verify()

    def close(self) -> None:
        for retained in self.files:
            retained.close()


class _RetainedCohortSources:
    """Retain the exact artifact directory and every slot through evaluation."""

    def __init__(self):
        self.files = _RetainedAuthoritySet()
        self.path = None
        self.descriptor = None
        self.entry = None
        self.names = None

    def capture_directory(self, path: Path, expected_names) -> None:
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path, flags)
            before = os.fstat(descriptor)
            names = set(os.listdir(descriptor))
            after = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o700
                or _stat_identity(before) != _stat_identity(after)
                or _stat_identity(after) != _stat_identity(current)
                or names != set(expected_names)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
                )
            self.path = path
            self.descriptor = descriptor
            self.entry = before
            self.names = set(names)
        except SystemPaperEvaluationError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
            ) from error

    def capture_artifact(self, path: Path) -> _RetainedAuthorityFile:
        return self.files.capture(
            path, maximum_bytes=_MAX_SLOT_ARTIFACT_BYTES
        )

    def verify(self) -> None:
        self.files.verify()
        if (
            self.descriptor is None
            or self.path is None
            or self.entry is None
            or self.names is None
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path, follow_symlinks=False)
            names = set(os.listdir(self.descriptor))
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            _stat_identity(self.entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
            or names != self.names
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        self.files.close()
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def _absolute_paths(values: Mapping[str, Path]) -> Dict[str, Path]:
    result = {}
    for name, value in values.items():
        if not isinstance(value, (str, Path)) or "\x00" in str(value):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PATH_INVALID"
            )
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PATH_INVALID"
            )
        result[name] = path
    return result


def _derive_plist_path(contract_path: Path) -> Path:
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(contract_path.parent, flags)
        before = os.fstat(descriptor)
        names = set(os.listdir(descriptor))
        after = os.fstat(descriptor)
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o700
        or _stat_identity(before) != _stat_identity(after)
        or contract_path.name not in names
        or len(names) != 2
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        )
    other = next(iter(names - {contract_path.name}))
    if not other.endswith(".plist") or "/" in other:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        )
    return contract_path.parent / other


def _install_preview(retained: _RetainedAuthorityFile) -> Mapping[str, Any]:
    try:
        value = json.loads(retained.body.decode("utf-8"))
        if (
            not isinstance(value, Mapping)
            or canonical_json(value).encode("utf-8") != retained.body
            or not isinstance(value["preflight_receipt"]["receipt_path"], str)
        ):
            raise ValueError("invalid preview")
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
        ) from error
    return value


def _copy_event_metadata(
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    *,
    plan: Mapping[str, Any],
    temporary_parent: Path,
) -> Mapping[str, Any]:
    main = state_files["main"]
    if main is None:
        return {"events": (), "projection": {}}
    policy = SystemPaperSchedulePolicy.create(plan)
    try:
        with tempfile.TemporaryDirectory(
            prefix="system-paper-evaluation-", dir=str(temporary_parent)
        ) as directory:
            root = Path(directory)
            root.chmod(0o700)
            copy_path = root / "system-paper.sqlite"
            for suffix, retained in state_files.items():
                if retained is None:
                    continue
                target = (
                    copy_path
                    if suffix == "main"
                    else Path(str(copy_path) + suffix)
                )
                _write_retained_copy(retained, target)
                target.chmod(0o600)
            replay = load_system_paper_schedule_event_metadata(copy_path, policy)
    except SystemPaperEvaluationError:
        raise
    except Exception as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_STATE_REPLAY_INVALID"
        ) from error
    return replay


def _evaluate_complete_cohort(*_args, **_kwargs):
    raise SystemPaperEvaluationError(
        "SYSTEM_PAPER_EVALUATION_FINAL_NOT_IMPLEMENTED"
    )


@dataclass(frozen=True)
class _SystemPaperCohortSlot:
    slot_id: str
    scheduled_for: str
    artifact_path: str
    artifact_sha256: str
    input_bytes: bytes
    result_bytes: bytes
    slot_hash: str
    runtime_snapshot_hash: str


def _write_retained_copy(
    retained: _RetainedAuthorityFile, target: Path
) -> None:
    os.lseek(retained.descriptor, 0, os.SEEK_SET)
    with target.open("xb") as handle:
        while True:
            chunk = os.read(retained.descriptor, 64 * 1024)
            if not chunk:
                break
            handle.write(chunk)


def _strict_prepared_input(body: bytes) -> Mapping[str, Any]:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    def reject_number(_value):
        raise ValueError("binary float")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
        if (
            not isinstance(value, Mapping)
            or canonical_json(value).encode("utf-8") != body
        ):
            raise ValueError("noncanonical input")
        return value
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
        ) from error


def _stream_row_dicts(cursor) -> Tuple[Mapping[str, Any], ...]:
    return tuple(dict(row) for row in cursor)


def _copy_full_state_rows(
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    *,
    plan: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[Mapping[str, Any], ...]]:
    policy = SystemPaperSchedulePolicy.create(plan)
    try:
        with tempfile.TemporaryDirectory(
            prefix="system-paper-evaluation-full-", dir=str(_PRIVATE_TMP)
        ) as directory:
            root = Path(directory)
            root.chmod(0o700)
            copy_path = root / "system-paper.sqlite"
            for suffix, retained in state_files.items():
                if retained is None:
                    continue
                target = (
                    copy_path
                    if suffix == "main"
                    else Path(str(copy_path) + suffix)
                )
                _write_retained_copy(retained, target)
                target.chmod(0o600)
            copied_replay = load_system_paper_schedule_event_metadata(
                copy_path, policy
            )
            if copied_replay != replay:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
                )
            connection = sqlite3.connect(str(copy_path), timeout=0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA query_only = ON")
                inputs = _stream_row_dicts(
                    connection.execute(
                        "SELECT * FROM prepared_inputs ORDER BY slot_id"
                    )
                )
                results = _stream_row_dicts(
                    connection.execute(
                        "SELECT * FROM prepared_results ORDER BY slot_id"
                    )
                )
            finally:
                connection.close()
    except SystemPaperEvaluationError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
        ) from error
    return inputs, results


def _retained_evidence(retained: _RetainedAuthorityFile) -> Mapping[str, Any]:
    entry = retained.entry
    return {
        "path": str(retained.path),
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "mode": stat.S_IMODE(entry.st_mode),
        "owner_uid": entry.st_uid,
        "link_count": entry.st_nlink,
        "size_bytes": entry.st_size,
        "mtime_ns": str(entry.st_mtime_ns),
        "sha256": retained.content_sha256,
    }


def _replay_system_paper_cohort(
    *,
    plan: Mapping[str, Any],
    start: Mapping[str, Any],
    replay: Mapping[str, Any],
    slot_root: Path,
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    retained_sources: _RetainedCohortSources,
) -> Tuple[_SystemPaperCohortSlot, ...]:
    """Require the exact frozen cohort before any economic evaluation."""

    started, _started_text = _utc(start["cohort_started_at"])
    tail, _tail_text = _utc(start["cohort_tail_end"])
    expected_count = start.get("expected_slot_count")
    if (
        expected_count != 540
        or tail != started + timedelta(days=90)
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
        )
    policy = SystemPaperSchedulePolicy.create(plan)
    expected_slots = tuple(
        policy.slot_from_scheduled(started + timedelta(hours=4 * index))
        for index in range(expected_count)
    )
    if (
        expected_slots[-1].scheduled_for
        != utc_datetime(tail - timedelta(hours=4))
        or expected_slots[-1].expires_at
        != utc_datetime(tail + _TAIL_SETTLE_DELAY)
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
        )
    projection = replay.get("projection")
    expected_ids = {slot.slot_id for slot in expected_slots}
    if (
        not isinstance(projection, Mapping)
        or set(projection) != expected_ids
        or any(
            projection[slot.slot_id].get("terminal_state") != "SUCCEEDED"
            or projection[slot.slot_id].get("attempt_status") != "SUCCEEDED"
            or projection[slot.slot_id].get("durable_stage") != "RESULT"
            for slot in expected_slots
        )
        or any(
            event.get("event_type") in ("FAILED", "MISSED", "EXPIRED")
            for event in replay.get("events", ())
        )
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
        )
    expected_names = {slot.slot_id + ".json" for slot in expected_slots}
    retained_sources.capture_directory(slot_root, expected_names)
    try:
        artifact_sources = tuple(
            retained_sources.capture_artifact(
                slot_root / (slot.slot_id + ".json")
            )
            for slot in expected_slots
        )
        input_rows, result_rows = _copy_full_state_rows(
            state_files, plan=plan, replay=replay
        )
        inputs_by_slot = {row["slot_id"]: row for row in input_rows}
        results_by_slot = {row["slot_id"]: row for row in result_rows}
        if (
            len(input_rows) != len(expected_slots)
            or len(result_rows) != len(expected_slots)
            or set(inputs_by_slot) != expected_ids
            or set(results_by_slot) != expected_ids
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
            )
        artifact_bodies = tuple(source.body for source in artifact_sources)
        load_system_paper_slot_result_bytes(
            artifact_bodies[-1],
            parent_result_bodies=artifact_bodies[:-1],
        )
        output_root_hash = business_hash(
            {
                "purpose": "SYSTEM_PAPER_IMMUTABLE_OUTPUT_ROOT",
                "resolved_path": str(slot_root.parent.resolve()),
            }
        )
        cohort = []
        prefix = []
        first_success_hash = None
        for event in replay["events"]:
            if (
                event["slot_id"] == expected_slots[0].slot_id
                and event["event_type"] == "SUCCEEDED"
            ):
                first_success_hash = event["event_hash"]
                break
        for index, (slot, source) in enumerate(
            zip(expected_slots, artifact_sources)
        ):
            input_row = inputs_by_slot[slot.slot_id]
            result_row = results_by_slot[slot.slot_id]
            input_body = input_row["input_bytes"]
            result_body = result_row["result_bytes"]
            if not isinstance(input_body, bytes) or not isinstance(result_body, bytes):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
                )
            envelope = _strict_prepared_input(input_body)
            result = json.loads(source.body.decode("utf-8"))
            prefix.append(slot.slot_id)
            expected_input_hashes = {
                "input_sha256": hashlib.sha256(input_body).hexdigest(),
                "plan_hash": plan["plan_hash"],
                "market_bundle_hash": envelope["capture"][
                    "public_market_bundle"
                ]["bundle_hash"],
                "previous_snapshot_hash": envelope[
                    "previous_runtime_snapshot"
                ]["snapshot_hash"],
                "fill_scenario_hash": business_hash(envelope["fill_scenario"]),
                "output_root_hash": output_root_hash,
            }
            expected_result_hashes = {
                "result_sha256": hashlib.sha256(result_body).hexdigest(),
                "slot_hash": result["slot_hash"],
                "runtime_snapshot_hash": result["runtime_snapshot"][
                    "snapshot_hash"
                ],
                "parent_slot_hash": result["parent_slot_hash_or_null"]
                or "0" * 64,
                "output_root_hash": output_root_hash,
            }
            if (
                source.body != result_body
                or any(
                    input_row[name] != value
                    for name, value in expected_input_hashes.items()
                )
                or any(
                    result_row[name] != value
                    for name, value in expected_result_hashes.items()
                )
                or envelope.get("slot_id") != slot.slot_id
                or envelope.get("scheduled_for") != slot.scheduled_for
                or envelope.get("plan") != plan
                or envelope.get("schedule_policy_hash")
                != policy.schedule_policy_hash
                or envelope.get("output_root_hash") != output_root_hash
                or result.get("slot_id") != slot.slot_id
                or result.get("scheduled_for") != slot.scheduled_for
                or result.get("plan_hash") != plan["plan_hash"]
                or result.get("replay_inputs")
                != {
                    "plan": envelope["plan"],
                    "scheduled_for": envelope["scheduled_for"],
                    "public_market_bundle": envelope["capture"][
                        "public_market_bundle"
                    ],
                    "previous_runtime_snapshot": envelope[
                        "previous_runtime_snapshot"
                    ],
                    "fill_scenario": envelope["fill_scenario"],
                }
                or result["runtime_snapshot"]["processed_slot_ids"] != prefix
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
                )
            if index == 0:
                first = start["first_slot"]
                if (
                    first["slot_id"] != slot.slot_id
                    or first["scheduled_for"] != slot.scheduled_for
                    or first["result_path"] != str(source.path)
                    or first["result_sha256"]
                    != hashlib.sha256(source.body).hexdigest()
                    or first["slot_hash"] != result["slot_hash"]
                    or first["runtime_snapshot_hash"]
                    != result["runtime_snapshot"]["snapshot_hash"]
                    or first["prepared_input_sha256"]
                    != expected_input_hashes["input_sha256"]
                    or first["prepared_result_sha256"]
                    != expected_result_hashes["result_sha256"]
                    or first["event_chain_end_hash"] != first_success_hash
                    or first["artifact_evidence"]
                    != _retained_evidence(source)
                ):
                    raise SystemPaperEvaluationError(
                        "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
                    )
            cohort.append(
                _SystemPaperCohortSlot(
                    slot_id=slot.slot_id,
                    scheduled_for=slot.scheduled_for,
                    artifact_path=str(source.path),
                    artifact_sha256=hashlib.sha256(source.body).hexdigest(),
                    input_bytes=input_body,
                    result_bytes=source.body,
                    slot_hash=result["slot_hash"],
                    runtime_snapshot_hash=result["runtime_snapshot"][
                        "snapshot_hash"
                    ],
                )
            )
        retained_sources.verify()
        return tuple(cohort)
    except SystemPaperEvaluationError:
        raise
    except (KeyError, OSError, TypeError, ValueError, SystemPaperRuntimeError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID"
        ) from error


def observe_system_paper_evaluation_readiness(
    *,
    plan_path: Path,
    start_receipt_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    slot_root: Path,
    runtime_root: Path,
    output_root: Path,
    _clock=None,
    _machine_probe=None,
    _filesystem_probe=None,
) -> Mapping[str, Any]:
    """Observe readiness without reading any slot economic artifact pre-tail."""

    paths = _absolute_paths(
        {
            "plan": plan_path,
            "start": start_receipt_path,
            "install": install_receipt_path,
            "contract": contract_path,
            "slot_root": slot_root,
            "runtime_root": runtime_root,
            "output_root": output_root,
        }
    )
    observed, observed_at = _utc((_clock or _now)())
    retained = _RetainedAuthoritySet()
    state_retained = _RetainedAuthoritySet()
    cohort_retained = _RetainedCohortSources()
    try:
        try:
            install_source = retained.capture(
                paths["install"], maximum_bytes=_MAX_INSTALL_PREVIEW_BYTES
            )
        except SystemPaperEvaluationError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
            ) from error
        preview = _install_preview(install_source)
        plist_path = _derive_plist_path(paths["contract"])
        preflight_path = Path(preview["preflight_receipt"]["receipt_path"])
        if not preflight_path.is_absolute() or ".." in preflight_path.parts:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
            )
        retained.capture(paths["plan"])
        retained.capture(paths["contract"])
        retained.capture(plist_path)
        retained.capture(preflight_path)
        retained.capture(paths["start"], maximum_bytes=4 * 1024 * 1024)

        plan = load_system_paper_plan(paths["plan"])
        contract = load_system_paper_launchd_contract(
            contract_path=paths["contract"], plist_path=plist_path
        )
        if (
            paths["runtime_root"] != Path(contract["runtime_root"])
            or paths["slot_root"]
            != Path(contract["root_paths"]["artifacts"])
            / "system-paper-slots"
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_ROOT_MISMATCH"
            )
        install = load_system_paper_install_receipt(
            receipt_path=paths["install"],
            contract_path=paths["contract"],
            plist_path=plist_path,
            preflight_receipt_path=preflight_path,
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        retained.capture(Path(install["target_path"]))
        start = load_system_paper_start_receipt_metadata(
            receipt_path=paths["start"],
            contract_path=paths["contract"],
            plist_path=plist_path,
            preflight_receipt_path=preflight_path,
            install_receipt_path=paths["install"],
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        if (
            plan["plan_hash"] != contract["plan_hash"]
            or install["receipt_hash"]
            != start["source_binding"]["install_receipt_hash"]
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
            )

        state_path = (
            Path(contract["root_paths"]["state"])
            / "system-paper.sqlite"
        )
        state_files = {
            "main": state_retained.capture(
                state_path,
                maximum_bytes=_MAX_STATE_BYTES,
                retain_body=False,
            ),
            "-wal": None,
            "-shm": None,
        }
        for suffix in ("-wal", "-shm"):
            candidate = Path(str(state_path) + suffix)
            state_files[suffix] = state_retained.capture_optional(
                candidate,
                allow_empty=True,
                maximum_bytes=_MAX_STATE_BYTES,
                retain_body=False,
            )
        replay = _copy_event_metadata(
            state_files,
            plan=plan,
            temporary_parent=_PRIVATE_TMP,
        )
        start_at, start_text = _utc(start["cohort_started_at"])
        tail_at, tail_text = _utc(start["cohort_tail_end"])
        if observed >= tail_at + _TAIL_SETTLE_DELAY:
            replayed_start = load_system_paper_start_receipt(
                receipt_path=paths["start"],
                contract_path=paths["contract"],
                plist_path=plist_path,
                preflight_receipt_path=preflight_path,
                install_receipt_path=paths["install"],
                _machine_probe=_machine_probe,
                _filesystem_probe=_filesystem_probe,
            )
            if replayed_start != start:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
                )
            cohort = _replay_system_paper_cohort(
                plan=plan,
                start=start,
                replay=replay,
                slot_root=paths["slot_root"],
                state_files=state_files,
                retained_sources=cohort_retained,
            )
            complete = _evaluate_complete_cohort(
                plan=plan,
                contract=contract,
                install=install,
                start=start,
                replay=replay,
                cohort=cohort,
                observed_at=observed_at,
                slot_root=paths["slot_root"],
            )
            cohort_retained.verify()
            retained.verify()
            state_retained.verify()
            return complete
        projection = replay["projection"]
        incidents = sum(
            event["event_type"] in ("FAILED", "MISSED", "EXPIRED")
            for event in replay["events"]
        )
        successes = sum(
            item["terminal_state"] == "SUCCEEDED"
            for item in projection.values()
        )
        policy = SystemPaperSchedulePolicy.create(plan)
        scheduled = start_at
        next_required = None
        while scheduled < tail_at:
            slot = policy.slot_from_scheduled(scheduled)
            if (
                slot.slot_id not in projection
                or projection[slot.slot_id]["terminal_state"] != "SUCCEEDED"
            ):
                next_required = {
                    "slot_id": slot.slot_id,
                    "scheduled_for": slot.scheduled_for,
                    "due_at": slot.due_at,
                    "expires_at": slot.expires_at,
                }
                break
            scheduled += timedelta(hours=4)
        retained.verify()
        state_retained.verify()
        return {
            "status": "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL",
            "observed_at": observed_at,
            "cohort_started_at": start_text,
            "tail_end": tail_text,
            "elapsed_days": max(
                0, int((observed - start_at).total_seconds() // 86_400)
            ),
            "verified_terminal_slot_count": successes,
            "incident_count": incidents,
            "next_required_slot": next_required,
            "evidence_health": (
                "VERIFIED" if incidents == 0 else "INCIDENT_DETECTED"
            ),
        }
    except SystemPaperEvaluationError:
        raise
    except Exception as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        ) from error
    finally:
        cohort_retained.close()
        state_retained.close()
        retained.close()
