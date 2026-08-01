"""Exact-byte Git release helpers for Challenger failure evidence."""

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_json
from .challenger_cohort_failure import (
    ChallengerCohortFailureError,
    load_challenger_cohort_failure_receipt,
)


_MAX_RECEIPT_BYTES = 64 * 1024 * 1024
_FAILURE_ARTIFACT = (
    "challenger-cohort-missed-slot-failure-receipt-v0.54.0.json"
)
_FAILURE_RUNTIME_DIRECTORY = "challenger-cohort-failure-receipts"


class ChallengerCohortFailureReleaseError(ValueError):
    """The exact runtime-to-Git evidence release failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _source(path: Path) -> tuple[Path, bytes, Mapping[str, Any]]:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_SOURCE_INVALID"
        )
    try:
        resolved = selected.resolve(strict=True)
        before = resolved.lstat()
        if (
            resolved != selected.absolute()
            or not stat.S_ISREG(before.st_mode)
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
        ) or len(body) != before.st_size:
            raise ValueError
    except (OSError, ValueError) as error:
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_SOURCE_INVALID"
        ) from error
    return (
        resolved,
        body,
        {
            "device": after.st_dev,
            "inode": after.st_ino,
            "owner_uid": after.st_uid,
            "mode_octal": "0600",
            "link_count": after.st_nlink,
            "size_bytes": len(body),
            "mtime_ns": after.st_mtime_ns,
            "sha256": hashlib.sha256(body).hexdigest(),
        },
    )


def _target(path: Path, *, expected_name: str) -> Path:
    selected = Path(path).expanduser()
    if not selected.is_absolute() or selected.is_symlink():
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_TARGET_INVALID"
        )
    try:
        parent = selected.parent.resolve(strict=True)
        parent_stat = parent.lstat()
        if (
            selected.parent.resolve() != selected.parent.absolute()
            or not stat.S_ISDIR(parent_stat.st_mode)
            or stat.S_ISLNK(parent_stat.st_mode)
            or parent_stat.st_uid != os.getuid()
            or stat.S_IMODE(parent_stat.st_mode) & 0o022
            or selected.name != expected_name
        ):
            raise ValueError
        return parent / selected.name
    except (OSError, ValueError) as error:
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_TARGET_INVALID"
        ) from error


def _publish(path: Path, body: bytes) -> bool:
    if path.exists() or path.is_symlink():
        try:
            file_stat = path.lstat()
            if (
                not stat.S_ISREG(file_stat.st_mode)
                or stat.S_ISLNK(file_stat.st_mode)
                or file_stat.st_uid != os.getuid()
                or file_stat.st_nlink != 1
                or path.read_bytes() != body
            ):
                raise ValueError
            os.chmod(path, 0o600)
            return False
        except (OSError, ValueError) as error:
            raise ChallengerCohortFailureReleaseError(
                "CHALLENGER_COHORT_FAILURE_RELEASE_CONFLICT"
            ) from error
    descriptor, name = tempfile.mkstemp(
        prefix=".challenger-failure-release-",
        suffix=".tmp",
        dir=str(path.parent),
    )
    temporary = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise ChallengerCohortFailureReleaseError(
                "CHALLENGER_COHORT_FAILURE_RELEASE_CONFLICT"
            ) from error
        temporary.unlink()
        os.chmod(path, 0o600)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def _rollback_created(path: Path, body: bytes) -> None:
    try:
        file_stat = path.lstat()
        if (
            not stat.S_ISREG(file_stat.st_mode)
            or stat.S_ISLNK(file_stat.st_mode)
            or file_stat.st_uid != os.getuid()
            or file_stat.st_nlink != 1
            or path.read_bytes() != body
        ):
            raise ValueError
        path.unlink()
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except (OSError, ValueError) as error:
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_ROLLBACK_FAILED"
        ) from error


def release_challenger_cohort_failure_receipt(
    *,
    runtime_receipt_path: Path,
    artifact_output_path: Path,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    _receipt_loader=None,
) -> Mapping[str, Any]:
    loader = _receipt_loader or load_challenger_cohort_failure_receipt
    source_path, source_bytes, source_stat = _source(runtime_receipt_path)
    loader_arguments = {
        "cohort_plan_path": Path(cohort_plan_path),
        "evaluation_plan_path": Path(evaluation_plan_path),
        "install_receipt_path": Path(install_receipt_path),
        "contract_path": Path(contract_path),
        "plist_path": Path(plist_path),
    }
    try:
        receipt = loader(receipt_path=source_path, **loader_arguments)
    except (
        ChallengerCohortFailureError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_RECEIPT_INVALID"
        ) from error
    if (
        not isinstance(receipt, Mapping)
        or source_bytes != canonical_json(receipt).encode("utf-8")
        or receipt.get("observation_status")
        != "COHORT_MISSED_SLOT_FAILURE_VERIFIED"
        or source_path.parent.name != _FAILURE_RUNTIME_DIRECTORY
        or source_path.name != f"{receipt.get('receipt_id')}.json"
    ):
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_RECEIPT_INVALID"
        )
    target = _target(
        artifact_output_path, expected_name=_FAILURE_ARTIFACT
    )
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
        replay = loader(receipt_path=target, **loader_arguments)
        if replay != receipt:
            raise ValueError
        final_source_path, final_source_bytes, final_source_stat = _source(
            source_path
        )
        if (
            final_source_path != source_path
            or final_source_bytes != source_bytes
            or final_source_stat != source_stat
        ):
            raise ValueError
    except (
        ChallengerCohortFailureReleaseError,
        ChallengerCohortFailureError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        if created:
            _rollback_created(target, source_bytes)
        raise ChallengerCohortFailureReleaseError(
            "CHALLENGER_COHORT_FAILURE_RELEASE_REPLAY_INVALID"
        ) from error
    return {
        "status": "EXACT_FAILURE_RECEIPT_RELEASED",
        "runtime_receipt_path": str(source_path),
        "artifact_output_path": str(target),
        "artifact_created": created,
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "file_sha256": source_stat["sha256"],
        "size_bytes": source_stat["size_bytes"],
        "runtime_and_artifact_bytes_equal": True,
        "launchctl_command_count": 0,
        "market_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "strategy_runner_invocation_count": 0,
        "maintenance_invocation_count": 0,
    }
