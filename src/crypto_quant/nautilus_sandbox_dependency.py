"""Portable verification for the isolated NautilusTrader sandbox supply chain."""

import hashlib
import json
import os
import platform
import re
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .evidence import artifact_self_hash


_SCHEMA = "nautilus-sandbox-dependency-lock-v1.schema.json"
_MAX_BYTES = 2 * 1024 * 1024
_DISTRIBUTION_RE = re.compile(
    r'\{ url = "(?P<url>https://files\.pythonhosted\.org/[^\"]+)", '
    r'hash = "sha256:(?P<sha>[0-9a-f]{64})", size = (?P<size>[1-9][0-9]*)'
)


class NautilusSandboxDependencyError(ValueError):
    """The sandbox dependency boundary failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locked_distributions(lock_text: str) -> Tuple[Dict[str, Any], ...]:
    result = []
    for block in lock_text.split("[[package]]")[1:]:
        name_match = re.search(r'^\s*name = "([^\"]+)"', block, re.MULTILINE)
        version_match = re.search(r'^\s*version = "([^\"]+)"', block, re.MULTILINE)
        if name_match is None or version_match is None:
            continue
        package_name = name_match.group(1)
        if re.search(r'^\s*source = \{ editable = ', block, re.MULTILINE):
            continue
        for match in _DISTRIBUTION_RE.finditer(block):
            url = match.group("url")
            result.append(
                {
                    "name": package_name,
                    "version": version_match.group(1),
                    "filename": Path(urlparse(url).path).name,
                    "size": int(match.group("size")),
                    "sha256": match.group("sha"),
                    "source_origin": "https://files.pythonhosted.org",
                }
            )
    if not result:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_DISTRIBUTIONS_MISSING")
    return tuple(sorted(result, key=lambda item: (item["name"], item["filename"])))


def _identity(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "package": payload["package"],
        "wheel": payload["wheel"],
        "license": payload["license"],
        "platform": payload["platform"],
        "transitive_lock": payload["transitive_lock"],
        "authority": payload["authority"],
        "status": payload["status"],
    }


def dependency_lock_hash(payload: Mapping[str, Any]) -> str:
    """Hash the artifact while excluding only its self-hash field."""

    return artifact_self_hash(payload, "dependency_lock_hash")


def build_nautilus_sandbox_dependency_lock(*, workspace_root: Path) -> Dict[str, Any]:
    """Build the exact portable dependency identity from the committed uv lock."""

    root = Path(workspace_root)
    lock_path = root / "sandboxes" / "nautilus" / "uv.lock"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_FILE_MISSING")
    lock_text = lock_path.read_text(encoding="utf-8")
    version_match = re.search(r"^version = ([0-9]+)$", lock_text, re.MULTILINE)
    if version_match is None:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_FORMAT_INVALID")
    payload: Dict[str, Any] = {
        "$schema": "./nautilus-sandbox-dependency-lock-v1.schema.json",
        "schema_version": "1.0.0",
        "dependency_lock_id": "nautilus_sandbox_dependency_lock_" + "0" * 64,
        "dependency_lock_hash": "0" * 64,
        "package": {
            "name": "nautilus_trader",
            "version": "1.227.0",
            "development_status": "BETA",
            "requires_python": ">=3.12,<3.15",
            "official_tag": "v1.227.0",
            "tag_object": "0ccb5b55879c072a6e07fc7cbe5297c53c378107",
            "peeled_commit": "280ae1762df51a492a4ce71506a40b5c8706def5",
        },
        "wheel": {
            "filename": "nautilus_trader-1.227.0-cp312-cp312-macosx_15_0_arm64.whl",
            "size": 145812901,
            "sha256": "735fbbc0737be8f945ee641aeb0dbf0ea6b4c6111f11f10c244fe198f8158953",
            "python_tag": "cp312",
            "abi_tag": "cp312",
            "platform_tag": "macosx_15_0_arm64",
        },
        "license": {
            "expression": "LGPL-3.0-or-later",
            "path": "LICENSE",
            "git_blob": "5550e2db15f239ea8d3cf54bfa3b035eab8d3174",
            "size": 7651,
            "sha256": "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c",
        },
        "platform": {
            "operating_system": "macOS",
            "minimum_version": "15.0",
            "machine": "arm64",
            "python": "3.12",
            "observed_compatible_machine": "macOS 15.7.5 arm64 CPython 3.12.13",
        },
        "transitive_lock": {
            "path": "sandboxes/nautilus/uv.lock",
            "format": "uv.lock",
            "version": int(version_match.group(1)),
            "file_sha256": _sha256(lock_path),
            "distributions": list(_locked_distributions(lock_text)),
        },
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": False,
            "live_adapter_allowed": False,
            "credentials_allowed": False,
            "network_allowed_during_sandbox_runtime": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "production_state_writes_allowed": False,
        },
        "status": "DEPENDENCY_LOCK_VERIFIED_SANDBOX_ONLY",
    }
    payload["dependency_lock_id"] = stable_id(
        "nautilus_sandbox_dependency_lock", _identity(payload)
    )
    payload["dependency_lock_hash"] = dependency_lock_hash(payload)
    errors = sorted(_validator().iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_SCHEMA_INVALID")
    return payload


def _version_tuple(value: str) -> Tuple[int, ...]:
    match = re.match(r"^(\d+)(?:\.(\d+))?", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.groups(default="0"))


def verify_nautilus_sandbox_dependency_lock(
    payload: Mapping[str, Any],
    *,
    workspace_root: Path,
    machine: Optional[str] = None,
    macos_version: Optional[str] = None,
    check_platform: bool = True,
) -> Dict[str, Any]:
    """Verify exact semantics and, when requested, the local sandbox platform."""

    try:
        errors = sorted(_validator().iter_errors(payload), key=lambda error: list(error.path))
    except Exception as exc:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_SCHEMA_INVALID") from exc
    if errors:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_SCHEMA_INVALID")
    expected = build_nautilus_sandbox_dependency_lock(workspace_root=workspace_root)
    if dict(payload) != expected:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_SEMANTIC_MISMATCH")
    if check_platform:
        selected_machine = machine if machine is not None else platform.machine()
        selected_version = (
            macos_version if macos_version is not None else platform.mac_ver()[0]
        )
        if (
            selected_machine != "arm64"
            or _version_tuple(selected_version) < _version_tuple("15.0")
        ):
            raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_PLATFORM_MISMATCH")
    return expected


def load_nautilus_sandbox_dependency_lock(path: Path) -> Dict[str, Any]:
    """Load an owner-only canonical artifact without enforcing the replay host OS."""

    requested = Path(path)
    if not requested.is_absolute() or requested.is_symlink():
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_UNSAFE_FILE")
    try:
        status = os.stat(requested, follow_symlinks=False)
    except OSError as exc:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_UNSAFE_FILE") from exc
    if (
        not stat.S_ISREG(status.st_mode)
        or status.st_uid != os.getuid()
        or status.st_nlink != 1
        or stat.S_IMODE(status.st_mode) & 0o077
        or status.st_size <= 0
        or status.st_size > _MAX_BYTES
    ):
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_UNSAFE_FILE")
    raw = requested.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_JSON_INVALID") from exc
    if not isinstance(payload, dict) or raw != canonical_json(payload).encode("utf-8"):
        raise NautilusSandboxDependencyError("DEPENDENCY_LOCK_NOT_CANONICAL")
    workspace_root = Path(__file__).resolve().parents[2]
    return verify_nautilus_sandbox_dependency_lock(
        payload,
        workspace_root=workspace_root,
        check_platform=False,
    )
