import unittest
from pathlib import Path

from crypto_quant.errors import PolicyError
from crypto_quant.release import PolicyBundle, _format_checker

ROOT = Path(__file__).resolve().parents[1]


class ReleaseEvaluatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = PolicyBundle.load(ROOT / "config")

    def gate(self, gate_id):
        for gates in self.bundle.flat_gate_groups().values():
            for gate in gates:
                if gate["gate_id"] == gate_id:
                    return gate
        self.fail(f"gate not found: {gate_id}")

    def test_current_design_is_deterministically_fail_closed(self) -> None:
        results = [self.bundle.readiness() for _ in range(100)]
        self.assertEqual({result.result for result in results}, {"FAIL"})
        self.assertEqual(len({result.result_hash for result in results}), 1)
        reasons = set(results[0].reason_codes)
        self.assertIn("PRODUCTION_ACTIVATION_DISABLED", reasons)
        self.assertIn("MISSING_BINDING:evaluator_build_hash", reasons)

    def test_all_authoritative_gates_resolve(self) -> None:
        groups = self.bundle.flat_gate_groups()
        self.assertEqual(len(groups), 20)
        self.assertEqual(sum(len(gates) for gates in groups.values()), 149)
        with self.assertRaises(PolicyError):
            self.bundle.metrics.resolve("unknown_profit_metric")

    def test_schema_dates_are_checked_without_optional_format_packages(self) -> None:
        checker = _format_checker()
        self.assertTrue(checker.conforms("2026-07-26", "date"))
        self.assertFalse(checker.conforms("2026-02-30", "date"))
        self.assertTrue(checker.conforms("2026-07-26T00:00:00Z", "date-time"))
        self.assertFalse(checker.conforms("2026-07-26T00:00:00", "date-time"))

    def test_literal_gate_pass_fail_and_missing_evidence(self) -> None:
        gate = self.gate("BASE_VARIABLE_NET_LOG_GROWTH_LCB")
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                gate,
                {"baseline_variable_net_log_growth_lcb95": "0.001"},
                {},
            ),
            "PASS",
        )
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                gate,
                {"baseline_variable_net_log_growth_lcb95": "0"},
                {},
            ),
            "FAIL",
        )
        self.assertEqual(self.bundle.evaluate_literal_gate(gate, {}, {}), "FAIL")

    def test_applies_when_missing_context_fails_closed(self) -> None:
        gate = self.gate("MODEL_BUNDLE_SCHEMA_VALID")
        evidence = {"model_bundle_schema_validation_pass": True}
        self.assertEqual(
            self.bundle.evaluate_literal_gate(gate, evidence, {}),
            "FAIL",
        )
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                gate,
                evidence,
                {"release_route": "BASELINE_ONLY"},
            ),
            "NOT_APPLICABLE",
        )
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                gate,
                evidence,
                {"release_route": "AI_ENHANCED"},
            ),
            "PASS",
        )
        malformed = dict(gate)
        malformed["applies_when"] = {
            "all": [{"attribute": "release_route", "comparator": "MAYBE", "value": "x"}]
        }
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                malformed,
                evidence,
                {"release_route": "AI_ENHANCED"},
            ),
            "FAIL",
        )

    def test_non_literal_threshold_is_not_silently_approximated(self) -> None:
        gate = self.gate("ACTUAL_CAPITAL_AT_LEAST_APPROVED")
        self.assertEqual(
            self.bundle.evaluate_literal_gate(
                gate,
                {"actual_deployable_capital_usdt": "1000"},
                {},
            ),
            "FAIL",
        )


if __name__ == "__main__":
    unittest.main()
