"""Tail-blind authority and fixed-tail evaluation for System Paper."""

import fcntl
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    localcontext,
)
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
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
    SystemPaperStartReceiptError,
    load_system_paper_start_receipt,
    load_system_paper_start_receipt_metadata,
)


_MAX_INSTALL_PREVIEW_BYTES = 2 * 1024 * 1024
_MAX_AUTHORITY_BYTES = 32 * 1024 * 1024
_MAX_STATE_BYTES = 128 * 1024 * 1024
_MAX_SLOT_ARTIFACT_BYTES = 1024 * 1024
_MAX_INVENTORY_ENTRIES = 1024
_INVENTORY_DIGEST_MODULUS = 1 << 256
_PRIVATE_TMP = Path("/private/tmp")
_TAIL_SETTLE_DELAY = timedelta(minutes=5)
_STARTING_EQUITY = Decimal("1000")
_STUDENT_T_95_ONE_SIDED_DF2 = Decimal("2.91998558035372")
_EVALUATION_SCHEMA = "system-paper-evaluation-v1.schema.json"
_MAX_EVALUATION_BYTES = 8 * 1024 * 1024
_ZERO_HASH = "0" * 64
FROZEN_CONTEXT = Context(
    prec=50,
    rounding=ROUND_HALF_EVEN,
    Emin=-999999,
    Emax=999999,
    capitals=1,
    clamp=0,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


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


def _directory_attachment_identity(entry: os.stat_result) -> Tuple[int, ...]:
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_uid,
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


class _RetainedOutputRoot:
    """Owner-only root retained for relative result operations."""

    def __init__(self, path: Path, descriptor: int, entry: os.stat_result):
        self.path = path
        self.descriptor = descriptor
        self.entry = entry
        self.files = []
        self.locked = False

    @classmethod
    def open(cls, path: Path) -> "_RetainedOutputRoot":
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path, flags)
            entry = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                not stat.S_ISDIR(entry.st_mode)
                or entry.st_uid != os.getuid()
                or stat.S_IMODE(entry.st_mode) != 0o700
                or _directory_attachment_identity(entry)
                != _directory_attachment_identity(current)
            ):
                raise OSError("unsafe output root")
            return cls(path, descriptor, entry)
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
            ) from error

    def _relative_file(
        self, name: str, *, maximum_bytes: int
    ) -> _RetainedAuthorityFile:
        descriptor = None
        try:
            if not name or name in (".", "..") or "/" in name or "\x00" in name:
                raise OSError("unsafe result name")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(name, flags, dir_fd=self.descriptor)
            entry = os.fstat(descriptor)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != os.getuid()
                or entry.st_nlink != 1
                or stat.S_IMODE(entry.st_mode) != 0o600
                or entry.st_size <= 0
                or entry.st_size > maximum_bytes
            ):
                raise OSError("unsafe result")
            body = _RetainedAuthorityFile._read(descriptor, maximum_bytes)
            retained = os.fstat(descriptor)
            current = os.stat(
                name, dir_fd=self.descriptor, follow_symlinks=False
            )
            if (
                len(body) != entry.st_size
                or _stat_identity(entry) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise OSError("changed result")
            source = _RetainedAuthorityFile(
                self.path / name,
                descriptor,
                entry,
                body,
                maximum_bytes,
                hashlib.sha256(body).hexdigest(),
            )
            self.files.append((name, source))
            return source
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_RESULT_INVALID"
            ) from error

    def acquire_lock(self) -> None:
        if self.locked:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
            )
        try:
            fcntl.flock(self.descriptor, fcntl.LOCK_EX)
            self.verify()
            self.locked = True
        except Exception as error:
            try:
                fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
            ) from error

    def verify(self) -> None:
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path, follow_symlinks=False)
            if (
                _directory_attachment_identity(self.entry)
                != _directory_attachment_identity(retained)
                or _directory_attachment_identity(retained)
                != _directory_attachment_identity(current)
            ):
                raise OSError("changed output root")
            for name, source in self.files:
                source.verify()
                attached = os.stat(
                    name,
                    dir_fd=self.descriptor,
                    follow_symlinks=False,
                )
                if _stat_identity(source.entry) != _stat_identity(attached):
                    raise OSError("detached result")
        except (OSError, SystemPaperEvaluationError) as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_RESULT_INVALID"
            ) from error

    def close(self) -> None:
        for _name, source in self.files:
            source.close()
        self.files = []
        try:
            if self.locked:
                fcntl.flock(self.descriptor, fcntl.LOCK_UN)
                self.locked = False
        finally:
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
            _directory_attachment_identity(self.parent_entry)
            != _directory_attachment_identity(retained)
            or _directory_attachment_identity(retained)
            != _directory_attachment_identity(current)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        os.close(self.descriptor)


class _RetainedAuthorityEntry:
    """Retain exact no-follow metadata for an entry whose bytes are unsafe."""

    def __init__(self, path, descriptor, parent_entry, entry):
        self.path = path
        self.descriptor = descriptor
        self.parent_entry = parent_entry
        self.entry = entry

    @classmethod
    def open(cls, path: Path) -> "_RetainedAuthorityEntry":
        path = Path(path)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path.parent, flags)
            before = os.fstat(descriptor)
            entry = os.stat(
                path.name, dir_fd=descriptor, follow_symlinks=False
            )
            retained = os.fstat(descriptor)
            current = os.stat(path.parent, follow_symlinks=False)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o700
                or _stat_identity(before) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return cls(path, descriptor, before, entry)
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
            current_parent = os.stat(self.path.parent, follow_symlinks=False)
            current = os.stat(
                self.path.name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            _directory_attachment_identity(self.parent_entry)
            != _directory_attachment_identity(retained)
            or _directory_attachment_identity(retained)
            != _directory_attachment_identity(current_parent)
            or _stat_identity(self.entry) != _stat_identity(current)
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

    def capture_entry(self, path: Path) -> _RetainedAuthorityEntry:
        retained = _RetainedAuthorityEntry.open(path)
        self.files.append(retained)
        return retained

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


def _unsafe_inventory_status(entry: os.stat_result) -> Optional[str]:
    if stat.S_ISLNK(entry.st_mode):
        return "UNSAFE_SYMLINK"
    if not stat.S_ISREG(entry.st_mode):
        return "UNSAFE_TYPE"
    if entry.st_uid != os.getuid():
        return "UNSAFE_OWNER"
    if entry.st_nlink != 1:
        return "UNSAFE_HARDLINK"
    if stat.S_IMODE(entry.st_mode) != 0o600:
        return "UNSAFE_MODE"
    if entry.st_size > _MAX_SLOT_ARTIFACT_BYTES:
        return "UNSAFE_OVERSIZED"
    if entry.st_size == 0:
        return "UNSAFE_EMPTY"
    return None


def _unsafe_inventory_evidence(
    name: str, entry: os.stat_result, status_code: str
) -> Mapping[str, Any]:
    return {
        "artifact_name": name,
        "entry_status": status_code,
        "entry_identity_hash": business_hash(
            {
                "artifact_name": name,
                "stat_identity": tuple(
                    str(value) for value in _stat_identity(entry)
                ),
            }
        ),
    }


@dataclass(frozen=True)
class _InventoryDirectorySnapshot:
    """Constant-memory, order-independent identity for one directory scan."""

    entry_count: int
    digest_xor: str
    digest_sum: str
    digest_sum_squares: str
    bounded_names: Optional[Tuple[str, ...]]
    has_unsafe_entry: bool


def _inventory_entry_digest(name: str, entry: os.stat_result) -> int:
    digest = hashlib.sha256()
    digest.update(b"SYSTEM_PAPER_INVENTORY_ENTRY_V1\x00")
    name_bytes = os.fsencode(name)
    digest.update(len(name_bytes).to_bytes(8, "big"))
    digest.update(name_bytes)
    for value in _stat_identity(entry):
        encoded = str(value).encode("ascii")
        digest.update(len(encoded).to_bytes(2, "big"))
        digest.update(encoded)
    return int.from_bytes(digest.digest(), "big")


def _scan_inventory_directory(
    descriptor: int,
) -> _InventoryDirectorySnapshot:
    """Fingerprint every no-follow child without materializing the directory."""

    entry_count = 0
    digest_xor = 0
    digest_sum = 0
    digest_sum_squares = 0
    bounded_names = []
    has_unsafe_entry = False
    try:
        with os.scandir(descriptor) as entries:
            for candidate in entries:
                name = candidate.name
                child = os.stat(
                    name,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                entry_digest = _inventory_entry_digest(name, child)
                entry_count += 1
                digest_xor ^= entry_digest
                digest_sum = (
                    digest_sum + entry_digest
                ) % _INVENTORY_DIGEST_MODULUS
                digest_sum_squares = (
                    digest_sum_squares + entry_digest * entry_digest
                ) % _INVENTORY_DIGEST_MODULUS
                has_unsafe_entry = (
                    has_unsafe_entry
                    or _unsafe_inventory_status(child) is not None
                )
                if bounded_names is not None:
                    if entry_count <= _MAX_INVENTORY_ENTRIES:
                        bounded_names.append(name)
                    else:
                        bounded_names = None
    except OSError as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
        ) from error
    return _InventoryDirectorySnapshot(
        entry_count=entry_count,
        digest_xor=f"{digest_xor:064x}",
        digest_sum=f"{digest_sum:064x}",
        digest_sum_squares=f"{digest_sum_squares:064x}",
        bounded_names=(
            None
            if bounded_names is None
            else tuple(sorted(bounded_names))
        ),
        has_unsafe_entry=has_unsafe_entry,
    )


def _inventory_snapshot_hash(
    directory_entry: os.stat_result,
    snapshot: _InventoryDirectorySnapshot,
) -> str:
    return business_hash(
        {
            "directory_stat_identity": tuple(
                str(value) for value in _stat_identity(directory_entry)
            ),
            "entry_count": snapshot.entry_count,
            "entry_digest_xor": snapshot.digest_xor,
            "entry_digest_sum": snapshot.digest_sum,
            "entry_digest_sum_squares": snapshot.digest_sum_squares,
        }
    )


class _RetainedCohortSources:
    """Retain the exact artifact directory and every slot through evaluation."""

    def __init__(self):
        self.files = _RetainedAuthoritySet()
        self.path = None
        self.descriptor = None
        self.entry = None
        self.snapshot = None

    def capture_directory(self, path: Path):
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path, flags)
            before = os.fstat(descriptor)
            if not stat.S_ISDIR(before.st_mode):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
                )
            snapshot = _scan_inventory_directory(descriptor)
            after = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                _stat_identity(before) != _stat_identity(after)
                or _stat_identity(after) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            self.path = path
            self.descriptor = descriptor
            self.entry = before
            self.snapshot = snapshot
            return snapshot.bounded_names
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

    def capture_inventory_artifact(self, path: Path):
        if self.descriptor is None:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )
        try:
            entry = os.stat(
                path.name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        status_code = _unsafe_inventory_status(entry)
        if status_code is None:
            return self.capture_artifact(path), None
        return None, _unsafe_inventory_evidence(
            path.name, entry, status_code
        )

    def verify(self) -> None:
        self.files.verify()
        if (
            self.descriptor is None
            or self.path is None
            or self.entry is None
            or self.snapshot is None
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path, follow_symlinks=False)
            snapshot = _scan_inventory_directory(self.descriptor)
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            _stat_identity(self.entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
            or snapshot != self.snapshot
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        self.files.close()
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


class _RetainedEvaluationAuthority:
    """Keep the observer's first authority capture live through publication."""

    def __init__(self):
        self.files = _RetainedAuthoritySet()
        self.state = _RetainedAuthoritySet()
        self.cohort = _RetainedCohortSources()
        self.inconclusive_inventory = _RetainedCohortSources()
        self.inconclusive_attachment = _RetainedAuthoritySet()

    def verify(self) -> None:
        self.files.verify()
        self.state.verify()
        if self.cohort.descriptor is not None:
            self.cohort.verify()
        if self.inconclusive_inventory.descriptor is not None:
            self.inconclusive_inventory.verify()
        self.inconclusive_attachment.verify()

    def close(self) -> None:
        self.inconclusive_attachment.close()
        self.inconclusive_inventory.close()
        self.cohort.close()
        self.state.close()
        self.files.close()


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


def _expected_evaluation_output_root(contract: Mapping[str, Any]) -> Path:
    """Derive the sole evaluator publication root from contract authority."""

    try:
        artifacts = Path(contract["root_paths"]["artifacts"])
    except (KeyError, TypeError, ValueError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        ) from error
    if not artifacts.is_absolute() or ".." in artifacts.parts:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        )
    return artifacts / "system-paper-evaluations"


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


def _raw_state_group_hash(
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
) -> str:
    members = []
    for suffix in ("main", "-wal", "-shm"):
        retained = state_files[suffix]
        members.append(
            {
                "suffix": suffix,
                "state": "PRESENT" if retained is not None else "ABSENT",
                "sha256_or_null": (
                    retained.content_sha256 if retained is not None else None
                ),
            }
        )
    return business_hash(
        {
            "purpose": "SYSTEM_PAPER_RAW_SQLITE_GROUP_V1",
            "members": members,
        }
    )


def _state_binding(
    *,
    replay: Optional[Mapping[str, Any]],
    raw_state_group_hash: str,
) -> Mapping[str, Any]:
    if replay is None:
        return {
            "state_binding_kind": "RAW_SQLITE_GROUP",
            "state_binding_hash": raw_state_group_hash,
            "event_chain_end_hash_or_null": None,
            "raw_state_group_hash": raw_state_group_hash,
        }
    events = tuple(replay.get("events", ()))
    event_hash = events[-1]["event_hash"] if events else _ZERO_HASH
    return {
        "state_binding_kind": "EVENT_CHAIN_END",
        "state_binding_hash": event_hash,
        "event_chain_end_hash_or_null": event_hash,
        "raw_state_group_hash": raw_state_group_hash,
    }


def _stable_replay_reason(error: SystemPaperEvaluationError) -> str:
    cause = error.__cause__
    if cause is not None and "PREPARED" in str(cause):
        return "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
    return "SYSTEM_PAPER_EVALUATION_STATE_REPLAY_INVALID"


def _evaluate_complete_cohort(*_args, **kwargs):
    economic = _evaluate_complete_system_paper_cohort(kwargs["cohort"])
    cohort = tuple(kwargs["cohort"])
    replay = kwargs["replay"]
    events = tuple(replay["events"])
    if not events:
        raise SystemPaperEvaluationError("SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE")
    inventory = tuple(
        {
            "artifact_name": Path(slot.artifact_path).name,
            "slot_id": slot.slot_id,
            "scheduled_for": slot.scheduled_for,
            "artifact_sha256": slot.artifact_sha256,
            "prepared_input_sha256": hashlib.sha256(slot.input_bytes).hexdigest(),
            "prepared_result_sha256": hashlib.sha256(slot.result_bytes).hexdigest(),
            "slot_hash": slot.slot_hash,
            "runtime_snapshot_hash": slot.runtime_snapshot_hash,
        }
        for slot in cohort
    )
    activity = {
        "credential_reads": 0,
        "account_requests": 0,
        "real_broker_calls": 0,
        "real_order_writes": 0,
    }
    for slot in cohort:
        result = json.loads(slot.result_bytes.decode("utf-8"))
        for name in activity:
            activity[name] += result["safety_counts"][name]
    return {
        **economic,
        "tail_end": kwargs["start"]["cohort_tail_end"],
        "source_binding": {
            "plan_hash": kwargs["plan"]["plan_hash"],
            "install_receipt_hash": kwargs["install"]["receipt_hash"],
            "contract_hash": kwargs["contract"]["contract_hash"],
            "start_receipt_hash": kwargs["start"]["receipt_hash"],
            **_state_binding(
                replay=replay,
                raw_state_group_hash=kwargs["raw_state_group_hash"],
            ),
        },
        "evidence_inventory": inventory,
        "security_counts": activity,
    }


def _maximum_drawdown(equities) -> Decimal:
    with localcontext(FROZEN_CONTEXT):
        values = tuple(equities)
        if (
            not values
            or any(
                not isinstance(value, Decimal) or value <= 0
                for value in values
            )
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
            )
        peak = values[0]
        maximum = Decimal("0")
        for value in values:
            peak = max(peak, value)
            maximum = max(maximum, (peak - value) / peak)
        return maximum


def _three_block_statistics(equities) -> Mapping[str, Any]:
    values = tuple(equities)
    if (
        len(values) != 540
        or any(
            not isinstance(value, Decimal) or value <= 0
            for value in values
        )
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
        )
    starts = (_STARTING_EQUITY, values[179], values[359])
    ends = (values[179], values[359], values[539])
    with localcontext(FROZEN_CONTEXT):
        returns = tuple(
            (end - start) / start for start, end in zip(starts, ends)
        )
        mean = sum(returns, Decimal("0")) / Decimal("3")
        sample_variance = sum(
            ((value - mean) ** 2 for value in returns), Decimal("0")
        ) / Decimal("2")
        sample_sd = sample_variance.sqrt()
        lcb = mean - (
            _STUDENT_T_95_ONE_SIDED_DF2
            * sample_sd
            / Decimal("3").sqrt()
        )
    return {
        "block_returns": returns,
        "mean": mean,
        "sample_sd": sample_sd,
        "lcb": lcb,
        "passed": lcb > 0,
    }


def _decimal_value(value: object) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
        ) from error
    if not parsed.is_finite():
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
        )
    return parsed


def _evaluate_complete_system_paper_cohort(
    cohort,
) -> Mapping[str, Any]:
    with localcontext(FROZEN_CONTEXT):
        return _evaluate_complete_system_paper_cohort_decimal(cohort)


def _evaluate_complete_system_paper_cohort_decimal(
    cohort,
) -> Mapping[str, Any]:
    slots = tuple(cohort)
    if len(slots) != 540 or any(
        not isinstance(slot, _SystemPaperCohortSlot) for slot in slots
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
        )
    duplicate_order_events = 0
    unrecorded_fills = 0
    hard_risk_violations = 0
    reconciliation_exposure_increases = 0
    forbidden_activity_count = 0
    traceable_count = 0
    full_replay_count = 0
    seen_order_events = set()
    seen_order_ids = set()
    gross_filled_notional = Decimal("0")
    modeled_execution_cost = Decimal("0")
    maximum_fee_rate = Decimal("0")
    maximum_slippage_rate = Decimal("0")
    equities = []
    final_active_order = False
    final_risk_locked = False
    try:
        for index, slot in enumerate(slots):
            result = json.loads(slot.result_bytes.decode("utf-8"))
            envelope = _strict_prepared_input(slot.input_bytes)
            bundle = envelope["capture"]["public_market_bundle"]
            ledger = result["ledger"]
            reconciliation = result["reconciliation"]
            snapshot = result["runtime_snapshot"]
            replay_flags = result["replay"]
            order = result["order"]
            equities.append(_decimal_value(snapshot["marked_equity_usdt"]))
            forbidden_activity_count += sum(
                result["safety_counts"][name]
                for name in (
                    "credential_reads",
                    "account_requests",
                    "real_broker_calls",
                    "real_order_writes",
                )
            )
            traceable = (
                result["slot_id"] == slot.slot_id
                and result["scheduled_for"] == slot.scheduled_for
                and result["market_bundle_hash"] == bundle["bundle_hash"]
                and isinstance(result["signal"]["decision_hash"], str)
                and bool(result["signal"]["decision_hash"])
                and ledger["balanced"] is True
                and ledger["debits_usdt"] == ledger["credits_usdt"]
                and reconciliation["unexplained_position_difference"] == "0"
                and reconciliation["ledger_imbalance_usdt"] == "0"
            )
            if traceable:
                traceable_count += 1
            if (
                replay_flags["decision_hash_match"] is True
                and replay_flags["market_bundle_hash_match"] is True
                and replay_flags["full_slot_hash_match"] is True
            ):
                full_replay_count += 1
            previous_snapshot = result["replay_inputs"][
                "previous_runtime_snapshot"
            ]
            if (
                previous_snapshot["active_order_or_null"] is not None
                and _decimal_value(snapshot["position_quantity"])
                > _decimal_value(previous_snapshot["position_quantity"])
            ):
                reconciliation_exposure_increases += 1
            if order is not None:
                local_order_id = order["local_order_id"]
                if local_order_id in seen_order_ids:
                    duplicate_order_events += 1
                seen_order_ids.add(local_order_id)
                for event_id in order["event_ids"]:
                    if event_id in seen_order_events:
                        duplicate_order_events += 1
                    seen_order_events.add(event_id)
                filled = _decimal_value(order["filled_quantity"])
                if filled < 0:
                    raise SystemPaperEvaluationError(
                        "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
                    )
                if filled > 0:
                    if not ledger["entries"]:
                        unrecorded_fills += 1
                    if (
                        order["side"] == "BUY"
                        and (
                            result["risk"]["state"] == "LOCKED"
                            or result["risk"]["drawdown_state"]
                            in ("HALT", "HARD_BOUNDARY")
                        )
                    ):
                        hard_risk_violations += 1
                    price = _decimal_value(
                        order["average_fill_price_or_null"]
                    )
                    fee = _decimal_value(order["fee_usdt"])
                    if price <= 0 or fee < 0:
                        raise SystemPaperEvaluationError(
                            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
                        )
                    notional = filled * price
                    gross_filled_notional += notional
                    if order["side"] == "BUY":
                        touch = _decimal_value(bundle["bbo"]["ask_price"])
                        shortfall = max(
                            Decimal("0"), (price - touch) * filled
                        )
                    elif order["side"] == "SELL":
                        touch = _decimal_value(bundle["bbo"]["bid_price"])
                        shortfall = max(
                            Decimal("0"), (touch - price) * filled
                        )
                    else:
                        raise SystemPaperEvaluationError(
                            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
                        )
                    fee_rate = fee / notional
                    slippage_rate = shortfall / notional
                    maximum_fee_rate = max(maximum_fee_rate, fee_rate)
                    maximum_slippage_rate = max(
                        maximum_slippage_rate, slippage_rate
                    )
                    modeled_execution_cost += fee + shortfall
            if index == len(slots) - 1:
                final_active_order = snapshot["active_order_or_null"] is not None
                final_risk_locked = snapshot["risk_state"] == "LOCKED"
    except SystemPaperEvaluationError:
        raise
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_ECONOMIC_INPUT_INVALID"
        ) from error

    traceability_ratio = Decimal(traceable_count) / Decimal("540")
    full_replay_ratio = Decimal(full_replay_count) / Decimal("540")
    safety_passed = (
        duplicate_order_events == 0
        and unrecorded_fills == 0
        and hard_risk_violations == 0
        and reconciliation_exposure_increases == 0
        and forbidden_activity_count == 0
        and not final_active_order
        and not final_risk_locked
        and traceability_ratio == 1
        and full_replay_ratio == 1
    )
    aggregate_limit = gross_filled_notional * Decimal("0.0025")
    cost_passed = (
        maximum_fee_rate <= Decimal("0.0015")
        and maximum_slippage_rate <= Decimal("0.001")
        and modeled_execution_cost <= aggregate_limit
    )
    maximum_drawdown = _maximum_drawdown(
        (_STARTING_EQUITY,) + tuple(equities)
    )
    drawdown_passed = maximum_drawdown < Decimal("0.10")
    blocks = _three_block_statistics(tuple(equities))
    gates = {
        "safety": {
            "passed": safety_passed,
            "duplicate_order_events": duplicate_order_events,
            "duplicate_order_events_threshold": 0,
            "unrecorded_fills": unrecorded_fills,
            "unrecorded_fills_threshold": 0,
            "hard_risk_violations": hard_risk_violations,
            "hard_risk_violations_threshold": 0,
            "reconciliation_exposure_increases": (
                reconciliation_exposure_increases
            ),
            "reconciliation_exposure_increases_threshold": 0,
            "forbidden_activity_count": forbidden_activity_count,
            "forbidden_activity_count_threshold": 0,
            "final_active_order": final_active_order,
            "final_active_order_threshold": False,
            "final_risk_locked": final_risk_locked,
            "final_risk_locked_threshold": False,
            "traceability_ratio": traceability_ratio,
            "traceability_ratio_threshold": Decimal("1"),
            "full_replay_ratio": full_replay_ratio,
            "full_replay_ratio_threshold": Decimal("1"),
        },
        "cost": {
            "passed": cost_passed,
            "maximum_effective_fee_rate": maximum_fee_rate,
            "fee_rate_limit": Decimal("0.0015"),
            "maximum_effective_slippage_rate": maximum_slippage_rate,
            "slippage_rate_limit": Decimal("0.001"),
            "gross_filled_notional_usdt": gross_filled_notional,
            "modeled_execution_cost_usdt": modeled_execution_cost,
            "aggregate_cost_limit_usdt": aggregate_limit,
        },
        "drawdown": {
            "passed": drawdown_passed,
            "maximum_drawdown": maximum_drawdown,
            "threshold_exclusive": Decimal("0.10"),
        },
        "block_return": {
            "passed": blocks["passed"],
            "block_returns": blocks["block_returns"],
            "mean": blocks["mean"],
            "sample_sd": blocks["sample_sd"],
            "student_t_constant": _STUDENT_T_95_ONE_SIDED_DF2,
            "lcb": blocks["lcb"],
            "threshold_exclusive": Decimal("0"),
        },
    }
    passed = all(gate["passed"] for gate in gates.values())
    return {
        "status": (
            "SYSTEM_PAPER_GATE_PASS"
            if passed
            else "SYSTEM_PAPER_GATE_DID_NOT_PASS"
        ),
        "slot_count": len(slots),
        "gates": gates,
    }


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


def _replay_retained_prepared_state(
    *,
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    plan: Mapping[str, Any],
    start: Mapping[str, Any],
    contract: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Replay prepared SQLite rows without opening the slot inventory."""

    policy = SystemPaperSchedulePolicy.create(plan)
    try:
        projection = replay["projection"]
        state_slots = tuple(
            sorted(
                projection.values(),
                key=lambda item: _utc(item["scheduled_for"])[0],
            )
        )
        if not state_slots:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
            )
        state_first = state_slots[0]
        started, started_text = _utc(state_first["scheduled_for"])
        receipt_started, receipt_started_text = _utc(
            start["cohort_started_at"]
        )
        receipt_tail, receipt_tail_text = _utc(start["cohort_tail_end"])
        first = start["first_slot"]
        if (
            start["expected_slot_count"] != 540
            or receipt_started != started
            or receipt_started_text != started_text
            or receipt_tail != started + timedelta(days=90)
            or receipt_tail_text
            != utc_datetime(started + timedelta(days=90))
            or first["slot_id"] != state_first["slot_id"]
            or first["scheduled_for"] != state_first["scheduled_for"]
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
            )
        expected_slots = tuple(
            policy.slot_from_scheduled(started + timedelta(hours=4 * index))
            for index in range(540)
        )
        expected_by_id = {slot.slot_id: slot for slot in expected_slots}
        input_rows, result_rows = _copy_full_state_rows(
            state_files, plan=plan, replay=replay
        )
        inputs_by_slot = {row["slot_id"]: row for row in input_rows}
        results_by_slot = {row["slot_id"]: row for row in result_rows}
        input_events = {
            event["slot_id"]: event
            for event in replay["events"]
            if event["event_type"] == "INPUT_PREPARED"
        }
        result_events = {
            event["slot_id"]: event
            for event in replay["events"]
            if event["event_type"] == "RESULT_PREPARED"
        }
        if (
            len(inputs_by_slot) != len(input_rows)
            or len(results_by_slot) != len(result_rows)
            or len(input_events)
            != sum(
                event["event_type"] == "INPUT_PREPARED"
                for event in replay["events"]
            )
            or len(result_events)
            != sum(
                event["event_type"] == "RESULT_PREPARED"
                for event in replay["events"]
            )
            or set(inputs_by_slot) != set(input_events)
            or set(results_by_slot) != set(result_events)
            or not set(results_by_slot).issubset(inputs_by_slot)
            or not set(inputs_by_slot).issubset(expected_by_id)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
            )
        expected_output_root_hash = business_hash(
            {
                "purpose": "SYSTEM_PAPER_IMMUTABLE_OUTPUT_ROOT",
                "resolved_path": str(
                    Path(contract["root_paths"]["artifacts"]).resolve()
                ),
            }
        )
        ordered_inputs = []
        envelopes = {}
        for slot in expected_slots:
            row = inputs_by_slot.get(slot.slot_id)
            if row is None:
                continue
            body = row["input_bytes"]
            if not isinstance(body, bytes):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
                )
            try:
                envelope = _strict_prepared_input(body)
            except SystemPaperEvaluationError as error:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
                ) from error
            expected_hashes = {
                "input_sha256": hashlib.sha256(body).hexdigest(),
                "plan_hash": plan["plan_hash"],
                "market_bundle_hash": envelope["capture"][
                    "public_market_bundle"
                ]["bundle_hash"],
                "previous_snapshot_hash": envelope[
                    "previous_runtime_snapshot"
                ]["snapshot_hash"],
                "fill_scenario_hash": business_hash(
                    envelope["fill_scenario"]
                ),
                "output_root_hash": expected_output_root_hash,
            }
            event = input_events[slot.slot_id]
            if (
                row["source_event_id"] != event["event_id"]
                or any(
                    row[name] != value
                    for name, value in expected_hashes.items()
                )
                or envelope.get("slot_id") != row["slot_id"]
                or envelope.get("scheduled_for") != slot.scheduled_for
                or envelope.get("plan") != plan
                or envelope.get("schedule_policy_hash")
                != policy.schedule_policy_hash
                or envelope.get("output_root_hash")
                != expected_output_root_hash
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
                )
            envelopes[slot.slot_id] = envelope
            ordered_inputs.append(row)

        ordered_results = tuple(
            results_by_slot[slot.slot_id]
            for slot in expected_slots
            if slot.slot_id in results_by_slot
        )
        ordered_result_slots = tuple(
            expected_by_id[row["slot_id"]] for row in ordered_results
        )
        result_bodies = tuple(row["result_bytes"] for row in ordered_results)
        if (
            not result_bodies
            or any(not isinstance(body, bytes) for body in result_bodies)
            or ordered_result_slots
            != expected_slots[: len(ordered_result_slots)]
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
            )
        load_system_paper_slot_result_bytes(
            result_bodies[-1], parent_result_bodies=result_bodies[:-1]
        )
        parsed_results = tuple(
            json.loads(body.decode("utf-8")) for body in result_bodies
        )
        prefix = []
        for slot, row, result in zip(
            ordered_result_slots, ordered_results, parsed_results
        ):
            envelope = envelopes[slot.slot_id]
            body = row["result_bytes"]
            prefix.append(slot.slot_id)
            expected_hashes = {
                "result_sha256": hashlib.sha256(body).hexdigest(),
                "slot_hash": result["slot_hash"],
                "runtime_snapshot_hash": result["runtime_snapshot"][
                    "snapshot_hash"
                ],
                "parent_slot_hash": result["parent_slot_hash_or_null"]
                or _ZERO_HASH,
                "output_root_hash": expected_output_root_hash,
            }
            event = result_events[slot.slot_id]
            if (
                row["source_event_id"] != event["event_id"]
                or any(
                    row[name] != value
                    for name, value in expected_hashes.items()
                )
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
                or result["runtime_snapshot"]["processed_slot_ids"]
                != prefix
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
                )

        first_slot = expected_slots[0]
        first_input = inputs_by_slot.get(first_slot.slot_id)
        first_result = results_by_slot.get(first_slot.slot_id)
        first_value = parsed_results[0]
        first_success = next(
            (
                event
                for event in replay["events"]
                if event["event_type"] == "SUCCEEDED"
                and event["slot_id"] == first_slot.slot_id
            ),
            None,
        )
        expected_result_path = str(
            Path(contract["root_paths"]["artifacts"])
            / "system-paper-slots"
            / (first_slot.slot_id + ".json")
        )
        if (
            first_input is None
            or first_result is None
            or first_success is None
            or first["slot_id"] != first_slot.slot_id
            or first["scheduled_for"] != first_slot.scheduled_for
            or first["result_path"] != expected_result_path
            or first["artifact_evidence"]["path"] != expected_result_path
            or first["result_sha256"]
            != hashlib.sha256(first_result["result_bytes"]).hexdigest()
            or first["prepared_input_sha256"]
            != hashlib.sha256(first_input["input_bytes"]).hexdigest()
            or first["prepared_result_sha256"]
            != hashlib.sha256(first_result["result_bytes"]).hexdigest()
            or first["slot_hash"] != first_value["slot_hash"]
            or first["runtime_snapshot_hash"]
            != first_value["runtime_snapshot"]["snapshot_hash"]
            or first["event_chain_end_hash"] != first_success["event_hash"]
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
            )
        return {
            "input_rows": tuple(ordered_inputs),
            "result_rows": ordered_results,
        }
    except SystemPaperEvaluationError:
        raise
    except (KeyError, TypeError, ValueError, SystemPaperRuntimeError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
        ) from error


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


def _inventory_surface_state(
    slot_root: Path,
    *,
    retained_sources: _RetainedCohortSources,
    retained_attachment: _RetainedAuthoritySet,
) -> str:
    """Retain and classify the one authoritative post-tail inventory scan."""

    try:
        retained_sources.capture_directory(slot_root)
    except SystemPaperEvaluationError as original_error:
        if original_error.reason_code == "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED":
            raise
        try:
            retained_attachment.capture_absent(slot_root)
            return "MISSING"
        except SystemPaperEvaluationError:
            try:
                retained_attachment.capture_entry(slot_root)
            except SystemPaperEvaluationError:
                raise original_error
            return "UNSAFE"
    entry = retained_sources.entry
    snapshot = retained_sources.snapshot
    if entry is None or snapshot is None:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
        )
    if (
        entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
        or snapshot.entry_count > _MAX_INVENTORY_ENTRIES
        or snapshot.has_unsafe_entry
    ):
        return "UNSAFE"
    if snapshot.entry_count == 0:
        return "EMPTY"
    return "PRESENT"


def _inconclusive_inventory(
    slot_root: Path,
    *,
    retained_sources: _RetainedCohortSources,
    retained_attachment: _RetainedAuthoritySet,
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    plan: Mapping[str, Any],
    replay: Mapping[str, Any],
    inventory_state: str,
) -> Mapping[str, Any]:
    """Describe only the retained first inventory without recapturing it."""

    if inventory_state == "MISSING":
        retained_attachment.verify()
        return {"inventory_state": "MISSING", "slots": ()}
    if retained_sources.descriptor is None:
        entries = retained_attachment.files
        if not entries:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )
        root = entries[-1].entry
        if stat.S_ISLNK(root.st_mode):
            status_code = "UNSAFE_ROOT_SYMLINK"
        elif not stat.S_ISDIR(root.st_mode):
            status_code = "UNSAFE_ROOT_TYPE"
        elif root.st_uid != os.getuid():
            status_code = "UNSAFE_ROOT_OWNER"
        elif stat.S_IMODE(root.st_mode) != 0o700:
            status_code = "UNSAFE_ROOT_MODE"
        else:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )
        retained_attachment.verify()
        return {
            "inventory_state": "UNSAFE",
            "slots": (_unsafe_inventory_evidence(".", root, status_code),),
        }
    names = retained_sources.snapshot.bounded_names
    input_rows = ()
    result_rows = ()
    snapshot = retained_sources.snapshot
    if snapshot is None:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
        )
    if snapshot.entry_count > _MAX_INVENTORY_ENTRIES:
        retained_sources.verify()
        return {
            "inventory_state": "UNSAFE",
            "slots": (
                {
                    "artifact_name": ".",
                    "entry_status": "UNSAFE_ENTRY_COUNT",
                    "entry_count": snapshot.entry_count,
                    "entry_identity_hash": _inventory_snapshot_hash(
                        retained_sources.entry,
                        snapshot,
                    ),
                },
            ),
        }
    try:
        input_rows, result_rows = _copy_full_state_rows(
            state_files, plan=plan, replay=replay
        )
    except SystemPaperEvaluationError:
        # The final reason already records invalid/incomplete replay.  Preserve
        # the exact files even when the prepared-row metadata cannot be trusted.
        pass
    inputs = {
        row.get("slot_id"): row
        for row in input_rows
        if isinstance(row, Mapping)
    }
    results = {
        row.get("slot_id"): row
        for row in result_rows
        if isinstance(row, Mapping)
    }
    records = []
    unsafe = False
    if names is None:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
        )
    root_entry = retained_sources.entry
    if (
        root_entry.st_uid != os.getuid()
        or stat.S_IMODE(root_entry.st_mode) != 0o700
    ):
        status_code = (
            "UNSAFE_ROOT_OWNER"
            if root_entry.st_uid != os.getuid()
            else "UNSAFE_ROOT_MODE"
        )
        retained_sources.verify()
        return {
            "inventory_state": "UNSAFE",
            "slots": (
                _unsafe_inventory_evidence(".", root_entry, status_code),
            ),
        }
    for name in names:
        source, unsafe_evidence = retained_sources.capture_inventory_artifact(
            slot_root / name
        )
        if unsafe_evidence is not None:
            unsafe = True
            records.append(unsafe_evidence)
            continue
        slot_id = None
        scheduled_for = None
        slot_hash = None
        runtime_snapshot_hash = None
        try:
            value = _strict_prepared_input(source.body)
            if isinstance(value.get("slot_id"), str):
                slot_id = value["slot_id"]
            if isinstance(value.get("scheduled_for"), str):
                scheduled_for = value["scheduled_for"]
            if isinstance(value.get("slot_hash"), str):
                slot_hash = value["slot_hash"]
            snapshot = value.get("runtime_snapshot")
            if (
                isinstance(snapshot, Mapping)
                and isinstance(snapshot.get("snapshot_hash"), str)
            ):
                runtime_snapshot_hash = snapshot["snapshot_hash"]
        except SystemPaperEvaluationError:
            pass
        input_row = inputs.get(slot_id, {})
        result_row = results.get(slot_id, {})
        records.append(
            {
                "artifact_name": name,
                "slot_id": slot_id,
                "scheduled_for": scheduled_for,
                "artifact_sha256": source.content_sha256,
                "prepared_input_sha256": input_row.get("input_sha256"),
                "prepared_result_sha256": result_row.get("result_sha256"),
                "slot_hash": slot_hash,
                "runtime_snapshot_hash": runtime_snapshot_hash,
            }
        )
    retained_sources.verify()
    return {
        "inventory_state": (
            "UNSAFE" if unsafe else "EMPTY" if not names else "PRESENT"
        ),
        "slots": tuple(records),
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
    if (
        retained_sources.descriptor is None
        or retained_sources.snapshot is None
        or retained_sources.snapshot.bounded_names
        != tuple(sorted(expected_names))
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
        )
    retained_sources.verify()
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


def _inconclusive_readiness(
    *,
    observed_at: str,
    start_text: str,
    tail_text: str,
    start: Mapping[str, Any],
    successes: int,
    incidents: int,
    plan: Mapping[str, Any],
    install: Mapping[str, Any],
    contract: Mapping[str, Any],
    replay: Optional[Mapping[str, Any]],
    raw_state_group_hash: str,
    reason_code: str,
    inventory: Mapping[str, Any],
) -> Mapping[str, Any]:
    return {
        "status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        "observed_at": observed_at,
        "cohort_started_at": start_text,
        "tail_end": tail_text,
        "reason_code": reason_code,
        "expected_slot_count": start["expected_slot_count"],
        "verified_terminal_slot_count": successes,
        "incident_count": incidents,
        "source_binding": {
            "plan_hash": plan["plan_hash"],
            "install_receipt_hash": install["receipt_hash"],
            "contract_hash": contract["contract_hash"],
            "start_receipt_hash": start["receipt_hash"],
            **_state_binding(
                replay=replay,
                raw_state_group_hash=raw_state_group_hash,
            ),
        },
        "evidence_inventory": inventory,
    }


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
    _retained_authority=None,
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
    authority = _retained_authority or _RetainedEvaluationAuthority()
    owns_authority = _retained_authority is None
    retained = authority.files
    state_retained = authority.state
    cohort_retained = authority.cohort
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
            or paths["output_root"]
            != _expected_evaluation_output_root(contract)
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
        raw_state_hash = _raw_state_group_hash(state_files)
        start_at, start_text = _utc(start["cohort_started_at"])
        tail_at, tail_text = _utc(start["cohort_tail_end"])
        try:
            replay = _copy_event_metadata(
                state_files,
                plan=plan,
                temporary_parent=_PRIVATE_TMP,
            )
        except SystemPaperEvaluationError as error:
            retained.verify()
            state_retained.verify()
            if (
                observed < tail_at + _TAIL_SETTLE_DELAY
                or error.reason_code
                != "SYSTEM_PAPER_EVALUATION_STATE_REPLAY_INVALID"
            ):
                raise
            surface_state = _inventory_surface_state(
                paths["slot_root"],
                retained_sources=cohort_retained,
                retained_attachment=authority.inconclusive_attachment,
            )
            inventory = _inconclusive_inventory(
                paths["slot_root"],
                retained_sources=cohort_retained,
                retained_attachment=authority.inconclusive_attachment,
                state_files=state_files,
                plan=plan,
                replay={},
                inventory_state=surface_state,
            )
            retained.verify()
            state_retained.verify()
            if cohort_retained.descriptor is not None:
                cohort_retained.verify()
            return _inconclusive_readiness(
                observed_at=observed_at,
                start_text=start_text,
                tail_text=tail_text,
                start=start,
                successes=0,
                incidents=0,
                plan=plan,
                install=install,
                contract=contract,
                replay=None,
                raw_state_group_hash=raw_state_hash,
                reason_code=_stable_replay_reason(error),
                inventory=inventory,
            )
        projection = replay["projection"]
        incidents = sum(
            event["event_type"] in ("FAILED", "MISSED", "EXPIRED")
            for event in replay["events"]
        )
        policy = SystemPaperSchedulePolicy.create(plan)
        expected_slot_ids = {
            policy.slot_from_scheduled(
                start_at + timedelta(hours=4 * index)
            ).slot_id
            for index in range(start["expected_slot_count"])
        }
        successes = sum(
            projection.get(slot_id, {}).get("terminal_state") == "SUCCEEDED"
            for slot_id in expected_slot_ids
        )
        if observed >= tail_at + _TAIL_SETTLE_DELAY:
            prepared_replay_reason = None
            try:
                _replay_retained_prepared_state(
                    state_files=state_files,
                    plan=plan,
                    start=start,
                    contract=contract,
                    replay=replay,
                )
            except SystemPaperEvaluationError as error:
                retained.verify()
                state_retained.verify()
                if (
                    error.reason_code
                    != "SYSTEM_PAPER_EVALUATION_PREPARED_REPLAY_INVALID"
                ):
                    raise
                prepared_replay_reason = error.reason_code
            else:
                retained.verify()
                state_retained.verify()
            surface_state = _inventory_surface_state(
                paths["slot_root"],
                retained_sources=cohort_retained,
                retained_attachment=authority.inconclusive_attachment,
            )
            if prepared_replay_reason is not None:
                inventory = _inconclusive_inventory(
                    paths["slot_root"],
                    retained_sources=cohort_retained,
                    retained_attachment=authority.inconclusive_attachment,
                    state_files=state_files,
                    plan=plan,
                    replay=replay,
                    inventory_state=surface_state,
                )
                retained.verify()
                state_retained.verify()
                if cohort_retained.descriptor is not None:
                    cohort_retained.verify()
                return _inconclusive_readiness(
                    observed_at=observed_at,
                    start_text=start_text,
                    tail_text=tail_text,
                    start=start,
                    successes=successes,
                    incidents=incidents,
                    plan=plan,
                    install=install,
                    contract=contract,
                    replay=None,
                    raw_state_group_hash=raw_state_hash,
                    reason_code=prepared_replay_reason,
                    inventory=inventory,
                )
            if surface_state != "PRESENT":
                inventory = _inconclusive_inventory(
                    paths["slot_root"],
                    retained_sources=cohort_retained,
                    retained_attachment=authority.inconclusive_attachment,
                    state_files=state_files,
                    plan=plan,
                    replay=replay,
                    inventory_state=surface_state,
                )
                retained.verify()
                state_retained.verify()
                if cohort_retained.descriptor is not None:
                    cohort_retained.verify()
                return _inconclusive_readiness(
                    observed_at=observed_at,
                    start_text=start_text,
                    tail_text=tail_text,
                    start=start,
                    successes=successes,
                    incidents=incidents,
                    plan=plan,
                    install=install,
                    contract=contract,
                    replay=replay,
                    raw_state_group_hash=raw_state_hash,
                    reason_code="SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
                    inventory=inventory,
                )
            try:
                replayed_start = load_system_paper_start_receipt(
                    receipt_path=paths["start"],
                    contract_path=paths["contract"],
                    plist_path=plist_path,
                    preflight_receipt_path=preflight_path,
                    install_receipt_path=paths["install"],
                    _machine_probe=_machine_probe,
                    _filesystem_probe=_filesystem_probe,
                )
            except SystemPaperStartReceiptError as error:
                retained.verify()
                state_retained.verify()
                if cohort_retained.descriptor is not None:
                    cohort_retained.verify()
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
                ) from error
            if replayed_start != start:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
                )
            try:
                cohort = _replay_system_paper_cohort(
                    plan=plan,
                    start=start,
                    replay=replay,
                    slot_root=paths["slot_root"],
                    state_files=state_files,
                    retained_sources=cohort_retained,
                )
            except SystemPaperEvaluationError as error:
                if error.reason_code not in (
                    "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
                    "SYSTEM_PAPER_EVALUATION_COHORT_REPLAY_INVALID",
                ):
                    raise
                retained.verify()
                state_retained.verify()
                return _inconclusive_readiness(
                    observed_at=observed_at,
                    start_text=start_text,
                    tail_text=tail_text,
                    start=start,
                    successes=successes,
                    incidents=incidents,
                    plan=plan,
                    install=install,
                    contract=contract,
                    replay=replay,
                    raw_state_group_hash=raw_state_hash,
                    reason_code=error.reason_code,
                    inventory=_inconclusive_inventory(
                        paths["slot_root"],
                        retained_sources=cohort_retained,
                        retained_attachment=authority.inconclusive_attachment,
                        state_files=state_files,
                        plan=plan,
                        replay=replay,
                        inventory_state=surface_state,
                    ),
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
                raw_state_group_hash=raw_state_hash,
            )
            cohort_retained.verify()
            retained.verify()
            state_retained.verify()
            return complete
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
        if owns_authority:
            authority.close()


@lru_cache(maxsize=1)
def _evaluation_validator() -> Draft202012Validator:
    try:
        schema = json.loads(
            resources.files("crypto_quant")
            .joinpath("schemas", _EVALUATION_SCHEMA)
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except Exception as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SCHEMA_INVALID"
        ) from error


def _result_identity(result: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "contract_hash": result["sources"]["contract_hash"],
        "start_receipt_hash": result["sources"]["start_receipt_hash"],
        "state_binding_hash": result["sources"]["state_binding_hash"],
        "slot_inventory_hash": result["evidence_inventory"]["inventory_hash"],
    }


def _evaluation_hash(result: Mapping[str, Any]) -> str:
    return artifact_self_hash(result, "result_hash")


def _terminal_key(result: Mapping[str, Any]) -> str:
    sources = result["sources"]
    return business_hash(
        {
            "purpose": "SYSTEM_PAPER_EVALUATION_TERMINAL_V1",
            "contract_hash": sources["contract_hash"],
            "start_receipt_hash": sources["start_receipt_hash"],
        }
    )


def _result_path(output_root: Path, result_id: str) -> Path:
    root = _absolute_paths({"output_root": output_root})["output_root"]
    if root.is_symlink():
        raise SystemPaperEvaluationError("SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID")
    return root / (result_id + ".json")


def _secure_output_root(root: Path) -> None:
    parent = root.parent
    try:
        parent_entry = os.stat(parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(parent_entry.st_mode)
            or parent_entry.st_uid != os.getuid()
            or stat.S_IMODE(parent_entry.st_mode) != 0o700
        ):
            raise OSError("unsafe parent")
        try:
            os.mkdir(root, 0o700)
        except FileExistsError:
            pass
        entry = os.stat(root, follow_symlinks=False)
        if (
            not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != os.getuid()
            or stat.S_IMODE(entry.st_mode) != 0o700
            or root.is_symlink()
        ):
            raise OSError("unsafe output root")
    except OSError as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_OUTPUT_INVALID"
        ) from error


def _strict_existing_finals(
    root: _RetainedOutputRoot,
) -> Tuple[Tuple[Mapping[str, Any], bytes], ...]:
    """Parse every final under the locked root; corruption blocks progress."""

    try:
        with os.scandir(root.descriptor) as entries:
            names = tuple(sorted(candidate.name for candidate in entries))
        result_names = names
        prefix = "system_paper_evaluation_"
        if (
            len(result_names) > _MAX_INVENTORY_ENTRIES
            or any(
                not name.startswith(prefix)
                or not name.endswith(".json")
                or len(name) != len(prefix) + 64 + len(".json")
                or any(
                    character not in "0123456789abcdef"
                    for character in name[len(prefix) : -len(".json")]
                )
                for name in result_names
            )
        ):
            raise ValueError("invalid final inventory")
        finals = []
        for name in result_names:
            source = root._relative_file(
                name, maximum_bytes=_MAX_EVALUATION_BYTES
            )
            artifact = _strict_prepared_input(source.body)
            if (
                canonical_json(artifact).encode("utf-8") != source.body
                or tuple(_evaluation_validator().iter_errors(artifact))
                or name != artifact.get("result_id", "") + ".json"
                or artifact.get("result_hash") != _evaluation_hash(artifact)
            ):
                raise ValueError("invalid final")
            finals.append((artifact, source.body))
        root.verify()
        return tuple(finals)
    except Exception as error:
        if (
            isinstance(error, SystemPaperEvaluationError)
            and error.reason_code
            == "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
        ):
            raise
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_RESULT_CONFLICT"
        ) from error


def _publish_terminal_final(
    *,
    output_root: Path,
    artifact: Mapping[str, Any],
    authority: _RetainedEvaluationAuthority,
) -> Mapping[str, Any]:
    """Serialize first-final publication for one contract/start series."""

    _secure_output_root(output_root)
    root = _RetainedOutputRoot.open(output_root)
    try:
        root.acquire_lock()
        candidate_body = canonical_json(artifact).encode("utf-8")
        key = _terminal_key(artifact)
        existing = tuple(
            (value, body)
            for value, body in _strict_existing_finals(root)
            if _terminal_key(value) == key
        )
        if len(existing) > 1:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_TERMINAL_CONFLICT"
            )
        if existing:
            if existing[0][1] != candidate_body:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_TERMINAL_CONFLICT"
                )
            authority.verify()
            root.verify()
            return artifact

        def verify_before_link() -> None:
            authority.verify()
            root.verify()

        authority.verify()
        root.verify()
        publish_owner_exact(
            _result_path(output_root, artifact["result_id"]),
            candidate_body,
            _before_link=verify_before_link,
        )
        authority.verify()
        published = tuple(
            (value, body)
            for value, body in _strict_existing_finals(root)
            if _terminal_key(value) == key
        )
        if len(published) != 1 or published[0][1] != candidate_body:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_TERMINAL_CONFLICT"
            )
        authority.verify()
        root.verify()
        return artifact
    finally:
        root.close()


def _fallback_binding(paths: Mapping[str, Path]) -> Mapping[str, Any]:
    del paths
    raise SystemPaperEvaluationError("SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID")


def _canonical_result(value: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        return _strict_prepared_input(canonical_json(value).encode("utf-8"))
    except SystemPaperEvaluationError as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_RESULT_INVALID"
        ) from error


def _final_artifact(
    *, observation: Mapping[str, Any], paths: Mapping[str, Path]
) -> Mapping[str, Any]:
    binding = observation.get("source_binding")
    records = observation.get("evidence_inventory")
    if not isinstance(binding, Mapping):
        binding = _fallback_binding(paths)
    if isinstance(records, Mapping):
        inventory_state = records.get("inventory_state")
        records = records.get("slots")
    else:
        inventory_state = "PRESENT"
    if not isinstance(records, tuple) or inventory_state not in (
        "PRESENT",
        "EMPTY",
        "MISSING",
        "UNSAFE",
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_SCHEMA_INVALID"
        )
    inventory = list(records)
    inventory_identity = {
        "inventory_state": inventory_state,
        "slots": inventory,
    }
    result = {
        "$schema": "./system-paper-evaluation-v1.schema.json",
        "schema_version": "1.0.0",
        "result_id": "system_paper_evaluation_" + _ZERO_HASH,
        "result_hash": _ZERO_HASH,
        # Call time is deliberately excluded: this is the earliest final gate.
        "evaluated_at": utc_datetime(
            _utc(observation["tail_end"])[0] + _TAIL_SETTLE_DELAY
        ),
        "status": observation["status"],
        "sources": {
            "plan_path": str(paths["plan"]),
            "start_receipt_path": str(paths["start"]),
            "install_receipt_path": str(paths["install"]),
            "contract_path": str(paths["contract"]),
            "slot_root": str(paths["slot_root"]),
            "runtime_root": str(paths["runtime_root"]),
            "output_root": str(paths["output_root"]),
            "plan_hash": binding["plan_hash"],
            "install_receipt_hash": binding["install_receipt_hash"],
            "contract_hash": binding["contract_hash"],
            "start_receipt_hash": binding["start_receipt_hash"],
            "state_binding_kind": binding["state_binding_kind"],
            "state_binding_hash": binding["state_binding_hash"],
            "event_chain_end_hash_or_null": binding[
                "event_chain_end_hash_or_null"
            ],
            "raw_state_group_hash": binding["raw_state_group_hash"],
        },
        "evidence_inventory": {
            "expected_slot_count": observation.get("expected_slot_count", 540),
            "verified_terminal_slot_count": observation[
                "verified_terminal_slot_count"
            ] if "verified_terminal_slot_count" in observation else observation["slot_count"],
            "inventory_state": inventory_state,
            "inventory_hash": business_hash(inventory_identity),
            "slots": inventory,
        },
        "gates": observation.get("gates", {}),
        "security_counts": observation.get(
            "security_counts",
            {
                "credential_reads": 0,
                "account_requests": 0,
                "real_broker_calls": 0,
                "real_order_writes": 0,
            },
        ),
        "reason_code_or_null": observation.get("reason_code"),
    }
    result["result_id"] = stable_id("system_paper_evaluation", _result_identity(result))
    result["result_hash"] = _evaluation_hash(result)
    result = _canonical_result(result)
    if tuple(_evaluation_validator().iter_errors(result)):
        raise SystemPaperEvaluationError("SYSTEM_PAPER_EVALUATION_SCHEMA_INVALID")
    return result


def _recompute_system_paper_evaluation(
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
    _retained_authority=None,
) -> Mapping[str, Any]:
    """Purely recompute one result while retaining every source authority."""
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
    authority = _retained_authority or _RetainedEvaluationAuthority()
    owns_authority = _retained_authority is None
    try:
        observation = observe_system_paper_evaluation_readiness(
            plan_path=paths["plan"], start_receipt_path=paths["start"],
            install_receipt_path=paths["install"], contract_path=paths["contract"],
            slot_root=paths["slot_root"], runtime_root=paths["runtime_root"],
            output_root=paths["output_root"], _clock=_clock,
            _machine_probe=_machine_probe, _filesystem_probe=_filesystem_probe,
            _retained_authority=authority,
        )
        if observation["status"] == "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL":
            return observation
        artifact = _final_artifact(observation=observation, paths=paths)
        authority.verify()
        return artifact
    finally:
        if owns_authority:
            authority.close()


def evaluate_system_paper(
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
    """Publish one stable, immutable final artifact; pending observation writes zero."""
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
    authority = _RetainedEvaluationAuthority()
    try:
        artifact = _recompute_system_paper_evaluation(
            plan_path=paths["plan"],
            start_receipt_path=paths["start"],
            install_receipt_path=paths["install"],
            contract_path=paths["contract"],
            slot_root=paths["slot_root"],
            runtime_root=paths["runtime_root"],
            output_root=paths["output_root"],
            _clock=_clock,
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
            _retained_authority=authority,
        )
        if artifact["status"] == "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL":
            return artifact
        try:
            return _publish_terminal_final(
                output_root=paths["output_root"],
                artifact=artifact,
                authority=authority,
            )
        except SystemPaperEvaluationError:
            raise
        except Exception as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_RESULT_CONFLICT"
            ) from error
    finally:
        authority.close()


def load_system_paper_evaluation(
    *, evaluation_path: Path, _machine_probe=None, _filesystem_probe=None
) -> Mapping[str, Any]:
    """Load an immutable artifact and replay every original authority input."""
    retained_root = None
    try:
        path = _absolute_paths({"evaluation": evaluation_path})["evaluation"]
        retained_root = _RetainedOutputRoot.open(path.parent)
        source = retained_root._relative_file(
            path.name, maximum_bytes=_MAX_EVALUATION_BYTES
        )
        artifact = _strict_prepared_input(source.body)
        if (
            tuple(_evaluation_validator().iter_errors(artifact))
            or path.name != artifact.get("result_id", "") + ".json"
            or artifact.get("result_hash") != _evaluation_hash(artifact)
        ):
            raise ValueError("invalid artifact")
        sources = artifact["sources"]
        declared_root = Path(sources["output_root"])
        if path != declared_root / (artifact["result_id"] + ".json"):
            raise ValueError("detached artifact")
        retained_root.verify()
        replayed = _recompute_system_paper_evaluation(
            plan_path=Path(sources["plan_path"]),
            start_receipt_path=Path(sources["start_receipt_path"]),
            install_receipt_path=Path(sources["install_receipt_path"]),
            contract_path=Path(sources["contract_path"]),
            slot_root=Path(sources["slot_root"]),
            runtime_root=Path(sources["runtime_root"]),
            output_root=Path(sources["output_root"]),
            _clock=lambda: artifact["evaluated_at"],
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        retained_root.verify()
        if replayed != artifact:
            raise ValueError("replay differs")
        return artifact
    except Exception as error:
        if isinstance(error, SystemPaperEvaluationError) and error.reason_code == "SYSTEM_PAPER_EVALUATION_RESULT_INVALID":
            raise
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_RESULT_INVALID"
        ) from error
    finally:
        if retained_root is not None:
            retained_root.close()
