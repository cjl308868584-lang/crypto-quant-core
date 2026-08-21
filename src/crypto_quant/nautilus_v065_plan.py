"""Immutable preregistration for the isolated v0.65 NautilusTrader spike."""

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "nautilus-e2e-spike-plan-v1.schema.json"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAX_PLAN_BYTES = 4 * 1024 * 1024
_V064_COMMIT = "c4f6ea213077850a8fc8b9bd3392f1a4bac466f9"
_LOWER_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ZERO_HASH = "0" * 64

_FOUNDATION = {
    "release_tag": "v0.64.0",
    "peeled_commit": _V064_COMMIT,
    "package_version": "0.64.0",
    "manifest_version": "1.58.0",
    "build_input_tree_hash": "a2a85267fb424b793fac538df40a55be33e900621cb877b1aa1303f16b134344",
    "manifest_hash": "6d32f81a3f9b558f1aa911b1d8d49b9d51491a9ac720675ee2d1cff88186b760",
    "manifest_file_sha256": "038cf827b84ff47b596bd1f3ab72e370ffb17a64a5e6e36264c952769b32abca",
}

_PREDECESSOR = {
    "release_tag": "v0.63.0",
    "peeled_commit": "df91e19240df14839125608422489adf3b902e76",
    "dependency_lock_path": (
        "artifacts/nautilus-sandbox/"
        "nautilus-sandbox-dependency-lock-v0.63.0.json"
    ),
    "dependency_lock_file_sha256": (
        "ed0342ea4274026b6d936b5489f215eb44b4ae5e8ba651b69f3ed01db09230ee"
    ),
    "comparison_path": (
        "artifacts/nautilus-sandbox/"
        "nautilus-sandbox-comparison-v0.63.0.json"
    ),
    "comparison_file_sha256": (
        "88eb4df9cd37e31fca0e636b2ebcf077ddacb33a1eb9877d5e318f04a9a903be"
    ),
    "conclusion": "INCONCLUSIVE_BLOCKED",
    "reason_code": "SUPPLY_CHAIN_FETCH_NOT_MACHINE_REPLAYABLE",
    "interpretation": "NO_ENGINE_OR_GOLDEN_COMPATIBILITY_RESULT",
}

_CANDIDATE = {
    "package": "nautilus_trader",
    "version": "1.230.0",
    "requires_python": ">=3.12,<3.15",
    "official_tag": "v1.230.0",
    "tag_object": "112d335088ec11cdd1d60038b16c8fe56406aead",
    "peeled_commit": "8160730c7c550480b0a439fb11086a4c4de15f0b",
    "wheel_filename": (
        "nautilus_trader-1.230.0-cp312-cp312-macosx_15_0_arm64.whl"
    ),
    "wheel_size": 156035900,
    "wheel_sha256": (
        "033f6207d1c52095d64a7644f43b90cab939c2038044db70a4165f2acef3d079"
    ),
    "license_expression": "LGPL-3.0-or-later",
    "license_sha256": (
        "ee907919ec88c9c017b1f8b608db20960b6598aefcc4fe58820bde955d65ed3c"
    ),
    "operating_system": "macOS",
    "operating_system_major": 15,
    "machine": "arm64",
    "python_implementation": "CPython",
    "python_minor": "3.12",
}

_SCENARIOS = [
    "IMMEDIATE_FULL",
    "PARTIAL_THEN_FULL",
    "BELOW_MINIMUM_REJECTED",
    "FRESH_PROCESS_REPLAY",
]

_DIFFERENCE_CLASSES = [
    "EXACT_MATCH",
    "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE",
    "ROUNDING_POLICY_DIFFERENCE",
    "FILL_MODEL_DIFFERENCE",
    "FEE_MODEL_DIFFERENCE",
    "POSITION_ACCOUNTING_DIFFERENCE",
    "PNL_ACCOUNTING_DIFFERENCE",
    "RESTART_SEMANTICS_DIFFERENCE",
    "UNSUPPORTED_INSTRUMENT_RULE",
    "SUPPLY_CHAIN_OR_LICENSE_FAILURE",
    "SAFETY_BOUNDARY_VIOLATION",
    "INVALID_OR_INCOMPLETE_EVIDENCE",
]

_TERMINAL_CONCLUSIONS = [
    "ADOPT_FOR_PREREGISTERED_SHADOW",
    "REJECT_KEEP_CURRENT_CORE",
    "INCONCLUSIVE_KEEP_CURRENT_CORE",
]

_ADOPTION_GATES = {
    "exact_supply_chain": True,
    "slsa_attestation": True,
    "license_verified": True,
    "golden_scenarios": True,
    "zero_safety_counters": True,
    "fresh_process_replay": True,
    "no_unresolved_economic_difference": True,
    "critical_important_review_zero": True,
    "allowed_adopt_difference_classes": [
        "EXACT_MATCH",
        "EXPECTED_ENGINE_REPRESENTATION_DIFFERENCE",
    ],
    "adopt_next_action": "PREREGISTERED_SHADOW_DESIGN_ONLY",
    "first_final_is_permanent": True,
}

_AUTHORITY = {
    "production_activation": False,
    "runtime_install_authorized": False,
    "sandbox_service_install_authorized": False,
    "live_adapter_allowed": False,
    "credentials_allowed": False,
    "market_requests_allowed_during_sandbox": False,
    "account_requests_allowed": False,
    "broker_requests_allowed": False,
    "real_orders_allowed": False,
    "production_state_writes_allowed": False,
    "runner_or_scheduler_invocation_allowed": False,
}

_WARNINGS = [
    "V0_63_INCONCLUSIVE_IS_NOT_A_REJECTION",
    "FORMAL_ACQUISITION_NOT_EXECUTED",
    "CURRENT_RESEARCH_FACT_SOURCES_UNCHANGED",
    "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
    "NO_INSTALL_CREDENTIAL_ORDER_OR_CANARY_AUTHORITY",
]


class NautilusV065PlanError(ValueError):
    """The v0.65 preregistration plan failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def nautilus_v065_plan_hash(plan: Mapping[str, Any]) -> str:
    """Hash the plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _plan_identity(plan: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "foundation": plan["foundation"],
        "predecessor": plan["predecessor"],
        "candidate": plan["candidate"],
        "code_lock_candidate": plan["code_lock_candidate"],
        "scenarios": plan["scenarios"],
        "difference_classes": plan["difference_classes"],
        "terminal_conclusions": plan["terminal_conclusions"],
        "adoption_gates": plan["adoption_gates"],
        "authority": plan["authority"],
    }


def _repository(repository_root: Path) -> Path:
    root = Path(repository_root)
    if (
        not root.is_absolute()
        or root != _REPOSITORY_ROOT
        or not root.is_dir()
        or not (root / ".git").exists()
    ):
        raise NautilusV065PlanError("NAUTILUS_V065_REPOSITORY_ROOT_INVALID")
    return root


def _git(
    root: Path,
    *args: str,
    input_bytes: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "LANG": "C",
        "LC_ALL": "C",
    }
    try:
        return subprocess.run(
            ["/usr/bin/git", *args],
            cwd=root,
            env=environment,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise NautilusV065PlanError("NAUTILUS_V065_GIT_IDENTITY_INVALID") from error


def _git_text(root: Path, *args: str) -> str:
    result = _git(root, *args)
    if result.returncode != 0:
        raise NautilusV065PlanError("NAUTILUS_V065_GIT_IDENTITY_INVALID")
    try:
        return result.stdout.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise NautilusV065PlanError("NAUTILUS_V065_GIT_IDENTITY_INVALID") from error


def _verify_frozen_files(root: Path) -> None:
    for path, expected in (
        (
            _PREDECESSOR["dependency_lock_path"],
            _PREDECESSOR["dependency_lock_file_sha256"],
        ),
        (
            _PREDECESSOR["comparison_path"],
            _PREDECESSOR["comparison_file_sha256"],
        ),
    ):
        result = _git(root, "show", "v0.63.0:" + path)
        if result.returncode != 0 or hashlib.sha256(result.stdout).hexdigest() != expected:
            raise NautilusV065PlanError("NAUTILUS_V065_PREDECESSOR_IDENTITY_INVALID")
    manifest = _git(root, "show", "v0.64.0:config/evaluator-build-manifest-v1.json")
    if (
        manifest.returncode != 0
        or hashlib.sha256(manifest.stdout).hexdigest()
        != _FOUNDATION["manifest_file_sha256"]
    ):
        raise NautilusV065PlanError("NAUTILUS_V065_FOUNDATION_IDENTITY_INVALID")


def build_nautilus_v065_plan(
    *, repository_root: Path, candidate_commit: str
) -> Dict[str, Any]:
    """Build a side-effect-free preregistration plan from reviewed Git identity."""

    root = _repository(repository_root)
    if not isinstance(candidate_commit, str) or not _LOWER_COMMIT.fullmatch(
        candidate_commit
    ):
        raise NautilusV065PlanError("NAUTILUS_V065_CANDIDATE_COMMIT_INVALID")
    available = _git(root, "cat-file", "-e", candidate_commit + "^{commit}")
    if available.returncode != 0:
        raise NautilusV065PlanError("NAUTILUS_V065_CANDIDATE_COMMIT_UNAVAILABLE")
    ancestor = _git(root, "merge-base", "--is-ancestor", _V064_COMMIT, candidate_commit)
    if ancestor.returncode != 0:
        raise NautilusV065PlanError(
            "NAUTILUS_V065_CANDIDATE_NOT_V064_DESCENDANT"
        )
    tree = _git_text(root, "rev-parse", candidate_commit + "^{tree}")
    if not _LOWER_COMMIT.fullmatch(tree):
        raise NautilusV065PlanError("NAUTILUS_V065_CANDIDATE_TREE_INVALID")
    if _git_text(root, "rev-parse", "v0.64.0^{}") != _V064_COMMIT:
        raise NautilusV065PlanError("NAUTILUS_V065_FOUNDATION_IDENTITY_INVALID")
    if _git_text(root, "rev-parse", "v0.63.0^{}") != _PREDECESSOR["peeled_commit"]:
        raise NautilusV065PlanError("NAUTILUS_V065_PREDECESSOR_IDENTITY_INVALID")
    _verify_frozen_files(root)

    plan: Dict[str, Any] = {
        "$schema": "./nautilus-e2e-spike-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "nautilus_v065_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "foundation": copy.deepcopy(_FOUNDATION),
        "predecessor": copy.deepcopy(_PREDECESSOR),
        "candidate": copy.deepcopy(_CANDIDATE),
        "code_lock_candidate": {
            "commit": candidate_commit,
            "tree": tree,
            "foundation_ancestor": _V064_COMMIT,
        },
        "scenarios": list(_SCENARIOS),
        "difference_classes": list(_DIFFERENCE_CLASSES),
        "terminal_conclusions": list(_TERMINAL_CONCLUSIONS),
        "adoption_gates": copy.deepcopy(_ADOPTION_GATES),
        "authority": copy.deepcopy(_AUTHORITY),
        "status": "SPIKE_PLAN_PREREGISTERED_NOT_EXECUTED",
        "warnings": list(_WARNINGS),
    }
    plan["plan_id"] = stable_id("nautilus_v065_plan", _plan_identity(plan))
    plan["plan_hash"] = nautilus_v065_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_SCHEMA_INVALID")
    return copy.deepcopy(plan)


def _required_open_flags() -> int:
    flags = os.O_RDONLY
    for name in ("O_NOFOLLOW", "O_NONBLOCK"):
        value = getattr(os, name, None)
        if not isinstance(value, int) or value == 0:
            raise NautilusV065PlanError("NAUTILUS_V065_PLATFORM_UNSUPPORTED")
        flags |= value
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if isinstance(cloexec, int):
        flags |= cloexec
    return flags


def _trusted_stat(value: os.stat_result, *, size: Optional[int] = None) -> bool:
    mode = stat.S_IMODE(value.st_mode)
    return (
        stat.S_ISREG(value.st_mode)
        and value.st_uid == os.geteuid()
        and value.st_nlink == 1
        and mode & 0o022 == 0
        and mode & 0o400 != 0
        and value.st_size > 0
        and value.st_size <= _MAX_PLAN_BYTES
        and (size is None or value.st_size == size)
    )


def _read_plan_bytes(path: Path) -> bytes:
    if not path.is_absolute():
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
    try:
        before = path.lstat()
    except (OSError, ValueError) as error:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID") from error
    if not _trusted_stat(before):
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
    try:
        descriptor = os.open(path, _required_open_flags())
    except OSError as error:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID") from error
    primary: Optional[BaseException] = None
    try:
        opened = os.fstat(descriptor)
        if (
            not _trusted_stat(opened, size=before.st_size)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
        chunks = []
        offset = 0
        while offset < opened.st_size:
            try:
                chunk = os.pread(descriptor, min(65536, opened.st_size - offset), offset)
            except InterruptedError:
                continue
            if not chunk:
                raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
            chunks.append(chunk)
            offset += len(chunk)
        if os.pread(descriptor, 1, opened.st_size):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
        after = os.fstat(descriptor)
        if (
            not _trusted_stat(after, size=opened.st_size)
            or (
                after.st_dev,
                after.st_ino,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            != (
                opened.st_dev,
                opened.st_ino,
                opened.st_mtime_ns,
                opened.st_ctime_ns,
            )
        ):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
        attached = path.lstat()
        if (
            not _trusted_stat(attached, size=opened.st_size)
            or (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID")
        return b"".join(chunks)
    except BaseException as error:
        primary = error
        if isinstance(error, NautilusV065PlanError):
            raise
        if isinstance(error, OSError):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_PATH_INVALID") from error
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as close_error:
            if primary is None:
                raise NautilusV065PlanError("NAUTILUS_V065_PLAN_CLOSE_FAILED") from close_error
            try:
                setattr(primary, "close_error", close_error)
            except Exception:
                pass


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return "NAUTILUS_V065_PLAN_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return "NAUTILUS_V065_PLAN_JSON_FLOAT_FORBIDDEN"
    return "NAUTILUS_V065_PLAN_JSON_INVALID"


def load_nautilus_v065_plan(path: Path) -> Dict[str, Any]:
    """Load and replay one owner-controlled canonical preregistration plan."""

    body = _read_plan_bytes(Path(path))
    try:
        plan = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise NautilusV065PlanError(_mapped_json_error(error)) from error
    try:
        expected_bytes = canonical_json(plan).encode("utf-8") + b"\n"
    except (CanonicalizationError, RecursionError) as error:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_JSON_INVALID") from error
    if body != expected_bytes:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_NOT_CANONICAL")
    if tuple(_validator().iter_errors(plan)):
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_SCHEMA_INVALID")
    try:
        if plan["plan_hash"] != nautilus_v065_plan_hash(plan):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_HASH_MISMATCH")
        if plan["plan_id"] != stable_id("nautilus_v065_plan", _plan_identity(plan)):
            raise NautilusV065PlanError("NAUTILUS_V065_PLAN_ID_MISMATCH")
        expected = build_nautilus_v065_plan(
            repository_root=_REPOSITORY_ROOT,
            candidate_commit=plan["code_lock_candidate"]["commit"],
        )
    except NautilusV065PlanError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_SEMANTIC_INVALID") from error
    if plan != expected:
        raise NautilusV065PlanError("NAUTILUS_V065_PLAN_SEMANTIC_MISMATCH")
    return copy.deepcopy(plan)
