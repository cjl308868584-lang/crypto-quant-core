import inspect
import json
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from types import SimpleNamespace

from unittest.mock import patch

from crypto_quant import challenger_replacement_economic_evaluation_cli as cli_module
from crypto_quant import challenger_replacement_v3_observer as observer_module
from crypto_quant.challenger_replacement_economic_evaluation_cli import main


class EconomicEvaluationCliTests(unittest.TestCase):
    def test_fixed_loader_delegates_to_owner_only_in_context_evaluation(self):
        expected = {"status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"}
        with patch(
            "crypto_quant.challenger_replacement_v3_observer._evaluate_fixed_economic_result",
            return_value=expected,
            create=True,
        ) as loader:
            self.assertIs(cli_module._load_fixed_evaluation_result(), expected)
        loader.assert_called_once_with()

    def test_owner_only_capability_stays_open_until_evaluation_returns(self):
        lifecycle = {"open": False}
        state = SimpleNamespace(event_root=SimpleNamespace(descriptor=-1))
        receipt = {"economic_start": {"scheduled_for": "2026-01-01T00:00:00.000Z"}}
        deployment = {"candidate_build": {"release_tag": "v0.76.0"}}

        @contextmanager
        def opened(_root):
            lifecycle["open"] = True
            state.event_root.descriptor = 41
            try:
                yield deployment, state, {}, receipt
            finally:
                state.event_root.descriptor = -1
                lifecycle["open"] = False

        expected = {"status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"}
        def evaluate(*_args, **_sources):
            self.assertTrue(lifecycle["open"])
            self.assertEqual(state.event_root.descriptor, 41)
            return expected

        with patch.object(observer_module, "_runtime_entry", return_value=9), \
             patch.object(observer_module, "_open_sources", side_effect=opened), \
             patch.object(observer_module, "_observed_at",
                          return_value="2026-04-01T00:00:00.000Z"), \
             patch.object(observer_module, "build_economic_evaluation_facts_from_state",
                          return_value=object()), \
             patch.object(observer_module, "evaluate_challenger_replacement_economic_result",
                          side_effect=evaluate, create=True), \
             patch.object(observer_module.os, "close"):
            self.assertIs(observer_module._evaluate_fixed_economic_result(), expected)
        self.assertFalse(lifecycle["open"])
        self.assertEqual(state.event_root.descriptor, -1)

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
        expected = {"status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"}
        stdout, stderr = StringIO(), StringIO()
        with patch(
            "crypto_quant.challenger_replacement_economic_evaluation_cli._load_fixed_evaluation_result",
            return_value=expected,
        ) as evaluate, redirect_stdout(stdout), redirect_stderr(stderr):
            code = main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(stderr.getvalue(), "")
        evaluate.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
