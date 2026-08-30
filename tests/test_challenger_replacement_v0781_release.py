import json
from pathlib import Path
import unittest

import crypto_quant


ROOT = Path(__file__).resolve().parents[1]


class V0781ReleaseTests(unittest.TestCase):
    def test_patch_version_and_manifest_are_exact(self):
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

    def test_release_inventory_contains_hardening_boundary(self):
        manifest = json.loads((
            ROOT / "config/evaluator-build-manifest-v1.json"
        ).read_text())
        required = {
            "config/challenger-replacement-binance-private-event-v1.schema.json",
            "src/crypto_quant/challenger_replacement_binance_e0_cli.py",
            "src/crypto_quant/challenger_replacement_binance_e0_orchestration.py",
            "docs/adr/0079-binance-e0-release-blocker-hardening.md",
            "docs/implementation-status-v0.78.1.md",
            "docs/runbooks/binance-e0-operations-v0.78.1.md",
            "docs/superpowers/specs/2026-08-28-binance-e0-release-blocker-hardening-design.md",
            "docs/superpowers/plans/2026-08-28-binance-e0-release-blocker-hardening.md",
            "tests/test_challenger_replacement_binance_e0_cli.py",
            "tests/test_challenger_replacement_binance_e0_orchestration.py",
            "tests/test_challenger_replacement_v0781_release.py",
        }
        self.assertTrue(required <= set(manifest["file_hashes"]))

    def test_status_and_runbook_preserve_zero_authority(self):
        for relative in (
            "docs/implementation-status-v0.78.1.md",
            "docs/runbooks/binance-e0-operations-v0.78.1.md",
        ):
            text = (ROOT / relative).read_text()
            for claim in (
                "BINANCE_E0_CODE_COMPLETE_NOT_ACTIVATED",
                "production_activation=false",
                "no service installed or started",
                "no credential created or read",
                "no private Binance request made",
                "no order submitted",
                "no funds moved",
            ):
                self.assertIn(claim, text, relative)


if __name__ == "__main__":
    unittest.main()
