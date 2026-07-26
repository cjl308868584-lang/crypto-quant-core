import unittest
from copy import deepcopy
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

    def scoped_gate(self, gate_id):
        for group, gates in self.bundle.flat_gate_groups().items():
            for gate in gates:
                if gate["gate_id"] == gate_id:
                    return group, gate
        self.fail(f"gate not found: {gate_id}")

    def scope(
        self,
        group,
        *,
        route="BASELINE_ONLY",
        stage="OFFLINE_OOS",
        ledger="BASELINE_LEDGER",
    ):
        scope = {
            "gate_group_id": group,
            "release_route": route,
            "release_kind": "INITIAL",
            "recipe_release_id": "recipe-1",
            "recipe_release_hash": "a" * 64,
            "experiment_manifest_id": "experiment-1",
            "experiment_manifest_hash": "e" * 64,
            "deployment_line_id": "line-1",
            "deployment_line_hash": "f" * 64,
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "stage": stage,
            "evaluation_window_start": "2025-01-01T00:00:00Z",
            "evaluation_window_end": "2025-12-31T23:59:59Z",
            "approved_production_capital_usdt": "500",
            "policy_bundle_hash": "b" * 64,
            "evaluation_ledger": ledger,
            "fallback_activation_requested": False,
            "policy_binding_hashes": {"evaluator_build_hash": "c" * 64},
            "actual_deployable_capital_usdt": "1000",
            "break_even_capital_lcb_root_usdt": "800",
        }
        if route == "AI_ENHANCED":
            scope.update(
                {
                    "ai_endpoint": "GROWTH",
                    "model_bundle_id": "model-1",
                    "model_bundle_schema_id": "model-bundle-v1.1.schema.json",
                    "model_bundle_hash": "d" * 64,
                }
            )
        if stage in ("CANARY_25", "CANARY_50", "CANARY_75"):
            scope["canary_block_number"] = {
                "CANARY_25": 1,
                "CANARY_50": 2,
                "CANARY_75": 3,
            }[stage]
        return scope

    def test_current_design_is_deterministically_fail_closed(self) -> None:
        results = [self.bundle.readiness() for _ in range(100)]
        self.assertEqual({result.result for result in results}, {"FAIL"})
        self.assertEqual(len({result.result_hash for result in results}), 1)
        reasons = set(results[0].reason_codes)
        self.assertIn("PRODUCTION_ACTIVATION_DISABLED", reasons)
        self.assertIn("MISSING_BINDING:evaluator_build_hash", reasons)

    def test_wrong_evaluator_build_binding_fails_readiness(self) -> None:
        policy = deepcopy(self.bundle.policy)
        policy["status"] = "ACTIVE"
        policy["production_activation"]["enabled"] = True
        for binding in policy["required_policy_bindings"]:
            binding["value"] = (
                "f" * 64
                if binding["binding"] == "evaluator_build_hash"
                else f"approved:{binding['binding']}"
            )
        bundle = PolicyBundle(
            root=self.bundle.root,
            policy=policy,
            catalog=deepcopy(self.bundle.catalog),
            evidence_schema=deepcopy(self.bundle.evidence_schema),
            estimators=self.bundle.estimators,
            evaluator_build=self.bundle.evaluator_build,
        )

        result = bundle.readiness()

        self.assertEqual(result.result, "FAIL")
        self.assertIn("EVALUATOR_BUILD_HASH_MISMATCH", result.reason_codes)

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

    def test_every_nonliteral_gate_form_has_exact_boundary_behavior(self) -> None:
        statistical = {
            "max_ci_width": {
                "BASELINE_ONLY": {"LONG": {"BASELINE": "0.05"}}
            },
            "audit_max_ci_width": {
                "BASELINE_ONLY": {"LONG": {"BASELINE": "0.04"}}
            },
        }
        forward = {
            "minimum_tradable_opportunity_rate": {
                "LONG": {"CANARY_25": "0.60"}
            }
        }
        cases = (
            (
                "ACTUAL_CI_WIDTH",
                {
                    "actual_primary_endpoint_ci_width": "0.05",
                },
                {
                    "actual_primary_endpoint_ci_width": "0.0501",
                },
                {
                    "release_route": "BASELINE_ONLY",
                    "direction": "LONG",
                    "ai_endpoint": None,
                },
                {"statistical_design_policy_id": statistical},
            ),
            (
                "FEATURE_COMPLEXITY_LIMIT",
                {"final_feature_count": 19, "effective_event_count": 399},
                {"final_feature_count": 20, "effective_event_count": 399},
                {},
                {},
            ),
            (
                "AI_RISK_RETURN_NONINFERIORITY",
                {
                    "ai_paired_delta_economic_net_log_growth_lcb95": "-0.02",
                    "baseline_economic_net_log_growth": "0.20",
                },
                {
                    "ai_paired_delta_economic_net_log_growth_lcb95": "-0.0201",
                    "baseline_economic_net_log_growth": "0.20",
                },
                {},
                {},
            ),
            (
                "AUDIT_BASE_ACTUAL_CI_WIDTH",
                {"audit_actual_primary_endpoint_ci_width": "0.04"},
                {"audit_actual_primary_endpoint_ci_width": "0.0401"},
                {
                    "release_route": "BASELINE_ONLY",
                    "direction": "LONG",
                    "ai_endpoint": None,
                },
                {"statistical_design_policy_id": statistical},
            ),
            (
                "AUDIT_AI_RISK_RETURN_NONINFERIORITY",
                {
                    "audit_ai_paired_delta_economic_net_log_growth_lcb95": "-0.03",
                    "audit_baseline_economic_net_log_growth": "0.30",
                },
                {
                    "audit_ai_paired_delta_economic_net_log_growth_lcb95": "-0.0301",
                    "audit_baseline_economic_net_log_growth": "0.30",
                },
                {},
                {},
            ),
            (
                "CANARY_TRADABLE_OPPORTUNITY",
                {"canary_min_notional_adjusted_tradable_opportunity_rate": "0.60"},
                {"canary_min_notional_adjusted_tradable_opportunity_rate": "0.5999"},
                {"direction": "LONG", "stage": "CANARY_25"},
                {"forward_control_policy_id": forward},
            ),
            (
                "ACTUAL_CAPITAL_AT_LEAST_APPROVED",
                {
                    "actual_deployable_capital_usdt": "500",
                    "approved_production_capital_usdt": "500",
                },
                {
                    "actual_deployable_capital_usdt": "499",
                    "approved_production_capital_usdt": "500",
                },
                {},
                {},
            ),
            (
                "ACTUAL_CAPITAL_AT_LEAST_BREAK_EVEN",
                {
                    "actual_deployable_capital_usdt": "800",
                    "break_even_capital_lcb_root_usdt": "800",
                },
                {
                    "actual_deployable_capital_usdt": "799",
                    "break_even_capital_lcb_root_usdt": "800",
                },
                {},
                {},
            ),
            (
                "MINOR_ECONOMIC_NONINFERIORITY",
                {
                    "minor_candidate_minus_active_economic_net_log_growth_lcb95": "-0.01",
                    "active_bundle_economic_net_log_growth": "0.20",
                },
                {
                    "minor_candidate_minus_active_economic_net_log_growth_lcb95": "-0.0101",
                    "active_bundle_economic_net_log_growth": "0.20",
                },
                {},
                {},
            ),
        )
        self.assertEqual(len(cases), 9)
        for gate_id, passing, failing, context, bindings in cases:
            group, gate = self.scoped_gate(gate_id)
            with self.subTest(gate_id=gate_id):
                passed = self.bundle.evaluate_gate(
                    group,
                    gate,
                    passing,
                    context,
                    binding_documents=bindings,
                )
                failed = self.bundle.evaluate_gate(
                    group,
                    gate,
                    failing,
                    context,
                    binding_documents=bindings,
                )
                self.assertEqual(passed.result, "PASS")
                self.assertEqual(failed.result, "FAIL")

    def test_ast_floor_min_and_strict_decimal_comparison(self) -> None:
        group, gate = self.scoped_gate("FEATURE_COMPLEXITY_LIMIT")
        at_boundary = self.bundle.evaluate_gate(
            group,
            gate,
            {"final_feature_count": 19, "effective_event_count": 399},
            {},
        )
        outside = self.bundle.evaluate_gate(
            group,
            gate,
            {"final_feature_count": 20, "effective_event_count": 399},
            {},
        )
        self.assertEqual(at_boundary.threshold_value, 19)
        self.assertEqual(at_boundary.result, "PASS")
        self.assertEqual(outside.result, "FAIL")
        self.assertEqual(outside.reason_codes, ("COMPARISON_FALSE",))
        wrong_json_type = self.bundle.evaluate_gate(
            group,
            gate,
            {"final_feature_count": "19", "effective_event_count": 399},
            {},
        )
        self.assertEqual(wrong_json_type.result, "FAIL")

    def test_expression_division_by_zero_and_free_form_fail_closed(self) -> None:
        division = self.bundle.resolve_expression(
            {
                "op": "DIVIDE",
                "args": [{"literal": "1"}, {"literal": "0"}],
            },
            {},
            {},
        )
        self.assertEqual(division.status, "INCONCLUSIVE")
        self.assertEqual(division.reason_codes, ("DIVISION_BY_ZERO",))

        repeating = self.bundle.resolve_expression(
            {
                "op": "DIVIDE",
                "args": [{"literal": "1"}, {"literal": "3"}],
            },
            {},
            {},
        )
        self.assertEqual(repeating.status, "FAIL")
        self.assertEqual(
            repeating.reason_codes,
            ("NON_TERMINATING_DECIMAL_RESULT",),
        )

        unsupported = self.bundle.resolve_expression(
            {"formula": "__import__('os').system('false')"},
            {},
            {},
        )
        self.assertEqual(unsupported.status, "FAIL")
        self.assertEqual(unsupported.reason_codes, ("INVALID_EXPRESSION_NODE",))

    def test_dynamic_reference_missing_binding_or_context_fails(self) -> None:
        group, gate = self.scoped_gate("ACTUAL_CI_WIDTH")
        observations = {"actual_primary_endpoint_ci_width": "0.01"}
        missing_binding = self.bundle.evaluate_gate(
            group,
            gate,
            observations,
            {
                "release_route": "BASELINE_ONLY",
                "direction": "LONG",
                "ai_endpoint": None,
            },
        )
        self.assertEqual(missing_binding.result, "FAIL")
        self.assertEqual(
            missing_binding.reason_codes,
            ("MISSING_BINDING_DOCUMENT:statistical_design_policy_id",),
        )

        missing_context = self.bundle.evaluate_gate(
            group,
            gate,
            observations,
            {"release_route": "BASELINE_ONLY"},
            binding_documents={"statistical_design_policy_id": {}},
        )
        self.assertEqual(missing_context.result, "FAIL")
        self.assertTrue(
            missing_context.reason_codes[0].startswith(
                "THRESHOLD_REFERENCE_UNRESOLVED:"
            )
        )

    def test_group_aggregation_propagates_inconclusive_and_keeps_children(self) -> None:
        observations = {
            "break_even_root_is_finite": True,
            "actual_deployable_capital_usdt": "1000",
            "approved_production_capital_usdt": "500",
            "break_even_capital_lcb_root_usdt": "800",
        }
        scope = self.scope("CAPITAL_READINESS")
        passed = self.bundle.evaluate_group(
            "CAPITAL_READINESS",
            observations,
            {},
            actual_scope=scope,
            expected_scope=deepcopy(scope),
        )
        self.assertEqual(passed.result, "PASS")
        self.assertEqual(len(passed.gate_results), 3)
        self.assertEqual({item.result for item in passed.gate_results}, {"PASS"})

        inconclusive = self.bundle.evaluate_group(
            "CAPITAL_READINESS",
            observations,
            {},
            actual_scope=scope,
            expected_scope=deepcopy(scope),
            inconclusive_metrics={"break_even_capital_lcb_root_usdt"},
        )
        self.assertEqual(inconclusive.result, "INCONCLUSIVE")
        self.assertEqual(
            inconclusive.gate_results[2].result,
            "INCONCLUSIVE",
        )
        self.assertIn(
            "REQUIRED_GATE_INCONCLUSIVE:ACTUAL_CAPITAL_AT_LEAST_BREAK_EVEN",
            inconclusive.reason_codes,
        )

    def test_scope_exact_match_blocks_stage_direction_and_policy_reuse(self) -> None:
        observations = {
            "break_even_root_is_finite": True,
            "actual_deployable_capital_usdt": "1000",
            "approved_production_capital_usdt": "500",
            "break_even_capital_lcb_root_usdt": "800",
        }
        actual = self.scope("CAPITAL_READINESS", stage="CANARY_25")
        for field, changed in (
            ("stage", "CANARY_50"),
            ("direction", "SHORT"),
            ("policy_bundle_hash", "f" * 64),
            ("approved_production_capital_usdt", "600"),
        ):
            expected = deepcopy(actual)
            expected[field] = changed
            with self.subTest(field=field):
                result = self.bundle.evaluate_group(
                    "CAPITAL_READINESS",
                    observations,
                    {},
                    actual_scope=actual,
                    expected_scope=expected,
                )
                self.assertEqual(result.result, "FAIL")
                self.assertIn(
                    f"SCOPE_VALUE_MISMATCH:{field}",
                    result.reason_codes,
                )
                self.assertEqual(
                    {item.result for item in result.gate_results},
                    {"FAIL"},
                )

    def test_scope_context_mismatch_is_not_hidden_by_equal_scope_objects(self) -> None:
        scope = self.scope("CAPITAL_READINESS")
        result = self.bundle.evaluate_group(
            "CAPITAL_READINESS",
            {
                "break_even_root_is_finite": True,
                "actual_deployable_capital_usdt": "1000",
                "approved_production_capital_usdt": "500",
                "break_even_capital_lcb_root_usdt": "800",
            },
            {"direction": "SHORT"},
            actual_scope=scope,
            expected_scope=deepcopy(scope),
        )
        self.assertEqual(result.result, "FAIL")
        self.assertIn("SCOPE_CONTEXT_MISMATCH:direction", result.reason_codes)

    def test_scope_hash_and_group_result_are_reproducible(self) -> None:
        scope = self.scope("CAPITAL_READINESS")
        kwargs = {
            "gate_group_id": "CAPITAL_READINESS",
            "observations": {
                "break_even_root_is_finite": True,
                "actual_deployable_capital_usdt": "1000",
                "approved_production_capital_usdt": "500",
                "break_even_capital_lcb_root_usdt": "800",
            },
            "context": {},
            "actual_scope": scope,
            "expected_scope": deepcopy(scope),
        }
        results = [self.bundle.evaluate_group(**kwargs) for _ in range(100)]
        self.assertEqual({result.result for result in results}, {"PASS"})
        self.assertEqual(len({result.result_hash for result in results}), 1)
        self.assertEqual(
            len(
                {
                    tuple(item.result_hash for item in result.gate_results)
                    for result in results
                }
            ),
            1,
        )

    def test_audit_and_forward_matrix_selection_is_route_specific(self) -> None:
        baseline = self.bundle.audit_plan("INITIAL", "BASELINE_ONLY")
        self.assertEqual(
            {(item.gate_group_id, item.evaluation_ledger) for item in baseline},
            {
                ("STRUCTURAL", "ROUTE_RUNTIME"),
                ("SAMPLE", "BASELINE_LEDGER"),
                ("RELEASE_AUDIT_CONTROL", "ROUTE_RUNTIME"),
                ("AUDIT_BASE_ARM", "BASELINE_LEDGER"),
            },
        )
        ai = self.bundle.audit_plan("MAJOR", "AI_ENHANCED", "GROWTH")
        self.assertIn(
            ("AUDIT_AI_ARM", "AI_LEDGER"),
            {(item.gate_group_id, item.evaluation_ledger) for item in ai},
        )
        self.assertIn(
            ("AUDIT_AI_ENDPOINT.GROWTH", "PAIRED_COMPARISON"),
            {(item.gate_group_id, item.evaluation_ledger) for item in ai},
        )
        self.assertNotIn(
            "CANARY_AI",
            self.bundle.forward_gate_groups("BASELINE_ONLY", "CANARY_25"),
        )
        self.assertIn(
            "CANARY_AI",
            self.bundle.forward_gate_groups("AI_ENHANCED", "CANARY_25"),
        )
        with self.assertRaises(PolicyError):
            self.bundle.audit_plan("INITIAL", "BASELINE_ONLY", "GROWTH")

    def test_evidence_scope_snapshot_includes_conditional_dimensions(self) -> None:
        evidence = self.scope(
            "CANARY_AI",
            route="AI_ENHANCED",
            stage="CANARY_25",
            ledger="PAIRED_COMPARISON",
        )
        evidence.update(
            {
                "metric_catalog_id": "release-metrics-v1.1",
                "release_gate_policy_id": "release-gates-v1.1",
                "release_gate_policy_version": (
                    self.bundle.policy["policy_version"]
                ),
                "recipe_release_schema_id": "recipe-release-v1.1.schema.json",
                "frozen_release_inputs": {
                    "approved_capital_and_break_even_plan": {
                        "artifact_hash": "e" * 64,
                    }
                },
            }
        )
        snapshot = self.bundle.evidence_scope_snapshot(evidence)
        self.assertEqual(snapshot["ai_endpoint"], "GROWTH")
        self.assertEqual(snapshot["canary_block_number"], 1)
        self.assertEqual(snapshot["actual_deployable_capital_usdt"], "1000")
        self.assertEqual(snapshot["experiment_manifest_id"], "experiment-1")
        self.assertEqual(snapshot["deployment_line_hash"], "f" * 64)
        self.assertIn("policy_binding_hashes", snapshot)
        self.assertEqual(
            snapshot["approved_capital_and_break_even_plan_hash"],
            "e" * 64,
        )

    def test_evidence_schema_errors_are_stable_and_fail_closed(self) -> None:
        first = self.bundle.evidence_schema_errors({})
        second = self.bundle.evidence_schema_errors({})
        self.assertEqual(first, second)
        self.assertTrue(first)
        self.assertTrue(all(reason.startswith("EVIDENCE_SCHEMA:") for reason in first))

    def test_policy_scope_dimensions_must_exist_in_evidence_schema(self) -> None:
        policy = deepcopy(self.bundle.policy)
        policy["evidence_scope"]["required_dimensions"].append(
            "undeclared_scope_field"
        )
        bundle = PolicyBundle(
            root=self.bundle.root,
            policy=policy,
            catalog=deepcopy(self.bundle.catalog),
            evidence_schema=deepcopy(self.bundle.evidence_schema),
            estimators=self.bundle.estimators,
            evaluator_build=self.bundle.evaluator_build,
        )
        with self.assertRaisesRegex(
            PolicyError,
            "Evidence Scope fields absent from schema",
        ):
            bundle.validate_cross_references()


if __name__ == "__main__":
    unittest.main()
