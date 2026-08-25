import json
import unittest
from pathlib import Path

import crypto_quant
from crypto_quant.build import EvaluatorBuild, _V074_RELEASE_PATHS


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/implementation-status-v0.74.0.md"


class V074ReleaseTests(unittest.TestCase):
    def test_versions_manifest_and_candidate_inventory_are_exact(self):
        self.assertRegex(
            (ROOT / "pyproject.toml").read_text(),
            r'(?m)^version = "0\.75\.0"$',
        )
        self.assertRegex(
            (ROOT / "setup.py").read_text(), r'version="0\.75\.0"'
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
            ("0.75.0", "0.75.0", "1.69.0"),
        )
        expected = set(EvaluatorBuild.expected_file_paths(ROOT))
        required = set(_V074_RELEASE_PATHS)
        self.assertEqual(required - expected, set())
        self.assertEqual(required - set(manifest["file_hashes"]), set())
        self.assertEqual(set(manifest["file_hashes"]), expected)

    def test_status_preserves_preregistered_nonactivation_boundary(self):
        status = STATUS.read_text()
        for required in (
            "ECONOMIC_EVALUATION_PLAN_PREREGISTERED_NOT_STARTED",
            "production_activation=false",
            "runtime_install_authorized=false",
            "replacement_start_authorized=false",
            "real_orders_allowed=false",
            "economic_outcome_reads=0",
            "no seven-day timer started",
            "no 90-day timer started",
        ):
            self.assertIn(required, status)

    def test_readme_points_to_current_status_and_keeps_future_milestones(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("\u5f53\u524d\u4ee3\u7801\u7248\u672c\u4e3a `0.75.0`", readme)
        self.assertIn("\u5b9e\u65bd\u8ffd\u8e2a v0.75.0", readme)
        self.assertIn(
            "\u6700\u7ec8\u7ecf\u6d4e\u8bc4\u4f30\u5668\u4e0e\u5b89\u88c5/\u542f\u52a8\u4ecd\u662f\u672a\u6765\u4e92\u76f8\u72ec\u7acb\u7684\u91cc\u7a0b\u7891",
            readme,
        )


if __name__ == "__main__":
    unittest.main()
