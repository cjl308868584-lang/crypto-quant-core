import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.challenger_replacement_binance_simulation_input import (
    load_challenger_replacement_binance_simulation_input_bytes,
)
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_fixture_simulation import (
    run_challenger_replacement_fixture_simulation_opportunity,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.challenger_replacement_opportunity_evidence import (
    load_challenger_replacement_simulation_result_evidence_bytes,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import (
    fixture_v072_build_identity,
    fixture_v072_golden_streams,
    fixture_v3_plan,
)
from tests.test_challenger_replacement_events import EventWorkspace


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/challenger_replacement_v072"
SCHEMA_PATH = ROOT / "config/challenger-replacement-binance-golden-fixture-manifest-v1.schema.json"
MANIFEST_PATH = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-binance-golden-fixture-manifest-v0.72.0.json"
)
RELATIVE_PATHS = (
    "spot-cycle/01-input.json", "spot-cycle/02-result.json",
    "spot-cycle/03-input.json", "spot-cycle/04-result.json",
    "spot-cycle/05-input.json", "spot-cycle/06-result.json",
    "perp-cycle/01-input.json", "perp-cycle/02-result.json",
    "perp-cycle/03-input.json", "perp-cycle/04-result.json",
    "perp-cycle/05-input.json", "perp-cycle/06-result.json",
    "perp-cycle/07-input.json", "perp-cycle/08-result.json",
)
AUTHORITY = {
    "network_requests": 0, "account_requests": 0, "broker_requests": 0,
    "orders_submitted_to_venue": 0, "credentials_used": False,
    "production_state_writes": 0, "production_activation": False,
    "runtime_install_authorized": False, "replacement_start_authorized": False,
    "real_orders_allowed": False,
}


def _expected_inventory():
    return [
        {
            "path": relative,
            "stream": relative.split("/")[0],
            "ordinal": index + 1,
            "kind": "INPUT" if "input" in relative else "RESULT",
            "size": (FIXTURE_ROOT / relative).stat().st_size,
            "sha256": hashlib.sha256((FIXTURE_ROOT / relative).read_bytes()).hexdigest(),
        }
        for index, relative in enumerate(RELATIVE_PATHS)
    ]


def _validate_manifest(document):
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    if tuple(Draft202012Validator(schema).iter_errors(document)):
        raise ValueError("schema")
    plan = fixture_v3_plan()
    contract = build_challenger_replacement_simulation_contract(plan=plan)
    expected = {
        "$schema": "./challenger-replacement-binance-golden-fixture-manifest-v1.schema.json",
        "schema_version": "1.0.0",
        "manifest_id": document["manifest_id"],
        "manifest_hash": document["manifest_hash"],
        "evidence_qualification": "COMMITTED_FIXTURE_NOT_LIVE_MARKET_OR_ACCOUNT",
        "plan": {"plan_id": plan["plan_id"], "plan_hash": plan["plan_hash"]},
        "simulation_contract": {
            "contract_id": contract["contract_id"],
            "contract_hash": contract["contract_hash"],
        },
        "build_identity": fixture_v072_build_identity(),
        "inventory": _expected_inventory(),
        "authority": AUTHORITY,
    }
    identity = {key: expected[key] for key in (
        "plan", "simulation_contract", "build_identity", "inventory"
    )}
    expected["manifest_id"] = stable_id(
        "challenger_replacement_binance_golden_fixture_manifest", identity
    )
    expected["manifest_hash"] = artifact_self_hash(expected, "manifest_hash")
    if document != expected:
        raise ValueError("identity")
    return copy.deepcopy(document)


class ChallengerReplacementV072ArtifactTests(unittest.TestCase):
    def test_exact_fixture_paths_schema_and_manifest_exist(self):
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertTrue(MANIFEST_PATH.is_file())
        self.assertEqual(
            tuple(sorted(str(path.relative_to(FIXTURE_ROOT)) for path in FIXTURE_ROOT.rglob("*.json"))),
            tuple(sorted(RELATIVE_PATHS)),
        )

    def test_manifest_is_exact_canonical_and_replays_all_documents(self):
        body = MANIFEST_PATH.read_bytes()
        document = _validate_manifest(json.loads(body))
        self.assertEqual(body, canonical_json(document).encode("utf-8"))
        plan = fixture_v3_plan()
        contract = build_challenger_replacement_simulation_contract(plan=plan)
        build = fixture_v072_build_identity()
        for relative in RELATIVE_PATHS:
            data = (FIXTURE_ROOT / relative).read_bytes()
            if "input" in relative:
                source = json.loads(data)
                loaded = load_challenger_replacement_binance_simulation_input_bytes(
                    data,
                    plan=plan,
                    contract=contract,
                    build_identity=build,
                    opportunity_id=source["opportunity"]["opportunity_id"],
                )
            else:
                loaded = load_challenger_replacement_simulation_result_evidence_bytes(
                    data, plan=plan, contract=contract, build_identity=build
                )
            self.assertEqual(data, canonical_json(loaded).encode("utf-8"))

    def test_manifest_rejects_path_order_hash_contract_and_unknown_mutations(self):
        original = json.loads(MANIFEST_PATH.read_bytes())
        mutations = []
        wrong_order = copy.deepcopy(original)
        wrong_order["inventory"][0], wrong_order["inventory"][1] = (
            wrong_order["inventory"][1], wrong_order["inventory"][0]
        )
        mutations.append(wrong_order)
        for key, value in (
            ("path", "wrong.json"), ("sha256", "0" * 64), ("size", 1)
        ):
            changed = copy.deepcopy(original); changed["inventory"][0][key] = value
            mutations.append(changed)
        contract = copy.deepcopy(original)
        contract["simulation_contract"]["contract_hash"] = "0" * 64
        mutations.append(contract)
        unknown = copy.deepcopy(original); unknown["unknown"] = True
        mutations.append(unknown)
        for document in mutations:
            with self.assertRaises(ValueError):
                _validate_manifest(document)

    def test_fresh_roots_reproduce_complete_cycle_result_bytes(self):
        expected_actions = {
            "spot-cycle": ("OPEN_SPOT_LONG", "HOLD_SPOT_LONG", "CLOSE_SPOT_LONG"),
            "perp-cycle": (
                "OPEN_PERP_SHORT", "HOLD_PERP_SHORT", "HOLD_PERP_SHORT",
                "CLOSE_PERP_SHORT",
            ),
        }
        for stream, inputs in fixture_v072_golden_streams().items():
            with self.subTest(stream=stream):
                workspace = EventWorkspace()
                try:
                    with open_challenger_replacement_event_root(
                        workspace.identity()
                    ) as root:
                        state = ChallengerReplacementOpportunityState(
                            event_root=root,
                            plan=fixture_v3_plan(),
                            build_identity=fixture_v072_build_identity(),
                        )
                        actions = []
                        for index, input_bytes in enumerate(inputs):
                            self.assertEqual(
                                input_bytes,
                                (FIXTURE_ROOT / stream / f"{index * 2 + 1:02d}-input.json").read_bytes(),
                            )
                            result = run_challenger_replacement_fixture_simulation_opportunity(
                                state=state,
                                input_bytes=input_bytes,
                                worker_id="golden-fixture-worker",
                            )
                            result_bytes = canonical_json(result).encode("utf-8")
                            self.assertEqual(
                                result_bytes,
                                (FIXTURE_ROOT / stream / f"{index * 2 + 2:02d}-result.json").read_bytes(),
                            )
                            actions.append(result["decision"]["action"])
                        self.assertEqual(tuple(actions), expected_actions[stream])
                        self.assertEqual(
                            state.replay()["latest_next_snapshot_or_null"]["position_state"],
                            "FLAT",
                        )
                finally:
                    workspace.close()


if __name__ == "__main__":
    unittest.main()
