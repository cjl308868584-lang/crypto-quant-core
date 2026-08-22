import ast
import json
import re
import unittest
from pathlib import Path

import crypto_quant

from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_SHA = "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09"
SETUP_PYTHON_SHA = "ece7cb06caefa5fff74198d8649806c4678c61a1"


class NautilusV065ReleaseTests(unittest.TestCase):
    def test_public_ci_keeps_core_matrix_and_replays_inconclusive_on_macos(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('python-version: ["3.9", "3.12"]', workflow)
        self.assertNotIn("actions/checkout@v5", workflow)
        self.assertNotIn("actions/setup-python@v6", workflow)
        self.assertGreaterEqual(workflow.count(f"actions/checkout@{CHECKOUT_SHA}"), 2)
        self.assertGreaterEqual(workflow.count(f"actions/setup-python@{SETUP_PYTHON_SHA}"), 2)
        sandbox = workflow.split("  nautilus-sandbox-replay:\n", 1)[1]
        self.assertIn("name: nautilus-sandbox (3.12, macos-15 arm64)", sandbox)
        self.assertIn("runs-on: macos-15", sandbox)
        self.assertIn('python-version: "3.12"', sandbox)
        self.assertIn('test "$(uname -m)" = "arm64"', sandbox)
        self.assertIn('test "$(sw_vers -productVersion | cut -d. -f1)" = "15"', sandbox)
        self.assertIn("test_nautilus_v065_artifacts", sandbox)
        self.assertIn("load_nautilus_v065_formal_completion", sandbox)
        self.assertIn("INCONCLUSIVE_KEEP_CURRENT_CORE", sandbox)
        self.assertIn("NAUTILUS_V065_PLATFORM_MISMATCH", sandbox)
        for forbidden in (
            "acquire-and-run",
            "publish-plan",
            "nautilus_trader",
            "secrets.",
            "actions/cache",
        ):
            self.assertNotIn(forbidden, sandbox)

    def test_release_identity_and_build_inputs_are_v065(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r'^version = "0\.67\.0"$', pyproject, re.MULTILINE)
        )
        setup_tree = ast.parse((ROOT / "setup.py").read_text(encoding="utf-8"))
        setup_version = next(
            keyword.value.value
            for node in ast.walk(setup_tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setup"
            for keyword in node.keywords
            if keyword.arg == "version"
        )
        self.assertEqual(setup_version, "0.67.0")
        self.assertEqual(crypto_quant.__version__, "0.67.0")
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["manifest_version"], "1.61.0")
        self.assertEqual(manifest["package_version"], "0.67.0")
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-supply-chain-receipt-v0.65.0.json",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-comparison-v0.65.0.json",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-complete-v0.65.0.json",
            "docs/adr/0065-nautilus-end-to-end-spike.md",
            "docs/implementation-status-v0.65.0.md",
            "tests/test_nautilus_v065_artifacts.py",
            "tests/test_nautilus_v065_release.py",
        }
        self.assertEqual(required - expected, set())

    def test_release_docs_report_platform_inconclusive_without_engine_claim(self):
        adr = (ROOT / "docs/adr/0065-nautilus-end-to-end-spike.md").read_text(
            encoding="utf-8"
        )
        status = (ROOT / "docs/implementation-status-v0.65.0.md").read_text(
            encoding="utf-8"
        )
        for document in (adr, status):
            self.assertIn("INCONCLUSIVE_KEEP_CURRENT_CORE", document)
            self.assertIn("NAUTILUS_V065_PLATFORM_MISMATCH", document)
            self.assertIn("runner_invocation_count=0", document)
            self.assertIn("不证明 Nautilus 不适配", document)
            self.assertIn("不证明当前核心更优", document)


if __name__ == "__main__":
    unittest.main()
