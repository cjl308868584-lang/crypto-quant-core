"""Fixed-tail cumulative evaluation for the Challenger cohort."""

import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from decimal import (
    Context,
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    localcontext,
)
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from .canonical import (
    business_hash,
    canonical_decimal,
    canonical_json,
    stable_id,
    utc_datetime,
)
from .challenger_cohort_daily_archive import (
    ChallengerCohortDailyArchiveError,
    _required_minutes,
    _secure_directory,
)
from .challenger_cohort_economic_results import (
    ChallengerCohortEconomicResultError,
    _plan_binding,
    build_challenger_cohort_episode_economic_result,
    discover_episode_records,
    index_path,
    load_archive_records,
    load_existing_indexes,
    load_result,
    read_exact_economic_plan,
    result_path,
    validate_result_inventory,
)
from .challenger_cohort_episode_receipt import (
    ChallengerCohortEpisodeReceiptError,
    _partition,
    _read_exact_plan,
    _slot_summary,
)
from .challenger_cohort_evaluation_plan import (
    ChallengerCohortEvaluationPlanError,
    challenger_cohort_evaluation_contract,
    challenger_cohort_evaluation_plan_hash,
    challenger_cohort_evaluation_plan_reasons,
)
from .challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptError,
    _bundle_evidence,
    _logs,
    _trusted_sources,
)
from .challenger_first_slot_receipt import (
    ChallengerFirstSlotReceiptError,
    _launchctl_evidence,
    _read_state,
)
from .challenger_launchd_install import _command_runner
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes
from .statistics import _draw_start


_SCHEMA = "challenger-cohort-cumulative-evaluation-v1.schema.json"
_ZERO_HASH = "0" * 64
_DESIGN_COMMIT = "543684f"
_EVALUATION_PLAN_ID = (
    "challenger_cohort_evaluation_plan_"
    "54a5456345f57219e2ee8763fd35dd4c753e843d31709f342e283fd4026eb037"
)
_EVALUATION_PLAN_HASH = (
    "a6901e7e721682e6d3e7ded9000b5f183ed35e694b7036c7b596c0555a3ab440"
)
_EVALUATION_PLAN_FILE_SHA256 = (
    "49e3b7642e163bb95c4ce01bc1c8d95a23b0cefce277d2f99f2e69029207a4d8"
)
_PILOT_ID = (
    "challenger_episode_economic_result_"
    "8f2b70abf6221dc2531ecd9e6b4ada9732e8775d9673b67d4865fe7fa9b18723"
)
_PILOT_HASH = (
    "2ac4e92fa32c3841548c433590cda3fea799702fdcda291d25866db2bd993fc4"
)
_PILOT_FILE_SHA256 = (
    "8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee"
)
_TAIL = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
_END = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
_MAX_PLAN_BYTES = 512 * 1024
_MAX_PILOT_BYTES = 2 * 1024 * 1024
_MAX_RESULT_BYTES = 64 * 1024 * 1024
_RESULT_DIRECTORY = "challenger-cohort-economic-results"
_INDEX_DIRECTORY = "challenger-cohort-economic-result-index"
_OUTPUT_DIRECTORY = "challenger-cohort-cumulative-evaluations"
_CONTEXT = Context(prec=50)
_ONE = Decimal("1")


class ChallengerCohortCumulativeEvaluationError(ValueError):
    """A fixed-tail trust, calculation, or publication check failed closed."""

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
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
            ) from error
    else:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
        )
    converted = parsed.astimezone(timezone.utc)
    if converted.microsecond % 1000:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
        )
    rendered = utc_datetime(converted)
    if isinstance(value, str) and rendered != value:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
        )
    return converted, rendered


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_NUMBER_INVALID"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_NUMBER_INVALID"
        ) from error
    if not parsed.is_finite():
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_NUMBER_INVALID"
        )
    return parsed


def _secure_json(
    path: Path,
    *,
    maximum_bytes: int,
    modes: Sequence[int],
) -> Tuple[Mapping[str, Any], bytes]:
    try:
        requested = Path(path).expanduser()
        status = requested.lstat()
        if (
            not requested.is_absolute()
            or stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) not in modes
            or status.st_size <= 0
            or status.st_size > maximum_bytes
            or requested.resolve(strict=True) != requested.absolute()
        ):
            raise ValueError
        body = requested.read_bytes()
        value = _strict_json_bytes(body[:-1] if body.endswith(b"\n") else body)
        if not isinstance(value, Mapping):
            raise ValueError
        return value, body
    except Exception as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_INPUT_INVALID"
        ) from error


def _read_exact_evaluation_plan(
    path: Path,
    *,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
) -> Tuple[Mapping[str, Any], str]:
    plan, body = _secure_json(
        path, maximum_bytes=_MAX_PLAN_BYTES, modes=(0o600, 0o644)
    )
    file_sha256 = hashlib.sha256(body).hexdigest()
    if (
        file_sha256 != _EVALUATION_PLAN_FILE_SHA256
        or plan.get("plan_id") != _EVALUATION_PLAN_ID
        or plan.get("plan_hash") != _EVALUATION_PLAN_HASH
        or plan.get("plan_hash")
        != challenger_cohort_evaluation_plan_hash(plan)
        or challenger_cohort_evaluation_plan_reasons(
            plan,
            cohort_plan=cohort_plan,
            cohort_plan_file_sha256=cohort_plan_file_sha256,
        )
    ):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_EVALUATION_PLAN_INVALID"
        )
    return plan, file_sha256


def _read_exact_pilot(path: Path) -> Tuple[Mapping[str, Any], str]:
    pilot, body = _secure_json(
        path, maximum_bytes=_MAX_PILOT_BYTES, modes=(0o600, 0o644)
    )
    file_sha256 = hashlib.sha256(body).hexdigest()
    try:
        valid = (
            file_sha256 == _PILOT_FILE_SHA256
            and pilot["result_id"] == _PILOT_ID
            and pilot["result_hash"] == _PILOT_HASH
            and pilot["result_hash"] == artifact_self_hash(pilot, "result_hash")
            and pilot["economics"]["positive_label"] == 0
            and _decimal(pilot["economics"]["net_pnl_usdt"]) < 0
            and _decimal(pilot["economics"]["net_return"]) < 0
            and pilot["eligibility"]["profitability"]
            == "INELIGIBLE_SINGLE_EPISODE"
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_PILOT_INVALID"
        )
    return pilot, file_sha256


def observe_challenger_cohort_continuity(
    *,
    cohort_plan_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    clock=None,
    _launchctl_runner=None,
) -> Mapping[str, Any]:
    """Verify current state/bundles/logs without publishing Episode receipts."""

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
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_TIME_INVALID"
            )
        cohort, completed, active, next_required = _partition(
            decisions, observed=observed
        )
        bundles = (
            _bundle_evidence(
                bundle_directory=paths["bundle_directory"],
                decisions=cohort,
            )
            if cohort
            else ()
        )
        logs = (
            _logs(
                stdout_path=paths["stdout"],
                stderr_path=paths["stderr"],
                decisions=cohort,
                bundles=bundles,
            )
            if cohort
            else None
        )
        launchctl_print, launchd_runs = _launchctl_evidence(
            runner=_launchctl_runner or _command_runner,
            contract=contract,
            install_receipt=install_receipt,
            paths=paths,
        )
    except ChallengerCohortCumulativeEvaluationError:
        raise
    except (
        ChallengerCohortEpisodeReceiptError,
        ChallengerFirstEpisodeReceiptError,
        ChallengerFirstSlotReceiptError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_INVALID"
        ) from error

    slots = tuple(_slot_summary(item) for item in cohort)
    window_slots = tuple(
        item
        for item in slots
        if _utc(item["scheduled_for"])[0] < _END
    )
    completed_ids = tuple(
        cohort[start]["state_after"]["episode_id_or_null"]
        for start, _end in completed
    )
    active_id = (
        cohort[active[0]]["state_after"]["episode_id_or_null"]
        if active is not None
        else None
    )
    bundle_root = business_hash(
        [
            {
                "sequence": item["sequence"],
                "scheduled_for": item["scheduled_for"],
                "bundle_id": item["bundle_id"],
                "bundle_hash": item["bundle_hash"],
                "file_sha256": item["file_stat"]["sha256"],
                "decision_hash": item["decision_hash"],
            }
            for item in bundles
        ]
    )
    log_root = business_hash(
        []
        if logs is None
        else [
            {
                "sequence": item["sequence"],
                "line_number": item["line_number"],
                "record_hash": item["record_hash"],
            }
            for item in logs["stdout"]["matched_records"]
        ]
    )
    return {
        "observed_at": observed_at,
        "tail_end": utc_datetime(_TAIL),
        "cohort_plan": {
            "plan_id": plan["plan_id"],
            "plan_hash": plan["plan_hash"],
            "plan_file_sha256": plan_file_sha256,
        },
        "state": {
            "path": state_evidence["path"],
            "file_sha256": state_evidence["file_stat"]["sha256"],
            "total_decision_count": len(decisions),
            "decision_chain_end_hash_or_null": state_evidence[
                "decision_chain_end_hash_or_null"
            ],
        },
        "window_slot_count": len(window_slots),
        "cohort_slot_count": len(slots),
        "slots": list(slots),
        "slots_root_hash": business_hash(list(slots)),
        "completed_episode_count": len(completed_ids),
        "completed_episode_ids": list(completed_ids),
        "completed_episode_ids_root_hash": business_hash(list(completed_ids)),
        "active_episode_id_or_null": active_id,
        "next_required_slot_or_null": (
            utc_datetime(next_required) if next_required is not None else None
        ),
        "source_bundle_count": len(bundles),
        "source_bundles_root_hash": bundle_root,
        "stdout_records_root_hash": log_root,
        "stdout_prefix_sha256_or_null": (
            logs["stdout"]["observed_prefix_stat"]["sha256"]
            if logs is not None
            else None
        ),
        "stderr_prefix_sha256_or_null": (
            logs["stderr"]["observed_prefix_stat"]["sha256"]
            if logs is not None
            else None
        ),
        "launchctl_print_hash": launchctl_print["command_evidence_hash"],
        "launchd_runs_observed": launchd_runs,
        "security_boundary": {
            "launchctl_print_count": 1,
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
        },
    }


def _empty_directory(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        _secure_directory(path.parent, create=False)
        _secure_directory(path, create=False)
        return not tuple(path.iterdir())
    except (ChallengerCohortDailyArchiveError, OSError) as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_INVENTORY_INVALID"
        ) from error


def load_complete_economic_inventory(
    *,
    cohort_plan_path: Path,
    economic_plan_path: Path,
    episode_receipt_output_root: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    archive_output_root: Path,
    result_output_root: Path,
    receipt_loader=None,
) -> Mapping[str, Any]:
    """Replay every v0.47 result and require the complete immutable index."""

    try:
        cohort_plan, cohort_plan_file_sha256 = _read_exact_plan(
            cohort_plan_path
        )
        economic_plan, economic_plan_file_sha256 = read_exact_economic_plan(
            economic_plan_path
        )
        cohort_binding, economic_binding = _plan_binding(
            cohort_plan,
            cohort_plan_file_sha256,
            economic_plan,
            economic_plan_file_sha256,
        )
        episode_records = discover_episode_records(
            receipt_output_root=episode_receipt_output_root,
            cohort_plan_path=cohort_plan_path,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            receipt_loader=receipt_loader,
        )
        result_root = Path(result_output_root).expanduser().resolve()
        result_directory = result_root / _RESULT_DIRECTORY
        index_directory = result_root / _INDEX_DIRECTORY
        if not episode_records:
            if not _empty_directory(result_directory) or not _empty_directory(
                index_directory
            ):
                raise ChallengerCohortCumulativeEvaluationError(
                    "CHALLENGER_COHORT_CUMULATIVE_ZERO_INVENTORY_INVALID"
                )
            return {
                "cohort_binding": cohort_binding,
                "economic_binding": economic_binding,
                "episode_records": (),
                "result_records": (),
                "latest_index": None,
                "latest_index_hash": _ZERO_HASH,
                "latest_index_file_sha256": _ZERO_HASH,
            }
        archive_records = load_archive_records(
            cohort_plan_path=cohort_plan_path,
            episode_receipt_output_root=episode_receipt_output_root,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            archive_output_root=archive_output_root,
            cohort_plan=cohort_plan,
            cohort_plan_file_sha256=cohort_plan_file_sha256,
            receipt_loader=receipt_loader,
        )
        required_periods = set(
            _required_minutes(
                tuple(record["receipt"] for record in episode_records)
            )
        )
        if set(archive_records) != required_periods:
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_ARCHIVE_SET_INVALID"
            )
        result_records = []
        expected_paths = []
        for episode_record in episode_records:
            arguments = {
                "cohort_plan": cohort_plan,
                "cohort_plan_file_sha256": cohort_plan_file_sha256,
                "economic_plan": economic_plan,
                "economic_plan_file_sha256": economic_plan_file_sha256,
                "episode_record": episode_record,
                "archive_records": archive_records,
            }
            rebuilt = build_challenger_cohort_episode_economic_result(
                **arguments
            )
            path = result_path(result_root, rebuilt)
            if not path.exists():
                raise ChallengerCohortCumulativeEvaluationError(
                    "CHALLENGER_COHORT_CUMULATIVE_RESULT_MISSING"
                )
            loaded, file_sha256 = load_result(
                output_path=path, build_arguments=arguments
            )
            if loaded != rebuilt:
                raise ChallengerCohortCumulativeEvaluationError(
                    "CHALLENGER_COHORT_CUMULATIVE_RESULT_REPLAY_MISMATCH"
                )
            expected_paths.append(path)
            result_records.append(
                {
                    "result": loaded,
                    "result_file_sha256": file_sha256,
                    "episode_record": episode_record,
                    "path": path,
                    "build_arguments": arguments,
                }
            )
        validate_result_inventory(
            result_root=result_root, expected_paths=expected_paths
        )
        if (
            not result_directory.exists()
            or tuple(sorted(result_directory.iterdir()))
            != tuple(sorted(expected_paths))
        ):
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_RESULT_INVENTORY_INVALID"
            )
        indexes = load_existing_indexes(
            result_root=result_root,
            cohort_binding=cohort_binding,
            economic_binding=economic_binding,
            result_records=result_records,
        )
        if len(indexes) != len(result_records):
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_INDEX_INCOMPLETE"
            )
        expected_index_paths = tuple(
            index_path(result_root, item) for item in indexes
        )
        if (
            not index_directory.exists()
            or tuple(sorted(index_directory.iterdir()))
            != tuple(sorted(expected_index_paths))
        ):
            raise ChallengerCohortCumulativeEvaluationError(
                "CHALLENGER_COHORT_CUMULATIVE_INDEX_INVENTORY_INVALID"
            )
        latest_path = expected_index_paths[-1]
        latest_file_sha256 = hashlib.sha256(
            latest_path.read_bytes()
        ).hexdigest()
        return {
            "cohort_binding": cohort_binding,
            "economic_binding": economic_binding,
            "episode_records": episode_records,
            "result_records": tuple(result_records),
            "latest_index": indexes[-1],
            "latest_index_hash": indexes[-1]["index_hash"],
            "latest_index_file_sha256": latest_file_sha256,
        }
    except ChallengerCohortCumulativeEvaluationError:
        raise
    except (
        ChallengerCohortDailyArchiveError,
        ChallengerCohortEconomicResultError,
        ChallengerCohortEpisodeReceiptError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_ECONOMIC_INVENTORY_INVALID"
        ) from error


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _mbb_replicates(
    values: Sequence[Decimal],
    *,
    block_length: int,
    resample_count: int,
    seed: int,
) -> Tuple[Decimal, ...]:
    start_count = len(values) - block_length + 1
    blocks_per_sample = (
        len(values) + block_length - 1
    ) // block_length
    replicates = []
    for replicate in range(resample_count):
        sampled = []
        for draw in range(blocks_per_sample):
            start = _draw_start(
                seed=seed,
                replicate=replicate,
                draw=draw,
                start_count=start_count,
            )
            sampled.extend(values[start : start + block_length])
        replicates.append(_mean(sampled[: len(values)]))
    return tuple(replicates)


def _nearest_rank(
    sorted_values: Sequence[Decimal], numerator: int, denominator: int
) -> Decimal:
    rank = max(
        1,
        min(
            len(sorted_values),
            (len(sorted_values) * numerator + denominator - 1)
            // denominator,
        ),
    )
    return sorted_values[rank - 1]


def _ess(values: Sequence[Decimal]) -> Optional[int]:
    if len(values) < 3:
        return None
    count = Decimal(len(values))
    mean = _mean(values)
    centered = tuple(value - mean for value in values)
    gamma_zero = sum(
        (value * value for value in centered), Decimal("0")
    ) / count
    if gamma_zero == 0:
        return None
    autocorrelations = []
    for lag in range(1, len(values)):
        covariance = sum(
            (
                centered[index] * centered[index + lag]
                for index in range(len(values) - lag)
            ),
            Decimal("0"),
        ) / count
        autocorrelations.append(covariance / gamma_zero)
    retained_sum = Decimal("0")
    for index in range(0, len(autocorrelations) - 1, 2):
        pair = autocorrelations[index] + autocorrelations[index + 1]
        if pair <= 0:
            break
        retained_sum += pair
    tau = max(_ONE, _ONE + Decimal("2") * retained_sum)
    effective = (count / tau).to_integral_value(rounding=ROUND_FLOOR)
    return int(min(count, effective))


def _sample_statistics(
    observations: Sequence[Mapping[str, Any]],
    *,
    evaluation_plan: Mapping[str, Any],
) -> Mapping[str, Any]:
    design = evaluation_plan["statistical_design"]
    values = tuple(_decimal(item["net_return"]) for item in observations)
    blocks = evaluation_plan["time_blocks"]
    block_counts = [
        sum(
            1
            for item in observations
            if block["start_inclusive"]
            <= item["entry_scheduled_for"]
            < block["end_exclusive"]
        )
        for block in blocks
    ]
    count = len(values)
    effective = _ess(values)
    mean = _mean(values) if values else None
    lcb = lower = upper = width = power = None
    if (
        values
        and count >= design["block_length"]
        and count // design["block_length"]
        >= design["minimum_block_count"]
        and effective is not None
    ):
        replicates = sorted(
            _mbb_replicates(
                values,
                block_length=design["block_length"],
                resample_count=design["resample_count"],
                seed=design["seed"],
            )
        )
        lcb = _nearest_rank(replicates, 5, 100)
        lower = _nearest_rank(replicates, 5, 200)
        upper = _nearest_rank(replicates, 195, 200)
        width = upper - lower
        errors = tuple(value - mean for value in replicates)
        critical = _nearest_rank(sorted(errors), 95, 100)
        mere = _decimal(design["minimum_economic_effect"])
        power = (
            Decimal(
                sum(1 for error in errors if mere + error > critical)
            )
            / Decimal(design["resample_count"])
        )
    metrics = {
        "completed_episode_count": count,
        "effective_event_count": effective,
        "floor_episode_count_div_block_length": (
            count // design["block_length"]
        ),
        "nonempty_fixed_time_block_count": sum(
            1 for value in block_counts if value > 0
        ),
        "achieved_power_at_mere": (
            canonical_decimal(power) if power is not None else None
        ),
        "primary_two_sided_ci_full_width": (
            canonical_decimal(width) if width is not None else None
        ),
    }
    gates = [
        {
            "gate_id": "NOMINAL_COMPLETED_EPISODES",
            "value": count,
            "comparator": "GTE",
            "threshold": 30,
            "passed": count >= 30,
        },
        {
            "gate_id": "EFFECTIVE_EVENT_COUNT",
            "value": effective,
            "comparator": "GTE",
            "threshold": 20,
            "passed": effective is not None and effective >= 20,
        },
        {
            "gate_id": "MINIMUM_MBB_BLOCK_COUNT",
            "value": count // design["block_length"],
            "comparator": "GTE",
            "threshold": 10,
            "passed": count // design["block_length"] >= 10,
        },
        {
            "gate_id": "ALL_FIXED_TIME_BLOCKS_NONEMPTY",
            "value": metrics["nonempty_fixed_time_block_count"],
            "comparator": "EQ",
            "threshold": 6,
            "passed": metrics["nonempty_fixed_time_block_count"] == 6,
        },
        {
            "gate_id": "ACHIEVED_POWER_AT_MERE",
            "value": metrics["achieved_power_at_mere"],
            "comparator": "GTE",
            "threshold": "0.80",
            "passed": power is not None and power >= Decimal("0.80"),
        },
        {
            "gate_id": "PRIMARY_CI_FULL_WIDTH",
            "value": metrics["primary_two_sided_ci_full_width"],
            "comparator": "LTE",
            "threshold": "0.02",
            "passed": width is not None and width <= Decimal("0.02"),
        },
    ]
    return {
        "observation_count": count,
        "mean_episode_net_return": (
            canonical_decimal(mean) if mean is not None else None
        ),
        "mean_episode_net_return_lcb95": (
            canonical_decimal(lcb) if lcb is not None else None
        ),
        "two_sided_ci_lower": (
            canonical_decimal(lower) if lower is not None else None
        ),
        "two_sided_ci_upper": (
            canonical_decimal(upper) if upper is not None else None
        ),
        "metrics": metrics,
        "time_block_episode_counts": block_counts,
        "sample_gates": gates,
        "all_sample_gates_pass": all(item["passed"] for item in gates),
    }


def _time_block_results(
    observations: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    output = []
    for block in blocks:
        members = tuple(
            item
            for item in observations
            if block["start_inclusive"]
            <= item["entry_scheduled_for"]
            < block["end_exclusive"]
        )
        pnl = sum(
            (_decimal(item["net_pnl_usdt"]) for item in members),
            Decimal("0"),
        )
        output.append(
            {
                "block_id": block["block_id"],
                "start_inclusive": block["start_inclusive"],
                "end_exclusive": block["end_exclusive"],
                "episode_count": len(members),
                "net_pnl_usdt": canonical_decimal(pnl),
                "nonnegative": bool(members) and pnl >= 0,
            }
        )
    return tuple(output)


def _path_result(
    observations: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    equity = Decimal("1000")
    high = equity
    maximum = Decimal("0")
    never_nonpositive = True
    for item in observations:
        equity += _decimal(item["net_pnl_usdt"])
        if equity <= 0:
            never_nonpositive = False
        high = max(high, equity)
        if high > 0:
            maximum = max(maximum, (high - equity) / high)
    return {
        "starting_equity_usdt": "1000",
        "ending_equity_usdt": canonical_decimal(equity),
        "fixed_notional_max_drawdown": canonical_decimal(maximum),
        "equity_never_nonpositive": never_nonpositive,
    }


def _round_up(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _stress_result(
    observations: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    total = Decimal("0")
    for item in observations:
        entry = _round_up(
            _decimal(item["entry_source_high"]) * Decimal("1.0015"),
            Decimal("0.01"),
        )
        exit_price = _round_down(
            _decimal(item["exit_source_low"]) * Decimal("0.9985"),
            Decimal("0.01"),
        )
        quantity = _round_down(
            Decimal("1000") / entry, Decimal("0.0001")
        )
        entry_notional = entry * quantity
        exit_notional = exit_price * quantity
        total += (
            (exit_price - entry) * quantity
            - entry_notional * Decimal("0.00225")
            - exit_notional * Decimal("0.00225")
        )
    return {
        "policy_id": "CHALLENGER_EPISODE_STRESS_1_5X_FRICTION_V1",
        "episode_count": len(observations),
        "total_net_pnl_usdt": canonical_decimal(total),
    }


def _observations(
    result_records: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    output = []
    for record in result_records:
        result = record["result"]
        receipt = record["episode_record"]["receipt"]
        output.append(
            {
                "ordinal": receipt["episode"]["ordinal"],
                "episode_id": receipt["episode"]["episode_id"],
                "entry_scheduled_for": receipt["episode"][
                    "entry_scheduled_for"
                ],
                "episode_receipt_id": receipt["receipt_id"],
                "episode_receipt_hash": receipt["receipt_hash"],
                "episode_receipt_file_sha256": record["episode_record"][
                    "file_sha256"
                ],
                "result_id": result["result_id"],
                "result_hash": result["result_hash"],
                "result_file_sha256": record["result_file_sha256"],
                "evaluated_at": result["evaluated_at"],
                "net_pnl_usdt": result["economics"]["net_pnl_usdt"],
                "net_return": result["economics"]["net_return"],
                "positive_label": result["economics"]["positive_label"],
                "entry_source_high": result["economics"][
                    "entry_source_high"
                ],
                "exit_source_low": result["economics"]["exit_source_low"],
            }
        )
    return tuple(output)


def challenger_cohort_cumulative_evaluation_hash(
    evaluation: Mapping[str, Any],
) -> str:
    return artifact_self_hash(evaluation, "evaluation_hash")


def _identity(evaluation: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "evaluation_plan_hash": evaluation["evaluation_plan"]["plan_hash"],
        "continuity_root_hash": evaluation["continuity"][
            "continuity_root_hash"
        ],
        "latest_index_hash": evaluation["economic_inventory"][
            "latest_index_hash"
        ],
        "pilot_result_hash": evaluation["pilot"]["result_hash"],
        "evaluated_at": evaluation["evaluated_at"],
    }


def challenger_cohort_cumulative_evaluation_reasons(
    evaluation: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Replay the frozen result semantics without consulting mutable runtime."""

    reasons = []
    try:
        if tuple(_validator().iter_errors(evaluation)):
            reasons.append("CHALLENGER_COHORT_CUMULATIVE_SCHEMA_INVALID")
        if evaluation.get(
            "evaluation_hash"
        ) != challenger_cohort_cumulative_evaluation_hash(evaluation):
            reasons.append("CHALLENGER_COHORT_CUMULATIVE_HASH_MISMATCH")
        if evaluation.get("evaluation_id") != stable_id(
            "challenger_cohort_cumulative_evaluation",
            _identity(evaluation),
        ):
            reasons.append("CHALLENGER_COHORT_CUMULATIVE_ID_MISMATCH")
        if evaluation["evaluation_plan"] != {
            "plan_id": _EVALUATION_PLAN_ID,
            "plan_hash": _EVALUATION_PLAN_HASH,
            "plan_file_sha256": _EVALUATION_PLAN_FILE_SHA256,
        }:
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_PLAN_BINDING_INVALID"
            )
        if evaluation["pilot"]["result_id"] != _PILOT_ID or evaluation[
            "pilot"
        ]["result_hash"] != _PILOT_HASH or evaluation["pilot"][
            "result_file_sha256"
        ] != _PILOT_FILE_SHA256:
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_PILOT_BINDING_INVALID"
            )
        continuity = evaluation["continuity"]
        expected_continuity_root = business_hash(
            {
                "slots_root_hash": continuity["slots_root_hash"],
                "completed_episode_ids_root_hash": continuity[
                    "completed_episode_ids_root_hash"
                ],
                "source_bundles_root_hash": continuity[
                    "source_bundles_root_hash"
                ],
                "stdout_records_root_hash": continuity[
                    "stdout_records_root_hash"
                ],
                "decision_chain_end_hash_or_null": continuity[
                    "decision_chain_end_hash_or_null"
                ],
            }
        )
        if (
            continuity["continuity_root_hash"]
            != expected_continuity_root
        ):
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_CONTINUITY_ROOT_INVALID"
            )
        observations = tuple(evaluation["confirmatory_observations"])
        if (
            len(observations)
            != evaluation["economic_inventory"]["result_count"]
            or len(observations)
            != continuity["completed_episode_count"]
            or [item["ordinal"] for item in observations]
            != list(range(1, len(observations) + 1))
            or [item["entry_scheduled_for"] for item in observations]
            != sorted(item["entry_scheduled_for"] for item in observations)
            or len({item["episode_id"] for item in observations})
            != len(observations)
        ):
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_OBSERVATION_SET_INVALID"
            )
        contract = challenger_cohort_evaluation_contract()
        replay_plan = {
            "statistical_design": contract["statistical_design"],
            "time_blocks": contract["time_blocks"],
        }
        original = _sample_statistics(
            observations, evaluation_plan=replay_plan
        )
        removable = sorted(
            (
                item
                for item in observations
                if _decimal(item["net_pnl_usdt"]) > 0
            ),
            key=lambda item: (
                -_decimal(item["net_pnl_usdt"]),
                item["episode_id"],
            ),
        )[:5]
        removed_ids = {item["episode_id"] for item in removable}
        retained = tuple(
            item
            for item in observations
            if item["episode_id"] not in removed_ids
        )
        leave_statistics = _sample_statistics(
            retained, evaluation_plan=replay_plan
        )
        expected_leave = {
            "removed_episode_ids": [
                item["episode_id"] for item in removable
            ],
            "removed_count": len(removable),
            "retained_observation_count": len(retained),
            "statistics": leave_statistics,
        }
        time_blocks = _time_block_results(
            observations, contract["time_blocks"]
        )
        path = _path_result(observations)
        stress = _stress_result(observations)
        nonnegative_blocks = sum(
            1 for item in time_blocks if item["nonnegative"]
        )
        original_lcb = original["mean_episode_net_return_lcb95"]
        leave_lcb = leave_statistics["mean_episode_net_return_lcb95"]
        economic_gates = [
            {
                "gate_id": "PRIMARY_MEAN_RETURN_LCB",
                "value": original_lcb,
                "comparator": "GT",
                "threshold": "0",
                "passed": (
                    original_lcb is not None
                    and _decimal(original_lcb) > 0
                ),
            },
            {
                "gate_id": "NONNEGATIVE_FIXED_TIME_BLOCKS",
                "value": nonnegative_blocks,
                "comparator": "GTE",
                "threshold": 5,
                "passed": nonnegative_blocks >= 5,
            },
            {
                "gate_id": "FIXED_NOTIONAL_MAX_DRAWDOWN",
                "value": path["fixed_notional_max_drawdown"],
                "comparator": "LT",
                "threshold": "0.10",
                "passed": (
                    path["equity_never_nonpositive"]
                    and _decimal(path["fixed_notional_max_drawdown"])
                    < Decimal("0.10")
                ),
            },
            {
                "gate_id": "STRESS_1_5X_TOTAL_NET_PNL",
                "value": stress["total_net_pnl_usdt"],
                "comparator": "GTE",
                "threshold": "0",
                "passed": _decimal(stress["total_net_pnl_usdt"]) >= 0,
            },
            {
                "gate_id": "LEAVE_TOP_5_POSITIVE_EPISODES_LCB",
                "value": leave_lcb,
                "comparator": "GT",
                "threshold": "0",
                "passed": (
                    leave_lcb is not None and _decimal(leave_lcb) > 0
                ),
            },
        ]
        if (
            original != evaluation["confirmatory_statistics"]
            or expected_leave != evaluation["leave_top_5"]
            or list(time_blocks) != evaluation["time_blocks"]
            or path != evaluation["path"]
            or stress != evaluation["stress_1_5x"]
            or economic_gates != evaluation["economic_gates"]
        ):
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_CALCULATION_MISMATCH"
            )
        sample_pass = (
            original["all_sample_gates_pass"]
            and leave_statistics["all_sample_gates_pass"]
        )
        expected_status = (
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
            if not sample_pass
            else (
                "RESEARCH_CONTINUATION_GATE_PASS"
                if all(item["passed"] for item in economic_gates)
                else "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
            )
        )
        if evaluation["status"] != expected_status:
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_STATUS_MISMATCH"
            )
        pilot_pnl = _decimal(evaluation["pilot"]["net_pnl_usdt"])
        pilot_return = _decimal(evaluation["pilot"]["net_return"])
        confirmatory_pnl = sum(
            (_decimal(item["net_pnl_usdt"]) for item in observations),
            Decimal("0"),
        )
        all_returns = (pilot_return,) + tuple(
            _decimal(item["net_return"]) for item in observations
        )
        expected_all_stream = {
            "pilot_count": 1,
            "confirmatory_count": len(observations),
            "all_stream_count": len(observations) + 1,
            "pilot_total_net_pnl_usdt": canonical_decimal(pilot_pnl),
            "confirmatory_total_net_pnl_usdt": canonical_decimal(
                confirmatory_pnl
            ),
            "all_stream_total_net_pnl_usdt": canonical_decimal(
                pilot_pnl + confirmatory_pnl
            ),
            "all_stream_mean_net_return": canonical_decimal(
                _mean(all_returns)
            ),
        }
        if (
            evaluation["all_stream_descriptive"]
            != expected_all_stream
        ):
            reasons.append(
                "CHALLENGER_COHORT_CUMULATIVE_ALL_STREAM_MISMATCH"
            )
    except Exception:
        reasons.append(
            "CHALLENGER_COHORT_CUMULATIVE_SEMANTIC_INVALID"
        )
    return tuple(sorted(set(reasons)))


def build_challenger_cohort_cumulative_evaluation(
    *,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
    evaluation_plan: Mapping[str, Any],
    evaluation_plan_file_sha256: str,
    economic_binding: Mapping[str, Any],
    pilot: Mapping[str, Any],
    pilot_file_sha256: str,
    continuity: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the final fixed-tail artifact from already verified inputs."""

    if (
        evaluation_plan_file_sha256 != _EVALUATION_PLAN_FILE_SHA256
        or pilot_file_sha256 != _PILOT_FILE_SHA256
        or continuity["window_slot_count"] != 540
        or continuity["active_episode_id_or_null"] is not None
    ):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_FINAL_CONTINUITY_INVALID"
        )
    result_records = inventory["result_records"]
    observations = _observations(result_records)
    completed_ids = continuity["completed_episode_ids"]
    if (
        list(item["episode_id"] for item in observations) != completed_ids
        or len(observations) != continuity["completed_episode_count"]
    ):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_EPISODE_SET_INVALID"
        )
    with localcontext(_CONTEXT):
        original = _sample_statistics(
            observations, evaluation_plan=evaluation_plan
        )
        removable = sorted(
            (
                item
                for item in observations
                if _decimal(item["net_pnl_usdt"]) > 0
            ),
            key=lambda item: (
                -_decimal(item["net_pnl_usdt"]),
                item["episode_id"],
            ),
        )[:5]
        removed_ids = {item["episode_id"] for item in removable}
        retained = tuple(
            item
            for item in observations
            if item["episode_id"] not in removed_ids
        )
        leave_out = _sample_statistics(
            retained, evaluation_plan=evaluation_plan
        )
        time_blocks = _time_block_results(
            observations, evaluation_plan["time_blocks"]
        )
        path = _path_result(observations)
        stress = _stress_result(observations)
        nonnegative_blocks = sum(
            1 for item in time_blocks if item["nonnegative"]
        )
        original_lcb = original["mean_episode_net_return_lcb95"]
        leave_lcb = leave_out["mean_episode_net_return_lcb95"]
        stress_total = _decimal(stress["total_net_pnl_usdt"])
        drawdown = _decimal(path["fixed_notional_max_drawdown"])
        economic_gates = [
            {
                "gate_id": "PRIMARY_MEAN_RETURN_LCB",
                "value": original_lcb,
                "comparator": "GT",
                "threshold": "0",
                "passed": (
                    original_lcb is not None
                    and _decimal(original_lcb) > 0
                ),
            },
            {
                "gate_id": "NONNEGATIVE_FIXED_TIME_BLOCKS",
                "value": nonnegative_blocks,
                "comparator": "GTE",
                "threshold": 5,
                "passed": nonnegative_blocks >= 5,
            },
            {
                "gate_id": "FIXED_NOTIONAL_MAX_DRAWDOWN",
                "value": path["fixed_notional_max_drawdown"],
                "comparator": "LT",
                "threshold": "0.10",
                "passed": (
                    path["equity_never_nonpositive"]
                    and drawdown < Decimal("0.10")
                ),
            },
            {
                "gate_id": "STRESS_1_5X_TOTAL_NET_PNL",
                "value": stress["total_net_pnl_usdt"],
                "comparator": "GTE",
                "threshold": "0",
                "passed": stress_total >= 0,
            },
            {
                "gate_id": "LEAVE_TOP_5_POSITIVE_EPISODES_LCB",
                "value": leave_lcb,
                "comparator": "GT",
                "threshold": "0",
                "passed": (
                    leave_lcb is not None and _decimal(leave_lcb) > 0
                ),
            },
        ]
        sample_pass = (
            original["all_sample_gates_pass"]
            and leave_out["all_sample_gates_pass"]
        )
        economic_pass = all(item["passed"] for item in economic_gates)
        if not sample_pass:
            final_status = "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
        elif economic_pass:
            final_status = "RESEARCH_CONTINUATION_GATE_PASS"
        else:
            final_status = "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
        confirmatory_pnl = sum(
            (_decimal(item["net_pnl_usdt"]) for item in observations),
            Decimal("0"),
        )
        pilot_pnl = _decimal(pilot["economics"]["net_pnl_usdt"])
        pilot_return = _decimal(pilot["economics"]["net_return"])
        all_returns = (pilot_return,) + tuple(
            _decimal(item["net_return"]) for item in observations
        )
        evaluated_at = max(
            [utc_datetime(_TAIL)]
            + [item["evaluated_at"] for item in observations]
        )
    continuity_binding = {
        "window_slot_count": continuity["window_slot_count"],
        "cohort_slot_count": continuity["cohort_slot_count"],
        "slots_root_hash": continuity["slots_root_hash"],
        "completed_episode_count": continuity["completed_episode_count"],
        "completed_episode_ids_root_hash": continuity[
            "completed_episode_ids_root_hash"
        ],
        "active_episode_id_or_null": None,
        "source_bundles_root_hash": continuity[
            "source_bundles_root_hash"
        ],
        "stdout_records_root_hash": continuity[
            "stdout_records_root_hash"
        ],
        "state_file_sha256": continuity["state"]["file_sha256"],
        "decision_chain_end_hash_or_null": continuity["state"][
            "decision_chain_end_hash_or_null"
        ],
        "launchctl_print_hash": continuity["launchctl_print_hash"],
        "continuity_root_hash": business_hash(
            {
                "slots_root_hash": continuity["slots_root_hash"],
                "completed_episode_ids_root_hash": continuity[
                    "completed_episode_ids_root_hash"
                ],
                "source_bundles_root_hash": continuity[
                    "source_bundles_root_hash"
                ],
                "stdout_records_root_hash": continuity[
                    "stdout_records_root_hash"
                ],
                "decision_chain_end_hash_or_null": continuity["state"][
                    "decision_chain_end_hash_or_null"
                ],
            }
        ),
    }
    latest_index = inventory["latest_index"]
    evaluation = {
        "$schema": "./challenger-cohort-cumulative-evaluation-v1.schema.json",
        "schema_version": "1.0.0",
        "evaluation_id": (
            "challenger_cohort_cumulative_evaluation_" + _ZERO_HASH
        ),
        "evaluation_hash": _ZERO_HASH,
        "evaluated_at": evaluated_at,
        "design_commit": _DESIGN_COMMIT,
        "package_baseline": "0.47.0",
        "cohort_plan": {
            "plan_id": cohort_plan["plan_id"],
            "plan_hash": cohort_plan["plan_hash"],
            "plan_file_sha256": cohort_plan_file_sha256,
        },
        "evaluation_plan": {
            "plan_id": evaluation_plan["plan_id"],
            "plan_hash": evaluation_plan["plan_hash"],
            "plan_file_sha256": evaluation_plan_file_sha256,
        },
        "economic_plan": dict(economic_binding),
        "pilot": {
            "result_id": pilot["result_id"],
            "result_hash": pilot["result_hash"],
            "result_file_sha256": pilot_file_sha256,
            "net_pnl_usdt": pilot["economics"]["net_pnl_usdt"],
            "net_return": pilot["economics"]["net_return"],
            "confirmatory_eligible": False,
        },
        "continuity": continuity_binding,
        "economic_inventory": {
            "result_count": len(observations),
            "latest_index_id_or_null": (
                latest_index["index_id"] if latest_index is not None else None
            ),
            "latest_index_hash": inventory["latest_index_hash"],
            "latest_index_file_sha256": inventory[
                "latest_index_file_sha256"
            ],
        },
        "confirmatory_observations": list(observations),
        "confirmatory_statistics": original,
        "leave_top_5": {
            "removed_episode_ids": [
                item["episode_id"] for item in removable
            ],
            "removed_count": len(removable),
            "retained_observation_count": len(retained),
            "statistics": leave_out,
        },
        "time_blocks": list(time_blocks),
        "path": path,
        "stress_1_5x": stress,
        "economic_gates": economic_gates,
        "all_stream_descriptive": {
            "pilot_count": 1,
            "confirmatory_count": len(observations),
            "all_stream_count": len(observations) + 1,
            "pilot_total_net_pnl_usdt": canonical_decimal(pilot_pnl),
            "confirmatory_total_net_pnl_usdt": canonical_decimal(
                confirmatory_pnl
            ),
            "all_stream_total_net_pnl_usdt": canonical_decimal(
                pilot_pnl + confirmatory_pnl
            ),
            "all_stream_mean_net_return": canonical_decimal(
                _mean(all_returns)
            ),
        },
        "status": final_status,
        "eligibility": {
            "decision_scope": "RESEARCH_CONTINUATION_ONLY",
            "profitability": (
                "INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER"
            ),
            "release_oos": "INELIGIBLE_NO_SEALED_RELEASE_AUDIT",
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_COHORT",
        },
        "security_boundary": {
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
            "binary_float_allowed": False,
            "sample_override_allowed": False,
            "threshold_override_allowed": False,
            "economic_override_allowed": False,
        },
        "warnings": [
            "FIXED_NOTIONAL_ARCHIVE_EXECUTION_PROXY_ONLY",
            "PASS_ONLY_ALLOWS_NEXT_RESEARCH_PHASE",
            "NOT_SYSTEM_PAPER_OR_REAL_FILL_EVIDENCE",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    evaluation["evaluation_id"] = stable_id(
        "challenger_cohort_cumulative_evaluation", _identity(evaluation)
    )
    evaluation["evaluation_hash"] = (
        challenger_cohort_cumulative_evaluation_hash(evaluation)
    )
    if tuple(_validator().iter_errors(evaluation)):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_SCHEMA_INVALID"
        )
    return evaluation


def _evaluation_path(
    output_root: Path, evaluation: Mapping[str, Any]
) -> Path:
    requested = Path(output_root).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_OUTPUT_INVALID"
        )
    return (
        requested.resolve()
        / _OUTPUT_DIRECTORY
        / f"{evaluation['evaluation_id']}.json"
    )


def publish_challenger_cohort_cumulative_evaluation(
    *,
    evaluation: Mapping[str, Any],
    output_root: Path,
) -> Path:
    if challenger_cohort_cumulative_evaluation_reasons(evaluation):
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_RESULT_INVALID"
        )
    path = _evaluation_path(output_root, evaluation)
    try:
        _secure_directory(path.parent.parent, create=True)
        _secure_directory(path.parent, create=True)
        _publish_exact(path, canonical_json(evaluation).encode("utf-8"))
        loaded, _body = _secure_json(
            path, maximum_bytes=_MAX_RESULT_BYTES, modes=(0o600,)
        )
        if loaded != evaluation:
            raise ValueError
    except Exception as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_RESULT_CONFLICT"
        ) from error
    return path


def load_challenger_cohort_cumulative_evaluation(
    *, evaluation_path: Path
) -> Mapping[str, Any]:
    """Load and replay one immutable final evaluation artifact."""

    try:
        path = Path(evaluation_path).expanduser()
        _secure_directory(path.parent.parent, create=False)
        _secure_directory(path.parent, create=False)
        evaluation, _body = _secure_json(
            path, maximum_bytes=_MAX_RESULT_BYTES, modes=(0o600,)
        )
        if (
            path.parent.name != _OUTPUT_DIRECTORY
            or path.name != f"{evaluation['evaluation_id']}.json"
            or challenger_cohort_cumulative_evaluation_reasons(evaluation)
        ):
            raise ValueError
        return evaluation
    except Exception as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_RESULT_INVALID"
        ) from error


def evaluate_challenger_cohort(
    *,
    cohort_plan_path: Path,
    evaluation_plan_path: Path,
    economic_plan_path: Path,
    pilot_result_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    plist_path: Path,
    episode_receipt_output_root: Path,
    archive_output_root: Path,
    result_output_root: Path,
    evaluation_output_root: Path,
    clock=None,
    _launchctl_runner=None,
    continuity_loader=None,
    economic_loader=None,
    receipt_loader=None,
) -> Mapping[str, Any]:
    """Observe before the tail or publish the one final evaluation after it."""

    try:
        cohort_plan, cohort_plan_file_sha256 = _read_exact_plan(
            cohort_plan_path
        )
        evaluation_plan, evaluation_plan_file_sha256 = (
            _read_exact_evaluation_plan(
                evaluation_plan_path,
                cohort_plan=cohort_plan,
                cohort_plan_file_sha256=cohort_plan_file_sha256,
            )
        )
        pilot, pilot_file_sha256 = _read_exact_pilot(pilot_result_path)
        continuity = (
            continuity_loader or observe_challenger_cohort_continuity
        )(
            cohort_plan_path=cohort_plan_path,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            clock=clock,
            _launchctl_runner=_launchctl_runner,
        )
        observed = _utc(continuity["observed_at"])[0]
        if observed < _TAIL:
            return {
                "status": "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS",
                "observed_at": continuity["observed_at"],
                "tail_end": utc_datetime(_TAIL),
                "verified_cohort_slot_count": continuity[
                    "window_slot_count"
                ],
                "completed_episode_count": continuity[
                    "completed_episode_count"
                ],
                "active_episode_id_or_null": continuity[
                    "active_episode_id_or_null"
                ],
                "next_required_slot_or_null": continuity[
                    "next_required_slot_or_null"
                ],
                "evaluation_published": False,
                "market_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
                "runner_invocation_count": 0,
            }
        inventory = (
            economic_loader or load_complete_economic_inventory
        )(
            cohort_plan_path=cohort_plan_path,
            economic_plan_path=economic_plan_path,
            episode_receipt_output_root=episode_receipt_output_root,
            install_receipt_path=install_receipt_path,
            contract_path=contract_path,
            plist_path=plist_path,
            archive_output_root=archive_output_root,
            result_output_root=result_output_root,
            receipt_loader=receipt_loader,
        )
        evaluation = build_challenger_cohort_cumulative_evaluation(
            cohort_plan=cohort_plan,
            cohort_plan_file_sha256=cohort_plan_file_sha256,
            evaluation_plan=evaluation_plan,
            evaluation_plan_file_sha256=evaluation_plan_file_sha256,
            economic_binding=inventory["economic_binding"],
            pilot=pilot,
            pilot_file_sha256=pilot_file_sha256,
            continuity=continuity,
            inventory=inventory,
        )
        path = publish_challenger_cohort_cumulative_evaluation(
            evaluation=evaluation, output_root=evaluation_output_root
        )
        return {
            "status": evaluation["status"],
            "evaluated_at": evaluation["evaluated_at"],
            "evaluation_id": evaluation["evaluation_id"],
            "evaluation_hash": evaluation["evaluation_hash"],
            "evaluation_path": str(path),
            "evaluation_published": True,
            "confirmatory_episode_count": len(
                evaluation["confirmatory_observations"]
            ),
            "market_request_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "runner_invocation_count": 0,
        }
    except ChallengerCohortCumulativeEvaluationError:
        raise
    except (
        ChallengerCohortEvaluationPlanError,
        ChallengerCohortEpisodeReceiptError,
        ChallengerCohortEconomicResultError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise ChallengerCohortCumulativeEvaluationError(
            "CHALLENGER_COHORT_CUMULATIVE_FAILED_CLOSED_NO_BACKFILL"
        ) from error
