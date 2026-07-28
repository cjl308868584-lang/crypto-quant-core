"""Read-only, cross-bound first-slot receipt for the live challenger."""

import hashlib
import json
import os
import re
import sqlite3
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_forward import (
    ChallengerForwardError,
    challenger_decision_reasons,
    challenger_forward_policy,
)
from .challenger_forward_runner import (
    ChallengerForwardRunnerError,
    load_challenger_source_bundle,
)
from .challenger_launchd import (
    challenger_launchd_contract_trust_hash,
    load_challenger_launchd_contract,
)
from .challenger_launchd_install import (
    ChallengerLaunchdInstallError,
    LaunchctlResult,
    _command_evidence,
    _command_evidence_valid,
    _command_runner,
    _print_bindings_valid,
    load_challenger_install_receipt,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-first-slot-receipt-v1.schema.json"
_LABEL = "local.crypto-quant.challenger-forward"
_LAUNCHCTL = "/bin/launchctl"
_START = datetime(2026, 7, 29, tzinfo=timezone.utc)
_DEADLINE = _START + timedelta(hours=4)
_MAX_STATE_BYTES = 16 * 1024 * 1024
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024
_MAX_LOG_BYTES = 4 * 1024 * 1024
_MAX_RECEIPT_BYTES = 4 * 1024 * 1024
_MAX_LOG_LINES = 10000


class ChallengerFirstSlotReceiptError(ValueError):
    """The observation, replay, or immutable receipt failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc_now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_TIME_INVALID"
            ) from error
    else:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_TIME_INVALID"
        )
    return converted, rendered


def _secure_file(
    path: Path,
    *,
    maximum_bytes: int,
    allow_empty: bool,
    reason_code: str,
) -> Tuple[Dict[str, Any], bytes]:
    candidate = Path(path)
    try:
        parent_status = candidate.parent.lstat()
        status = candidate.lstat()
        if (
            stat.S_ISLNK(parent_status.st_mode)
            or not stat.S_ISDIR(parent_status.st_mode)
            or parent_status.st_uid != os.getuid()
            or stat.S_IMODE(parent_status.st_mode) != 0o700
            or stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size > maximum_bytes
            or (not allow_empty and status.st_size == 0)
        ):
            raise ChallengerFirstSlotReceiptError(reason_code)
        data = candidate.read_bytes()
        after = candidate.lstat()
    except OSError as error:
        raise ChallengerFirstSlotReceiptError(reason_code) from error
    if (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(data) != status.st_size:
        raise ChallengerFirstSlotReceiptError(reason_code)
    return (
        {
            "device": status.st_dev,
            "inode": status.st_ino,
            "owner_uid": status.st_uid,
            "mode_octal": "0600",
            "link_count": status.st_nlink,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        },
        data,
    )


def _paths(contract: Mapping[str, Any]) -> Mapping[str, Path]:
    try:
        arguments = contract["program_arguments"]
        runtime = Path(contract["runtime_root"]).resolve(strict=True)
        if (
            not isinstance(arguments, list)
            or len(arguments) != 7
            or arguments[1:4]
            != [
                "-m",
                "crypto_quant.challenger_forward_runner_cli",
                "--state-path",
            ]
            or arguments[5] != "--output-root"
        ):
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_CONTRACT_INVALID"
            )
        state = Path(arguments[4]).resolve()
        output = Path(arguments[6]).resolve()
        state.relative_to(runtime)
        output.relative_to(runtime)
    except (KeyError, OSError, TypeError, ValueError) as error:
        if isinstance(error, ChallengerFirstSlotReceiptError):
            raise
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_CONTRACT_INVALID"
        ) from error
    return {
        "runtime": runtime,
        "state": state,
        "output": output,
        "stdout": runtime / "log" / "challenger-forward.stdout.log",
        "stderr": runtime / "log" / "challenger-forward.stderr.log",
        "bundle_directory": (
            output / "challenger-forward" / "source-bundles"
        ),
    }


def _read_state(
    state_path: Path,
) -> Tuple[Mapping[str, Any], Tuple[Mapping[str, Any], ...]]:
    wal_path = Path(f"{state_path}-wal")
    if wal_path.exists():
        wal_stat, _wal_bytes = _secure_file(
            wal_path,
            maximum_bytes=_MAX_STATE_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_FIRST_SLOT_STATE_BUSY",
        )
        if wal_stat["size_bytes"] != 0:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_STATE_BUSY"
            )
    shm_path = Path(f"{state_path}-shm")
    if shm_path.exists():
        _secure_file(
            shm_path,
            maximum_bytes=_MAX_STATE_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_FIRST_SLOT_STATE_BUSY",
        )
    state_stat, before = _secure_file(
        state_path,
        maximum_bytes=_MAX_STATE_BYTES,
        allow_empty=False,
        reason_code="CHALLENGER_FIRST_SLOT_STATE_INVALID",
    )
    uri = f"file:{quote(str(state_path), safe='/')}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        metadata_rows = connection.execute(
            "SELECT singleton, policy_hash, registration_hash "
            "FROM metadata ORDER BY singleton"
        ).fetchall()
        rows = connection.execute(
            "SELECT sequence, scheduled_for, decision_id, decision_hash, "
            "decision_bytes FROM decisions ORDER BY sequence"
        ).fetchall()
    except sqlite3.Error as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_STATE_INVALID"
        ) from error
    finally:
        if "connection" in locals():
            connection.close()
    after_stat, after = _secure_file(
        state_path,
        maximum_bytes=_MAX_STATE_BYTES,
        allow_empty=False,
        reason_code="CHALLENGER_FIRST_SLOT_STATE_INVALID",
    )
    if before != after or state_stat != after_stat:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_STATE_CHANGED"
        )
    policy = challenger_forward_policy()
    expected_metadata = {
        "policy_hash": policy["policy_hash"],
        "registration_hash": policy["hypothesis_registration_hash"],
    }
    if (
        len(metadata_rows) != 1
        or metadata_rows[0]["singleton"] != 1
        or {
            "policy_hash": metadata_rows[0]["policy_hash"],
            "registration_hash": metadata_rows[0][
                "registration_hash"
            ],
        }
        != expected_metadata
    ):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_STATE_BINDING_INVALID"
        )
    decisions = []
    previous = None
    for expected_sequence, row in enumerate(rows, 1):
        try:
            decision = _strict_json_bytes(bytes(row["decision_bytes"]))
        except Exception as error:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_STATE_INVALID"
            ) from error
        if (
            row["sequence"] != expected_sequence
            or row["scheduled_for"] != decision.get("scheduled_for")
            or row["decision_id"] != decision.get("decision_id")
            or row["decision_hash"] != decision.get("decision_hash")
            or challenger_decision_reasons(
                decision, previous_decision=previous
            )
        ):
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_STATE_INVALID"
            )
        decisions.append(decision)
        previous = decision
    state_evidence = {
        "path": str(state_path),
        "file_stat": state_stat,
        "metadata": expected_metadata,
        "decision_count": len(decisions),
        "decision_chain_end_hash_or_null": (
            decisions[-1]["decision_hash"] if decisions else None
        ),
    }
    return state_evidence, tuple(decisions)


def _matching_bundle(
    *,
    bundle_directory: Path,
    first_decision: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], Mapping[str, Any]]:
    try:
        candidates = sorted(bundle_directory.glob("*.json"))
    except OSError as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_BUNDLE_INVALID"
        ) from error
    matches = []
    for path in candidates:
        file_stat, _data = _secure_file(
            path,
            maximum_bytes=_MAX_BUNDLE_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_FIRST_SLOT_BUNDLE_INVALID",
        )
        try:
            bundle = load_challenger_source_bundle(path)
        except ChallengerForwardRunnerError as error:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_BUNDLE_INVALID"
            ) from error
        if bundle.get("scheduled_for") == utc_datetime(_START):
            matches.append((path, file_stat, bundle))
    if len(matches) != 1:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_BUNDLE_COUNT_INVALID"
        )
    path, file_stat, bundle = matches[0]
    if bundle["candidate_decision"] != first_decision:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_BUNDLE_DECISION_MISMATCH"
        )
    evidence = {
        "path": str(path.resolve()),
        "file_stat": file_stat,
        "bundle_id": bundle["bundle_id"],
        "bundle_hash": bundle["bundle_hash"],
    }
    return evidence, bundle


def _log_lines(data: bytes) -> Tuple[Mapping[str, Any], ...]:
    lines = data.splitlines()
    if len(lines) > _MAX_LOG_LINES or any(not line for line in lines):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_STDOUT_INVALID"
        )
    records = []
    for line in lines:
        try:
            records.append(_strict_json_bytes(line))
        except Exception as error:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_STDOUT_INVALID"
            ) from error
    return tuple(records)


def _log_evidence(
    *,
    stdout_path: Path,
    stderr_path: Path,
    first_decision: Mapping[str, Any],
    bundle_evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    stdout_stat, stdout_bytes = _secure_file(
        stdout_path,
        maximum_bytes=_MAX_LOG_BYTES,
        allow_empty=False,
        reason_code="CHALLENGER_FIRST_SLOT_STDOUT_INVALID",
    )
    stderr_stat, _stderr_bytes = _secure_file(
        stderr_path,
        maximum_bytes=_MAX_LOG_BYTES,
        allow_empty=True,
        reason_code="CHALLENGER_FIRST_SLOT_STDERR_INVALID",
    )
    records = _log_lines(stdout_bytes)
    matches = []
    for line_number, record in enumerate(records, 1):
        if (
            record.get("status") == "RECORDED"
            and record.get("decision_count") == 1
            and record.get("decision_id") == first_decision["decision_id"]
            and record.get("decision_hash") == first_decision["decision_hash"]
            and record.get("source_bundle_path")
            == bundle_evidence["path"]
            and record.get("source_bundle_hash")
            == bundle_evidence["bundle_hash"]
            and record.get("server_time_request_count") == 3
            and record.get("kline_request_count") == 1
            and record.get("broker_request_count") == 0
            and record.get("order_submission_count") == 0
        ):
            matches.append((line_number, record))
    if len(matches) != 1:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_LOG_MATCH_INVALID"
        )
    line_number, record = matches[0]
    return {
        "stdout": {
            "path": str(stdout_path),
            "observed_prefix_stat": stdout_stat,
            "matched_line_number": line_number,
            "matched_record": dict(record),
            "matched_record_hash": hashlib.sha256(
                canonical_json(record).encode("utf-8")
            ).hexdigest(),
        },
        "stderr": {
            "path": str(stderr_path),
            "observed_stat": stderr_stat,
            "empty": stderr_stat["size_bytes"] == 0,
        },
    }


def _launchctl_evidence(
    *,
    runner,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Tuple[Mapping[str, Any], int]:
    service = install_receipt["service"]
    argv = (_LAUNCHCTL, "print", service)
    try:
        result = runner(argv)
    except ChallengerLaunchdInstallError:
        raise
    except Exception as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_LAUNCHCTL_FAILED"
        ) from error
    if not isinstance(result, LaunchctlResult):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_LAUNCHCTL_FAILED"
        )
    evidence = _command_evidence(argv, result)
    text = result.stdout.decode("utf-8")
    run_matches = re.findall(
        r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)", text
    )
    if (
        result.returncode != 0
        or not _print_bindings_valid(
            result.stdout,
            contract=contract,
            domain=install_receipt["domain"],
            target=Path(install_receipt["target_path"]),
        )
        or str(paths["stdout"]) not in text
        or str(paths["stderr"]) not in text
        or "last exit code = 0" not in text
        or len(run_matches) != 1
        or int(run_matches[0]) < 1
    ):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_SERVICE_INVALID"
        )
    return evidence, int(run_matches[0])


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_first_slot_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "install_receipt_hash": receipt["install_receipt"][
            "receipt_hash"
        ],
        "observed_at": receipt["observed_at"],
        "first_decision_hash": receipt["state"]["first_decision"][
            "decision_hash"
        ],
        "bundle_hash": receipt["source_bundle"]["bundle_hash"],
        "state_file_hash": receipt["state"]["file_stat"]["sha256"],
        "stdout_prefix_hash": receipt["logs"]["stdout"][
            "observed_prefix_stat"
        ]["sha256"],
        "launchctl_print_hash": receipt["launchctl_print"][
            "command_evidence_hash"
        ],
    }


def _receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Tuple[str, ...]:
    if not isinstance(receipt, Mapping):
        return ("CHALLENGER_FIRST_SLOT_RECEIPT_INVALID",)
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_RECEIPT_SCHEMA_INVALID"
            )
        if (
            receipt.get("receipt_hash")
            != challenger_first_slot_receipt_hash(receipt)
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_RECEIPT_HASH_MISMATCH"
            )
        expected_install = {
            "receipt_id": install_receipt["receipt_id"],
            "receipt_hash": install_receipt["receipt_hash"],
            "target_path": install_receipt["target_path"],
            "target_sha256": install_receipt["target_stat"]["sha256"],
            "execution_snapshot": install_receipt["source_contract"][
                "execution_snapshot"
            ],
        }
        if receipt["install_receipt"] != expected_install:
            reasons.append(
                "CHALLENGER_FIRST_SLOT_INSTALL_RECEIPT_MISMATCH"
            )
        expected_contract = {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": (
                challenger_launchd_contract_trust_hash(contract)
            ),
            "launchd_plist_sha256": contract["launchd_plist_sha256"],
        }
        if receipt["contract"] != expected_contract:
            reasons.append(
                "CHALLENGER_FIRST_SLOT_CONTRACT_MISMATCH"
            )
        state_evidence, decisions = _read_state(paths["state"])
        observed_count = receipt["state"]["decision_count"]
        if (
            observed_count < 1
            or len(decisions) < observed_count
            or receipt["state"]["path"] != state_evidence["path"]
            or receipt["state"]["metadata"] != state_evidence["metadata"]
            or receipt["state"]["first_decision"] != decisions[0]
            or receipt["state"]["decision_chain_end_hash"]
            != decisions[observed_count - 1]["decision_hash"]
        ):
            reasons.append("CHALLENGER_FIRST_SLOT_STATE_MISMATCH")
        bundle_evidence, _bundle = _matching_bundle(
            bundle_directory=paths["bundle_directory"],
            first_decision=decisions[0],
        )
        if receipt["source_bundle"] != bundle_evidence:
            reasons.append("CHALLENGER_FIRST_SLOT_BUNDLE_MISMATCH")
        logs = receipt["logs"]
        stdout_stat, stdout_bytes = _secure_file(
            paths["stdout"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_FIRST_SLOT_STDOUT_INVALID",
        )
        prefix = logs["stdout"]["observed_prefix_stat"]
        prefix_size = prefix["size_bytes"]
        if (
            logs["stdout"]["path"] != str(paths["stdout"])
            or stdout_stat["size_bytes"] < prefix_size
            or hashlib.sha256(stdout_bytes[:prefix_size]).hexdigest()
            != prefix["sha256"]
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_STDOUT_PREFIX_MISMATCH"
            )
        records = _log_lines(stdout_bytes[:prefix_size])
        line_number = logs["stdout"]["matched_line_number"]
        if (
            line_number < 1
            or line_number > len(records)
            or records[line_number - 1]
            != logs["stdout"]["matched_record"]
            or logs["stdout"]["matched_record_hash"]
            != hashlib.sha256(
                canonical_json(logs["stdout"]["matched_record"]).encode(
                    "utf-8"
                )
            ).hexdigest()
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_LOG_RECORD_MISMATCH"
            )
        record = logs["stdout"]["matched_record"]
        first_decision = receipt["state"]["first_decision"]
        if (
            record.get("status") != "RECORDED"
            or record.get("decision_count") != 1
            or record.get("decision_id") != first_decision["decision_id"]
            or record.get("decision_hash") != first_decision["decision_hash"]
            or record.get("source_bundle_path")
            != receipt["source_bundle"]["path"]
            or record.get("source_bundle_hash")
            != receipt["source_bundle"]["bundle_hash"]
            or record.get("server_time_request_count") != 3
            or record.get("kline_request_count") != 1
            or record.get("broker_request_count") != 0
            or record.get("order_submission_count") != 0
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_LOG_RECORD_MISMATCH"
            )
        stderr_stat, stderr_bytes = _secure_file(
            paths["stderr"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_FIRST_SLOT_STDERR_INVALID",
        )
        stderr_prefix = logs["stderr"]["observed_stat"]
        stderr_size = stderr_prefix["size_bytes"]
        if (
            logs["stderr"]["path"] != str(paths["stderr"])
            or stderr_stat["size_bytes"] < stderr_size
            or hashlib.sha256(stderr_bytes[:stderr_size]).hexdigest()
            != stderr_prefix["sha256"]
            or logs["stderr"]["empty"] != (stderr_size == 0)
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_STDERR_PREFIX_MISMATCH"
            )
        print_argv = (
            _LAUNCHCTL,
            "print",
            install_receipt["service"],
        )
        if (
            not _command_evidence_valid(
                receipt["launchctl_print"], print_argv
            )
            or receipt["launchctl_print"]["return_code"] != 0
            or not _print_bindings_valid(
                receipt["launchctl_print"]["stdout_utf8"].encode("utf-8"),
                contract=contract,
                domain=install_receipt["domain"],
                target=Path(install_receipt["target_path"]),
            )
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_LAUNCHCTL_EVIDENCE_INVALID"
            )
        print_text = receipt["launchctl_print"]["stdout_utf8"]
        print_runs = re.findall(
            r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)",
            print_text,
        )
        if (
            "last exit code = 0" not in print_text
            or str(paths["stdout"]) not in print_text
            or str(paths["stderr"]) not in print_text
            or len(print_runs) != 1
            or int(print_runs[0]) != receipt["launchd_runs_observed"]
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_LAUNCHCTL_EVIDENCE_INVALID"
            )
        if (
            receipt["forward_start"] != utc_datetime(_START)
            or receipt["record_deadline"] != utc_datetime(_DEADLINE)
            or _utc(receipt["observed_at"])[0]
            < _utc(first_decision["recorded_at"])[0]
        ):
            reasons.append("CHALLENGER_FIRST_SLOT_TIME_MISMATCH")
        if receipt["receipt_id"] != stable_id(
            "challenger_first_slot_receipt", _identity(receipt)
        ):
            reasons.append(
                "CHALLENGER_FIRST_SLOT_RECEIPT_ID_MISMATCH"
            )
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        ChallengerFirstSlotReceiptError,
    ):
        reasons.append(
            "CHALLENGER_FIRST_SLOT_RECEIPT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _publish_receipt(
    receipt: Mapping[str, Any],
    *,
    output_root: Path,
) -> Path:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_OUTPUT_INVALID"
        )
    directory = requested.resolve() / "challenger-first-slot-receipts"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / f"{receipt['receipt_id']}.json"
    try:
        _publish_exact(path, canonical_json(receipt).encode("utf-8"))
    except ValueError as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_RECEIPT_CONFLICT"
        ) from error
    return path


def observe_challenger_first_slot(
    *,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    receipt_output_root: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    try:
        contract = load_challenger_launchd_contract(
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        install_receipt = load_challenger_install_receipt(
            receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
    except (
        ChallengerLaunchdInstallError,
        ChallengerForwardError,
        OSError,
        ValueError,
    ) as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_SOURCE_INVALID"
        ) from error
    paths = _paths(contract)
    state_evidence, decisions = _read_state(paths["state"])
    observed, observed_at = _utc((clock or _utc_now)())
    if not decisions:
        if observed < _START:
            status = "WAITING_BEFORE_FIRST_SLOT"
        elif observed < _DEADLINE:
            status = "OBSERVATION_PENDING_WITHIN_RECORD_DEADLINE"
        else:
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_MISSED"
            )
        return {
            "status": status,
            "observed_at": observed_at,
            "forward_start": utc_datetime(_START),
            "record_deadline": utc_datetime(_DEADLINE),
            "decision_count": 0,
            "receipt_published": False,
            "launchctl_command_count": 0,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
        }
    first_decision = decisions[0]
    if first_decision.get("scheduled_for") != utc_datetime(_START):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_WRONG_FIRST_DECISION"
        )
    if observed < _utc(first_decision["recorded_at"])[0]:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_TIME_INVALID"
        )
    bundle_evidence, _bundle = _matching_bundle(
        bundle_directory=paths["bundle_directory"],
        first_decision=first_decision,
    )
    logs = _log_evidence(
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        first_decision=first_decision,
        bundle_evidence=bundle_evidence,
    )
    runner = _launchctl_runner or _command_runner
    launchctl_print, launchd_runs = _launchctl_evidence(
        runner=runner,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    )
    receipt = {
        "$schema": "./challenger-first-slot-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_first_slot_receipt_" + "0" * 64,
        "receipt_hash": "0" * 64,
        "observed_at": observed_at,
        "forward_start": utc_datetime(_START),
        "record_deadline": utc_datetime(_DEADLINE),
        "install_receipt": {
            "receipt_id": install_receipt["receipt_id"],
            "receipt_hash": install_receipt["receipt_hash"],
            "target_path": install_receipt["target_path"],
            "target_sha256": install_receipt["target_stat"]["sha256"],
            "execution_snapshot": install_receipt["source_contract"][
                "execution_snapshot"
            ],
        },
        "contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
            "contract_trust_hash": (
                challenger_launchd_contract_trust_hash(contract)
            ),
            "launchd_plist_sha256": contract["launchd_plist_sha256"],
        },
        "launchctl_print": launchctl_print,
        "launchd_runs_observed": launchd_runs,
        "state": {
            **state_evidence,
            "first_decision": dict(first_decision),
            "decision_chain_end_hash": decisions[-1]["decision_hash"],
        },
        "source_bundle": bundle_evidence,
        "logs": logs,
        "observation_status": "FIRST_SLOT_RECORDED_VERIFIED",
        "security_boundary": {
            "launchctl_print_count": 1,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
        },
        "eligibility": {
            "forward_evidence": "LOCAL_PREQUENTIAL_RESEARCH_ONLY",
            "external_time_anchor": "INELIGIBLE_LOCAL_ONLY",
            "paper": "INELIGIBLE_NO_MATURE_OUTCOME",
            "release_oos": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
            "profitability": "INELIGIBLE",
        },
        "warnings": [
            "BINANCE_TIME_RECEIPT_IS_NOT_INDEPENDENT_PUBLICATION",
            "NO_HISTORICAL_BACKFILL",
            "NO_MATURE_OUTCOME",
            "NO_PROFITABILITY_CLAIM",
            *(
                []
                if logs["stderr"]["empty"]
                else ["STDERR_WAS_NONEMPTY_AND_IS_HASH_BOUND"]
            ),
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_first_slot_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_first_slot_receipt_hash(receipt)
    if _receipt_reasons(
        receipt,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_RECEIPT_INVALID"
        )
    receipt_path = _publish_receipt(
        receipt, output_root=receipt_output_root
    )
    return {
        "status": "FIRST_SLOT_RECORDED_VERIFIED",
        "observed_at": observed_at,
        "decision_id": first_decision["decision_id"],
        "decision_hash": first_decision["decision_hash"],
        "source_bundle_hash": bundle_evidence["bundle_hash"],
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "receipt_path": str(receipt_path),
        "receipt_published": True,
        "launchctl_command_count": 1,
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
    }


def load_challenger_first_slot_receipt(
    *,
    receipt_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Mapping[str, Any]:
    try:
        path = Path(receipt_path).expanduser().resolve(strict=True)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size > _MAX_RECEIPT_BYTES
        ):
            raise ChallengerFirstSlotReceiptError(
                "CHALLENGER_FIRST_SLOT_RECEIPT_READ_FAILED"
            )
        receipt = _strict_json_bytes(path.read_bytes())
        contract = load_challenger_launchd_contract(
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        install_receipt = load_challenger_install_receipt(
            receipt_path=Path(install_receipt_path),
            contract_path=Path(contract_path),
            plist_path=Path(plist_path),
        )
        paths = _paths(contract)
    except Exception as error:
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_RECEIPT_READ_FAILED"
        ) from error
    if _receipt_reasons(
        receipt,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerFirstSlotReceiptError(
            "CHALLENGER_FIRST_SLOT_RECEIPT_INVALID"
        )
    return receipt
