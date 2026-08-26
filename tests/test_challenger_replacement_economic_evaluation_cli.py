import inspect
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from unittest.mock import patch

from crypto_quant import challenger_replacement_economic_evaluation_cli as cli_module
from crypto_quant.challenger_replacement_economic_evaluation_cli import main


class EconomicEvaluationCliTests(unittest.TestCase):
    def test_fixed_loader_delegates_to_the_owner_only_observer_boundary(self):
        expected = {"facts": object(), "economic_plan": {}, "build_identity": {}}
        with patch(
            "crypto_quant.challenger_replacement_v3_observer._load_fixed_economic_sources",
            return_value=expected,
            create=True,
        ) as loader:
            self.assertIs(cli_module._load_fixed_evaluation_sources(), expected)
        loader.assert_called_once_with()

    def test_only_no_arguments_or_help_and_not_activated_is_read_only(self):
        self.assertEqual(tuple(inspect.signature(main).parameters), ("argv",))
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(main([]), 3)
            self.assertIn("ECONOMIC_EVALUATION_NOT_ACTIVATED", output.getvalue())
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["--help"]), 0)
            self.assertEqual(main(["--path", "/tmp/result"]), 2)

    def test_fixed_sources_run_the_real_evaluator_and_emit_canonical_json(self):
        sources = {
            "facts": object(), "economic_plan": {}, "build_identity": {},
        }
        expected = {"status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"}
        stdout, stderr = StringIO(), StringIO()
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation_cli._load_fixed_evaluation_sources",
            return_value=sources,
        ), patch(
            "crypto_quant.challenger_replacement_economic_evaluation_cli.evaluate_challenger_replacement_economic_result",
            return_value=expected,
        ) as evaluate, redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(stderr.getvalue(), "")
        evaluate.assert_called_once_with(**sources)


if __name__ == "__main__":
    unittest.main()
