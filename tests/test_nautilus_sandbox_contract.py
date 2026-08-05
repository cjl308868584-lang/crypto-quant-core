import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.canonical import stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.nautilus_sandbox_contract import (
    NautilusSandboxContractError,
    build_nautilus_current_reference,
    build_nautilus_sandbox_request,
    load_nautilus_sandbox_request,
    load_nautilus_sandbox_result,
)
from crypto_quant.nautilus_sandbox_dependency import (
    build_nautilus_sandbox_dependency_lock,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "nautilus-sandbox" / "ethusdt-4h-input-v1.json"
CURRENT_REFERENCE = (
    ROOT / "tests" / "fixtures" / "nautilus-sandbox" / "current-reference-v1.json"
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class NautilusSandboxContractTests(unittest.TestCase):
    def dependency_lock(self):
        return build_nautilus_sandbox_dependency_lock(workspace_root=ROOT)

    def fixture(self):
        return read_json(FIXTURE)

    def current_reference(self):
        return build_nautilus_current_reference(fixture=self.fixture())

    def test_fixture_is_exact_ethusdt_4h_offline_scope(self):
        fixture = self.fixture()
        self.assertEqual(fixture["instrument"]["instrument_id"], "ETHUSDT.BINANCE")
        self.assertEqual(fixture["instrument"]["interval"], "4h")
        self.assertEqual(fixture["instrument"]["price_precision"], 2)
        self.assertEqual(fixture["instrument"]["size_precision"], 4)
        self.assertEqual(fixture["instrument"]["tick_size"], "0.01")
        self.assertEqual(fixture["instrument"]["step_size"], "0.0001")
        self.assertEqual(fixture["instrument"]["minimum_quantity"], "0.0001")
        self.assertEqual(fixture["instrument"]["minimum_notional"], "10")
        self.assertEqual(fixture["costs"]["taker_fee_rate"], "0.0015")
        self.assertEqual(fixture["starting_cash"], "1000")
        self.assertEqual(
            [scenario["scenario_id"] for scenario in fixture["scenarios"]],
            [
                "IMMEDIATE_FULL_FILL",
                "PARTIAL_THEN_FULL_FILL",
                "BELOW_MINIMUM_REJECTION",
                "FRESH_PROCESS_REPLAY",
            ],
        )
        self.assertEqual(fixture["authority"]["market_request_count"], 0)
        self.assertFalse(fixture["authority"]["live_data_allowed"])

    def test_current_reference_freezes_directional_authorization(self):
        reference = self.current_reference()
        self.assertEqual(
            CURRENT_REFERENCE.read_bytes(),
            canonical_json(reference).encode("utf-8") + b"\n",
        )
        self.assertEqual(reference["authority"], "CURRENT_CORE_FACT_SOURCE")
        self.assertEqual(reference["decision"]["action"], "ENTER_LONG")
        self.assertEqual(reference["target"]["side"], "BUY")
        self.assertEqual(reference["risk_authorization"]["maximum_notional"], "40")
        self.assertEqual(reference["risk_authorization"]["maximum_position"], "0.02")
        self.assertFalse(reference["risk_authorization"]["override_allowed"])
        self.assertEqual(reference["runtime_counters"], {
            "network_request_count": 0,
            "credential_access_count": 0,
            "broker_request_count": 0,
            "real_order_count": 0,
            "production_state_write_count": 0,
        })

    def test_request_binds_exact_lock_fixture_and_reference(self):
        request = build_nautilus_sandbox_request(
            dependency_lock=self.dependency_lock(),
            fixture=self.fixture(),
            current_reference=self.current_reference(),
        )
        self.assertEqual(request["authority"], "CURRENT_CORE_TO_SANDBOX_ONE_WAY")
        self.assertEqual(request["engine_count"], 1)
        self.assertEqual(request["engine_api"], "LOW_LEVEL_BACKTEST_ENGINE")
        self.assertEqual(request["runtime_network_allowed"], False)
        self.assertEqual(request["live_adapter_allowed"], False)
        self.assertEqual(request["scenario_ids"], [
            "IMMEDIATE_FULL_FILL",
            "PARTIAL_THEN_FULL_FILL",
            "BELOW_MINIMUM_REJECTION",
            "FRESH_PROCESS_REPLAY",
        ])
        for name in (
            "dependency_lock_hash",
            "fixture_hash",
            "current_reference_hash",
            "request_hash",
        ):
            self.assertRegex(request[name], r"^[0-9a-f]{64}$")

    def test_schemas_are_mirrored_and_validate_request(self):
        request = build_nautilus_sandbox_request(
            dependency_lock=self.dependency_lock(),
            fixture=self.fixture(),
            current_reference=self.current_reference(),
        )
        for schema_name, payload in (
            ("nautilus-sandbox-request-v1.schema.json", request),
            ("nautilus-sandbox-result-v1.schema.json", self.valid_result(request)),
        ):
            config = ROOT / "config" / schema_name
            packaged = ROOT / "src" / "crypto_quant" / "schemas" / schema_name
            self.assertEqual(config.read_bytes(), packaged.read_bytes())
            schema = json.loads(config.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(payload)

    def valid_result(self, request):
        result = {
            "$schema": "./nautilus-sandbox-result-v1.schema.json",
            "schema_version": "1.0.0",
            "result_id": "nautilus_sandbox_result_" + "0" * 64,
            "result_hash": "0" * 64,
            "request_hash": request["request_hash"],
            "dependency_lock_hash": request["dependency_lock_hash"],
            "fixture_hash": request["fixture_hash"],
            "current_reference_hash": request["current_reference_hash"],
            "authority": "NON_AUTHORITATIVE_SANDBOX_OBSERVATION",
            "engine": {"name": "BacktestEngine", "count": 1, "version": "1.227.0"},
            "scenarios": [],
            "safety_counters": {
                "network_request_count": 0,
                "credential_access_count": 0,
                "live_broker_call_count": 0,
                "runtime_state_write_count": 0,
            },
            "status": "SANDBOX_OBSERVATION_COMPLETE",
        }
        result["result_id"] = stable_id(
            "nautilus_sandbox_result",
            {key: value for key, value in result.items() if key not in {"result_id", "result_hash"}},
        )
        result["result_hash"] = artifact_self_hash(result, "result_hash")
        return result

    def test_loaders_reject_unbound_or_unsafe_payloads(self):
        request = build_nautilus_sandbox_request(
            dependency_lock=self.dependency_lock(),
            fixture=self.fixture(),
            current_reference=self.current_reference(),
        )
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "request.json"
            path.write_text(canonical_json(request), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(load_nautilus_sandbox_request(path), request)

            changed = copy.deepcopy(request)
            changed["runtime_network_allowed"] = True
            path.write_text(canonical_json(changed), encoding="utf-8")
            with self.assertRaisesRegex(
                NautilusSandboxContractError, "SANDBOX_REQUEST_SCHEMA_INVALID"
            ):
                load_nautilus_sandbox_request(path)

            path.write_text(canonical_json(request), encoding="utf-8")
            path.chmod(0o622)
            with self.assertRaisesRegex(
                NautilusSandboxContractError, "SANDBOX_CONTRACT_UNSAFE_FILE"
            ):
                load_nautilus_sandbox_request(path)

    def test_result_loader_rejects_authority_or_counter_violation(self):
        request = build_nautilus_sandbox_request(
            dependency_lock=self.dependency_lock(),
            fixture=self.fixture(),
            current_reference=self.current_reference(),
        )
        result = self.valid_result(request)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "result.json"
            path.write_text(canonical_json(result), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(load_nautilus_sandbox_result(path), result)

            result["safety_counters"]["network_request_count"] = 1
            path.write_text(canonical_json(result), encoding="utf-8")
            with self.assertRaisesRegex(
                NautilusSandboxContractError, "SANDBOX_RESULT_SCHEMA_INVALID"
            ):
                load_nautilus_sandbox_result(path)


if __name__ == "__main__":
    unittest.main()
