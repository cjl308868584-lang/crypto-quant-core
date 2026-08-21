import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.nautilus_v065_contract import (
    NautilusV065ContractError,
    build_nautilus_v065_current_reference,
    build_nautilus_v065_request,
    load_nautilus_v065_request,
    load_nautilus_v065_result,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "nautilus-v065"
REQUEST_FIXTURE = FIXTURES / "ethusdt-4h-input-v2.json"
REFERENCE_FIXTURE = FIXTURES / "current-reference-v2.json"
REQUEST_SCHEMA = ROOT / "config" / "nautilus-sandbox-request-v2.schema.json"
RESULT_SCHEMA = ROOT / "config" / "nautilus-sandbox-result-v2.schema.json"


class NautilusV065ContractTests(unittest.TestCase):
    def request(self):
        return build_nautilus_v065_request(
            plan_id="nautilus_v065_plan_" + "1" * 64,
            plan_hash="2" * 64,
            supply_chain_receipt_id="nautilus_v065_supply_chain_" + "3" * 64,
            supply_chain_receipt_hash="4" * 64,
        )

    def test_request_freezes_market_instrument_authority_and_four_scenarios(self):
        request = self.request()
        self.assertEqual(len(request["closed_bars"]), 21)
        self.assertEqual(
            [bar["sequence"] for bar in request["closed_bars"]], list(range(1, 22))
        )
        self.assertEqual(
            request["instrument"],
            {
                "instrument_id": "BINANCE:SPOT:ETHUSDT",
                "symbol": "ETHUSDT",
                "base_asset": "ETH",
                "quote_asset": "USDT",
                "price_tick": "0.01",
                "quantity_step": "0.0001",
                "min_quantity": "0.0001",
                "min_notional": "5",
                "price_precision": 2,
                "quantity_precision": 4,
                "maker_fee": "0.001",
                "taker_fee": "0.001",
            },
        )
        self.assertEqual(
            [item["scenario"] for item in request["scenarios"]],
            ["IMMEDIATE_FULL", "PARTIAL_THEN_FULL", "BELOW_MINIMUM_REJECTED", "FRESH_PROCESS_REPLAY"],
        )
        self.assertEqual(request["starting_state"], {"cash_usdt": "1000", "position_eth": "0"})
        self.assertEqual(set(request["authority_counters"].values()), {0})
        self.assertEqual(request["decision_authority"]["risk"]["max_quantity"], "0.05")
        self.assertFalse(request["decision_authority"]["risk"]["short_allowed"])

    def test_every_market_event_is_append_ordered_hash_bound_and_decimal_only(self):
        request = self.request()
        for bar in request["closed_bars"]:
            self.assertRegex(bar["event_hash"], r"^[0-9a-f]{64}$")
            for field in ("open", "high", "low", "close", "volume"):
                self.assertIsInstance(bar[field], str)
        for scenario in request["scenarios"]:
            self.assertEqual(
                [event["sequence"] for event in scenario["events"]],
                list(range(1, len(scenario["events"]) + 1)),
            )
            for event in scenario["events"]:
                self.assertRegex(event["event_hash"], r"^[0-9a-f]{64}$")
        self.assertNotIn("url", canonical_json(request).lower())
        self.assertEqual(request["authority_counters"]["credential_reads"], 0)
        self.assertNotIn("fee", canonical_json(request["scenarios"]).lower())
        self.assertNotIn("pnl", canonical_json(request["scenarios"]).lower())

    def test_committed_fixtures_are_exact_canonical_builder_outputs(self):
        request = self.request()
        reference = build_nautilus_v065_current_reference(request=request)
        self.assertEqual(REQUEST_FIXTURE.read_bytes(), canonical_json(request).encode() + b"\n")
        self.assertEqual(REFERENCE_FIXTURE.read_bytes(), canonical_json(reference).encode() + b"\n")
        with tempfile.TemporaryDirectory() as raw:
            request_path = Path(raw) / "request.json"
            result_path = Path(raw) / "result.json"
            request_path.write_bytes(REQUEST_FIXTURE.read_bytes())
            result_path.write_bytes(REFERENCE_FIXTURE.read_bytes())
            request_path.chmod(0o600)
            result_path.chmod(0o600)
            self.assertEqual(load_nautilus_v065_request(request_path.resolve()), request)
            self.assertEqual(load_nautilus_v065_result(result_path.resolve()), reference)

    def test_request_rejects_override_float_unbound_decision_and_expanded_risk(self):
        request = self.request()
        mutations = []
        for key, value in (("url", "https://example.invalid"), ("credential", "secret"), ("production_path", "/Users/example/production")):
            changed = copy.deepcopy(request)
            changed[key] = value
            mutations.append(changed)
        changed = copy.deepcopy(request)
        changed["starting_state"]["cash_usdt"] = 1000.0
        mutations.append(changed)
        changed = copy.deepcopy(request)
        changed["decision_authority"]["target"]["decision_id"] = "decision_" + "0" * 64
        mutations.append(changed)
        changed = copy.deepcopy(request)
        changed["decision_authority"]["risk"]["max_quantity"] = "0.06"
        mutations.append(changed)
        for changed in mutations:
            with self.subTest():
                with tempfile.TemporaryDirectory() as raw:
                    path = Path(raw) / "request.json"
                    try:
                        body = canonical_json(changed)
                    except Exception:
                        body = json.dumps(changed, sort_keys=True, separators=(",", ":"))
                    path.write_bytes(body.encode() + b"\n")
                    path.chmod(0o600)
                    with self.assertRaises(NautilusV065ContractError):
                        load_nautilus_v065_request(path.resolve())

    def test_schemas_are_strict_mirrored_and_accept_only_frozen_contracts(self):
        for schema_path in (REQUEST_SCHEMA, RESULT_SCHEMA):
            package = ROOT / "src" / "crypto_quant" / "schemas" / schema_path.name
            self.assertEqual(schema_path.read_bytes(), package.read_bytes())
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        request_validator = Draft202012Validator(json.loads(REQUEST_SCHEMA.read_text()))
        result_validator = Draft202012Validator(json.loads(RESULT_SCHEMA.read_text()))
        self.assertEqual(list(request_validator.iter_errors(self.request())), [])
        self.assertEqual(
            list(result_validator.iter_errors(build_nautilus_v065_current_reference(request=self.request()))), []
        )
        extra = self.request()
        extra["live_venue_client"] = "BINANCE"
        self.assertNotEqual(list(request_validator.iter_errors(extra)), [])

    def test_builders_do_not_modify_existing_system_or_replacement_authority(self):
        roots = [ROOT / "artifacts" / "system-paper", ROOT / "artifacts" / "challenger-replacement"]
        def snapshot():
            return {
                str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                for root in roots
                for path in sorted(root.glob("*.json"))
            }
        before = snapshot()
        request = self.request()
        build_nautilus_v065_current_reference(request=request)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
