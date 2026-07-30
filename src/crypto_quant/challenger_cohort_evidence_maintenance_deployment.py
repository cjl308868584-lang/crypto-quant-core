"""Private snapshot and install candidate for cohort evidence maintenance."""

import hashlib
import json
import os
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_cohort_evidence_maintenance_launchd import (
    ChallengerCohortEvidenceMaintenanceLaunchdError,
    build_challenger_cohort_evidence_maintenance_launchd_contract,
    challenger_cohort_evidence_maintenance_launchd_trust_hash,
    load_challenger_cohort_evidence_maintenance_launchd_contract,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = (
    "challenger-cohort-evidence-maintenance-deployment-manifest-v1.schema.json"
)
_LABEL = "local.crypto-quant.challenger-cohort-evidence-maintenance"
_SNAPSHOT_DIRECTORY = "challenger-cohort-evidence-maintenance"
_CANDIDATE_DIRECTORY = (
    "challenger-cohort-evidence-maintenance-install-candidate"
)
_COHORT_PLAN = (
    "artifacts/challenger-forward/"
    "challenger-episode-cohort-plan-v0.43.0.json"
)
_ECONOMIC_PLAN = (
    "artifacts/challenger-forward/"
    "challenger-episode-economic-plan-v0.37.0.json"
)
_MAX_FILE_BYTES = 4 * 1024 * 1024
_MAX_TREE_BYTES = 32 * 1024 * 1024
_MAX_FILES = 1000
_MAX_MANIFEST_BYTES = 4 * 1024 * 1024
_WARNINGS = (
    "DEPLOYMENT_MANIFEST_DOES_NOT_PROVE_INSTALLATION",
    "MAINTENANCE_NOT_INVOKED",
    "FIRST_NATURAL_SCHEDULE_RECEIPT_REQUIRED",
    "NO_PROFITABILITY_CLAIM",
    "NO_SYSTEM_PAPER_OR_AI_ADVANTAGE_CLAIM",
)


class ChallengerCohortEvidenceMaintenanceDeploymentError(ValueError):
    """The private snapshot or install candidate failed closed."""

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
            raise ChallengerCohortEvidenceMaintenanceDeploymentError(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_TIME_INVALID"
        )
    return rendered


def _secure_file(path: Path, reason: str) -> Path:
    try:
        raw = Path(path).expanduser()
        if not raw.is_absolute() or raw.is_symlink():
            raise ValueError
        resolved = raw.resolve(strict=True)
        status = resolved.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size <= 0
        ):
            raise ValueError
        return resolved
    except Exception as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            reason
        ) from error


def _secure_output_root(path: Path) -> Path:
    raw = Path(path).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_OUTPUT_INVALID"
        )
    try:
        raw.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(raw, 0o700)
        resolved = raw.resolve(strict=True)
        status = resolved.lstat()
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_OUTPUT_INVALID"
        ) from error
    if (
        not stat.S_ISDIR(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or status.st_uid != os.getuid()
        or stat.S_IMODE(status.st_mode) != 0o700
    ):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_OUTPUT_INVALID"
        )
    return resolved


def _stat_identity(status: os.stat_result) -> Tuple[int, ...]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_uid,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _source_relative_paths(repository: Path) -> Tuple[str, ...]:
    package = repository / "src" / "crypto_quant"
    required = (
        repository / "pyproject.toml",
        package,
        repository / _COHORT_PLAN,
        repository / _ECONOMIC_PLAN,
    )
    if (
        repository.is_symlink()
        or not repository.is_dir()
        or package.is_symlink()
        or not package.is_dir()
        or not all(item.exists() for item in required)
    ):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        )
    paths = {"pyproject.toml", _COHORT_PLAN, _ECONOMIC_PLAN}
    try:
        for entry in package.rglob("*"):
            relative = entry.relative_to(repository)
            if (
                "__pycache__" in relative.parts
                or any(part.startswith(".") for part in relative.parts)
                or entry.name.endswith((".pyc", ".pyo"))
            ):
                continue
            status = entry.lstat()
            if stat.S_ISDIR(status.st_mode):
                if stat.S_ISLNK(status.st_mode):
                    raise ValueError
                continue
            paths.add(relative.as_posix())
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        ) from error
    return tuple(sorted(paths))


def _read_source_files(
    repository: Path,
) -> Tuple[Tuple[Dict[str, Any], ...], Mapping[str, bytes]]:
    owner_uid = os.getuid()
    records = []
    data_by_path = {}
    total = 0
    try:
        root_status = repository.lstat()
        if (
            not stat.S_ISDIR(root_status.st_mode)
            or stat.S_ISLNK(root_status.st_mode)
            or root_status.st_uid != owner_uid
        ):
            raise ValueError
        for relative in _source_relative_paths(repository):
            path = repository / relative
            before = path.lstat()
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_ISLNK(before.st_mode)
                or before.st_uid != owner_uid
                or before.st_nlink != 1
                or before.st_size <= 0
                or before.st_size > _MAX_FILE_BYTES
            ):
                raise ValueError
            body = path.read_bytes()
            after = path.lstat()
            if (
                _stat_identity(before) != _stat_identity(after)
                or len(body) != before.st_size
            ):
                raise ValueError
            total += len(body)
            records.append(
                {
                    "path": relative,
                    "size_bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            data_by_path[relative] = body
            if len(records) > _MAX_FILES or total > _MAX_TREE_BYTES:
                raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        ) from error
    required = {
        "pyproject.toml",
        "src/crypto_quant/__init__.py",
        "src/crypto_quant/challenger_cohort_evidence_maintenance.py",
        "src/crypto_quant/challenger_cohort_evidence_maintenance_cli.py",
        _COHORT_PLAN,
        _ECONOMIC_PLAN,
    }
    if not required.issubset(data_by_path):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        )
    return tuple(records), data_by_path


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


def _write_snapshot(
    *,
    runtime_root: Path,
    records: Sequence[Mapping[str, Any]],
    data_by_path: Mapping[str, bytes],
) -> Tuple[Path, bool]:
    summary = _tree_summary(records)
    deployment = _secure_output_root(runtime_root / "deployment")
    parent = _secure_output_root(deployment / _SNAPSHOT_DIRECTORY)
    final = parent / summary["tree_hash"][:16]
    if final.exists() or final.is_symlink():
        _verify_snapshot(final, records)
        return final, False
    temporary = Path(
        tempfile.mkdtemp(prefix=".snapshot-", dir=str(parent))
    )
    installed = False
    try:
        os.chmod(temporary, 0o700)
        for item in records:
            destination = temporary / item["path"]
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(destination.parent, 0o700)
            descriptor = os.open(
                str(destination),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                body = data_by_path[item["path"]]
                with os.fdopen(descriptor, "wb", closefd=False) as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                os.close(descriptor)
            os.chmod(destination, 0o600)
        for directory in sorted(
            (item for item in temporary.rglob("*") if item.is_dir()),
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            os.chmod(directory, 0o700)
            _fsync_directory(directory)
        _fsync_directory(temporary)
        try:
            os.rename(temporary, final)
        except FileExistsError:
            _verify_snapshot(final, records)
            return final, False
        installed = True
        _fsync_directory(parent)
        _verify_snapshot(final, records)
        return final, True
    except OSError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SNAPSHOT_WRITE_FAILED"
        ) from error
    finally:
        if not installed and temporary.exists():
            shutil.rmtree(temporary)


def _verify_snapshot(
    root: Path,
    expected_records: Sequence[Mapping[str, Any]],
) -> None:
    owner_uid = os.getuid()
    expected = {item["path"]: dict(item) for item in expected_records}
    actual = {}
    try:
        status = root.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != owner_uid
            or stat.S_IMODE(status.st_mode) != 0o700
        ):
            raise ValueError
        for entry in root.rglob("*"):
            entry_status = entry.lstat()
            if (
                stat.S_ISLNK(entry_status.st_mode)
                or entry_status.st_uid != owner_uid
            ):
                raise ValueError
            if stat.S_ISDIR(entry_status.st_mode):
                if stat.S_IMODE(entry_status.st_mode) != 0o700:
                    raise ValueError
                continue
            if (
                not stat.S_ISREG(entry_status.st_mode)
                or entry_status.st_nlink != 1
                or stat.S_IMODE(entry_status.st_mode) != 0o600
            ):
                raise ValueError
            relative = entry.relative_to(root).as_posix()
            body = entry.read_bytes()
            actual[relative] = {
                "path": relative,
                "size_bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SNAPSHOT_INVALID"
        ) from error
    if actual != expected:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SNAPSHOT_INVALID"
        )


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def deployment_manifest_hash(manifest: Mapping[str, Any]) -> str:
    return artifact_self_hash(manifest, "manifest_hash")


def _manifest_reasons(
    manifest: Mapping[str, Any],
    *,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    _strategy_loader=None,
) -> Tuple[str, ...]:
    if not isinstance(manifest, Mapping):
        return ("CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(manifest)):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SCHEMA_INVALID"
            )
        if manifest.get("manifest_hash") != deployment_manifest_hash(
            manifest
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_HASH_MISMATCH"
            )
        source = manifest["source_contract"]
        source_contract_path = _secure_file(
            Path(source["contract_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
        )
        source_plist_path = _secure_file(
            Path(source["plist_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
        )
        source_contract = (
            load_challenger_cohort_evidence_maintenance_launchd_contract(
                contract_path=source_contract_path,
                plist_path=source_plist_path,
                trusted_attestation_hash=trusted_source_attestation_hash,
                _strategy_loader=_strategy_loader,
            )
        )
        expected_source = {
            "contract_path": str(source_contract_path),
            "contract_file_sha256": hashlib.sha256(
                source_contract_path.read_bytes()
            ).hexdigest(),
            "plist_path": str(source_plist_path),
            "plist_file_sha256": hashlib.sha256(
                source_plist_path.read_bytes()
            ).hexdigest(),
            "contract_id": source_contract["contract_id"],
            "contract_hash": source_contract["contract_hash"],
            "contract_trust_hash": trusted_source_attestation_hash,
            "repository_root": source_contract["repository_root"],
            "runtime_root": source_contract["runtime_root"],
            "python_executable": source_contract["python_executable"],
        }
        if source != expected_source:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_MISMATCH"
            )
        snapshot = manifest["execution_snapshot"]
        records = tuple(snapshot["files"])
        _verify_snapshot(Path(snapshot["repository_root"]), records)
        summary = _tree_summary(records)
        expected_snapshot = {
            "repository_root": snapshot["repository_root"],
            **summary,
            "files": list(records),
        }
        if snapshot != expected_snapshot:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SNAPSHOT_MISMATCH"
            )
        candidate = manifest["install_candidate"]
        candidate_contract_path = _secure_file(
            Path(candidate["contract_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_CANDIDATE_INVALID",
        )
        candidate_plist_path = _secure_file(
            Path(candidate["plist_path"]),
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_CANDIDATE_INVALID",
        )
        candidate_contract = (
            load_challenger_cohort_evidence_maintenance_launchd_contract(
                contract_path=candidate_contract_path,
                plist_path=candidate_plist_path,
                trusted_attestation_hash=trusted_candidate_attestation_hash,
                _strategy_loader=_strategy_loader,
            )
        )
        expected_candidate = {
            "contract_path": str(candidate_contract_path),
            "contract_file_sha256": hashlib.sha256(
                candidate_contract_path.read_bytes()
            ).hexdigest(),
            "plist_path": str(candidate_plist_path),
            "plist_file_sha256": hashlib.sha256(
                candidate_plist_path.read_bytes()
            ).hexdigest(),
            "contract_id": candidate_contract["contract_id"],
            "contract_hash": candidate_contract["contract_hash"],
            "contract_trust_hash": trusted_candidate_attestation_hash,
            "launchd_plist_sha256": candidate_contract[
                "launchd_plist_sha256"
            ],
        }
        if candidate != expected_candidate:
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_CANDIDATE_MISMATCH"
            )
        if (
            candidate_contract["repository_root"]
            != snapshot["repository_root"]
            or candidate_contract["runtime_root"]
            != source_contract["runtime_root"]
            or candidate_contract["python_executable"]
            != source_contract["python_executable"]
            or candidate_contract["strategy_trust"]
            != source_contract["strategy_trust"]
            or candidate_contract["plans"]["cohort_plan_file_sha256"]
            != source_contract["plans"]["cohort_plan_file_sha256"]
            or candidate_contract["plans"]["economic_plan_file_sha256"]
            != source_contract["plans"]["economic_plan_file_sha256"]
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_BINDING_MISMATCH"
            )
        identity = {
            "source_contract_hash": source_contract["contract_hash"],
            "snapshot_tree_hash": summary["tree_hash"],
            "candidate_contract_hash": candidate_contract["contract_hash"],
            "prepared_at": manifest["prepared_at"],
        }
        if manifest.get("manifest_id") != stable_id(
            "challenger_cohort_evidence_maintenance_deployment", identity
        ):
            reasons.append(
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_ID_MISMATCH"
            )
    except (
        ChallengerCohortEvidenceMaintenanceDeploymentError,
        ChallengerCohortEvidenceMaintenanceLaunchdError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_REPLAY_INVALID"
        )
    return tuple(sorted(set(reasons)))


def prepare_challenger_cohort_evidence_maintenance_deployment(
    *,
    source_contract_path: Path,
    source_plist_path: Path,
    trusted_source_attestation_hash: str,
    output_root: Path,
    clock=None,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    source_contract_file = _secure_file(
        source_contract_path,
        "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
    )
    source_plist_file = _secure_file(
        source_plist_path,
        "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
    )
    try:
        source_contract = (
            load_challenger_cohort_evidence_maintenance_launchd_contract(
                contract_path=source_contract_file,
                plist_path=source_plist_file,
                trusted_attestation_hash=trusted_source_attestation_hash,
                _strategy_loader=_strategy_loader,
            )
        )
    except ChallengerCohortEvidenceMaintenanceLaunchdError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        ) from error
    if (
        source_contract.get("label") != _LABEL
        or source_contract.get("installation_status")
        != "NOT_INSTALLED_NO_EXTERNAL_RECEIPT"
        or source_contract.get("cadence", {}).get("run_at_load") is not False
    ):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID"
        )
    source_repository = Path(source_contract["repository_root"])
    records, data_by_path = _read_source_files(source_repository)
    snapshot_root, snapshot_created = _write_snapshot(
        runtime_root=Path(source_contract["runtime_root"]),
        records=records,
        data_by_path=data_by_path,
    )
    prepared_at = _utc(
        (clock or (lambda: datetime.now(timezone.utc)))()
    )
    try:
        candidate_contract, candidate_plist_bytes = (
            build_challenger_cohort_evidence_maintenance_launchd_contract(
                repository_root=snapshot_root,
                runtime_root=Path(source_contract["runtime_root"]),
                python_executable=Path(
                    source_contract["python_executable"]
                ),
                install_receipt_path=Path(
                    source_contract["strategy_trust"][
                        "install_receipt_path"
                    ]
                ),
                contract_path=Path(
                    source_contract["strategy_trust"][
                        "strategy_contract_path"
                    ]
                ),
                plist_path=Path(
                    source_contract["strategy_trust"][
                        "strategy_plist_path"
                    ]
                ),
                created_at=prepared_at,
                _strategy_loader=_strategy_loader,
            )
        )
    except ChallengerCohortEvidenceMaintenanceLaunchdError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_CANDIDATE_INVALID"
        ) from error
    candidate_trust = (
        challenger_cohort_evidence_maintenance_launchd_trust_hash(
            candidate_contract
        )
    )
    root = _secure_output_root(output_root)
    directory = root / _CANDIDATE_DIRECTORY
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    contract_output = directory / "maintenance-launchd-contract.json"
    plist_output = directory / f"{_LABEL}.plist"
    manifest_output = directory / "deployment-manifest.json"
    expected_names = {
        contract_output.name,
        plist_output.name,
        manifest_output.name,
    }
    if any(item.name not in expected_names for item in directory.iterdir()):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVENTORY_INVALID"
        )
    candidate_contract_bytes = canonical_json(candidate_contract).encode(
        "utf-8"
    )
    try:
        _publish_exact(contract_output, candidate_contract_bytes)
        _publish_exact(plist_output, candidate_plist_bytes)
    except ValueError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_PUBLISH_CONFLICT"
        ) from error
    for path in (contract_output, plist_output):
        os.chmod(path, 0o600)
    snapshot_summary = _tree_summary(records)
    source = {
        "contract_path": str(source_contract_file),
        "contract_file_sha256": hashlib.sha256(
            source_contract_file.read_bytes()
        ).hexdigest(),
        "plist_path": str(source_plist_file),
        "plist_file_sha256": hashlib.sha256(
            source_plist_file.read_bytes()
        ).hexdigest(),
        "contract_id": source_contract["contract_id"],
        "contract_hash": source_contract["contract_hash"],
        "contract_trust_hash": trusted_source_attestation_hash,
        "repository_root": source_contract["repository_root"],
        "runtime_root": source_contract["runtime_root"],
        "python_executable": source_contract["python_executable"],
    }
    candidate = {
        "contract_path": str(contract_output),
        "contract_file_sha256": hashlib.sha256(
            candidate_contract_bytes
        ).hexdigest(),
        "plist_path": str(plist_output),
        "plist_file_sha256": hashlib.sha256(
            candidate_plist_bytes
        ).hexdigest(),
        "contract_id": candidate_contract["contract_id"],
        "contract_hash": candidate_contract["contract_hash"],
        "contract_trust_hash": candidate_trust,
        "launchd_plist_sha256": candidate_contract[
            "launchd_plist_sha256"
        ],
    }
    identity = {
        "source_contract_hash": source_contract["contract_hash"],
        "snapshot_tree_hash": snapshot_summary["tree_hash"],
        "candidate_contract_hash": candidate_contract["contract_hash"],
        "prepared_at": prepared_at,
    }
    manifest = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "manifest_id": stable_id(
            "challenger_cohort_evidence_maintenance_deployment", identity
        ),
        "manifest_hash": "0" * 64,
        "prepared_at": prepared_at,
        "source_contract": source,
        "execution_snapshot": {
            "repository_root": str(snapshot_root),
            **snapshot_summary,
            "files": list(records),
        },
        "install_candidate": candidate,
        "security_boundary": {
            "snapshot_publish_count": 1,
            "candidate_publish_count": 2,
            "network_request_count": 0,
            "launchctl_command_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "strategy_state_write_count": 0,
            "strategy_runner_invocation_count": 0,
            "maintenance_invocation_count": 0,
        },
        "deployment_status": "PREPARED_NOT_INSTALLED",
        "warnings": list(_WARNINGS),
    }
    manifest["manifest_hash"] = deployment_manifest_hash(manifest)
    if tuple(_validator().iter_errors(manifest)):
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SCHEMA_INVALID"
        )
    try:
        _publish_exact(
            manifest_output, canonical_json(manifest).encode("utf-8")
        )
    except ValueError as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_PUBLISH_CONFLICT"
        ) from error
    os.chmod(manifest_output, 0o600)
    reasons = _manifest_reasons(
        manifest,
        trusted_source_attestation_hash=trusted_source_attestation_hash,
        trusted_candidate_attestation_hash=candidate_trust,
        _strategy_loader=_strategy_loader,
    )
    if reasons:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVALID"
        )
    return {
        "outcome": "PREPARED_NOT_INSTALLED",
        "manifest_path": str(manifest_output),
        "manifest_id": manifest["manifest_id"],
        "manifest_hash": manifest["manifest_hash"],
        "snapshot_root": str(snapshot_root),
        "snapshot_tree_hash": snapshot_summary["tree_hash"],
        "snapshot_created": snapshot_created,
        "candidate_contract_path": str(contract_output),
        "candidate_plist_path": str(plist_output),
        "candidate_contract_id": candidate_contract["contract_id"],
        "candidate_contract_hash": candidate_contract["contract_hash"],
        "candidate_contract_trust_hash": candidate_trust,
        "candidate_plist_sha256": candidate_contract[
            "launchd_plist_sha256"
        ],
        "launchctl_command_count": 0,
        "maintenance_invocation_count": 0,
    }


def load_challenger_cohort_evidence_maintenance_deployment(
    *,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    _strategy_loader=None,
) -> Mapping[str, Any]:
    manifest_file = _secure_file(
        manifest_path,
        "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_READ_FAILED",
    )
    try:
        if manifest_file.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ValueError
        manifest = _strict_json_bytes(manifest_file.read_bytes())
        candidate = manifest["install_candidate"]
        contract_file = Path(candidate["contract_path"]).resolve(
            strict=True
        )
        plist_file = Path(candidate["plist_path"]).resolve(strict=True)
        expected = {
            manifest_file.name,
            contract_file.name,
            plist_file.name,
        }
        if (
            contract_file.parent != manifest_file.parent
            or plist_file.parent != manifest_file.parent
            or {item.name for item in manifest_file.parent.iterdir()}
            != expected
        ):
            raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_READ_FAILED"
        ) from error
    reasons = _manifest_reasons(
        manifest,
        trusted_source_attestation_hash=trusted_source_attestation_hash,
        trusted_candidate_attestation_hash=trusted_candidate_attestation_hash,
        _strategy_loader=_strategy_loader,
    )
    if reasons:
        raise ChallengerCohortEvidenceMaintenanceDeploymentError(
            "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVALID"
        )
    return manifest
