import inspect
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from crypto_quant.challenger_replacement_economic_evaluation_cli import main


class EconomicEvaluationCliTests(unittest.TestCase):
    def test_only_no_arguments_or_help_and_not_activated_is_read_only(self):
        self.assertEqual(tuple(inspect.signature(main).parameters), ("argv",))
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.assertEqual(main([]), 3)
            self.assertIn("ECONOMIC_EVALUATION_NOT_ACTIVATED", output.getvalue())
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(main(["--help"]), 0)
            self.assertEqual(main(["--path", "/tmp/result"]), 2)


if __name__ == "__main__":
    unittest.main()
