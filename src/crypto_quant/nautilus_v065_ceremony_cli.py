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
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
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
    load_nautilus_v065_request,
    load_nautilus_v065_result,
    verify_nautilus_v065_result,
)
from .nautilus_v065_evidence import (
    build_nautilus_v065_execution_failure_comparison,
    build_nautilus_v065_supply_failure_comparison,
    compare_nautilus_v065,
    verify_nautilus_v065_comparison,
)
from .nautilus_v065_plan import build_nautilus_v065_plan, load_nautilus_v065_plan
from .nautilus_v065_supply_chain import (
    _OFFLINE_IMPORT_CODE,
    NautilusV065SupplyChainError,
    build_nautilus_v065_dependency_lock,
    load_nautilus_v065_supply_chain_receipt,
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
_COMPLETE_NAME = "nautilus-sandbox-complete-v0.65.0.json"
_FINAL_NAMES = frozenset(
    {
        _PLAN_NAME, _RECEIPT_NAME, _REQUEST_NAME, _FIRST_RESULT_NAME,
        _REPLAY_RESULT_NAME, _COMPARISON_NAME, _COMPLETE_NAME,
    }
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
        return [str(_find_executable("curl")), "--fail", "--silent", "--show-error", "--proto", "=https", "https://raw.githubusercontent.com/nautechsystems/nautilus_trader/8160730c7c550480b0a439fb11086a4c4de15f0b/LICENSE"]
    if name == "pypi_version":
        return [
            str(_find_executable("curl")), "--fail", "--silent", "--show-error",
            "--proto", "=https", "https://pypi.org/pypi/nautilus_trader/1.230.0/json",
        ]
    if workspace is None:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_WORKSPACE_REQUIRED")
    wheelhouse = workspace / "wheelhouse"
    venv = workspace / "venv"
    if name.startswith("download:"):
        filename = name.removeprefix("download:")
        spec = _download_specs().get(filename)
        if spec is None:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_DOWNLOAD_URL_MISSING")
        url, size = spec
        return [
            str(_find_executable("curl")), "--fail", "--silent", "--show-error",
            "--proto", "=https", "--max-filesize", str(size),
            "--output", str(wheelhouse / filename),
            "--write-out", "%{http_code} %{url_effective}\n", url,
        ]
    if name == "slsa":
        return [str(_find_executable("gh")), "attestation", "verify", str(wheelhouse / _WHEEL), "--repo", "nautechsystems/nautilus_trader"]
    if name == "offline_venv":
        return [str(_find_executable("uv")), "venv", "--offline", "--python", str(_find_executable("python")), str(venv)]
    if name == "offline_sync":
        return [str(_find_executable("uv")), "pip", "install", "--offline", "--python", str(venv / "bin" / "python"), "--find-links", str(wheelhouse), "nautilus_trader==1.230.0"]
    if name == "offline_import":
        return [str(venv / "bin" / "python"), "-I", "-c", _OFFLINE_IMPORT_CODE]
    raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_UNKNOWN")


def _encoded_output(raw: bytes) -> tuple[str, str]:
    try:
        return "utf-8", raw.decode("utf-8")
    except UnicodeDecodeError:
        return "base64", base64.b64encode(raw).decode("ascii")


def _run_bounded_command(
    argv: Sequence[str], *, cwd: Path, environment: Mapping[str, str], timeout: int
) -> tuple[int, bytes, bytes, bool]:
    process = subprocess.Popen(
        list(argv), cwd=cwd, env=dict(environment), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
        start_new_session=True,
    )
    if process.stdout is None or process.stderr is None:
        process.kill()
        process.wait()
        raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_FAILED")
    selector = selectors.DefaultSelector()
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    for stream in streams:
        selector.register(stream, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    timed_out = False
    drain_deadline: Optional[float] = None

    def terminate() -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        while selector.get_map():
            now = time.monotonic()
            remaining = deadline - now
            if remaining <= 0 and not timed_out:
                timed_out = True
                terminate()
                drain_deadline = now + 0.25
            if timed_out and drain_deadline is not None and now >= drain_deadline:
                break
            wait_for = (
                max(0.0, min(0.1, remaining))
                if not timed_out
                else max(0.0, min(0.1, drain_deadline - now))
            )
            for key, _mask in selector.select(wait_for):
                stream = key.fileobj
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    selector.unregister(stream)
                    continue
                buffer = streams[stream]
                if len(buffer) + len(chunk) > _MAX_OUTPUT:
                    terminate()
                    process.wait()
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_OUTPUT_LIMIT")
                buffer.extend(chunk)
        returncode = process.wait()
        return returncode, bytes(streams[process.stdout]), bytes(streams[process.stderr]), timed_out
    finally:
        terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        selector.close()
        process.stdout.close()
        process.stderr.close()


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
    started_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    try:
        returncode, stdout, stderr, timed_out = _run_bounded_command(
            argv,
            cwd=workspace if workspace is not None else _ROOT,
            environment=environment,
            timeout=120,
        )
    except OSError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_FAILED") from error
    completed_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    after = _command_executable_identity(name, executable, workspace)
    if before != after:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_CHANGED")
    stdout_encoding, stdout_text = _encoded_output(stdout)
    stderr_encoding, stderr_text = _encoded_output(stderr)
    record = {
        "name": name,
        "argv": argv,
        "exit_code": returncode,
        "environment": environment,
        "started_at": started_at,
        "completed_at": completed_at,
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
    if timed_out:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_COMMAND_TIMEOUT", evidence=record)
    if returncode != 0:
        reason = {
            "official_tag": "NAUTILUS_V065_TAG_FETCH_FAILED",
            "license": "NAUTILUS_V065_LICENSE_FETCH_FAILED",
            "pypi_version": "NAUTILUS_V065_PYPI_METADATA_FETCH_FAILED",
            "slsa": "NAUTILUS_V065_SLSA_VERIFICATION_FAILED",
            "offline_venv": "NAUTILUS_V065_OFFLINE_ENV_FAILED",
            "offline_sync": "NAUTILUS_V065_OFFLINE_SYNC_FAILED",
            "offline_import": "NAUTILUS_V065_OFFLINE_IMPORT_FAILED",
        }.get(
            name,
            "NAUTILUS_V065_DOWNLOAD_FAILED"
            if name.startswith("download:")
            else "NAUTILUS_V065_COMMAND_NONZERO",
        )
        raise NautilusV065SupplyChainError(reason, evidence=record)
    return record


def _download_specs() -> Dict[str, tuple[str, int]]:
    text = (_ROOT / "sandboxes/nautilus-v065/uv.lock").read_text(encoding="utf-8")
    return {
        url.rsplit("/", 1)[1]: (url, int(size))
        for url, size in re.findall(
            r'url = "(https://files\.pythonhosted\.org/[^"]+\.whl)", hash = "sha256:[0-9a-f]{64}", size = ([1-9][0-9]*)',
            text,
        )
    }


def _download_urls() -> Dict[str, str]:
    return {filename: spec[0] for filename, spec in _download_specs().items()}


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


def _verify_pypi_version_transcript(
    record: Mapping[str, Any], lock: Mapping[str, Any]
) -> None:
    try:
        if record["stdout_encoding"] != "utf-8":
            raise ValueError
        payload = json.loads(record["stdout_bytes"])
        candidate = next(
            item for item in lock["distributions"]
            if item["filename"] == _WHEEL
        )
        expected_url = _download_urls()[_WHEEL]
        matches = [
            item for item in payload["urls"]
            if item.get("filename") == _WHEEL
        ]
        if (
            payload["info"]["version"] != "1.230.0"
            or payload["info"].get("requires_python") != ">=3.12,<3.15"
            or len(matches) != 1
            or matches[0].get("size") != candidate["size"]
            or matches[0].get("url") != expected_url
            or matches[0].get("digests", {}).get("sha256") != candidate["sha256"]
        ):
            raise ValueError
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_PYPI_METADATA_MISMATCH"
        ) from error


def _verify_download_transcript(
    record: Mapping[str, Any], item: Mapping[str, Any], wheelhouse: Path
) -> Dict[str, Any]:
    filename = item["filename"]
    expected_url = _download_urls().get(filename)
    if (
        expected_url is None
        or record.get("stdout_encoding") != "utf-8"
        or record.get("stdout_bytes") != "200 " + expected_url + "\n"
        or record.get("stderr_size") != 0
    ):
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_DOWNLOAD_IDENTITY_MISMATCH"
        )
    target = wheelhouse / filename
    try:
        before = target.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_size != item["size"]
        ):
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_DOWNLOAD_IDENTITY_MISMATCH"
            )
        flags = os.O_RDONLY | _required_flag("O_NOFOLLOW") | _required_flag("O_NONBLOCK")
        descriptor = os.open(target, flags)
    except NautilusV065SupplyChainError:
        raise
    except OSError as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_DOWNLOAD_IDENTITY_MISMATCH"
        ) from error
    try:
        opened = os.fstat(descriptor)
        attached = target.lstat()
        if (
            (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or (attached.st_dev, attached.st_ino) != (before.st_dev, before.st_ino)
            or _hash_descriptor(descriptor, opened.st_size) != item["sha256"]
        ):
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_DOWNLOAD_HASH_MISMATCH"
            )
    except OSError as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_DOWNLOAD_IDENTITY_MISMATCH"
        ) from error
    finally:
        os.close(descriptor)
    return dict(item)


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

        for name in (
            "uv_version", "python_version", "git_version", "gh_version",
            "pypi_version", "official_tag", "license",
        ):
            capture(name)
        tag_output = transcripts[5]["stdout_bytes"]
        if _TAG_OBJECT not in tag_output or _TAG_COMMIT not in tag_output:
            error = NautilusV065SupplyChainError("NAUTILUS_V065_TAG_IDENTITY_MISMATCH")
            error.completed_transcripts = copy.deepcopy(transcripts)
            raise error
        try:
            _verify_pypi_version_transcript(transcripts[4], lock)
            _verify_license_transcript(transcripts[6])
            verified = []
            for item in lock["distributions"]:
                record = capture("download:" + item["filename"])
                verified.append(_verify_download_transcript(record, item, wheelhouse))
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


def _runner_failure_reason(returncode: int, stdout: bytes, stderr: bytes) -> str:
    if returncode != 0 and not stdout:
        return {
            b"CREDENTIAL_ENV_FORBIDDEN\n": "NAUTILUS_V065_SAFETY_CREDENTIAL_ATTEMPT",
            b"NETWORK_FORBIDDEN\n": "NAUTILUS_V065_SAFETY_NETWORK_ATTEMPT",
            b"SECOND_ENGINE_FORBIDDEN\n": "NAUTILUS_V065_SAFETY_SECOND_ENGINE_ATTEMPT",
        }.get(stderr, "NAUTILUS_V065_RUNNER_FAILED")
    return "NAUTILUS_V065_RUNNER_FAILED"


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
        raise NautilusV065SupplyChainError(
            _runner_failure_reason(result.returncode, result.stdout, result.stderr)
        )
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
    legacy_staging_name = ".v0.65.0.in-progress"
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
        for name in (legacy_staging_name, formal.name):
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
            os.mkdir(formal.name, 0o700, dir_fd=parent_fd)
        except OSError as error:
            raise NautilusV065SupplyChainError(
                "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
            ) from error
        created = os.stat(formal.name, dir_fd=parent_fd, follow_symlinks=False)
        formal_fd = os.open(formal.name, flags, dir_fd=parent_fd)
        try:
            value = os.fstat(formal_fd)
            attached = os.stat(formal.name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(value.st_mode)
                or value.st_uid != os.geteuid()
                or stat.S_IMODE(value.st_mode) != 0o700
                or (value.st_dev, value.st_ino) != (created.st_dev, created.st_ino)
                or (value.st_dev, value.st_ino) != (attached.st_dev, attached.st_ino)
            ):
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_FORMAL_STATE_CONFLICT"
                )
            result = _acquire_and_run(plan=plan, artifact_root=formal)
            _verify_staged_artifact_set(
                formal, formal_fd, result, expected_plan=plan
            )
            _publish_formal_completion_marker(
                formal, formal_fd, result, expected_plan=plan
            )
            os.fsync(formal_fd)
            attached = os.stat(formal.name, dir_fd=parent_fd, follow_symlinks=False)
            if (value.st_dev, value.st_ino) != (attached.st_dev, attached.st_ino):
                raise NautilusV065SupplyChainError(
                    "NAUTILUS_V065_FORMAL_COMMIT_FAILED"
                )
        finally:
            os.close(formal_fd)
        os.fsync(parent_fd)
        _validate_artifact_root(parent, parent_fd, before)
        return result
    finally:
        os.close(parent_fd)


def _verify_staged_artifact_set(
    staging: Path,
    staging_fd: int,
    summary: Mapping[str, Any],
    *,
    expected_plan: Mapping[str, Any],
) -> None:
    try:
        if set(summary) != {"conclusion", "runner_invocation_count"}:
            raise ValueError
        raw_comparison, _identity = _read_final(staging_fd, _COMPARISON_NAME)
        comparison_value = dict(_strict_json_bytes(raw_comparison))
        if raw_comparison != canonical_json(comparison_value).encode("utf-8") + b"\n":
            raise ValueError
        comparison = verify_nautilus_v065_comparison(comparison_value)
        if (
            summary["conclusion"] != comparison["conclusion"]
            or summary["runner_invocation_count"] != comparison["runner_invocation_count"]
        ):
            raise ValueError
        mode = comparison["mode"]
        if mode == "SUPPLY_CHAIN_FAILURE":
            expected = {_RECEIPT_NAME, _COMPARISON_NAME}
        elif mode == "EXECUTION_FAILURE":
            expected = {_RECEIPT_NAME, _REQUEST_NAME, _COMPARISON_NAME}
            if comparison["bindings"]["first_result_id"] is not None:
                expected.add(_FIRST_RESULT_NAME)
        elif mode == "ENGINE_COMPARISON":
            expected = {
                _RECEIPT_NAME, _REQUEST_NAME, _FIRST_RESULT_NAME,
                _REPLAY_RESULT_NAME, _COMPARISON_NAME,
            }
        else:
            raise ValueError
        if set(os.listdir(staging_fd)) != expected:
            raise ValueError
        for name in expected:
            body, _value = _read_final(staging_fd, name)
            parsed = dict(_strict_json_bytes(body))
            if body != canonical_json(parsed).encode("utf-8") + b"\n":
                raise ValueError
        receipt = load_nautilus_v065_supply_chain_receipt(
            (staging / _RECEIPT_NAME).resolve()
        )
        if (
            receipt["plan_id"] != expected_plan["plan_id"]
            or receipt["plan_hash"] != expected_plan["plan_hash"]
        ):
            raise ValueError
        request = None
        first = None
        replay = None
        if _REQUEST_NAME in expected:
            request = load_nautilus_v065_request((staging / _REQUEST_NAME).resolve())
        if _FIRST_RESULT_NAME in expected:
            first = load_nautilus_v065_result((staging / _FIRST_RESULT_NAME).resolve())
        if _REPLAY_RESULT_NAME in expected:
            replay = load_nautilus_v065_result((staging / _REPLAY_RESULT_NAME).resolve())
        bindings = comparison["bindings"]
        actual = {
            "plan_id": receipt["plan_id"],
            "plan_hash": receipt["plan_hash"],
            "receipt_id": receipt["receipt_id"],
            "receipt_hash": receipt["receipt_hash"],
            "request_id": None if request is None else request["request_id"],
            "request_hash": None if request is None else request["request_hash"],
            "current_reference_id": None,
            "current_reference_hash": None,
            "first_result_id": None if first is None else first["result_id"],
            "first_result_hash": None if first is None else first["result_hash"],
            "replay_result_id": None if replay is None else replay["result_id"],
            "replay_result_hash": None if replay is None else replay["result_hash"],
        }
        if request is not None:
            if (
                request["plan_id"] != receipt["plan_id"]
                or request["plan_hash"] != receipt["plan_hash"]
                or request["supply_chain_receipt_id"] != receipt["receipt_id"]
                or request["supply_chain_receipt_hash"] != receipt["receipt_hash"]
            ):
                raise ValueError
            current = build_nautilus_v065_current_reference(request=request)
            actual["current_reference_id"] = current["result_id"]
            actual["current_reference_hash"] = current["result_hash"]
            for result in (first, replay):
                if result is not None and (
                    result["request_id"] != request["request_id"]
                    or result["request_hash"] != request["request_hash"]
                ):
                    raise ValueError
        if mode != "ENGINE_COMPARISON":
            actual["current_reference_id"] = None
            actual["current_reference_hash"] = None
        if bindings != actual:
            raise ValueError
    except (NautilusV065SupplyChainError, NautilusV065ContractError):
        raise
    except (KeyError, TypeError, ValueError, OSError, CanonicalizationError) as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_FORMAL_ARTIFACT_SET_INVALID"
        ) from error


def _publish_formal_completion_marker(
    formal: Path,
    formal_fd: int,
    summary: Mapping[str, Any],
    *,
    expected_plan: Mapping[str, Any],
) -> None:
    try:
        comparison_raw, _identity = _read_final(formal_fd, _COMPARISON_NAME)
        comparison = verify_nautilus_v065_comparison(
            dict(_strict_json_bytes(comparison_raw))
        )
        names = sorted(os.listdir(formal_fd))
        if _COMPLETE_NAME in names:
            raise ValueError
        files = []
        for name in names:
            body, _value = _read_final(formal_fd, name)
            files.append({
                "name": name,
                "size": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            })
        marker = {
            "format": "NAUTILUS_V065_FORMAL_COMPLETION_V1",
            "plan_id": expected_plan["plan_id"],
            "plan_hash": expected_plan["plan_hash"],
            "comparison_id": comparison["comparison_id"],
            "comparison_hash": comparison["comparison_hash"],
            "conclusion": summary["conclusion"],
            "runner_invocation_count": summary["runner_invocation_count"],
            "files": files,
            "marker_hash": "0" * 64,
        }
        marker["marker_hash"] = hashlib.sha256(
            canonical_json(marker).encode("utf-8")
        ).hexdigest()
        body = canonical_json(marker).encode("utf-8") + b"\n"
        _publish_fixed_artifact(root=formal, final_name=_COMPLETE_NAME, data=body)
        replayed, _value = _read_final(formal_fd, _COMPLETE_NAME)
        if replayed != body:
            raise ValueError
    except (NautilusV065SupplyChainError, NautilusV065ContractError):
        raise
    except (KeyError, TypeError, ValueError, OSError, CanonicalizationError) as error:
        raise NautilusV065SupplyChainError(
            "NAUTILUS_V065_FORMAL_COMMIT_FAILED"
        ) from error


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
