import hashlib
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
    load_challenger_replacement_simulation_contract_bytes,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / (
    "artifacts/challenger-replacement/"
    "challenger-replacement-binance-simulation-contract-v0.71.0.json"
)
EXPECTED_AUTHORITY = {
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


class ChallengerReplacementV071ArtifactTests(unittest.TestCase):
    def test_formal_contract_is_exact_canonical_builder_output(self):
        plan = fixture_v3_plan()
        body = CONTRACT_PATH.read_bytes()
        expected = build_challenger_replacement_simulation_contract(plan=plan)
        self.assertEqual(body, canonical_json(expected).encode("utf-8"))
        self.assertEqual(
            load_challenger_replacement_simulation_contract_bytes(body, plan=plan),
            expected,
        )
        self.assertEqual(expected["authority"], EXPECTED_AUTHORITY)
        self.assertEqual(
            hashlib.sha256(body).hexdigest(),
            "65a0af1cccee5ad60aeaa7b0266bb217fab680d866ea3191ca77d214a292d86f",
        )
        for forbidden in (
            b'"release_tag"', b'"peeled_commit"', b'"ci_run"',
            b'"runtime_identity"', b'"account_identity"', b'"credential"',
            b'"order_identity"',
        ):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
