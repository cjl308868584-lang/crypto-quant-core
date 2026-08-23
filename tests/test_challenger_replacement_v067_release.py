import json
import re
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]


class V067ReleaseTests(unittest.TestCase):
    def test_versions_and_all_candidate_inputs_are_frozen(self):
        self.assertRegex((ROOT / "pyproject.toml").read_text(), r'(?m)^version = "0\.69\.0"$')
        manifest = json.loads((ROOT / "config/evaluator-build-manifest-v1.json").read_text())
        self.assertEqual((crypto_quant.__version__, manifest["package_version"], manifest["manifest_version"]), ("0.69.0", "0.69.0", "1.63.0"))
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/challenger-replacement-live-capture-v1.schema.json",
            "config/challenger-replacement-source-bundle-v2.schema.json",
            "config/challenger-replacement-decision-v2.schema.json",
            "config/challenger-replacement-deployment-v1.schema.json",
            "config/challenger-replacement-preflight-v1.schema.json",
            "src/crypto_quant/challenger_replacement_live_input.py",
            "src/crypto_quant/challenger_replacement_live_runtime_cli.py",
            "src/crypto_quant/challenger_replacement_deployment.py",
            "src/crypto_quant/challenger_replacement_preflight.py",
            "artifacts/challenger-replacement/challenger-replacement-deployment-v0.67.0.json",
            "artifacts/challenger-replacement/local.crypto-quant.challenger-replacement-v1.plist",
            "tests/test_challenger_replacement_v067_safety.py",
            "tests/test_challenger_replacement_v067_release.py",
            "docs/adr/0067-replacement-live-input-deployment-candidate.md",
            "docs/implementation-status-v0.67.0.md",
        }
        self.assertEqual(required - expected, set())

    def test_release_docs_preserve_nonactivation_boundary(self):
        documents = [(ROOT / path).read_text() for path in (
            "docs/adr/0067-replacement-live-input-deployment-candidate.md",
            "docs/implementation-status-v0.67.0.md",
        )]
        for document in documents:
            for text in ("DEPLOYMENT_CANDIDATE_RELEASED_NOT_INSTALLED", "production_activation=false", "runtime_install_authorized=false", "replacement_start_authorized=false", "real_orders_allowed=false", "no 90-day timer started"):
                self.assertIn(text, document)


if __name__ == "__main__":
    unittest.main()
