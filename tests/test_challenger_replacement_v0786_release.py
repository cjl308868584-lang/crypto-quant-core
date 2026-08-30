import json
from pathlib import Path
import unittest

import crypto_quant
from crypto_quant.challenger_replacement_v3_activation_trust import activation_paths


ROOT = Path(__file__).resolve().parents[1]


class V0786ReleaseTests(unittest.TestCase):
    def test_release_identity_and_activation_paths_are_v0786(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(crypto_quant.__version__, "0.78.6")
        self.assertIn('version = "0.78.6"', (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.6"', (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.6", "1.78.0"),
        )
        paths = activation_paths()
        self.assertTrue(paths["contract"].endswith(
            "challenger-replacement-v3-install-contract-v0.78.6.json"
        ))
        self.assertTrue(paths["candidate_plist"].endswith(
            "local.crypto-quant.challenger-replacement-v1-v0.78.6.plist"
        ))
        self.assertTrue(paths["preflight_root"].endswith(
            "preflight-receipts-v0.78.6"
        ))
        self.assertTrue(paths["install_receipt_root"].endswith(
            "install-receipts-v0.78.6"
        ))

    def test_release_documents_freeze_partial_install_boundary(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        required = {
            "docs/adr/0084-v0786-install-receipt-time-hotfix.md",
            "docs/implementation-status-v0.78.6.md",
            "tests/test_challenger_replacement_v0786_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))
        status = (ROOT / "docs/implementation-status-v0.78.6.md").read_text()
        adr = (ROOT / "docs/adr/0084-v0786-install-receipt-time-hotfix.md").read_text()
        for text in (status, adr):
            self.assertIn("v0.78.6", text)
            self.assertIn("must not be deleted", text)
            self.assertIn("disabled", text)
            self.assertIn("unloaded", text)
            self.assertIn("recovery protocol", text)


if __name__ == "__main__":
    unittest.main()
