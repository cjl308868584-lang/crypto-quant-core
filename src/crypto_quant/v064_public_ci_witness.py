"""Strict offline derivation of the bounded v0.64 public Linux witness."""

import copy
import hashlib
import json
import os
import re
import stat
import subprocess
from datetime import datetime
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .evidence import artifact_self_hash
from .v064_public_ci_bundle import (
    build_v064_public_ci_bundle_manifest,
    verify_v064_public_ci_bundle,
)
from .v064_public_ci_witness_cli import _commands


_SCHEMA = "v064-public-ci-witness-v1.schema.json"
_MAX_BYTES = 64 * 1024 * 1024
_PUBLIC_REPOSITORY = "cjl308868584-lang/crypto-quant-v064-public-ci-r3"
_PUBLIC_ROOT = Path("/private/tmp/crypto-quant-v064-public-ci-r3-candidate")


class V064PublicCiWitnessError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _safe_int(value: str) -> int:
    parsed = int(value)
    if parsed < -(1 << 53) + 1 or parsed > (1 << 53) - 1:
        raise ValueError("UNSAFE_INTEGER")
    return parsed


def _json(body: bytes, reason: str) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not 0 < len(body) <= _MAX_BYTES or body.startswith(b"\xef\xbb\xbf") or b"\r" in body:
        raise V064PublicCiWitnessError(reason)

    def pairs(items):
        result = {}
        for key, value in items:
            if not isinstance(key, str) or not key.isascii() or key in result:
                raise ValueError("INVALID_KEY")
            result[key] = value
        return result

    def reject(_value):
        raise ValueError("NON_INTEGER")

    try:
        value = json.loads(
            body.decode("utf-8"), object_pairs_hook=pairs, parse_int=_safe_int,
            parse_float=reject, parse_constant=reject,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise V064PublicCiWitnessError(reason) from error
    if not isinstance(value, Mapping):
        raise V064PublicCiWitnessError(reason)
    return value


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_TIMESTAMP_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_TIMESTAMP_INVALID") from error


def _replay_public_candidate(private_repository: Path, bundle: dict) -> Dict[str, Any]:
    try:
        expected = build_v064_public_ci_bundle_manifest(
            Path(private_repository), bundle["source"]["candidate_commit"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_BUNDLE_INVALID") from error
    if bundle != expected:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_BUNDLE_INVALID")
    result = verify_v064_public_ci_bundle(
        Path(private_repository), bundle["source"]["candidate_commit"], _PUBLIC_ROOT
    )
    return {
        "commit": result["commit"], "tree": result["tree"], "parent_count": 0,
        "manifest_sha256": result["manifest_sha256"],
    }


def _raw(path: str, body: bytes) -> Dict[str, Any]:
    return {"path": path, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def _exact_keys(value: Mapping[str, Any], expected, reason: str) -> None:
    if set(value) != set(expected):
        raise V064PublicCiWitnessError(reason)


def _normalize_job(value: Mapping[str, Any], version: str) -> Dict[str, Any]:
    reason = "V064_PUBLIC_CI_JOB_INVALID"
    _exact_keys(value, ("id", "name", "status", "conclusion", "runner_name", "labels", "started_at", "completed_at", "steps"), reason)
    if value["name"] != "portability (%s)" % version or value["status"] != "completed" or value["conclusion"] != "success":
        raise V064PublicCiWitnessError(reason)
    if not isinstance(value["runner_name"], str) or not value["runner_name"] or value["labels"] != ["ubuntu-latest"]:
        raise V064PublicCiWitnessError(reason)
    started = _timestamp(value["started_at"]); completed = _timestamp(value["completed_at"])
    if completed < started:
        raise V064PublicCiWitnessError(reason)
    steps = value["steps"]
    if not isinstance(steps, list) or not steps:
        raise V064PublicCiWitnessError(reason)
    numbers = set(); normalized = []
    for step in steps:
        if not isinstance(step, Mapping):
            raise V064PublicCiWitnessError(reason)
        _exact_keys(step, ("number", "name", "status", "conclusion"), reason)
        if not isinstance(step["number"], int) or isinstance(step["number"], bool) or step["number"] < 1 or step["number"] in numbers:
            raise V064PublicCiWitnessError(reason)
        numbers.add(step["number"])
        if not isinstance(step["name"], str) or not step["name"] or step["status"] != "completed" or step["conclusion"] != "success":
            raise V064PublicCiWitnessError(reason)
        normalized.append(dict(step))
    if not any(step["name"] == "Run fixed-owner public boundary" for step in normalized):
        raise V064PublicCiWitnessError(reason)
    return {
        "python_version": version, "job_id": value["id"], "name": value["name"],
        "status": value["status"], "conclusion": value["conclusion"],
        "runner_os": "Linux", "started_at": value["started_at"],
        "completed_at": value["completed_at"], "steps": normalized,
    }


def _validate_transcript(transcript: dict, run_id: int, bodies) -> bytes:
    reason = "V064_PUBLIC_CI_TRANSCRIPT_INVALID"
    if not isinstance(transcript, Mapping):
        raise V064PublicCiWitnessError(reason)
    _exact_keys(transcript, ("schema_version", "gh_identity", "commands"), reason)
    if transcript["schema_version"] != "1.0.0" or not isinstance(transcript["commands"], list) or len(transcript["commands"]) != 3:
        raise V064PublicCiWitnessError(reason)
    identity = transcript["gh_identity"]
    if not isinstance(identity, Mapping):
        raise V064PublicCiWitnessError(reason)
    _exact_keys(identity, ("path", "file_sha256", "version_size", "version_sha256"), reason)
    if (
        identity["path"] != "/Users/chenm4/.local/bin/gh"
        or identity["file_sha256"] != "b1d6c442fde99ca27c04e1e74d624895abe37785f4a3e9e9b684bf7586ce4bc8"
        or identity["version_size"] != 79
        or identity["version_sha256"] != "baca303bf2a08915a78b513817a4fc7c754a7bcdd0fce71990e75c5e067688ff"
    ):
        raise V064PublicCiWitnessError(reason)
    for record, name, argv, body in zip(transcript["commands"], ("run_api", "jobs_api", "run_log"), _commands(run_id), bodies):
        if not isinstance(record, Mapping):
            raise V064PublicCiWitnessError(reason)
        _exact_keys(record, ("name", "argv", "exit_code", "stdout_size", "stdout_sha256", "stderr_size", "stderr_sha256"), reason)
        if record != {
            "name": name, "argv": list(argv), "exit_code": 0,
            "stdout_size": len(body), "stdout_sha256": hashlib.sha256(body).hexdigest(),
            "stderr_size": 0, "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        }:
            raise V064PublicCiWitnessError(reason)
    return canonical_json(transcript).encode("utf-8") + b"\n"


def derive_v064_public_ci_witness(*, bundle: dict, run_bytes: bytes, jobs_bytes: bytes, log_bytes: bytes, transcript: dict, private_repository: Path) -> Dict[str, Any]:
    run = _json(run_bytes, "V064_PUBLIC_CI_RUN_INVALID")
    jobs_value = _json(jobs_bytes, "V064_PUBLIC_CI_JOBS_INVALID")
    if run_bytes != canonical_json(run).encode("utf-8") + b"\n":
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_RUN_INVALID")
    if jobs_bytes != canonical_json(jobs_value).encode("utf-8") + b"\n":
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOBS_INVALID")
    candidate = _replay_public_candidate(Path(private_repository), bundle)
    run_keys = ("id", "workflow_id", "run_attempt", "event", "head_branch", "head_sha", "status", "conclusion", "created_at", "updated_at", "path", "repository")
    _exact_keys(run, run_keys, "V064_PUBLIC_CI_RUN_INVALID")
    if run["repository"] != _PUBLIC_REPOSITORY or run["head_sha"] != candidate["commit"] or run["path"] != ".github/workflows/ci.yml" or run["event"] != "push" or run["head_branch"] != "main" or run["run_attempt"] != 1 or run["status"] != "completed" or run["conclusion"] != "success":
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_RUN_INVALID")
    created = _timestamp(run["created_at"]); updated = _timestamp(run["updated_at"])
    if updated < created:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_RUN_INVALID")
    _exact_keys(jobs_value, ("total_count", "jobs"), "V064_PUBLIC_CI_JOBS_INVALID")
    raw_jobs = jobs_value["jobs"]
    if jobs_value["total_count"] != 2 or not isinstance(raw_jobs, list) or len(raw_jobs) != 2:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOBS_INVALID")
    by_name = {}
    for raw_job in raw_jobs:
        if not isinstance(raw_job, Mapping) or not isinstance(raw_job.get("name"), str) or raw_job["name"] in by_name:
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOB_INVALID")
        by_name[raw_job["name"]] = raw_job
    if set(by_name) != {"portability (3.9)", "portability (3.12)"}:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOB_INVALID")
    normalized = [
        _normalize_job(by_name["portability (%s)" % version], version)
        for version in ("3.9", "3.12")
    ]
    if len({job["job_id"] for job in normalized}) != 2:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOB_INVALID")
    if any(
        _timestamp(job["started_at"]) < created
        or _timestamp(job["completed_at"]) > updated
        for job in normalized
    ):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_JOB_INVALID")
    try:
        log = log_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID") from error
    if not log or "\r" in log or len(log_bytes) > _MAX_BYTES:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID")
    markers = (
        "source_candidate_f=" + bundle["source"]["candidate_commit"],
        "public_commit=" + candidate["commit"],
        "manifest_sha256=" + candidate["manifest_sha256"],
        "file_set_sha256=" + bundle["file_set_sha256"],
    )
    parsed_log = {
        "3.9": {"verify": [], "setup": [], "run": []},
        "3.12": {"verify": [], "setup": [], "run": []},
    }
    timestamp_pattern = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z (.*)$")
    for line in log.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or parts[1] not in {
            "Verify closed bundle before repository imports",
            "Run actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
            "Run fixed-owner public boundary",
        }:
            continue
        match = timestamp_pattern.fullmatch(parts[2])
        if match is None:
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID")
        if parts[0] == "portability (3.9)": version = "3.9"
        elif parts[0] == "portability (3.12)": version = "3.12"
        else: raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID")
        if parts[1].startswith("Verify closed"):
            kind = "verify"
        elif parts[1].startswith("Run actions/setup-python@"):
            kind = "setup"
        else:
            kind = "run"
        parsed_log[version][kind].append(match.group(1))
    for index, version in enumerate(("3.9", "3.12")):
        if any(parsed_log[version]["verify"].count(item) != 1 for item in markers):
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID")
        setup_pattern = re.compile(
            r"^Successfully set up CPython \((" + re.escape(version)
            + r"\.[0-9]+)\)$"
        )
        setup_versions = [
            match.group(1) for item in parsed_log[version]["setup"]
            for match in [setup_pattern.fullmatch(item)] if match is not None
        ]
        run_lines = parsed_log[version]["run"]
        python_pattern = re.compile(
            r"^Python (" + re.escape(version) + r"\.[0-9]+)$"
        )
        fixed_owner_versions = [
            match.group(1) for item in run_lines
            for match in [python_pattern.fullmatch(item)] if match is not None
        ]
        tests_pattern = re.compile(r"^Ran 16 tests in [0-9]+(?:\.[0-9]+)?s$")
        if (
            len(setup_versions) != 1
            or len(fixed_owner_versions) != 1
            or setup_versions != fixed_owner_versions
            or sum(bool(tests_pattern.fullmatch(item)) for item in run_lines) != 1
            or run_lines.count("OK") != 1
        ):
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_LOG_INVALID")
        normalized[index]["setup_python_version"] = setup_versions[0]
        normalized[index]["fixed_owner_python_version"] = fixed_owner_versions[0]
    transcript_bytes = _validate_transcript(transcript, run["id"], (run_bytes, jobs_bytes, log_bytes))
    workflow = next((item for item in bundle["files"] if item["path"] == ".github/workflows/ci.yml"), None)
    if workflow is None:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_BUNDLE_INVALID")
    identity = {"private_commit": bundle["source"]["candidate_commit"], "public_commit": candidate["commit"], "run_id": run["id"], "manifest_sha256": candidate["manifest_sha256"]}
    value: Dict[str, Any] = {
        "$schema": "./v064-public-ci-witness-v1.schema.json", "schema_version": "1.2.0",
        "witness_id": stable_id("v064_public_ci_witness", identity), "witness_hash": "0" * 64,
        "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_COMPLETED",
        "predecessor_failed_public_witnesses": copy.deepcopy(
            bundle["predecessor_failed_public_witnesses"]
        ),
        "private_source": {
            "repository": bundle["source"]["private_repository"],
            "candidate_commit": bundle["source"]["candidate_commit"],
            "candidate_tree": bundle["source"]["candidate_tree"],
            "object_format": bundle["source"]["object_format"],
            "historical_billing_blocked_private_pr": copy.deepcopy(
                bundle["source"]["historical_billing_blocked_private_pr"]
            ),
        },
        "public_source": {"repository": _PUBLIC_REPOSITORY, "commit": candidate["commit"], "tree": candidate["tree"], "branch": "main", "parent_count": candidate["parent_count"]},
        "bundle": {"manifest_sha256": candidate["manifest_sha256"], "file_set_sha256": bundle["file_set_sha256"]},
        "workflow": {"path": workflow["path"], "blob_oid": workflow["source_blob_oid"], "sha256": workflow["sha256"]},
        "run": {
            "run_id": run["id"],
            **{key: run[key] for key in run_keys if key not in {"id", "path", "repository"}},
        },
        "jobs": normalized,
        "raw_evidence": {
            "run_api": _raw("artifacts/v064-public-ci-r3/v064-public-ci-r3-run-api-v1.json", run_bytes),
            "jobs_api": _raw("artifacts/v064-public-ci-r3/v064-public-ci-r3-jobs-api-v1.json", jobs_bytes),
            "run_log": _raw("artifacts/v064-public-ci-r3/v064-public-ci-r3-run-log-v1.txt", log_bytes),
            "acquisition_transcript": _raw("artifacts/v064-public-ci-r3/v064-public-ci-r3-acquisition-transcript-v1.json", transcript_bytes),
        },
        "ancestry": {"witness_binds_private_source_f": True, "public_commit_is_parentless": True, "candidate_g_not_yet_bound": True},
        "safety": {"production_activation": False, "credentials_present": False, "broker_allowed": False, "orders_allowed": False, "runtime_state_write_allowed": False},
        "non_claims": ["NOT_FULL_PROJECT_CI", "NOT_PRIVATE_PR_CHECK", "NOT_STRATEGY_CORRECTNESS_EVIDENCE", "NOT_PROFITABILITY_OR_AI_ADVANTAGE_EVIDENCE", "NOT_PAPER_CANARY_OR_LIVE_TRADING_AUTHORIZATION"],
    }
    value["witness_hash"] = artifact_self_hash(value, "witness_hash")
    if tuple(_validator().iter_errors(value)):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_SCHEMA_INVALID")
    return value


def _read_exact(path: Path) -> bytes:
    requested = Path(path)
    if not requested.is_absolute():
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
    nofollow = getattr(os, "O_NOFOLLOW", None); nonblock = getattr(os, "O_NONBLOCK", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if not isinstance(nofollow, int) or not nofollow or not isinstance(nonblock, int) or not nonblock or not isinstance(directory, int) or not directory:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_UNSUPPORTED")
    parent_descriptor = None
    descriptor = None
    try:
        parts = requested.parts
        if not parts or parts[0] != "/":
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
        parent_descriptor = os.open("/", os.O_RDONLY | directory | nofollow)
        for component in parts[1:-1]:
            next_descriptor = os.open(
                component, os.O_RDONLY | directory | nofollow | nonblock,
                dir_fd=parent_descriptor,
            )
            opened_parent = os.fstat(next_descriptor)
            if not stat.S_ISDIR(opened_parent.st_mode) or opened_parent.st_uid not in {0, os.getuid()} or stat.S_IMODE(opened_parent.st_mode) & 0o022:
                os.close(next_descriptor)
                raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
            os.close(parent_descriptor)
            parent_descriptor = next_descriptor
        descriptor = os.open(parts[-1], os.O_RDONLY | nofollow | nonblock, dir_fd=parent_descriptor)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1 or stat.S_IMODE(opened.st_mode) & 0o022 or not 0 < opened.st_size <= _MAX_BYTES:
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
        chunks = []; remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
            chunks.append(chunk); remaining -= len(chunk)
        attached = requested.lstat(); after = os.fstat(descriptor)
        if (attached.st_dev, attached.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID")
        return b"".join(chunks)
    except V064PublicCiWitnessError:
        raise
    except OSError as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_PATH_INVALID") from error
    finally:
        if descriptor is not None:
            try: os.close(descriptor)
            except OSError: pass
        if parent_descriptor is not None:
            try: os.close(parent_descriptor)
            except OSError: pass


def load_v064_public_ci_witness(path: Path) -> Dict[str, Any]:
    body = _read_exact(Path(path)); value = dict(_json(body, "V064_PUBLIC_CI_WITNESS_JSON_INVALID"))
    if body != canonical_json(value).encode("utf-8") + b"\n":
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_CANONICAL_BYTES_REQUIRED")
    if tuple(_validator().iter_errors(value)):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_SCHEMA_INVALID")
    if any(
        job["setup_python_version"] != job["fixed_owner_python_version"]
        for job in value["jobs"]
    ):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_SCHEMA_INVALID")
    identity = {"private_commit": value["private_source"]["candidate_commit"], "public_commit": value["public_source"]["commit"], "run_id": value["run"]["run_id"], "manifest_sha256": value["bundle"]["manifest_sha256"]}
    if value["witness_id"] != stable_id("v064_public_ci_witness", identity):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_ID_MISMATCH")
    if value["witness_hash"] != artifact_self_hash(value, "witness_hash"):
        raise V064PublicCiWitnessError("V064_PUBLIC_CI_WITNESS_HASH_MISMATCH")
    return copy.deepcopy(value)


_SOURCE_PATHS = {
    ".github/workflows/ci.yml": "public_ci/v064/.github/workflows/ci.yml",
    ".gitignore": "public_ci/v064/.gitignore",
    "NOTICE.md": "public_ci/v064/NOTICE.md",
    "README.md": "public_ci/v064/README.md",
    "SECURITY.md": "public_ci/v064/SECURITY.md",
    "src/crypto_quant/challenger_replacement_supersession_publish.py": "src/crypto_quant/challenger_replacement_supersession_publish.py",
    "tests/test_v064_linux_supersession_publish.py": "tests/test_v064_linux_supersession_publish.py",
}
_ALLOWED_G_DELTA = {
    "artifacts/v064-public-ci/v064-public-ci-run-api-v1.json",
    "artifacts/v064-public-ci/v064-public-ci-jobs-api-v1.json",
    "artifacts/v064-public-ci/v064-public-ci-run-log-v1.txt",
    "artifacts/v064-public-ci/v064-public-ci-acquisition-transcript-v1.json",
    "artifacts/v064-public-ci/v064-public-ci-witness-v1.json",
    "tests/test_v064_public_ci_witness.py",
    "config/evaluator-build-manifest-v1.json",
}


def _git(repository: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("/usr/bin/git", "-C", str(repository), *arguments),
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode or completed.stderr:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_GIT_INVALID")
    return completed.stdout


def _git_oid(body: bytes) -> str:
    try:
        value = body.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_GIT_INVALID") from error
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_GIT_INVALID")
    return value


def verify_v064_public_source_unchanged(
    repository: Path, source_commit_f: str, candidate_commit_g: str,
    manifest: dict,
) -> Dict[str, Any]:
    root = Path(repository)
    for supplied, reason in (
        (source_commit_f, "V064_PUBLIC_SOURCE_F_INVALID"),
        (candidate_commit_g, "V064_PUBLIC_SOURCE_G_INVALID"),
    ):
        if not isinstance(supplied, str) or len(supplied) != 40 or any(character not in "0123456789abcdef" for character in supplied):
            raise V064PublicCiWitnessError(reason)
    if manifest.get("source", {}).get("candidate_commit") != source_commit_f:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_F_INVALID")
    if source_commit_f == candidate_commit_g:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_NOT_STRICT_DESCENDANT")
    ancestor = subprocess.run(
        ("/usr/bin/git", "-C", str(root), "merge-base", "--is-ancestor", source_commit_f, candidate_commit_g),
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if ancestor.returncode != 0 or ancestor.stdout or ancestor.stderr:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_NOT_STRICT_DESCENDANT")
    entries = manifest.get("files")
    if (
        not isinstance(entries, list)
        or len(entries) != len(_SOURCE_PATHS)
        or any(not isinstance(entry, Mapping) or set(entry) != {"path", "source_blob_oid"} for entry in entries)
        or {entry["path"] for entry in entries} != set(_SOURCE_PATHS)
    ):
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_MANIFEST_INVALID")
    for entry in entries:
        private_path = _SOURCE_PATHS[entry["path"]]
        oid = _git_oid(_git(root, "rev-parse", "%s:%s" % (candidate_commit_g, private_path)))
        if oid != entry.get("source_blob_oid"):
            raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_BLOB_CHANGED")
    changed = _git(root, "diff", "--name-only", "-z", source_commit_f, candidate_commit_g, "--")
    try:
        paths = {item.decode("utf-8") for item in changed.split(b"\0") if item}
    except UnicodeDecodeError as error:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_GIT_INVALID") from error
    if not paths or not paths <= _ALLOWED_G_DELTA:
        raise V064PublicCiWitnessError("V064_PUBLIC_SOURCE_DELTA_INVALID")
    return {
        "status": "V064_PUBLIC_SOURCE_UNCHANGED",
        "source_commit_f": source_commit_f,
        "candidate_commit_g": candidate_commit_g,
        "verified_blob_count": len(entries),
        "allowed_delta_paths": sorted(paths),
    }
