"""Exact-byte Git release helper for the first maintenance run receipt."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional

from .canonical import canonical_json
from .challenger_cohort_evidence_maintenance_first_run import (
    ChallengerCohortEvidenceMaintenanceFirstRunError,
    load_challenger_cohort_evidence_maintenance_first_run_receipt,
)


_MAX_RECEIPT_BYTES = 8 * 1024 * 1024


class ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(ValueError):
    """The runtime-to-Git exact receipt release failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _source(path: Path) -> tuple[Path, bytes, Mapping[str, Any]]:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_SOURCE_INVALID"
        )
    try:
        resolved = selected.resolve(strict=True)
        before = resolved.lstat()
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_size <= 0
            or before.st_size > _MAX_RECEIPT_BYTES
        ):
            raise ValueError
        body = resolved.read_bytes()
        after = resolved.lstat()
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_SOURCE_INVALID"
        ) from error
    return (
        resolved,
        body,
        {
            "device": after.st_dev,
            "inode": after.st_ino,
            "owner_uid": after.st_uid,
            "mode_octal": f"{stat.S_IMODE(after.st_mode):04o}",
            "link_count": after.st_nlink,
            "size_bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        },
    )


def _target(path: Path) -> Path:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_TARGET_INVALID"
        )
    try:
        parent = selected.parent.resolve(strict=True)
        status = parent.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or stat.S_IMODE(status.st_mode) & 0o022
        ):
            raise ValueError
        resolved = parent / selected.name
        if resolved == Path("/") or not selected.name.endswith(".json"):
            raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_TARGET_INVALID"
        ) from error
    return resolved


def _publish(path: Path, body: bytes) -> bool:
    if path.exists() or path.is_symlink():
        try:
            status = path.lstat()
            if (
                not stat.S_ISREG(status.st_mode)
                or stat.S_ISLNK(status.st_mode)
                or status.st_uid != os.getuid()
                or status.st_nlink != 1
                or path.read_bytes() != body
            ):
                raise ValueError
            os.chmod(path, 0o600)
            return False
        except (OSError, ValueError) as error:
            raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_CONFLICT"
            ) from error
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".challenger-maintenance-first-run-release-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(temporary_name)
    published = False
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
                "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_CONFLICT"
            ) from error
        published = True
        temporary.unlink()
        os.chmod(path, 0o600)
        directory_descriptor = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()
    return published


def release_challenger_cohort_evidence_maintenance_first_run_receipt(
    *,
    runtime_receipt_path: Path,
    install_receipt_path: Path,
    manifest_path: Path,
    trusted_source_attestation_hash: str,
    trusted_candidate_attestation_hash: str,
    artifact_output_path: Path,
    _receipt_loader=None,
) -> Mapping[str, Any]:
    loader = (
        _receipt_loader
        or load_challenger_cohort_evidence_maintenance_first_run_receipt
    )
    source_path, source_bytes, source_stat = _source(
        runtime_receipt_path
    )
    try:
        receipt = loader(
            receipt_path=source_path,
            install_receipt_path=Path(install_receipt_path),
            manifest_path=Path(manifest_path),
            trusted_source_attestation_hash=(
                trusted_source_attestation_hash
            ),
            trusted_candidate_attestation_hash=(
                trusted_candidate_attestation_hash
            ),
        )
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_RECEIPT_INVALID"
        ) from error
    if (
        not isinstance(receipt, Mapping)
        or source_bytes != canonical_json(receipt).encode("utf-8")
        or receipt.get("observation_status")
        != "FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED"
    ):
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_RECEIPT_INVALID"
        )
    target = _target(artifact_output_path)
    created = _publish(target, source_bytes)
    try:
        target_bytes = target.read_bytes()
        target_stat = target.lstat()
        if (
            target_bytes != source_bytes
            or hashlib.sha256(target_bytes).hexdigest()
            != source_stat["sha256"]
            or target_stat.st_uid != os.getuid()
            or target_stat.st_nlink != 1
            or stat.S_IMODE(target_stat.st_mode) != 0o600
        ):
            raise ValueError
        replay = loader(
            receipt_path=target,
            install_receipt_path=Path(install_receipt_path),
            manifest_path=Path(manifest_path),
            trusted_source_attestation_hash=(
                trusted_source_attestation_hash
            ),
            trusted_candidate_attestation_hash=(
                trusted_candidate_attestation_hash
            ),
        )
        if replay != receipt:
            raise ValueError
    except (
        ChallengerCohortEvidenceMaintenanceFirstRunError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortEvidenceMaintenanceFirstRunReleaseError(
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_RELEASE_REPLAY_INVALID"
        ) from error
    return {
        "status": "EXACT_RECEIPT_RELEASED",
        "runtime_receipt_path": str(source_path),
        "artifact_output_path": str(target),
        "artifact_created": created,
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "file_sha256": source_stat["sha256"],
        "size_bytes": source_stat["size_bytes"],
        "runtime_and_artifact_bytes_equal": True,
        "observer_network_request_count": 0,
        "launchctl_command_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "strategy_runner_invocation_count": 0,
        "maintenance_invocation_count": 0,
    }
