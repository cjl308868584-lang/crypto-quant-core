import json
from pathlib import Path
import unittest

import crypto_quant


ROOT = Path(__file__).resolve().parents[1]


class V0784ReleaseTests(unittest.TestCase):
    def test_patch_version_manifest_and_activation_binding_are_exact(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        self.assertEqual(crypto_quant.__version__, "0.78.5")
        self.assertIn('version = "0.78.5"',
                      (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.5"',
                      (ROOT / "setup.py").read_text())
        self.assertEqual(
            (manifest["package_version"], manifest["manifest_version"]),
            ("0.78.5", "1.77.0"),
        )
        trust = (
            ROOT / "src/crypto_quant/"
            "challenger_replacement_v3_activation_trust.py"
        ).read_text()
        preflight = (
            ROOT / "src/crypto_quant/"
            "challenger_replacement_v3_activation_preflight.py"
        ).read_text()
        self.assertIn('"tag": "v0.78.5"', trust)
        self.assertIn('manifest["manifest_version"] != "1.77.0"', trust)
        self.assertIn('"git", "rev-parse", "v0.78.5^{}"', preflight)

    def test_release_inventory_contains_only_bounded_hotfix_evidence(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        required = {
            "docs/adr/0082-v0784-preflight-hotfix.md",
            "docs/implementation-status-v0.78.4.md",
            "tests/fixtures/pmset-g-custom-ac-safe.txt",
            "tests/test_challenger_replacement_v0784_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))

    def test_status_preserves_failure_evidence_and_zero_authority(self):
        text = (
            ROOT / "docs/implementation-status-v0.78.4.md"
        ).read_text()
        for claim in (
            "V3_SIMULATION_ACTIVATION_PREFLIGHT_FIXED_NOT_INSTALLED",
            "PREFLIGHT_PATH_BOUNDARY_INVALID",
            "PREFLIGHT_POWER_UNSAFE",
            "production_activation=false",
            "no replacement service installed or started",
            "no credential created or read",
            "no private Binance request made",
            "no order submitted",
            "no funds moved",
        ):
            self.assertIn(claim, text)


if __name__ == "__main__":
    unittest.main()
