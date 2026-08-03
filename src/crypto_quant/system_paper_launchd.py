"""Release-bound, non-installing System Paper LaunchAgent contract."""

import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .system_paper_evidence import SystemPaperEvidenceError, publish_owner_exact
from .system_paper_plan import build_system_paper_plan
from .system_paper_scheduler import SystemPaperSchedulePolicy


_SCHEMA = "system-paper-launchd-contract-v1.schema.json"
_LABEL = "local.crypto-quant.system-paper-v1"
_TIMEZONE = "Asia/Shanghai"
_HOURS = (0, 4, 8, 12, 16, 20)
_MINUTE = 5
_RELEASE_TAG = "v0.58.0"
_RELEASE_VERSION = "0.58.0"
_MANIFEST_VERSION = "1.52.0"
_FOUNDATION_TAG = "v0.57.0"
_FOUNDATION_COMMIT = "6b103a5d962ca53c470f08573418be73929b63a7"
_FOUNDATION_PACKAGE_VERSION = "0.57.0"
_FOUNDATION_MANIFEST_VERSION = "1.51.0"
_FOUNDATION_TREE_HASH = (
    "2f0e0b9b23db0338f8aee0a743fa54b3cc63459860d8b34d5385ffbf499141f3"
)
_FOUNDATION_MANIFEST_HASH = (
    "3a25f58a7ad715a937aa8a95a9b65ca7965b837df05f791ddcea1355239beada"
)
_FOUNDATION_MANIFEST_FILE_SHA256 = (
    "f926a034fda40e036682d353e541ad3dddbd43248e5bcf74446124db400568a6"
)
_ORIGINS = frozenset(
    (
        "https://github.com/cjl308868584-lang/crypto-quant-core.git",
        "git@github.com:cjl308868584-lang/crypto-quant-core.git",
    )
)
_MANIFEST_PATH = "config/evaluator-build-manifest-v1.json"
_MAX_FILE_BYTES = 8 * 1024 * 1024
_MAX_TREE_BYTES = 128 * 1024 * 1024
_MAX_FILES = 2000
_WARNINGS = (
    "SYSTEM_PAPER_NOT_INSTALLED",
    "PREFLIGHT_INSTALL_AND_FIRST_NATURAL_SLOT_RECEIPTS_REQUIRED",
    "PUBLIC_MARKET_DATA_ONLY",
    "NO_PROFITABILITY_OR_LIVE_TRADING_CLAIM",
)


class SystemPaperLaunchdError(ValueError):
    """The release, snapshot, path, plist, or contract failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperLaunchdError(
                "SYSTEM_PAPER_LAUNCHD_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_TIME_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_TIME_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_TIME_INVALID")
    rendered = utc_datetime(parsed)
    if isinstance(value, str) and rendered != value:
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_TIME_INVALID")
    return rendered


def _strict_json(data: bytes, reason: str) -> Mapping[str, Any]:
    if not isinstance(data, bytes) or not data or len(data) > _MAX_FILE_BYTES:
        raise SystemPaperLaunchdError(reason)

    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise SystemPaperLaunchdError(reason)
            value[key] = item
        return value

    def reject_number(_value):
        raise SystemPaperLaunchdError(reason)

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except SystemPaperLaunchdError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperLaunchdError(reason) from error
    if not isinstance(value, Mapping):
        raise SystemPaperLaunchdError(reason)
    return value


def _canonical_contract(data: bytes) -> Mapping[str, Any]:
    value = _strict_json(data, "SYSTEM_PAPER_LAUNCHD_CONTRACT_READ_INVALID")
    if canonical_json(value).encode("utf-8") != data:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_CONTRACT_READ_INVALID"
        )
    return value


def _no_symlink_ancestors(path: Path, reason: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            entry = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise SystemPaperLaunchdError(reason) from error
        if stat.S_ISLNK(entry.st_mode):
            raise SystemPaperLaunchdError(reason)


def _absolute(value: object, reason: str) -> Path:
    if not isinstance(value, (str, Path)) or "\x00" in str(value):
        raise SystemPaperLaunchdError(reason)
    path = Path(value).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise SystemPaperLaunchdError(reason)
    _no_symlink_ancestors(path, reason)
    return path


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _validate_isolation(repository: Path, runtime: Path, output: Path) -> None:
    values = (runtime, output)
    for path in values:
        lowered = str(path).lower()
        if (
            "challenger" in lowered
            or path == Path("/tmp")
            or _is_within(path, Path("/tmp"))
            or path == Path("/private/tmp")
            or _is_within(path, Path("/private/tmp"))
            or _is_within(path, repository)
            or _is_within(repository, path)
        ):
            raise SystemPaperLaunchdError(
                "SYSTEM_PAPER_LAUNCHD_PATH_ISOLATION_INVALID"
            )
    if (
        runtime == output
        or _is_within(runtime, output)
        or _is_within(output, runtime)
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PATH_ISOLATION_INVALID"
        )


def _validate_repository(path: Path) -> Path:
    try:
        resolved = path.resolve(strict=True)
        entry = path.lstat()
    except OSError as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_REPOSITORY_INVALID"
        ) from error
    if (
        resolved != path
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_REPOSITORY_INVALID"
        )
    return resolved


def _validate_python(path: Path) -> Path:
    try:
        entry = path.stat()
    except OSError as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PYTHON_INVALID"
        ) from error
    if not stat.S_ISREG(entry.st_mode) or not os.access(path, os.X_OK):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PYTHON_INVALID"
        )
    return path


def _secure_root(path: Path, reason: str) -> Path:
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
        resolved = path.resolve(strict=True)
        entry = path.lstat()
    except OSError as error:
        raise SystemPaperLaunchdError(reason) from error
    if (
        resolved != path
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        raise SystemPaperLaunchdError(reason)
    return path


def _secure_file(path: Path, reason: str, *, max_bytes: int = _MAX_FILE_BYTES) -> Path:
    try:
        if not path.is_absolute() or path.is_symlink():
            raise ValueError
        resolved = path.resolve(strict=True)
        entry = path.lstat()
        if (
            resolved != path
            or not stat.S_ISREG(entry.st_mode)
            or entry.st_uid != os.getuid()
            or entry.st_nlink != 1
            or stat.S_IMODE(entry.st_mode) != 0o600
            or entry.st_size <= 0
            or entry.st_size > max_bytes
        ):
            raise ValueError
        return path
    except (OSError, ValueError) as error:
        raise SystemPaperLaunchdError(reason) from error


def _existing_owner_directory(path: Path, reason: str) -> None:
    try:
        _no_symlink_ancestors(path, reason)
        entry = path.lstat()
    except OSError as error:
        raise SystemPaperLaunchdError(reason) from error
    if (
        not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        raise SystemPaperLaunchdError(reason)


def _default_command_runner(argv, *, cwd=None, env=None):
    return subprocess.run(
        tuple(argv),
        cwd=None if cwd is None else str(cwd),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run(command_runner, argv: Sequence[str], repository: Path, *, env=None) -> str:
    try:
        result = command_runner(tuple(argv), cwd=repository, env=env)
    except Exception as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_RELEASE_COMMAND_FAILED"
        ) from error
    if (
        isinstance(getattr(result, "returncode", None), bool)
        or getattr(result, "returncode", None) != 0
        or not isinstance(getattr(result, "stdout", None), str)
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_RELEASE_COMMAND_FAILED"
        )
    return result.stdout


def _git_release(repository: Path, command_runner) -> Dict[str, str]:
    if _run(command_runner, ("git", "status", "--porcelain=v1"), repository):
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_RELEASE_DIRTY")
    head = _run(command_runner, ("git", "rev-parse", "HEAD"), repository).strip()
    tag_type = _run(
        command_runner, ("git", "cat-file", "-t", _RELEASE_TAG), repository
    ).strip()
    release_commit = _run(
        command_runner,
        ("git", "rev-parse", f"{_RELEASE_TAG}^{{}}"),
        repository,
    ).strip()
    foundation_commit = _run(
        command_runner,
        ("git", "rev-parse", f"{_FOUNDATION_TAG}^{{}}"),
        repository,
    ).strip()
    _run(
        command_runner,
        ("git", "merge-base", "--is-ancestor", _FOUNDATION_TAG, "HEAD"),
        repository,
    )
    origin = _run(
        command_runner, ("git", "remote", "get-url", "origin"), repository
    ).strip()
    remote = _run(
        command_runner,
        ("git", "ls-remote", "origin", "refs/heads/main"),
        repository,
    ).strip()
    remote_commit = remote.split("\t", 1)[0] if "\t" in remote else ""
    if (
        not re.fullmatch(r"[0-9a-f]{40}", head)
        or tag_type != "tag"
        or release_commit != head
        or foundation_commit != _FOUNDATION_COMMIT
        or origin not in _ORIGINS
        or remote_commit != head
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_RELEASE_IDENTITY_INVALID"
        )
    return {
        "release_tag": _RELEASE_TAG,
        "release_commit": head,
        "origin": origin,
        "remote_main_commit": remote_commit,
    }


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


def _source_file(repository: Path, relative: str):
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != relative
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SOURCE_INVENTORY_INVALID"
        )
    path = repository / candidate
    try:
        before = path.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_size <= 0
            or before.st_size > _MAX_FILE_BYTES
        ):
            raise ValueError
        body = path.read_bytes()
        after = path.lstat()
        if _stat_identity(before) != _stat_identity(after) or len(body) != before.st_size:
            raise ValueError
    except (OSError, ValueError) as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SOURCE_INVALID"
        ) from error
    return path, body, _stat_identity(after)


def _package_version(data_by_path: Mapping[str, bytes]) -> str:
    patterns = {
        "pyproject.toml": r'^version = "([0-9]+\.[0-9]+\.[0-9]+)"$',
        "setup.py": r'version="([0-9]+\.[0-9]+\.[0-9]+)"',
        "src/crypto_quant/__init__.py": r'__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"',
    }
    values = []
    try:
        for relative, pattern in patterns.items():
            match = re.search(
                pattern,
                data_by_path[relative].decode("utf-8"),
                flags=re.MULTILINE,
            )
            if match is None:
                raise ValueError
            values.append(match.group(1))
    except (KeyError, UnicodeDecodeError, ValueError) as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PACKAGE_VERSION_INVALID"
        ) from error
    if len(set(values)) != 1 or values[0] != _RELEASE_VERSION:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PACKAGE_VERSION_INVALID"
        )
    return values[0]


def _read_release_source(repository: Path):
    manifest_path, manifest_bytes, manifest_identity = _source_file(
        repository, _MANIFEST_PATH
    )
    manifest = dict(
        _strict_json(
            manifest_bytes,
            "SYSTEM_PAPER_LAUNCHD_BUILD_MANIFEST_INVALID",
        )
    )
    try:
        schema = json.loads(
            (repository / "config" / "evaluator-build-manifest-v1.schema.json")
            .read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        if tuple(Draft202012Validator(schema).iter_errors(manifest)):
            raise ValueError
        if manifest.get("manifest_hash") != artifact_self_hash(
            manifest, "manifest_hash"
        ):
            raise ValueError
        file_hashes = dict(manifest["file_hashes"])
        if manifest.get("build_input_tree_hash") != business_hash(file_hashes):
            raise ValueError
        if (
            manifest.get("manifest_version") != _MANIFEST_VERSION
            or manifest.get("package_version") != _RELEASE_VERSION
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_BUILD_MANIFEST_INVALID"
        ) from error
    required = {
        "pyproject.toml",
        "setup.py",
        "requirements.lock",
        "src/crypto_quant/__init__.py",
        "src/crypto_quant/system_paper_runtime_cli.py",
        "src/crypto_quant/system_paper_launchd.py",
        "src/crypto_quant/system_paper_launchd_cli.py",
        "config/evaluator-build-manifest-v1.schema.json",
        "config/system-paper-launchd-contract-v1.schema.json",
        "src/crypto_quant/schemas/system-paper-launchd-contract-v1.schema.json",
    }
    if _MANIFEST_PATH in file_hashes or not required.issubset(file_hashes):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SOURCE_INVENTORY_INVALID"
        )
    records = []
    data_by_path = {}
    identities = {}
    total = 0
    for relative in sorted(file_hashes):
        path, body, identity = _source_file(repository, relative)
        digest = hashlib.sha256(body).hexdigest()
        if digest != file_hashes[relative]:
            raise SystemPaperLaunchdError(
                "SYSTEM_PAPER_LAUNCHD_SOURCE_HASH_MISMATCH"
            )
        records.append(
            {"path": relative, "size_bytes": len(body), "sha256": digest}
        )
        data_by_path[relative] = body
        identities[relative] = (path, identity)
        total += len(body)
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    records.append(
        {
            "path": _MANIFEST_PATH,
            "size_bytes": len(manifest_bytes),
            "sha256": manifest_digest,
        }
    )
    data_by_path[_MANIFEST_PATH] = manifest_bytes
    identities[_MANIFEST_PATH] = (manifest_path, manifest_identity)
    if len(records) > _MAX_FILES or total + len(manifest_bytes) > _MAX_TREE_BYTES:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SOURCE_INVENTORY_INVALID"
        )
    package_version = _package_version(data_by_path)
    return (
        manifest,
        tuple(sorted(records, key=lambda item: item["path"])),
        data_by_path,
        identities,
        package_version,
        manifest_digest,
    )


def _verify_source_unchanged(identities) -> None:
    try:
        for path, expected in identities.values():
            if _stat_identity(path.lstat()) != expected:
                raise ValueError
    except (OSError, ValueError) as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SOURCE_CHANGED"
        ) from error


def _tree_summary(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    values = [dict(item) for item in records]
    return {
        "file_count": len(values),
        "total_bytes": sum(item["size_bytes"] for item in values),
        "tree_hash": business_hash({"files": values}),
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_snapshot_file(path: Path, body: bytes) -> None:
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _verify_snapshot(root: Path, records: Sequence[Mapping[str, Any]]) -> None:
    expected = {item["path"]: dict(item) for item in records}
    actual = {}
    try:
        root_entry = root.lstat()
        if (
            not stat.S_ISDIR(root_entry.st_mode)
            or root_entry.st_uid != os.getuid()
            or stat.S_IMODE(root_entry.st_mode) != 0o700
        ):
            raise ValueError
        for path in root.rglob("*"):
            entry = path.lstat()
            if stat.S_ISLNK(entry.st_mode) or entry.st_uid != os.getuid():
                raise ValueError
            if stat.S_ISDIR(entry.st_mode):
                if stat.S_IMODE(entry.st_mode) != 0o700:
                    raise ValueError
                continue
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_nlink != 1
                or stat.S_IMODE(entry.st_mode) != 0o600
            ):
                raise ValueError
            body = path.read_bytes()
            relative = path.relative_to(root).as_posix()
            actual[relative] = {
                "path": relative,
                "size_bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
    except (OSError, ValueError) as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_INVALID"
        ) from error
    if actual != expected:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_INVALID"
        )


def _write_snapshot(runtime: Path, records, data_by_path, identities):
    summary = _tree_summary(records)
    deployment = _secure_root(
        runtime / "deployment", "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_ROOT_INVALID"
    )
    parent = _secure_root(
        deployment / "system-paper-snapshots",
        "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_ROOT_INVALID",
    )
    final = parent / summary["tree_hash"]
    if final.exists() or final.is_symlink():
        _verify_source_unchanged(identities)
        _verify_snapshot(final, records)
        return final, False, summary
    temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=str(parent)))
    installed = False
    try:
        os.chmod(temporary, 0o700)
        for item in records:
            destination = temporary / item["path"]
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(destination.parent, 0o700)
            _write_snapshot_file(destination, data_by_path[item["path"]])
        for directory in sorted(
            (item for item in temporary.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(temporary)
        _verify_source_unchanged(identities)
        _verify_snapshot(temporary, records)
        os.rename(temporary, final)
        installed = True
        _fsync_directory(parent)
        _verify_snapshot(final, records)
        return final, True, summary
    except SystemPaperLaunchdError:
        raise
    except OSError as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_WRITE_FAILED"
        ) from error
    finally:
        if not installed and temporary.exists():
            shutil.rmtree(temporary)


def _verify_snapshot_import(
    snapshot: Path,
    python: Path,
    command_runner,
    records: Sequence[Mapping[str, Any]],
) -> None:
    environment = {
        "PYTHONPATH": str(snapshot / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C",
        "LC_ALL": "C",
    }
    output = _run(
        command_runner,
        (
            str(python),
            "-c",
            "import crypto_quant.system_paper_runtime_cli; print('SYSTEM_PAPER_SNAPSHOT_IMPORT_OK')",
        ),
        snapshot,
        env=environment,
    )
    if output.strip() != "SYSTEM_PAPER_SNAPSHOT_IMPORT_OK":
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_SNAPSHOT_IMPORT_INVALID"
        )
    _verify_snapshot(snapshot, records)


def _timezone_link_target() -> str:
    return os.readlink("/etc/localtime")


def _verify_timezone() -> Dict[str, Any]:
    try:
        target = _timezone_link_target()
        local = time.localtime()
    except OSError as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_TIMEZONE_INVALID"
        ) from error
    if (
        not target.endswith("/" + _TIMEZONE)
        or getattr(local, "tm_gmtoff", None) != 28800
        or local.tm_isdst != 0
    ):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_TIMEZONE_INVALID"
        )
    return {
        "iana_name": _TIMEZONE,
        "utc_offset_seconds": 28800,
        "daylight_saving_time_active": False,
    }


def _program_arguments(python: Path, runtime: Path) -> Tuple[str, ...]:
    return (
        str(python),
        "-m",
        "crypto_quant.system_paper_runtime_cli",
        "--state-path",
        str(runtime / "state" / "system-paper.sqlite"),
        "--output-root",
        str(runtime / "artifacts"),
    )


def _plist_payload(snapshot: Path, runtime: Path, python: Path) -> Dict[str, Any]:
    return {
        "Label": _LABEL,
        "ProgramArguments": list(_program_arguments(python, runtime)),
        "WorkingDirectory": str(snapshot),
        "EnvironmentVariables": {"PYTHONPATH": str(snapshot / "src")},
        "StartCalendarInterval": [
            {"Hour": hour, "Minute": _MINUTE} for hour in _HOURS
        ],
        "RunAtLoad": True,
        "ProcessType": "Background",
        "ThrottleInterval": 60,
        "LowPriorityIO": True,
        "AbandonProcessGroup": True,
        "Umask": 0o077,
        "StandardOutPath": str(runtime / "log" / "system-paper.stdout.log"),
        "StandardErrorPath": str(runtime / "log" / "system-paper.stderr.log"),
    }


def _plist_bytes(payload: Mapping[str, Any]) -> bytes:
    return plistlib.dumps(dict(payload), fmt=plistlib.FMT_XML, sort_keys=True)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _release_payload(git_release, manifest, package_version, manifest_digest):
    return {
        "foundation_tag": _FOUNDATION_TAG,
        "foundation_commit": _FOUNDATION_COMMIT,
        "foundation_package_version": _FOUNDATION_PACKAGE_VERSION,
        "foundation_manifest_version": _FOUNDATION_MANIFEST_VERSION,
        "foundation_build_input_tree_hash": _FOUNDATION_TREE_HASH,
        "foundation_manifest_hash": _FOUNDATION_MANIFEST_HASH,
        "foundation_manifest_file_sha256": _FOUNDATION_MANIFEST_FILE_SHA256,
        **git_release,
        "package_version": package_version,
        "manifest_version": manifest["manifest_version"],
        "build_input_tree_hash": manifest["build_input_tree_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "manifest_file_sha256": manifest_digest,
    }


def _contract(
    *,
    created_at,
    runtime,
    python,
    snapshot,
    records,
    summary,
    release,
    timezone_payload,
    plist_bytes,
):
    plan = build_system_paper_plan()
    policy = SystemPaperSchedulePolicy.create(plan)
    plist_hash = hashlib.sha256(plist_bytes).hexdigest()
    identity = {
        "release_commit": release["release_commit"],
        "snapshot_tree_hash": summary["tree_hash"],
        "runtime_root": str(runtime),
        "python_executable": str(python),
        "launchd_plist_sha256": plist_hash,
    }
    value = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "contract_id": stable_id("system_paper_launchd_contract", identity),
        "contract_hash": "0" * 64,
        "created_at": _utc(created_at),
        "platform": "MACOS_LAUNCHD",
        "label": _LABEL,
        "release": release,
        "plan_hash": plan["plan_hash"],
        "schedule_policy_hash": policy.schedule_policy_hash,
        "execution_snapshot": {
            "repository_root": str(snapshot),
            **summary,
            "files": [dict(item) for item in records],
        },
        "runtime_root": str(runtime),
        "root_paths": {
            "runtime": str(runtime),
            "state": str(runtime / "state"),
            "log": str(runtime / "log"),
            "artifacts": str(runtime / "artifacts"),
            "deployment": str(runtime / "deployment"),
            "preflight_receipts": str(runtime / "preflight-receipts"),
            "install_receipts": str(runtime / "install-receipts"),
            "start_receipts": str(runtime / "start-receipts"),
        },
        "python_executable": str(python),
        "system_timezone": timezone_payload,
        "cadence": {
            "time_basis": "SYSTEM_LOCAL_ASIA_SHANGHAI_UTC_PLUS_08",
            "utc_slot_hours": list(_HOURS),
            "local_launch_hours": list(_HOURS),
            "minute": _MINUTE,
            "run_at_load": True,
        },
        "program_arguments": list(_program_arguments(python, runtime)),
        "environment_variable_names": ["PYTHONPATH"],
        "launchd_plist_sha256": plist_hash,
        "installation_status": "NOT_INSTALLED_NO_EXTERNAL_RECEIPT",
        "security_boundary": {
            "production_activation_enabled": False,
            "launchctl_invoked": False,
            "runtime_invocation_count": 0,
            "network_request_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        },
        "warnings": list(_WARNINGS),
    }
    value["contract_hash"] = artifact_self_hash(value, "contract_hash")
    if tuple(_validator().iter_errors(value)):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_CONTRACT_SCHEMA_INVALID"
        )
    return value


def system_paper_launchd_contract_trust_hash(contract: Mapping[str, Any]) -> str:
    try:
        return business_hash(
            {
                "attestation_type": "SYSTEM_PAPER_LAUNCHD_CONTRACT_ATTESTATION",
                "contract_id": contract["contract_id"],
                "contract_hash": contract["contract_hash"],
                "release_commit": contract["release"]["release_commit"],
                "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
                "launchd_plist_sha256": contract["launchd_plist_sha256"],
            }
        )
    except (KeyError, TypeError):
        return ""


def _contract_reasons(contract: Mapping[str, Any], plist_bytes: bytes) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(contract)):
            reasons.append("SYSTEM_PAPER_LAUNCHD_CONTRACT_SCHEMA_INVALID")
        if contract.get("contract_hash") != artifact_self_hash(
            contract, "contract_hash"
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_CONTRACT_HASH_MISMATCH")
        snapshot = contract["execution_snapshot"]
        records = tuple(snapshot["files"])
        summary = _tree_summary(records)
        if snapshot != {
            "repository_root": snapshot["repository_root"],
            **summary,
            "files": list(records),
        }:
            reasons.append("SYSTEM_PAPER_LAUNCHD_SNAPSHOT_SUMMARY_MISMATCH")
        snapshot_root = Path(snapshot["repository_root"])
        _verify_snapshot(snapshot_root, records)
        manifest = dict(
            _strict_json(
                (snapshot_root / _MANIFEST_PATH).read_bytes(),
                "SYSTEM_PAPER_LAUNCHD_BUILD_MANIFEST_INVALID",
            )
        )
        release = contract["release"]
        runtime_root = Path(contract["runtime_root"])
        expected_root_paths = {
            "runtime": str(runtime_root),
            "state": str(runtime_root / "state"),
            "log": str(runtime_root / "log"),
            "artifacts": str(runtime_root / "artifacts"),
            "deployment": str(runtime_root / "deployment"),
            "preflight_receipts": str(runtime_root / "preflight-receipts"),
            "install_receipts": str(runtime_root / "install-receipts"),
            "start_receipts": str(runtime_root / "start-receipts"),
        }
        if contract.get("root_paths") != expected_root_paths:
            reasons.append("SYSTEM_PAPER_LAUNCHD_ROOT_BINDING_MISMATCH")
        expected_snapshot_parent = (
            runtime_root / "deployment" / "system-paper-snapshots"
        )
        if (
            snapshot_root.parent != expected_snapshot_parent
            or snapshot_root.name != summary["tree_hash"]
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_SNAPSHOT_PATH_MISMATCH")
        for directory in (
            runtime_root,
            runtime_root / "state",
            runtime_root / "log",
            runtime_root / "artifacts",
            runtime_root / "deployment",
            expected_snapshot_parent,
        ):
            _existing_owner_directory(
                directory, "SYSTEM_PAPER_LAUNCHD_RUNTIME_ROOT_INVALID"
            )
        expected_release_constants = {
            "foundation_tag": _FOUNDATION_TAG,
            "foundation_commit": _FOUNDATION_COMMIT,
            "foundation_package_version": _FOUNDATION_PACKAGE_VERSION,
            "foundation_manifest_version": _FOUNDATION_MANIFEST_VERSION,
            "foundation_build_input_tree_hash": _FOUNDATION_TREE_HASH,
            "foundation_manifest_hash": _FOUNDATION_MANIFEST_HASH,
            "foundation_manifest_file_sha256": _FOUNDATION_MANIFEST_FILE_SHA256,
            "release_tag": _RELEASE_TAG,
            "package_version": _RELEASE_VERSION,
            "manifest_version": _MANIFEST_VERSION,
        }
        if any(release.get(key) != value for key, value in expected_release_constants.items()):
            reasons.append("SYSTEM_PAPER_LAUNCHD_RELEASE_BINDING_MISMATCH")
        if release.get("release_commit") != release.get("remote_main_commit"):
            reasons.append("SYSTEM_PAPER_LAUNCHD_RELEASE_BINDING_MISMATCH")
        record_hashes = {item["path"]: item["sha256"] for item in records}
        expected_record_paths = set(manifest["file_hashes"]) | {_MANIFEST_PATH}
        if (
            len(record_hashes) != len(records)
            or [item["path"] for item in records] != sorted(record_hashes)
            or set(record_hashes) != expected_record_paths
            or any(
                record_hashes.get(relative) != digest
                for relative, digest in manifest["file_hashes"].items()
            )
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_RELEASE_BINDING_MISMATCH")
        snapshot_data = {
            relative: (snapshot_root / relative).read_bytes()
            for relative in (
                "pyproject.toml",
                "setup.py",
                "src/crypto_quant/__init__.py",
            )
        }
        if _package_version(snapshot_data) != release.get("package_version"):
            reasons.append("SYSTEM_PAPER_LAUNCHD_RELEASE_BINDING_MISMATCH")
        if (
            manifest.get("manifest_hash") != release.get("manifest_hash")
            or manifest.get("manifest_hash")
            != artifact_self_hash(manifest, "manifest_hash")
            or manifest.get("build_input_tree_hash")
            != release.get("build_input_tree_hash")
            or manifest.get("build_input_tree_hash")
            != business_hash(manifest.get("file_hashes"))
            or hashlib.sha256(
                (snapshot_root / _MANIFEST_PATH).read_bytes()
            ).hexdigest()
            != release.get("manifest_file_sha256")
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_RELEASE_BINDING_MISMATCH")
        expected_plist = _plist_payload(
            snapshot_root,
            runtime_root,
            Path(contract["python_executable"]),
        )
        _validate_python(
            _absolute(
                contract["python_executable"],
                "SYSTEM_PAPER_LAUNCHD_PYTHON_INVALID",
            )
        )
        if (
            hashlib.sha256(plist_bytes).hexdigest()
            != contract["launchd_plist_sha256"]
            or plistlib.loads(plist_bytes) != expected_plist
            or _plist_bytes(expected_plist) != plist_bytes
            or contract["program_arguments"]
            != list(expected_plist["ProgramArguments"])
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_PLIST_REPLAY_MISMATCH")
        expected_id = stable_id(
            "system_paper_launchd_contract",
            {
                "release_commit": release["release_commit"],
                "snapshot_tree_hash": summary["tree_hash"],
                "runtime_root": contract["runtime_root"],
                "python_executable": contract["python_executable"],
                "launchd_plist_sha256": contract["launchd_plist_sha256"],
            },
        )
        if contract.get("contract_id") != expected_id:
            reasons.append("SYSTEM_PAPER_LAUNCHD_CONTRACT_ID_MISMATCH")
        if contract.get("warnings") != list(_WARNINGS):
            reasons.append("SYSTEM_PAPER_LAUNCHD_WARNINGS_MISMATCH")
        plan = build_system_paper_plan()
        if (
            contract.get("plan_hash") != plan["plan_hash"]
            or contract.get("schedule_policy_hash")
            != SystemPaperSchedulePolicy.create(plan).schedule_policy_hash
        ):
            reasons.append("SYSTEM_PAPER_LAUNCHD_PLAN_BINDING_MISMATCH")
    except (
        SystemPaperLaunchdError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        plistlib.InvalidFileException,
    ):
        reasons.append("SYSTEM_PAPER_LAUNCHD_CONTRACT_REPLAY_INVALID")
    return tuple(sorted(set(reasons)))


def publish_system_paper_launchd_contract(
    *,
    output_root: Path,
    repository_root: Path,
    runtime_root: Path,
    python_executable: Path,
    clock=None,
    _command_runner=None,
) -> Mapping[str, Any]:
    repository = _validate_repository(
        _absolute(repository_root, "SYSTEM_PAPER_LAUNCHD_REPOSITORY_INVALID")
    )
    runtime = _absolute(runtime_root, "SYSTEM_PAPER_LAUNCHD_RUNTIME_ROOT_INVALID")
    output = _absolute(output_root, "SYSTEM_PAPER_LAUNCHD_OUTPUT_ROOT_INVALID")
    python = _validate_python(
        _absolute(python_executable, "SYSTEM_PAPER_LAUNCHD_PYTHON_INVALID")
    )
    _validate_isolation(repository, runtime, output)
    timezone_payload = _verify_timezone()
    runner = _command_runner or _default_command_runner
    git_release = _git_release(repository, runner)
    (
        manifest,
        records,
        data_by_path,
        identities,
        package_version,
        manifest_digest,
    ) = _read_release_source(repository)
    runtime = _secure_root(runtime, "SYSTEM_PAPER_LAUNCHD_RUNTIME_ROOT_INVALID")
    for name in ("state", "log", "artifacts"):
        _secure_root(
            runtime / name, "SYSTEM_PAPER_LAUNCHD_RUNTIME_ROOT_INVALID"
        )
    snapshot, snapshot_created, summary = _write_snapshot(
        runtime, records, data_by_path, identities
    )
    try:
        _verify_snapshot_import(snapshot, python, runner, records)
        if _git_release(repository, runner) != git_release:
            raise SystemPaperLaunchdError(
                "SYSTEM_PAPER_LAUNCHD_RELEASE_CHANGED"
            )
    except Exception:
        if snapshot_created and snapshot.exists():
            shutil.rmtree(snapshot)
        raise
    release = _release_payload(
        git_release, manifest, package_version, manifest_digest
    )
    plist_payload = _plist_payload(snapshot, runtime, python)
    plist_bytes = _plist_bytes(plist_payload)
    created_at = (clock or (lambda: utc_datetime(datetime.now(timezone.utc))))()
    contract = _contract(
        created_at=created_at,
        runtime=runtime,
        python=python,
        snapshot=snapshot,
        records=records,
        summary=summary,
        release=release,
        timezone_payload=timezone_payload,
        plist_bytes=plist_bytes,
    )
    if _contract_reasons(contract, plist_bytes):
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_CONTRACT_INVALID")
    output = _secure_root(output, "SYSTEM_PAPER_LAUNCHD_OUTPUT_ROOT_INVALID")
    directory = _secure_root(
        output / "system-paper-deployment",
        "SYSTEM_PAPER_LAUNCHD_OUTPUT_ROOT_INVALID",
    )
    contract_path = directory / "system-paper-launchd-contract.json"
    plist_path = directory / f"{_LABEL}.plist"
    expected_names = {contract_path.name, plist_path.name}
    if any(item.name not in expected_names for item in directory.iterdir()):
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_OUTPUT_INVENTORY_INVALID"
        )
    try:
        publish_owner_exact(
            contract_path, canonical_json(contract).encode("utf-8")
        )
        publish_owner_exact(plist_path, plist_bytes)
    except SystemPaperEvidenceError as error:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_PUBLISH_CONFLICT"
        ) from error
    trust_hash = system_paper_launchd_contract_trust_hash(contract)
    return {
        "outcome": "GENERATED_NOT_INSTALLED",
        "contract_path": str(contract_path),
        "plist_path": str(plist_path),
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": trust_hash,
        "launchd_plist_sha256": contract["launchd_plist_sha256"],
        "snapshot_root": str(snapshot),
        "snapshot_tree_hash": summary["tree_hash"],
        "snapshot_created": snapshot_created,
        "installation_status": contract["installation_status"],
        "launchctl_invoked": False,
    }


def load_system_paper_launchd_contract(
    *, contract_path: Path, plist_path: Path, _command_runner=None
) -> Mapping[str, Any]:
    contract_file = _secure_file(
        Path(contract_path), "SYSTEM_PAPER_LAUNCHD_CONTRACT_READ_INVALID"
    )
    plist_file = _secure_file(
        Path(plist_path), "SYSTEM_PAPER_LAUNCHD_PLIST_READ_INVALID"
    )
    if contract_file.parent != plist_file.parent or {
        item.name for item in contract_file.parent.iterdir()
    } != {contract_file.name, plist_file.name}:
        raise SystemPaperLaunchdError(
            "SYSTEM_PAPER_LAUNCHD_OUTPUT_INVENTORY_INVALID"
        )
    contract = _canonical_contract(contract_file.read_bytes())
    plist_bytes = plist_file.read_bytes()
    if _contract_reasons(contract, plist_bytes):
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_CONTRACT_INVALID")
    snapshot = contract["execution_snapshot"]
    _verify_snapshot_import(
        Path(snapshot["repository_root"]),
        Path(contract["python_executable"]),
        _command_runner or _default_command_runner,
        tuple(snapshot["files"]),
    )
    if _contract_reasons(contract, plist_bytes):
        raise SystemPaperLaunchdError("SYSTEM_PAPER_LAUNCHD_CONTRACT_INVALID")
    return contract
