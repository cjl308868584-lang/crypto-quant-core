import ast
import inspect
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "challenger_replacement_v3_activation_trust.py",
    "challenger_replacement_v3_activation_trust_cli.py",
    "challenger_replacement_v3_installed_runtime.py",
    "challenger_replacement_v3_activation_preflight.py",
    "challenger_replacement_v3_activation_preflight_cli.py",
    "challenger_replacement_v3_activation_install.py",
    "challenger_replacement_v3_activation_install_cli.py",
    "challenger_replacement_v3_activation_start.py",
    "challenger_replacement_v3_activation_start_cli.py",
)


class V078ArchitectureTests(unittest.TestCase):
    def test_exact_thin_module_inventory_and_line_budget(self):
        source = ROOT / "src/crypto_quant"
        lines = sum(len((source / name).read_text().splitlines()) for name in MODULES)
        self.assertLess(lines, 1550)
        self.assertEqual(lines, 1527)

    def test_activation_modules_do_not_import_private_or_system_paper_layers(self):
        forbidden = (
            "challenger_replacement_binance_private",
            "challenger_replacement_canary_controller",
            "challenger_replacement_binance_credential",
            "system_paper",
        )
        for name in MODULES:
            text = (ROOT / "src/crypto_quant" / name).read_text()
            imports = {
                node.module or "" for node in ast.walk(ast.parse(text))
                if isinstance(node, ast.ImportFrom)
            }
            self.assertFalse(any(
                any(value in module for value in forbidden) for module in imports
            ), name)

    def test_installer_contains_only_print_and_bootstrap_launchctl_actions(self):
        text = (ROOT / "src/crypto_quant/challenger_replacement_v3_activation_install.py").read_text()
        for forbidden in ('"kickstart"', '"start"', '"enable"', '"submit"', '"bootout"'):
            self.assertNotIn(forbidden, text)
        self.assertIn('"print"', text)
        self.assertIn('"bootstrap"', text)

    def test_public_entrypoints_accept_no_override_parameters(self):
        from crypto_quant import challenger_replacement_v3_activation_preflight as preflight
        from crypto_quant import challenger_replacement_v3_activation_install as install
        from crypto_quant import challenger_replacement_v3_activation_start as start

        for function in (
            preflight.collect_fixed_v3_activation_preflight,
            install.install_fixed_v3_simulation_launch_agent,
            start.observe_fixed_v3_first_opportunity,
            start.publish_fixed_v3_start_receipt,
        ):
            self.assertEqual(tuple(inspect.signature(function).parameters), ())


if __name__ == "__main__":
    unittest.main()
