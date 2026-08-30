"""Fixed, code-only trust contracts for replacement Challenger installation."""

import errno
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
from importlib import resources
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_events import _rename_noreplace
from .challenger_replacement_deployment import (
    render_challenger_replacement_install_plist as render_replacement_install_plist,
)
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash


_RUNTIME_ROOT = (
    "/Users/chenm4/Library/Application Support/CryptoQuant/"
    "challenger-replacement-v1"
)
_TARGET_PLIST = (
    "/Users/chenm4/Library/LaunchAgents/"
    "local.crypto-quant.challenger-replacement-v1.plist"
)
_MAX_SNAPSHOT_FILES = 1024
_MAX_SNAPSHOT_FILE_BYTES = 4 * 1024 * 1024
_MAX_SNAPSHOT_TOTAL_BYTES = 128 * 1024 * 1024
_HASH_CHARS = frozenset("0123456789abcdef")

V067_FOUNDATION = MappingProxyType(
    {
        "release_tag": "v0.67.0",
        "tag_object": "7c65c0a34cf37f4d46ed3cdd2a0278657aa3e8c5",
        "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
        "package_version": "0.67.0",
        "manifest_version": "1.61.0",
        "manifest_hash": (
            "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110"
        ),
        "main_ci_run": 32572208544,
    }
)
V067_STRATEGY_CORE = MappingProxyType({
    "release_tag": "v0.67.0",
    "peeled_commit": "ca022edccdcbb2d28b1ea25002e5f19512795e3e",
    "package_version": "0.67.0", "manifest_version": "1.61.0",
    "build_input_tree_hash": "5c2a98492aa45f311cea75617745ac6d1e0afe0ea2ff36a5950a0f5c00c4efa1",
    "manifest_hash": "2b72a470a2f210461a3a6753fd3d603fee9b90df76e825deea3b9bde61a26110",
    "manifest_file_sha256": "ec2ba2d48dd35676eb442ed80cd0e45a642a2b109626db2f54a25d25823a2bf8",
    "file_hashes": {
        "src/crypto_quant/challenger_replacement_decision.py": "a72a93a7aec50e6d5d8ffb9424b33eb05453fef2f9396b1dac05a665c7b6c6ec",
        "src/crypto_quant/challenger_replacement_evidence.py": "920e84a77138509f94b42b416b1ce57adc84daad0a855ab39e9ac6a44799002f",
        "src/crypto_quant/challenger_replacement_live_input.py": "84640cbf81659d05d8abdfa935e8340eb565db20bd3006641a77033d59263536",
        "src/crypto_quant/challenger_replacement_runtime.py": "fbaeb06894f0a3f0468c7382c411e4296fbc2b7e514dfcc26867a97a21eaa97f",
    },
})


class ReplacementInstallTrustError(ValueError):
    """A fixed fail-closed replacement installation trust error."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _validate_strategy_core_inventory(inventory):
    if any(
        inventory.get(name) != digest
        for name, digest in V067_STRATEGY_CORE["file_hashes"].items()
    ):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_STRATEGY_CORE_CHANGED"
        )


def replacement_install_paths() -> Mapping[str, str]:
    """Return the only production paths authorized by the frozen contract."""

    deployment = _RUNTIME_ROOT + "/deployment"
    return {
        "runtime_root": _RUNTIME_ROOT,
        "deployment_root": deployment,
        "contract": deployment
        + "/challenger-replacement-install-contract-v1.json",
        "candidate_plist": deployment
        + "/local.crypto-quant.challenger-replacement-v1.plist",
        "preflight_root": deployment + "/preflight-receipts",
        "install_receipt_root": deployment + "/install-receipts",
        "start_receipt_root": _RUNTIME_ROOT + "/evidence/start-receipts",
        "event_root": _RUNTIME_ROOT
        + "/state/challenger-replacement-events-v1",
        "stdout": _RUNTIME_ROOT + "/log/challenger-replacement.stdout.log",
        "stderr": _RUNTIME_ROOT + "/log/challenger-replacement.stderr.log",
        "target_plist": _TARGET_PLIST,
    }


def _require_open_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_PLATFORM_UNSUPPORTED"
        )
    return value


def _close_descriptor(descriptor: int, primary_error=None) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        if primary_error is None:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_CLOSE_FAILED"
            ) from error
        try:
            primary_error.close_failure = error
        except (AttributeError, TypeError):
            pass


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        try:
            written = os.write(descriptor, remaining)
        except InterruptedError:
            continue
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
        if written <= 0:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            )
        remaining = remaining[written:]


def _fsync_retry(descriptor: int) -> None:
    while True:
        try:
            os.fsync(descriptor)
            return
        except InterruptedError:
            continue
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FSYNC_FAILED"
            ) from error


def _read_exact(descriptor: int, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        try:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
        except InterruptedError:
            continue
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
        if not chunk:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _same_file_identity(left, right) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        left.st_uid,
        left.st_mode,
        left.st_nlink,
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_uid,
        right.st_mode,
        right.st_nlink,
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _validate_absolute_ancestors(path: Path) -> None:
    if not path.is_absolute():
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
        )
    for ancestor in reversed(path.parents):
        try:
            entry = ancestor.lstat()
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
            ) from error
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
            )


def _open_directory(path: Path, *, exact_mode=None) -> tuple:
    nofollow = _require_open_flag("O_NOFOLLOW")
    nonblock = _require_open_flag("O_NONBLOCK")
    directory = _require_open_flag("O_DIRECTORY")
    _validate_absolute_ancestors(path)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | nonblock | directory)
        opened = os.fstat(descriptor)
        attached = path.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or opened.st_uid != os.getuid()
            or (exact_mode is not None and stat.S_IMODE(opened.st_mode) != exact_mode)
            or (exact_mode is None and stat.S_IMODE(opened.st_mode) & 0o022)
            or (opened.st_dev, opened.st_ino) != (attached.st_dev, attached.st_ino)
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
            )
        return descriptor, opened
    except BaseException:
        if descriptor >= 0:
            _close_descriptor(descriptor)
        raise


def _validate_directory_attachment(
    path: Path, descriptor: int, opened, reason_code: str
) -> None:
    try:
        current = os.fstat(descriptor)
        attached = path.lstat()
    except OSError as error:
        raise ReplacementInstallTrustError(reason_code) from error
    if (
        not stat.S_ISDIR(current.st_mode)
        or not stat.S_ISDIR(attached.st_mode)
        or (
            current.st_dev,
            current.st_ino,
            current.st_uid,
            stat.S_IMODE(current.st_mode),
        )
        != (
            opened.st_dev,
            opened.st_ino,
            opened.st_uid,
            stat.S_IMODE(opened.st_mode),
        )
        or (current.st_dev, current.st_ino)
        != (attached.st_dev, attached.st_ino)
    ):
        raise ReplacementInstallTrustError(reason_code)


def _relative_parts(name: str) -> tuple:
    if not isinstance(name, str) or not name or not name.isascii():
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_INVENTORY_INVALID"
        )
    candidate = PurePosixPath(name)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_INVENTORY_INVALID"
        )
    return candidate.parts


def _validate_inventory(inventory: Mapping[str, str]) -> None:
    if (
        not isinstance(inventory, Mapping)
        or not 0 < len(inventory) <= _MAX_SNAPSHOT_FILES
    ):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_INVENTORY_INVALID"
        )
    for name, digest in inventory.items():
        _relative_parts(name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in _HASH_CHARS for character in digest)
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_INVENTORY_INVALID"
            )


def _open_relative_directory(
    parent: int, name: str, *, create: bool, exact_mode=0o700
) -> int:
    nofollow = _require_open_flag("O_NOFOLLOW")
    nonblock = _require_open_flag("O_NONBLOCK")
    directory = _require_open_flag("O_DIRECTORY")
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | nofollow | nonblock | directory,
            dir_fd=parent,
        )
        entry = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(entry.st_mode)
            or entry.st_uid != os.getuid()
            or (
                exact_mode is not None
                and stat.S_IMODE(entry.st_mode) != exact_mode
            )
            or (
                exact_mode is None
                and stat.S_IMODE(entry.st_mode) & 0o022
            )
            or (entry.st_dev, entry.st_ino) != (attached.st_dev, attached.st_ino)
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
            )
        return descriptor
    except BaseException:
        try:
            if "descriptor" in locals():
                _close_descriptor(descriptor)
        finally:
            raise


def _read_source_record(repository_fd: int, name: str):
    parts = _relative_parts(name)
    current = os.dup(repository_fd)
    primary_error = None
    try:
        for part in parts[:-1]:
            following = _open_relative_directory(
                current, part, create=False, exact_mode=None
            )
            _close_descriptor(current)
            current = following
        descriptor = -1
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | _require_open_flag("O_NOFOLLOW")
                | _require_open_flag("O_NONBLOCK"),
                dir_fd=current,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) & 0o022
                or not 0 < opened.st_size <= _MAX_SNAPSHOT_FILE_BYTES
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
                )
            body = _read_exact(descriptor, opened.st_size)
            after = os.fstat(descriptor)
            attached = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if not _same_file_identity(opened, after) or not _same_file_identity(
                after, attached
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
                )
            return body, after
        except OSError as error:
            primary_error = ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
            )
            raise primary_error from error
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if descriptor >= 0:
                _close_descriptor(descriptor, primary_error)
    finally:
        _close_descriptor(current, primary_error)


def _snapshot_tree_hash(inventory: Mapping[str, str]) -> str:
    _validate_inventory(inventory)
    return business_hash(
        {
            "schema_version": "challenger_replacement_snapshot_v1",
            "file_hashes": dict(sorted(inventory.items())),
        }
    )


def _read_snapshot_file(root_fd: int, name: str, expected_hash: str) -> bytes:
    parts = _relative_parts(name)
    current = os.dup(root_fd)
    primary_error = None
    try:
        for part in parts[:-1]:
            following = _open_relative_directory(current, part, create=False)
            _close_descriptor(current)
            current = following
        descriptor = -1
        try:
            descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | _require_open_flag("O_NOFOLLOW")
                | _require_open_flag("O_NONBLOCK"),
                dir_fd=current,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or not 0 < opened.st_size <= _MAX_SNAPSHOT_FILE_BYTES
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
                )
            body = _read_exact(descriptor, opened.st_size)
            after = os.fstat(descriptor)
            attached = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if (
                not _same_file_identity(opened, after)
                or not _same_file_identity(after, attached)
                or hashlib.sha256(body).hexdigest() != expected_hash
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
                )
            return body
        except OSError as error:
            primary_error = ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
            raise primary_error from error
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if descriptor >= 0:
                _close_descriptor(descriptor, primary_error)
    finally:
        _close_descriptor(current, primary_error)


def _snapshot_tree_entries(root_fd: int, prefix=""):
    files = set()
    directories = set()
    try:
        names = os.listdir(root_fd)
    except OSError as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
        ) from error
    for name in names:
        if not isinstance(name, str) or not name or not name.isascii():
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        relative = name if not prefix else prefix + "/" + name
        try:
            entry = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            ) from error
        if stat.S_ISDIR(entry.st_mode):
            child = _open_relative_directory(root_fd, name, create=False)
            try:
                child_files, child_directories = _snapshot_tree_entries(
                    child, relative
                )
            finally:
                _close_descriptor(child)
            directories.add(relative)
            directories.update(child_directories)
            files.update(child_files)
        elif (
            stat.S_ISREG(entry.st_mode)
            and entry.st_uid == os.getuid()
            and entry.st_nlink == 1
            and stat.S_IMODE(entry.st_mode) == 0o600
            and 0 < entry.st_size <= _MAX_SNAPSHOT_FILE_BYTES
        ):
            files.add(relative)
        else:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
    return files, directories


def _replay_snapshot(parent_fd: int, tree_hash: str, inventory: Mapping[str, str]):
    try:
        root_fd = _open_relative_directory(parent_fd, tree_hash, create=False)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
        ) from error
    primary_error = None
    try:
        actual_files, actual_directories = _snapshot_tree_entries(root_fd)
        expected_files = set(inventory)
        expected_directories = {
            "/".join(parts[:index])
            for name in inventory
            for parts in (_relative_parts(name),)
            for index in range(1, len(parts))
        }
        if (
            actual_files != expected_files
            or actual_directories != expected_directories
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        total = 0
        for name, expected_hash in sorted(inventory.items()):
            total += len(_read_snapshot_file(root_fd, name, expected_hash))
        opened = os.fstat(root_fd)
        attached = os.stat(tree_hash, dir_fd=parent_fd, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (attached.st_dev, attached.st_ino):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        return opened, total
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _close_descriptor(root_fd, primary_error)


def _create_snapshot_file(root_fd: int, name: str, body: bytes) -> None:
    parts = _relative_parts(name)
    current = os.dup(root_fd)
    primary_error = None
    try:
        for part in parts[:-1]:
            following = _open_relative_directory(current, part, create=True)
            _fsync_retry(current)
            _close_descriptor(current)
            current = following
        descriptor = -1
        try:
            descriptor = os.open(
                parts[-1],
                os.O_CREAT
                | os.O_EXCL
                | os.O_RDWR
                | _require_open_flag("O_NOFOLLOW"),
                0o600,
                dir_fd=current,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_size != 0
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_STAGING_UNTRUSTED"
                )
            _write_all(descriptor, body)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if _read_exact(descriptor, len(body)) != body:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
                )
            after = os.fstat(descriptor)
            attached = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
            if (
                not _same_file_identity(after, attached)
                or after.st_size != len(body)
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_STAGING_UNTRUSTED"
                )
            _fsync_retry(descriptor)
            _fsync_retry(current)
        except OSError as error:
            primary_error = ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            )
            raise primary_error from error
        except BaseException as error:
            primary_error = error
            raise
        finally:
            if descriptor >= 0:
                _close_descriptor(descriptor, primary_error)
    finally:
        _close_descriptor(current, primary_error)


def _publish_snapshot_from_inventory(
    repository: Path,
    snapshot_parent: Path,
    inventory: Mapping[str, str],
) -> Mapping[str, Any]:
    """Private fixtureable implementation for the fixed production renderer."""

    for flag in ("O_NOFOLLOW", "O_NONBLOCK", "O_DIRECTORY"):
        _require_open_flag(flag)
    _validate_inventory(inventory)
    tree_hash = _snapshot_tree_hash(inventory)
    repository_fd, repository_entry = _open_directory(Path(repository))
    parent_fd = -1
    primary_error = None
    try:
        bodies = {}
        source_stats = {}
        total_size = 0
        for name, expected_hash in sorted(inventory.items()):
            body, source_entry = _read_source_record(repository_fd, name)
            if hashlib.sha256(body).hexdigest() != expected_hash:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
                )
            total_size += len(body)
            if total_size > _MAX_SNAPSHOT_TOTAL_BYTES:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_INVENTORY_INVALID"
                )
            bodies[name] = body
            source_stats[name] = source_entry
        parent_fd, parent_entry = _open_directory(
            Path(snapshot_parent), exact_mode=0o700
        )
        names = os.listdir(parent_fd)
        if any(name.startswith(".stage-snapshot-") for name in names):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_ORPHAN_STAGING"
            )
        existing = _replay_snapshot(parent_fd, tree_hash, inventory)
        if existing is not None:
            _fsync_retry(parent_fd)
            entry, replayed_total = existing
            if replayed_total != total_size:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
                )
            _validate_directory_attachment(
                Path(repository),
                repository_fd,
                repository_entry,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
            )
            _validate_directory_attachment(
                Path(snapshot_parent),
                parent_fd,
                parent_entry,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED",
            )
            return {
                "outcome": "ALREADY_PUBLISHED",
                "root": str(Path(snapshot_parent) / tree_hash),
                "tree_hash": tree_hash,
                "file_count": len(inventory),
                "total_size_bytes": total_size,
                "root_device": entry.st_dev,
                "root_inode": entry.st_ino,
            }
        staging = ".stage-snapshot-{}-{}".format(
            tree_hash, secrets.token_hex(16)
        )
        try:
            os.mkdir(staging, 0o700, dir_fd=parent_fd)
            staging_fd = _open_relative_directory(parent_fd, staging, create=False)
        except OSError as error:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
        try:
            for name, body in sorted(bodies.items()):
                _create_snapshot_file(staging_fd, name, body)
            _fsync_retry(staging_fd)
        finally:
            _close_descriptor(staging_fd)
        try:
            _rename_noreplace(parent_fd, staging, tree_hash)
        except FileExistsError:
            race = _replay_snapshot(parent_fd, tree_hash, inventory)
            if race is None:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_CONFLICT"
                )
            _fsync_retry(parent_fd)
            entry, replayed_total = race
            for name, expected_body in sorted(bodies.items()):
                current_body, current_entry = _read_source_record(
                    repository_fd, name
                )
                if (
                    current_body != expected_body
                    or not _same_file_identity(
                        source_stats[name], current_entry
                    )
                ):
                    raise ReplacementInstallTrustError(
                        "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
                    )
            if replayed_total != total_size:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
                )
            _validate_directory_attachment(
                Path(repository),
                repository_fd,
                repository_entry,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
            )
            _validate_directory_attachment(
                Path(snapshot_parent),
                parent_fd,
                parent_entry,
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED",
            )
            return {
                "outcome": "ALREADY_PUBLISHED",
                "root": str(Path(snapshot_parent) / tree_hash),
                "tree_hash": tree_hash,
                "file_count": len(inventory),
                "total_size_bytes": total_size,
                "root_device": entry.st_dev,
                "root_inode": entry.st_ino,
            }
        except OSError as error:
            if error.errno in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_PLATFORM_UNSUPPORTED"
                ) from error
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
        _fsync_retry(parent_fd)
        replayed = _replay_snapshot(parent_fd, tree_hash, inventory)
        if replayed is None:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        entry, replayed_total = replayed
        if replayed_total != total_size:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        for name, expected_body in sorted(bodies.items()):
            current_body, current_entry = _read_source_record(repository_fd, name)
            if (
                current_body != expected_body
                or not _same_file_identity(source_stats[name], current_entry)
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED"
                )
        _validate_directory_attachment(
            Path(repository),
            repository_fd,
            repository_entry,
            "CHALLENGER_REPLACEMENT_SNAPSHOT_SOURCE_UNTRUSTED",
        )
        _validate_directory_attachment(
            Path(snapshot_parent),
            parent_fd,
            parent_entry,
            "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED",
        )
        return {
            "outcome": "PUBLISHED",
            "root": str(Path(snapshot_parent) / tree_hash),
            "tree_hash": tree_hash,
            "file_count": len(inventory),
            "total_size_bytes": total_size,
            "root_device": entry.st_dev,
            "root_inode": entry.st_ino,
        }
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if parent_fd >= 0:
            _close_descriptor(parent_fd, primary_error)
        _close_descriptor(repository_fd, primary_error)


def _read_published_exact(parent_fd: int, name: str):
    descriptor = -1
    primary_error = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | _require_open_flag("O_NOFOLLOW")
            | _require_open_flag("O_NONBLOCK"),
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o600
            or not 0 < opened.st_size <= _MAX_SNAPSHOT_FILE_BYTES
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
            )
        body = _read_exact(descriptor, opened.st_size)
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not _same_file_identity(opened, after) or not _same_file_identity(
            after, attached
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
            )
        return body, after
    except OSError as error:
        primary_error = ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
        )
        raise primary_error from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary_error)


def _publish_contract_exact(parent: Path, name: str, body: bytes, *, parent_mode=0o700):
    parent_fd, parent_opened = _open_directory(parent, exact_mode=parent_mode)
    primary_error = None
    try:
        existing = _read_published_exact(parent_fd, name)
        if existing is not None:
            if existing[0] != body:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT"
                )
            _fsync_retry(parent_fd)
            _validate_directory_attachment(
                parent, parent_fd, parent_opened,
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED",
            )
            return "ALREADY_PUBLISHED", existing[1]
        if any(
            candidate.startswith(".stage-contract-")
            for candidate in os.listdir(parent_fd)
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_ORPHAN_STAGING"
            )
        staging = ".stage-contract-{}-{}.tmp".format(
            hashlib.sha256(body).hexdigest(), secrets.token_hex(16)
        )
        descriptor = -1
        write_error = None
        try:
            descriptor = os.open(
                staging,
                os.O_CREAT
                | os.O_EXCL
                | os.O_RDWR
                | _require_open_flag("O_NOFOLLOW"),
                0o600,
                dir_fd=parent_fd,
            )
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_size != 0
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
                )
            _write_all(descriptor, body)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if _read_exact(descriptor, len(body)) != body:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
                )
            after = os.fstat(descriptor)
            attached = os.stat(staging, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not _same_file_identity(after, attached)
                or after.st_size != len(body)
            ):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
                )
            _fsync_retry(descriptor)
        except OSError as error:
            write_error = ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            )
            raise write_error from error
        except BaseException as error:
            write_error = error
            raise
        finally:
            if descriptor >= 0:
                _close_descriptor(descriptor, write_error)
        try:
            _rename_noreplace(parent_fd, staging, name)
        except FileExistsError:
            raced = _read_published_exact(parent_fd, name)
            if raced is None or raced[0] != body:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_CONFLICT"
                )
            _fsync_retry(parent_fd)
            _validate_directory_attachment(
                parent, parent_fd, parent_opened,
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED",
            )
            return "ALREADY_PUBLISHED", raced[1]
        except OSError as error:
            if error.errno in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_INSTALL_PLATFORM_UNSUPPORTED"
                ) from error
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_IO_FAILED"
            ) from error
        _fsync_retry(parent_fd)
        final = _read_published_exact(parent_fd, name)
        if final is None or final[0] != body:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED"
            )
        _validate_directory_attachment(
            parent, parent_fd, parent_opened,
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_UNTRUSTED",
        )
        return "PUBLISHED", final[1]
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _close_descriptor(parent_fd, primary_error)


def _binding_from_snapshot(
    snapshot,
    inventory,
    relative_path: str,
    *,
    id_key: str,
    hash_key: str,
):
    root_fd = -1
    primary_error = None
    try:
        expected_hash = inventory[relative_path]
        root_fd, opened = _open_directory(
            Path(snapshot["root"]), exact_mode=0o700
        )
        if (
            opened.st_dev != snapshot["root_device"]
            or opened.st_ino != snapshot["root_inode"]
        ):
            raise ValueError("snapshot identity")
        body = _read_snapshot_file(root_fd, relative_path, expected_hash)
        value = dict(_strict_json_bytes(body))
        return {
            "path": relative_path,
            "file_sha256": hashlib.sha256(body).hexdigest(),
            id_key: value[id_key],
            hash_key: value[hash_key],
        }, value
    except (KeyError, OSError, TypeError, ValueError) as error:
        primary_error = ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_FOUNDATION_INVALID"
        )
        raise primary_error from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if root_fd >= 0:
            _close_descriptor(root_fd, primary_error)


def _build_install_contract(
    *,
    snapshot,
    inventory,
    candidate_release,
    github_verification,
    python_identity,
    event_root_identity,
):
    _validate_strategy_core_inventory(inventory)
    paths = dict(replacement_install_paths())
    plan, _ = _binding_from_snapshot(
        snapshot,
        inventory,
        "artifacts/challenger-replacement/challenger-replacement-plan-v0.64.0.json",
        id_key="plan_id",
        hash_key="plan_hash",
    )
    deployment, deployment_value = _binding_from_snapshot(
        snapshot,
        inventory,
        "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json",
        id_key="deployment_id",
        hash_key="deployment_hash",
    )
    deployment["plist_sha256"] = deployment_value["plist_sha256"]
    contract = {
        "$schema": "./challenger-replacement-install-contract-v1.schema.json",
        "schema_version": "1.0.0",
        "contract_id": "challenger_replacement_install_contract_" + "0" * 64,
        "contract_hash": "0" * 64,
        "predecessor_release": dict(V067_FOUNDATION),
        "candidate_release": dict(candidate_release),
        "github_verification": dict(github_verification),
        "plan": plan,
        "deployment": deployment,
        "strategy_core": dict(V067_STRATEGY_CORE),
        "event_root": dict(event_root_identity),
        "plist": {"path": paths["candidate_plist"], "file_sha256": "0" * 64},
        "snapshot": {
            key: snapshot[key]
            for key in (
                "root",
                "tree_hash",
                "file_count",
                "total_size_bytes",
                "root_device",
                "root_inode",
            )
        },
        "python": dict(python_identity),
        "service": {
            "label": "local.crypto-quant.challenger-replacement-v1",
            "identity": "gui/501/local.crypto-quant.challenger-replacement-v1",
        },
        "paths": paths,
        "runtime": {
            "module": "crypto_quant.challenger_replacement_installed_runtime_cli",
            "worker_id": "challenger-replacement-natural-runner-v1",
            "program_arguments": [
                python_identity["path"],
                "-m",
                "crypto_quant.challenger_replacement_installed_runtime_cli",
            ],
            "working_directory": snapshot["root"],
            "environment": {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONPATH": snapshot["root"] + "/src",
            },
        },
        "schedule": [
            {"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)
        ],
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": True,
            "replacement_start_authorized": False,
            "real_orders_allowed": False,
        },
        "warnings": [
            "INSTALL_AUTHORIZES_BOOTSTRAP_ONLY",
            "NO_KICKSTART_OR_MANUAL_RUNTIME",
            "NO_CREDENTIAL_BROKER_OR_ORDER_AUTHORITY",
            "START_RECEIPT_NOT_YET_AVAILABLE",
        ],
    }
    contract["plist"]["file_sha256"] = hashlib.sha256(
        render_replacement_install_plist(contract)
    ).hexdigest()
    identity = {
        key: value
        for key, value in contract.items()
        if key not in ("contract_id", "contract_hash")
    }
    contract["contract_id"] = stable_id(
        "challenger_replacement_install_contract", identity
    )
    contract["contract_hash"] = artifact_self_hash(contract, "contract_hash")
    return contract


def _run_fixed_command(argv, *, cwd: Path, environment=None):
    try:
        result = subprocess.run(
            tuple(argv),
            cwd=cwd,
            env=(
                {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
                if environment is None
                else dict(environment)
            ),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_RELEASE_IDENTITY_INVALID"
        ) from error
    if (
        result.returncode != 0
        or len(result.stdout) > 1024 * 1024
        or len(result.stderr) > 1024 * 1024
    ):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_RELEASE_IDENTITY_INVALID"
        )
    return result.stdout, result.stderr


def _command_transcript(argv, stdout, stderr):
    return {
        "argv": list(argv),
        "exit_code": 0,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }


def _collect_fixed_release_inputs(repository: Path):
    manifest_path = repository / "config/evaluator-build-manifest-v1.json"
    try:
        manifest = dict(_strict_json_bytes(manifest_path.read_bytes()))
        if (
            manifest["manifest_version"] != "1.62.0"
            or manifest["package_version"] != "0.68.0"
            or manifest["manifest_hash"]
            != artifact_self_hash(manifest, "manifest_hash")
        ):
            raise ValueError("manifest identity")
        inventory = dict(manifest["file_hashes"])
        if not inventory or any(
            hashlib.sha256((repository / name).read_bytes()).hexdigest() != digest
            for name, digest in inventory.items()
        ):
            raise ValueError("manifest files")
        inventory["config/evaluator-build-manifest-v1.json"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
    except (KeyError, OSError, TypeError, ValueError) as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_RELEASE_IDENTITY_INVALID"
        ) from error

    git_commands = (
        ("git", "remote", "get-url", "origin"),
        ("git", "rev-parse", "HEAD"),
        ("git", "rev-parse", "origin/main"),
        ("git", "rev-parse", "v0.68.0^{}"),
        ("git", "rev-parse", "v0.68.0"),
        ("git", "cat-file", "-t", "v0.68.0"),
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    )
    outputs = [
        _run_fixed_command(argv, cwd=repository)[0].decode("utf-8", "strict").strip()
        for argv in git_commands
    ]
    origin, head, remote_main, peeled, tag_object, tag_type, status_text = outputs
    if (
        origin != "https://github.com/cjl308868584-lang/crypto-quant-core.git"
        or not len(head) == 40
        or not head == remote_main == peeled
        or len(tag_object) != 40
        or tag_type != "tag"
        or status_text
    ):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_RELEASE_IDENTITY_INVALID"
        )

    repository_argv = (
        "gh", "api", "repos/cjl308868584-lang/crypto-quant-core"
    )
    repo_out, repo_err = _run_fixed_command(repository_argv, cwd=repository)
    run_argv = (
        "gh", "run", "list", "--repo",
        "cjl308868584-lang/crypto-quant-core", "--workflow", "ci.yml",
        "--branch", "main", "--commit", head, "--status", "success",
        "--limit", "1", "--json", "databaseId,headSha,conclusion",
    )
    run_out, run_err = _run_fixed_command(run_argv, cwd=repository)
    try:
        repository_value = json.loads(repo_out.decode("utf-8"))
        runs = json.loads(run_out.decode("utf-8"))
        if len(runs) != 1:
            raise ValueError("run count")
        run = runs[0]
        run_id = run["databaseId"]
        jobs_argv = (
            "gh", "run", "view", str(run_id), "--repo",
            "cjl308868584-lang/crypto-quant-core", "--json", "jobs",
        )
        jobs_out, jobs_err = _run_fixed_command(jobs_argv, cwd=repository)
        jobs_value = json.loads(jobs_out.decode("utf-8"))["jobs"]
        jobs = {item["name"]: item["conclusion"] for item in jobs_value}
        if (
            repository_value["full_name"]
            != "cjl308868584-lang/crypto-quant-core"
            or repository_value["visibility"] != "public"
            or repository_value["permissions"]["admin"] is not True
            or run["headSha"] != head
            or run["conclusion"] != "success"
            or jobs
            != {
                "Python 3.9": "success",
                "Python 3.12": "success",
                "macOS 15 arm64": "success",
            }
        ):
            raise ValueError("github identity")
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_RELEASE_IDENTITY_INVALID"
        ) from error
    github = {
        "request_count": 3,
        "repository": {
            "name_with_owner": repository_value["full_name"],
            "visibility": repository_value["visibility"].upper(),
            "admin": True,
        },
        "main_run": {
            "run_id": run_id,
            "head_sha": head,
            "conclusion": "success",
        },
        "jobs": jobs,
        "transcripts": [
            _command_transcript(repository_argv, repo_out, repo_err),
            _command_transcript(run_argv, run_out, run_err),
            _command_transcript(jobs_argv, jobs_out, jobs_err),
        ],
    }
    candidate = {
        "release_tag": "v0.68.0",
        "tag_object": tag_object,
        "peeled_commit": head,
        "package_version": "0.68.0",
        "manifest_version": "1.62.0",
        "manifest_hash": manifest["manifest_hash"],
        "manifest_file_sha256": hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest(),
        "build_input_tree_hash": manifest["build_input_tree_hash"],
        "main_ci_run": run_id,
        "main_ci_jobs": jobs,
    }
    return inventory, candidate, github


def _ensure_fixed_snapshot_directories(paths):
    runtime = Path(paths["runtime_root"])
    deployment = runtime / "deployment"
    receipt_names = []
    for key, fallback in (
        ("preflight_root", deployment / "preflight-receipts"), ("install_receipt_root", deployment / "install-receipts"),
        *((('recovery_receipt_root', None),) if "recovery_receipt_root" in paths else ()),
    ):
        receipt = Path(paths.get(key, fallback))
        if receipt.parent != deployment:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
            )
        receipt_names.append(receipt.name)
    anchor = runtime.parent
    anchor_fd, _ = _open_directory(anchor)
    primary_error = None
    current = anchor_fd
    try:
        for name in (runtime.name, "deployment"):
            following = _open_relative_directory(current, name, create=True)
            _fsync_retry(current)
            if current != anchor_fd:
                _close_descriptor(current)
            current = following
        for name in ("snapshots", *receipt_names):
            try:
                child = _open_relative_directory(current, name, create=True)
            except OSError as error:
                raise ReplacementInstallTrustError(
                    "CHALLENGER_REPLACEMENT_SNAPSHOT_PATH_UNTRUSTED"
                ) from error
            _fsync_retry(current)
            _close_descriptor(child)
        snapshot_parent = runtime / "deployment" / "snapshots"
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if current != anchor_fd:
            _close_descriptor(current, primary_error)
        _close_descriptor(anchor_fd, primary_error)
    runtime_fd, _ = _open_directory(runtime, exact_mode=0o700)
    primary_error = None
    try:
        for parent_name, child_name in (
            ("state", "challenger-replacement-events-v1"),
            ("evidence", "start-receipts"),
        ):
            parent_fd = _open_relative_directory(
                runtime_fd, parent_name, create=True
            )
            try:
                child_fd = _open_relative_directory(
                    parent_fd, child_name, create=True
                )
                _close_descriptor(child_fd)
                _fsync_retry(parent_fd)
            finally:
                _close_descriptor(parent_fd)
        log_fd = _open_relative_directory(runtime_fd, "log", create=True)
        _close_descriptor(log_fd)
        _fsync_retry(runtime_fd)
        return snapshot_parent
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _close_descriptor(runtime_fd, primary_error)


def _fixed_empty_event_root_identity(paths):
    path = Path(paths["event_root"])
    descriptor, opened = _open_directory(path, exact_mode=0o700)
    primary_error = None
    try:
        if os.listdir(descriptor):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_NOT_EMPTY"
            )
        _validate_directory_attachment(
            path, descriptor, opened,
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_UNTRUSTED",
        )
        return {
            "path": str(path), "device": opened.st_dev,
            "inode": opened.st_ino, "owner_uid": opened.st_uid,
            "mode": stat.S_IMODE(opened.st_mode),
            "initial_event_count": 0, "initial_orphan_staging_count": 0,
        }
    except BaseException as error:
        primary_error = error
        raise
    finally:
        _close_descriptor(descriptor, primary_error)


def _fixed_python_identity(
    snapshot_root: str,
    *,
    package_version="0.68.0",
    allow_user_site=False,
    dependency_modules=(),
    dependency_versions=None,
    python_paths=(),
    import_modules=(
        "crypto_quant.challenger_replacement_installed_runtime_cli",
        "crypto_quant.challenger_replacement_runtime",
        "crypto_quant.challenger_replacement_decision",
        "crypto_quant.challenger_replacement_evidence",
    ),
):
    python_path = Path("/usr/bin/python3")
    descriptor = -1
    primary_error = None
    try:
        descriptor = os.open(python_path, os.O_RDONLY
                             | _require_open_flag("O_NOFOLLOW")
                             | _require_open_flag("O_NONBLOCK"))
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != 0
            or stat.S_IMODE(opened.st_mode) & 0o022
            or not 0 < opened.st_size <= 64 * 1024 * 1024
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID")
        body = _read_exact(descriptor, opened.st_size)
        after = os.fstat(descriptor)
        attached = python_path.lstat()
        if not _same_file_identity(opened, after) or not _same_file_identity(
            after, attached
        ):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID")
    except OSError as error:
        primary_error = error
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID") from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary_error)
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(tuple(python_paths) + (snapshot_root + "/src",)),
    }
    if not allow_user_site:
        environment["PYTHONNOUSERSITE"] = "1"
    imports = ",".join(
        ("crypto_quant",) + tuple(import_modules) + tuple(dependency_modules)
    )
    dependency_versions = dependency_versions or {}
    if set(dependency_versions) != set(dependency_modules):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID"
        )
    if dependency_modules:
        code = (
            "import " + imports + ",importlib.metadata,json,sys;"
            "print(json.dumps({'dependency_versions':{name:importlib.metadata.version(value[0]) "
            "for name,value in " + repr(dict(dependency_versions)) + ".items()},"
            "'package_version':crypto_quant.__version__,'sys_version':sys.version},"
            "separators=(',',':'),sort_keys=True))"
        )
    else:
        code = (
            "import " + imports + ",json,sys;print(json.dumps({"
            "'package_version':crypto_quant.__version__,'sys_version':sys.version},"
            "separators=(',',':'),sort_keys=True))"
        )
    command = (
        ("/usr/bin/python3",) + (() if allow_user_site else ("-s",))
        + ("-c", code)
    )
    stdout, stderr = _run_fixed_command(
        command, cwd=Path(snapshot_root), environment=environment
    )
    try:
        identity_output = json.loads(stdout.decode("utf-8", "strict"))
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID"
        ) from error
    if (
        not isinstance(identity_output, dict)
        or set(identity_output) != ({"package_version", "sys_version"}
                                    | ({"dependency_versions"}
                                       if dependency_modules else set()))
        or identity_output["package_version"] != package_version
        or not isinstance(identity_output["sys_version"], str)
        or not identity_output["sys_version"]
        or (dependency_modules and identity_output["dependency_versions"]
            != {name: value[1] for name, value in dependency_versions.items()})
    ):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_INVALID"
        )
    return {
        "path": str(python_path),
        "device": opened.st_dev,
        "inode": opened.st_ino,
        "owner_uid": opened.st_uid,
        "mode": stat.S_IMODE(opened.st_mode),
        "link_count": opened.st_nlink,
        "size_bytes": opened.st_size,
        "sha256": hashlib.sha256(body).hexdigest(),
        "sys_version": identity_output["sys_version"],
        "import_stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "import_stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }


def _revalidate_fixed_python_identity(contract):
    try:
        if _fixed_python_identity(contract["snapshot"]["root"]) != contract[
            "python"
        ]:
            raise ValueError("identity")
    except ReplacementInstallTrustError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_PYTHON_IDENTITY_CHANGED"
        ) from error


def render_fixed_replacement_snapshot_and_contract():
    """Render the fixed ceremony inputs after v0.68 is fully released."""

    repository = Path(__file__).resolve().parents[2]
    inventory, candidate, github = _collect_fixed_release_inputs(repository)
    paths = replacement_install_paths()
    snapshot_parent = _ensure_fixed_snapshot_directories(paths)
    snapshot = _publish_snapshot_from_inventory(
        repository, snapshot_parent, inventory
    )
    python_identity = _fixed_python_identity(snapshot["root"])
    contract = _build_install_contract(
        snapshot=snapshot,
        inventory=inventory,
        candidate_release=candidate,
        github_verification=github,
        python_identity=python_identity,
        event_root_identity=_fixed_empty_event_root_identity(paths),
    )
    body = canonical_json(contract).encode("utf-8")
    load_replacement_install_contract_bytes(body)
    plist_body = render_replacement_install_plist(contract)
    plist_outcome, _ = _publish_contract_exact(
        Path(paths["deployment_root"]), Path(paths["candidate_plist"]).name,
        plist_body,
    )
    outcome, _ = _publish_contract_exact(
        Path(paths["deployment_root"]), Path(paths["contract"]).name, body
    )
    return {
        "snapshot": snapshot,
        "contract": contract,
        "plist_outcome": plist_outcome,
        "contract_outcome": outcome,
    }


def _contract_schema() -> Mapping[str, Any]:
    return json.loads(
        resources.files("crypto_quant")
        .joinpath("schemas/challenger-replacement-install-contract-v1.schema.json")
        .read_text(encoding="utf-8")
    )


def load_replacement_install_contract_bytes(data: bytes) -> Mapping[str, Any]:
    """Load canonical contract bytes without touching any production path."""

    try:
        contract = dict(_strict_json_bytes(data))
        if data != canonical_json(contract).encode("utf-8"):
            raise ValueError("non-canonical contract")
        if tuple(Draft202012Validator(_contract_schema()).iter_errors(contract)):
            raise ValueError("contract schema")
        identity = {
            key: value
            for key, value in contract.items()
            if key not in ("contract_id", "contract_hash")
        }
        if contract["contract_id"] != stable_id(
            "challenger_replacement_install_contract", identity
        ):
            raise ValueError("contract id")
        if contract["contract_hash"] != artifact_self_hash(
            contract, "contract_hash"
        ):
            raise ValueError("contract hash")
        if contract["predecessor_release"] != dict(V067_FOUNDATION):
            raise ValueError("predecessor")
        if contract["paths"] != replacement_install_paths():
            raise ValueError("paths")
        if contract["strategy_core"] != dict(V067_STRATEGY_CORE):
            raise ValueError("strategy core")
        event_root = contract["event_root"]
        if (
            event_root["path"] != contract["paths"]["event_root"]
            or event_root["owner_uid"] != 501
            or event_root["mode"] != 0o700
            or event_root["initial_event_count"] != 0
            or event_root["initial_orphan_staging_count"] != 0
        ):
            raise ValueError("event root")
        if contract["runtime"]["worker_id"] != (
            "challenger-replacement-natural-runner-v1"
        ):
            raise ValueError("worker")
        if contract["plist"] != {
            "path": replacement_install_paths()["candidate_plist"],
            "file_sha256": hashlib.sha256(
                render_replacement_install_plist(contract)
            ).hexdigest(),
        }:
            raise ValueError("plist")
        if contract["authority"] != {
            "production_activation": False,
            "runtime_install_authorized": True,
            "replacement_start_authorized": False,
            "real_orders_allowed": False,
        }:
            raise ValueError("authority")
        if contract["schedule"] != [
            {"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)
        ]:
            raise ValueError("schedule")
        return contract
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReplacementInstallTrustError):
            raise
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID"
        ) from error


def _load_fixed_published_contract():
    path = Path(replacement_install_paths()["contract"])
    parent_fd, _ = _open_directory(path.parent, exact_mode=0o700)
    primary = None
    try:
        loaded = _read_published_exact(parent_fd, path.name)
        if loaded is None:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID"
            )
        contract = load_replacement_install_contract_bytes(loaded[0])
        replay_replacement_snapshot(contract)
        plist = _read_published_exact(
            parent_fd, Path(contract["plist"]["path"]).name
        )
        if plist is None or hashlib.sha256(plist[0]).hexdigest() != contract["plist"]["file_sha256"]:
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_INSTALL_CONTRACT_INVALID")
        return contract, loaded[0], plist[0]
    except BaseException as error:
        primary = error
        raise
    finally:
        _close_descriptor(parent_fd, primary)


def replay_replacement_snapshot(contract: Mapping[str, Any]):
    snapshot = contract["snapshot"]
    root = Path(snapshot["root"])
    if root != (Path(contract["paths"]["deployment_root"]) / "snapshots"
                / snapshot["tree_hash"]):
        raise ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
        )
    parent_fd, _ = _open_directory(root.parent, exact_mode=0o700)
    root_fd = -1
    primary = None
    manifest_name = "config/evaluator-build-manifest-v1.json"
    try:
        root_fd = _open_relative_directory(
            parent_fd, snapshot["tree_hash"], create=False
        )
        opened = os.fstat(root_fd)
        body = _read_snapshot_file(
            root_fd, manifest_name,
            contract["candidate_release"]["manifest_file_sha256"],
        )
        inventory = dict(_strict_json_bytes(body)["file_hashes"])
        inventory[manifest_name] = hashlib.sha256(body).hexdigest()
        replayed = _replay_snapshot(parent_fd, snapshot["tree_hash"], inventory)
        if replayed is None or (
            replayed[0].st_dev, replayed[0].st_ino, len(inventory), replayed[1]
        ) != (
            snapshot["root_device"], snapshot["root_inode"],
            snapshot["file_count"], snapshot["total_size_bytes"],
        ) or (opened.st_dev, opened.st_ino) != (replayed[0].st_dev, replayed[0].st_ino):
            raise ReplacementInstallTrustError(
                "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
            )
        return {"file_count": len(inventory), "total_size_bytes": replayed[1]}
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ReplacementInstallTrustError):
            primary = error
            raise
        primary = ReplacementInstallTrustError(
            "CHALLENGER_REPLACEMENT_SNAPSHOT_FINAL_UNTRUSTED"
        )
        raise primary from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if root_fd >= 0:
            _close_descriptor(root_fd, primary)
        _close_descriptor(parent_fd, primary)
