import json
from pathlib import Path
import unittest

import crypto_quant


ROOT = Path(__file__).resolve().parents[1]


class V0782ReleaseTests(unittest.TestCase):
    def test_patch_version_and_manifest_are_exact(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        self.assertEqual(crypto_quant.__version__, "0.78.7")
        self.assertIn('version = "0.78.7"',
                      (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.7"',
                      (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.7", "1.79.0"),
        )

    def test_release_inventory_contains_activation_rebind(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        required = {
            "docs/adr/0080-v0782-activation-release-rebind.md",
            "docs/implementation-status-v0.78.2.md",
            "tests/test_challenger_replacement_v0782_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))

    def test_status_records_preinstall_discovery_and_zero_authority(self):
        text = (
            ROOT / "docs/implementation-status-v0.78.2.md"
        ).read_text()
        for claim in (
            "V3_SIMULATION_ACTIVATION_RELEASE_REBOUND_NOT_INSTALLED",
            "CHALLENGER_REPLACEMENT_V3_RELEASE_IDENTITY_INVALID",
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
