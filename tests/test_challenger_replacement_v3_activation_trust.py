import json
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json


ROOT = Path(__file__).resolve().parents[1]


class ChallengerReplacementV3ActivationTrustTests(unittest.TestCase):
    def test_fixed_candidate_binds_releases_and_excludes_private_execution(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            build_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        self.assertEqual(candidate["release"]["tag"], "v0.78.0")
        self.assertEqual(candidate["predecessor_release"]["tag"], "v0.77.0")
        self.assertEqual(candidate["deployment"]["release_tag"], "v0.76.0")
        self.assertLessEqual(len(candidate["snapshot_inventory"]), 256)
        forbidden = (
            "binance_private", "private_protocol", "private_runtime",
            "canary_controller", "credential_envelope",
        )
        self.assertFalse(any(
            any(word in path.lower() for word in forbidden)
            for path in candidate["snapshot_inventory"]
        ))
        self.assertEqual(
            candidate["runtime_module"],
            "crypto_quant.challenger_replacement_v3_installed_runtime",
        )
        self.assertFalse(candidate["authority"]["production_activation"])
        self.assertFalse(candidate["authority"]["real_orders_allowed"])
        self.assertIn(
            "src/crypto_quant/challenger_replacement_v3_activation_trust_cli.py",
            candidate["snapshot_inventory"],
        )

    def test_candidate_loader_requires_exact_canonical_local_identity(self):
        from crypto_quant.challenger_replacement_v3_activation_trust import (
            ChallengerReplacementV3ActivationTrustError,
            build_fixed_v3_activation_candidate,
            load_fixed_v3_activation_candidate,
        )

        candidate = build_fixed_v3_activation_candidate()
        body = canonical_json(candidate).encode()
        self.assertEqual(load_fixed_v3_activation_candidate(body), candidate)
        with self.assertRaises(ChallengerReplacementV3ActivationTrustError):
            load_fixed_v3_activation_candidate(body + b"\n")

    def test_three_schema_mirrors_are_exact_and_closed(self):
        names = (
            "challenger-replacement-v3-install-contract-v1.schema.json",
            "challenger-replacement-v3-activation-preflight-v1.schema.json",
            "challenger-replacement-v3-activation-install-receipt-v1.schema.json",
        )
        for name in names:
            packaged = ROOT / "src/crypto_quant/schemas" / name
            configured = ROOT / "config" / name
            self.assertEqual(packaged.read_bytes(), configured.read_bytes())
            schema = json.loads(packaged.read_text())
            self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
