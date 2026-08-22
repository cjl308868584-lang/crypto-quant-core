import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class V068ReleaseTests(unittest.TestCase):
    def test_design_and_plan_are_committed_without_production_artifacts(self):
        self.assertTrue((ROOT / "docs/superpowers/specs/2026-08-22-replacement-install-observer-start-design.md").is_file())
        self.assertTrue((ROOT / "docs/superpowers/plans/2026-08-22-replacement-install-observer-start.md").is_file())
        artifact_names = {path.name for path in
                          (ROOT / "artifacts/challenger-replacement").glob("*v0.68.0.json")}
        self.assertEqual(artifact_names, set())


if __name__ == "__main__":
    unittest.main()
