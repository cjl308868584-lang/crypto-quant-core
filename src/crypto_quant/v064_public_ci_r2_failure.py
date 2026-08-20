"""Closed offline record for the v0.64 R2 public CI semantic failure."""

import copy
import hashlib
import json
import os
import re
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json


_SCHEMA = "v064-public-ci-r2-failure-record-v1.schema.json"
_MAX_BYTES = 64 * 1024 * 1024
_ROOT_NAMES = {
    "run_api": "v064-public-ci-r2-run-api-v1.json",
    "jobs_api": "v064-public-ci-r2-jobs-api-v1.json",
    "run_log": "v064-public-ci-r2-run-log-v1.txt",
    "record": "v064-public-ci-r2-failure-record-v1.json",
}
_ARTIFACT_ROOT = "artifacts/v064-public-ci-r2-failure"
_RAW = {
    "run_api": (363, "310d2cad6840dc80d4cbcd6cc229d32704fd3c8854b44b6bbd893b708d4f9986"),
    "jobs_api": (2312, "3078337f2f8e5aa9add1b099391e19125d5dcdeaef803e1f50d9666716ad773c"),
    "run_log": (105558, "e6ee2bcf599cff56b0bcda8292bdb7a85e5ef186973f4fe3a14c67f97a0bbf47"),
}
_JOBS = (("3.9", 96305223463), ("3.12", 96305223215))


class V064PublicCiR2FailureError(ValueError):
    """The R2 semantic-failure evidence failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _safe_integer(value: str) -> int:
    parsed = int(value)
    if not -(1 << 53) < parsed < (1 << 53):
        raise ValueError("unsafe integer")
    return parsed


def _json(body: bytes, reason: str) -> Mapping[str, Any]:
    if not isinstance(body, bytes) or not body or len(body) > _MAX_BYTES or not body.endswith(b"\n") or b"\r" in body or body.startswith(b"\xef\xbb\xbf"):
        raise V064PublicCiR2FailureError(reason)

    def pairs(items):
        result = {}
        for key, value in items:
            if not isinstance(key, str) or not key.isascii() or key in result:
                raise ValueError("invalid object")
            result[key] = value
        return result

    def reject_number(_value):
        raise ValueError("noninteger number")

    try:
        value = json.loads(body.decode("utf-8"), object_pairs_hook=pairs, parse_int=_safe_integer, parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise V064PublicCiR2FailureError(reason) from error
    if not isinstance(value, Mapping) or body != canonical_json(value).encode("utf-8") + b"\n":
        raise V064PublicCiR2FailureError(reason)
    return value


def _exact_keys(value: Mapping[str, Any], expected, reason: str) -> None:
    if set(value) != set(expected):
        raise V064PublicCiR2FailureError(reason)


def _raw(name: str, body: bytes) -> Dict[str, Any]:
    return {
        "path": _ARTIFACT_ROOT + "/" + _ROOT_NAMES[name],
        "size": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _parse_run(body: bytes) -> Mapping[str, Any]:
    reason = "V064_PUBLIC_CI_R2_RUN_INVALID"
    value = _json(body, reason)
    _exact_keys(value, ("conclusion", "created_at", "event", "head_branch", "head_sha", "id", "path", "repository", "run_attempt", "status", "updated_at", "workflow_id"), reason)
    required = {
        "repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2",
        "head_sha": "5541aba00e4e93e6389c2c61a81e69c2dd228947",
        "id": 32328770160,
        "path": ".github/workflows/ci.yml",
        "run_attempt": 1,
        "event": "push",
        "head_branch": "main",
        "status": "completed",
        "conclusion": "success",
        "workflow_id": 338298387,
    }
    if any(value[key] != expected for key, expected in required.items()):
        raise V064PublicCiR2FailureError(reason)
    return value


def _parse_jobs(body: bytes) -> list:
    reason = "V064_PUBLIC_CI_R2_JOBS_INVALID"
    value = _json(body, reason)
    _exact_keys(value, ("jobs", "total_count"), reason)
    if value["total_count"] != 2 or not isinstance(value["jobs"], list) or len(value["jobs"]) != 2:
        raise V064PublicCiR2FailureError(reason)
    seen = {}
    expected_job_keys = ("completed_at", "conclusion", "id", "labels", "name", "runner_name", "started_at", "status", "steps")
    for job in value["jobs"]:
        if not isinstance(job, Mapping):
            raise V064PublicCiR2FailureError(reason)
        _exact_keys(job, expected_job_keys, reason)
        if not isinstance(job["name"], str) or job["name"] in seen or job["status"] != "completed" or job["conclusion"] != "success" or job["labels"] != ["ubuntu-latest"] or not isinstance(job["runner_name"], str) or not job["runner_name"]:
            raise V064PublicCiR2FailureError(reason)
        if not isinstance(job["steps"], list) or not any(isinstance(step, Mapping) and step.get("name") == "Run fixed-owner public boundary" and step.get("status") == "completed" and step.get("conclusion") == "success" for step in job["steps"]):
            raise V064PublicCiR2FailureError(reason)
        seen[job["name"]] = job
    normalized = []
    for version, job_id in _JOBS:
        job = seen.get("portability (%s)" % version)
        if job is None or job["id"] != job_id:
            raise V064PublicCiR2FailureError(reason)
        normalized.append(job)
    return normalized


def _parse_log(body: bytes) -> list:
    reason = "V064_PUBLIC_CI_R2_LOG_INVALID"
    if not isinstance(body, bytes) or not body or len(body) > _MAX_BYTES or b"\r" in body:
        raise V064PublicCiR2FailureError(reason)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise V064PublicCiR2FailureError(reason) from error
    captured = {"3.9": [], "3.12": []}
    timestamp = re.compile(r"^\ufeff?[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?Z (.*)$")
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3 or parts[1] not in {"Verify closed bundle before repository imports", "Run fixed-owner public boundary"}:
            continue
        version = parts[0].removeprefix("portability (").removesuffix(")")
        match = timestamp.fullmatch(parts[2])
        if version not in captured or match is None:
            raise V064PublicCiR2FailureError(reason)
        captured[version].append((parts[1], match.group(1)))
    markers = (
        "source_candidate_f=5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219",
        "public_commit=5541aba00e4e93e6389c2c61a81e69c2dd228947",
        "manifest_sha256=b2017d2e4099ee64d0cbbcbd35f38b1833fbe351d2696f70248ad60056b20ae2",
        "file_set_sha256=6c6d5bde35d1f5f4e484f5874b47fad3d0f575eef4eeb8e4deb9de659be4eb69",
    )
    observed = []
    for version, _job_id in _JOBS:
        preflight = [message for step, message in captured[version] if step == "Verify closed bundle before repository imports"]
        boundary = [message for step, message in captured[version] if step == "Run fixed-owner public boundary"]
        if any(preflight.count(marker) != 1 for marker in markers) or boundary.count("Python 3.12.3") != 1:
            raise V064PublicCiR2FailureError(reason)
        observed.append("3.12.3")
    return observed


def derive_v064_public_ci_r2_failure(*, run_bytes: bytes, jobs_bytes: bytes, log_bytes: bytes) -> Dict[str, Any]:
    """Derive the fixed R2 failure; no conclusion is accepted from callers."""
    run = _parse_run(run_bytes)
    jobs = _parse_jobs(jobs_bytes)
    observed = _parse_log(log_bytes)
    value: Dict[str, Any] = {
        "$schema": "./v064-public-ci-r2-failure-record-v1.schema.json",
        "schema_version": "1.0.0",
        "status": "PUBLIC_LINUX_PORTABILITY_WITNESS_DID_NOT_PASS",
        "reason_code": "PUBLIC_MATRIX_INTERPRETER_IDENTITY_MISMATCH",
        "readback_provenance": "POST_RUN_READ_ONLY_READBACK",
        "private_source": {"candidate_commit": "5bc01c9b9b9d9a21846dd8c6ba1d81b0183dd219", "candidate_tree": "53d3baf7d7c84e5bc8fcafa2561bbb959477ac4d"},
        "public_source": {"repository": "cjl308868584-lang/crypto-quant-v064-public-ci-r2", "root_commit": "5541aba00e4e93e6389c2c61a81e69c2dd228947", "root_tree": "3d732e8e1fbb9cf94541f6e26e778d5eb21ca8f3"},
        "workflow": {"path": run["path"], "blob_oid": "ba5b6851ed53ad79100409b92c78c09c07608ed2"},
        "bundle": {"manifest_sha256": "b2017d2e4099ee64d0cbbcbd35f38b1833fbe351d2696f70248ad60056b20ae2", "file_set_sha256": "6c6d5bde35d1f5f4e484f5874b47fad3d0f575eef4eeb8e4deb9de659be4eb69"},
        "run": {"run_id": run["id"], "run_attempt": run["run_attempt"], "event": run["event"], "head_branch": run["head_branch"], "status": run["status"], "github_conclusion": run["conclusion"]},
        "expected_python_versions": [version for version, _job_id in _JOBS],
        "observed_fixed_owner_versions": observed,
        "jobs": [{"python_version": version, "job_id": job["id"], "github_conclusion": job["conclusion"], "observed_fixed_owner_version": observed[index]} for index, ((version, _job_id), job) in enumerate(zip(_JOBS, jobs))],
        "raw_evidence": {"run_api": _raw("run_api", run_bytes), "jobs_api": _raw("jobs_api", jobs_bytes), "run_log": _raw("run_log", log_bytes)},
        "success_witness_published": False,
        "safety": {"production_activation": False, "credentials_present": False, "broker_allowed": False, "orders_allowed": False, "runtime_state_write_allowed": False},
    }
    if tuple(_validator().iter_errors(value)):
        raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_RECORD_SCHEMA_INVALID")
    return value


def _read_final(path: Path, reason: str) -> bytes:
    requested = Path(path)
    if not requested.is_absolute():
        raise V064PublicCiR2FailureError(reason)
    descriptor = None
    try:
        before = requested.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != 0o644 or not 0 < before.st_size <= _MAX_BYTES:
            raise V064PublicCiR2FailureError(reason)
        descriptor = os.open(requested, os.O_RDONLY | os.O_NOFOLLOW)
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (before.st_dev, before.st_ino, before.st_size) or not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or opened.st_nlink != 1 or stat.S_IMODE(opened.st_mode) != 0o644:
            raise V064PublicCiR2FailureError(reason)
        body = bytearray()
        while len(body) < opened.st_size:
            chunk = os.read(descriptor, min(65536, opened.st_size - len(body)))
            if not chunk:
                raise V064PublicCiR2FailureError(reason)
            body.extend(chunk)
        after = os.fstat(descriptor)
        attached = requested.lstat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) or (attached.st_dev, attached.st_ino) != (opened.st_dev, opened.st_ino):
            raise V064PublicCiR2FailureError(reason)
        return bytes(body)
    except V064PublicCiR2FailureError:
        raise
    except OSError as error:
        raise V064PublicCiR2FailureError(reason) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_v064_public_ci_r2_failure_root(root: Path) -> Dict[str, Any]:
    """Reload and independently replay all fixed final R2 failure artifacts."""
    directory = Path(root)
    if not directory.is_absolute() or not directory.is_dir():
        raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_ROOT_INVALID")
    record_body = _read_final(directory / _ROOT_NAMES["record"], "V064_PUBLIC_CI_R2_RECORD_PATH_INVALID")
    record = _json(record_body, "V064_PUBLIC_CI_R2_RECORD_INVALID")
    if tuple(_validator().iter_errors(record)):
        raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_RECORD_SCHEMA_INVALID")
    run = _read_final(directory / _ROOT_NAMES["run_api"], "V064_PUBLIC_CI_R2_RAW_PATH_INVALID")
    jobs = _read_final(directory / _ROOT_NAMES["jobs_api"], "V064_PUBLIC_CI_R2_RAW_PATH_INVALID")
    log = _read_final(directory / _ROOT_NAMES["run_log"], "V064_PUBLIC_CI_R2_RAW_PATH_INVALID")
    for name, body in (("run_api", run), ("jobs_api", jobs), ("run_log", log)):
        if (len(body), hashlib.sha256(body).hexdigest()) != _RAW[name]:
            raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_RAW_EVIDENCE_INVALID")
    derived = derive_v064_public_ci_r2_failure(run_bytes=run, jobs_bytes=jobs, log_bytes=log)
    if record != derived:
        raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_RECORD_MISMATCH")
    return copy.deepcopy(dict(record))


def load_v064_public_ci_r2_failure(path: Path) -> Dict[str, Any]:
    requested = Path(path)
    if requested.name != _ROOT_NAMES["record"]:
        raise V064PublicCiR2FailureError("V064_PUBLIC_CI_R2_RECORD_PATH_INVALID")
    return load_v064_public_ci_r2_failure_root(requested.parent)
