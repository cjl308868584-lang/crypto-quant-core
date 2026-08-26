"""Pure, fixture-free contract for deterministic public-market simulation."""

import copy
import json
from functools import lru_cache
from importlib import resources
from typing import Mapping

from jsonschema import Draft202012Validator

from .canonical import canonical_json, stable_id
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_plan import (
    ChallengerReplacementPlanError,
    _strict_json_bytes,
)
from .challenger_replacement_plan_v3 import challenger_replacement_plan_v3_reasons
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-public-simulation-contract-v1.schema.json"
_MAX_BYTES = 65_536
_PUBLIC_PROFILE = {
    "mode": "PUBLIC_MARKET_DETERMINISTIC_BINANCE_SIMULATION",
    "fill_model": "DETERMINISTIC_IMMEDIATE_FULL_MARKET_MODEL",
    "funding_source": "EXACT_PUBLIC_FUNDING_RECORDS_IN_OPPORTUNITY_INTERVAL",
    "protective_stop_status": "CONFIRMED_SIMULATED",
}
_MODEL = {
    "starting_virtual_equity_usdt": "100",
    "capital_limit_usdt": "100",
    "gross_exposure_limit": "0.5",
    "configured_leverage": "1",
    "technical_leverage_cap": "2",
    "contract_multiplier": "1",
    "market_order_slippage_per_side": "0.001",
    "spot_taker_fee": "0.0015",
    "perpetual_taker_fee": "0.0015",
    "protective_stop_distance": "0.02",
    "quote_quantum_usdt": "0.00000001",
}
_AUTHORITY = {
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
}


class ChallengerReplacementPublicSimulationContractError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="PUBLIC_SIMULATION_CONTRACT_INVALID"):
    raise ChallengerReplacementPublicSimulationContractError(reason)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _bindings(plan, economic_plan, predecessor_contract):
    if (
        not isinstance(plan, Mapping)
        or challenger_replacement_plan_v3_reasons(plan)
        or economic_plan != build_challenger_replacement_economic_plan()
        or predecessor_contract
        != build_challenger_replacement_simulation_contract(plan=plan)
    ):
        _invalid()
    foundation = economic_plan["foundation"]["v071_simulation_contract"]
    predecessor = {
        "contract_id": predecessor_contract["contract_id"],
        "contract_hash": predecessor_contract["contract_hash"],
        "file_sha256": foundation["file_sha256"],
    }
    if predecessor != foundation:
        _invalid()
    return predecessor


def _document(plan, economic_plan, predecessor_contract):
    predecessor = _bindings(plan, economic_plan, predecessor_contract)
    document = {
        "$schema": "./" + _SCHEMA,
        "schema_version": "1.0.0",
        "contract_id": "",
        "contract_hash": "0" * 64,
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "economic_plan": {
            "plan_id": economic_plan["plan_id"],
            "plan_hash": economic_plan["plan_hash"],
            "accounting_policy_hash": economic_plan["economic_measurement"][
                "policy_hash"
            ],
        },
        "predecessor_contract": predecessor,
        "public_profile": copy.deepcopy(_PUBLIC_PROFILE),
        "model": copy.deepcopy(_MODEL),
        "authority": copy.deepcopy(_AUTHORITY),
        "status": "PUBLIC_SIMULATION_CONTRACT_FROZEN_NOT_ACTIVATED",
        "warnings": [
            "MODEL_COSTS_ARE_NOT_ACCOUNT_OR_VENUE_OBSERVATIONS",
            "SIMULATED_FILL_IS_NOT_A_BINANCE_FILL_CLAIM",
            "NO_PROFITABILITY_OR_CANARY_ELIGIBILITY",
        ],
    }
    identity = {
        "plan": document["plan"],
        "economic_plan": document["economic_plan"],
        "predecessor_contract": predecessor,
        "public_profile": document["public_profile"],
        "model": document["model"],
    }
    document["contract_id"] = stable_id(
        "challenger_replacement_public_simulation_contract", identity
    )
    document["contract_hash"] = artifact_self_hash(document, "contract_hash")
    return document


def build_challenger_replacement_public_simulation_contract(
    *, plan, economic_plan, predecessor_contract
):
    document = _document(plan, economic_plan, predecessor_contract)
    if tuple(_validator().iter_errors(document)):
        _invalid()
    return copy.deepcopy(document)


def load_challenger_replacement_public_simulation_contract_bytes(
    data, *, plan, economic_plan, predecessor_contract
):
    if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_BYTES:
        _invalid("PUBLIC_SIMULATION_CONTRACT_BYTES_INVALID")
    try:
        document = _strict_json_bytes(data)
        if data != canonical_json(document).encode("utf-8"):
            _invalid("PUBLIC_SIMULATION_CONTRACT_BYTES_INVALID")
        expected = _document(plan, economic_plan, predecessor_contract)
        if (
            tuple(_validator().iter_errors(document))
            or document != expected
            or document["contract_hash"]
            != artifact_self_hash(document, "contract_hash")
        ):
            _invalid()
        return copy.deepcopy(dict(document))
    except ChallengerReplacementPublicSimulationContractError:
        raise
    except (ChallengerReplacementPlanError, KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementPublicSimulationContractError(
            "PUBLIC_SIMULATION_CONTRACT_BYTES_INVALID"
        ) from error
