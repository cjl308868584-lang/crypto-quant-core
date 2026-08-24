import copy
import json
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_simulation_contract import (
    ChallengerReplacementSimulationContractError,
    build_challenger_replacement_simulation_contract,
    load_challenger_replacement_simulation_contract_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = ROOT / (
    "config/challenger-replacement-simulation-contract-v1.schema.json"
)
PACKAGE_SCHEMA = ROOT / (
    "src/crypto_quant/schemas/"
    "challenger-replacement-simulation-contract-v1.schema.json"
)
PLAN_FILE_SHA256 = (
    "6fae2ae0df4b8402ddc1df1b5bca611e11df41eee8d42f591d5d7b5fb24a31c3"
)


class ChallengerReplacementSimulationContractTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()

    def contract(self):
        return build_challenger_replacement_simulation_contract(plan=self.plan)

    def canonical_bytes(self, value):
        return canonical_json(value).encode("utf-8")

    def test_schema_mirror_is_exact_and_valid_contract_round_trips(self):
        self.assertEqual(CONFIG_SCHEMA.read_bytes(), PACKAGE_SCHEMA.read_bytes())
        contract = self.contract()
        encoded = self.canonical_bytes(contract)
        self.assertEqual(
            load_challenger_replacement_simulation_contract_bytes(
                encoded, plan=self.plan
            ),
            contract,
        )
        self.assertEqual(
            contract["contract_hash"],
            artifact_self_hash(contract, "contract_hash"),
        )
        self.assertEqual(
            contract["contract_id"],
            "challenger_replacement_simulation_contract_"
            "c95cee71f23e58cf40bc4739e5063824de1a77fd5c6fcc72794ff42e1f84f791",
        )

    def test_contract_freezes_exact_fixture_only_assumptions(self):
        contract = self.contract()
        self.assertEqual(
            set(contract),
            {
                "$schema",
                "schema_version",
                "contract_id",
                "contract_hash",
                "mode",
                "venue",
                "economic_asset",
                "starting_virtual_equity_usdt",
                "capital_limit_usdt",
                "gross_exposure_limit",
                "configured_leverage",
                "technical_leverage_cap",
                "fill_model",
                "market_order_slippage_per_side",
                "spot_taker_fee",
                "perpetual_taker_fee",
                "protective_stop_distance",
                "funding_source",
                "quote_quantum_usdt",
                "plan",
                "policy_bindings",
                "products",
                "accounting",
                "risk_rehearsal",
                "authority",
                "status",
                "warnings",
            },
        )
        self.assertEqual(
            contract["plan"],
            {
                "plan_id": self.plan["plan_id"],
                "plan_hash": self.plan["plan_hash"],
                "file_sha256": PLAN_FILE_SHA256,
            },
        )
        self.assertEqual(
            contract["mode"],
            "FIXTURE_ONLY_DETERMINISTIC_BINANCE_SIMULATION",
        )
        self.assertEqual(contract["venue"], "BINANCE_ONLY")
        self.assertEqual(contract["economic_asset"], "ETH")
        self.assertEqual(contract["starting_virtual_equity_usdt"], "100")
        self.assertEqual(contract["capital_limit_usdt"], "100")
        self.assertEqual(contract["gross_exposure_limit"], "0.5")
        self.assertEqual(contract["configured_leverage"], "1")
        self.assertEqual(contract["technical_leverage_cap"], "2")
        self.assertEqual(
            {
                key: contract[key]
                for key in (
                    "fill_model",
                    "market_order_slippage_per_side",
                    "spot_taker_fee",
                    "perpetual_taker_fee",
                    "protective_stop_distance",
                    "funding_source",
                    "quote_quantum_usdt",
                )
            },
            {
                "fill_model": "DETERMINISTIC_IMMEDIATE_FULL_MARKET_FIXTURE",
                "market_order_slippage_per_side": "0.001",
                "spot_taker_fee": "0.0015",
                "perpetual_taker_fee": "0.0015",
                "protective_stop_distance": "0.02",
                "funding_source": "EXACT_FIXTURE_RATE_AT_SCHEDULED_BOUNDARY",
                "quote_quantum_usdt": "0.00000001",
            },
        )
        self.assertEqual(
            contract["products"],
            {
                "spot_instrument": "BINANCE:SPOT:ETHUSDT",
                "spot_direction": "LONG_ONLY_UNMARGINED",
                "perpetual_instrument": "BINANCE:USDT_PERP:ETHUSDT",
                "perpetual_direction": "SHORT_ONLY",
                "products_mutually_exclusive": True,
                "perpetual_position_mode": "ONE_WAY",
                "perpetual_margin_mode": "ISOLATED",
            },
        )
        self.assertEqual(
            contract["authority"],
            {
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
        )
        self.assertEqual(
            contract["status"],
            "CONTRACT_FROZEN_FIXTURE_SIMULATION_NOT_STARTED",
        )

    def test_policy_bindings_are_exact_v3_hashes(self):
        contract = self.contract()
        self.assertEqual(
            contract["policy_bindings"],
            {
                "decision_policy_hash": self.plan["decision_policy"][
                    "policy_hash"
                ],
                "opportunity_policy_hash": self.plan["opportunity_policy"][
                    "policy_hash"
                ],
                "product_policy_hash": self.plan["product_policy"][
                    "policy_hash"
                ],
                "risk_policy_hash": self.plan["risk_policy"]["policy_hash"],
                "storage_authority_policy_hash": self.plan[
                    "storage_authority"
                ]["policy_hash"],
            },
        )

    def test_builder_is_deterministic_and_does_not_embed_release_identity(self):
        values = [self.contract() for _ in range(20)]
        self.assertTrue(all(value == values[0] for value in values))
        encoded = self.canonical_bytes(values[0])
        for forbidden in (
            b'"release_tag"',
            b'"peeled_commit"',
            b'"manifest_hash"',
            b'"ci_run"',
        ):
            self.assertNotIn(forbidden, encoded)

    def test_loader_rejects_noncanonical_or_unbounded_bytes(self):
        encoded = self.canonical_bytes(self.contract())
        for malformed in (
            b"",
            encoded + b"\n",
            b" " + encoded,
            b"{" + (b" " * 65_536) + b"}",
            b"[]",
            b"not-json",
        ):
            with self.subTest(size=len(malformed)):
                with self.assertRaisesRegex(
                    ChallengerReplacementSimulationContractError,
                    "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID",
                ):
                    load_challenger_replacement_simulation_contract_bytes(
                        malformed, plan=self.plan
                    )

    def test_loader_rejects_semantic_tampering_and_unknown_fields(self):
        cases = []
        changed_fee = self.contract()
        changed_fee["spot_taker_fee"] = "0.001"
        cases.append(changed_fee)
        changed_plan = self.contract()
        changed_plan["plan"]["plan_hash"] = "0" * 64
        cases.append(changed_plan)
        extra_release = self.contract()
        extra_release["release_tag"] = "v0.71.0"
        cases.append(extra_release)
        removed_authority = self.contract()
        del removed_authority["authority"]["real_orders_allowed"]
        cases.append(removed_authority)
        for changed in cases:
            changed["contract_hash"] = artifact_self_hash(
                changed, "contract_hash"
            )
            with self.subTest(keys=tuple(changed)):
                with self.assertRaisesRegex(
                    ChallengerReplacementSimulationContractError,
                    "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_INVALID",
                ):
                    load_challenger_replacement_simulation_contract_bytes(
                        self.canonical_bytes(changed), plan=self.plan
                    )

        float_value = self.contract()
        float_value["gross_exposure_limit"] = 0.5
        float_bytes = json.dumps(
            float_value, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationContractError,
            "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID",
        ):
            load_challenger_replacement_simulation_contract_bytes(
                float_bytes, plan=self.plan
            )

    def test_loader_rejects_different_expected_plan(self):
        changed_plan = copy.deepcopy(self.plan)
        changed_plan["plan_hash"] = "0" * 64
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationContractError,
            "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_INVALID",
        ):
            load_challenger_replacement_simulation_contract_bytes(
                self.canonical_bytes(self.contract()), plan=changed_plan
            )

    def test_schema_rejects_duplicate_json_keys(self):
        encoded = self.canonical_bytes(self.contract())
        parsed = json.loads(encoded)
        duplicate = (
            '{"schema_version":"1.0.0","schema_version":"1.0.0",'
            '"contract_id":"%s"}' % parsed["contract_id"]
        ).encode("utf-8")
        with self.assertRaisesRegex(
            ChallengerReplacementSimulationContractError,
            "CHALLENGER_REPLACEMENT_SIMULATION_CONTRACT_BYTES_INVALID",
        ):
            load_challenger_replacement_simulation_contract_bytes(
                duplicate, plan=self.plan
            )


if __name__ == "__main__":
    unittest.main()
