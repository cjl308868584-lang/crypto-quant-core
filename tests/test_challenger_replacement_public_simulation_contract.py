import unittest
from copy import deepcopy

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    ChallengerReplacementPublicSimulationContractError,
    build_challenger_replacement_public_simulation_contract,
    load_challenger_replacement_public_simulation_contract_bytes,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.evidence import artifact_self_hash
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan


class PublicSimulationContractTests(unittest.TestCase):
    def setUp(self):
        self.plan = fixture_v3_plan()
        self.economic_plan = build_challenger_replacement_economic_plan()
        self.predecessor = build_challenger_replacement_simulation_contract(
            plan=self.plan
        )

    def _build(self):
        return build_challenger_replacement_public_simulation_contract(
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
        )

    def _load(self, document):
        return load_challenger_replacement_public_simulation_contract_bytes(
            canonical_json(document).encode("utf-8"),
            plan=self.plan,
            economic_plan=self.economic_plan,
            predecessor_contract=self.predecessor,
        )

    def test_contract_freezes_public_profile_costs_risk_and_predecessors(self):
        contract = self._build()

        self.assertEqual(contract["public_profile"], {
            "mode": "PUBLIC_MARKET_DETERMINISTIC_BINANCE_SIMULATION",
            "fill_model": "DETERMINISTIC_IMMEDIATE_FULL_MARKET_MODEL",
            "funding_source": "EXACT_PUBLIC_FUNDING_RECORDS_IN_OPPORTUNITY_INTERVAL",
            "protective_stop_status": "CONFIRMED_SIMULATED",
        })
        self.assertEqual(contract["model"], {
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
        })
        self.assertEqual(
            contract["economic_plan"]["accounting_policy_hash"],
            "844901a2fcadb5d1405bf4cf504bf84a42cacab7ec91b3ad4a4516a5f96ff42b",
        )
        self.assertEqual(contract["predecessor_contract"], {
            "contract_id": self.predecessor["contract_id"],
            "contract_hash": self.predecessor["contract_hash"],
            "file_sha256": "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
        })
        self.assertEqual(contract["authority"], {
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
        })
        self.assertEqual(self._load(contract), contract)

    def test_rehashed_economic_label_and_authority_changes_are_rejected(self):
        for path, value in (
            (("model", "gross_exposure_limit"), "1"),
            (("public_profile", "protective_stop_status"), "CONFIRMED_FIXTURE"),
            (("authority", "real_orders_allowed"), True),
            (("economic_plan", "accounting_policy_hash"), "0" * 64),
        ):
            contract = self._build()
            contract[path[0]][path[1]] = value
            contract["contract_hash"] = artifact_self_hash(
                contract, "contract_hash"
            )
            with self.subTest(path=path), self.assertRaises(
                ChallengerReplacementPublicSimulationContractError
            ):
                self._load(contract)

    def test_fixture_contract_cannot_be_substituted_for_public_contract(self):
        with self.assertRaises(ChallengerReplacementPublicSimulationContractError):
            load_challenger_replacement_public_simulation_contract_bytes(
                canonical_json(self.predecessor).encode("utf-8"),
                plan=self.plan,
                economic_plan=self.economic_plan,
                predecessor_contract=self.predecessor,
            )


if __name__ == "__main__":
    unittest.main()
