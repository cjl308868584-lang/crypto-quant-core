"""Preregistered cumulative evaluation plan for the Challenger cohort."""

import json
import os
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_episode_cohort_plan import (
    challenger_episode_cohort_plan_hash,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-cohort-evaluation-plan-v1.schema.json"
_ZERO_HASH = "0" * 64
_REGISTERED_AT = "2026-07-30T10:22:40.000Z"
_SOURCE_ID = (
    "challenger_episode_cohort_plan_"
    "56fa3d25d37d5445e7c29ad7cda6cd4dac622e036ee0a017c5790fb33142ab1c"
)
_SOURCE_HASH = (
    "20575f808b0e1bb4d1f26e01cd92acae59a77c1a28f28058a9d456cdabdf5201"
)
_SOURCE_FILE_SHA256 = (
    "a431fe2d316d8c9a647a4c45de280644e60554719603b5506670cef8a02ee7ff"
)
_MAX_PLAN_BYTES = 512 * 1024


class ChallengerCohortEvaluationPlanError(ValueError):
    """The cumulative evaluation preregistration failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_cohort_evaluation_plan_hash(
    plan: Mapping[str, Any],
) -> str:
    return artifact_self_hash(plan, "plan_hash")


def _source_valid(plan: object, file_sha256: object) -> bool:
    if not isinstance(plan, Mapping):
        return False
    try:
        return (
            file_sha256 == _SOURCE_FILE_SHA256
            and plan["plan_id"] == _SOURCE_ID
            and plan["plan_hash"] == _SOURCE_HASH
            and plan["plan_hash"]
            == challenger_episode_cohort_plan_hash(plan)
            and plan["registered_at"] < _REGISTERED_AT
            and plan["status"] == "PREREGISTERED_BEFORE_SECOND_EPISODE"
            and plan["cohort"]["start_inclusive"]
            == "2026-07-30T12:00:00.000Z"
            and plan["cohort"]["end_exclusive"]
            == "2026-10-28T12:00:00.000Z"
            and plan["cohort"]["observation_tail_end"]
            == "2026-10-29T12:00:00.000Z"
            and plan["known_pilot"]["role"]
            == "EXPOSED_PILOT_MANDATORY_ALL_STREAM"
            and not plan["known_pilot"]["confirmatory_eligible"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def _time_blocks() -> list:
    boundaries = (
        ("2026-07-30T12:00:00.000Z", "2026-08-14T12:00:00.000Z"),
        ("2026-08-14T12:00:00.000Z", "2026-08-29T12:00:00.000Z"),
        ("2026-08-29T12:00:00.000Z", "2026-09-13T12:00:00.000Z"),
        ("2026-09-13T12:00:00.000Z", "2026-09-28T12:00:00.000Z"),
        ("2026-09-28T12:00:00.000Z", "2026-10-13T12:00:00.000Z"),
        ("2026-10-13T12:00:00.000Z", "2026-10-28T12:00:00.000Z"),
    )
    return [
        {
            "block_id": f"cohort_block_{index:02d}",
            "start_inclusive": start,
            "end_exclusive": end,
            "calendar_days": 15,
            "required_slot_count": 90,
            "minimum_completed_episode_count": 1,
        }
        for index, (start, end) in enumerate(boundaries, start=1)
    ]


def challenger_cohort_evaluation_contract() -> Dict[str, Any]:
    """Return the fixed population, statistics, and decision contract."""

    return {
        "population_contract": {
            "required_slot_count": 540,
            "slot_cadence_seconds": 14400,
            "entry_population": (
                "ALL_ENTER_LONG_WITH_ENTRY_SLOT_IN_HALF_OPEN_WINDOW"
            ),
            "observation_order": "ENTRY_SLOT_ASCENDING",
            "observation_value": "EPISODE_NET_RETURN",
            "pilot_treatment": (
                "EXCLUDED_FROM_CONFIRMATORY_INCLUDED_IN_ALL_STREAM"
            ),
            "rejected_entry_treatment": (
                "RETAIN_FOR_CONTINUITY_NOT_ECONOMIC_EPISODE"
            ),
            "episode_omission_allowed": False,
            "historical_backfill_allowed": False,
            "continuity_failure_status": "FAILED_CLOSED_NO_BACKFILL",
        },
        "time_blocks": _time_blocks(),
        "primary_hypothesis": {
            "endpoint": "MEAN_EPISODE_NET_RETURN",
            "null": "MEAN_EPISODE_NET_RETURN_LTE_ZERO",
            "alternative": "MEAN_EPISODE_NET_RETURN_GT_ZERO",
            "family_size": 1,
            "multiple_testing_method": "HOLM_V1",
            "family_wise_alpha": "0.05",
            "primary_comparator": "GT",
            "primary_threshold": "0",
        },
        "statistical_design": {
            "confidence_level": "0.95",
            "block_length": 3,
            "minimum_block_count": 10,
            "resample_count": 10000,
            "seed": 2026073044,
            "sampling_rule": (
                "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
            ),
            "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
            "one_sided_interval": (
                "ONE_SIDED_95_PERCENTILE_MBB_LCB_V1"
            ),
            "two_sided_interval": "TWO_SIDED_95_PERCENTILE_MBB_V1",
            "effective_sample_method": (
                "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1"
            ),
            "power_method": "SHIFTED_CENTERED_MBB_AT_MERE_V1",
            "minimum_economic_effect": "0.005",
            "minimum_achieved_power": "0.80",
            "maximum_two_sided_ci_full_width": "0.02",
        },
        "sample_gates": [
            {
                "gate_id": "NOMINAL_COMPLETED_EPISODES",
                "metric": "completed_episode_count",
                "comparator": "GTE",
                "threshold": 30,
            },
            {
                "gate_id": "EFFECTIVE_EVENT_COUNT",
                "metric": "effective_event_count",
                "comparator": "GTE",
                "threshold": 20,
            },
            {
                "gate_id": "MINIMUM_MBB_BLOCK_COUNT",
                "metric": "floor_episode_count_div_block_length",
                "comparator": "GTE",
                "threshold": 10,
            },
            {
                "gate_id": "ALL_FIXED_TIME_BLOCKS_NONEMPTY",
                "metric": "nonempty_fixed_time_block_count",
                "comparator": "EQ",
                "threshold": 6,
            },
            {
                "gate_id": "ACHIEVED_POWER_AT_MERE",
                "metric": "achieved_power_at_mere",
                "comparator": "GTE",
                "threshold": "0.80",
            },
            {
                "gate_id": "PRIMARY_CI_FULL_WIDTH",
                "metric": "primary_two_sided_ci_full_width",
                "comparator": "LTE",
                "threshold": "0.02",
            },
        ],
        "economic_gates": [
            {
                "gate_id": "PRIMARY_MEAN_RETURN_LCB",
                "metric": "mean_episode_net_return_lcb95",
                "comparator": "GT",
                "threshold": "0",
            },
            {
                "gate_id": "NONNEGATIVE_FIXED_TIME_BLOCKS",
                "metric": "nonnegative_fixed_time_block_count",
                "comparator": "GTE",
                "threshold": 5,
                "denominator": 6,
            },
            {
                "gate_id": "FIXED_NOTIONAL_MAX_DRAWDOWN",
                "metric": "fixed_notional_max_drawdown",
                "comparator": "LT",
                "threshold": "0.10",
            },
            {
                "gate_id": "STRESS_1_5X_TOTAL_NET_PNL",
                "metric": "stress_1_5x_total_net_pnl_usdt",
                "comparator": "GTE",
                "threshold": "0",
            },
            {
                "gate_id": "LEAVE_TOP_5_POSITIVE_EPISODES_LCB",
                "metric": "leave_top_5_mean_episode_net_return_lcb95",
                "comparator": "GT",
                "threshold": "0",
            },
        ],
        "path_policy": {
            "starting_equity_usdt": "1000",
            "update_formula": (
                "EQUITY_K_EQUALS_EQUITY_PREVIOUS_PLUS_EPISODE_NET_PNL_USDT"
            ),
            "nonpositive_equity_result": (
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
            ),
            "drawdown_method": "HIGH_WATERMARK_MAX_DRAWDOWN_V1",
            "fixed_notional_research_proxy": True,
            "real_account_equity_claimed": False,
        },
        "stress_policy": {
            "policy_id": "CHALLENGER_EPISODE_STRESS_1_5X_FRICTION_V1",
            "entry_slippage_rate": "0.0015",
            "exit_slippage_rate": "0.0015",
            "taker_fee_rate_per_side": "0.00225",
            "entry_rounding": "ROUND_UP_TO_0.01",
            "exit_rounding": "ROUND_DOWN_TO_0.01",
            "quantity_formula": (
                "ROUND_DOWN_1000_DIV_STRESSED_ENTRY_FILL_TO_0.0001"
            ),
            "same_source_rows_required": True,
            "decimal_arithmetic_only": True,
        },
        "leave_out_policy": {
            "policy_id": "LEAVE_TOP_5_POSITIVE_EPISODES_V1",
            "eligible_for_removal": "NET_PNL_USDT_GT_ZERO",
            "maximum_removed_count": 5,
            "ranking": "NET_PNL_DESC_EPISODE_ID_ASC",
            "fewer_than_five": "REMOVE_ALL_POSITIVE_EPISODES",
            "rerun_all_sample_gates": True,
            "rerun_same_mbb_design": True,
        },
        "final_state_machine": {
            "before_tail_end": (
                "COLLECTING_DESCRIPTIVE_NO_EARLY_SUCCESS"
            ),
            "all_sample_and_economic_gates_pass": (
                "RESEARCH_CONTINUATION_GATE_PASS"
            ),
            "sample_gates_pass_economic_gate_fails": (
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
            ),
            "trusted_but_sample_gate_insufficient": (
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
            ),
            "continuity_or_trust_failure": (
                "FAILED_CLOSED_NO_BACKFILL"
            ),
        },
        "interim_policy": {
            "early_success_allowed": False,
            "pnl_based_early_stop_allowed": False,
            "window_extension_allowed": False,
            "window_reset_allowed": False,
            "interim_pnl_ranking_allowed": False,
            "technical_failure_recording_allowed": True,
        },
    }


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "source_plan_hash": plan["source_cohort_plan"]["plan_hash"],
        "endpoint": plan["primary_hypothesis"]["endpoint"],
        "statistical_design_hash": business_hash(
            plan["statistical_design"]
        ),
        "sample_gates_hash": business_hash(plan["sample_gates"]),
        "economic_gates_hash": business_hash(plan["economic_gates"]),
        "registered_at": plan["registered_at"],
    }


def build_challenger_cohort_evaluation_plan(
    *,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
) -> Dict[str, Any]:
    """Build the plan without reading outcomes, runtime, or the network."""

    if not _source_valid(cohort_plan, cohort_plan_file_sha256):
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_SOURCE_INVALID"
        )
    contract = challenger_cohort_evaluation_contract()
    plan = {
        "$schema": "./challenger-cohort-evaluation-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_cohort_evaluation_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "registered_at": _REGISTERED_AT,
        "design_commit": "cd3ad50",
        "package_baseline": "0.43.0",
        "source_cohort_plan": {
            "plan_id": cohort_plan["plan_id"],
            "plan_hash": cohort_plan["plan_hash"],
            "file_sha256": cohort_plan_file_sha256,
            "registered_at": cohort_plan["registered_at"],
            "start_inclusive": cohort_plan["cohort"][
                "start_inclusive"
            ],
            "end_exclusive": cohort_plan["cohort"]["end_exclusive"],
            "observation_tail_end": cohort_plan["cohort"][
                "observation_tail_end"
            ],
        },
        **contract,
        "status": "PREREGISTERED_BEFORE_CONFIRMATORY_COHORT_START",
        "authority": {
            "runtime_state_read_count": 0,
            "market_request_count": 0,
            "runner_invocation_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "sample_override_allowed": False,
            "threshold_override_allowed": False,
            "economic_override_allowed": False,
        },
        "eligibility": {
            "decision_scope": "RESEARCH_CONTINUATION_ONLY",
            "profitability": (
                "INELIGIBLE_RESEARCH_PROXY_NOT_SYSTEM_PAPER"
            ),
            "release_oos": "INELIGIBLE_NO_SEALED_RELEASE_AUDIT",
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_COHORT",
        },
        "warnings": [
            "NO_CONFIRMATORY_OUTCOME_WAS_OBSERVED",
            "NO_EARLY_SUCCESS_OR_OPTIONAL_STOPPING",
            "PASS_WOULD_ONLY_ALLOW_NEXT_RESEARCH_PHASE",
            "NOT_SYSTEM_PAPER_OR_RELEASE_AUDIT",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    plan["plan_id"] = stable_id(
        "challenger_cohort_evaluation_plan", _identity(plan)
    )
    plan["plan_hash"] = challenger_cohort_evaluation_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_PLAN_INVALID"
        )
    return plan


def challenger_cohort_evaluation_plan_reasons(
    plan: Mapping[str, Any],
    *,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("CHALLENGER_COHORT_EVALUATION_SCHEMA_INVALID")
        if plan.get(
            "plan_hash"
        ) != challenger_cohort_evaluation_plan_hash(plan):
            reasons.append("CHALLENGER_COHORT_EVALUATION_HASH_MISMATCH")
        rebuilt = build_challenger_cohort_evaluation_plan(
            cohort_plan=cohort_plan,
            cohort_plan_file_sha256=cohort_plan_file_sha256,
        )
        if business_hash(rebuilt) != business_hash(plan):
            reasons.append(
                "CHALLENGER_COHORT_EVALUATION_SEMANTIC_MISMATCH"
            )
    except (
        ChallengerCohortEvaluationPlanError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_COHORT_EVALUATION_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_challenger_cohort_evaluation_plan(
    *,
    plan: Mapping[str, Any],
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
    output_path: Path,
) -> None:
    if challenger_cohort_evaluation_plan_reasons(
        plan,
        cohort_plan=cohort_plan,
        cohort_plan_file_sha256=cohort_plan_file_sha256,
    ):
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_PLAN_INVALID"
        )
    path = Path(output_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_OUTPUT_INVALID"
        )
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        _publish_exact(path, canonical_json(plan).encode("utf-8"))
    except ValueError as error:
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_PLAN_CONFLICT"
        ) from error


def load_challenger_cohort_evaluation_plan(
    *,
    plan_path: Path,
    cohort_plan: Mapping[str, Any],
    cohort_plan_file_sha256: str,
) -> Mapping[str, Any]:
    try:
        path = Path(plan_path).expanduser().resolve(strict=True)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or stat.S_ISLNK(status.st_mode)
            or status.st_uid != os.getuid()
            or status.st_nlink != 1
            or stat.S_IMODE(status.st_mode) != 0o600
            or status.st_size > _MAX_PLAN_BYTES
        ):
            raise ValueError
        plan = _strict_json_bytes(path.read_bytes())
    except Exception as error:
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_PLAN_READ_FAILED"
        ) from error
    if challenger_cohort_evaluation_plan_reasons(
        plan,
        cohort_plan=cohort_plan,
        cohort_plan_file_sha256=cohort_plan_file_sha256,
    ):
        raise ChallengerCohortEvaluationPlanError(
            "CHALLENGER_COHORT_EVALUATION_PLAN_INVALID"
        )
    return plan
