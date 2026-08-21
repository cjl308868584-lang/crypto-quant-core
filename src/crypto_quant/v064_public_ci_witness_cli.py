"""Fixed GitHub evidence acquisition boundary for the v0.64 witness."""

import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import secrets
import selectors
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .canonical import canonical_json
from .challenger_replacement_supersession_publish import _atomic_no_replace


_GH = "/Users/chenm4/.local/bin/gh"
_REPOSITORY = "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
_PRIVATE_REPOSITORY = Path(__file__).absolute().parents[2]
_ARTIFACT_ROOT = _PRIVATE_REPOSITORY / "artifacts" / "v064-public-ci-r3"
_PUBLIC_CANDIDATE_MANIFEST = Path(
    "/private/tmp/crypto-quant-v064-public-ci-r3-candidate/bundle-manifest-v1.json"
)
_EVIDENCE_NAMES = (
    "v064-public-ci-r3-run-api-v1.json",
    "v064-public-ci-r3-jobs-api-v1.json",
    "v064-public-ci-r3-run-log-v1.txt",
    "v064-public-ci-r3-acquisition-transcript-v1.json",
    "v064-public-ci-r3-witness-v1.json",
)
_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_OWNER_UID = 501
_STAGING_PREFIX = ".v064-public-ci-r3-"
_STAGING_RE = re.compile(
    r"\A\.v064-public-ci-r3-(?P<final>" +
    "|".join(re.escape(name) for name in _EVIDENCE_NAMES) +
    r")-(?P<digest>[0-9a-f]{64})-(?P<nonce>[0-9a-f]{32})\.staging\Z",
    re.ASCII,
)
_GH_SHA256 = "b1d6c442fde99ca27c04e1e74d624895abe37785f4a3e9e9b684bf7586ce4bc8"
_GH_VERSION = (
    b"gh version 2.96.0 (2026-07-02)\n"
    b"https://github.com/cli/cli/releases/tag/v2.96.0\n"
)
_GH_HOME = "/Users/chenm4"
_GH_ENV = {
    "HOME": _GH_HOME, "PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C",
}
_RUN_PROJECTION = "{id,workflow_id,run_attempt,event,head_branch,head_sha,status,conclusion,created_at,updated_at,path,repository:.repository.full_name}"
_JOBS_PROJECTION = "{total_count,jobs:[.jobs[]|{id,name,status,conclusion,runner_name,labels,started_at,completed_at,steps:[.steps[]|{number,name,status,conclusion}]}]}"


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or not value:
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNSUPPORTED")
    return value


def _canonical_json_bytes(body: bytes) -> bool:
    try:
        value = json.loads(body.decode("utf-8"))
        encoded = canonical_json(value).encode("utf-8") + b"\n"
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
        return False
    return encoded == body


def _acquire_ceremony_lock(root_fd: int) -> None:
    try:
        fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK}:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_CONCURRENT") from error
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_LOCK_FAILED") from error


def _write_all(descriptor: int, body: bytes) -> None:
    offset = 0
    while offset < len(body):
        try:
            written = os.write(descriptor, body[offset:])
        except InterruptedError:
            continue
        except OSError as error:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED") from error
        if written <= 0:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED")
        offset += written


def _fsync(descriptor: int) -> None:
    while True:
        try:
            os.fsync(descriptor)
            return
        except InterruptedError:
            continue
        except OSError as error:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_FSYNC_FAILED") from error


def _close_preserving(descriptor: int, primary: BaseException = None) -> None:
    try:
        os.close(descriptor)
    except OSError as error:
        if primary is not None:
            try:
                setattr(primary, "close_error", "V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED")
            except BaseException:
                pass
            return
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED") from error


def _read_descriptor(descriptor: int, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        try:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
        except InterruptedError:
            continue
        except OSError as error:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED") from error
        if not chunk:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED")
        chunks.append(chunk)
        remaining -= len(chunk)
    try:
        extra = os.read(descriptor, 1)
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED") from error
    if extra:
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED")
    return b"".join(chunks)


def _trusted_directory(value: os.stat_result, mode: int) -> bool:
    return (
        stat.S_ISDIR(value.st_mode)
        and value.st_uid == os.geteuid() == _OWNER_UID
        and stat.S_IMODE(value.st_mode) == mode
    )


def _validate_repository_identity() -> None:
    raw_module = Path(__file__)
    if (
        not raw_module.is_absolute()
        or raw_module.is_symlink()
        or raw_module.parents[2] != _PRIVATE_REPOSITORY
    ):
        raise ValueError("V064_PUBLIC_CI_R3_REPOSITORY_INVALID")
    current = Path(raw_module.anchor)
    try:
        for component in raw_module.parts[1:]:
            current = current / component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise ValueError("V064_PUBLIC_CI_R3_REPOSITORY_INVALID")
    except ValueError:
        raise
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_R3_REPOSITORY_INVALID") from error
    try:
        from .challenger_replacement_plan_supersession_cli import (
            _validate_reviewed_repo_root,
        )

        _validate_reviewed_repo_root(_PRIVATE_REPOSITORY)
    except BaseException as error:
        raise ValueError("V064_PUBLIC_CI_R3_REPOSITORY_INVALID") from error


def _validate_root(descriptor: int, expected: os.stat_result) -> None:
    try:
        opened = os.fstat(descriptor)
        attached = _ARTIFACT_ROOT.lstat()
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID") from error
    if (
        not _trusted_directory(opened, 0o700)
        or not _trusted_directory(attached, 0o700)
        or (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
        or (attached.st_dev, attached.st_ino) != (expected.st_dev, expected.st_ino)
    ):
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")


def _open_artifact_root() -> Tuple[int, os.stat_result]:
    _validate_repository_identity()
    if _ARTIFACT_ROOT != _PRIVATE_REPOSITORY / "artifacts" / "v064-public-ci-r3":
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")
    nofollow = _required_flag("O_NOFOLLOW")
    directory = _required_flag("O_DIRECTORY")
    flags = os.O_RDONLY | nofollow | directory
    parent = _PRIVATE_REPOSITORY / "artifacts"
    parent_fd = None
    root_fd = None
    completed = False
    primary = None
    try:
        parent_stat = parent.lstat()
        if (
            not stat.S_ISDIR(parent_stat.st_mode)
            or parent_stat.st_uid != os.geteuid() == _OWNER_UID
            or stat.S_IMODE(parent_stat.st_mode) != 0o755
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")
        parent_fd = os.open(parent, flags)
        opened_parent = os.fstat(parent_fd)
        if (opened_parent.st_dev, opened_parent.st_ino) != (
            parent_stat.st_dev, parent_stat.st_ino
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")
        try:
            os.mkdir("v064-public-ci-r3", 0o700, dir_fd=parent_fd)
            _fsync(parent_fd)
        except FileExistsError:
            pass
        root_fd = os.open("v064-public-ci-r3", flags, dir_fd=parent_fd)
        opened_root = os.fstat(root_fd)
        if not _trusted_directory(opened_root, 0o700):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")
        _validate_root(root_fd, opened_root)
        completed = True
        return root_fd, opened_root
    except ValueError as error:
        primary = error
        raise
    except OSError as error:
        mapped = ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID")
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        close_error = None
        if parent_fd is not None:
            try:
                _close_preserving(parent_fd, primary)
            except BaseException as error:
                close_error = error
        if root_fd is not None and (not completed or close_error is not None):
            _close_preserving(root_fd, primary or close_error)
        if close_error is not None:
            raise close_error


def _read_named(root_fd: int, name: str, expected: bytes) -> bytes:
    flags = os.O_RDONLY | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK")
    descriptor = None
    primary = None
    try:
        descriptor = os.open(name, flags, dir_fd=root_fd)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid() == _OWNER_UID
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != len(expected)
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED")
        body = _read_descriptor(descriptor, opened.st_size)
        attached = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        after = os.fstat(descriptor)
        if (
            (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino)
            or (after.st_size, after.st_mtime_ns, after.st_ctime_ns) !=
            (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            or body != expected
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED")
        return body
    except ValueError as error:
        primary = error
        raise
    except OSError as error:
        mapped = ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED")
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_preserving(descriptor, primary)


def _create_staging(root_fd: int, final_name: str, body: bytes) -> str:
    digest = hashlib.sha256(body).hexdigest()
    name = "%s%s-%s-%s.staging" % (
        _STAGING_PREFIX, final_name, digest, secrets.token_hex(16)
    )
    descriptor = None
    primary = None
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | _required_flag("O_NOFOLLOW"),
            0o600,
            dir_fd=root_fd,
        )
        _write_all(descriptor, body)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _read_descriptor(descriptor, len(body)) != body:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED")
        _fsync(descriptor)
        opened = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid() == _OWNER_UID
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != len(body)
            or (opened.st_dev, opened.st_ino) != (attached.st_dev, attached.st_ino)
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_UNTRUSTED")
        return name
    except ValueError as error:
        primary = error
        raise
    except OSError as error:
        mapped = ValueError("V064_PUBLIC_CI_R3_EVIDENCE_IO_FAILED")
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_preserving(descriptor, primary)


def _recover_staging(root_fd: int, name: str, body: bytes) -> None:
    descriptor = None
    primary = None
    try:
        descriptor = os.open(
            name,
            os.O_RDWR | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK"),
            dir_fd=root_fd,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid() == _OWNER_UID
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size > len(body)
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        prefix = _read_descriptor(descriptor, opened.st_size)
        if prefix != body[: opened.st_size]:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        if opened.st_size < len(body):
            os.lseek(descriptor, 0, os.SEEK_END)
            _write_all(descriptor, body[opened.st_size :])
        os.lseek(descriptor, 0, os.SEEK_SET)
        if _read_descriptor(descriptor, len(body)) != body:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        _fsync(descriptor)
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(after.st_mode)
            or after.st_uid != os.geteuid() == _OWNER_UID
            or stat.S_IMODE(after.st_mode) != 0o600
            or after.st_nlink != 1
            or after.st_size != len(body)
            or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
    except ValueError as error:
        primary = error
        raise
    except OSError as error:
        mapped = ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        primary = mapped
        raise mapped from error
    except BaseException as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_preserving(descriptor, primary)


def _staging_inventory(root_fd: int, prepared: Mapping[str, bytes]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    try:
        names = os.listdir(root_fd)
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_ROOT_INVALID") from error
    for name in names:
        if name in _EVIDENCE_NAMES:
            continue
        if not name.startswith(_STAGING_PREFIX):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        match = _STAGING_RE.fullmatch(name)
        if match is None:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        final_name = match.group("final")
        body = prepared[final_name]
        if match.group("digest") != hashlib.sha256(body).hexdigest():
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        if final_name in result:
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        _recover_staging(root_fd, name, body)
        result[final_name] = name
    return result


def _publish_evidence(prepared: Mapping[str, bytes]) -> Dict[str, Any]:
    if (
        not isinstance(prepared, Mapping)
        or tuple(prepared) != _EVIDENCE_NAMES
        or any(
            not isinstance(prepared[name], bytes)
            or not 0 < len(prepared[name]) <= _MAX_EVIDENCE_BYTES
            for name in _EVIDENCE_NAMES
        )
    ):
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_INVALID")
    if any(
        not _canonical_json_bytes(prepared[name])
        for name in (
            "v064-public-ci-r3-run-api-v1.json",
            "v064-public-ci-r3-jobs-api-v1.json",
            "v064-public-ci-r3-acquisition-transcript-v1.json",
            "v064-public-ci-r3-witness-v1.json",
        )
    ):
        raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_INVALID")
    for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"):
        _required_flag(flag)
    root_fd = None
    primary = None
    try:
        root_fd, identity = _open_artifact_root()
        _acquire_ceremony_lock(root_fd)
        staging = _staging_inventory(root_fd, prepared)
        missing = []
        existing = []
        for name in _EVIDENCE_NAMES:
            try:
                os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            except FileNotFoundError:
                missing.append(name)
                continue
            _read_named(root_fd, name, prepared[name])
            existing.append(name)
            if name in staging:
                raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        for name in missing:
            if name not in staging:
                staging[name] = _create_staging(root_fd, name, prepared[name])
        _validate_root(root_fd, identity)
        for name in missing:
            _atomic_no_replace(root_fd, staging[name], name)
            _fsync(root_fd)
            _read_named(root_fd, name, prepared[name])
            _validate_root(root_fd, identity)
        if _staging_inventory(root_fd, prepared):
            raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_RECOVERY_BLOCKED")
        _fsync(root_fd)
        for name in _EVIDENCE_NAMES:
            _read_named(root_fd, name, prepared[name])
        _validate_root(root_fd, identity)
        return {
            "status": (
                "V064_PUBLIC_CI_R3_EVIDENCE_ALREADY_PUBLISHED"
                if len(existing) == len(_EVIDENCE_NAMES)
                else "V064_PUBLIC_CI_R3_EVIDENCE_PUBLISHED"
            ),
            "files": {
                name: {
                    "size": len(prepared[name]),
                    "sha256": hashlib.sha256(prepared[name]).hexdigest(),
                }
                for name in _EVIDENCE_NAMES
            },
        }
    except BaseException as error:
        primary = error
        raise
    finally:
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError as error:
                if primary is None:
                    raise ValueError("V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED") from error
                try:
                    setattr(primary, "close_error", "V064_PUBLIC_CI_R3_EVIDENCE_CLOSE_FAILED")
                except BaseException:
                    pass


def _run_id(value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise ValueError("V064_PUBLIC_CI_RUN_ID_INVALID")
    parsed = int(value)
    if parsed < 1 or parsed > (1 << 53) - 1 or str(parsed) != value:
        raise ValueError("V064_PUBLIC_CI_RUN_ID_INVALID")
    return parsed


def _commands(run_id: int) -> Tuple[Tuple[str, ...], ...]:
    value = str(run_id)
    prefix = "repos/%s/actions/runs/%s" % (_REPOSITORY, value)
    return (
        (_GH, "api", prefix, "--jq", _RUN_PROJECTION),
        (_GH, "api", prefix + "/jobs?filter=all&per_page=100", "--jq", _JOBS_PROJECTION),
        (_GH, "run", "view", value, "--repo", _REPOSITORY, "--log"),
    )


def _gh_file_sha256() -> str:
    descriptor = None
    digest = hashlib.sha256()
    try:
        opened_path = os.lstat(_GH)
        if (
            not stat.S_ISREG(opened_path.st_mode)
            or opened_path.st_uid != os.getuid()
            or opened_path.st_nlink != 1
            or stat.S_IMODE(opened_path.st_mode) != 0o755
        ):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if not isinstance(nofollow, int) or not nofollow:
            raise ValueError("V064_PUBLIC_CI_GH_UNSUPPORTED")
        descriptor = os.open(_GH, os.O_RDONLY | nofollow)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (opened_path.st_dev, opened_path.st_ino, opened_path.st_size):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        while True:
            body = os.read(descriptor, 1024 * 1024)
            if not body:
                break
            digest.update(body)
        attached = os.lstat(_GH)
        if (attached.st_dev, attached.st_ino, attached.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("V064_PUBLIC_CI_GH_INVALID")
        return digest.hexdigest()
    except OSError as error:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _verify_gh() -> Dict[str, Any]:
    file_sha256 = _gh_file_sha256()
    if file_sha256 != _GH_SHA256:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    completed = _run_bounded(
        (_GH, "--version"), timeout_seconds=5, max_bytes=4096,
    )
    if completed.returncode or completed.stderr or completed.stdout != _GH_VERSION:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    if _gh_file_sha256() != file_sha256:
        raise ValueError("V064_PUBLIC_CI_GH_INVALID")
    return {
        "path": _GH, "file_sha256": file_sha256,
        "version_size": len(completed.stdout),
        "version_sha256": hashlib.sha256(completed.stdout).hexdigest(),
    }


def _run_bounded(argv, *, timeout_seconds: int, max_bytes: int):
    process = None
    try:
        process = subprocess.Popen(
            argv,
            env=_GH_ENV,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if process.stdout is None or process.stderr is None:
            raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        chunks = {"stdout": [], "stderr": []}
        sizes = {"stdout": 0, "stderr": 0}
        deadline = time.monotonic() + timeout_seconds
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
            events = selector.select(remaining)
            if not events:
                raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
            for key, _mask in events:
                body = os.read(key.fileobj.fileno(), 64 * 1024)
                if not body:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                sizes[name] += len(body)
                if sizes[name] > max_bytes:
                    raise ValueError("V064_PUBLIC_CI_GH_OUTPUT_TOO_LARGE")
                chunks[name].append(body)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED")
        return_code = process.wait(timeout=remaining)
        return subprocess.CompletedProcess(
            argv, return_code, b"".join(chunks["stdout"]),
            b"".join(chunks["stderr"]),
        )
    except ValueError:
        raise
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("V064_PUBLIC_CI_GH_COMMAND_FAILED") from error
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None:
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()


def _capture(run_id: int) -> Dict[str, Any]:
    gh_identity = _verify_gh()
    raw = {}
    raw_stderr = {}
    records = []
    for name, argv in zip(("run_api", "jobs_api", "run_log"), _commands(run_id)):
        if _verify_gh() != gh_identity:
            raise ValueError("V064_PUBLIC_CI_GH_IDENTITY_CHANGED")
        completed = _run_bounded(
            argv, timeout_seconds=60, max_bytes=64 * 1024 * 1024,
        )
        if _verify_gh() != gh_identity:
            raise ValueError("V064_PUBLIC_CI_GH_IDENTITY_CHANGED")
        raw[name] = completed.stdout
        raw_stderr[name] = completed.stderr
        records.append({
            "name": name, "argv": list(argv), "exit_code": completed.returncode,
            "stdout_size": len(completed.stdout),
            "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            "stderr_size": len(completed.stderr),
            "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        })
    return {
        "raw": raw, "raw_stderr": raw_stderr,
        "transcript": {
            "schema_version": "1.0.0", "gh_identity": gh_identity,
            "commands": records,
        },
    }


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser(prog="crypto-quant-v064-public-ci-witness")
    parser.add_argument("--run-id", required=True, type=_run_id)
    arguments = parser.parse_args(tuple(argv))
    result = _capture(arguments.run_id)
    summary = {
        "schema_version": result["transcript"]["schema_version"],
        "commands": result["transcript"]["commands"],
    }
    if not all(item["exit_code"] == 0 for item in summary["commands"]) or any(
        result["raw_stderr"][name]
        for name in ("run_api", "jobs_api", "run_log")
    ):
        sys.stdout.write(canonical_json(summary) + "\n")
        return 2
    from .v064_public_ci_bundle import load_v064_public_ci_bundle_manifest
    from .v064_public_ci_witness import derive_v064_public_ci_witness

    bundle = load_v064_public_ci_bundle_manifest(_PUBLIC_CANDIDATE_MANIFEST)
    witness = derive_v064_public_ci_witness(
        bundle=bundle,
        run_bytes=result["raw"]["run_api"],
        jobs_bytes=result["raw"]["jobs_api"],
        log_bytes=result["raw"]["run_log"],
        transcript=result["transcript"],
        private_repository=_PRIVATE_REPOSITORY,
    )
    prepared = {
        "v064-public-ci-r3-run-api-v1.json": result["raw"]["run_api"],
        "v064-public-ci-r3-jobs-api-v1.json": result["raw"]["jobs_api"],
        "v064-public-ci-r3-run-log-v1.txt": result["raw"]["run_log"],
        "v064-public-ci-r3-acquisition-transcript-v1.json": (
            canonical_json(result["transcript"]).encode("utf-8") + b"\n"
        ),
        "v064-public-ci-r3-witness-v1.json": (
            canonical_json(witness).encode("utf-8") + b"\n"
        ),
    }
    publication = _publish_evidence(prepared)
    sys.stdout.write(canonical_json(publication) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
