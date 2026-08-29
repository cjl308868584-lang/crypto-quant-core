import json
import hashlib
import unittest
from pathlib import Path

import crypto_quant


ROOT = Path(__file__).resolve().parents[1]


class V078ReleaseTests(unittest.TestCase):
    def test_vendored_runtime_wheels_are_exact_release_inputs(self):
        expected = {
            "attrs-26.1.0-py3-none-any.whl": "c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309",
            "jsonschema-4.25.1-py3-none-any.whl": "3fba0169e345c7175110351d456342c364814cfcf3b964ba4587f22915230a63",
            "jsonschema_specifications-2025.9.1-py3-none-any.whl": "98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe",
            "referencing-0.36.2-py3-none-any.whl": "e8699adbbf8b5c7de96d8ffa0eb5c158b3beafce084968e2ea8bb08c6794dcd0",
            "rpds_py-0.27.1-cp39-cp39-macosx_11_0_arm64.whl": "1fea2b1a922c47c51fd07d656324531adc787e415c8b116530a1d29c0516c62d",
            "typing_extensions-4.16.0-py3-none-any.whl": "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
        }
        root = ROOT / "vendor/challenger-replacement-v3/wheels"
        self.assertEqual({path.name for path in root.iterdir()}, set(expected))
        self.assertEqual(
            {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
             for name in expected}, expected,
        )

    def test_versions_and_manifest_are_v078(self):
        self.assertEqual(crypto_quant.__version__, "0.78.2")
        self.assertIn('version = "0.78.2"', (ROOT / "pyproject.toml").read_text())
        self.assertIn('version="0.78.2"', (ROOT / "setup.py").read_text())
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual((manifest["package_version"], manifest["manifest_version"]),
                         ("0.78.2", "1.74.0"))

    def test_release_documents_define_one_external_ceremony_and_no_v079(self):
        paths = (
            ROOT / "docs/adr/0078-v3-simulation-activation-trust-chain.md",
            ROOT / "docs/implementation-status-v0.78.0.md",
            ROOT / "docs/runbooks/challenger-replacement-v3-simulation-activation.md",
        )
        for path in paths:
            text = path.read_text()
            for claim in (
                "V3_SIMULATION_ACTIVATION_TRUST_CHAIN_CODE_RELEASED_NOT_INSTALLED",
                "production_activation=false", "no service installed or started",
                "no credentials", "no real orders", "no funds moved",
                "System Paper is non-blocking", "no v0.79",
            ):
                self.assertIn(claim, text, path.name)


if __name__ == "__main__":
    unittest.main()
