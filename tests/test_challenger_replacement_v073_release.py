import json
import re
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/implementation-status-v0.73.0.md"


class V073ReleaseTests(unittest.TestCase):
    def test_versions_manifest_and_candidate_inventory_are_exact(self):
        self.assertRegex(
            (ROOT / "pyproject.toml").read_text(),
            r'(?m)^version = "0\.78\.0"$',
        )
        self.assertRegex(
            (ROOT / "setup.py").read_text(), r'version="0\.78\.0"'
        )
        manifest = json.loads(
            (ROOT / "config/evaluator-build-manifest-v1.json").read_text()
        )
        self.assertEqual(
            (
                crypto_quant.__version__,
                manifest["package_version"],
                manifest["manifest_version"],
            ),
            ("0.78.0", "0.78.0", "1.72.0"),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = {
            "config/operations-projection-v2.schema.json",
            "tests/test_challenger_replacement_readiness.py",
            "tests/test_challenger_replacement_readiness_observer.py",
            "tests/test_operations_projection_v2.py",
            "tests/test_v073_authority_boundaries.py",
            "tests/test_challenger_replacement_v073_release.py",
            "docs/superpowers/specs/2026-08-25-replacement-v3-readiness-observer-design.md",
            "docs/superpowers/plans/2026-08-25-replacement-v3-readiness-observer.md",
            "docs/adr/0073-replacement-v3-readiness-and-tail-blind-observation.md",
            "docs/implementation-status-v0.73.0.md",
        }
        self.assertEqual(required - expected, set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_status_preserves_nonactivation_and_honest_local_gate(self):
        status = STATUS.read_text()
        for required in (
            "READINESS_EVALUATOR_AND_READ_ONLY_INTEGRATION_VERIFIED_NOT_STARTED",
            "2055_EXECUTED_5_SKIPPED_18_EXPECTED_RELEASE_FREEZE_FAILURES_BEFORE_FINAL_REFRESH",
            "production_activation=false",
            "runtime_install_authorized=false",
            "replacement_start_authorized=false",
            "real_orders_allowed=false",
            "no seven-day timer started",
            "no 90-day timer started",
        ):
            self.assertIn(required, status)

    def test_readme_points_to_current_status_and_keeps_nonclaims(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("当前代码版本为 `0.78.0`", readme)
        self.assertIn("实施追踪 v0.78.0", readme)
        self.assertIn("90 天最终经济阈值仍须未来单独预注册", readme)


if __name__ == "__main__":
    unittest.main()
