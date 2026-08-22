"""Plan-only DecisionOpportunity and Binance Canary preregistration v3.

Building or loading this plan grants no install, runtime, credential, account,
Broker, order, funding, or production-activation authority.
"""

import copy
import json
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _read_owner_controlled_regular_file,
    _strict_json_bytes,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-plan-v3.schema.json"
_ZERO_HASH = "0" * 64

_FOUNDATION = {
    "release_tag": "v0.68.0",
    "peeled_commit": "b65481cce9c8955f73da5b78ef2bd3c981f3be3c",
    "package_version": "0.68.0",
    "manifest_version": "1.62.0",
    "build_input_tree_hash": (
        "c8419340b66e2b0405b19cda7eeed09114307deed0575249974cc6248743ddc9"
    ),
    "manifest_hash": (
        "5e7646febc6f09261387d448dc6c5f4431c3fc53b06073af48539a2e020aa8a8"
    ),
    "manifest_file_sha256": (
        "8830930b3a425b73aee8a24fc0d4b011aa9557dd34d6065e7f9b955097da25d8"
    ),
}

_PREVIOUS_PLAN = {
    "release_tag": "v0.64.0",
    "path": (
        "artifacts/challenger-replacement/"
        "challenger-replacement-plan-v0.64.0.json"
    ),
    "file_sha256": (
        "5f1774fd912451d79c9efe13401e80f312fee3c707d9faa252933ef3e8810a8f"
    ),
    "plan_id": (
        "challenger_replacement_plan_"
        "65d85d60a534a917f45a1ffa5fc9d3f74d6d24995b900d31b8c73cd26f0bd97b"
    ),
    "plan_hash": (
        "c9a1e5f74c52fbf23be5a1d27fd23c25f3601ed58133178fc25480391ab65705"
    ),
    "status": "PLAN_FROZEN_REPLACEMENT_V2_NOT_STARTED",
}

_SEMANTIC_CHANGES = [
    "LONG_ONLY_SPOT_TO_MUTUALLY_EXCLUSIVE_SPOT_LONG_OR_PERP_SHORT",
    "ALL_540_SLOTS_TO_DECISION_OPPORTUNITY_OUTCOMES",
    "SINGLE_90_DAY_GATE_TO_7_DAY_OPERATIONAL_AND_90_DAY_ECONOMIC",
    "MAXIMUM_1X_TO_STAGED_2X_TECHNICAL_CAP",
    "PERCENTAGE_STAGES_TO_FIXED_CAPITAL_E0_E1_E2",
    "NO_CREDENTIAL_ORDER_AUTHORITY_TO_FUTURE_EXACT_ACTIVATION_ONLY",
]

_WARNINGS = [
    "OLD_COHORT_PERMANENTLY_FAILED_NO_BACKFILL",
    "V0_64_PLAN_SUPERSEDED_BEFORE_START",
    "REPLACEMENT_V3_NOT_INSTALLED_OR_STARTED",
    "NO_INTERIM_ECONOMIC_REPORTING",
    "SEVEN_DAY_OPERATIONAL_PASS_IS_NOT_PROFITABILITY_EVIDENCE",
    "NO_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
    "CREDENTIAL_ORDER_FUND_AND_CANARY_NOT_AUTHORIZED",
]

_POLICY_SECTIONS = (
    "scope",
    "decision_policy",
    "opportunity_policy",
    "operational_qualification",
    "economic_evidence",
    "canary_ladder",
    "product_policy",
    "risk_policy",
    "isolation_policy",
    "evidence_policy",
    "storage_authority",
)


class ChallengerReplacementPlanV3Error(ValueError):
    """The replacement Challenger v3 plan failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _with_policy_hash(policy: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(policy))
    result["policy_hash"] = business_hash(policy)
    return result


def challenger_replacement_plan_v3_hash(plan: Mapping[str, Any]) -> str:
    """Hash the v3 plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "previous_plan_file_sha256": plan["supersession"][
            "previous_plan_file_sha256"
        ],
        "previous_plan_id": plan["supersession"]["previous_plan_id"],
        "previous_plan_hash": plan["supersession"]["previous_plan_hash"],
        "foundation": plan["foundation"],
        **{
            f"{name}_policy_hash": plan[name]["policy_hash"]
            for name in _POLICY_SECTIONS
        },
    }


def _decision_policy() -> Dict[str, Any]:
    hypothesis = {
        "registration": "REPLACEMENT_V3_DUAL_DIRECTION_PRE_START",
        "economic_asset": "ETH",
        "spot_state": "SPOT_LONG",
        "perpetual_state": "PERP_SHORT",
        "sma_window": 20,
        "momentum_lag_bars": 5,
        "sma20_distance_minimum": "0.005",
        "minimum_hold_hours": 8,
        "vertical_exit_hours": 24,
        "long_entry": (
            "LATEST_CLOSE_GTE_PRIOR_SMA20_TIMES_1_005_"
            "AND_LOG_RETURN_5_GT_ZERO"
        ),
        "short_entry": (
            "LATEST_CLOSE_LTE_PRIOR_SMA20_TIMES_0_995_"
            "AND_LOG_RETURN_5_LT_ZERO"
        ),
        "long_exit_after_minimum": (
            "LATEST_CLOSE_LTE_PRIOR_SMA20_OR_VERTICAL_EXIT"
        ),
        "short_exit_after_minimum": (
            "LATEST_CLOSE_GTE_PRIOR_SMA20_OR_VERTICAL_EXIT"
        ),
        "same_opportunity_close_and_reverse_allowed": False,
        "reverse_requires_next_opportunity_after_verified_flat": True,
    }
    return _with_policy_hash(
        {
            "version": (
                "CHALLENGER_REPLACEMENT_SMA20_MOMENTUM_DUAL_DIRECTION_V1"
            ),
            "predecessor_policy_id": (
                "CHALLENGER_REPLACEMENT_SMA20_MOMENTUM_V1"
            ),
            "predecessor_policy_hash": (
                "d444fbee8cbc7c186e8ff31fccae4b37020061573d446f4d2b0428acd7f95bc1"
            ),
            "hypothesis_registration_hash": business_hash(hypothesis),
            **{
                key: value
                for key, value in hypothesis.items()
                if key
                not in (
                    "registration",
                    "economic_asset",
                    "spot_state",
                    "perpetual_state",
                )
            },
        }
    )


def _stage(
    capital: str, exposure: str, days: int, cycles: int
) -> Dict[str, Any]:
    return {
        "capital_limit_usdt": capital,
        "gross_exposure_limit": exposure,
        "minimum_calendar_days": days,
        "minimum_strategy_cycles": cycles,
    }


def _absolute_risk() -> Dict[str, Any]:
    return {
        "daily_loss_limit_kind": "ABSOLUTE_USDT",
        "daily_loss_limit": "2",
        "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
        "drawdown_limit_kind": "ABSOLUTE_USDT",
        "drawdown_limit": "5",
        "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
    }


def build_challenger_replacement_plan_v3() -> Dict[str, Any]:
    """Build the sole v3 governance plan without runtime side effects."""

    scope = _with_policy_hash(
        {
            "mode": "REPLACEMENT_CHALLENGER_CONFIRMATORY_V3",
            "cohort_generation": "replacement-v2",
            "route": "BASELINE_ONLY",
            "economic_asset": "ETH",
            "symbol": "ETHUSDT",
            "venue": "BINANCE_ONLY",
            "market_and_direction": (
                "MUTUALLY_EXCLUSIVE_SPOT_LONG_OR_USDM_PERPETUAL_SHORT"
            ),
            "research_hypothesis_reset": True,
        }
    )
    opportunity = _with_policy_hash(
        {
            "cadence_seconds": 14_400,
            "capture_open_offset_seconds": 120,
            "capture_close_offset_seconds": 600,
            "terminal_outcomes": ["OBSERVED", "MISSED"],
            "historical_decision_backfill_allowed": False,
            "missed_opportunity_recovery": (
                "APPEND_MISSED_WITH_ACTUAL_DETECTION_TIME"
            ),
            "missed_reason_codes": [
                "PROCESS_NOT_RUNNING",
                "CAPTURE_WINDOW_EXPIRED",
                "PUBLIC_MARKET_SOURCE_UNAVAILABLE",
                "CLOCK_OR_CONNECTIVITY_UNTRUSTED",
                "PRECONDITION_FAILED_CLOSED",
            ],
        }
    )
    operational = _with_policy_hash(
        {
            "start_source": "FIRST_VERIFIED_NATURAL_OBSERVED_OPPORTUNITY",
            "minimum_calendar_days": 7,
            "minimum_observed_coverage": "0.95",
            "minimum_strategy_cycles": 3,
            "spot_roundtrip_required": True,
            "perpetual_roundtrip_required": True,
            "automatic_extension_required": True,
            "window_reset_allowed": False,
            "profitability_claim_allowed": False,
            "terminal_statuses": [
                "OPERATIONAL_QUALIFICATION_PASS",
                "PENDING_AUTOMATIC_EXTENSION",
                "OPERATIONAL_QUALIFICATION_DID_NOT_PASS",
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            ],
        }
    )
    economic = _with_policy_hash(
        {
            "start_source": "INDEPENDENT_ECONOMIC_START_RECEIPT",
            "minimum_calendar_days": 90,
            "terminal_coverage_required": "1",
            "minimum_observed_coverage": "0.95",
            "interim_profitability_pass_allowed": False,
            "window_reset_allowed": False,
            "window_extension_to_seek_better_result_allowed": False,
            "terminal_statuses": [
                "RESEARCH_CONTINUATION_GATE_PASS",
                "RESEARCH_CONTINUATION_GATE_DID_NOT_PASS",
                "INCONCLUSIVE_INSUFFICIENT_EVIDENCE",
            ],
        }
    )
    ladder = _with_policy_hash(
        {
            "E0": _stage("100", "0.5", 7, 3),
            "E1": _stage("300", "1", 14, 5),
            "E2": _stage("1000", "2", 30, 10),
            "spot_roundtrip_each_stage_required": True,
            "perpetual_roundtrip_each_stage_required": True,
            "promotion_automatic": False,
        }
    )
    product = _with_policy_hash(
        {
            "venue": "BINANCE_ONLY",
            "economic_asset": "ETH",
            "spot_instrument": "ETHUSDT_SPOT",
            "spot_direction": "LONG_ONLY_UNMARGINED",
            "perpetual_instrument": "ETHUSDT_USDM_PERPETUAL",
            "perpetual_direction": "SHORT_ONLY",
            "position_states": ["FLAT", "SPOT_LONG", "PERP_SHORT"],
            "products_mutually_exclusive": True,
            "flatten_before_reversal_required": True,
            "perpetual_position_mode": "ONE_WAY",
            "perpetual_margin_mode": "ISOLATED",
            "technical_leverage_cap": "2",
            "gateio_fallback_allowed": False,
        }
    )
    risk = _with_policy_hash(
        {
            "E0": _absolute_risk(),
            "E1": _absolute_risk(),
            "E2": {
                "daily_loss_limit_kind": "FRACTION_OF_STAGE_CAPITAL",
                "daily_loss_limit": "0.02",
                "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
                "drawdown_limit_kind": "FRACTION_OF_HIGH_WATER_EQUITY",
                "drawdown_limit": "0.075",
                "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
            },
            "daily_boundary_timezone": "UTC",
            "loss_components": ["REALIZED", "UNREALIZED", "FEES", "FUNDING"],
            "failure_conditions": [
                "UNRESOLVED_UNKNOWN",
                "DUPLICATE_ECONOMIC_ORDER",
                "UNRECORDED_OR_CONFLICTING_FILL",
                "LEDGER_POSITION_MISMATCH",
                "DISASTER_STOP_MISSING_OR_UNCONFIRMED",
                "ACCOUNT_MARGIN_OR_LEVERAGE_MODE_MISMATCH",
                "CLOCK_MARKET_ACCOUNT_OR_USER_STREAM_INSUFFICIENT",
                "S0_OR_S1_INCIDENT",
                "CREDENTIAL_OR_IP_BOUNDARY_UNTRUSTED",
                "EVIDENCE_DURABILITY_OR_IDENTITY_FAILURE",
            ],
            "incident_unlock_automatic": False,
        }
    )
    isolation = _with_policy_hash(
        {
            "service_label": "local.crypto-quant.challenger-replacement-v1",
            "service_identity": (
                "gui/501/local.crypto-quant.challenger-replacement-v1"
            ),
            "runtime_root": (
                "/Users/chenm4/Library/Application Support/CryptoQuant/"
                "challenger-replacement-v1"
            ),
            "target_plist": (
                "/Users/chenm4/Library/LaunchAgents/"
                "local.crypto-quant.challenger-replacement-v1.plist"
            ),
            "state_events_relative_path": (
                "state/challenger-replacement-events-v1"
            ),
            "owner_only_required": True,
            "single_hardlink_required": True,
            "symlink_ancestors_forbidden": True,
            "no_overwrite_required": True,
        }
    )
    evidence = _with_policy_hash(
        {
            "all_opportunities_included": True,
            "missed_visible": True,
            "historical_backfill_allowed": False,
            "interim_economics_withheld": True,
            "operational_and_economic_results_separate": True,
            "old_evidence_migrated": False,
        }
    )
    storage = _with_policy_hash(
        {
            "authoritative_state_kind": (
                "APPEND_ONLY_CANONICAL_DECISION_OPPORTUNITY_EVENT_LOG"
            ),
            "authoritative_relative_path": (
                "state/challenger-replacement-events-v1"
            ),
            "runner_authority_source": "CANONICAL_EVENT_LOG_ONLY",
            "observer_authority_source": "STRICT_EVENT_PROJECTION_ONLY",
            "operational_evaluator_authority_source": (
                "STRICT_EVENT_PROJECTION_ONLY"
            ),
            "economic_evaluator_authority_source": (
                "STRICT_EVENT_PROJECTION_ONLY"
            ),
            "exports_authoritative": False,
        }
    )

    plan: Dict[str, Any] = {
        "$schema": "./challenger-replacement-plan-v3.schema.json",
        "schema_version": "3.0.0",
        "plan_id": "challenger_replacement_plan_v3_" + _ZERO_HASH,
        "plan_hash": _ZERO_HASH,
        "foundation": copy.deepcopy(_FOUNDATION),
        "predecessor": {
            "previous_plan": copy.deepcopy(_PREVIOUS_PLAN),
            "old_cohort_failure_preserved": True,
            "old_cohort_decommission_preserved": True,
        },
        "scope": scope,
        "decision_policy": _decision_policy(),
        "opportunity_policy": opportunity,
        "operational_qualification": operational,
        "economic_evidence": economic,
        "canary_ladder": ladder,
        "product_policy": product,
        "risk_policy": risk,
        "isolation_policy": isolation,
        "evidence_policy": evidence,
        "storage_authority": storage,
        "supersession": {
            "previous_plan_release_tag": "v0.64.0",
            "previous_plan_file_sha256": _PREVIOUS_PLAN["file_sha256"],
            "previous_plan_id": _PREVIOUS_PLAN["plan_id"],
            "previous_plan_hash": _PREVIOUS_PLAN["plan_hash"],
            "reason": (
                "SUPERSEDED_PRE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE"
            ),
            "previous_plan_disposition": (
                "SUPERSEDED_BEFORE_START_RESEARCH_AND_OPERATIONAL_POLICY_CHANGE"
            ),
            "supersession_forbidden_after": (
                "FIRST_V3_START_RECEIPT_OR_CANONICAL_PRODUCTION_"
                "OPPORTUNITY_EVENT"
            ),
            "semantic_changes": list(_SEMANTIC_CHANGES),
        },
        "authority": {
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
        },
        "status": "PLAN_FROZEN_REPLACEMENT_V3_NOT_STARTED",
        "eligibility": {
            "operational": "INELIGIBLE_SIMULATION_NOT_STARTED",
            "economic": "INELIGIBLE_90_DAY_EVIDENCE_NOT_STARTED",
            "canary": "INELIGIBLE_NOT_AUTHORIZED",
            "profitability": "INELIGIBLE_NO_FINAL_EVIDENCE",
            "ai_advantage": "INELIGIBLE_NO_PAIRED_AI_PLAN",
        },
        "warnings": list(_WARNINGS),
    }
    plan["plan_id"] = stable_id(
        "challenger_replacement_plan_v3", _identity(plan)
    )
    plan["plan_hash"] = challenger_replacement_plan_v3_hash(plan)
    if tuple(_validator().iter_errors(plan)):
        raise ChallengerReplacementPlanV3Error(
            "CHALLENGER_REPLACEMENT_PLAN_V3_SCHEMA_INVALID"
        )
    return copy.deepcopy(plan)

def challenger_replacement_plan_v3_reasons(
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return deterministic fail-closed reason codes for v3 semantics."""

    reasons = []
    try:
        if tuple(_validator().iter_errors(plan)):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V3_SCHEMA_INVALID")
        if plan.get("plan_hash") != challenger_replacement_plan_v3_hash(plan):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V3_HASH_MISMATCH")
        for section_name in _POLICY_SECTIONS:
            section = dict(plan[section_name])
            claimed = section.pop("policy_hash")
            if claimed != business_hash(section):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_PLAN_V3_POLICY_HASH_MISMATCH"
                )
        if plan.get("plan_id") != stable_id(
            "challenger_replacement_plan_v3", _identity(plan)
        ):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V3_ID_MISMATCH")
        if business_hash(plan) != business_hash(
            build_challenger_replacement_plan_v3()
        ):
            reasons.append("CHALLENGER_REPLACEMENT_PLAN_V3_SEMANTIC_MISMATCH")
    except (
        CanonicalizationError,
        ChallengerReplacementPlanError,
        ChallengerReplacementPlanV3Error,
        KeyError,
        TypeError,
        ValueError,
    ):
        reasons.append("CHALLENGER_REPLACEMENT_PLAN_V3_SEMANTIC_INVALID")
    return tuple(sorted(set(reasons)))


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return "CHALLENGER_REPLACEMENT_PLAN_V3_JSON_DUPLICATE_KEY"
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return "CHALLENGER_REPLACEMENT_PLAN_V3_JSON_FLOAT_FORBIDDEN"
    return "CHALLENGER_REPLACEMENT_PLAN_V3_JSON_INVALID"


def load_challenger_replacement_plan_v3(path: Path) -> Dict[str, Any]:
    """Load owner-controlled canonical bytes for the one frozen v3 plan."""

    plan_path = Path(path)
    if not plan_path.is_absolute():
        raise ChallengerReplacementPlanV3Error(
            "CHALLENGER_REPLACEMENT_PLAN_V3_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(plan_path)
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV3Error(
            "CHALLENGER_REPLACEMENT_PLAN_V3_PATH_INVALID"
        ) from error
    try:
        plan = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementPlanV3Error(
            _mapped_json_error(error)
        ) from error
    try:
        canonical = canonical_json(plan).encode("utf-8")
    except (CanonicalizationError, RecursionError) as error:
        raise ChallengerReplacementPlanV3Error(
            "CHALLENGER_REPLACEMENT_PLAN_V3_JSON_INVALID"
        ) from error
    if body not in (canonical, canonical + b"\n"):
        raise ChallengerReplacementPlanV3Error(
            "CHALLENGER_REPLACEMENT_PLAN_V3_CANONICAL_BYTES_REQUIRED"
        )
    reasons = challenger_replacement_plan_v3_reasons(plan)
    if reasons:
        raise ChallengerReplacementPlanV3Error(reasons[0])
    return copy.deepcopy(plan)
