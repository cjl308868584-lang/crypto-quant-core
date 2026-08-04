"""Immutable 90-day System Paper start receipt publication and replay."""

import hashlib
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .evidence import artifact_self_hash
from .system_paper_evidence import SystemPaperEvidenceError, publish_owner_exact
from .system_paper_install import load_system_paper_install_receipt
from .system_paper_launchd import (
    load_system_paper_launchd_contract,
    system_paper_launchd_contract_trust_hash,
)
from .system_paper_observer import (
    SystemPaperObserverError,
    observe_system_paper_first_slot,
    replay_system_paper_first_slot_evidence,
)


_SCHEMA = "system-paper-start-receipt-v1.schema.json"
_EXPECTED_SLOT_COUNT = 540
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_MAX_SOURCE_EVIDENCE_BYTES = 32 * 1024 * 1024
_WARNINGS = (
    "START_RECEIPT_BEGINS_PAPER_RESEARCH_ONLY",
    "NINETY_DAY_RESULT_NOT_YET_AVAILABLE",
    "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
    "NO_LIVE_TRADING_AUTHORITY",
)


class SystemPaperStartReceiptError(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperStartReceiptError(
                "SYSTEM_PAPER_START_RECEIPT_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_TIME_INVALID"
        )
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_TIME_INVALID"
        )
    return parsed, utc_datetime(parsed)


@lru_cache(maxsize=1)
def _validator():
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _source_binding(contract, preflight_path, install_path, install):
    preflight_bytes = Path(preflight_path).read_bytes()
    install_bytes = Path(install_path).read_bytes()
    return {
        "contract_id": contract["contract_id"],
        "contract_hash": contract["contract_hash"],
        "contract_trust_hash": system_paper_launchd_contract_trust_hash(contract),
        "release_commit": contract["release"]["release_commit"],
        "snapshot_tree_hash": contract["execution_snapshot"]["tree_hash"],
        "preflight_receipt_id": install["preflight_receipt"]["receipt_id"],
        "preflight_receipt_hash": install["preflight_receipt"]["receipt_hash"],
        "preflight_file_sha256": hashlib.sha256(preflight_bytes).hexdigest(),
        "install_receipt_id": install["receipt_id"],
        "install_receipt_hash": install["receipt_hash"],
        "install_file_sha256": hashlib.sha256(install_bytes).hexdigest(),
    }


def _receipt_reasons(receipt, *, contract, source, install):
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_SCHEMA_INVALID")
        if receipt["receipt_hash"] != artifact_self_hash(receipt, "receipt_hash"):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_HASH_MISMATCH")
        if receipt["source_binding"] != source:
            reasons.append("SYSTEM_PAPER_START_RECEIPT_SOURCE_BINDING_MISMATCH")
        observation = receipt["observation"]
        first = observation["first_slot"]
        if set(observation) != {
            "status",
            "observed_at",
            "first_eligible_slot",
            "successful_slot_count",
            "terminal_slot_count",
            "first_slot",
            "source_evidence",
            "state_evidence",
            "launchd",
            "security_boundary",
        } or set(first) != {
            "slot_id",
            "scheduled_for",
            "result_path",
            "result_sha256",
            "slot_hash",
            "runtime_snapshot_hash",
            "prepared_input_sha256",
            "prepared_result_sha256",
            "event_chain_end_hash",
            "artifact_evidence",
            "stdout_evidence",
            "stderr_evidence",
            "runner_summary",
        }:
            reasons.append("SYSTEM_PAPER_START_RECEIPT_OBSERVATION_INVALID")
        if (
            observation["status"] != "FIRST_NATURAL_SLOT_VERIFIED"
            or receipt["first_slot"] != first
            or first["scheduled_for"] != receipt["cohort_started_at"]
            or receipt["published_at"] != observation["observed_at"]
        ):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_OBSERVATION_INVALID")
        started, started_text = _utc(receipt["cohort_started_at"])
        if (
            receipt["cohort_started_at"] != started_text
            or receipt["cohort_tail_end"]
            != utc_datetime(started + timedelta(days=90))
            or receipt["expected_slot_count"] != _EXPECTED_SLOT_COUNT
        ):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_COHORT_DERIVATION_INVALID")
        identity = {
            "contract_hash": contract["contract_hash"],
            "install_receipt_hash": install["receipt_hash"],
            "first_slot_id": first["slot_id"],
            "cohort_started_at": receipt["cohort_started_at"],
        }
        if receipt["receipt_id"] != stable_id(
            "system_paper_start_receipt", identity
        ):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_ID_MISMATCH")
        if receipt["security_boundary"] != {
            "launchctl_read_count": 1,
            "network_request_count": 0,
            "runtime_invocation_count": 0,
            "scheduler_invocation_count": 0,
            "state_write_count": 0,
            "credential_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
        } or receipt["warnings"] != list(_WARNINGS):
            reasons.append("SYSTEM_PAPER_START_RECEIPT_SECURITY_BOUNDARY_INVALID")
    except (KeyError, TypeError, ValueError, SystemPaperStartReceiptError):
        reasons.append("SYSTEM_PAPER_START_RECEIPT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _file_matches(evidence):
    path = Path(evidence["path"])
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(path, flags)
        entry = os.fstat(descriptor)
        if (
            not stat.S_ISREG(entry.st_mode)
            or not 0 <= entry.st_size <= _MAX_SOURCE_EVIDENCE_BYTES
        ):
            return False
        chunks = []
        total = 0
        while total <= _MAX_SOURCE_EVIDENCE_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, _MAX_SOURCE_EVIDENCE_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        body = b"".join(chunks)
        retained = os.fstat(descriptor)
        current = os.stat(path, follow_symlinks=False)
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        len(body) != entry.st_size
        or len(body) > _MAX_SOURCE_EVIDENCE_BYTES
        or _stat_identity(entry) != _stat_identity(retained)
        or _stat_identity(retained) != _stat_identity(current)
    ):
        return False
    actual = {
        "path": str(path),
        "device": entry.st_dev,
        "inode": entry.st_ino,
        "mode": stat.S_IMODE(entry.st_mode),
        "owner_uid": entry.st_uid,
        "link_count": entry.st_nlink,
        "size_bytes": entry.st_size,
        "mtime_ns": str(entry.st_mtime_ns),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    return actual == evidence


def _observation_evidences(observation):
    values = list(observation["source_evidence"].values())
    values.extend(
        item for item in observation["state_evidence"].values() if item is not None
    )
    first = observation["first_slot"]
    values.extend(
        (
            first["artifact_evidence"],
            first["stdout_evidence"],
            first["stderr_evidence"],
        )
    )
    return values


def _source_evidences(observation):
    return tuple(observation["source_evidence"].values())


def _stat_identity(entry):
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_uid,
        entry.st_nlink,
        entry.st_size,
        entry.st_mtime_ns,
        entry.st_ctime_ns,
    )


def _read_bounded_receipt(path, expected_root):
    if path.parent != expected_root or path.name in {"", ".", ".."}:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
        )
    root_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    root_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    file_flags |= getattr(os, "O_CLOEXEC", 0)
    root_fd = None
    file_fd = None
    try:
        root_fd = os.open(expected_root, root_flags)
        root_before = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_before.st_mode)
            or root_before.st_uid != os.getuid()
            or stat.S_IMODE(root_before.st_mode) != 0o700
        ):
            raise SystemPaperStartReceiptError(
                "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
            )
        file_fd = os.open(path.name, file_flags, dir_fd=root_fd)
        entry_before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(entry_before.st_mode)
            or entry_before.st_uid != os.getuid()
            or entry_before.st_nlink != 1
            or stat.S_IMODE(entry_before.st_mode) != 0o600
            or not 0 < entry_before.st_size <= _MAX_RECEIPT_BYTES
        ):
            raise SystemPaperStartReceiptError(
                "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
            )

        chunks = []
        total = 0
        while total <= _MAX_RECEIPT_BYTES:
            chunk = os.read(
                file_fd,
                min(64 * 1024, _MAX_RECEIPT_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        body = b"".join(chunks)
        entry_after = os.fstat(file_fd)
        path_after = os.stat(path.name, dir_fd=root_fd, follow_symlinks=False)
        inventory = set(os.listdir(root_fd))
        root_after = os.fstat(root_fd)
        if (
            len(body) != entry_before.st_size
            or len(body) > _MAX_RECEIPT_BYTES
            or _stat_identity(entry_before) != _stat_identity(entry_after)
            or _stat_identity(entry_after) != _stat_identity(path_after)
            or _stat_identity(root_before) != _stat_identity(root_after)
        ):
            raise SystemPaperStartReceiptError(
                "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
            )
        return body, inventory
    except SystemPaperStartReceiptError:
        raise
    except OSError as error:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
        ) from error
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if root_fd is not None:
            os.close(root_fd)


def publish_system_paper_start_receipt(
    *,
    contract_path: Path,
    plist_path: Path,
    preflight_receipt_path: Path,
    install_receipt_path: Path,
    _launchctl_runner=None,
    _machine_probe=None,
    _filesystem_probe=None,
    _clock=None,
) -> Mapping[str, Any]:
    observation = observe_system_paper_first_slot(
        contract_path=contract_path,
        plist_path=plist_path,
        preflight_receipt_path=preflight_receipt_path,
        install_receipt_path=install_receipt_path,
        _launchctl_runner=_launchctl_runner,
        _machine_probe=_machine_probe,
        _filesystem_probe=_filesystem_probe,
        _clock=_clock,
    )
    if observation["status"] != "FIRST_NATURAL_SLOT_VERIFIED":
        return {
            "outcome": "START_RECEIPT_PENDING",
            "observation_status": observation["status"],
        }
    contract = load_system_paper_launchd_contract(
        contract_path=contract_path, plist_path=plist_path
    )
    install = load_system_paper_install_receipt(
        receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        preflight_receipt_path=preflight_receipt_path,
        _machine_probe=_machine_probe,
        _filesystem_probe=_filesystem_probe,
    )
    source = _source_binding(
        contract, preflight_receipt_path, install_receipt_path, install
    )
    first = observation["first_slot"]
    started, started_text = _utc(first["scheduled_for"])
    identity = {
        "contract_hash": contract["contract_hash"],
        "install_receipt_hash": install["receipt_hash"],
        "first_slot_id": first["slot_id"],
        "cohort_started_at": started_text,
    }
    receipt = {
        "$schema": f"./{_SCHEMA}",
        "schema_version": "1.0.0",
        "receipt_id": stable_id("system_paper_start_receipt", identity),
        "receipt_hash": "0" * 64,
        "published_at": observation["observed_at"],
        "source_binding": source,
        "observation": observation,
        "first_slot": first,
        "cohort_started_at": started_text,
        "cohort_tail_end": utc_datetime(started + timedelta(days=90)),
        "expected_slot_count": _EXPECTED_SLOT_COUNT,
        "security_boundary": dict(observation["security_boundary"]),
        "warnings": list(_WARNINGS),
    }
    receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
    if _receipt_reasons(
        receipt, contract=contract, source=source, install=install
    ):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_INVALID"
        )
    if not all(_file_matches(item) for item in _observation_evidences(observation)):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_SOURCE_CHANGED"
        )
    root = Path(contract["root_paths"]["start_receipts"])
    root.mkdir(mode=0o700, parents=False, exist_ok=True)
    entry = root.lstat()
    if (
        root.resolve(strict=True) != root
        or not stat.S_ISDIR(entry.st_mode)
        or entry.st_uid != os.getuid()
        or stat.S_IMODE(entry.st_mode) != 0o700
    ):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_OUTPUT_INVALID"
        )
    path = root / f"{receipt['receipt_id']}.json"
    if any(item.name != path.name for item in root.iterdir()):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_OUTPUT_INVENTORY_INVALID"
        )
    try:
        publish_owner_exact(path, canonical_json(receipt).encode("utf-8"))
    except SystemPaperEvidenceError as error:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_CONFLICT"
        ) from error
    return {
        "outcome": "START_RECEIPT_PUBLISHED",
        "receipt_path": str(path),
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "cohort_started_at": receipt["cohort_started_at"],
        "cohort_tail_end": receipt["cohort_tail_end"],
        "expected_slot_count": receipt["expected_slot_count"],
    }


def load_system_paper_start_receipt(
    *,
    receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    preflight_receipt_path: Path,
    install_receipt_path: Path,
    _machine_probe=None,
    _filesystem_probe=None,
) -> Mapping[str, Any]:
    contract = load_system_paper_launchd_contract(
        contract_path=contract_path, plist_path=plist_path
    )
    install = load_system_paper_install_receipt(
        receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
        preflight_receipt_path=preflight_receipt_path,
        _machine_probe=_machine_probe,
        _filesystem_probe=_filesystem_probe,
    )
    path = Path(receipt_path)
    expected_root = Path(contract["root_paths"]["start_receipts"])
    try:
        body, inventory = _read_bounded_receipt(path, expected_root)
        receipt = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
        ) from error
    if (
        not isinstance(receipt, Mapping)
        or path.name != f"{receipt.get('receipt_id')}.json"
        or canonical_json(receipt).encode("utf-8") != body
    ):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_READ_INVALID"
        )
    if inventory != {path.name}:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_OUTPUT_INVENTORY_INVALID"
        )
    source = _source_binding(
        contract, preflight_receipt_path, install_receipt_path, install
    )
    if _receipt_reasons(
        receipt, contract=contract, source=source, install=install
    ):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_INVALID"
        )
    observation = receipt["observation"]
    first = observation["first_slot"]
    if not all(_file_matches(item) for item in _source_evidences(observation)):
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_SOURCE_CHANGED"
        )
    try:
        replayed = replay_system_paper_first_slot_evidence(
            observation=observation, contract=contract, install=install
        )
    except SystemPaperObserverError as error:
        if error.reason_code == "SYSTEM_PAPER_OBSERVER_STORED_LAUNCHCTL_INVALID":
            raise SystemPaperStartReceiptError(
                "SYSTEM_PAPER_START_RECEIPT_INVALID"
            ) from error
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_SOURCE_CHANGED"
        ) from error
    if any(
        observation[key] != replayed[key]
        for key in (
            "status",
            "first_eligible_slot",
            "successful_slot_count",
            "terminal_slot_count",
            "first_slot",
            "launchd",
        )
    ) or receipt["first_slot"] != replayed["first_slot"]:
        raise SystemPaperStartReceiptError(
            "SYSTEM_PAPER_START_RECEIPT_INVALID"
        )
    return receipt
