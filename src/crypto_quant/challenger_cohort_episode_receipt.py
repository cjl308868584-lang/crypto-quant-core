"""Read-only, all-inclusive receipts for Challenger cohort Episodes."""

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
from .challenger_episode_cohort_plan import (
    challenger_episode_cohort_plan_hash,
)
from .challenger_first_episode_receipt import (
    _bundle_evidence,
    _logs,
    _trusted_sources,
)
from .challenger_first_slot_receipt import (
    ChallengerFirstSlotReceiptError,
    _launchctl_evidence,
    _log_lines,
    _read_state,
    _secure_file,
)
from .challenger_launchd import challenger_launchd_contract_trust_hash
from .challenger_launchd_install import (
    _command_evidence_valid,
    _command_runner,
    _print_bindings_valid,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-cohort-episode-receipt-v1.schema.json"
_ZERO_HASH = "0" * 64
_PLAN_ID = (
    "challenger_episode_cohort_plan_"
    "56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c"
)
_PLAN_HASH = (
    "20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201"
)
_PLAN_FILE_SHA256 = (
    "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff"
)
_START = datetime(2026, 7, 30, 12, tzinfo=timezone.utc)
_END = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
_TAIL = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
_CADENCE = timedelta(hours=4)
_MAX_PLAN_BYTES = 256 * 1024
_MAX_RECEIPT_BYTES = 64 * 1024 * 1024
_MAX_LOG_BYTES = 64 * 1024 * 1024
_LAUNCHCTL = "/bin/launchctl"


class ChallengerCohortEpisodeReceiptError(ValueError):
    """A cohort continuity observation or Episode receipt failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
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


def _read_exact_plan(path: Path) -> Tuple[Mapping[str, Any], str]:
    try:
        requested = Path(path).expanduser()
        status = requested.lstat()
        if (
            not requested.is_absolute()
            or stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) not in (0o600, 0o644)
            or status.st_size <= 0
            or status.st_size > _MAX_PLAN_BYTES
        ):
            raise ValueError
        body = requested.resolve(strict=True).read_bytes()
        file_sha256 = hashlib.sha256(body).hexdigest()
        plan = _strict_json_bytes(
            body[:-1] if body.endswith(b"\n") else body
        )
        if (
            file_sha256 != _PLAN_FILE_SHA256
            or plan.get("plan_id") != _PLAN_ID
            or plan.get("plan_hash") != _PLAN_HASH
            or plan.get("plan_hash")
            != challenger_episode_cohort_plan_hash(plan)
            or plan.get("status")
            != "PREREGISTERED_BEFORE_SECOND_EPISODE"
            or plan["cohort"]["start_inclusive"] != utc_datetime(_START)
            or plan["cohort"]["end_exclusive"] != utc_datetime(_END)
            or plan["cohort"]["observation_tail_end"]
            != utc_datetime(_TAIL)
            or plan["cohort"]["slot_cadence_seconds"] != 14400
            or plan["cohort"]["episode_omission_allowed"]
            or plan["cohort"]["historical_backfill_allowed"]
            or plan["authority"]["episode_override_allowed"]
            or plan["authority"]["state_write_count"] != 0
            or plan["authority"]["runner_invocation_count"] != 0
            or plan["authority"]["broker_request_count"] != 0
            or plan["authority"]["order_submission_count"] != 0
        ):
            raise ValueError
        return plan, file_sha256
    except Exception as error:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_PLAN_INVALID"
        ) from error


def _slot_summary(decision: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "sequence": decision["sequence"],
        "scheduled_for": decision["scheduled_for"],
        "action": decision["action"],
        "decision_id": decision["decision_id"],
        "decision_hash": decision["decision_hash"],
        "previous_decision_hash": decision["previous_decision_hash"],
        "state_before": decision["state_before"],
        "state_after": decision["state_after"],
    }


def _partition(
    decisions: Sequence[Mapping[str, Any]],
    *,
    observed: datetime,
) -> Tuple[
    Tuple[Mapping[str, Any], ...],
    Tuple[Tuple[int, int], ...],
    Optional[Tuple[int, int]],
    Optional[datetime],
]:
    cohort = []
    completed = []
    active_start: Optional[int] = None
    first_after_start = None
    for decision in decisions:
        scheduled = _utc(decision["scheduled_for"])[0]
        if scheduled < _START:
            continue
        if first_after_start is None:
            first_after_start = scheduled
        if scheduled >= _END and active_start is None:
            break
        if scheduled >= _TAIL:
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_TAIL_EXCEEDED"
            )
        if not cohort and scheduled != _START:
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_SLOT_MISSED"
            )
        if cohort and scheduled != (
            _utc(cohort[-1]["scheduled_for"])[0] + _CADENCE
        ):
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_SLOT_MISSED"
            )
        before = decision["state_before"]
        after = decision["state_after"]
        action = decision["action"]
        index = len(cohort)
        if active_start is None:
            if not _flat(before):
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_STATE_INVALID"
                )
            if action == "REJECT_ENTRY":
                if not _flat(after):
                    raise ChallengerCohortEpisodeReceiptError(
                        "CHALLENGER_COHORT_EPISODE_STATE_INVALID"
                    )
            elif action == "ENTER_LONG" and scheduled < _END:
                if (
                    after.get("position_state") != "LONG"
                    or after.get("entry_decision_time_or_null")
                    != decision["scheduled_for"]
                    or not isinstance(
                        after.get("episode_id_or_null"), str
                    )
                    or _utc(after["minimum_hold_until_or_null"])[0]
                    != scheduled + timedelta(hours=8)
                    or _utc(after["vertical_exit_at_or_null"])[0]
                    != scheduled + timedelta(hours=24)
                ):
                    raise ChallengerCohortEpisodeReceiptError(
                        "CHALLENGER_COHORT_EPISODE_ENTRY_INVALID"
                    )
                active_start = index
            else:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_ACTION_INVALID"
                )
        else:
            entry = cohort[active_start]
            long_state = entry["state_after"]
            scheduled_entry = _utc(entry["scheduled_for"])[0]
            minimum = scheduled_entry + timedelta(hours=8)
            vertical = scheduled_entry + timedelta(hours=24)
            if before != long_state:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_STATE_INVALID"
                )
            if action in ("HOLD_LONG_MINIMUM", "HOLD_LONG"):
                if (
                    after != long_state
                    or (
                        action == "HOLD_LONG_MINIMUM"
                        and scheduled >= minimum
                    )
                    or (action == "HOLD_LONG" and scheduled < minimum)
                    or scheduled >= vertical
                ):
                    raise ChallengerCohortEpisodeReceiptError(
                        "CHALLENGER_COHORT_EPISODE_ACTION_INVALID"
                    )
            elif action == "EXIT_LONG_SMA20":
                if scheduled < minimum or not _flat(after):
                    raise ChallengerCohortEpisodeReceiptError(
                        "CHALLENGER_COHORT_EPISODE_EXIT_INVALID"
                    )
                completed.append((active_start, index))
                active_start = None
            elif action == "EXIT_LONG_VERTICAL_24H":
                if scheduled < vertical or not _flat(after):
                    raise ChallengerCohortEpisodeReceiptError(
                        "CHALLENGER_COHORT_EPISODE_EXIT_INVALID"
                    )
                completed.append((active_start, index))
                active_start = None
            else:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_ACTION_INVALID"
                )
        cohort.append(decision)

    if first_after_start is not None and first_after_start != _START:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_SLOT_MISSED"
        )
    expected = _START if not cohort else (
        _utc(cohort[-1]["scheduled_for"])[0] + _CADENCE
    )
    required = expected < _END or active_start is not None
    if required and observed >= expected + _CADENCE:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_SLOT_MISSED"
        )
    if active_start is not None:
        entry = cohort[active_start]
        if observed >= _utc(
            entry["state_after"]["vertical_exit_at_or_null"]
        )[0] + _CADENCE:
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_VERTICAL_EXIT_MISSED"
            )
    if observed >= _TAIL and (
        active_start is not None
        or len([row for row in cohort if _utc(row["scheduled_for"])[0] < _END])
        != 540
    ):
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_COHORT_INCOMPLETE"
        )
    active = (
        (active_start, len(cohort) - 1)
        if active_start is not None
        else None
    )
    return tuple(cohort), tuple(completed), active, (
        expected if required else None
    )


def challenger_cohort_episode_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    return artifact_self_hash(receipt, "receipt_hash")


def _identity(receipt: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "cohort_plan_hash": receipt["cohort_plan"]["plan_hash"],
        "episode_id": receipt["episode"]["episode_id"],
        "entry_decision_hash": receipt["episode"][
            "entry_decision_hash"
        ],
        "exit_decision_hash": receipt["episode"]["exit_decision_hash"],
        "cohort_prefix_root_hash": receipt["state"][
            "cohort_prefix_root_hash"
        ],
        "prior_completed_episode_ids_root_hash": receipt[
            "prior_completed_episodes"
        ]["episode_ids_root_hash"],
    }


def _receipt_path(
    output_root: Path,
    *,
    entry_scheduled_for: str,
    episode_id: str,
) -> Path:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_OUTPUT_INVALID"
        )
    try:
        requested.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(requested, 0o700)
        root_status = requested.lstat()
        if (
            not stat.S_ISDIR(root_status.st_mode)
            or stat.S_ISLNK(root_status.st_mode)
            or root_status.st_uid != os.getuid()
            or stat.S_IMODE(root_status.st_mode) != 0o700
        ):
            raise ValueError
    except Exception as error:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_OUTPUT_INVALID"
        ) from error
    directory = (
        requested.resolve(strict=True)
        / "challenger-cohort-episode-receipts"
    )
    stamp = (
        entry_scheduled_for.replace("-", "")
        .replace(":", "")
        .replace(".000", "")
    )
    return directory / f"{stamp}-{episode_id}.json"


def _build_receipt(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    state_evidence: Mapping[str, Any],
    all_decisions: Sequence[Mapping[str, Any]],
    cohort_prefix: Sequence[Mapping[str, Any]],
    episode_decisions: Sequence[Mapping[str, Any]],
    prefix_bundles: Sequence[Mapping[str, Any]],
    prefix_logs: Mapping[str, Any],
    launchctl_print: Mapping[str, Any],
    launchd_runs: int,
    observed_at: str,
    ordinal: int,
    prior_ids: Sequence[str],
) -> Dict[str, Any]:
    entry = episode_decisions[0]
    exit_decision = episode_decisions[-1]
    receipt = {
        "$schema": "./challenger-cohort-episode-receipt-v1.schema.json",
        "schema_version": "1.0.0",
        "receipt_id": "challenger_cohort_episode_receipt_" + _ZERO_HASH,
        "receipt_hash": _ZERO_HASH,
        "observed_at": observed_at,
        "cohort_plan": {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "plan_file_sha256": plan_file_sha256,
            "start_inclusive": plan["cohort"]["start_inclusive"],
            "end_exclusive": plan["cohort"]["end_exclusive"],
            "observation_tail_end": plan["cohort"][
                "observation_tail_end"
            ],
        },
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
            "total_decision_count_observed": len(all_decisions),
            "observed_decisions_root_hash": business_hash(
                list(all_decisions)
            ),
            "observed_state_chain_end_hash": state_evidence[
                "decision_chain_end_hash_or_null"
            ],
            "cohort_prefix_slot_count": len(cohort_prefix),
            "cohort_prefix_slots": [
                _slot_summary(value) for value in cohort_prefix
            ],
            "cohort_prefix_root_hash": business_hash(
                [_slot_summary(value) for value in cohort_prefix]
            ),
            "cohort_prefix_chain_end_hash": cohort_prefix[-1][
                "decision_hash"
            ],
        },
        "episode": {
            "ordinal": ordinal,
            "episode_id": entry["state_after"]["episode_id_or_null"],
            "entry_sequence": entry["sequence"],
            "entry_scheduled_for": entry["scheduled_for"],
            "entry_recorded_at": entry["recorded_at"],
            "entry_decision_id": entry["decision_id"],
            "entry_decision_hash": entry["decision_hash"],
            "minimum_hold_until": entry["state_after"][
                "minimum_hold_until_or_null"
            ],
            "vertical_exit_at": entry["state_after"][
                "vertical_exit_at_or_null"
            ],
            "exit_sequence": exit_decision["sequence"],
            "exit_scheduled_for": exit_decision["scheduled_for"],
            "exit_recorded_at": exit_decision["recorded_at"],
            "exit_action": exit_decision["action"],
            "exit_decision_id": exit_decision["decision_id"],
            "exit_decision_hash": exit_decision["decision_hash"],
            "decision_count": len(episode_decisions),
            "decisions": list(episode_decisions),
            "decisions_root_hash": business_hash(
                list(episode_decisions)
            ),
        },
        "prior_completed_episodes": {
            "count": len(prior_ids),
            "episode_ids": list(prior_ids),
            "episode_ids_root_hash": business_hash(list(prior_ids)),
        },
        "source_bundles": list(prefix_bundles),
        "logs": prefix_logs,
        "observation_status": "COHORT_EPISODE_COMPLETED_VERIFIED",
        "security_boundary": {
            "launchctl_print_count": 1,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "episode_selector_allowed": False,
        },
        "eligibility": {
            "cohort": "CONFIRMATORY_COHORT_MEMBER",
            "forward_evidence": "LOCAL_PREQUENTIAL_RESEARCH_ONLY",
            "execution": "INELIGIBLE_NO_ECONOMIC_RESULT",
            "paper": "INELIGIBLE_COHORT_COLLECTION_INCOMPLETE",
            "profitability": "INELIGIBLE",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_COHORT",
        },
        "warnings": [
            "NO_HISTORICAL_BACKFILL",
            "REJECTED_ENTRY_SLOTS_ARE_PREFIX_BOUND",
            "EPISODE_SELECTION_IS_NOT_ALLOWED",
            "NO_EXECUTION_OR_COST_RESULT_IN_THIS_RECEIPT",
            "SINGLE_EPISODE_CANNOT_ESTABLISH_EDGE",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
            *(
                []
                if prefix_logs["stderr"]["empty"]
                else ["STDERR_WAS_NONEMPTY_AND_IS_HASH_BOUND"]
            ),
        ],
    }
    receipt["receipt_id"] = stable_id(
        "challenger_cohort_episode_receipt", _identity(receipt)
    )
    receipt["receipt_hash"] = challenger_cohort_episode_receipt_hash(
        receipt
    )
    if tuple(_validator().iter_errors(receipt)):
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_RECEIPT_SCHEMA_INVALID"
        )
    return receipt


def _logs_through(
    logs: Mapping[str, Any],
    *,
    stdout_path: Path,
    matched_count: int,
) -> Mapping[str, Any]:
    matched = logs["stdout"]["matched_records"][:matched_count]
    if len(matched) != matched_count or not matched:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_LOG_INVALID"
        )
    try:
        _file_stat, data = _secure_file(
            stdout_path,
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_COHORT_EPISODE_STDOUT_INVALID",
        )
        lines = data.splitlines(keepends=True)
        last_line = matched[-1]["line_number"]
        if last_line < 1 or last_line > len(lines):
            raise ValueError
        prefix = b"".join(lines[:last_line])
        observed_prefix_stat = dict(
            logs["stdout"]["observed_prefix_stat"]
        )
        observed_prefix_stat["size_bytes"] = len(prefix)
        observed_prefix_stat["sha256"] = hashlib.sha256(
            prefix
        ).hexdigest()
    except Exception as error:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_LOG_INVALID"
        ) from error
    return {
        "stdout": {
            "path": logs["stdout"]["path"],
            "observed_prefix_stat": observed_prefix_stat,
            "matched_records": matched,
        },
        "stderr": logs["stderr"],
    }


def _receipt_reasons(
    receipt: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    contract: Mapping[str, Any],
    install_receipt: Mapping[str, Any],
    paths: Mapping[str, Path],
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(receipt)):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_RECEIPT_SCHEMA_INVALID"
            )
        if receipt.get(
            "receipt_hash"
        ) != challenger_cohort_episode_receipt_hash(receipt):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_RECEIPT_HASH_MISMATCH"
            )
        if receipt.get("receipt_id") != stable_id(
            "challenger_cohort_episode_receipt", _identity(receipt)
        ):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_RECEIPT_ID_MISMATCH"
            )
        if receipt["cohort_plan"] != {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "plan_file_sha256": plan_file_sha256,
            "start_inclusive": plan["cohort"]["start_inclusive"],
            "end_exclusive": plan["cohort"]["end_exclusive"],
            "observation_tail_end": plan["cohort"][
                "observation_tail_end"
            ],
        }:
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_PLAN_MISMATCH"
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
                "CHALLENGER_COHORT_EPISODE_INSTALL_MISMATCH"
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
                "CHALLENGER_COHORT_EPISODE_CONTRACT_MISMATCH"
            )
        print_argv = (_LAUNCHCTL, "print", install_receipt["service"])
        print_evidence = receipt["launchctl_print"]
        print_text = print_evidence["stdout_utf8"]
        run_matches = re.findall(
            r"(?:^|\n)[ \t]*runs = ([0-9]+)(?:\n|$)", print_text
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
                "CHALLENGER_COHORT_EPISODE_LAUNCHCTL_INVALID"
            )
        current_state, decisions = _read_state(paths["state"])
        count = receipt["state"]["cohort_prefix_slot_count"]
        observed_count = receipt["state"][
            "total_decision_count_observed"
        ]
        current = [
            row
            for row in decisions
            if _START <= _utc(row["scheduled_for"])[0]
        ][:count]
        summaries = [_slot_summary(row) for row in current]
        if (
            receipt["state"]["path"] != current_state["path"]
            or receipt["state"]["metadata"] != current_state["metadata"]
            or observed_count < count
            or observed_count > len(decisions)
            or receipt["state"]["observed_decisions_root_hash"]
            != business_hash(list(decisions[:observed_count]))
            or receipt["state"]["observed_state_chain_end_hash"]
            != decisions[observed_count - 1]["decision_hash"]
            or len(current) != count
            or summaries != receipt["state"]["cohort_prefix_slots"]
            or business_hash(summaries)
            != receipt["state"]["cohort_prefix_root_hash"]
            or current[-1]["decision_hash"]
            != receipt["state"]["cohort_prefix_chain_end_hash"]
        ):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_STATE_PREFIX_MISMATCH"
            )
        episode = receipt["episode"]
        start_index = next(
            index
            for index, row in enumerate(current)
            if row["decision_hash"] == episode["entry_decision_hash"]
        )
        end_index = next(
            index
            for index, row in enumerate(current)
            if row["decision_hash"] == episode["exit_decision_hash"]
        )
        episode_decisions = current[start_index : end_index + 1]
        prior = [
            current[start]["state_after"]["episode_id_or_null"]
            for start, end in _completed_ranges(current)
            if end < start_index
        ]
        if (
            list(episode_decisions) != episode["decisions"]
            or episode["decisions_root_hash"]
            != business_hash(list(episode_decisions))
            or episode["decision_count"] != len(episode_decisions)
            or receipt["prior_completed_episodes"]
            != {
                "count": len(prior),
                "episode_ids": prior,
                "episode_ids_root_hash": business_hash(prior),
            }
        ):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_EPISODE_MISMATCH"
            )
        bundles = _bundle_evidence(
            bundle_directory=paths["bundle_directory"],
            decisions=current,
        )
        if list(bundles) != receipt["source_bundles"]:
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_BUNDLE_MISMATCH"
            )
        stdout_stat, stdout_bytes = _secure_file(
            paths["stdout"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=False,
            reason_code="CHALLENGER_COHORT_EPISODE_STDOUT_INVALID",
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
                "CHALLENGER_COHORT_EPISODE_STDOUT_PREFIX_MISMATCH"
            )
        records = _log_lines(stdout_bytes[:prefix_size])
        if len(stdout["matched_records"]) != count:
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_LOG_MISMATCH"
            )
        else:
            for decision, bundle, matched in zip(
                current, bundles, stdout["matched_records"]
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
                        "CHALLENGER_COHORT_EPISODE_LOG_MISMATCH"
                    )
        stderr_stat, stderr_bytes = _secure_file(
            paths["stderr"],
            maximum_bytes=_MAX_LOG_BYTES,
            allow_empty=True,
            reason_code="CHALLENGER_COHORT_EPISODE_STDERR_INVALID",
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
                "CHALLENGER_COHORT_EPISODE_STDERR_PREFIX_MISMATCH"
            )
        if receipt["security_boundary"] != {
            "launchctl_print_count": 1,
            "network_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "shell_invoked": False,
            "arbitrary_command_allowed": False,
            "episode_selector_allowed": False,
        }:
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_BOUNDARY_INVALID"
            )
        entry = episode_decisions[0]
        final = episode_decisions[-1]
        expected_episode = {
            "ordinal": episode["ordinal"],
            "episode_id": entry["state_after"]["episode_id_or_null"],
            "entry_sequence": entry["sequence"],
            "entry_scheduled_for": entry["scheduled_for"],
            "entry_recorded_at": entry["recorded_at"],
            "entry_decision_id": entry["decision_id"],
            "entry_decision_hash": entry["decision_hash"],
            "minimum_hold_until": entry["state_after"][
                "minimum_hold_until_or_null"
            ],
            "vertical_exit_at": entry["state_after"][
                "vertical_exit_at_or_null"
            ],
            "exit_sequence": final["sequence"],
            "exit_scheduled_for": final["scheduled_for"],
            "exit_recorded_at": final["recorded_at"],
            "exit_action": final["action"],
            "exit_decision_id": final["decision_id"],
            "exit_decision_hash": final["decision_hash"],
            "decision_count": len(episode_decisions),
            "decisions": list(episode_decisions),
            "decisions_root_hash": business_hash(
                list(episode_decisions)
            ),
        }
        if (
            episode != expected_episode
            or episode["ordinal"]
            != receipt["prior_completed_episodes"]["count"] + 1
            or episode["entry_scheduled_for"] < utc_datetime(_START)
            or episode["entry_scheduled_for"] >= utc_datetime(_END)
            or final["action"]
            not in ("EXIT_LONG_SMA20", "EXIT_LONG_VERTICAL_24H")
            or not _flat(final["state_after"])
            or _utc(receipt["observed_at"])[0]
            < _utc(final["recorded_at"])[0]
        ):
            reasons.append(
                "CHALLENGER_COHORT_EPISODE_SUMMARY_INVALID"
            )
    except Exception:
        reasons.append(
            "CHALLENGER_COHORT_EPISODE_RECEIPT_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def _completed_ranges(
    cohort: Sequence[Mapping[str, Any]],
) -> Tuple[Tuple[int, int], ...]:
    ranges = []
    start = None
    for index, decision in enumerate(cohort):
        if decision["action"] == "ENTER_LONG":
            if start is not None:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_STATE_INVALID"
                )
            start = index
        elif decision["action"] in (
            "EXIT_LONG_SMA20",
            "EXIT_LONG_VERTICAL_24H",
        ):
            if start is None:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_STATE_INVALID"
                )
            ranges.append((start, index))
            start = None
    return tuple(ranges)


def observe_challenger_cohort_episodes(
    *,
    cohort_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    receipt_output_root: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    plan, plan_file_sha256 = _read_exact_plan(cohort_plan_path)
    try:
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
        )
        state_evidence, decisions = _read_state(paths["state"])
        observed, observed_at = _utc(
            (clock or (lambda: utc_datetime(datetime.now(timezone.utc))))()
        )
        if decisions and observed < _utc(decisions[-1]["recorded_at"])[0]:
            raise ChallengerCohortEpisodeReceiptError(
                "CHALLENGER_COHORT_EPISODE_TIME_INVALID"
            )
        cohort, completed, active, next_required = _partition(
            decisions, observed=observed
        )
        if cohort:
            bundles = _bundle_evidence(
                bundle_directory=paths["bundle_directory"],
                decisions=cohort,
            )
            logs = _logs(
                stdout_path=paths["stdout"],
                stderr_path=paths["stderr"],
                decisions=cohort,
                bundles=bundles,
            )
        else:
            bundles = ()
            logs = None
        launchctl_print, launchd_runs = _launchctl_evidence(
            runner=_launchctl_runner or _command_runner,
            contract=contract,
            install_receipt=install_receipt,
            paths=paths,
        )
    except ChallengerCohortEpisodeReceiptError:
        raise
    except Exception as error:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_SOURCE_INVALID"
        ) from error

    published = []
    prior_ids = []
    for ordinal, (start, end) in enumerate(completed, 1):
        prefix = cohort[: end + 1]
        episode_decisions = cohort[start : end + 1]
        prefix_logs = _logs_through(
            logs,
            stdout_path=paths["stdout"],
            matched_count=end + 1,
        )
        receipt = _build_receipt(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            contract=contract,
            install_receipt=install_receipt,
            state_evidence=state_evidence,
            all_decisions=decisions,
            cohort_prefix=prefix,
            episode_decisions=episode_decisions,
            prefix_bundles=bundles[: end + 1],
            prefix_logs=prefix_logs,
            launchctl_print=launchctl_print,
            launchd_runs=launchd_runs,
            observed_at=observed_at,
            ordinal=ordinal,
            prior_ids=prior_ids,
        )
        path = _receipt_path(
            receipt_output_root,
            entry_scheduled_for=receipt["episode"][
                "entry_scheduled_for"
            ],
            episode_id=receipt["episode"]["episode_id"],
        )
        if path.exists():
            loaded = load_challenger_cohort_episode_receipt(
                receipt_path=path,
                cohort_plan_path=cohort_plan_path,
                install_receipt_path=install_receipt_path,
                contract_path=contract_path,
                plist_path=plist_path,
            )
            receipt = dict(loaded)
            created = False
        else:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(path.parent, 0o700)
            try:
                _publish_exact(
                    path, canonical_json(receipt).encode("utf-8")
                )
            except ValueError as error:
                raise ChallengerCohortEpisodeReceiptError(
                    "CHALLENGER_COHORT_EPISODE_RECEIPT_CONFLICT"
                ) from error
            created = True
        published.append(
            {
                "ordinal": ordinal,
                "episode_id": receipt["episode"]["episode_id"],
                "receipt_id": receipt["receipt_id"],
                "receipt_hash": receipt["receipt_hash"],
                "receipt_path": str(path),
                "created": created,
            }
        )
        prior_ids.append(receipt["episode"]["episode_id"])

    if observed < _START:
        status = "COHORT_NOT_STARTED_VERIFIED"
    elif active is not None:
        status = "COHORT_EPISODE_IN_PROGRESS_VERIFIED"
    elif not cohort or _utc(cohort[-1]["scheduled_for"])[0] < _END:
        status = "COHORT_CONTINUITY_COLLECTING_VERIFIED"
    else:
        status = "COHORT_SLOT_WINDOW_COMPLETED_VERIFIED"
    return {
        "status": status,
        "observed_at": observed_at,
        "cohort_slot_count": len(cohort),
        "completed_episode_count": len(completed),
        "active_episode_id_or_null": (
            cohort[active[0]]["state_after"]["episode_id_or_null"]
            if active is not None
            else None
        ),
        "next_required_scheduled_for_or_null": (
            utc_datetime(next_required)
            if next_required is not None
            else None
        ),
        "receipts": published,
        "receipt_created_count": sum(
            1 for item in published if item["created"]
        ),
        "launchctl_command_count": 1,
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
    }


def load_challenger_cohort_episode_receipt(
    *,
    receipt_path: Path,
    cohort_plan_path: Path,
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
            or status.st_size <= 0
            or status.st_size > _MAX_RECEIPT_BYTES
        ):
            raise ValueError
        receipt = _strict_json_bytes(path.read_bytes())
        plan, plan_file_sha256 = _read_exact_plan(cohort_plan_path)
        contract, install_receipt, paths = _trusted_sources(
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
        )
    except Exception as error:
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_RECEIPT_READ_FAILED"
        ) from error
    if _receipt_reasons(
        receipt,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        contract=contract,
        install_receipt=install_receipt,
        paths=paths,
    ):
        raise ChallengerCohortEpisodeReceiptError(
            "CHALLENGER_COHORT_EPISODE_RECEIPT_INVALID"
        )
    return receipt
