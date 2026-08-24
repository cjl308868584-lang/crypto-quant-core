"""Frozen, fixture-only replacement simulation assumptions.

This module has no path, network, account, Broker, order, install, or start
capability.  Release provenance is bound later by the release manifest.
"""

import copy
import json
from functools import lru_cache
from importlib import resources
from typing import Any, Dict, Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .challenger_replacement_plan_v3 import (
    challenger_replacement_plan_v3_reasons,
)
from .errors import CanonicalizationError
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-simulation-contract-v1.schema.json"
_MAX_BYTES = 65_536
_ZERO_HASH = "0" * 64
_PLAN_ID = (
    "challenger_replacement_plan_v3_"
    "e1b6a4187cb4bb4b371ea503f83284056d4f0c6c504feb7827971869a52f666f"
)
_PLAN_HASH = "f29474a1700b0c3cf313047e2d6e85182e68104d9584ec9df7b492aa7ab00486"
_PLAN_FILE_SHA256 = (
    "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
)
_WARNINGS = [
    "FIXTURE_ONLY_NOT_LIVE_MARKET",
    "NO_ACCOUNT_OR_VENUE_FEE_CLAIM",
    "NO_OPERATIONAL_OR_ECONOMIC_TIMER_STARTED",
    "NO_PROFITABILITY_OR_CANARY_ELIGIBILITY",
]


class ChallengerReplacementSimulationContractError(ValueError):
    """The fixture simulation contract failed closed."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_INVALID"):
    raise ChallengerReplacementSimulationContractError(reason)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    resource = resources.files("crypto_quant").joinpath("schemas", _SCHEMA)
    schema = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _valid_plan(plan: object) -> bool:
    return (
        isinstance(plan, Mapping)
        and plan.get("plan_id") == _PLAN_ID
        and plan.get("plan_hash") == _PLAN_HASH
        and not challenger_replacement_plan_v3_reasons(plan)
    )


def _document(plan: Mapping[str, Any]) -> Dict[str, Any]:
    policy_bindings = {
        "decision_policy_hash": plan["decision_policy"]["policy_hash"],
        "opportunity_policy_hash": plan["opportunity_policy"]["policy_hash"],
        "product_policy_hash": plan["product_policy"]["policy_hash"],
        "risk_policy_hash": plan["risk_policy"]["policy_hash"],
        "storage_authority_policy_hash": plan["storage_authority"][
            "policy_hash"
        ],
    }
    products = {
        "spot_instrument": "BINANCE:SPOT:ETHUSDT",
        "spot_direction": "LONG_ONLY_UNMARGINED",
        "perpetual_instrument": "BINANCE:USDT_PERP:ETHUSDT",
        "perpetual_direction": "SHORT_ONLY",
        "products_mutually_exclusive": True,
        "perpetual_position_mode": "ONE_WAY",
        "perpetual_margin_mode": "ISOLATED",
    }
    accounting = {
        "decimal_arithmetic_only": True,
        "binary_float_allowed": False,
        "contract_multiplier_required": True,
        "fee_authority": "CONTRACT_MUST_EQUAL_INSTRUMENT_METADATA",
        "spot_conservative_mark": "BID",
        "perpetual_conservative_mark": "MARK",
        "perpetual_short_quantity_sign": "NEGATIVE",
        "funding_cashflow_formula": (
            "NEGATIVE_SIGNED_Q_TIMES_MULTIPLIER_TIMES_MARK_TIMES_RATE"
        ),
        "utc_day_start_boundary": "POST_STOP_FUNDING_MARK_BEFORE_NEW_ACTION",
        "continuous_high_water": True,
    }
    risk = {
        "daily_boundary_timezone": "UTC",
        "daily_loss_limit_usdt": "2",
        "daily_limit_action": "STOP_NEW_RISK_UNTIL_NEXT_UTC_DAY",
        "drawdown_limit_usdt": "5",
        "drawdown_limit_action": "FLATTEN_AND_STAGE_FAIL",
        "equality_triggers": True,
        "gross_drift_action": "REDUCE_BEFORE_STRATEGY_OR_FLATTEN_FAIL",
        "margin_exhausted_action": "FLATTEN_AND_STAGE_FAIL",
    }
    contract: Dict[str, Any] = {
        "$schema": "./" + _SCHEMA,
        "schema_version": "1.0.0",
        "contract_id": "challenger_replacement_simulation_contract_" + _ZERO_HASH,
        "contract_hash": _ZERO_HASH,
        "mode": "FIXTURE_ONLY_DETERMINISTIC_BINANCE_SIMULATION",
        "venue": "BINANCE_ONLY",
        "economic_asset": "ETH",
        "starting_virtual_equity_usdt": "100",
        "capital_limit_usdt": "100",
        "gross_exposure_limit": "0.5",
        "configured_leverage": "1",
        "technical_leverage_cap": "2",
        "fill_model": "DETERMINISTIC_IMMEDIATE_FULL_MARKET_FIXTURE",
        "market_order_slippage_per_side": "0.001",
        "spot_taker_fee": "0.0015",
        "perpetual_taker_fee": "0.0015",
        "protective_stop_distance": "0.02",
        "funding_source": "EXACT_FIXTURE_RATE_AT_SCHEDULED_BOUNDARY",
        "quote_quantum_usdt": "0.00000001",
        "plan": {
            "plan_id": _PLAN_ID,
            "plan_hash": _PLAN_HASH,
            "file_sha256": _PLAN_FILE_SHA256,
        },
        "policy_bindings": policy_bindings,
        "products": products,
        "accounting": accounting,
        "risk_rehearsal": risk,
        "authority": {
            "network_requests": 0,
            "account_requests": 0,
            "broker_requests": 0,
            "orders_submitted_to_venue": 0,
            "credentials_used": False,
            "production_state_writes": 0,
            "production_activation": False,
            "runtime_install_authorized": False,
            "replacement_start_authorized": False,
            "real_orders_allowed": False,
        },
        "status": "CONTRACT_FROZEN_FIXTURE_SIMULATION_NOT_STARTED",
        "warnings": list(_WARNINGS),
    }
    contract["contract_id"] = stable_id(
        "challenger_replacement_simulation_contract",
        {
            "plan": contract["plan"],
            "policy_bindings": policy_bindings,
            "mode": contract["mode"],
            "venue": contract["venue"],
            "economic_asset": contract["economic_asset"],
            "starting_virtual_equity_usdt": contract[
                "starting_virtual_equity_usdt"
            ],
            "capital_limit_usdt": contract["capital_limit_usdt"],
            "gross_exposure_limit": contract["gross_exposure_limit"],
            "configured_leverage": contract["configured_leverage"],
            "technical_leverage_cap": contract["technical_leverage_cap"],
            "fill_model": contract["fill_model"],
            "market_order_slippage_per_side": contract[
                "market_order_slippage_per_side"
            ],
            "spot_taker_fee": contract["spot_taker_fee"],
            "perpetual_taker_fee": contract["perpetual_taker_fee"],
            "protective_stop_distance": contract["protective_stop_distance"],
            "funding_source": contract["funding_source"],
            "quote_quantum_usdt": contract["quote_quantum_usdt"],
            "products": products,
            "accounting": accounting,
            "risk_rehearsal": risk,
        },
    )
    contract["contract_hash"] = artifact_self_hash(contract, "contract_hash")
    return contract


def _validate(document: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if (
        tuple(_validator().iter_errors(document))
        or dict(document) != dict(expected)
        or document.get("contract_hash")
        != artifact_self_hash(document, "contract_hash")
    ):
        _invalid()


def build_challenger_replacement_simulation_contract(*, plan):
    """Build the sole fixture-only contract without side effects."""

    if not _valid_plan(plan):
        _invalid()
    try:
        document = _document(plan)
        _validate(document, document)
        return copy.deepcopy(document)
    except ChallengerReplacementSimulationContractError:
        raise
    except (KeyError, TypeError, ValueError, CanonicalizationError) as error:
        raise ChallengerReplacementSimulationContractError(
            "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_INVALID"
        ) from error


def load_challenger_replacement_simulation_contract_bytes(data: bytes, *, plan):
    """Replay exact canonical contract bytes against the frozen v3 plan."""

    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        _invalid("CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID")
    if not _valid_plan(plan):
        _invalid()
    try:
        document = _strict_json_bytes(data)
        if not isinstance(document, Mapping):
            raise TypeError("contract must be an object")
        if data != canonical_json(document).encode("utf-8"):
            _invalid("CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID")
        expected = _document(plan)
        _validate(document, expected)
        return copy.deepcopy(dict(document))
    except ChallengerReplacementSimulationContractError:
        raise
    except (
        ChallengerReplacementPlanError,
        CanonicalizationError,
        KeyError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ChallengerReplacementSimulationContractError(
            "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID"
        ) from error
