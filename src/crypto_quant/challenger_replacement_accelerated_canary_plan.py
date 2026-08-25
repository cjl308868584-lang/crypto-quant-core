"""Plan-only accelerated replacement Canary preregistration.

This module is pure governance. It reads no runtime, market, account, credential,
order, fund, state, or economic outcome and grants no production authority.
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


_SCHEMA = "challenger-replacement-accelerated-canary-plan-v1.schema.json"
_ZERO_HASH = "0" * 64
_ARTIFACT_SHA256 = _ZERO_HASH
_POLICY_SECTIONS = (
    "supersession_scope",
    "projection_contract",
    "code_complete_program",
    "simulation_qualification",
    "operational_ceremony",
    "hard_stop_policy",
    "canary_ladder",
    "credential_boundary",
    "approval_ledger",
)


class ChallengerReplacementAcceleratedCanaryPlanError(ValueError):
    """The accelerated Canary preregistration failed closed."""

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
    except (OSError, SchemaError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SCHEMA_INVALID"
        ) from error


def _schema_errors(value: Mapping[str, Any]) -> Tuple[Any, ...]:
    try:
        return tuple(_validator().iter_errors(value))
    except ChallengerReplacementAcceleratedCanaryPlanError:
        raise
    except (OSError, SchemaError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SCHEMA_INVALID"
        ) from error


def _with_policy_hash(value: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result["policy_hash"] = business_hash(value)
    return result


def challenger_replacement_accelerated_canary_plan_hash(
    plan: Mapping[str, Any],
) -> str:
    """Hash the plan while excluding only its self-hash field."""

    return artifact_self_hash(plan, "plan_hash")


def _identity(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "foundation": plan["foundation"],
        **{
            section + "_policy_hash": plan[section]["policy_hash"]
            for section in _POLICY_SECTIONS
        },
    }


def build_challenger_replacement_accelerated_canary_plan() -> Dict[str, Any]:
    """Build the deterministic, parameterless accelerated Canary plan."""

    supersession_scope = _with_policy_hash(
        {
            "changed_rules": [
                "SEVEN_DAY_NATURAL_CYCLE_GATE_TO_CONTINUOUS_72_HOUR_QUALIFICATION",
                "NATURAL_PRE_E0_PRODUCT_ROUNDTRIPS_TO_EXCLUDED_OPERATIONAL_CEREMONY",
                "PERMANENT_STREAM_LOCK_TO_IMMUTABLE_FAILED_BLOCK_AND_APPROVED_NEW_BLOCK",
                "BROAD_TERMINAL_OPERATIONAL_FAILURES_TO_FOUR_ABSOLUTE_STAGE_HARD_STOPS",
            ],
            "unchanged_rules": [
                "FOUR_HOUR_DECISION_OPPORTUNITY_CADENCE",
                "MISSED_RETAINED_NO_BACKFILL",
                "V074_NINETY_DAY_ECONOMIC_RESEARCH_UNCHANGED",
                "BINANCE_ONLY_MUTUALLY_EXCLUSIVE_SPOT_LONG_PERP_SHORT",
                "ONE_WAY_ISOLATED_PERPETUAL_TECHNICAL_CAP_2X",
                "E0_E1_E2_CAPITAL_EXPOSURE_AND_LOSS_LIMITS",
                "NO_SHORT_WINDOW_PROFITABILITY_OR_AI_ADVANTAGE_CLAIM",
            ],
            "effective_for_future_bound_start_only": True,
            "retroactive_rewrite_allowed": False,
            "economic_contract_changed": False,
        }
    )
    projection_contract = _with_policy_hash(
        {
            "fact_source": (
                "APPEND_ONLY_CANONICAL_DECISION_OPPORTUNITY_EVENT_LOG"
            ),
            "economic_projection": (
                "V074_ECONOMIC_RESEARCH_PROJECTION_V1_UNCHANGED"
            ),
            "operational_projection": (
                "ACCELERATED_OPERATIONAL_CANARY_PROJECTION_V2"
            ),
            "projection_write_authority": False,
            "exports_authoritative": False,
            "ceremony_economic_use": (
                "EXCLUDED_FROM_STRATEGY_AND_ECONOMIC_EVIDENCE"
            ),
        }
    )
    code_complete_program = _with_policy_hash(
        {
            "minimum_target_days": 10,
            "maximum_target_days": 14,
            "release_sequence": [
                "V075_GOVERNANCE_SUPERSESSION",
                "V076_PUBLIC_SIMULATION_AND_RESEARCH_BUNDLE",
                "V077_BINANCE_PRIVATE_BOUNDARY_AND_CANARY_BUNDLE",
            ],
            "milestone": "CODE_COMPLETE_NOT_ACTIVATED",
            "activation_at_milestone": False,
        }
    )
    simulation_qualification = _with_policy_hash(
        {
            "start_source": (
                "FIRST_NATURAL_PRODUCTION_QUALIFIED_OBSERVED_"
                "AFTER_INSTALL_AND_PREFLIGHT"
            ),
            "minimum_continuous_seconds": 259_200,
            "cadence_seconds": 14_400,
            "fixture_time_counts": False,
            "healthy_segment_rule": (
                "ONE_FINAL_UNINTERRUPTED_SEGMENT_DISCONNECTED_SECONDS_NEVER_SUMMED"
            ),
            "flat_missed_action": (
                "CLOSE_SEGMENT_RECOVERABLE_START_NEW_SEGMENT_"
                "AT_NEXT_NATURAL_OBSERVED"
            ),
            "short_disconnect_action": (
                "CLOSE_SEGMENT_RECOVERABLE_AFTER_FLAT_RECONCILIATION"
            ),
            "exposed_miss_action": (
                "REJECT_NEW_RISK_FLATTEN_FAIL_BLOCK_REQUIRE_INCIDENT_UNLOCK"
            ),
            "terminal_outcomes": ["OBSERVED", "MISSED"],
            "complete_fault_matrix_required": True,
            "replay_required": True,
        }
    )
    operational_ceremony = _with_policy_hash(
        {
            "label": "OPERATIONAL_CEREMONY_NOT_STRATEGY_EVIDENCE",
            "start_state": "CEREMONY_READY_FLAT",
            "ordered_states": [
                "CEREMONY_READY_FLAT",
                "SPOT_BUY_SUBMITTED",
                "SPOT_LONG_RECONCILED",
                "SPOT_SELL_SUBMITTED",
                "FLAT_RECONCILED_AFTER_SPOT",
                "PERP_SHORT_SUBMITTED",
                "PERP_SHORT_AND_PROTECTIVE_STOP_CONFIRMED",
                "PERP_CLOSE_REDUCE_ONLY_SUBMITTED",
                "FLAT_RECONCILED_AFTER_PERP",
                "CEREMONY_QUALIFIED",
            ],
            "amount_source": (
                "VENUE_VERIFIED_MINIMUM_PERMISSIBLE_AMOUNT_AT_APPROVED_PREFLIGHT"
            ),
            "spot_instrument": "ETHUSDT_SPOT",
            "perpetual_instrument": "ETHUSDT_USDM_PERPETUAL",
            "perpetual_position_mode": "ONE_WAY",
            "perpetual_margin_mode": "ISOLATED",
            "technical_leverage_cap": "2",
            "product_mutual_exclusion": True,
            "protective_stop_required_while_exposed": True,
            "close_reduce_only_required": True,
            "evidence_exclusions": {
                "strategy_cycle_count": True,
                "economic_population": True,
                "simulation_performance": True,
                "stage_strategy_cycle_count": True,
            },
            "retry_policy": (
                "FAILED_BLOCK_RETAINED_NEW_EXACT_APPROVAL_"
                "AFTER_INCIDENT_ACCEPTANCE"
            ),
        }
    )
    hard_stop_policy = _with_policy_hash(
        {
            "absolute_classes": [
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN",
                "VENUE_LOCAL_POSITION_MISMATCH",
                "PERPETUAL_EXPOSURE_WITHOUT_VALID_PROTECTIVE_STOP",
                "RISK_INCREASE_ATTEMPT_AFTER_STAGE_LOSS_LIMIT",
            ],
            "duplicate_order_mapping": (
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN_OR_"
                "VENUE_LOCAL_POSITION_MISMATCH"
            ),
            "unrecorded_fill_mapping": (
                "UNRESOLVED_ECONOMIC_ORDER_UNKNOWN_OR_"
                "VENUE_LOCAL_POSITION_MISMATCH"
            ),
            "block_effect": (
                "REJECT_NEW_RISK_RECONCILE_FLATTEN_AND_"
                "PERMANENTLY_FAIL_CURRENT_BLOCK"
            ),
            "project_effect": "PROJECT_NOT_PERMANENTLY_ABANDONED",
            "recovery_requirements": [
                "IMMUTABLE_INCIDENT_RECORD",
                "VERIFIED_FLAT_POSITION",
                "EXPLICIT_INCIDENT_UNLOCK_APPROVAL",
                "NEW_STAGE_BLOCK_IDENTITY",
            ],
            "recoverable_flat_conditions": [
                "SHORT_NETWORK_INTERRUPTION",
                "FLAT_MISSED_OPPORTUNITY",
                "INSUFFICIENT_SAMPLE",
                "INCOMPLETE_PRODUCT_COVERAGE",
                "NEGATIVE_SHORT_WINDOW_RETURN",
            ],
        }
    )
    canary_ladder = _with_policy_hash(
        {
            "E0": {
                "capital_limit_usdt": "100",
                "gross_exposure_limit": "0.5",
                "gross_exposure_notional_limit_usdt": "50",
                "minimum_calendar_days": 7,
                "minimum_strategy_cycles": 3,
                "daily_loss_limit_kind": "ABSOLUTE_USDT",
                "daily_loss_limit": "2",
                "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
                "drawdown_limit_kind": "ABSOLUTE_USDT",
                "drawdown_limit": "5",
                "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
            },
            "E1": {
                "capital_limit_usdt": "300",
                "gross_exposure_limit": "1",
                "minimum_calendar_days": 14,
                "minimum_strategy_cycles": 5,
                "daily_loss_limit_kind": "ABSOLUTE_USDT",
                "daily_loss_limit": "2",
                "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
                "drawdown_limit_kind": "ABSOLUTE_USDT",
                "drawdown_limit": "5",
                "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
            },
            "E2": {
                "capital_limit_usdt": "1000",
                "gross_exposure_limit": "2",
                "technical_leverage_cap": "2",
                "minimum_calendar_days": 30,
                "minimum_strategy_cycles": 10,
                "daily_loss_limit_kind": "FRACTION_OF_STAGE_CAPITAL",
                "daily_loss_limit": "0.02",
                "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
                "drawdown_limit_kind": "FRACTION_OF_HIGH_WATER_EQUITY",
                "drawdown_limit": "0.075",
                "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
            },
            "product_cycle_requirements": {
                "spot_complete_cycle_each_stage": 1,
                "perpetual_complete_cycle_each_stage": 1,
                "ceremony_cycles_count": False,
            },
            "promotion_automatic": False,
        }
    )
    credential_boundary = _with_policy_hash(
        {
            "venue": "BINANCE_ONLY",
            "repository_external": True,
            "owner_only": True,
            "withdrawal_allowed": False,
            "ip_allowlist_required": True,
            "least_privilege_required": True,
            "secret_logging_allowed": False,
        }
    )
    approval_ledger = _with_policy_hash(
        {
            "separately_approved_actions": [
                "INSTALL_PRODUCTION_LIKE_SIMULATION_SERVICE",
                "BOOTSTRAP_START_SERVICE_AND_CREATE_START_RECEIPTS",
                "CREATE_OR_READ_REAL_BINANCE_API_KEY",
                "FUND_OR_TRANSFER_CEREMONY_OR_E0_CAPITAL",
                "ACTIVATE_SPOT_CEREMONY_ORDERS",
                "ACTIVATE_PERPETUAL_CEREMONY_ORDERS",
                "ACTIVATE_E0",
                "PROMOTE_E1",
                "PROMOTE_E2",
                "UNLOCK_FAILED_BLOCK_AFTER_INCIDENT_REVIEW",
            ],
            "inference_from_general_approval_allowed": False,
            "binding_fields": [
                "RELEASED_BUILD_IDENTITY",
                "CONFIGURATION_HASH",
                "ACCOUNT_IDENTITY",
                "CAPITAL_LIMIT",
                "EXPIRY",
                "RISK_LIMITS",
            ],
        }
    )
    plan = {
        "$schema": (
            "./challenger-replacement-accelerated-canary-plan-v1.schema.json"
        ),
        "schema_version": "1.0.0",
        "plan_id": (
            "challenger_replacement_accelerated_canary_plan_" + _ZERO_HASH
        ),
        "plan_hash": _ZERO_HASH,
        "foundation": {
            "v069_plan": {
                "file_sha256": (
                    "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
                ),
                "plan_id": (
                    "challenger_replacement_plan_v3_"
                    "e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
                ),
                "plan_hash": (
                    "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
                ),
            },
            "v073_release": {
                "release_tag": "v0.73.0",
                "peeled_commit": "34bd0e9ba96c769b7301c482730a03fb975c24ce",
                "package_version": "0.73.0",
                "manifest_version": "1.67.0",
                "manifest_hash": (
                    "0117d3a17bdea7e2a22004d675175083e9d863722c6c176632d29e3c4c6e62d0"
                ),
            },
            "v074_economic_plan": {
                "file_sha256": (
                    "24fba7579ac36c037aaef4fbf34a69b56503358edbd64addbe01f30a70c33297"
                ),
                "plan_id": (
                    "challenger_replacement_economic_evaluation_plan_"
                    "13ba2b74dd8c330732789a3fccd36f017847047f9fd07ea0bcf36b66f54a943e"
                ),
                "plan_hash": (
                    "7c02267a0895cb3d8ceea79b6a38415140de23fb1cfcf3350c7fddff62089fa4"
                ),
            },
            "v074_release": {
                "release_tag": "v0.74.0",
                "tag_object": "86624de8be8d5117e4b4ef6fd825a9eb711c7c38",
                "peeled_commit": "bfe0080b0a29a74550449a1eb2ac2907a2d2ddac",
                "package_version": "0.74.0",
                "manifest_version": "1.68.0",
                "manifest_file_sha256": (
                    "0db974c9d143abee2e3fc078c09db8893a82754f1c4209178fb982d3d449db12"
                ),
                "manifest_hash": (
                    "699b50fe198b25934e67433d95ea75deb3f6e0657fa8c440a61c7d6c5349e2ec"
                ),
                "tree_hash": (
                    "fe58cc252f9b548e6eedb25e8249c6329cd20ee50f7a0cec48fe88abbbe4bb8e"
                ),
            },
        },
        "supersession_scope": supersession_scope,
        "projection_contract": projection_contract,
        "code_complete_program": code_complete_program,
        "simulation_qualification": simulation_qualification,
        "operational_ceremony": operational_ceremony,
        "hard_stop_policy": hard_stop_policy,
        "canary_ladder": canary_ladder,
        "credential_boundary": credential_boundary,
        "approval_ledger": approval_ledger,
        "authority": {
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "credentials_allowed": False,
            "account_requests_allowed": False,
            "broker_requests_allowed": False,
            "real_orders_allowed": False,
            "fund_movement_allowed": False,
            "ceremony_authorized": False,
            "e0_activation_authorized": False,
            "market_requests": 0,
            "private_account_requests": 0,
            "production_state_writes": 0,
            "economic_outcome_reads": 0,
        },
        "status": "ACCELERATED_CANARY_PLAN_PREREGISTERED_NOT_ACTIVATED",
        "warnings": [
            "V074_ECONOMIC_RESEARCH_REMAINS_IMMUTABLE",
            "SEVENTY_TWO_HOURS_IS_OPERATIONAL_NOT_PROFITABILITY_EVIDENCE",
            "CEREMONY_IS_NOT_STRATEGY_OR_ECONOMIC_EVIDENCE",
            "CODE_COMPLETE_NOT_ACTIVATED_NOT_YET_REACHED",
            "NO_INSTALL_START_CREDENTIAL_ORDER_FUND_OR_CANARY_AUTHORITY",
        ],
    }
    plan["plan_id"] = stable_id(
        "challenger_replacement_accelerated_canary_plan", _identity(plan)
    )
    plan["plan_hash"] = challenger_replacement_accelerated_canary_plan_hash(
        plan
    )
    if _schema_errors(plan):
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SCHEMA_INVALID"
        )
    return copy.deepcopy(plan)


def challenger_replacement_accelerated_canary_plan_reasons(
    plan: Mapping[str, Any],
) -> Tuple[str, ...]:
    """Return deterministic fail-closed integrity reasons."""

    reasons = []
    try:
        if _schema_errors(plan):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SCHEMA_INVALID"
            )
        if plan.get(
            "plan_hash"
        ) != challenger_replacement_accelerated_canary_plan_hash(plan):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_HASH_MISMATCH"
            )
        for section_name in _POLICY_SECTIONS:
            section = dict(plan[section_name])
            claimed = section.pop("policy_hash")
            if claimed != business_hash(section):
                reasons.append(
                    "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                    "PLAN_POLICY_HASH_MISMATCH"
                )
                break
        if plan.get("plan_id") != stable_id(
            "challenger_replacement_accelerated_canary_plan", _identity(plan)
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_ID_MISMATCH"
            )
        if business_hash(plan) != business_hash(
            build_challenger_replacement_accelerated_canary_plan()
        ):
            reasons.append(
                "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
                "PLAN_SEMANTIC_MISMATCH"
            )
    except ChallengerReplacementAcceleratedCanaryPlanError as error:
        reasons.append(error.reason_code)
    except (
        CanonicalizationError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        reasons.append(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_SEMANTIC_MISMATCH"
        )
    return tuple(dict.fromkeys(reasons))


def _mapped_json_error(error: ChallengerReplacementPlanError) -> str:
    if error.reason_code.endswith("JSON_DUPLICATE_KEY"):
        return (
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "PLAN_JSON_DUPLICATE_KEY"
        )
    if error.reason_code.endswith("JSON_FLOAT_FORBIDDEN"):
        return (
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "PLAN_JSON_FLOAT_FORBIDDEN"
        )
    return "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_INVALID"


def load_challenger_replacement_accelerated_canary_plan(
    path: Path,
) -> Dict[str, Any]:
    """Load only owner-controlled canonical bytes for the frozen plan."""

    try:
        plan_path = Path(path)
    except (OSError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID"
        ) from error
    if not plan_path.is_absolute():
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID"
        )
    try:
        body = _read_owner_controlled_regular_file(plan_path)
    except (ChallengerReplacementPlanError, OSError, ValueError) as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_PATH_INVALID"
        ) from error
    try:
        plan = dict(_strict_json_bytes(body))
    except ChallengerReplacementPlanError as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            _mapped_json_error(error)
        ) from error
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_INVALID"
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
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_PLAN_JSON_INVALID"
        ) from error
    if body != canonical + b"\n":
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "PLAN_CANONICAL_BYTES_REQUIRED"
        )
    if hashlib.sha256(body).hexdigest() != _ARTIFACT_SHA256:
        raise ChallengerReplacementAcceleratedCanaryPlanError(
            "CHALLENGER_REPLACEMENT_ACCELERATED_CANARY_"
            "PLAN_FILE_SHA256_MISMATCH"
        )
    reasons = challenger_replacement_accelerated_canary_plan_reasons(plan)
    if reasons:
        raise ChallengerReplacementAcceleratedCanaryPlanError(reasons[0])
    return copy.deepcopy(plan)
