"""Frozen plan-only replacement Challenger economic preregistration.

This module neither reads economic outcomes nor grants runtime, credential,
broker, order, funding, installation, start, or production authority.
"""

import copy
import hashlib
import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _read_owner_controlled_regular_file,
    _strict_json_bytes,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-economic-evaluation-plan-v1.schema.json"
_ARTIFACT_SHA256 = (
    "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
)
_ZERO_HASH = "0" * 64


class ChallengerReplacementEconomicPlanError(ValueError):
    """The economic preregistration failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    try:
        resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
        schema = json.loads(resource.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except (
        OSError,
        SchemaError,
        TypeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID"
        ) from error


def _schema_errors(value: Mapping[str, Any]) -> Tuple[Any, ...]:
    try:
        return tuple(_validator().iter_errors(value))
    except ChallengerReplacementEconomicPlanError:
        raise
    except (
        OSError,
        SchemaError,
        TypeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID"
        ) from error


def _with_policy_hash(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["policy_hash"] = business_hash(value)
    return result


def challenger_replacement_economic_plan_hash(plan: Mapping[str, Any]) -> str:
    """Hash the plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "foundation": plan["foundation"],
        **{
            f"{section}_policy_hash": plan[section]["policy_hash"]
            for section in (
                "population_contract",
                "economic_measurement",
                "missingness_policy",
                "statistical_design",
                "final_state_machine",
                "interim_policy",
            )
        },
        "sample_gates_hash": business_hash(plan["sample_gates"]),
        "economic_gates_hash": business_hash(plan["economic_gates"]),
        "final_state_machine_hash": business_hash(plan["final_state_machine"]),
    }


def build_challenger_replacement_economic_plan() -> Dict[str, Any]:
    """Build the deterministic, parameterless economic preregistration."""

    population_contract = _with_policy_hash(
        {
            "start_source": "FIRST_VERIFIED_NATURAL_OBSERVED_DECISION_OPPORTUNITY",
            "start_identity_fields": [
                "opportunity_id", "event_hash", "scheduled_for", "observed_at",
                "plan_id", "plan_hash", "deployment_identity", "event_root_identity",
            ],
            "cadence_seconds": 14_400,
            "minimum_calendar_days": 90,
            "start_scheduled_for_or_null": None,
            "tail_scheduled_for_or_null": None,
            "tail_scheduled_for_base": "START_SCHEDULED_FOR",
            "tail_scheduled_for_offset_seconds": 7_776_000,
            "window_kind": "HALF_OPEN_SCHEDULED_FOR_START_INCLUSIVE_TAIL_EXCLUSIVE",
            "terminal_outcomes": ["OBSERVED", "MISSED"],
            "historical_backfill_allowed": False,
            "window_reset_allowed": False,
            "alternate_start_allowed": False,
            "tail_pre_action_mark_required": True,
            "tail_pre_action_mark_source": (
                "CANONICAL_SOURCE_AND_PRIOR_PROJECTION_AT_TAIL_SCHEDULED_FOR"
            ),
            "tail_action": "NO_NEW_ENTRY_OR_REVERSAL",
            "untrusted_tail_mark_input_allowed": False,
            "last_convenient_price_fallback_allowed": False,
            "missing_tail_mark_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
        }
    )
    economic_measurement = _with_policy_hash(
        {
            "starting_virtual_equity_usdt": "100",
            "capital_limit_usdt": "100",
            "gross_exposure_limit": "0.5",
            "technical_leverage_cap": "2",
            "configured_simulation_leverage": "1",
            "economic_asset": "ETH",
            "daily_boundary_count": 91,
            "daily_return_count": 90,
            "daily_return_formula": "BOUNDARY_EQUITY_DELTA_DIVIDED_BY_100",
            "decimal_arithmetic_only": True,
            "binary_float_allowed": False,
            "spot_mark": "CONSERVATIVE_BID_MARK",
            "perpetual_mark": "CANONICAL_MARK_PRICE_AND_CONTRACT_MULTIPLIER",
            "fee_treatment": "ACCRUED_ONCE_ONLY",
            "funding_treatment": "SIGNED_CASHFLOW_ONCE_ONLY",
            "slippage_treatment": "ADVERSE_COST_INCLUDED_ONCE_ONLY",
            "marked_equity_calculation": {
                "cash_coefficient": "1",
                "conservative_marked_position_value_coefficient": "1",
                "all_accrued_fees_coefficient": "-1",
                "signed_funding_cashflow_coefficient": "1",
                "accounting_semantics_source": "V071_SIMULATION_CONTRACT_ACCOUNTING",
            },
            "daily_boundary_construction": {
                "kind": "PRE_ACTION_UTC_ALIGNED",
                "offset_formula": "START_SCHEDULED_FOR_PLUS_K_TIMES_86400_SECONDS",
                "k_minimum": 0,
                "k_maximum": 90,
            },
            "daily_return_calculation": {
                "numerator": "BOUNDARY_EQUITY_K_MINUS_BOUNDARY_EQUITY_K_MINUS_1",
                "fixed_capital_denominator_usdt": "100",
                "intermediate_rounding_allowed": False,
                "canonical_output_encoder": "REPOSITORY_DECIMAL_ENCODER",
                "compounded": False,
                "annualized": False,
            },
            "maximum_drawdown_calculation": {
                "peak_source": "CONTINUOUS_HIGH_WATER_MARKED_EQUITY",
                "formula": "(PEAK_MINUS_CURRENT)_DIVIDED_BY_PEAK",
                "nonpositive_equity_result": (
                    "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
                ),
            },
            "stress_replay": {
                "nonnegative_fee_multiplier": "1.5",
                "adverse_slippage_multiplier": "1.5",
                "negative_funding_cashflow_multiplier": "1.5",
                "positive_funding_benefit_multiplier": "0.5",
                "unchanged_components": [
                    "GROSS_MARKET_MOVEMENT",
                    "QUANTITIES",
                    "PRODUCT_SELECTION",
                    "EVENT_ORDER",
                ],
                "unreconstructable_cost_result": (
                    "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
                ),
                "zero_cost_substitution_allowed": False,
            },
            "fixed_15_day_blocks": {
                "count": 6,
                "length_days": 15,
                "interval": "HALF_OPEN",
                "start_formula": "START_SCHEDULED_FOR_PLUS_N_TIMES_15_DAYS",
                "end_formula": (
                    "START_SCHEDULED_FOR_PLUS_(N_PLUS_1)_TIMES_15_DAYS"
                ),
                "n_values": [0, 1, 2, 3, 4, 5],
                "value_formula": "SUM_OF_DAILY_NET_RETURNS",
                "nonnegative_operator": "GTE_ZERO",
            },
        }
    )
    missingness_policy = _with_policy_hash(
        {
            "observed_coverage_minimum": "0.95",
            "terminal_coverage_required": "1",
            "exposed_miss_result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
            "optimistic_flat_miss": "ZERO_ECONOMIC_CHANGE",
            "pessimistic_flat_miss": "ONE_FROZEN_STOPPED_CYCLE_LOSS_PER_DISTINCT_FLAT_MISS",
            "flat_miss_notional_usdt": "50",
            "protective_stop_distance": "0.02",
            "market_slippage_per_side": "0.001",
            "taker_fee_per_side": "0.0015",
            "flat_miss_loss_rate": "0.025",
            "flat_miss_loss_usdt": "1.25",
            "pass_requires_both_bounds": True,
            "disagreement_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            "confirmed_failure_boundaries": [
                "EXPOSED_MISSED",
                "UNRESOLVED_POSITION",
                "ECONOMIC_GAP_LOCK",
                "UNRECORDED_FILL",
                "DUPLICATE_ECONOMIC_ORDER",
                "RECONCILIATION_FAILURE",
            ],
            "confirmed_failure_result": (
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS"
            ),
            "confirmed_failure_imputation_allowed": False,
            "confirmed_failure_repair_allowed": False,
            "flat_miss_included_in_population": True,
            "flat_miss_history_alteration_allowed": False,
            "flat_miss_notional_formula": (
                "STARTING_VIRTUAL_EQUITY_USDT_TIMES_GROSS_EXPOSURE_LIMIT"
            ),
            "flat_miss_loss_rate_formula": (
                "PROTECTIVE_STOP_DISTANCE_PLUS_2_TIMES_MARKET_SLIPPAGE_PER_SIDE_"
                "PLUS_2_TIMES_MAX_FROZEN_TAKER_FEE_PER_SIDE"
            ),
            "taker_fee_rate_selection": (
                "MAX_FROZEN_SPOT_AND_PERPETUAL_TAKER_RATE"
            ),
            "flat_miss_funding_benefit_usdt": "0",
            "charges_per_distinct_flat_missed_opportunity": 1,
            "duplicate_flat_miss_charge_allowed": False,
            "observed_coverage_formula": (
                "OBSERVED_DIVIDED_BY_(OBSERVED_PLUS_MISSED)_IN_EXACT_HALF_OPEN_WINDOW"
            ),
            "favorable_bound_selection_allowed": False,
        }
    )
    statistical_design = _with_policy_hash(
        {
            "primary_null": "MEAN_DAILY_NET_RETURN_LTE_ZERO",
            "primary_alternative": "MEAN_DAILY_NET_RETURN_GT_ZERO",
            "family_size": 1,
            "family_wise_alpha": "0.05",
            "method": "OVERLAPPING_NON_CIRCULAR_MOVING_BLOCK_BOOTSTRAP",
            "block_length_days": 7,
            "sample_length": 90,
            "resample_count": 10_000,
            "seed": 2026082574,
            "draw_start_method": "SHA256_REJECTION_SAMPLED_MBB_V1",
            "quantile": "CONSERVATIVE_NEAREST_RANK_0_05",
            "confidence_level": "0.95",
            "primary_endpoint": "MEAN_DAILY_NET_RETURN_LCB95",
            "minimum_economic_effect_daily": "0.0005",
            "power_method": "CENTERED_BOOTSTRAP_CRITICAL_VALUE_ACHIEVED_POWER",
            "multiple_testing_adjustment": "NONE_SINGLE_PRIMARY_HYPOTHESIS",
            "resample_construction": {
                "block_selection": "UNIFORM_OVERLAPPING_SEVEN_DAY_BLOCKS",
                "within_block_order": "ORIGINAL",
                "concatenation": "CONCATENATE_SELECTED_BLOCKS",
                "truncation_length": 90,
                "lower_bound": (
                    "CONSERVATIVE_NEAREST_RANK_5TH_PERCENTILE_OF_10000_"
                    "RESAMPLED_MEANS"
                ),
                "language_prng_allowed": False,
            },
            "achieved_power_calculation": {
                "minimum_economic_effect_is_alternate_pass_threshold": False,
                "centered_error_formula": (
                    "BOOTSTRAP_MEAN_MINUS_OBSERVED_SAMPLE_MEAN"
                ),
                "critical_value": (
                    "CONSERVATIVE_NEAREST_RANK_95TH_PERCENTILE_OF_CENTERED_ERRORS"
                ),
                "comparison_left": (
                    "MINIMUM_ECONOMIC_EFFECT_DAILY_PLUS_CENTERED_ERROR"
                ),
                "comparison_operator": "STRICT_GT_CRITICAL_VALUE",
                "centered_error_count": 10_000,
                "satisfying_error_aggregation": (
                    "COUNT_ALL_CENTERED_ERRORS_SATISFYING_COMPARISON"
                ),
                "result_formula": (
                    "SATISFYING_ERROR_AGGREGATION_DIVIDED_BY_RESULT_DENOMINATOR"
                ),
                "result_denominator": 10_000,
                "shortfall_result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            },
            "completed_cycle_counting": {
                "begins": "VERIFIED_FLAT_TO_EXPOSED_TRANSITION",
                "ends": "MATCHING_VERIFIED_EXPOSED_TO_FLAT_TRANSITION",
                "partial_fills_belong_to_matching_cycle": True,
                "partial_fills_create_additional_cycles": False,
                "retries_create_additional_cycles": False,
                "duplicate_observations_create_additional_cycles": False,
            },
            "sample_gate_shortfall_result": (
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
            ),
            "window_extension_allowed": False,
            "post_tail_evidence_changes_population": False,
        }
    )
    final_state_machine = _with_policy_hash(
        {
            "terminal_outcomes": [
                "RESEARCH_CONTINUATION_GATE_PASS",
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            ],
            "decision_rules": [
                {
                    "priority": 1,
                    "when_any": [
                        "INVALID_PLAN",
                        "IDENTITY_MISMATCH",
                        "MALFORMED_EVENT",
                        "DUPLICATE_AUTHORITY",
                        "MISSING_TAIL_PRE_ACTION_MARK",
                        "UNREADABLE_EVIDENCE",
                    ],
                    "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 2,
                    "when_any": [
                        "CONFIRMED_SAFETY_OR_RISK_BOUNDARY",
                        "EXPOSED_MISSED",
                        "ECONOMIC_GAP_LOCK",
                        "NONPOSITIVE_EQUITY",
                        "TRUSTED_SUFFICIENT_EVIDENCE_FAILS_ANY_ECONOMIC_GATE",
                    ],
                    "result": "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 3,
                    "when_any": [
                        "TRUSTED_EVIDENCE_FAILS_ANY_SAMPLE_GATE",
                        "OPTIMISTIC_PESSIMISTIC_FLAT_MISS_BOUND_DISAGREEMENT",
                    ],
                    "result": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
                    "research_continuation_discussion_eligible": False,
                },
                {
                    "priority": 4,
                    "when_all": [
                        "TRUSTED_EVIDENCE",
                        "SUFFICIENT_EVIDENCE",
                        "ALL_SAMPLE_GATES_PASS",
                        (
                            "ALL_ECONOMIC_GATES_PASS_UNDER_OPTIMISTIC_"
                            "FLAT_MISS_BOUND"
                        ),
                        (
                            "ALL_ECONOMIC_GATES_PASS_UNDER_PESSIMISTIC_"
                            "FLAT_MISS_BOUND"
                        ),
                    ],
                    "result": "RESEARCH_CONTINUATION_GATE_PASS",
                    "research_continuation_discussion_eligible": True,
                },
            ],
            "first_final_artifact_immutable": True,
            "rerun_allowed": False,
            "threshold_override_allowed": False,
            "sample_deletion_allowed": False,
            "alternate_seed_allowed": False,
            "alternate_start_allowed": False,
            "favorable_result_selection_allowed": False,
        }
    )
    interim_policy = _with_policy_hash(
        {
            "economics_withheld_before_tail": True,
            "early_success_allowed": False,
            "pnl_based_early_stop_allowed": False,
            "threshold_override_allowed": False,
            "sample_override_allowed": False,
            "rerun_to_seek_better_result_allowed": False,
        }
    )
    plan: Dict[str, Any] = {
        "$schema": "./challenger-replacement-economic-evaluation-plan-v1.schema.json",
        "schema_version": "1.0.0",
        "plan_id": "challenger_replacement_economic_evaluation_plan_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "foundation": {
            "v069_plan": {
                "file_sha256": "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3",
                "plan_id": "challenger_replacement_plan_v3_e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f",
                "plan_hash": "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486",
            },
            "v069_owner_attestation": {
                "file_sha256": "b1ec38575b2e4f2b93b9f4838aa04633f382b60aef65843e4812d9b5c799b9c7",
                "attestation_id": (
                    "challenger_replacement_v3_owner_attestation_"
                    "18626ea8f79c90f5924b50317635ce07c1c933879de42463f0e79095fb8e4388"
                ),
                "attestation_hash": (
                    "99d99968eb5aa12bad064864d02aac4f37248a0fafb36d633c8c18315206fb21"
                ),
            },
            "v070_result_evidence_schema": {"file_sha256": "755f4e049da22ab4300ce5ed68b73c0d9462581792b7b3955fff1712f6ca6dca"},
            "v071_simulation_contract": {
                "file_sha256": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
                "contract_id": (
                    "challenger_replacement_simulation_contract_"
                    "c95cee71f23e58cf40bc4739e5063824de1a77fd5c6fcc72794ff42e1f84f791"
                ),
                "contract_hash": (
                    "b21beb877101590aabcc65927539d58eb001c4dc5de89ead0306ac840450f501"
                ),
            },
            "v072_golden_manifest": {
                "file_sha256": "c86993a5d56805eee3b703301f92d704cf0e7dacd06d4725a7ad9c3c16dd2b5f",
                "manifest_id": (
                    "challenger_replacement_binance_golden_fixture_manifest_"
                    "b2ce1d97bd41c812a5f58907602519da7df8d4543e33298389f0e5232e5c1821"
                ),
                "manifest_hash": (
                    "6977acff468689aeba64f1d814842c77ffa394f28bf686fdc82d02f5b61efbb4"
                ),
            },
            "v073_release": {
                "release_tag": "v0.73.0",
                "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                "package_version": "0.73.0",
                "manifest_version": "1.67.0",
                "manifest_hash": "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0",
                "tree_hash": "569afbae2352932a05a6c5daeb1c52049c9a3ec74034d666664579aa2bd0a97e",
                "file_sha256": "c41a46442993bac947773d383f722dfbaa358417ba67e87bf1e81db37c5e1c74",
            },
        },
        "population_contract": population_contract,
        "economic_measurement": economic_measurement,
        "missingness_policy": missingness_policy,
        "statistical_design": statistical_design,
        "sample_gates": [
            {"metric": "CALENDAR_DAYS", "operator": "EQ", "threshold": "90"},
            {"metric": "DAILY_RETURN_COUNT", "operator": "EQ", "threshold": "90"},
            {"metric": "TERMINAL_COVERAGE", "operator": "EQ", "threshold": "1"},
            {"metric": "OBSERVED_COVERAGE", "operator": "GTE", "threshold": "0.95"},
            {"metric": "COMPLETED_CYCLES", "operator": "GTE", "threshold": "12"},
            {"metric": "SPOT_COMPLETED_CYCLES", "operator": "GTE", "threshold": "3"},
            {"metric": "PERPETUAL_COMPLETED_CYCLES", "operator": "GTE", "threshold": "3"},
            {"metric": "NONEMPTY_FIXED_BLOCKS", "operator": "EQ", "threshold": "6"},
            {"metric": "MINIMUM_MBB_BLOCKS", "operator": "GTE", "threshold": "12"},
            {"metric": "ACHIEVED_POWER_AT_MERE", "operator": "GTE", "threshold": "0.80"},
        ],
        "economic_gates": [
            {"metric": "MEAN_DAILY_NET_RETURN_LCB95", "operator": "GT", "threshold": "0"},
            {"metric": "TOTAL_NET_PNL_USDT", "operator": "GT", "threshold": "0"},
            {"metric": "MAX_DRAWDOWN_FRACTION", "operator": "LT", "threshold": "0.05"},
            {"metric": "NONNEGATIVE_FIXED_15_DAY_BLOCKS", "operator": "GTE", "threshold": "5", "denominator": "6"},
            {"metric": "STRESS_1_5X_ADVERSE_FRICTION_TOTAL_NET_PNL_USDT", "operator": "GTE", "threshold": "0"},
        ],
        "final_state_machine": final_state_machine,
        "interim_policy": interim_policy,
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "account_requests_allowed": False,
            "credentials_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "market_requests": 0,
            "production_state_writes": 0,
            "economic_outcome_reads": 0,
        },
        "status": "ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED",
        "eligibility": {
            "research_continuation_discussion": "ELIGIBLE_ONLY_AFTER_FUTURE_GATE_PASS",
            "canary": "INELIGIBLE",
            "live_trading": "INELIGIBLE",
            "profitability_claim": "INELIGIBLE",
        },
        "warnings": [
            "NO_ECONOMIC_OUTCOME_WAS_READ",
            "NO_90_DAY_ECONOMIC_CLOCK_WAS_STARTED",
            "NO_PRODUCTION_AUTHORITY_WAS_GRANTED",
        ],
    }
    plan["plan_id"] = stable_id(
        "challenger_replacement_economic_evaluation_plan", _identity(plan)
    )
    plan["plan_hash"] = challenger_replacement_economic_plan_hash(plan)
    if _schema_errors(plan):
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID"
        )
    return copy.deepcopy(plan)


_POLICY_SECTIONS = (
    "population_contract",
    "economic_measurement",
    "missingness_policy",
    "statistical_design",
    "final_state_machine",
    "interim_policy",
)


def challenger_replacement_economic_plan_reasons(
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return the released fail-closed integrity reasons in fixed order."""

    reasons = []
    try:
        if _schema_errors(plan):
            reasons.append("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID")
        if plan.get("plan_hash") != challenger_replacement_economic_plan_hash(plan):
            reasons.append("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_HASH_MISMATCH")
        for section_name in _POLICY_SECTIONS:
            section = dict(plan[section_name])
            claimed = section.pop("policy_hash")
            if claimed != business_hash(section):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_POLICY_HASH_MISMATCH"
                )
                break
        if plan.get("plan_id") != stable_id(
            "challenger_replacement_economic_evaluation_plan", _identity(plan)
        ):
            reasons.append("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_ID_MISMATCH")
        if business_hash(plan) != business_hash(
            build_challenger_replacement_economic_plan()
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SEMANTIC_MISMATCH"
            )
    except ChallengerReplacementEconomicPlanError as error:
        if error.reason_code == (
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SCHEMA_INVALID"
        ):
            reasons.append(error.reason_code)
        else:
            reasons.append(
                "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SEMANTIC_MISMATCH"
            )
    except (
        CanonicalizationError,
        ChallengerReplacementPlanError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_SEMANTIC_MISMATCH")
    return tuple(dict.fromkeys(reasons))


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_FLOAT_FORBIDDEN"
    return "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_INVALID"


def load_challenger_replacement_economic_plan(path: Path) -> Dict[str, Any]:
    """Load only owner-controlled canonical bytes for the frozen plan."""

    try:
        plan_path = Path(path)
    except (OSError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID"
        ) from error
    if not plan_path.is_absolute():
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(plan_path)
    except (ChallengerReplacementPlanError, OSError, ValueError) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_PATH_INVALID"
        ) from error
    try:
        plan = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementEconomicPlanError(_mapped_json_error(error)) from error
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_INVALID"
        ) from error
    try:
        canonical = canonical_json(plan).encode("utf-8")
    except (
        CanonicalizationError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ) as error:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_JSON_INVALID"
        ) from error
    if body != canonical + b"\n":
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_CANONICAL_BYTES_REQUIRED"
        )
    if hashlib.sha256(body).hexdigest() != _ARTIFACT_SHA256:
        raise ChallengerReplacementEconomicPlanError(
            "CHALLENGER_REPLACEMENT_ECONOMIC_PLAN_FILE_SHA256_MISMATCH"
        )
    reasons = challenger_replacement_economic_plan_reasons(plan)
    if reasons:
        raise ChallengerReplacementEconomicPlanError(reasons[0])
    return copy.deepcopy(plan)
