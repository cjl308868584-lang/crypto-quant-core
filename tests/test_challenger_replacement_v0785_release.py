import json
from pathlib import Path
import unittest

import crypto_quant
from crypto_quant.challenger_replacement_v3_activation_trust import (
    activation_paths,
)


ROOT = Path(__file__).resolve().parents[1]


class V0785ReleaseTests(unittest.TestCase):
    def test_release_identity_schemas_and_candidate_paths_are_v0785(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(crypto_quant.__version__, "0.78.5")
        self.assertIn('version = "0.78.5"', (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.5"', (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.5", "1.77.0"),
        )
        paths = activation_paths()
        self.assertTrue(
            paths["contract"].endswith(
                "challenger-replacement-v3-install-contract-v0.78.5.json"
            )
        )
        self.assertTrue(
            paths["candidate_plist"].endswith(
                "local.crypto-quant.challenger-replacement-v1-v0.78.5.plist"
            )
        )
        self.assertTrue(paths["preflight_root"].endswith("preflight-receipts-v0.78.5"))
        self.assertTrue(
            paths["install_receipt_root"].endswith("install-receipts-v0.78.5")
        )
        for relative in (
            "src/crypto_quant/schemas/challenger-replacement-v3-install-contract-v1.schema.json",
            "config/challenger-replacement-v3-install-contract-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-v3-activation-install-receipt-v1.schema.json",
            "config/challenger-replacement-v3-activation-install-receipt-v1.schema.json",
        ):
            text = (ROOT / relative).read_text()
            self.assertIn('"v0.78.5"', text)
            self.assertIn('"1.77.0"', text)

    def test_release_documents_preserve_evidence_and_inventory(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        required = {
            "docs/adr/0083-v0785-activation-candidate-supersession.md",
            "docs/implementation-status-v0.78.5.md",
            "docs/runbooks/challenger-replacement-v3-simulation-activation.md",
            "tests/test_challenger_replacement_v0785_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))
        for relative in required - {
            "tests/test_challenger_replacement_v0785_release.py"
        }:
            self.assertTrue((ROOT / relative).is_file())
        status = (ROOT / "docs/implementation-status-v0.78.5.md").read_text()
        adr = (
            ROOT / "docs/adr/0083-v0785-activation-candidate-supersession.md"
        ).read_text()
        runbook = (
            ROOT / "docs/runbooks/challenger-replacement-v3-simulation-activation.md"
        ).read_text()
        for text in (status, adr, runbook):
            self.assertIn("v0.78.3", text)
            self.assertIn("v0.78.5", text)
            self.assertIn("must not be deleted", text)


if __name__ == "__main__":
    unittest.main()
