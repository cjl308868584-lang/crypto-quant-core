"""Closed manifest for the bounded v0.64 public Linux CI witness."""

import copy
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json
from .challenger_replacement_supersession_publish import _atomic_no_replace


_SCHEMA = "v064-public-ci-bundle-manifest-v1.schema.json"
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_BASELINE = "df91e19240df14839125608422489adf3b902e76"
_FILES: Tuple[Tuple[str, str, str], ...] = (
    (".github/workflows/ci.yml", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/.github/workflows/ci.yml"),
    (".gitignore", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/.gitignore"),
    ("NOTICE.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/NOTICE.md"),
    ("README.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/README.md"),
    ("SECURITY.md", "PRIVATE_TEMPLATE_BLOB", "public_ci/v064/SECURITY.md"),
    (
        "src/crypto_quant/challenger_replacement_supersession_publish.py",
        "PRIVATE_GIT_BLOB",
        "src/crypto_quant/challenger_replacement_supersession_publish.py",
    ),
    (
        "tests/test_v064_linux_supersession_publish.py",
        "PRIVATE_GIT_BLOB",
        "tests/test_v064_linux_supersession_publish.py",
    ),
)
_SAFETY = {
    "production_activation": False,
    "credentials_present": False,
    "broker_allowed": False,
    "orders_allowed": False,
    "runtime_state_write_allowed": False,
}
_NON_CLAIMS = (
    "NOT_FULL_PROJECT_CI",
    "NOT_PRIVATE_PR_CHECK",
    "NOT_STRATEGY_CORRECTNESS_EVIDENCE",
    "NOT_PROFITABILITY_OR_AI_ADVANTAGE_EVIDENCE",
    "NOT_PAPER_CANARY_OR_LIVE_TRADING_AUTHORIZATION",
)


class V064PublicCiBundleError(ValueError):
    """The bounded public CI bundle failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _git(repository: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ("/usr/bin/git", "-C", str(repository), *arguments),
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_FAILED") from error
    if completed.returncode or completed.stderr:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_FAILED")
    return completed.stdout


def _single_oid(body: bytes) -> str:
    try:
        value = body.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_IDENTITY_INVALID") from error
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_GIT_IDENTITY_INVALID")
    return value


def _blob(repository: Path, commit: str, relative: str) -> Tuple[str, bytes]:
    record = _git(repository, "ls-tree", "-z", commit, "--", relative)
    parts = record.rstrip(b"\0").split(b"\t", 1)
    if len(parts) != 2 or parts[1] != relative.encode("utf-8"):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_SOURCE_ENTRY_INVALID")
    identity = parts[0].split(b" ")
    if len(identity) != 3 or identity[0] != b"100644" or identity[1] != b"blob":
        raise V064PublicCiBundleError("V064_PUBLIC_CI_SOURCE_ENTRY_INVALID")
    oid = _single_oid(identity[2] + b"\n")
    body = _git(repository, "cat-file", "blob", oid)
    if not body or len(body) > _MAX_MANIFEST_BYTES:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_SOURCE_BLOB_INVALID")
    return oid, body


def build_v064_public_ci_bundle_manifest(
    repository: Path, source_commit: str
) -> Dict[str, Any]:
    """Build the external manifest from exact private Git objects."""

    root = Path(repository)
    commit = _single_oid(_git(root, "rev-parse", "%s^{commit}" % source_commit))
    if commit != source_commit:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_SOURCE_COMMIT_INVALID")
    head = _single_oid(_git(root, "rev-parse", "HEAD^{commit}"))
    if commit != head:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_SOURCE_NOT_REVIEWED_HEAD")
    tree = _single_oid(_git(root, "rev-parse", "%s^{tree}" % commit))
    entries = []
    for relative, source_kind, source_relative in _FILES:
        oid, body = _blob(root, commit, source_relative)
        entries.append(
            {
                "path": relative,
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "source_kind": source_kind,
                "source_blob_oid": oid,
            }
        )
    manifest: Dict[str, Any] = {
        "$schema": "./v064-public-ci-bundle-manifest-v1.schema.json",
        "schema_version": "1.0.0",
        "purpose": "V064_LINUX_PORTABILITY_WITNESS_ONLY",
        "source": {
            "private_repository": "cjl308868584-lang/crypto-quant-core",
            "candidate_commit": commit,
            "candidate_tree": tree,
            "private_release_baseline": _BASELINE,
            "object_format": "sha1",
            "historical_billing_blocked_private_pr": {
                "number": 32,
                "run_id": 31436609135,
                "status": "PRIVATE_PR_CI_NOT_EXECUTED_BILLING_BLOCKED",
            },
        },
        "public_repository": "cjl308868584-lang/crypto-quant-v064-public-ci",
        "files": entries,
        "file_set_sha256": business_hash(entries),
        "safety": copy.deepcopy(_SAFETY),
        "non_claims": list(_NON_CLAIMS),
    }
    if tuple(_validator().iter_errors(manifest)):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_SCHEMA_INVALID")
    return manifest


def _read_manifest(path: Path) -> bytes:
    requested = Path(path)
    if not requested.is_absolute():
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID")
    try:
        before = requested.lstat()
    except OSError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) & 0o022
        or not 0 < before.st_size <= _MAX_MANIFEST_BYTES
    ):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int) or not nofollow:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_UNSUPPORTED")
    descriptor = None
    try:
        descriptor = os.open(requested, os.O_RDONLY | nofollow)
        opened = os.fstat(descriptor)
        if (
            (opened.st_dev, opened.st_ino, opened.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) & 0o022
        ):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID")
        chunks = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID")
        return b"".join(chunks)
    except V064PublicCiBundleError:
        raise
    except OSError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_PATH_INVALID") from error
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def load_v064_public_ci_bundle_manifest(path: Path) -> Dict[str, Any]:
    """Load and semantically replay one canonical external manifest."""

    body = _read_manifest(Path(path))
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_JSON_INVALID") from error
    if not isinstance(value, Mapping):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_JSON_INVALID")
    canonical = canonical_json(value).encode("utf-8") + b"\n"
    if body != canonical:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_CANONICAL_BYTES_REQUIRED")
    if tuple(_validator().iter_errors(value)):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_MANIFEST_SCHEMA_INVALID")
    if value["file_set_sha256"] != business_hash(value["files"]):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_FILE_SET_HASH_MISMATCH")
    return copy.deepcopy(dict(value))


def _forbidden_public_bytes(body: bytes, relative_path: str = "") -> bool:
    lowered = body.lower()
    forbidden = (
        b"\x00",
        b"\r",
        b"/users/",
        b"-----begin private key-----",
        b"strategy_result",
        b"economic_result",
        b"production_root",
        b"brokerclient",
        b"order_submission",
        b"credential_access",
    )
    if any(value in lowered for value in forbidden):
        return True
    if re.search(rb"(?:ghp_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,})", lowered):
        return True
    urls = re.findall(rb"https?://[^\s'\"<>]+", lowered)
    allowed_urls = (
        b"https://github.com/security/advisories/new",
    )
    if any(url not in allowed_urls for url in urls):
        return True
    term_scan = lowered
    if relative_path == ".github/workflows/ci.yml":
        term_scan = term_scan.replace(b"\n    strategy:\n", b"\n    matrix-policy:\n")
    if re.search(rb"(?<![a-z0-9_])(strategy|economic|broker|order|credential)(?![a-z0-9_])", term_scan):
        return True
    for token in lowered.replace(b"\n", b" ").split():
        if b"@" in token and b"." in token.split(b"@", 1)[-1]:
            return True
    return False


def _write_all(descriptor: int, body: bytes) -> None:
    view = memoryview(body)
    offset = 0
    while offset < len(view):
        try:
            written = os.write(descriptor, view[offset:])
        except InterruptedError:
            continue
        if written <= 0:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_WRITE_FAILED")
        offset += written


def _write_new_at(parent_descriptor: int, name: str, body: bytes) -> None:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if not isinstance(nofollow, int) or not nofollow:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_UNSUPPORTED")
    descriptor = None
    primary_error = None
    staging_name = ".v064-public-%s.staging" % secrets.token_hex(16)
    try:
        descriptor = os.open(
            staging_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
            0o600,
            dir_fd=parent_descriptor,
        )
        os.fchmod(descriptor, 0o644)
        _write_all(descriptor, body)
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks = []
        remaining = len(body)
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_WRITE_FAILED")
            chunks.append(chunk)
            remaining -= len(chunk)
        if b"".join(chunks) != body:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_WRITE_FAILED")
        os.fsync(descriptor)
        attached = os.stat(staging_name, dir_fd=parent_descriptor, follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (
            (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != os.getuid()
            or stat.S_IMODE(opened.st_mode) != 0o644
            or opened.st_size != len(body)
        ):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_STAGING_UNTRUSTED")
        _atomic_no_replace(parent_descriptor, staging_name, name)
        os.fsync(parent_descriptor)
    except OSError as error:
        mapped = V064PublicCiBundleError("V064_PUBLIC_CI_WRITE_FAILED")
        primary_error = mapped
        raise mapped from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        close_error = None
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                close_error = error
        if close_error is not None:
            if primary_error is not None:
                try:
                    setattr(primary_error, "close_failure", repr(close_error))
                except (AttributeError, TypeError):
                    pass
            else:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_CLOSE_FAILED") from close_error


def _write_new_file(
    path: Path, body: bytes, root_identity: Tuple[Path, Tuple[int, int]] = None
) -> None:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if not isinstance(nofollow, int) or not nofollow or not isinstance(directory, int) or not directory:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_UNSUPPORTED")
    parent_descriptor = None
    primary_error = None
    try:
        if root_identity is not None:
            attached = root_identity[0].lstat()
            if (attached.st_dev, attached.st_ino) != root_identity[1]:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_DESTINATION_REPLACED")
        parent_descriptor = os.open(path.parent, os.O_RDONLY | directory | nofollow)
        _write_new_at(parent_descriptor, path.name, body)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if parent_descriptor is not None:
            try:
                os.close(parent_descriptor)
            except OSError as error:
                if primary_error is None:
                    raise V064PublicCiBundleError("V064_PUBLIC_CI_CLOSE_FAILED") from error
                try:
                    setattr(primary_error, "parent_close_failure", repr(error))
                except (AttributeError, TypeError):
                    pass


def _retained_parent(root_descriptor: int, parts: Tuple[str, ...]) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if not isinstance(nofollow, int) or not nofollow or not isinstance(directory, int) or not directory:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_UNSUPPORTED")
    current = os.dup(root_descriptor)
    try:
        for part in parts:
            created = False
            try:
                os.mkdir(part, 0o700, dir_fd=current)
                created = True
            except FileExistsError:
                pass
            if created:
                os.fsync(current)
            next_descriptor = os.open(
                part, os.O_RDONLY | directory | nofollow, dir_fd=current
            )
            opened = os.fstat(next_descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o700
            ):
                os.close(next_descriptor)
                raise V064PublicCiBundleError("V064_PUBLIC_CI_DIRECTORY_UNTRUSTED")
            os.close(current)
            current = next_descriptor
        return current
    except BaseException:
        os.close(current)
        raise


def stage_v064_public_ci_bundle(
    repository: Path, source_commit: str, destination: Path
) -> Dict[str, Any]:
    """Stage the exact closed public tree without changing the private repository."""

    root = Path(repository)
    target = Path(destination)
    manifest = build_v064_public_ci_bundle_manifest(root, source_commit)
    bodies = {}
    source_paths = {relative: source for relative, _kind, source in _FILES}
    for entry in manifest["files"]:
        oid, body = _blob(root, source_commit, source_paths[entry["path"]])
        if oid != entry["source_blob_oid"] or _forbidden_public_bytes(
            body, entry["path"]
        ):
            reason = (
                "V064_PUBLIC_CI_SENSITIVE_BYTES_FORBIDDEN"
                if _forbidden_public_bytes(body, entry["path"])
                else "V064_PUBLIC_CI_SOURCE_BLOB_CHANGED"
            )
            raise V064PublicCiBundleError(reason)
        bodies[entry["path"]] = body
    manifest_body = canonical_json(manifest).encode("utf-8") + b"\n"
    if target.exists() or target.is_symlink():
        raise V064PublicCiBundleError("V064_PUBLIC_CI_DESTINATION_EXISTS")
    root_descriptor = None
    try:
        target.mkdir(mode=0o700)
        os.chmod(target, 0o700)
        created_root = target.lstat()
        root_identity = (target, (created_root.st_dev, created_root.st_ino))
        root_descriptor = os.open(
            target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        for relative in sorted(bodies):
            attached_root = target.lstat()
            if (attached_root.st_dev, attached_root.st_ino) != root_identity[1]:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_DESTINATION_REPLACED")
            parts = Path(relative).parts
            parent_descriptor = _retained_parent(root_descriptor, tuple(parts[:-1]))
            try:
                attached_root = target.lstat()
                if (attached_root.st_dev, attached_root.st_ino) != root_identity[1]:
                    raise V064PublicCiBundleError("V064_PUBLIC_CI_DESTINATION_REPLACED")
                _write_new_at(parent_descriptor, parts[-1], bodies[relative])
            finally:
                os.close(parent_descriptor)
        _write_new_at(root_descriptor, "bundle-manifest-v1.json", manifest_body)
        attached_root = target.lstat()
        if (attached_root.st_dev, attached_root.st_ino) != root_identity[1]:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_DESTINATION_REPLACED")
        os.fsync(root_descriptor)
    except V064PublicCiBundleError:
        raise
    except OSError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_STAGE_FAILED") from error
    finally:
        if root_descriptor is not None:
            try:
                os.close(root_descriptor)
            except OSError:
                pass
    return copy.deepcopy(manifest)


def _read_public_file(path: Path, root_descriptor: int = None, relative: str = "") -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    nonblock = getattr(os, "O_NONBLOCK", None)
    if not isinstance(nofollow, int) or not nofollow or not isinstance(nonblock, int) or not nonblock:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_UNSUPPORTED")
    parent_descriptor = None
    name = path.name
    if root_descriptor is not None:
        parts = Path(relative).parts
        parent_descriptor = _retained_parent(root_descriptor, tuple(parts[:-1]))
        name = parts[-1]
        try:
            before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        except BaseException:
            os.close(parent_descriptor)
            raise
    else:
        before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o644
        or not 0 < before.st_size <= _MAX_MANIFEST_BYTES
    ):
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    try:
        descriptor = os.open(
            name if parent_descriptor is not None else path,
            os.O_RDONLY | nofollow | nonblock,
            dir_fd=parent_descriptor,
        )
    except BaseException:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
        chunks = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        attached = (
            os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if parent_descriptor is not None
            else path.lstat()
        )
        if (after.st_dev, after.st_ino, after.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
        return b"".join(chunks)
    finally:
        os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _object_git(git_directory: Path, arguments: Tuple[str, ...], body: bytes = b"") -> bytes:
    environment = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_DIR": str(git_directory),
        "GIT_AUTHOR_NAME": "cjl308868584-lang",
        "GIT_AUTHOR_EMAIL": "cjl308868584-lang@users.noreply.github.com",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
        "GIT_COMMITTER_NAME": "cjl308868584-lang",
        "GIT_COMMITTER_EMAIL": "cjl308868584-lang@users.noreply.github.com",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
    }
    completed = subprocess.run(
        ("/usr/bin/git", *arguments),
        input=body,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )
    if completed.returncode or completed.stderr:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_BUILD_FAILED")
    return completed.stdout


def _write_tree(git_directory: Path, files: Mapping[str, Tuple[str, bytes]]) -> str:
    nested: Dict[str, Any] = {}
    for relative, value in files.items():
        cursor = nested
        parts = relative.split("/")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value

    def build(node: Mapping[str, Any]) -> str:
        records = []
        for name in sorted(node):
            value = node[name]
            if isinstance(value, dict):
                oid = build(value)
                records.append(("040000", "tree", oid, name))
            else:
                mode, data = value
                oid = _single_oid(
                    _object_git(git_directory, ("hash-object", "-w", "--stdin"), data)
                )
                records.append((mode, "blob", oid, name))
        body = b"".join(
            ("%s %s %s\t%s" % record).encode("utf-8") + b"\0"
            for record in records
        )
        return _single_oid(_object_git(git_directory, ("mktree", "-z"), body))

    return build(nested)


def build_v064_public_root_commit(
    repository: Path, source_commit: str, public_root: Path
) -> Dict[str, Any]:
    """Build and replay one deterministic parentless public root commit."""

    root = Path(public_root)
    expected_manifest = build_v064_public_ci_bundle_manifest(repository, source_commit)
    manifest_path = root / "bundle-manifest-v1.json"
    actual_manifest = load_v064_public_ci_bundle_manifest(manifest_path)
    if actual_manifest != expected_manifest:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    expected_paths = sorted(
        [entry["path"] for entry in actual_manifest["files"]]
        + ["bundle-manifest-v1.json"]
    )
    allowed_directories = {
        str(Path(relative).parent)
        for relative in expected_paths
        if str(Path(relative).parent) != "."
    }
    allowed_directories |= {
        str(parent)
        for relative in tuple(allowed_directories)
        for parent in Path(relative).parents
        if str(parent) != "."
    }
    actual_objects = list(root.rglob("*"))
    actual_paths = []
    actual_directories = set()
    for path in actual_objects:
        entry = path.lstat()
        relative = str(path.relative_to(root))
        if stat.S_ISREG(entry.st_mode):
            actual_paths.append(relative)
        elif stat.S_ISDIR(entry.st_mode):
            if entry.st_uid != os.getuid() or stat.S_IMODE(entry.st_mode) != 0o700:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
            actual_directories.add(relative)
        else:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    actual_paths.sort()
    if actual_paths != expected_paths or actual_directories != allowed_directories:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    files = {}
    entry_by_path = {entry["path"]: entry for entry in actual_manifest["files"]}
    root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for relative in expected_paths:
            path = root / relative
            body = _read_public_file(path, root_descriptor, relative)
            if relative != "bundle-manifest-v1.json":
                entry = entry_by_path[relative]
                if len(body) != entry["size"] or hashlib.sha256(body).hexdigest() != entry["sha256"]:
                    raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
            files[relative] = ("100644", body)
    finally:
        os.close(root_descriptor)
    git_directory = root.parent / (root.name + ".git")
    fresh_store = not git_directory.exists()
    if fresh_store:
        initialized = subprocess.run(
            ("/usr/bin/git", "init", "--bare", "-q", str(git_directory)),
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if initialized.returncode or initialized.stderr:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_BUILD_FAILED")
        os.chmod(git_directory, 0o700)
    try:
        git_stat = git_directory.lstat()
    except OSError as error:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_BUILD_FAILED") from error
    if (
        not stat.S_ISDIR(git_stat.st_mode)
        or git_stat.st_uid != os.getuid()
        or stat.S_IMODE(git_stat.st_mode) != 0o700
    ):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_BUILD_FAILED")
    if not fresh_store:
        refs_before = _object_git(
            git_directory, ("for-each-ref", "--format=%(refname) %(objectname)")
        )
        if not refs_before.startswith(b"refs/heads/main ") or refs_before.count(b"\n") != 1:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        if (git_directory / "objects/info/alternates").exists():
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        hooks = git_directory / "hooks"
        if hooks.exists() and any(path.is_file() and not path.name.endswith(".sample") for path in hooks.iterdir()):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        existing_commit = refs_before.decode("ascii").strip().split(" ", 1)[1]
        existing_body = _object_git(
            git_directory, ("cat-file", "commit", existing_commit)
        )
        expected_metadata = (
            b"author cjl308868584-lang <cjl308868584-lang@users.noreply.github.com> "
            b"946684800 +0000\ncommitter cjl308868584-lang "
            b"<cjl308868584-lang@users.noreply.github.com> 946684800 +0000\n\n"
            b"v0.64 bounded Linux portability witness\n"
        )
        existing_tree = _single_oid(
            _object_git(git_directory, ("rev-parse", existing_commit + "^{tree}"))
        )
        if existing_body != b"tree " + existing_tree.encode("ascii") + b"\n" + expected_metadata:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        existing_listing = _object_git(
            git_directory, ("ls-tree", "-r", "-z", existing_commit)
        )
        records = [record for record in existing_listing.split(b"\0") if record]
        if [record.split(b"\t", 1)[1].decode("utf-8") for record in records] != expected_paths:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        for record in records:
            identity, raw_path = record.split(b"\t", 1)
            mode, kind, oid = identity.split(b" ")
            relative = raw_path.decode("utf-8")
            if mode != b"100644" or kind != b"blob" or _object_git(
                git_directory, ("cat-file", "blob", oid.decode("ascii"))
            ) != files[relative][1]:
                raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
        return {
            "commit": existing_commit,
            "tree": _single_oid(
                _object_git(git_directory, ("rev-parse", existing_commit + "^{tree}"))
            ),
            "parent_count": 0,
            "author_email": "cjl308868584-lang@users.noreply.github.com",
            "paths": expected_paths,
            "git_directory": str(git_directory),
        }
    tree = _write_tree(git_directory, files)
    commit = _single_oid(
        _object_git(
            git_directory,
            ("commit-tree", tree),
            b"v0.64 bounded Linux portability witness\n",
        )
    )
    refs = _object_git(git_directory, ("for-each-ref", "--format=%(refname) %(objectname)"))
    expected_ref = ("refs/heads/main %s\n" % commit).encode("ascii")
    if refs not in (b"", expected_ref):
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_HISTORY_PRESENT")
    if not refs:
        _object_git(git_directory, ("update-ref", "refs/heads/main", commit))
    commit_body = _object_git(git_directory, ("cat-file", "commit", commit))
    if b"\nparent " in b"\n" + commit_body:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_REPLAY_FAILED")
    listing = _object_git(git_directory, ("ls-tree", "-r", "-z", commit))
    replay_paths = []
    for record in listing.split(b"\0"):
        if record:
            replay_paths.append(record.split(b"\t", 1)[1].decode("utf-8"))
    if replay_paths != expected_paths:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_OBJECT_REPLAY_FAILED")
    return {
        "commit": commit,
        "tree": tree,
        "parent_count": 0,
        "author_email": "cjl308868584-lang@users.noreply.github.com",
        "paths": expected_paths,
        "git_directory": str(git_directory),
    }


def verify_v064_public_ci_bundle(
    repository: Path, source_commit: str, public_root: Path
) -> Dict[str, Any]:
    """Replay the public tree against exact private source Git objects."""

    root = Path(public_root)
    manifest = load_v064_public_ci_bundle_manifest(root / "bundle-manifest-v1.json")
    expected = build_v064_public_ci_bundle_manifest(repository, source_commit)
    if manifest != expected:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    expected_paths = sorted(
        [entry["path"] for entry in manifest["files"]]
        + ["bundle-manifest-v1.json"]
    )
    actual_paths = sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file()
    )
    if actual_paths != expected_paths:
        raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    source_paths = {relative: source for relative, _kind, source in _FILES}
    for entry in manifest["files"]:
        path = root / entry["path"]
        try:
            opened = path.lstat()
            body = path.read_bytes()
        except OSError as error:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID") from error
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.getuid()
            or opened.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o644
            or len(body) != entry["size"]
            or hashlib.sha256(body).hexdigest() != entry["sha256"]
        ):
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
        oid, exact = _blob(repository, source_commit, source_paths[entry["path"]])
        if oid != entry["source_blob_oid"] or body != exact:
            raise V064PublicCiBundleError("V064_PUBLIC_CI_PUBLIC_ROOT_INVALID")
    candidate = build_v064_public_root_commit(repository, source_commit, root)
    return {
        "status": "V064_PUBLIC_CI_BUNDLE_VERIFIED",
        "file_count": len(expected_paths),
        "manifest_sha256": hashlib.sha256(
            (root / "bundle-manifest-v1.json").read_bytes()
        ).hexdigest(),
        "file_set_sha256": manifest["file_set_sha256"],
        "commit": candidate["commit"],
        "tree": candidate["tree"],
    }
