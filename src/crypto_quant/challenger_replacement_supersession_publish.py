"""Crash-safe publication for four fixed v0.64 governance artifacts only."""

import ctypes
import errno
import hashlib
import os
import platform
import re
import secrets
import stat
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


_MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_STAGING_RE = re.compile(
    r"\A\.v064-supersession-"
    r"(plan|machine-evidence|owner-attestation|supersession-record)-"
    r"[0-9a-f]{64}-[0-9a-f]{32}\.staging\Z",
    re.ASCII,
)
_STAGING_PREFIX = ".v064-supersession-"
_STAGING_SUFFIX = ".staging"
_MAX_SEALED_STAGING = 64
_FIXED_FINAL_NAMES = {
    "challenger-replacement-plan-v0.64.0.json",
    "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
    "challenger-replacement-owner-attestation-v0.64.0.json",
    "challenger-replacement-plan-supersession-v0.64.0.json",
}


class SupersessionPublishError(RuntimeError):
    """A fixed supersession artifact could not be published safely."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _artifact_parent() -> Path:
    module_path = Path(__file__)
    if not module_path.is_absolute():
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        )
    _validate_no_symlink_ancestors(module_path)
    return (
        module_path.parents[2]
        / "artifacts"
        / "challenger-replacement"
    )


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or value == 0:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PLATFORM_UNSUPPORTED"
        )
    return value


def _validate_no_symlink_ancestors(path: Path) -> None:
    absolute = Path(path)
    if not absolute.is_absolute():
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        )
    current = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            current = current / part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
                )
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        ) from error


def _trusted_parent_stat(value: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(value.st_mode)
        and value.st_uid == os.geteuid() == 501
        and stat.S_IMODE(value.st_mode) == 0o755
    )


def _open_parent() -> Tuple[int, os.stat_result]:
    parent = _artifact_parent()
    _validate_no_symlink_ancestors(parent)
    try:
        before = parent.lstat()
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        ) from error
    if not _trusted_parent_stat(before):
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        )
    flags = (
        os.O_RDONLY
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
    )
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(parent, flags)
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not _trusted_parent_stat(opened)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
            )
        return descriptor, opened
    except BaseException as primary:
        try:
            _close(descriptor)
        except SupersessionPublishError as close_error:
            try:
                setattr(primary, "close_error", close_error.reason_code)
            except BaseException:
                pass
        raise


def _validate_parent(descriptor: int, expected: os.stat_result) -> None:
    try:
        current = os.fstat(descriptor)
        _validate_no_symlink_ancestors(_artifact_parent())
        attached = _artifact_parent().lstat()
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        ) from error
    if (
        not _trusted_parent_stat(current)
        or (current.st_dev, current.st_ino)
        != (expected.st_dev, expected.st_ino)
        or not _trusted_parent_stat(attached)
        or (attached.st_dev, attached.st_ino)
        != (expected.st_dev, expected.st_ino)
    ):
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_PARENT_INVALID"
        )


def _close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_CLOSE_FAILED"
        ) from error


def _fsync_retry(descriptor: int) -> None:
    while True:
        try:
            os.fsync(descriptor)
            return
        except InterruptedError:
            continue
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_FSYNC_FAILED"
            ) from error


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        try:
            written = os.write(descriptor, data[offset:])
        except InterruptedError:
            continue
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_WRITE_FAILED"
            ) from error
        if written <= 0:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_WRITE_FAILED"
            )
        offset += written


def _read_exact_descriptor(descriptor: int, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        try:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
        except InterruptedError:
            continue
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_READ_FAILED"
            ) from error
        if not chunk:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_READ_FAILED"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _seek_start(descriptor: int) -> None:
    while True:
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            return
        except InterruptedError:
            continue
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_READ_FAILED"
            ) from error


def _read_one_or_eof(descriptor: int) -> bytes:
    while True:
        try:
            return os.read(descriptor, 1)
        except InterruptedError:
            continue
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_READ_FAILED"
            ) from error


def _emit_staging_basename(name: str) -> None:
    try:
        print("staging_basename=" + name, file=sys.stderr, flush=True)
    except (OSError, ValueError) as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_TRANSCRIPT_FAILED"
        ) from error


def _trusted_file_stat(value: os.stat_result, *, size: int) -> bool:
    return (
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid() == 501
        and stat.S_IMODE(value.st_mode) == 0o644
        and value.st_nlink == 1
        and value.st_size == size
        and 0 < size <= _MAX_ARTIFACT_BYTES
    )


def _trusted_empty_staging_stat(value: os.stat_result) -> bool:
    return (
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid() == 501
        and stat.S_IMODE(value.st_mode) == 0o644
        and value.st_nlink == 1
        and value.st_size == 0
    )


def _read_final(parent_fd: int, name: str) -> Tuple[bytes, os.stat_result]:
    flags = (
        os.O_RDONLY
        | _required_flag("O_NOFOLLOW")
        | _required_flag("O_NONBLOCK")
    )
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_UNTRUSTED"
        ) from error
    primary = None
    try:
        opened = os.fstat(descriptor)
        if not _trusted_file_stat(opened, size=opened.st_size):
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_UNTRUSTED"
            )
        body = _read_exact_descriptor(descriptor, opened.st_size)
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != identity
            or (attached.st_dev, attached.st_ino, attached.st_size, attached.st_mtime_ns, attached.st_ctime_ns) != identity
            or not _trusted_file_stat(after, size=opened.st_size)
            or not _trusted_file_stat(attached, size=opened.st_size)
        ):
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_UNTRUSTED"
            )
        return body, opened
    except OSError as error:
        mapped = SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_UNTRUSTED"
        )
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            _close(descriptor)
        except SupersessionPublishError as close_error:
            if primary is None:
                raise
            try:
                setattr(primary, "close_error", close_error.reason_code)
            except BaseException:
                pass


def _inventory_staging(parent_fd: int) -> List[Dict[str, Any]]:
    try:
        names = os.listdir(parent_fd)
    except OSError as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_INVENTORY_INVALID"
        ) from error
    sealed = []
    for name in sorted(names):
        if not (name.startswith(_STAGING_PREFIX) and name.endswith(_STAGING_SUFFIX)):
            continue
        if _STAGING_RE.fullmatch(name) is None:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_INVENTORY_INVALID"
            )
        try:
            value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_INVENTORY_INVALID"
            ) from error
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_uid != os.geteuid() == 501
            or stat.S_IMODE(value.st_mode) != 0o644
            or value.st_nlink != 1
            or value.st_size < 0
            or value.st_size > _MAX_ARTIFACT_BYTES
        ):
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_INVENTORY_INVALID"
            )
        sealed.append(
            {
                "classification": "SEALED_UNTRUSTED_PROTOCOL_NAMESPACE_ENTRY",
                "basename": name,
                "size": value.st_size,
                "device": value.st_dev,
                "inode": value.st_ino,
                "nlink": value.st_nlink,
                "mode_octal": format(stat.S_IMODE(value.st_mode), "04o"),
                "mtime_ns": value.st_mtime_ns,
                "ctime_ns": value.st_ctime_ns,
            }
        )
    if len(sealed) > _MAX_SEALED_STAGING:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_INVENTORY_INVALID"
        )
    return sealed


def _atomic_no_replace(
    parent_fd: int, staging_name: str, final_name: str
) -> None:
    system = platform.system()
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if system == "Darwin":
            function = getattr(libc, "renameatx_np")
            flag = 0x00000004
        elif system == "Linux":
            function = getattr(libc, "renameat2")
            flag = 1
        else:
            raise AttributeError(system)
    except (AttributeError, OSError) as error:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_UNSUPPORTED"
        ) from error
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_fd,
        staging_name.encode("ascii"),
        parent_fd,
        final_name.encode("ascii"),
        flag,
    )
    if result == 0:
        return
    code = ctypes.get_errno()
    if code == errno.EEXIST:
        raise FileExistsError(code, os.strerror(code), final_name)
    if code in {
        errno.ENOSYS,
        getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
        getattr(errno, "ENOTSUP", errno.ENOSYS),
    }:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_UNSUPPORTED"
        )
    raise SupersessionPublishError(
        "CHALLENGER_REPLACEMENT_SUPERSESSION_ATOMIC_NOREPLACE_FAILED"
    )


def _publish_fixed(kind: str, final_name: str, data: bytes) -> Dict[str, Any]:
    if (
        kind not in {"plan", "machine-evidence", "owner-attestation", "supersession-record"}
        or not isinstance(data, bytes)
        or not data
        or len(data) > _MAX_ARTIFACT_BYTES
    ):
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_ARTIFACT_INVALID"
        )
    parent_fd, parent_identity = _open_parent()
    primary = None
    try:
        _inventory_staging(parent_fd)
        try:
            existing, _ = _read_final(parent_fd, final_name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != data:
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_CONFLICT"
                )
            _fsync_retry(parent_fd)
            _validate_parent(parent_fd, parent_identity)
            replay_body, replay_stat = _read_final(parent_fd, final_name)
            if replay_body != data:
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_CONFLICT"
                )
            remaining = _inventory_staging(parent_fd)
            if remaining:
                raise SupersessionPublishError(
                    "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED"
                )
            return {
                "status": "ALREADY_PUBLISHED",
                "final_name": final_name,
                "file_sha256": hashlib.sha256(existing).hexdigest(),
                "device": replay_stat.st_dev,
                "inode": replay_stat.st_ino,
                "staging_basename": None,
            }

        digest = hashlib.sha256(data).hexdigest()
        staging_name = (
            f".v064-supersession-{kind}-{digest}-{secrets.token_hex(16)}.staging"
        )
        _emit_staging_basename(staging_name)
        flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_RDWR
            | _required_flag("O_NOFOLLOW")
        )
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            staging_fd = os.open(
                staging_name, flags, 0o644, dir_fd=parent_fd
            )
        except OSError as error:
            raise SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_CREATE_FAILED"
            ) from error
        staging_primary = None
        try:
            created = os.fstat(staging_fd)
            if not _trusted_empty_staging_stat(created):
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_UNTRUSTED"
                )
            _write_all(staging_fd, data)
            _seek_start(staging_fd)
            if _read_exact_descriptor(staging_fd, len(data)) != data:
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_BYTES_MISMATCH"
                )
            if _read_one_or_eof(staging_fd):
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_BYTES_MISMATCH"
                )
            complete = os.fstat(staging_fd)
            attached = os.stat(
                staging_name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                not _trusted_file_stat(complete, size=len(data))
                or not _trusted_file_stat(attached, size=len(data))
                or (complete.st_dev, complete.st_ino)
                != (created.st_dev, created.st_ino)
                or (attached.st_dev, attached.st_ino)
                != (created.st_dev, created.st_ino)
            ):
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_UNTRUSTED"
                )
            _fsync_retry(staging_fd)
            durable = os.fstat(staging_fd)
            durable_attached = os.stat(
                staging_name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                not _trusted_file_stat(durable, size=len(data))
                or not _trusted_file_stat(durable_attached, size=len(data))
                or (durable.st_dev, durable.st_ino)
                != (created.st_dev, created.st_ino)
                or (durable_attached.st_dev, durable_attached.st_ino)
                != (created.st_dev, created.st_ino)
            ):
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_UNTRUSTED"
                )
            try:
                _atomic_no_replace(parent_fd, staging_name, final_name)
            except FileExistsError:
                race_body, _ = _read_final(parent_fd, final_name)
                if race_body != data:
                    raise SupersessionPublishError(
                        "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_CONFLICT"
                    )
                _fsync_retry(parent_fd)
                _validate_parent(parent_fd, parent_identity)
                replay_body, replay_stat = _read_final(parent_fd, final_name)
                if replay_body != data:
                    raise SupersessionPublishError(
                        "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_CONFLICT"
                    )
                if _inventory_staging(parent_fd):
                    raise SupersessionPublishError(
                        "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED"
                    )
                return {
                    "status": "ALREADY_PUBLISHED",
                    "final_name": final_name,
                    "file_sha256": digest,
                    "device": replay_stat.st_dev,
                    "inode": replay_stat.st_ino,
                    "staging_basename": staging_name,
                }
            _fsync_retry(parent_fd)
            _validate_parent(parent_fd, parent_identity)
            final_body, final_stat = _read_final(parent_fd, final_name)
            if final_body != data:
                raise SupersessionPublishError(
                    "CHALLENGER_REPLACEMENT_SUPERSESSION_FINAL_CONFLICT"
                )
            if _inventory_staging(parent_fd):
                raise SupersessionPublishError(
                    "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED"
                )
            return {
                "status": "COMMITTED",
                "final_name": final_name,
                "file_sha256": digest,
                "device": final_stat.st_dev,
                "inode": final_stat.st_ino,
                "staging_basename": staging_name,
            }
        except OSError as error:
            mapped = SupersessionPublishError(
                "CHALLENGER_REPLACEMENT_SUPERSESSION_STAGING_IO_FAILED"
            )
            staging_primary = mapped
            raise mapped from error
        except BaseException as error:
            staging_primary = error
            raise
        finally:
            try:
                _close(staging_fd)
            except SupersessionPublishError as close_error:
                if staging_primary is None:
                    raise
                try:
                    setattr(
                        staging_primary, "close_error", close_error.reason_code
                    )
                except BaseException:
                    pass
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            _close(parent_fd)
        except SupersessionPublishError as close_error:
            if primary is None:
                raise
            try:
                setattr(primary, "close_error", close_error.reason_code)
            except BaseException:
                pass


def _require_empty_protocol_staging() -> None:
    """Fail closed unless the fixed artifact parent has no staging entries."""

    parent_fd, identity = _open_parent()
    primary = None
    try:
        if _inventory_staging(parent_fd):
            raise SupersessionPublishError(
                "RECOVERY_EVIDENCE_PRESENT_RELEASE_BLOCKED"
            )
        _validate_parent(parent_fd, identity)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            _close(parent_fd)
        except SupersessionPublishError as close_error:
            if primary is None:
                raise
            try:
                setattr(primary, "close_error", close_error.reason_code)
            except BaseException:
                pass


def _snapshot_fixed_artifact(name: str) -> Tuple[bytes, os.stat_result]:
    """Read one allowlisted final through the retained governance dirfd."""

    if name not in _FIXED_FINAL_NAMES:
        raise SupersessionPublishError(
            "CHALLENGER_REPLACEMENT_SUPERSESSION_ARTIFACT_INVALID"
        )
    parent_fd, identity = _open_parent()
    primary = None
    try:
        body, opened = _read_final(parent_fd, name)
        _validate_parent(parent_fd, identity)
        return body, opened
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            _close(parent_fd)
        except SupersessionPublishError as close_error:
            if primary is None:
                raise
            try:
                setattr(primary, "close_error", close_error.reason_code)
            except BaseException:
                pass


def publish_challenger_replacement_plan_v2_bytes(data: bytes) -> Dict[str, Any]:
    return _publish_fixed(
        "plan", "challenger-replacement-plan-v0.64.0.json", data
    )


def publish_challenger_replacement_machine_evidence_bytes(
    data: bytes,
) -> Dict[str, Any]:
    return _publish_fixed(
        "machine-evidence",
        "challenger-replacement-supersession-machine-evidence-v0.64.0.json",
        data,
    )


def publish_challenger_replacement_owner_attestation_bytes(
    data: bytes,
) -> Dict[str, Any]:
    return _publish_fixed(
        "owner-attestation",
        "challenger-replacement-owner-attestation-v0.64.0.json",
        data,
    )


def publish_challenger_replacement_supersession_record_bytes(
    data: bytes,
) -> Dict[str, Any]:
    return _publish_fixed(
        "supersession-record",
        "challenger-replacement-plan-supersession-v0.64.0.json",
        data,
    )
