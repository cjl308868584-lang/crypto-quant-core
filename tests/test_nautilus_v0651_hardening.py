import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]


class NautilusV0651HardeningTests(unittest.TestCase):
    def test_patch_release_files_are_frozen_build_inputs(self):
        expected_paths = set(EvaluatorBuild.expected_file_paths(ROOT))
        self.assertIn(
            "tests/test_nautilus_v0651_hardening.py",
            expected_paths,
        )
        self.assertIn(
            "docs/implementation-status-v0.65.1.md",
            expected_paths,
        )

    def test_patch_release_identity_is_v0651(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIsNotNone(
            re.search(r'^version = "0\.76\.0"$', pyproject, re.MULTILINE)
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
        self.assertEqual(setup_version, "0.76.0")
        self.assertEqual(crypto_quant.__version__, "0.76.0")
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["manifest_version"], "1.70.0")
        self.assertEqual(manifest["package_version"], "0.76.0")

    def test_patch_never_rewrites_or_relabels_v065_research_evidence(self):
        exact_hashes = {
            "artifacts/nautilus-sandbox/nautilus-e2e-spike-plan-v0.65.0.json": "c5bff241ee4dbba2ceb271d2842a0663669161f33416b2f2ac6caea5a78d6c08",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-supply-chain-receipt-v0.65.0.json": "11d15412ef7402434f3802fa380b7c4183de55a04d6ce025036d29c341ecc252",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-comparison-v0.65.0.json": "b679261e72f0eb81364be2878dc4ef8813279f47b1f57d31b460032bd08a77e5",
            "artifacts/nautilus-sandbox/v0.65.0/nautilus-sandbox-complete-v0.65.0.json": "cc52af4c5db422a688d5775c5a4900ede2477f2663e7e6b717a9b4dedb263202",
        }
        for relative, expected in exact_hashes.items():
            with self.subTest(relative=relative):
                self.assertEqual(
                    hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
                    expected,
                )

    def test_patch_status_freezes_scope_and_nonclaims(self):
        status = (ROOT / "docs/implementation-status-v0.65.1.md").read_text(
            encoding="utf-8"
        )
        for required in (
            "不重跑 v0.65.0 ceremony",
            "不修改 v0.65.0 research artifacts",
            "INCONCLUSIVE_KEEP_CURRENT_CORE",
            "runner_invocation_count=0",
            "不授权生产安装、真实 Broker 或订单",
        ):
            self.assertIn(required, status)


if __name__ == "__main__":
    unittest.main()
