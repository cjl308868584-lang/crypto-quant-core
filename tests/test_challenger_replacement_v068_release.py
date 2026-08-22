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

    def test_preflight_modules_keep_static_authority_and_line_gates(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install_preflight.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_preflight_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("fault_injector", text)
        self.assertNotIn("kickstart", text)
        self.assertNotIn("import Broker", text)
        self.assertNotIn("import Order", text)
        self.assertLessEqual(sum(len(path.read_text().splitlines()) for path in paths), 300)


if __name__ == "__main__":
    unittest.main()
