import json
from pathlib import Path
import unittest

import crypto_quant


ROOT = Path(__file__).resolve().parents[1]


class V0783ReleaseTests(unittest.TestCase):
    def test_patch_version_and_manifest_are_exact(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        self.assertEqual(crypto_quant.__version__, "0.78.6")
        self.assertIn('version = "0.78.6"',
                      (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.6"',
                      (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.6", "1.78.0"),
        )

    def test_release_inventory_contains_filesystem_identity_hotfix(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        required = {
            "docs/adr/0081-v0783-filesystem-identity-hotfix.md",
            "docs/implementation-status-v0.78.3.md",
            "tests/test_challenger_replacement_v0783_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))

    def test_status_preserves_zero_authority_and_records_renderer_failure(self):
        text = (
            ROOT / "docs/implementation-status-v0.78.3.md"
        ).read_text()
        for claim in (
            "V3_SIMULATION_ACTIVATION_FILESYSTEM_IDENTITY_FIXED_NOT_INSTALLED",
            "integer exceeds the exact JSON safe range",
            "production_activation=false",
            "no service installed or started",
            "no credential created or read",
            "no private Binance request made",
            "no order submitted",
            "no funds moved",
        ):
            self.assertIn(claim, text)


if __name__ == "__main__":
    unittest.main()
