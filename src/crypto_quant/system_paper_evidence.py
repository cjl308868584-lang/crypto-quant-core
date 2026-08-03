"""Owner-only, immutable publication for System Paper trust artifacts."""

import errno
import os
import secrets
import stat
from pathlib import Path
from typing import Callable, Optional


class SystemPaperEvidenceError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _read_all(descriptor: int, expected_size: int) -> bytes:
    chunks = []
    remaining = expected_size + 1
    while remaining:
        chunk = os.read(descriptor, min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _open_parent(path: Path):
    parent = path.parent
    if not path.is_absolute() or path.name in ("", ".", "..") or "/" in path.name:
        raise SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_PARENT_INVALID")
    try:
        resolved_parent = parent.resolve(strict=True)
    except OSError as error:
        raise SystemPaperEvidenceError(
            "SYSTEM_PAPER_EVIDENCE_PARENT_INVALID"
        ) from error
    if resolved_parent != parent:
        raise SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_PARENT_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(str(parent), flags)
        entry = os.fstat(descriptor)
    except OSError as error:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise SystemPaperEvidenceError(
            "SYSTEM_PAPER_EVIDENCE_PARENT_INVALID"
        ) from error
    if (
        not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_PARENT_INVALID")
    return descriptor, entry


def _entry_identity(entry: os.stat_result):
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_uid,
        entry.st_gid,
        entry.st_nlink,
        entry.st_size,
        entry.st_mtime_ns,
        entry.st_ctime_ns,
    )


def _same_parent(path: Path, retained: os.stat_result) -> bool:
    try:
        current = os.stat(str(path.parent), follow_symlinks=False)
    except OSError:
        return False
    return (
        current.st_dev,
        current.st_ino,
        current.st_mode,
        current.st_uid,
    ) == (
        retained.st_dev,
        retained.st_ino,
        retained.st_mode,
        retained.st_uid,
    )


def _existing_exact(parent_fd: int, name: str, data: bytes) -> bool:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise SystemPaperEvidenceError(
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
        ) from error
    error = None
    try:
        before = os.fstat(descriptor)
        body = _read_all(descriptor, len(data))
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as caught:
        error = caught
    try:
        os.close(descriptor)
    except OSError as caught:
        error = error or caught
    if error is not None:
        raise SystemPaperEvidenceError(
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
        ) from error
    if (
        _entry_identity(before) != _entry_identity(after)
        or _entry_identity(after) != _entry_identity(attached)
        or not stat.S_ISREG(after.st_mode)
        or after.st_uid != os.getuid()
        or stat.S_IMODE(after.st_mode) != 0o600
        or after.st_nlink != 1
        or after.st_size != len(data)
        or body != data
    ):
        raise SystemPaperEvidenceError(
            "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
        )
    return True


def publish_owner_exact(
    path: Path,
    data: bytes,
    *,
    _before_link: Optional[Callable[[], None]] = None,
) -> None:
    """Publish exact bytes once without replacing or chmodding an existing target."""

    target = Path(path)
    if not isinstance(data, bytes) or not data:
        raise SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_BYTES_INVALID")
    parent_fd, parent_entry = _open_parent(target)
    temporary_name = ".system-paper-evidence-" + secrets.token_hex(16) + ".tmp"
    temporary_created = False
    temporary_unlink_attempted = False
    succeeded = False
    failure = None
    try:
        if _existing_exact(parent_fd, target.name, data):
            if not _same_parent(target, parent_entry):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED"
                )
            succeeded = True
        else:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            try:
                descriptor = os.open(
                    temporary_name,
                    flags,
                    0o600,
                    dir_fd=parent_fd,
                )
            except OSError as error:
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
                ) from error
            temporary_created = True
            try:
                os.fchmod(descriptor, 0o600)
                view = memoryview(data)
                while view:
                    written = os.write(descriptor, view)
                    if written <= 0:
                        raise OSError(errno.EIO, "short write")
                    view = view[written:]
                os.fsync(descriptor)
                os.fstat(descriptor)
            except OSError as error:
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
                ) from error
            finally:
                try:
                    os.close(descriptor)
                except OSError as error:
                    raise SystemPaperEvidenceError(
                        "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
                    ) from error

            if _before_link is not None:
                _before_link()
            if not _same_parent(target, parent_entry):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED"
                )
            try:
                os.link(
                    temporary_name,
                    target.name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                if not _existing_exact(parent_fd, target.name, data):
                    raise SystemPaperEvidenceError(
                        "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
                    )
            except OSError as error:
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
                ) from error

            temporary_unlink_attempted = True
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError as error:
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_CLEANUP_FAILED"
                ) from error
            temporary_created = False
            os.fsync(parent_fd)
            if not _same_parent(target, parent_entry):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED"
                )
            if not _existing_exact(parent_fd, target.name, data):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
                )
            succeeded = True
    except SystemPaperEvidenceError as error:
        failure = error
    except OSError as error:
        failure = SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_WRITE_FAILED")
        failure.__cause__ = error
    finally:
        cleanup_failed = False
        cleanup_changed = False
        # Never unlink the public target after publication.  Standard unlinkat has
        # no inode precondition, so rollback could delete a concurrent replacement.
        # A failed private-temp unlink is likewise not retried after its pathname
        # attachment becomes uncertain; the owner-only directory preserves it for
        # failure forensics.
        if not succeeded and temporary_created and not temporary_unlink_attempted:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
                cleanup_changed = True
            except FileNotFoundError:
                pass
            except OSError:
                cleanup_failed = True
        if cleanup_changed:
            try:
                os.fsync(parent_fd)
            except OSError:
                cleanup_failed = True
        try:
            os.close(parent_fd)
        except OSError:
            cleanup_failed = True
        if cleanup_failed:
            cleanup_error = SystemPaperEvidenceError(
                "SYSTEM_PAPER_EVIDENCE_CLEANUP_FAILED"
            )
            if failure is not None:
                cleanup_error.__cause__ = failure
            failure = cleanup_error
    if failure is not None:
        raise failure
