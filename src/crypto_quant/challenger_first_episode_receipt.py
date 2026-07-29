"""Read-only, cross-bound receipt for the first challenger episode."""

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id, utc_datetime
from .challenger_first_slot_receipt import (
    ChallengerFirstSlotReceiptError,
    _launchctl_evidence,
    _log_lines,
    _paths,
    _read_state,
    _secure_file,
)
from .challenger_forward import ChallengerForwardError
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
    _command_evidence_valid,
    _command_runner,
    _print_bindings_valid,
    load_challenger_install_receipt,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-first-episode-receipt-v1.schema.json"
_START = datetime(2026, 7, 29, tzinfo=timezone.utc)
_MINIMUM = _START + timedelta(hours=8)
_VERTICAL = _START + timedelta(hours=24)
_CADENCE = timedelta(hours=4)
_MAX_BUNDLE_BYTES = 2 * 1024 * 1024
_MAX_LOG_BYTES = 4 * 1024 * 1024
_MAX_RECEIPT_BYTES = 8 * 1024 * 1024
_ZERO_HASH = "0" * 64
_LAUNCHCTL = "/bin/launchctl"


class ChallengerFirstEpisodeReceiptError(ValueError):
    """The first-episode observation or immutable receipt failed closed."""

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
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
        )
    return converted, rendered


def _flat(state: object) -> bool:
    return state == {
        "position_state": "FLAT",
        "episode_id_or_null": None,
        "entry_decision_time_or_null": None,
        "minimum_hold_until_or_null": None,
        "vertical_exit_at_or_null": None,
    }


def _episode_prefix(
    decisions: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[Mapping[str, Any], ...], bool]:
    if not decisions:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_ENTRY_MISSING"
        )
    first = decisions[0]
    try:
        long_state = first["state_after"]
        episode_id = long_state["episode_id_or_null"]
        if (
            first["sequence"] != 1
            or first["scheduled_for"] != utc_datetime(_START)
            or first["action"] != "ENTER_LONG"
            or not _flat(first["state_before"])
            or long_state["position_state"] != "LONG"
            or not isinstance(episode_id, str)
            or long_state["entry_decision_time_or_null"]
            != utc_datetime(_START)
            or long_state["minimum_hold_until_or_null"]
            != utc_datetime(_MINIMUM)
            or long_state["vertical_exit_at_or_null"]
            != utc_datetime(_VERTICAL)
        ):
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_ENTRY_INVALID"
            )
        prefix = [first]
        for decision in decisions[1:]:
            scheduled = _utc(decision["scheduled_for"])[0]
            if decision["state_before"] != long_state:
                raise ChallengerFirstEpisodeReceiptError(
                    "CHALLENGER_FIRST_EPISODE_STATE_DRIFT"
                )
            action = decision["action"]
            if action in ("HOLD_LONG_MINIMUM", "HOLD_LONG"):
                if decision["state_after"] != long_state:
                    raise ChallengerFirstEpisodeReceiptError(
                        "CHALLENGER_FIRST_EPISODE_STATE_DRIFT"
                    )
                if (
                    action == "HOLD_LONG_MINIMUM"
                    and scheduled >= _MINIMUM
                ) or (action == "HOLD_LONG" and scheduled < _MINIMUM):
                    raise ChallengerFirstEpisodeReceiptError(
                        "CHALLENGER_FIRST_EPISODE_ACTION_INVALID"
                    )
                if scheduled >= _VERTICAL:
                    raise ChallengerFirstEpisodeReceiptError(
                        "CHALLENGER_FIRST_EPISODE_VERTICAL_EXIT_MISSED"
                    )
                prefix.append(decision)
                continue
            if action == "EXIT_LONG_SMA20":
                if scheduled < _MINIMUM or not _flat(
                    decision["state_after"]
                ):
                    raise ChallengerFirstEpisodeReceiptError(
                        "CHALLENGER_FIRST_EPISODE_EXIT_INVALID"
                    )
            elif action == "EXIT_LONG_VERTICAL_24H":
                if scheduled < _VERTICAL or not _flat(
                    decision["state_after"]
                ):
                    raise ChallengerFirstEpisodeReceiptError(
                        "CHALLENGER_FIRST_EPISODE_EXIT_INVALID"
                    )
            else:
                raise ChallengerFirstEpisodeReceiptError(
                    "CHALLENGER_FIRST_EPISODE_ACTION_INVALID"
                )
            prefix.append(decision)
            if len(prefix) > 7:
                raise ChallengerFirstEpisodeReceiptError(
                    "CHALLENGER_FIRST_EPISODE_LENGTH_INVALID"
                )
            return tuple(prefix), True
        if len(prefix) > 6:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_VERTICAL_EXIT_MISSED"
            )
        return tuple(prefix), False
    except (KeyError, TypeError):
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_STATE_INVALID"
        )


def _bundle_evidence(
    *,
    bundle_directory: Path,
    decisions: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    try:
        candidates = sorted(bundle_directory.glob("*.json"))
    except OSError as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_BUNDLE_INVALID"
        ) from error
    by_slot: Dict[str, list] = {}
    for path in candidates:
        try:
            file_stat, _data = _secure_file(
                path,
                maximum_bytes=_MAX_BUNDLE_BYTES,
                allow_empty=False,
                reason_code="CHALLENGER_FIRST_EPISODE_BUNDLE_INVALID",
            )
            bundle = load_challenger_source_bundle(path)
        except (
            ChallengerFirstSlotReceiptError,
            ChallengerForwardRunnerError,
        ) as error:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_BUNDLE_INVALID"
            ) from error
        by_slot.setdefault(bundle["scheduled_for"], []).append(
            (path, file_stat, bundle)
        )
    evidence = []
    for decision in decisions:
        matches = by_slot.get(decision["scheduled_for"], [])
        if len(matches) != 1:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_BUNDLE_COUNT_INVALID"
            )
        path, file_stat, bundle = matches[0]
        if bundle["candidate_decision"] != decision:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_BUNDLE_DECISION_MISMATCH"
            )
        evidence.append(
            {
                "sequence": decision["sequence"],
                "scheduled_for": decision["scheduled_for"],
                "path": str(path.resolve()),
                "file_stat": file_stat,
                "bundle_id": bundle["bundle_id"],
                "bundle_hash": bundle["bundle_hash"],
                "decision_id": decision["decision_id"],
                "decision_hash": decision["decision_hash"],
            }
        )
    return tuple(evidence)


def _logs(
    *,
    stdout_path: Path,
    stderr_path: Path,
    decisions: Sequence[Mapping[str, Any]],
    bundles: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    try:
        stdout_stat, stdout_bytes = _secure_file(
            stdout_path,
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_FIRST_EPISODE_STDOUT_INVALID",
        )
        stderr_stat, _stderr_bytes = _secure_file(
            stderr_path,
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_FIRST_EPISODE_STDERR_INVALID",
        )
        records = _log_lines(stdout_bytes)
    except ChallengerFirstSlotReceiptError as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_LOG_INVALID"
        ) from error
    matched = []
    for decision, bundle in zip(decisions, bundles):
        matches = []
        for line_number, record in enumerate(records, 1):
            if (
                record.get("status") == "RECORDED"
                and record.get("decision_count") == decision["sequence"]
                and record.get("decision_id") == decision["decision_id"]
                and record.get("decision_hash") == decision["decision_hash"]
                and record.get("source_bundle_path") == bundle["path"]
                and record.get("source_bundle_hash")
                == bundle["bundle_hash"]
                and record.get("server_time_request_count") == 3
                and record.get("kline_request_count") == 1
                and record.get("broker_request_count") == 0
                and record.get("order_submission_count") == 0
            ):
                matches.append((line_number, record))
        if len(matches) != 1:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_LOG_MATCH_INVALID"
            )
        line_number, record = matches[0]
        matched.append(
            {
                "sequence": decision["sequence"],
                "line_number": line_number,
                "record": dict(record),
                "record_hash": hashlib.sha256(
                    canonical_json(record).encode("utf-8")
                ).hexdigest(),
            }
        )
    return {
        "stdout": {
            "path": str(stdout_path),
            "observed_prefix_stat": stdout_stat,
            "matched_records": matched,
        },
        "stderr": {
            "path": str(stderr_path),
            "observed_prefix_stat": stderr_stat,
            "empty": stderr_stat["size_bytes"] == 0,
        },
    }


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_first_episode_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "install_receipt_hash": receipt["install_receipt"][
            "receipt_hash"
        ],
        "observed_at": receipt["observed_at"],
        "episode_id": receipt["episode"]["episode_id"],
        "decisions_root_hash": receipt["state"]["decisions_root_hash"],
        "stdout_prefix_hash": receipt["logs"]["stdout"][
            "observed_prefix_stat"
        ]["sha256"],
        "launchctl_print_hash": receipt["launchctl_print"][
            "command_evidence_hash"
        ],
    }


def _trusted_sources(
    *,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
) -> Tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Path]]:
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
        paths = _paths(contract)
    except (
        ChallengerLaunchdInstallError,
        ChallengerForwardError,
        ChallengerFirstSlotReceiptError,
        OSError,
        ValueError,
    ) as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_SOURCE_INVALID"
        ) from error
    return contract, install_receipt, paths


def _receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_RECEIPT_SCHEMA_INVALID"
            )
        if receipt.get(
            "receipt_hash"
        ) != challenger_first_episode_receipt_hash(receipt):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_RECEIPT_HASH_MISMATCH"
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
                "CHALLENGER_FIRST_EPISODE_INSTALL_MISMATCH"
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
                "CHALLENGER_FIRST_EPISODE_CONTRACT_MISMATCH"
            )
        print_argv = (
            _LAUNCHCTL,
            "print",
            install_receipt["service"],
        )
        print_evidence = receipt["launchctl_print"]
        print_text = print_evidence["stdout_utf8"]
        run_matches = re.findall(
            r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)",
            print_text,
        )
        if (
            not _command_evidence_valid(print_evidence, print_argv)
            or print_evidence["return_code"] != 0
            or not _print_bindings_valid(
                print_text.encode("utf-8"),
                contract=contract,
                domain=install_receipt["domain"],
                target=Path(install_receipt["target_path"]),
            )
            or str(paths["stdout"]) not in print_text
            or str(paths["stderr"]) not in print_text
            or "last exit code = 0" not in print_text
            or len(run_matches) != 1
            or int(run_matches[0]) != receipt["launchd_runs_observed"]
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_LAUNCHCTL_INVALID"
            )
        state, decisions = _read_state(paths["state"])
        count = receipt["state"]["episode_decision_count"]
        current_prefix, completed = _episode_prefix(decisions)
        if (
            not completed
            or count != len(receipt["state"]["decisions"])
            or count != len(receipt["source_bundles"])
            or len(current_prefix) < count
            or list(current_prefix[:count])
            != receipt["state"]["decisions"]
            or receipt["state"]["path"] != state["path"]
            or receipt["state"]["metadata"] != state["metadata"]
            or receipt["state"]["total_decision_count_observed"] < count
            or len(decisions)
            < receipt["state"]["total_decision_count_observed"]
            or receipt["state"]["observed_decisions_root_hash"]
            != business_hash(
                list(
                    decisions[
                        : receipt["state"][
                            "total_decision_count_observed"
                        ]
                    ]
                )
            )
            or receipt["state"]["observed_state_chain_end_hash"]
            != decisions[
                receipt["state"]["total_decision_count_observed"] - 1
            ]["decision_hash"]
            or receipt["state"]["decisions_root_hash"]
            != business_hash(receipt["state"]["decisions"])
            or receipt["state"]["decision_chain_end_hash"]
            != receipt["state"]["decisions"][-1]["decision_hash"]
        ):
            reasons.append("CHALLENGER_FIRST_EPISODE_STATE_MISMATCH")
        bundles = _bundle_evidence(
            bundle_directory=paths["bundle_directory"],
            decisions=receipt["state"]["decisions"],
        )
        if list(bundles) != receipt["source_bundles"]:
            reasons.append("CHALLENGER_FIRST_EPISODE_BUNDLE_MISMATCH")
        stdout_stat, stdout_bytes = _secure_file(
            paths["stdout"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_FIRST_EPISODE_STDOUT_INVALID",
        )
        stdout = receipt["logs"]["stdout"]
        prefix_size = stdout["observed_prefix_stat"]["size_bytes"]
        if (
            stdout["path"] != str(paths["stdout"])
            or stdout_stat["size_bytes"] < prefix_size
            or hashlib.sha256(stdout_bytes[:prefix_size]).hexdigest()
            != stdout["observed_prefix_stat"]["sha256"]
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_STDOUT_PREFIX_MISMATCH"
            )
        records = _log_lines(stdout_bytes[:prefix_size])
        if len(stdout["matched_records"]) != count:
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_LOG_RECORD_MISMATCH"
            )
        else:
            for decision, bundle, matched in zip(
                receipt["state"]["decisions"],
                receipt["source_bundles"],
                stdout["matched_records"],
            ):
                line = matched["line_number"]
                record = matched["record"]
                if (
                    matched["sequence"] != decision["sequence"]
                    or line < 1
                    or line > len(records)
                    or records[line - 1] != record
                    or hashlib.sha256(
                        canonical_json(record).encode("utf-8")
                    ).hexdigest()
                    != matched["record_hash"]
                    or record.get("status") != "RECORDED"
                    or record.get("decision_count")
                    != decision["sequence"]
                    or record.get("decision_id")
                    != decision["decision_id"]
                    or record.get("decision_hash")
                    != decision["decision_hash"]
                    or record.get("source_bundle_path")
                    != bundle["path"]
                    or record.get("source_bundle_hash")
                    != bundle["bundle_hash"]
                    or record.get("server_time_request_count") != 3
                    or record.get("kline_request_count") != 1
                    or record.get("broker_request_count") != 0
                    or record.get("order_submission_count") != 0
                ):
                    reasons.append(
                        "CHALLENGER_FIRST_EPISODE_LOG_RECORD_MISMATCH"
                    )
        stderr_stat, stderr_bytes = _secure_file(
            paths["stderr"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_FIRST_EPISODE_STDERR_INVALID",
        )
        stderr = receipt["logs"]["stderr"]
        stderr_size = stderr["observed_prefix_stat"]["size_bytes"]
        if (
            stderr["path"] != str(paths["stderr"])
            or stderr_stat["size_bytes"] < stderr_size
            or hashlib.sha256(stderr_bytes[:stderr_size]).hexdigest()
            != stderr["observed_prefix_stat"]["sha256"]
            or stderr["empty"] != (stderr_size == 0)
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_STDERR_PREFIX_MISMATCH"
            )
        if receipt["receipt_id"] != stable_id(
            "challenger_first_episode_receipt", _identity(receipt)
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_RECEIPT_ID_MISMATCH"
            )
        final = receipt["state"]["decisions"][-1]
        first = receipt["state"]["decisions"][0]
        if receipt["episode"] != {
            "episode_id": first["state_after"]["episode_id_or_null"],
            "entry_scheduled_for": first["scheduled_for"],
            "minimum_hold_until": first["state_after"][
                "minimum_hold_until_or_null"
            ],
            "vertical_exit_at": first["state_after"][
                "vertical_exit_at_or_null"
            ],
            "exit_scheduled_for": final["scheduled_for"],
            "exit_action": final["action"],
        }:
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_SUMMARY_MISMATCH"
            )
        if (
            receipt["forward_start"] != utc_datetime(_START)
            or receipt["minimum_hold_until"] != utc_datetime(_MINIMUM)
            or receipt["vertical_exit_at"] != utc_datetime(_VERTICAL)
            or _utc(receipt["observed_at"])[0]
            < _utc(final["recorded_at"])[0]
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_TIME_MISMATCH"
            )
        if (
            receipt["security_boundary"]
            != {
                "launchctl_print_count": 1,
                "network_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "shell_invoked": False,
                "arbitrary_command_allowed": False,
            }
            or receipt["eligibility"]["profitability"] != "INELIGIBLE"
            or "NO_PROFITABILITY_CLAIM" not in receipt["warnings"]
        ):
            reasons.append(
                "CHALLENGER_FIRST_EPISODE_BOUNDARY_INVALID"
            )
    except (
        ChallengerFirstEpisodeReceiptError,
        ChallengerFirstSlotReceiptError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append(
            "CHALLENGER_FIRST_EPISODE_RECEIPT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _publish_receipt(
    receipt: Mapping[str, Any], *, output_root: Path
) -> Path:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_OUTPUT_INVALID"
        )
    directory = (
        requested.resolve() / "challenger-first-episode-receipts"
    )
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / f"{receipt['receipt_id']}.json"
    try:
        _publish_exact(path, canonical_json(receipt).encode("utf-8"))
    except ValueError as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_RECEIPT_CONFLICT"
        ) from error
    return path


def observe_challenger_first_episode(
    *,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    receipt_output_root: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    contract, install_receipt, paths = _trusted_sources(
        install_receipt_path=install_receipt_path,
        contract_path=contract_path,
        plist_path=plist_path,
    )
    try:
        state_evidence, decisions = _read_state(paths["state"])
    except ChallengerFirstSlotReceiptError as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_STATE_INVALID"
        ) from error
    observed, observed_at = _utc((clock or _utc_now)())
    prefix, completed = _episode_prefix(decisions)
    if observed < _utc(prefix[-1]["recorded_at"])[0]:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_TIME_INVALID"
        )
    if not completed:
        next_slot = _utc(prefix[-1]["scheduled_for"])[0] + _CADENCE
        if observed >= next_slot + _CADENCE:
            raise ChallengerFirstEpisodeReceiptError(
                "CHALLENGER_FIRST_EPISODE_SLOT_MISSED"
            )
    bundles = _bundle_evidence(
        bundle_directory=paths["bundle_directory"],
        decisions=prefix,
    )
    logs = _logs(
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        decisions=prefix,
        bundles=bundles,
    )
    try:
        launchctl_print, launchd_runs = _launchctl_evidence(
            runner=_launchctl_runner or _command_runner,
            contract=contract,
            install_receipt=install_receipt,
            paths=paths,
        )
    except (
        ChallengerFirstSlotReceiptError,
        ChallengerLaunchdInstallError,
    ) as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_SERVICE_INVALID"
        ) from error
    common = {
        "observed_at": observed_at,
        "episode_id": prefix[0]["state_after"]["episode_id_or_null"],
        "decision_count": len(prefix),
        "last_scheduled_for": prefix[-1]["scheduled_for"],
        "minimum_hold_until": utc_datetime(_MINIMUM),
        "vertical_exit_at": utc_datetime(_VERTICAL),
        "launchctl_command_count": 1,
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
    }
    if not completed:
        return {
            "status": "FIRST_EPISODE_IN_PROGRESS_VERIFIED",
            **common,
            "next_scheduled_for": utc_datetime(
                _utc(prefix[-1]["scheduled_for"])[0] + _CADENCE
            ),
            "receipt_published": False,
        }
    final = prefix[-1]
    receipt = {
        "$schema": "./challenger-first-episode-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_first_episode_receipt_" + _ZERO_HASH,
        "receipt_hash": _ZERO_HASH,
        "observed_at": observed_at,
        "forward_start": utc_datetime(_START),
        "minimum_hold_until": utc_datetime(_MINIMUM),
        "vertical_exit_at": utc_datetime(_VERTICAL),
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
            "path": state_evidence["path"],
            "observed_file_stat": state_evidence["file_stat"],
            "metadata": state_evidence["metadata"],
            "total_decision_count_observed": state_evidence[
                "decision_count"
            ],
            "observed_decisions_root_hash": business_hash(
                list(decisions)
            ),
            "observed_state_chain_end_hash": state_evidence[
                "decision_chain_end_hash_or_null"
            ],
            "episode_decision_count": len(prefix),
            "decisions": list(prefix),
            "decisions_root_hash": business_hash(list(prefix)),
            "decision_chain_end_hash": final["decision_hash"],
        },
        "episode": {
            "episode_id": prefix[0]["state_after"][
                "episode_id_or_null"
            ],
            "entry_scheduled_for": prefix[0]["scheduled_for"],
            "minimum_hold_until": utc_datetime(_MINIMUM),
            "vertical_exit_at": utc_datetime(_VERTICAL),
            "exit_scheduled_for": final["scheduled_for"],
            "exit_action": final["action"],
        },
        "source_bundles": list(bundles),
        "logs": logs,
        "observation_status": "FIRST_EPISODE_COMPLETED_VERIFIED",
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
            "paper": "INELIGIBLE_SINGLE_EPISODE",
            "release_oos": "INELIGIBLE_FORWARD_COLLECTION_ONLY",
            "profitability": "INELIGIBLE",
        },
        "warnings": [
            "BINANCE_TIME_RECEIPT_IS_NOT_INDEPENDENT_PUBLICATION",
            "NO_HISTORICAL_BACKFILL",
            "NO_EXECUTION_OR_COST_MODEL_BOUND",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "NO_PROFITABILITY_CLAIM",
            *(
                []
                if logs["stderr"]["empty"]
                else ["STDERR_WAS_NONEMPTY_AND_IS_HASH_BOUND"]
            ),
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_first_episode_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_first_episode_receipt_hash(
        receipt
    )
    if _receipt_reasons(
        receipt,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_RECEIPT_INVALID"
        )
    receipt_path = _publish_receipt(
        receipt, output_root=receipt_output_root
    )
    return {
        "status": "FIRST_EPISODE_COMPLETED_VERIFIED",
        **common,
        "exit_action": final["action"],
        "exit_scheduled_for": final["scheduled_for"],
        "receipt_id": receipt["receipt_id"],
        "receipt_hash": receipt["receipt_hash"],
        "receipt_path": str(receipt_path),
        "receipt_published": True,
    }


def load_challenger_first_episode_receipt(
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
            raise ValueError
        receipt = _strict_json_bytes(path.read_bytes())
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
        )
    except Exception as error:
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_RECEIPT_READ_FAILED"
        ) from error
    if _receipt_reasons(
        receipt,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerFirstEpisodeReceiptError(
            "CHALLENGER_FIRST_EPISODE_RECEIPT_INVALID"
        )
    return receipt
