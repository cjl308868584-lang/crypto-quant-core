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
        self.assertLessEqual(sum(len(path.read_text().splitlines()) for path in paths), 335)

    def test_installer_has_one_bootstrap_and_no_forbidden_mutation_surface(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        self.assertEqual(text.count('"bootstrap"'), 3)
        for forbidden in ('"kickstart"', '"bootout"', '"enable"',
                          '"submit"', "shell=True", "live_runtime_cli"):
            self.assertNotIn(forbidden, text)
        self.assertLessEqual(sum(len(path.read_text().splitlines()) for path in paths), 415)

    def test_trust_and_shared_plist_renderer_keep_reallocated_yagni_gate(self):
        import ast

        trust_paths = [
            ROOT / "src/crypto_quant/challenger_replacement_install_trust.py",
            ROOT / "src/crypto_quant/challenger_replacement_install_trust_cli.py",
        ]
        self.assertLessEqual(
            sum(len(path.read_text().splitlines()) for path in trust_paths), 1675
        )
        deployment = ROOT / "src/crypto_quant/challenger_replacement_deployment.py"
        tree = ast.parse(deployment.read_text())
        renderer = next(node for node in tree.body if getattr(node, "name", "")
                        == "render_challenger_replacement_install_plist")
        self.assertLessEqual(renderer.end_lineno - renderer.lineno + 1, 20)

    def test_installed_adapter_is_bounded_and_has_no_generic_authority(self):
        paths = [
            ROOT / "src/crypto_quant/challenger_replacement_installed_runtime.py",
            ROOT / "src/crypto_quant/challenger_replacement_installed_runtime_cli.py",
        ]
        text = "\n".join(path.read_text() for path in paths)
        for forbidden in (
            "sqlite3", "fault_injector", "shell=True", "kickstart",
            "bootstrap", "Broker", "Order", "api_key", "secret_key",
        ):
            self.assertNotIn(forbidden, text)
        self.assertLessEqual(
            sum(len(path.read_text().splitlines()) for path in paths), 220
        )


if __name__ == "__main__":
    unittest.main()
