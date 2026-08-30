import json
from pathlib import Path
import unittest

import crypto_quant
from crypto_quant.challenger_replacement_v3_activation_trust import activation_paths


ROOT = Path(__file__).resolve().parents[1]


class V0787ReleaseTests(unittest.TestCase):
    def test_release_identity_paths_and_recovery_files_are_v0787(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(crypto_quant.__version__, "0.78.7")
        self.assertIn('version = "0.78.7"', (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.7"', (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.7", "1.79.0"),
        )
        paths = activation_paths()
        self.assertTrue(paths["contract"].endswith(
            "challenger-replacement-v3-install-contract-v0.78.7.json"
        ))
        self.assertTrue(paths["candidate_plist"].endswith(
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist"
        ))
        self.assertTrue(paths["recovery_receipt_root"].endswith(
            "partial-install-recovery-receipts-v0.78.7"
        ))
        self.assertEqual(
            paths["target_plist"],
            "/Users/chenm4/Library/LaunchAgents/"
            "local.crypto-quant.challenger-replacement-v1-v0.78.7.plist",
        )
        required = {
            "config/challenger-replacement-v3-partial-install-recovery-v0.78.7.json",
            "src/crypto_quant/challenger_replacement_v3_partial_install_recovery.py",
            "src/crypto_quant/challenger_replacement_v3_partial_install_recovery_cli.py",
            "src/crypto_quant/schemas/challenger-replacement-v3-partial-install-recovery-plan-v1.schema.json",
            "src/crypto_quant/schemas/challenger-replacement-v3-partial-install-recovery-receipt-v1.schema.json",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))

    def test_release_documents_preserve_history_and_forbid_execution(self):
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        required = {
            "docs/adr/0085-v0787-partial-install-recovery.md",
            "docs/implementation-status-v0.78.7.md",
            "tests/test_challenger_replacement_v0787_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))
        texts = [
            (ROOT / "docs/adr/0085-v0787-partial-install-recovery.md").read_text(),
            (ROOT / "docs/implementation-status-v0.78.7.md").read_text(),
            (ROOT / "docs/runbooks/challenger-replacement-v3-simulation-activation.md").read_text(),
        ]
        for text in texts:
            self.assertIn("v0.78.7", text)
            self.assertIn("v0.78.5", text)
            self.assertIn("must not be deleted", text)
            self.assertIn("disabled", text)
            self.assertIn("unloaded", text)
        joined = "\n".join(texts)
        for step in (
            "renderer", "recovery qualification", "preflight",
            "bootstrap-only installer", "natural opportunity",
            "observer/start receipt",
        ):
            self.assertIn(step, joined)
        self.assertIn("does not authorize installation or start", joined)

    def test_recovery_code_has_no_execution_or_trading_authority(self):
        bodies = "\n".join(
            (ROOT / path).read_text()
            for path in (
                "src/crypto_quant/challenger_replacement_v3_partial_install_recovery.py",
                "src/crypto_quant/challenger_replacement_v3_partial_install_recovery_cli.py",
            )
        )
        for forbidden in (
            "launchctl bootstrap", "launchctl kickstart", "launchctl enable",
            "launchctl start", "api_key", "secret_key", "submit_order",
        ):
            self.assertNotIn(forbidden, bodies.lower())


if __name__ == "__main__":
    unittest.main()
