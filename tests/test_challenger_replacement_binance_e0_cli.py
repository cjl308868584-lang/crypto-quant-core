import io
from pathlib import Path
import unittest
from unittest.mock import patch


class BinanceE0CliTests(unittest.TestCase):
    OPPORTUNITY = "ETHUSDT@2026-08-28T12:00:00.000Z"

    def _module(self):
        from crypto_quant import challenger_replacement_binance_e0_cli
        return challenger_replacement_binance_e0_cli

    def test_no_arguments_is_zero_authority_usage_error(self):
        cli = self._module()
        with patch.object(cli, "run_fixed_binance_account_preflight") as preflight, \
                patch.object(cli, "run_fixed_binance_private_opportunity") as run, \
                patch.object(cli, "run_fixed_binance_emergency_stop") as stop:
            self.assertEqual(cli.main([]), 2)
        preflight.assert_not_called()
        run.assert_not_called()
        stop.assert_not_called()

    def test_only_three_closed_command_shapes_dispatch(self):
        cli = self._module()
        cases = (
            (["account-preflight"], "run_fixed_binance_account_preflight", ()),
            (["private-runtime", self.OPPORTUNITY],
             "run_fixed_binance_private_opportunity", (self.OPPORTUNITY,)),
            (["emergency-stop", self.OPPORTUNITY],
             "run_fixed_binance_emergency_stop", (self.OPPORTUNITY,)),
        )
        for argv, selected, arguments in cases:
            with self.subTest(argv=argv), patch.object(
                cli, selected, return_value={"status": "OK"},
            ) as command, patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(cli.main(argv), 0)
                command.assert_called_once_with(*arguments)
                self.assertEqual(out.getvalue(), '{"status":"OK"}\n')

    def test_endpoint_url_symbol_quantity_and_path_overrides_are_forbidden(self):
        cli = self._module()
        forbidden = ("--endpoint", "--url", "--symbol", "--quantity",
                     "--credential", "--root", "--reason")
        for option in forbidden:
            with self.subTest(option=option), patch.object(
                cli, "run_fixed_binance_private_opportunity",
            ) as run:
                self.assertEqual(cli.main([
                    "private-runtime", self.OPPORTUNITY, option, "x",
                ]), 2)
            run.assert_not_called()

    def test_invalid_opportunity_id_fails_before_dispatch(self):
        cli = self._module()
        with patch.object(
            cli, "run_fixed_binance_private_opportunity",
        ) as run:
            self.assertEqual(cli.main(["private-runtime", "ETHUSDT@now"]), 2)
        run.assert_not_called()

    def test_packaging_exposes_the_same_fixed_cli(self):
        root = Path(__file__).resolve().parents[1]
        target = (
            "challenger-replacement-binance-e0 = "
            '"crypto_quant.challenger_replacement_binance_e0_cli:main"'
        )
        self.assertIn(target, (root / "pyproject.toml").read_text())
        legacy = (root / "setup.py").read_text()
        self.assertIn("challenger-replacement-binance-e0=", legacy)
        self.assertIn(
            "crypto_quant.challenger_replacement_binance_e0_cli:main",
            legacy,
        )


if __name__ == "__main__":
    unittest.main()
