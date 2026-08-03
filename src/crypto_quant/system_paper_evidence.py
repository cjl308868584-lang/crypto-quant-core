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
    if (
        not path.is_absolute()
        or parent.resolve(strict=True) != parent
        or path.name in ("", ".", "..")
        or "/" in path.name
    ):
        raise SystemPaperEvidenceError("SYSTEM_PAPER_EVIDENCE_PARENT_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(parent), flags)
        entry = os.fstat(descriptor)
    except OSError as error:
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
    try:
        entry = os.fstat(descriptor)
        body = _read_all(descriptor, len(data))
    finally:
        os.close(descriptor)
    if (
        not stat.S_ISREG(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o600
        or entry.st_nlink != 1
        or entry.st_size != len(data)
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
    final_created = False
    try:
        if _existing_exact(parent_fd, target.name, data):
            if not _same_parent(target, parent_entry):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED"
                )
            return
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
            temporary_entry = os.fstat(descriptor)
        except OSError as error:
            raise SystemPaperEvidenceError(
                "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
            ) from error
        finally:
            os.close(descriptor)

        if _before_link is not None:
            _before_link()
        try:
            os.link(
                temporary_name,
                target.name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            final_created = True
        except FileExistsError:
            if not _existing_exact(parent_fd, target.name, data):
                raise SystemPaperEvidenceError(
                    "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
                )
        except OSError as error:
            raise SystemPaperEvidenceError(
                "SYSTEM_PAPER_EVIDENCE_WRITE_FAILED"
            ) from error

        os.unlink(temporary_name, dir_fd=parent_fd)
        temporary_created = False
        os.fsync(parent_fd)
        if not _same_parent(target, parent_entry):
            if final_created:
                try:
                    final_descriptor = os.open(
                        target.name,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=parent_fd,
                    )
                    try:
                        final_entry = os.fstat(final_descriptor)
                    finally:
                        os.close(final_descriptor)
                    if (final_entry.st_dev, final_entry.st_ino) == (
                        temporary_entry.st_dev,
                        temporary_entry.st_ino,
                    ):
                        os.unlink(target.name, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                except OSError:
                    pass
            raise SystemPaperEvidenceError(
                "SYSTEM_PAPER_EVIDENCE_PARENT_CHANGED"
            )
        if not _existing_exact(parent_fd, target.name, data):
            raise SystemPaperEvidenceError(
                "SYSTEM_PAPER_EVIDENCE_PUBLISH_CONFLICT"
            )
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)
