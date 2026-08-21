"""Fixed, credential-free ceremony for the bounded v0.65 Nautilus spike."""

import argparse
import base64
import copy
import hashlib
import json
import os
import platform
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence

from .canonical import canonical_json
from .challenger_replacement_supersession_publish import (
    SupersessionPublishError,
    _atomic_no_replace,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .errors import CanonicalizationError
from .nautilus_v065_contract import (
    NautilusV065ContractError,
    build_nautilus_v065_current_reference,
    build_nautilus_v065_request,
    load_nautilus_v065_result,
    verify_nautilus_v065_result,
)
from .nautilus_v065_evidence import (
    build_nautilus_v065_execution_failure_comparison,
    build_nautilus_v065_supply_failure_comparison,
    compare_nautilus_v065,
)
from .nautilus_v065_plan import build_nautilus_v065_plan, load_nautilus_v065_plan
from .nautilus_v065_supply_chain import (
    NautilusV065SupplyChainError,
    build_nautilus_v065_dependency_lock,
    supply_chain_receipt_hash,
)


_ROOT = Path(__file__).resolve().parents[2]
_ARTIFACT_ROOT = _ROOT / "artifacts" / "nautilus-sandbox"
_FORMAL_ROOT = _ARTIFACT_ROOT / "v0.65.0"
_PLAN_NAME = "nautilus-e2e-spike-plan-v0.65.0.json"
_RECEIPT_NAME = "nautilus-supply-chain-receipt-v0.65.0.json"
_REQUEST_NAME = "nautilus-sandbox-request-v0.65.0.json"
_FIRST_RESULT_NAME = "nautilus-sandbox-result-first-v0.65.0.json"
_REPLAY_RESULT_NAME = "nautilus-sandbox-result-replay-v0.65.0.json"
_COMPARISON_NAME = "nautilus-sandbox-comparison-v0.65.0.json"
_FINAL_NAMES = frozenset(
    {_PLAN_NAME, _RECEIPT_NAME, _REQUEST_NAME, _FIRST_RESULT_NAME, _REPLAY_RESULT_NAME, _COMPARISON_NAME}
)
_MAX_OUTPUT = 4 * 1024 * 1024
_MAX_ARTIFACT = 4 * 1024 * 1024
_TAG = "v1.230.0"
_TAG_OBJECT = "112d335088ec11cdd1d60038b16c8fe56406aead"
_TAG_COMMIT = "8160730c7c550480b0a439fb11086a4c4de15f0b"
_LICENSE_SHA = "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c"
_WHEEL = "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl"
_WHEEL_SHA = "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079"
_STAGING_RE = re.compile(r"^\.nautilus-v065-[0-9a-f]{64}-[0-9a-f]{32}\.staging$")


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if not isinstance(value, int) or value == 0:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_PLATFORM_UNSUPPORTED")
    return value


def _hash_descriptor(descriptor: int, size: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        try:
            chunk = os.pread(descriptor, min(65536, size - offset), offset)
        except InterruptedError:
            continue
        if not chunk:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _executable_identity(path: Path) -> Dict[str, Any]:
    flags = os.O_RDONLY | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK")
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID") from error
    try:
        value = os.fstat(descriptor)
        if (
            not stat.S_ISREG(value.st_mode)
            or value.st_size <= 0
            or value.st_size > 512 * 1024 * 1024
            or stat.S_IMODE(value.st_mode) & 0o022
        ):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID")
        return {
            "device": value.st_dev,
            "inode": value.st_ino,
            "mode": stat.S_IMODE(value.st_mode),
            "size": value.st_size,
            "sha256": _hash_descriptor(descriptor, value.st_size),
        }
    finally:
        try:
            os.close(descriptor)
        except OSError as error:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_CLOSE_FAILED") from error


def _venv_python_identity(path: Path, workspace: Path) -> Dict[str, Any]:
    expected = workspace / "venv" / "bin" / "python"
    if path != expected:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID")
    try:
        root = workspace.lstat()
        link = path.lstat()
        if (
            not stat.S_ISDIR(root.st_mode)
            or root.st_uid != os.geteuid()
            or stat.S_IMODE(root.st_mode) != 0o700
            or link.st_uid != os.geteuid()
            or link.st_nlink != 1
            or not (stat.S_ISLNK(link.st_mode) or stat.S_ISREG(link.st_mode))
        ):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID")
        target = path.resolve(strict=True) if stat.S_ISLNK(link.st_mode) else path
    except (OSError, RuntimeError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_INVALID") from error
    return _executable_identity(target)


def _command_executable_identity(name: str, executable: Path, workspace: Optional[Path]) -> Dict[str, Any]:
    if name == "offline_import":
        if workspace is None:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_WORKSPACE_REQUIRED")
        return _venv_python_identity(executable, workspace)
    return _executable_identity(executable)


def _find_executable(name: str) -> Path:
    candidates = {
        "git": (Path("/usr/bin/git"),),
        "curl": (Path("/usr/bin/curl"),),
        "uv": (Path.home() / ".local/bin/uv", Path("/opt/homebrew/bin/uv"), Path("/usr/local/bin/uv")),
        "gh": (Path.home() / ".local/bin/gh", Path("/opt/homebrew/bin/gh"), Path("/usr/local/bin/gh"), Path("/usr/bin/gh")),
        "python": (Path(sys.executable).resolve(), (Path.home() / ".local/bin/python3.12").resolve(), Path("/usr/local/bin/python3.12").resolve()),
    }[name]
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise NautilusV065SupplyChainError("NAUTILUS_V065_TOOL_MISSING")


def _command(name: str, workspace: Optional[Path]) -> Sequence[str]:
    if name == "uv_version":
        return [str(_find_executable("uv")), "--version"]
    if name == "python_version":
        return [str(_find_executable("python")), "--version"]
    if name == "git_version":
        return [str(_find_executable("git")), "--version"]
    if name == "gh_version":
        return [str(_find_executable("gh")), "--version"]
    if name == "official_tag":
        return [str(_find_executable("git")), "ls-remote", "https://github.com/nautechsystems/nautilus_trader.git", "refs/tags/v1.230.0", "refs/tags/v1.230.0^{}"]
    if name == "license":
        return [str(_find_executable("curl")), "--fail", "--silent", "--show-error", "--location", "https://raw.githubusercontent.com/nautechsystems/nautilus_trader/8160730c7c550480b0a439fb11086a4c4de15f0b/LICENSE"]
    if workspace is None:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_WORKSPACE_REQUIRED")
    wheelhouse = workspace / "wheelhouse"
    venv = workspace / "venv"
    if name == "slsa":
        return [str(_find_executable("gh")), "attestation", "verify", str(wheelhouse / _WHEEL), "--repo", "nautechsystems/nautilus_trader"]
    if name == "offline_venv":
        return [str(_find_executable("uv")), "venv", "--offline", "--python", str(_find_executable("python")), str(venv)]
    if name == "offline_sync":
        return [str(_find_executable("uv")), "pip", "install", "--offline", "--python", str(venv / "bin" / "python"), "--find-links", str(wheelhouse), "nautilus_trader==1.230.0"]
    if name == "offline_import":
        return [str(venv / "bin" / "python"), "-I", "-c", "import nautilus_trader,platform;assert nautilus_trader.__version__=='1.230.0';assert platform.machine()=='arm64'"]
    raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_UNKNOWN")


def _encoded_output(raw: bytes) -> tuple[str, str]:
    try:
        return "utf-8", raw.decode("utf-8")
    except UnicodeDecodeError:
        return "base64", base64.b64encode(raw).decode("ascii")


def _capture_fixed_command(name: str, *, workspace: Optional[Path] = None) -> Dict[str, Any]:
    argv = list(_command(name, workspace))
    executable = Path(argv[0])
    before = _command_executable_identity(name, executable, workspace)
    home = str((workspace / "home") if workspace is not None else Path.home())
    environment = {
        "HOME": home,
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    timeout_error = None
    returncode = -1
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                result = subprocess.run(
                    argv,
                    cwd=workspace if workspace is not None else _ROOT,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=120,
                    shell=False,
                    check=False,
                )
                returncode = result.returncode
            except subprocess.TimeoutExpired as error:
                timeout_error = error
            stdout_file.flush()
            stderr_file.flush()
            stdout_size = os.fstat(stdout_file.fileno()).st_size
            stderr_size = os.fstat(stderr_file.fileno()).st_size
            if stdout_size > _MAX_OUTPUT or stderr_size > _MAX_OUTPUT:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_OUTPUT_LIMIT")
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read(stdout_size + 1)
            stderr = stderr_file.read(stderr_size + 1)
            if len(stdout) != stdout_size or len(stderr) != stderr_size:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_OUTPUT_INVALID")
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_FAILED") from error
    after = _command_executable_identity(name, executable, workspace)
    if before != after:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_CHANGED")
    stdout_encoding, stdout_text = _encoded_output(stdout)
    stderr_encoding, stderr_text = _encoded_output(stderr)
    record = {
        "name": name,
        "argv": argv,
        "exit_code": returncode,
        "executable_path": str(executable),
        "stdout_encoding": stdout_encoding,
        "stdout_bytes": stdout_text,
        "stdout_size": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_encoding": stderr_encoding,
        "stderr_bytes": stderr_text,
        "stderr_size": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
    }
    for suffix, identity in (("before", before), ("after", after)):
        for field in ("device", "inode", "mode", "size", "sha256"):
            record[f"executable_{field}_{suffix}"] = identity[field]
    if timeout_error is not None:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_TIMEOUT", evidence=record) from timeout_error
    if returncode != 0:
        reason = {
            "official_tag": "NAUTILUS_V065_TAG_FETCH_FAILED",
            "license": "NAUTILUS_V065_LICENSE_FETCH_FAILED",
            "slsa": "NAUTILUS_V065_SLSA_VERIFICATION_FAILED",
            "offline_venv": "NAUTILUS_V065_OFFLINE_ENV_FAILED",
            "offline_sync": "NAUTILUS_V065_OFFLINE_SYNC_FAILED",
            "offline_import": "NAUTILUS_V065_OFFLINE_IMPORT_FAILED",
        }.get(name, "NAUTILUS_V065_COMMAND_NONZERO")
        raise NautilusV065SupplyChainError(reason, evidence=record)
    return record


def _download_urls() -> Dict[str, str]:
    text = (_ROOT / "sandboxes/nautilus-v065/uv.lock").read_text(encoding="utf-8")
    return {
        url.rsplit("/", 1)[1]: url
        for url in re.findall(r'url = "(https://files\.pythonhosted\.org/[^"]+\.whl)"', text)
    }


def _download_fixed_artifact(item: Mapping[str, Any], wheelhouse: Path) -> Dict[str, Any]:
    filename = item["filename"]
    url = _download_urls().get(filename)
    if url is None:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_URL_MISSING")
    target = wheelhouse / filename
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_error: Optional[BaseException] = None
    for _attempt in range(3):
        try:
            with opener.open(url, timeout=60) as response, target.open("xb") as stream:
                digest = hashlib.sha256()
                size = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > item["size"]:
                        raise NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_SIZE_MISMATCH")
                    stream.write(chunk)
                    digest.update(chunk)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
            if size != item["size"] or digest.hexdigest() != item["sha256"]:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_HASH_MISMATCH")
            return dict(item)
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            if target.exists() and target.is_file():
                target.unlink()
    raise NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_FAILED") from last_error


def _platform_identity() -> Dict[str, Any]:
    version = platform.mac_ver()[0]
    if platform.system() != "Darwin" or platform.machine() != "arm64" or not version.startswith("15.") or sys.version_info[:2] != (3, 12):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_PLATFORM_MISMATCH")
    return {"operating_system": "macOS", "operating_system_major": 15, "machine": "arm64", "python_implementation": platform.python_implementation(), "python_version": platform.python_version()}


def _verify_license_transcript(record: Mapping[str, Any]) -> None:
    if record["stdout_encoding"] != "utf-8":
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LICENSE_MISMATCH")
    raw = record["stdout_bytes"].encode("utf-8")
    if len(raw) != 7651 or hashlib.sha256(raw).hexdigest() != _LICENSE_SHA:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LICENSE_MISMATCH")


def _plan_binding(plan: Mapping[str, Any]) -> tuple[str, str]:
    try:
        if plan["status"] != "SPIKE_PLAN_PREREGISTERED_NOT_EXECUTED" or any(plan["authority"].values()):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_PLAN_AUTHORITY_INVALID")
        return plan["plan_id"], plan["plan_hash"]
    except (KeyError, TypeError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_PLAN_INVALID") from error


@contextmanager
def _verified_acquisition_workspace_success(plan: Mapping[str, Any]) -> Iterator[Dict[str, Any]]:
    """Keep the exact verified environment alive through sandbox execution."""

    plan_id, plan_hash = _plan_binding(plan)
    lock = build_nautilus_v065_dependency_lock(repository_root=_ROOT)
    observed_platform = _platform_identity()
    temporary_parent = "/private/tmp" if sys.platform == "darwin" and Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="nautilus-v065-", dir=temporary_parent) as raw:
        workspace = Path(raw)
        workspace.chmod(0o700)
        (workspace / "home").mkdir(mode=0o700)
        wheelhouse = workspace / "wheelhouse"
        wheelhouse.mkdir(mode=0o700)
        transcripts = []

        def capture(name: str) -> Dict[str, Any]:
            try:
                record = _capture_fixed_command(name, workspace=workspace)
            except NautilusV065SupplyChainError as error:
                error.completed_transcripts = copy.deepcopy(transcripts)
                raise
            transcripts.append(record)
            return record

        for name in ("uv_version", "python_version", "git_version", "gh_version", "official_tag", "license"):
            capture(name)
        tag_output = transcripts[4]["stdout_bytes"]
        if _TAG_OBJECT not in tag_output or _TAG_COMMIT not in tag_output:
            error = NautilusV065SupplyChainError("NAUTILUS_V065_TAG_IDENTITY_MISMATCH")
            error.completed_transcripts = copy.deepcopy(transcripts)
            raise error
        try:
            _verify_license_transcript(transcripts[5])
            verified = [_download_fixed_artifact(item, wheelhouse) for item in lock["distributions"]]
        except NautilusV065SupplyChainError as error:
            error.completed_transcripts = copy.deepcopy(transcripts)
            raise
        capture("slsa")
        for name in ("offline_venv", "offline_sync", "offline_import"):
            capture(name)
        tools = []
        for record in transcripts[:4]:
            tools.append({"name": record["name"].removesuffix("_version"), "version": record["stdout_bytes"].strip(), "executable_sha256_before": record["executable_sha256_before"], "executable_sha256_after": record["executable_sha256_after"]})
        receipt: Dict[str, Any] = {
            "$schema": "./nautilus-supply-chain-receipt-v2.schema.json",
            "schema_version": "2.0.0",
            "receipt_id": "nautilus_v065_supply_chain_" + "0" * 64,
            "receipt_hash": "0" * 64,
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "dependency_lock": lock,
            "platform": observed_platform,
            "tools": tools,
            "transcripts": transcripts,
            "verified_files": verified,
            "license": {"expression": "LGPL-3.0-or-later", "size": 7651, "sha256": _LICENSE_SHA},
            "official_source": {"tag": _TAG, "tag_object": _TAG_OBJECT, "peeled_commit": _TAG_COMMIT},
            "slsa": {"verified": True, "subject_filename": _WHEEL, "subject_sha256": _WHEEL_SHA},
            "authority_counters": {"credential_reads": 0, "market_requests": 0, "account_requests": 0, "broker_requests": 0, "orders": 0, "production_state_writes": 0},
            "status": "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY",
        }
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"] = "nautilus_v065_supply_chain_" + digest
        receipt["receipt_hash"] = digest
        yield {
            "status": receipt["status"],
            "receipt": receipt,
            "python": workspace / "venv" / "bin" / "python",
            "workspace": workspace,
        }


@contextmanager
def _verified_acquisition_workspace(plan: Mapping[str, Any]) -> Iterator[Dict[str, Any]]:
    """Yield either one retained verified environment or one frozen failure receipt."""

    plan_id, plan_hash = _plan_binding(plan)
    lock = build_nautilus_v065_dependency_lock(repository_root=_ROOT)
    acquired = _verified_acquisition_workspace_success(plan)
    try:
        session = acquired.__enter__()
    except NautilusV065SupplyChainError as error:
        completed = copy.deepcopy(getattr(error, "completed_transcripts", []))
        receipt: Dict[str, Any] = {
            "$schema": "./nautilus-supply-chain-receipt-v2.schema.json",
            "schema_version": "2.0.0",
            "receipt_id": "nautilus_v065_supply_chain_failure_" + "0" * 64,
            "receipt_hash": "0" * 64,
            "plan_id": plan_id,
            "plan_hash": plan_hash,
            "dependency_lock": lock,
            "transcripts": completed,
            "failure": {
                "reason_code": error.reason_code,
                "failed_stage": error.evidence["name"] if error.evidence is not None else "ACQUISITION",
                "completed_transcript_count": len(completed),
                "failed_command": copy.deepcopy(error.evidence),
            },
            "authority_counters": {
                "credential_reads": 0,
                "market_requests": 0,
                "account_requests": 0,
                "broker_requests": 0,
                "orders": 0,
                "production_state_writes": 0,
            },
            "status": "SUPPLY_CHAIN_ACQUISITION_FAILED",
        }
        digest = supply_chain_receipt_hash(receipt)
        receipt["receipt_id"] = "nautilus_v065_supply_chain_failure_" + digest
        receipt["receipt_hash"] = digest
        yield {
            "status": receipt["status"],
            "receipt": receipt,
            "reason_code": error.reason_code,
            "python": None,
            "workspace": None,
        }
        return
    try:
        yield session
    finally:
        acquired.__exit__(*sys.exc_info())


def acquire_nautilus_v065_supply_chain(*, plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Execute acquisition and return its verified or failure receipt."""

    with _verified_acquisition_workspace(plan) as session:
        return copy.deepcopy(session["receipt"])


def _read_final(parent_fd: int, name: str) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK")
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_UNTRUSTED") from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid() or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o600 or not 0 < before.st_size <= _MAX_ARTIFACT:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_UNTRUSTED")
        body = bytearray()
        while len(body) < before.st_size:
            try:
                chunk = os.read(descriptor, before.st_size - len(body))
            except InterruptedError:
                continue
            if not chunk:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_UNTRUSTED")
            body.extend(chunk)
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_uid,
            value.st_nlink,
            stat.S_IMODE(value.st_mode),
            value.st_size,
        )
        if identity(before) != identity(after) or identity(after) != identity(attached):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_UNTRUSTED")
        return bytes(body), after
    except NautilusV065SupplyChainError:
        raise
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_UNTRUSTED") from error
    finally:
        os.close(descriptor)


def _trusted_artifact_root_stat(value: os.stat_result) -> bool:
    mode = stat.S_IMODE(value.st_mode)
    return (
        stat.S_ISDIR(value.st_mode)
        and value.st_uid == os.geteuid()
        and mode & 0o700 == 0o700
        and mode & 0o022 == 0
    )


def _validate_artifact_root(root: Path, parent_fd: int, expected: os.stat_result) -> None:
    try:
        opened = os.fstat(parent_fd)
        attached = root.lstat()
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_ARTIFACT_ROOT_INVALID") from error
    for value in (opened, attached):
        if (
            not _trusted_artifact_root_stat(value)
            or (value.st_dev, value.st_ino) != (expected.st_dev, expected.st_ino)
        ):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_ARTIFACT_ROOT_INVALID")


def _publish_fixed_artifact(*, root: Path, final_name: str, data: bytes) -> Dict[str, Any]:
    if final_name not in _FINAL_NAMES or not isinstance(data, bytes) or not 0 < len(data) <= _MAX_ARTIFACT:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_ARTIFACT_INVALID")
    root = Path(root)
    before = root.lstat()
    if not root.is_absolute() or not _trusted_artifact_root_stat(before):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_ARTIFACT_ROOT_INVALID")
    flags = os.O_RDONLY | _required_flag("O_DIRECTORY") | _required_flag("O_NOFOLLOW")
    parent_fd = os.open(root, flags)
    try:
        opened = os.fstat(parent_fd)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_ARTIFACT_ROOT_INVALID")
        names = os.listdir(parent_fd)
        if any(_STAGING_RE.fullmatch(name) for name in names):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_STAGING_PRESENT")
        try:
            existing, value = _read_final(parent_fd, final_name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if existing != data:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_CONFLICT")
            os.fsync(parent_fd)
            _validate_artifact_root(root, parent_fd, before)
            return {"status": "ALREADY_PUBLISHED", "file_sha256": hashlib.sha256(data).hexdigest(), "device": value.st_dev, "inode": value.st_ino}
        digest = hashlib.sha256(data).hexdigest()
        staging = f".nautilus-v065-{digest}-{secrets.token_hex(16)}.staging"
        stage_flags = os.O_CREAT | os.O_EXCL | os.O_RDWR | _required_flag("O_NOFOLLOW")
        stage_fd = os.open(staging, stage_flags, 0o600, dir_fd=parent_fd)
        try:
            offset = 0
            while offset < len(data):
                try:
                    offset += os.write(stage_fd, data[offset:])
                except InterruptedError:
                    continue
            os.lseek(stage_fd, 0, os.SEEK_SET)
            if os.read(stage_fd, len(data) + 1) != data:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_STAGING_BYTES_MISMATCH")
            os.fsync(stage_fd)
            try:
                _atomic_no_replace(parent_fd, staging, final_name)
            except FileExistsError:
                existing, value = _read_final(parent_fd, final_name)
                if existing != data:
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_CONFLICT")
                os.fsync(parent_fd)
                _validate_artifact_root(root, parent_fd, before)
                return {"status": "ALREADY_PUBLISHED", "file_sha256": digest, "device": value.st_dev, "inode": value.st_ino}
            except SupersessionPublishError as error:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_ATOMIC_PUBLISH_FAILED") from error
            os.fsync(parent_fd)
            _validate_artifact_root(root, parent_fd, before)
            final, value = _read_final(parent_fd, final_name)
            if final != data:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FINAL_CONFLICT")
            return {"status": "COMMITTED", "file_sha256": digest, "device": value.st_dev, "inode": value.st_ino}
        finally:
            os.close(stage_fd)
    finally:
        os.close(parent_fd)


def _clean_head() -> str:
    status = subprocess.run(["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if status.returncode or status.stdout:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_WORKTREE_NOT_CLEAN")
    result = subprocess.run(["/usr/bin/git", "rev-parse", "HEAD"], cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_GIT_IDENTITY_INVALID")
    return result.stdout.decode("ascii").strip()


def _verify_formal_candidate(plan: Mapping[str, Any], current_head: str) -> None:
    plan_path = "artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json"
    artifact_test_path = "tests/test_nautilus_v065_artifacts.py"
    try:
        candidate = plan["code_lock_candidate"]["commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", candidate) or not re.fullmatch(
            r"[0-9a-f]{40}", current_head
        ):
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_CANDIDATE_INVALID"
            )
        commands = (
            ["rev-list", "--count", f"{candidate}..{current_head}"],
            ["diff", "--name-status", f"{candidate}..{current_head}"],
            ["show", f"{current_head}:{plan_path}"],
        )
        results = []
        for arguments in commands:
            result = subprocess.run(
                ["/usr/bin/git", *arguments],
                cwd=_ROOT,
                env={
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "LANG": "C",
                    "LC_ALL": "C",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
            )
            if result.returncode != 0 or len(result.stdout) > _MAX_ARTIFACT:
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_FORMAL_CANDIDATE_INVALID"
                )
            results.append(result.stdout)
        expected_delta = f"A\t{plan_path}\nA\t{artifact_test_path}\n".encode("ascii")
        expected_plan = canonical_json(plan).encode("utf-8") + b"\n"
        if results != [b"1\n", expected_delta, expected_plan]:
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_CANDIDATE_INVALID"
            )
    except NautilusV065SupplyChainError:
        raise
    except (KeyError, TypeError, CanonicalizationError, subprocess.SubprocessError, OSError) as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_FORMAL_CANDIDATE_INVALID"
        ) from error


def _invoke_fixed_runner(
    *,
    python: Path,
    workspace: Path,
    request: Mapping[str, Any],
    receipt: Mapping[str, Any],
    invocation: str,
) -> Dict[str, Any]:
    if invocation not in {"first", "replay"}:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_INVOCATION_INVALID")
    try:
        records = [item for item in receipt["transcripts"] if item["name"] == "offline_import"]
        if len(records) != 1 or records[0]["executable_path"] != str(python):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID")
        record = records[0]
        expected = {
            field: record[f"executable_{field}_before"]
            for field in ("device", "inode", "mode", "size", "sha256")
        }
        if any(record[f"executable_{field}_after"] != expected[field] for field in expected):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID")
        if _venv_python_identity(python, workspace) != expected:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID")
    except (KeyError, TypeError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID") from error
    root = Path(tempfile.mkdtemp(prefix=f"runner-{invocation}-", dir=workspace))
    root.chmod(0o700)
    request_path = root / "request.json"
    receipt_path = root / "receipt.json"
    result_path = root / "result.json"
    request_path.write_bytes(canonical_json(request).encode("utf-8") + b"\n")
    receipt_path.write_bytes(
        canonical_json({"receipt_id": receipt["receipt_id"], "receipt_hash": receipt["receipt_hash"]}).encode("utf-8") + b"\n"
    )
    request_path.chmod(0o600)
    receipt_path.chmod(0o600)
    environment = {
        "HOME": str(root),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "PYTHONPATH": str(_ROOT / "sandboxes" / "nautilus-v065" / "src"),
        "LANG": "C",
        "LC_ALL": "C",
    }
    result = subprocess.run(
        [
            str(python), "-P", "-m", "crypto_quant_nautilus_v065.runner",
            "--request", str(request_path), "--receipt", str(receipt_path), "--result", str(result_path),
        ],
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        shell=False,
        check=False,
    )
    if _venv_python_identity(python, workspace) != expected:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_PYTHON_IDENTITY_INVALID")
    if result.returncode != 0 or result.stdout or result.stderr:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RUNNER_FAILED")
    return load_nautilus_v065_result(result_path.resolve())


def _publish_canonical(root: Path, final_name: str, value: Mapping[str, Any]) -> None:
    _publish_fixed_artifact(
        root=root,
        final_name=final_name,
        data=canonical_json(value).encode("utf-8") + b"\n",
    )


def _read_candidate_blob(commit: str, relative_path: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or relative_path != "tests/fixtures/nautilus-v065/current-reference-v2.json":
        raise NautilusV065SupplyChainError("NAUTILUS_V065_CURRENT_REFERENCE_INVALID")
    result = subprocess.run(
        ["/usr/bin/git", "show", f"{commit}:{relative_path}"],
        cwd=_ROOT,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "LANG": "C", "LC_ALL": "C"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or not 0 < len(result.stdout) <= _MAX_ARTIFACT:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_CURRENT_REFERENCE_INVALID")
    return result.stdout


def _load_frozen_current_reference(
    plan: Mapping[str, Any], request: Mapping[str, Any]
) -> Dict[str, Any]:
    try:
        commit = plan["code_lock_candidate"]["commit"]
        relative_path = plan["fixture"]["current_reference_path"]
        expected_file_hash = plan["fixture"]["current_reference_file_sha256"]
        body = _read_candidate_blob(commit, relative_path)
        if hashlib.sha256(body).hexdigest() != expected_file_hash:
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_CURRENT_REFERENCE_INVALID"
            )
        frozen = dict(_strict_json_bytes(body))
        if body != canonical_json(frozen).encode("utf-8") + b"\n":
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_CURRENT_REFERENCE_INVALID"
            )
        frozen = verify_nautilus_v065_result(frozen)
        rebound = build_nautilus_v065_current_reference(request=request)
        evidence_keys = (
            "engine",
            "scenario_results",
            "fresh_process_replay_verified",
            "safety_counters",
        )
        if any(frozen[key] != rebound[key] for key in evidence_keys):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_CURRENT_REFERENCE_INVALID")
        return rebound
    except NautilusV065SupplyChainError:
        raise
    except (
        KeyError,
        TypeError,
        ChallengerReplacementPlanError,
        CanonicalizationError,
        NautilusV065ContractError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_CURRENT_REFERENCE_INVALID"
        ) from error


def _acquire_and_run(*, plan: Mapping[str, Any], artifact_root: Path) -> Dict[str, Any]:
    """Execute the fixed two-stage ceremony without accepting override inputs."""

    with _verified_acquisition_workspace(plan) as session:
        receipt = session["receipt"]
        if session["status"] != "SUPPLY_CHAIN_VERIFIED_SANDBOX_READY":
            comparison = build_nautilus_v065_supply_failure_comparison(
                plan=plan,
                receipt=receipt,
                reason_code=session["reason_code"],
                runner_invocation_count=0,
            )
            _publish_canonical(artifact_root, _RECEIPT_NAME, receipt)
            _publish_canonical(artifact_root, _COMPARISON_NAME, comparison)
            return {"conclusion": comparison["conclusion"], "runner_invocation_count": 0}
        request = build_nautilus_v065_request(
            plan_id=plan["plan_id"],
            plan_hash=plan["plan_hash"],
            supply_chain_receipt_id=receipt["receipt_id"],
            supply_chain_receipt_hash=receipt["receipt_hash"],
        )
        current = _load_frozen_current_reference(plan, request)
        first = None
        invocation_count = 1
        try:
            first = _invoke_fixed_runner(
                python=session["python"], workspace=session["workspace"], request=request,
                receipt=receipt, invocation="first",
            )
            invocation_count = 2
            replay = _invoke_fixed_runner(
                python=session["python"], workspace=session["workspace"], request=request,
                receipt=receipt, invocation="replay",
            )
        except NautilusV065SupplyChainError as error:
            comparison = build_nautilus_v065_execution_failure_comparison(
                plan=plan,
                receipt=receipt,
                request=request,
                reason_code=error.reason_code,
                runner_invocation_count=invocation_count,
                first_result=first,
            )
            values = [(_RECEIPT_NAME, receipt), (_REQUEST_NAME, request)]
            if first is not None:
                values.append((_FIRST_RESULT_NAME, first))
            values.append((_COMPARISON_NAME, comparison))
            for name, value in values:
                _publish_canonical(artifact_root, name, value)
            return {"conclusion": comparison["conclusion"], "runner_invocation_count": invocation_count}
        comparison = compare_nautilus_v065(
            plan=plan,
            receipt=receipt,
            request=request,
            current_reference=current,
            first_result=first,
            replay_result=replay,
        )
        for name, value in (
            (_RECEIPT_NAME, receipt),
            (_REQUEST_NAME, request),
            (_FIRST_RESULT_NAME, first),
            (_REPLAY_RESULT_NAME, replay),
            (_COMPARISON_NAME, comparison),
        ):
            _publish_canonical(artifact_root, name, value)
        return {"conclusion": comparison["conclusion"], "runner_invocation_count": 2}


def _commit_formal_ceremony(plan: Mapping[str, Any]) -> Dict[str, Any]:
    parent = _ARTIFACT_ROOT
    formal = _FORMAL_ROOT
    staging_name = ".v0.65.0.in-progress"
    if formal.parent != parent or formal.name != "v0.65.0":
        raise NautilusV065SupplyChainError("NAUTILUS_V065_FORMAL_STATE_CONFLICT")
    try:
        before = parent.lstat()
    except OSError as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
        ) from error
    if not parent.is_absolute() or not _trusted_artifact_root_stat(before):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_FORMAL_STATE_CONFLICT")
    flags = os.O_RDONLY | _required_flag("O_DIRECTORY") | _required_flag("O_NOFOLLOW")
    try:
        parent_fd = os.open(parent, flags)
    except OSError as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
        ) from error
    try:
        _validate_artifact_root(parent, parent_fd, before)
        for name in (staging_name, formal.name):
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError as error:
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
                ) from error
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
            )
        try:
            os.mkdir(staging_name, 0o700, dir_fd=parent_fd)
        except OSError as error:
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
            ) from error
        staging = parent / staging_name
        result = _acquire_and_run(plan=plan, artifact_root=staging)
        staging_fd = os.open(staging_name, flags, dir_fd=parent_fd)
        try:
            value = os.fstat(staging_fd)
            attached = os.stat(staging_name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(value.st_mode)
                or value.st_uid != os.geteuid()
                or stat.S_IMODE(value.st_mode) != 0o700
                or (value.st_dev, value.st_ino) != (attached.st_dev, attached.st_ino)
            ):
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
                )
            os.fsync(staging_fd)
        finally:
            os.close(staging_fd)
        try:
            _atomic_no_replace(parent_fd, staging_name, formal.name)
        except (FileExistsError, SupersessionPublishError, OSError) as error:
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_COMMIT_FAILED"
            ) from error
        os.fsync(parent_fd)
        committed = os.stat(formal.name, dir_fd=parent_fd, follow_symlinks=False)
        if (committed.st_dev, committed.st_ino) != (value.st_dev, value.st_ino):
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_COMMIT_FAILED"
            )
        _validate_artifact_root(parent, parent_fd, before)
        return result
    finally:
        os.close(parent_fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nautilus-v065-ceremony")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("publish-plan")
    subcommands.add_parser("acquire-and-run")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "publish-plan":
        plan = build_nautilus_v065_plan(repository_root=_ROOT, candidate_commit=_clean_head())
        if not _ARTIFACT_ROOT.exists():
            _ARTIFACT_ROOT.mkdir(mode=0o700)
        result = _publish_fixed_artifact(root=_ARTIFACT_ROOT, final_name=_PLAN_NAME, data=canonical_json(plan).encode("utf-8") + b"\n")
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    if args.command == "acquire-and-run":
        current_head = _clean_head()
        plan = load_nautilus_v065_plan((_ARTIFACT_ROOT / _PLAN_NAME).resolve())
        _verify_formal_candidate(plan, current_head)
        result = _commit_formal_ceremony(plan)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_UNKNOWN")


if __name__ == "__main__":
    raise SystemExit(main())
