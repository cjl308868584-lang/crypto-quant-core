"""Pure v3 deployment trust document; no installation authority."""

import copy
import hashlib
import json
import plistlib
from functools import lru_cache
from importlib import resources
from typing import Mapping

from jsonschema import Draft202012Validator

from .canonical import business_hash, canonical_json, stable_id
from .challenger_replacement_accelerated_canary_plan import (
    build_challenger_replacement_accelerated_canary_plan,
)
from .challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from .challenger_replacement_plan import ChallengerReplacementPlanError, _strict_json_bytes
from .challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from .challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from .evidence import artifact_self_hash


_SCHEMA = "challenger-replacement-v3-deployment-v1.schema.json"
_RUNTIME = "/Users/chenm4/Library/Application Support/CryptoQuant/challenger-replacement-v1"
_SNAPSHOT = _RUNTIME + "/deployment/snapshot"
_CORE_MODULES = """__init__ build canonical contracts decimal_math economics errors
estimators evidence instruments ledger market_data market_data_cli offline_paper
operations_projection_v3 paired_risk paper_scheduler reevaluation runtime_health
statistical_decision statistics trade_replay challenger_replacement_accelerated_canary_plan
challenger_replacement_binance_lifecycle challenger_replacement_binance_simulation_input
challenger_replacement_decision challenger_replacement_deployment
challenger_replacement_economic_evaluation challenger_replacement_economic_evaluation_cli
challenger_replacement_economic_plan challenger_replacement_events
challenger_replacement_evidence challenger_replacement_fault_matrix
challenger_replacement_install_trust challenger_replacement_live_input
challenger_replacement_operational_qualification challenger_replacement_opportunities
challenger_replacement_opportunity_evidence challenger_replacement_opportunity_projection
challenger_replacement_plan challenger_replacement_plan_v2 challenger_replacement_plan_v3
challenger_replacement_public_http challenger_replacement_public_market_capture
challenger_replacement_public_simulation challenger_replacement_public_simulation_contract
challenger_replacement_runtime challenger_replacement_simulation
challenger_replacement_simulation_contract challenger_replacement_v3_deployment
challenger_replacement_v3_observer challenger_replacement_v3_runtime
challenger_replacement_v3_start""".split()
_CORE_RESOURCES = """schemas/challenger-replacement-public-market-capture-v2.schema.json
schemas/challenger-replacement-public-simulation-contract-v1.schema.json
schemas/challenger-replacement-public-simulation-input-v1.schema.json
schemas/challenger-replacement-public-simulation-snapshot-v1.schema.json
schemas/challenger-replacement-public-simulation-result-v1.schema.json
schemas/challenger-replacement-v3-deployment-v1.schema.json
schemas/challenger-replacement-v3-start-receipt-v1.schema.json
schemas/challenger-replacement-fault-matrix-receipt-v1.schema.json
schemas/challenger-replacement-operational-qualification-v1.schema.json
schemas/challenger-replacement-economic-evaluation-v1.schema.json
schemas/challenger-replacement-plan-v3.schema.json schemas/challenger-replacement-economic-evaluation-plan-v1.schema.json schemas/challenger-replacement-accelerated-canary-plan-v1.schema.json schemas/challenger-replacement-simulation-contract-v1.schema.json schemas/challenger-replacement-live-capture-v1.schema.json schemas/challenger-replacement-binance-simulation-input-v1.schema.json schemas/challenger-replacement-opportunity-result-evidence-v2.schema.json
schemas/challenger-replacement-plan-v1.schema.json schemas/challenger-replacement-plan-v2.schema.json artifacts/challenger-replacement/challenger-replacement-plan-v0.62.0.json
schemas/operations-projection-v3.schema.json
fixtures/challenger-replacement-v076/binance-lifecycle-long-input.json""".split()
_CORE_PATHS = {"src/crypto_quant/" + name + ".py" for name in _CORE_MODULES} | {
    (name if name.startswith("artifacts/") else "src/crypto_quant/" + name)
    for name in _CORE_RESOURCES
}
_PREDECESSOR = {
    "repository": "cjl308868584-lang/crypto-quant-core",
    "visibility": "PUBLIC",
    "release_tag": "v0.75.0",
    "tag_object": "4bd4b2e21c760d6fad2a27903c67ee509ac116c9",
    "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
    "package_version": "0.75.0",
    "manifest_version": "1.69.0",
    "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
    "manifest_file_sha256": "df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220",
    "build_input_tree_hash": "07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78",
    "main_ci_run": 32869868571,
}


class ChallengerReplacementV3DeploymentError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _invalid(reason="CHALLENGER_REPLACEMENT_V3_DEPLOYMENT_INVALID"):
    raise ChallengerReplacementV3DeploymentError(reason)


@lru_cache(maxsize=1)
def _validator():
    schema = json.loads(resources.files("crypto_quant").joinpath(
        "schemas", _SCHEMA
    ).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _inputs(
    predecessor_release, plan, economic_plan, accelerated_plan,
    predecessor_contract, public_contract, build_identity, strategy_inventory
):
    hashes = set("0123456789abcdef")
    if (
        not isinstance(strategy_inventory, Mapping)
        or set(strategy_inventory) != _CORE_PATHS
        or any(
            not isinstance(value, str) or len(value) != 64 or set(value) - hashes
            for value in strategy_inventory.values()
        )
    ):
        _invalid()
    inventory_hash = business_hash(dict(sorted(strategy_inventory.items())))
    if (
        predecessor_release != _PREDECESSOR
        or economic_plan != build_challenger_replacement_economic_plan()
        or accelerated_plan != build_challenger_replacement_accelerated_canary_plan()
        or predecessor_contract
        != build_challenger_replacement_simulation_contract(plan=plan)
        or public_contract
        != build_challenger_replacement_public_simulation_contract(
            plan=plan, economic_plan=economic_plan,
            predecessor_contract=predecessor_contract,
        )
        or not isinstance(build_identity, Mapping)
        or set(build_identity) != {
            "reviewed_code_checkpoint", "package_version",
            "predecessor_manifest_identity", "executable_core_hash",
        }
        or build_identity.get("package_version") != "0.76.0"
        or build_identity.get("predecessor_manifest_identity") != _PREDECESSOR
        or not isinstance(build_identity.get("reviewed_code_checkpoint"), str)
        or len(build_identity["reviewed_code_checkpoint"]) != 40
        or set(build_identity["reviewed_code_checkpoint"]) - hashes
        or build_identity.get("executable_core_hash")
        != inventory_hash
    ):
        _invalid()


def _plist_payload(deployment):
    return {
        "Label": deployment["service"]["label"],
        "ProgramArguments": deployment["runtime"]["program_arguments"],
        "WorkingDirectory": deployment["paths"]["snapshot_root"],
        "StandardOutPath": deployment["paths"]["stdout"],
        "StandardErrorPath": deployment["paths"]["stderr"],
        "RunAtLoad": False, "KeepAlive": False,
        "ProcessType": "Background", "Umask": 0o077,
        "EnvironmentVariables": {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONPATH": deployment["paths"]["snapshot_root"] + "/src",
        },
        "StartCalendarInterval": [
            {"Hour": item["hour"], "Minute": item["minute"]}
            for item in deployment["schedule"]
        ],
    }


def render_challenger_replacement_v3_plist(deployment):
    return plistlib.dumps(
        _plist_payload(deployment), fmt=plistlib.FMT_XML, sort_keys=True
    )


def _document(
    *, predecessor_release, plan, economic_plan, accelerated_plan,
    predecessor_contract, public_contract, build_identity, strategy_inventory
):
    _inputs(
        predecessor_release, plan, economic_plan, accelerated_plan,
        predecessor_contract, public_contract, build_identity, strategy_inventory
    )
    paths = {
        "runtime_root": _RUNTIME,
        "event_root": _RUNTIME + "/state/challenger-replacement-events-v1",
        "stdout": _RUNTIME + "/log/challenger-replacement-v3.stdout.log",
        "stderr": _RUNTIME + "/log/challenger-replacement-v3.stderr.log",
        "snapshot_root": _SNAPSHOT,
        "python": _SNAPSHOT + "/bin/python3",
        "target_plist": "/Users/chenm4/Library/LaunchAgents/local.crypto-quant.challenger-replacement-v1.plist",
    }
    document = {
        "$schema": "./" + _SCHEMA, "schema_version": "1.0.0",
        "deployment_id": "", "deployment_hash": "0" * 64,
        "predecessor_release": copy.deepcopy(_PREDECESSOR),
        "plans": {
            "v069": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
            "v074": {"plan_id": economic_plan["plan_id"], "plan_hash": economic_plan["plan_hash"]},
            "v075": {"plan_id": accelerated_plan["plan_id"], "plan_hash": accelerated_plan["plan_hash"]},
        },
        "contracts": {
            "predecessor": {"contract_id": predecessor_contract["contract_id"], "contract_hash": predecessor_contract["contract_hash"]},
            "public": {"contract_id": public_contract["contract_id"], "contract_hash": public_contract["contract_hash"]},
        },
        "candidate_build": copy.deepcopy(dict(build_identity)),
        "executable_core_identity": dict(sorted(strategy_inventory.items())),
        "executable_core_hash": business_hash(dict(sorted(strategy_inventory.items()))),
        "service": {"label": "local.crypto-quant.challenger-replacement-v1", "identity": "gui/501/local.crypto-quant.challenger-replacement-v1"},
        "paths": paths,
        "runtime": {"module": "crypto_quant.challenger_replacement_v3_runtime", "program_arguments": [paths["python"], "-m", "crypto_quant.challenger_replacement_v3_runtime"]},
        "schedule": [{"hour": hour, "minute": 2} for hour in (0, 4, 8, 12, 16, 20)],
        "authority": {
            "production_activation": False, "runtime_install_authorized": False,
            "replacement_start_authorized": False, "credentials_allowed": False,
            "account_requests_allowed": False, "real_orders_allowed": False,
            "fund_movement_allowed": False,
        },
        "plist_sha256": "0" * 64,
        "status": "V3_DEPLOYMENT_CANDIDATE_NOT_INSTALLABLE_NOT_ACTIVATED",
    }
    document["plist_sha256"] = hashlib.sha256(
        render_challenger_replacement_v3_plist(document)
    ).hexdigest()
    identity = {key: value for key, value in document.items() if key not in {
        "$schema", "schema_version", "deployment_id", "deployment_hash"
    }}
    document["deployment_id"] = stable_id(
        "challenger_replacement_v3_deployment", identity
    )
    document["deployment_hash"] = artifact_self_hash(document, "deployment_hash")
    if tuple(_validator().iter_errors(document)):
        _invalid()
    return document


def build_challenger_replacement_v3_deployment(**kwargs):
    return copy.deepcopy(_document(**kwargs))


def load_challenger_replacement_v3_deployment_bytes(data, **kwargs):
    if not isinstance(data, bytes) or not 0 < len(data) <= 262_144:
        _invalid("CHALLENGER_REPLACEMENT_V3_DEPLOYMENT_BYTES_INVALID")
    try:
        value = _strict_json_bytes(data)
        expected = _document(**kwargs)
        if data != canonical_json(value).encode("utf-8") or value != expected:
            _invalid()
        return copy.deepcopy(value)
    except ChallengerReplacementV3DeploymentError:
        raise
    except (ChallengerReplacementPlanError, TypeError, ValueError) as error:
        raise ChallengerReplacementV3DeploymentError(
            "CHALLENGER_REPLACEMENT_V3_DEPLOYMENT_BYTES_INVALID"
        ) from error
