"""Deterministic preregistration for the Challenger multi-Episode cohort."""

import json
import os
import stat
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_episode_economic_evaluator import (
    challenger_episode_economic_result_hash,
)
from .challenger_episode_economic_plan import (
    challenger_episode_economic_policy,
)
from .evidence import artifact_self_hash
from .research_corpus import _publish_exact, _strict_json_bytes


_SCHEMA = "challenger-episode-cohort-plan-v1.schema.json"
_ZERO_HASH = "0" * 64
_REGISTERED_AT = "2026-07-30T09:10:00.000Z"
_COHORT_START = "2026-07-30T12:00:00.000Z"
_COHORT_END = "2026-10-28T12:00:00.000Z"
_OBSERVATION_TAIL_END = "2026-10-29T12:00:00.000Z"
_PILOT_RESULT_ID = (
    "challenger_episode_economic_result_"
    "8f2b70abf6221dc2531ecd9e6b4ada9732e8775d9673b67d4865fe7fa9b18723"
)
_PILOT_RESULT_HASH = (
    "2ac4e92fa32c3841548c433590cda3fea799702fdcda291d25866db2bd993fc4"
)
_PILOT_FILE_SHA256 = (
    "8627677275c31de573f1a59f638ba1678772115dc6d932027a36e2f8b62d9fee"
)
_POLICY_HASH = (
    "2ef83c7c73fff8b163d9bad8527921bd0d87e60595680236e936254536c800e4"
)
_REGISTRATION_HASH = (
    "885b33d3a91eae1d5822fe12c16773a446c23e702f9a4110ef32f474157fa27f"
)
_ECONOMIC_PLAN_ID = (
    "challenger_episode_economic_plan_"
    "e5c86696889d209373ce536ee0f54be72e59d7de96b6868cd5ab0358491985a4"
)
_ECONOMIC_PLAN_HASH = (
    "fa43e1bb24ac0e9d70c82a3d09f03ca43a5f99c429f43e6c67d6e68029732831"
)
_ECONOMIC_PLAN_FILE_SHA256 = (
    "f22cb582a7df38e14220fca75359f6290af2fdb5896e5829ba5d7fd805cf54da"
)
_MAX_PLAN_BYTES = 256 * 1024


class ChallengerEpisodeCohortPlanError(ValueError):
    """The cohort preregistration failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def challenger_episode_cohort_plan_hash(
    plan: Mapping[str, Any],
) -> str:
    return artifact_self_hash(plan, "plan_hash")


def _pilot_valid(result: object, file_sha256: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    try:
        return (
            file_sha256 == _PILOT_FILE_SHA256
            and result["result_id"] == _PILOT_RESULT_ID
            and result["result_hash"] == _PILOT_RESULT_HASH
            and result["result_hash"]
            == challenger_episode_economic_result_hash(result)
            and result["status"]
            == "COMPLETED_ARCHIVE_FORWARD_ECONOMIC_PROXY"
            and result["episode"]["entry_execution_minute"]
            == "2026-07-29T00:03:00.000Z"
            and result["episode"]["exit_execution_minute"]
            == "2026-07-29T16:03:00.000Z"
            and result["economics"]["net_pnl_usdt"]
            == "-23.4627746535"
            and result["economics"]["net_return"]
            == "-0.0234627746535"
            and result["economics"]["positive_label"] == 0
            and result["eligibility"]["profitability"]
            == "INELIGIBLE_SINGLE_EPISODE"
            and result["evaluated_at"] < _REGISTERED_AT
        )
    except (KeyError, TypeError, ValueError):
        return False


def challenger_episode_cohort_contract() -> Dict[str, Any]:
    """Return the non-overridable forward cohort contract."""

    policy = challenger_episode_economic_policy()
    return {
        "trial_binding": {
            "trial_family": "baseline-rule-challenger-2026q3",
            "challenger_policy_id": "SPOT_LONG_SMA20_COST_MARGIN_MOMENTUM_V2",
            "policy_hash": _POLICY_HASH,
            "hypothesis_registration_hash": _REGISTRATION_HASH,
            "release_route": "BASELINE_ONLY",
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "primary_endpoint": "GROWTH",
        },
        "cohort": {
            "start_inclusive": _COHORT_START,
            "end_exclusive": _COHORT_END,
            "duration_days": 90,
            "slot_cadence_seconds": 14400,
            "maximum_episode_hours": 24,
            "observation_tail_end": _OBSERVATION_TAIL_END,
            "entry_population": (
                "ALL_ENTER_LONG_WITH_ENTRY_SLOT_IN_HALF_OPEN_WINDOW"
            ),
            "exit_followup": "FOLLOW_TO_NATURAL_EXIT_EVEN_AFTER_END",
            "rejected_entry_treatment": (
                "RETAIN_FOR_CONTINUITY_NOT_ECONOMIC_EPISODE"
            ),
            "episode_omission_allowed": False,
            "historical_backfill_allowed": False,
        },
        "measurement_binding": {
            "economic_plan_id": _ECONOMIC_PLAN_ID,
            "economic_plan_hash": _ECONOMIC_PLAN_HASH,
            "economic_plan_file_sha256": _ECONOMIC_PLAN_FILE_SHA256,
            "economic_policy_hash": policy["policy_hash"],
            "execution_minute_rule": policy["execution_minute_rule"],
            "entry_source_field": policy["entry_source_field"],
            "exit_source_field": policy["exit_source_field"],
            "slippage_rate_per_side": policy["slippage_rate_per_side"],
            "assumed_taker_fee_rate_per_side": policy[
                "assumed_taker_fee_rate_per_side"
            ],
            "reference_capital_usdt": policy["reference_capital_usdt"],
            "price_tick_usdt": policy["price_tick_usdt"],
            "quantity_step_eth": policy["quantity_step_eth"],
            "decimal_arithmetic_only": True,
        },
        "stopping_policy": {
            "positive_or_negative_pnl_early_stop_allowed": False,
            "window_extension_allowed": False,
            "window_reset_allowed": False,
            "interim_profitability_pass_allowed": False,
            "interim_status": "DESCRIPTIVE_NO_EARLY_SUCCESS",
            "insufficient_evidence_status": "INCONCLUSIVE",
            "continuity_failure_status": "FAILED_CLOSED_NO_BACKFILL",
        },
        "reporting_policy": {
            "pilot_and_confirmatory_separate_required": True,
            "all_stream_required": True,
            "positive_only_reporting_allowed": False,
        },
        "ai_policy": {
            "ai_training_in_scope": False,
            "ai_trading_authority": False,
            "baseline_must_pass_before_ai_incremental_claim": True,
            "future_ai_requires_separate_preoutcome_paired_plan": True,
        },
    }


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "known_pilot_result_hash": plan["known_pilot"]["result_hash"],
        "policy_hash": plan["trial_binding"]["policy_hash"],
        "start_inclusive": plan["cohort"]["start_inclusive"],
        "end_exclusive": plan["cohort"]["end_exclusive"],
        "economic_policy_hash": plan["measurement_binding"][
            "economic_policy_hash"
        ],
        "registered_at": plan["registered_at"],
    }


def build_challenger_episode_cohort_plan(
    *,
    pilot_result: Mapping[str, Any],
    pilot_result_file_sha256: str,
) -> Dict[str, Any]:
    """Build the fixed cohort without reading runtime or future outcomes."""

    if not _pilot_valid(pilot_result, pilot_result_file_sha256):
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PILOT_INVALID"
        )
    contract = challenger_episode_cohort_contract()
    plan = {
        "$schema": "./challenger-episode-cohort-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_episode_cohort_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "registered_at": _REGISTERED_AT,
        "design_commit": "9083bf5",
        "package_baseline": "0.42.0",
        "known_pilot": {
            "role": "EXPOSED_PILOT_MANDATORY_ALL_STREAM",
            "result_id": pilot_result["result_id"],
            "result_hash": pilot_result["result_hash"],
            "result_file_sha256": pilot_result_file_sha256,
            "entry_scheduled_for": "2026-07-29T00:00:00.000Z",
            "exit_scheduled_for": "2026-07-29T16:00:00.000Z",
            "net_pnl_usdt": pilot_result["economics"]["net_pnl_usdt"],
            "net_return": pilot_result["economics"]["net_return"],
            "positive_label": pilot_result["economics"]["positive_label"],
            "confirmatory_eligible": False,
            "all_stream_inclusion_required": True,
        },
        **contract,
        "status": "PREREGISTERED_BEFORE_SECOND_EPISODE",
        "authority": {
            "market_request_count": 0,
            "runner_invocation_count": 0,
            "broker_request_count": 0,
            "order_submission_count": 0,
            "state_write_count": 0,
            "date_override_allowed": False,
            "episode_override_allowed": False,
            "economic_override_allowed": False,
        },
        "eligibility": {
            "confirmatory_cohort": "FORWARD_COHORT_PREREGISTERED",
            "execution": "INELIGIBLE_PROXY_NOT_REAL_FILL",
            "paper": "INELIGIBLE_COLLECTION_NOT_COMPLETE",
            "profitability": "INELIGIBLE_COLLECTION_NOT_COMPLETE",
            "ai_comparison": "INELIGIBLE_NO_PAIRED_AI_COHORT",
        },
        "warnings": [
            "KNOWN_NEGATIVE_PILOT_MUST_REMAIN_VISIBLE",
            "NO_OPTIONAL_STOPPING_OR_WINDOW_RESET",
            "INTERIM_RESULTS_CANNOT_ESTABLISH_PROFITABILITY",
            "PROXY_FILLS_ARE_NOT_REAL_EXECUTION",
            "NO_AI_ADVANTAGE_CLAIM",
            "NO_PROFITABILITY_CLAIM",
        ],
    }
    plan["plan_id"] = stable_id(
        "challenger_episode_cohort_plan", _identity(plan)
    )
    plan["plan_hash"] = challenger_episode_cohort_plan_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PLAN_INVALID"
        )
    return plan


def challenger_episode_cohort_plan_reasons(
    plan: Mapping[str, Any],
    *,
    pilot_result: Mapping[str, Any],
    pilot_result_file_sha256: str,
) -> Tuple[str, ...]:
    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("CHALLENGER_EPISODE_COHORT_SCHEMA_INVALID")
        if plan.get("plan_hash") != challenger_episode_cohort_plan_hash(plan):
            reasons.append("CHALLENGER_EPISODE_COHORT_HASH_MISMATCH")
        rebuilt = build_challenger_episode_cohort_plan(
            pilot_result=pilot_result,
            pilot_result_file_sha256=pilot_result_file_sha256,
        )
        if business_hash(rebuilt) != business_hash(plan):
            reasons.append("CHALLENGER_EPISODE_COHORT_SEMANTIC_MISMATCH")
    except (
        ChallengerEpisodeCohortPlanError,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_EPISODE_COHORT_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def publish_challenger_episode_cohort_plan(
    *,
    plan: Mapping[str, Any],
    pilot_result: Mapping[str, Any],
    pilot_result_file_sha256: str,
    output_path: Path,
) -> None:
    if challenger_episode_cohort_plan_reasons(
        plan,
        pilot_result=pilot_result,
        pilot_result_file_sha256=pilot_result_file_sha256,
    ):
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PLAN_INVALID"
        )
    path = Path(output_path).expanduser()
    if not path.is_absolute() or path.is_symlink():
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_OUTPUT_INVALID"
        )
    path = path.resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    try:
        _publish_exact(path, canonical_json(plan).encode("utf-8"))
    except ValueError as error:
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PLAN_CONFLICT"
        ) from error


def load_challenger_episode_cohort_plan(
    *,
    plan_path: Path,
    pilot_result: Mapping[str, Any],
    pilot_result_file_sha256: str,
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
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PLAN_READ_FAILED"
        ) from error
    if challenger_episode_cohort_plan_reasons(
        plan,
        pilot_result=pilot_result,
        pilot_result_file_sha256=pilot_result_file_sha256,
    ):
        raise ChallengerEpisodeCohortPlanError(
            "CHALLENGER_EPISODE_COHORT_PLAN_INVALID"
        )
    return plan
