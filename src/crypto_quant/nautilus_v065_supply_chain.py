"""Pinned dependency and receipt verification for the v0.65 Nautilus spike."""

import base64
import copy
import hashlib
import json
import os
import re
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from .canonical import canonical_json
from .challenger_replacement_plan import ChallengerReplacementPlanError, _strict_json_bytes
from .errors import CanonicalizationError
from .nautilus_v065_plan import NautilusV065PlanError, _read_plan_bytes


_SCHEMA = "nautilus-supply-chain-receipt-v2.schema.json"
_ROOT = Path(__file__).resolve().parents[2]
_LOCK_RELATIVE = Path("sandboxes/nautilus-v065/uv.lock")
_WHEEL = "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl"
_WHEEL_SHA = "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079"
_WHEEL_SIZE = 156035900
_SELECTED_FILENAMES = frozenset(
    {
        "click-8.4.2-py3-none-any.whl",
        "fsspec-2026.2.0-py3-none-any.whl",
        "msgspec-0.21.1-cp312-cp312-macosx_11_0_arm64.whl",
        _WHEEL,
        "numpy-2.5.2-cp312-cp312-macosx_14_0_arm64.whl",
        "pandas-3.0.5-cp312-cp312-macosx_11_0_arm64.whl",
        "portion-2.6.2-py3-none-any.whl",
        "pyarrow-25.0.1-cp312-cp312-macosx_12_0_arm64.whl",
        "python_dateutil-2.9.0.post0-py2.py3-none-any.whl",
        "pytz-2026.3.post1-py2.py3-none-any.whl",
        "six-1.17.0-py2.py3-none-any.whl",
        "sortedcontainers-2.4.0-py2.py3-none-any.whl",
        "tqdm-4.70.0-py3-none-any.whl",
        "uvloop-0.22.1-cp312-cp312-macosx_10_13_universal2.whl",
    }
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TRANSCRIPT_FIELDS = frozenset(
    {"name", "argv", "exit_code", "executable_path"}
    | {f"executable_{field}_{side}" for side in ("before", "after") for field in ("device", "inode", "mode", "size", "sha256")}
    | {f"{stream}_{field}" for stream in ("stdout", "stderr") for field in ("encoding", "bytes", "size", "sha256")}
)
_DIST_RE = re.compile(
    r'\{ url = "(?P<url>https://files\.pythonhosted\.org/[^"]+\.whl)", '
    r'hash = "sha256:(?P<sha>[0-9a-f]{64})", size = (?P<size>[1-9][0-9]*)'
)


class NautilusV065SupplyChainError(ValueError):
    """The v0.65 supply-chain boundary failed closed."""

    def __init__(
        self,
        reason_code: str,
        *,
        evidence: Optional[Mapping[str, Any]] = None,
    ):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.evidence = None if evidence is None else copy.deepcopy(dict(evidence))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _exact_root(repository_root: Path) -> Path:
    root = Path(repository_root)
    if not root.is_absolute() or not root.is_dir():
        raise NautilusV065SupplyChainError("NAUTILUS_V065_REPOSITORY_ROOT_INVALID")
    return root


def _scalar(text: str, name: str) -> str:
    match = re.search(r"^" + re.escape(name) + r" = (.+)$", text, re.MULTILINE)
    if match is None:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_FORMAT_INVALID")
    return match.group(1).strip().strip('"')


def _locked_distributions(lock_text: str) -> Tuple[Dict[str, Any], ...]:
    result = []
    for block in lock_text.split("[[package]]")[1:]:
        name_match = re.search(r'^name = "([^"]+)"$', block, re.MULTILINE)
        version_match = re.search(r'^version = "([^"]+)"$', block, re.MULTILINE)
        if name_match is None or version_match is None or "source = { virtual" in block:
            continue
        source = re.search(r'^source = \{ registry = "([^"]+)" \}$', block, re.MULTILINE)
        if source is None or source.group(1) != "https://pypi.org/simple":
            raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_SOURCE_INVALID")
        for match in _DIST_RE.finditer(block):
            filename = Path(urlparse(match.group("url")).path).name
            if filename not in _SELECTED_FILENAMES:
                continue
            result.append(
                {
                    "name": name_match.group(1),
                    "version": version_match.group(1),
                    "filename": filename,
                    "size": int(match.group("size")),
                    "sha256": match.group("sha"),
                    "source_origin": "https://files.pythonhosted.org",
                }
            )
    ordered = tuple(sorted(result, key=lambda item: (item["name"], item["filename"])))
    if {item["filename"] for item in ordered} != _SELECTED_FILENAMES:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_DISTRIBUTIONS_MISSING")
    top = [item for item in ordered if item["filename"] == _WHEEL]
    if (
        len(top) != 1
        or top[0]["name"] != "nautilus-trader"
        or top[0]["version"] != "1.230.0"
        or top[0]["size"] != _WHEEL_SIZE
        or top[0]["sha256"] != _WHEEL_SHA
    ):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_CANDIDATE_WHEEL_INVALID")
    if len(ordered) < 2:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_DISTRIBUTIONS_MISSING")
    return ordered


def build_nautilus_v065_dependency_lock(*, repository_root: Path) -> Dict[str, Any]:
    """Reconstruct the exact isolated uv dependency inventory without importing it."""

    root = _exact_root(repository_root)
    path = root / _LOCK_RELATIVE
    if not path.is_file() or path.is_symlink():
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_FILE_INVALID")
    try:
        body = path.read_bytes()
        text = body.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_FILE_INVALID") from error
    version = _scalar(text, "version")
    revision = _scalar(text, "revision")
    requires_python = _scalar(text, "requires-python")
    if version != "1" or not revision.isdigit() or requires_python != "==3.12.*":
        raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_FORMAT_INVALID")
    if not re.search(
        r'name = "nautilus-trader"[\s\S]*?version = "1\.230\.0"[\s\S]*?source = \{ registry = "https://pypi\.org/simple" \}',
        text,
    ):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_CANDIDATE_VERSION_INVALID")
    return {
        "format": "uv.lock",
        "version": 1,
        "revision": int(revision),
        "requires_python": requires_python,
        "path": str(_LOCK_RELATIVE),
        "file_sha256": hashlib.sha256(body).hexdigest(),
        "distributions": list(_locked_distributions(text)),
    }


def supply_chain_receipt_hash(payload: Mapping[str, Any]) -> str:
    """Return the receipt digest with both derived identity fields zeroed."""

    material = copy.deepcopy(dict(payload))
    prefix = "nautilus_v065_supply_chain_failure_" if material.get("status") == "SUPPLY_CHAIN_ACQUISITION_FAILED" else "nautilus_v065_supply_chain_"
    material["receipt_id"] = prefix + "0" * 64
    material["receipt_hash"] = "0" * 64
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def _decode_transcript(value: Mapping[str, Any], prefix: str) -> bytes:
    encoding = value[prefix + "_encoding"]
    content = value[prefix + "_bytes"]
    try:
        if encoding == "utf-8":
            raw = content.encode("utf-8")
        elif encoding == "base64":
            raw = base64.b64decode(content.encode("ascii"), validate=True)
        else:
            raise ValueError
    except (UnicodeError, ValueError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_TRANSCRIPT_INVALID") from error
    if (
        len(raw) != value[prefix + "_size"]
        or hashlib.sha256(raw).hexdigest() != value[prefix + "_sha256"]
    ):
        raise NautilusV065SupplyChainError("NAUTILUS_V065_TRANSCRIPT_HASH_MISMATCH")
    return raw


def _validate_receipt(payload: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        if tuple(_validator().iter_errors(payload)):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_SCHEMA_INVALID")
        expected_lock = build_nautilus_v065_dependency_lock(repository_root=_ROOT)
        if payload["dependency_lock"] != expected_lock:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_LOCK_SEMANTIC_MISMATCH")
        if payload["status"] == "SUPPLY_CHAIN_ACQUISITION_FAILED":
            expected_commands = [
                "uv_version", "python_version", "git_version", "gh_version",
                "official_tag", "license", "slsa", "offline_venv",
                "offline_sync", "offline_import",
            ]
            if payload["failure"]["completed_transcript_count"] != len(payload["transcripts"]):
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
            if [item.get("name") for item in payload["transcripts"]] != expected_commands[:len(payload["transcripts"])]:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
            for transcript in payload["transcripts"]:
                if set(transcript) != _TRANSCRIPT_FIELDS or transcript["exit_code"] != 0:
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
                _decode_transcript(transcript, "stdout")
                _decode_transcript(transcript, "stderr")
            failed = payload["failure"]["failed_command"]
            if failed is not None:
                if set(failed) != _TRANSCRIPT_FIELDS or not isinstance(failed["exit_code"], int) or failed["exit_code"] == 0:
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
                if len(payload["transcripts"]) >= len(expected_commands) or failed["name"] != expected_commands[len(payload["transcripts"])]:
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
                _decode_transcript(failed, "stdout")
                _decode_transcript(failed, "stderr")
            if any(payload["authority_counters"].values()):
                raise NautilusV065SupplyChainError("NAUTILUS_V065_FAILURE_RECEIPT_INVALID")
            digest = supply_chain_receipt_hash(payload)
            if payload["receipt_hash"] != digest or payload["receipt_id"] != "nautilus_v065_supply_chain_failure_" + digest:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_HASH_MISMATCH")
            return copy.deepcopy(dict(payload))
        if payload["verified_files"] != expected_lock["distributions"]:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_VERIFIED_FILES_MISMATCH")
        expected_commands = [
            "uv_version",
            "python_version",
            "git_version",
            "gh_version",
            "official_tag",
            "license",
            "slsa",
            "offline_venv",
            "offline_sync",
            "offline_import",
        ]
        if [item["name"] for item in payload["transcripts"]] != expected_commands:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_TRANSCRIPT_ORDER_INVALID")
        for transcript in payload["transcripts"]:
            _decode_transcript(transcript, "stdout")
            _decode_transcript(transcript, "stderr")
            for field in ("device", "inode", "mode", "size", "sha256"):
                if transcript[f"executable_{field}_before"] != transcript[f"executable_{field}_after"]:
                    raise NautilusV065SupplyChainError("NAUTILUS_V065_EXECUTABLE_CHANGED")
        for tool in payload["tools"]:
            if tool["executable_sha256_before"] != tool["executable_sha256_after"]:
                raise NautilusV065SupplyChainError("NAUTILUS_V065_TOOL_IDENTITY_CHANGED")
        digest = supply_chain_receipt_hash(payload)
        if payload["receipt_hash"] != digest or payload["receipt_id"] != "nautilus_v065_supply_chain_" + digest:
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_HASH_MISMATCH")
    except NautilusV065SupplyChainError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_INVALID") from error
    return copy.deepcopy(dict(payload))


def load_nautilus_v065_supply_chain_receipt(path: Path) -> Dict[str, Any]:
    """Load a canonical owner-controlled receipt and replay its exact hashes."""

    requested = Path(path)
    try:
        before = requested.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
        ):
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_PATH_INVALID")
        body = _read_plan_bytes(requested)
    except NautilusV065SupplyChainError:
        raise
    except (NautilusV065PlanError, OSError, ValueError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_PATH_INVALID") from error
    try:
        payload = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_JSON_INVALID") from error
    try:
        if body != canonical_json(payload).encode("utf-8") + b"\n":
            raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_NOT_CANONICAL")
    except (CanonicalizationError, RecursionError) as error:
        raise NautilusV065SupplyChainError("NAUTILUS_V065_RECEIPT_JSON_INVALID") from error
    return _validate_receipt(payload)
