import json
import unittest
from copy import deepcopy
from decimal import getcontext
from pathlib import Path

from crypto_quant.canonical import business_hash
from crypto_quant.economics import (
    economic_snapshot_hash,
    economic_snapshot_reasons,
)
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.evidence import EvidenceTrustContext
from crypto_quant.release import MetricResolver, PolicyBundle, load_json_strict
from crypto_quant.release_artifacts import (
    supporting_observation_bundle_hash,
    supporting_observation_hash,
    validate_supporting_observation_bundle,
)
from crypto_quant.statistics import (
    paired_ai_delta_series_snapshot,
    statistical_series_hash,
    statistical_series_reasons,
)


ROOT = Path(__file__).resolve().parents[1]


class PairedStatisticalEstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", catalog)
        golden = json.loads(
            (ROOT / "config" / "estimator-golden-vectors-v1.json").read_text(
                encoding="utf-8"
            )
        )
        cls.paired = golden["fixtures"]["statistical-paired-series-valid"]
        cls.robustness = golden["fixtures"][
            "statistical-robustness-series-valid"
        ]
        cls.economic = golden["fixtures"]["economic-snapshot-valid"]

    def execute(self, estimator_id, series):
        return self.registry.execute(
            estimator_id,
            {"statistical_series_snapshot": series},
        )

    @staticmethod
    def rehash(series):
        series["series_hash"] = statistical_series_hash(series)
        return series

    def rebuild(self, baseline, ai):
        return paired_ai_delta_series_snapshot(
            series_id="paired-rebuilt-v1",
            baseline_series_snapshot=baseline,
            ai_series_snapshot=ai,
            model_bundle_id=self.paired["model_bundle_id"],
            model_bundle_hash=self.paired["model_bundle_hash"],
            ai_endpoint=self.paired["ai_endpoint"],
            generated_at=self.paired["generated_at"],
        )

    def test_registered_paired_and_robustness_estimators_are_exact(self):
        expected = {
            "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1": 3,
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1": "0.008",
        }
        for estimator_id, value in expected.items():
            with self.subTest(estimator_id=estimator_id):
                result = self.execute(estimator_id, self.paired)
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, value)
        resolver = MetricResolver(
            load_json_strict(
                ROOT / "config" / "release-metrics-v1.1.json"
            )
        )
        self.assertEqual(
            resolver.resolve(
                "baseline_leave_top_5_positive_trades_out_net_log_growth_lcb95"
            )["estimator_id"],
            "LEAVE_TOP_5_POSITIVE_TRADES_OUT_MBB_LCB95_V1",
        )

    def test_paired_hash_and_bootstrap_ignore_global_decimal_context(self):
        original_precision = getcontext().prec
        try:
            hashes = set()
            values = set()
            for precision in (9, 18, 28, 60):
                getcontext().prec = precision
                for _ in range(20):
                    self.assertEqual(
                        statistical_series_reasons(self.paired),
                        (),
                    )
                    hashes.add(statistical_series_hash(self.paired))
                    values.add(
                        self.execute(
                            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
                            self.paired,
                        ).value
                    )
            self.assertEqual(hashes, {self.paired["series_hash"]})
            self.assertEqual(values, {"0.008"})
        finally:
            getcontext().prec = original_precision

        robust_expected = {
            "LEAVE_MAX_POSITIVE_FOLD_OUT_MBB_LCB95_V1": "-11",
            "LEAVE_TOP_5_POSITIVE_EVENTS_OUT_MBB_LCB95_V1": "-10",
            "LEAVE_MAX_POSITIVE_EVENT_OUT_MBB_LCB95_V1": "-11",
        }
        for estimator_id, value in robust_expected.items():
            with self.subTest(estimator_id=estimator_id):
                result = self.execute(estimator_id, self.robustness)
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, value)

    def test_builder_excludes_and_reports_unpaired_keys(self):
        arms = deepcopy(self.paired["source_arm_series"])
        arms["ai"]["observations"][-1]["proposal_id"] = "proposal-unpaired-ai"
        self.rehash(arms["ai"])
        rebuilt = self.rebuild(arms["baseline"], arms["ai"])
        report = rebuilt["pairing_report"]
        self.assertEqual(report["matched_pair_count"], 2)
        self.assertEqual(report["eligible_changed_pair_count"], 2)
        self.assertEqual(report["unpaired_baseline_count"], 1)
        self.assertEqual(report["unpaired_ai_count"], 1)
        self.assertEqual(
            report["unpaired_baseline"][0]["proposal_id"],
            "proposal-3",
        )
        self.assertEqual(
            report["unpaired_ai"][0]["proposal_id"],
            "proposal-unpaired-ai",
        )
        result = self.execute(
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
            rebuilt,
        )
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )

    def test_only_changed_action_or_exposure_is_eligible(self):
        arms = deepcopy(self.paired["source_arm_series"])
        for baseline, ai in zip(
            arms["baseline"]["observations"],
            arms["ai"]["observations"],
        ):
            ai["recommended_action"] = baseline["recommended_action"]
            ai["absolute_exposure_ratio"] = baseline[
                "absolute_exposure_ratio"
            ]
            ai["value"] = baseline["value"]
        self.rehash(arms["ai"])
        rebuilt = self.rebuild(arms["baseline"], arms["ai"])
        self.assertEqual(
            rebuilt["pairing_report"]["eligible_changed_pair_count"],
            0,
        )
        self.assertEqual(
            rebuilt["pairing_report"]["excluded_unchanged_pair_count"],
            3,
        )
        result = self.execute(
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
            rebuilt,
        )
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(
            result.reason_codes,
            ("PAIRED_SERIES_NO_ELIGIBLE_CHANGED_PAIRS",),
        )

    def test_paired_delta_and_nested_source_tampering_fail_closed(self):
        tampered = deepcopy(self.paired)
        tampered["observations"][0]["value"] = "999"
        self.rehash(tampered)
        result = self.execute(
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
            tampered,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(
            "PAIRED_SERIES_OBSERVATION_REPLAY_MISMATCH",
            result.reason_codes,
        )

        malformed_source = deepcopy(self.paired)
        del malformed_source["source_arm_series"]["baseline"][
            "approved_production_capital_usdt"
        ]
        self.rehash(malformed_source)
        result = self.execute(
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
            malformed_source,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("PAIRED_SOURCE_SERIES_SCHEMA_INVALID",),
        )

    def test_arm_scope_policy_capital_and_window_must_match(self):
        mutators = (
            lambda arm: arm.__setitem__(
                "approved_production_capital_usdt",
                "999",
            ),
            lambda arm: arm.__setitem__(
                "accounting_policy_hash",
                "9" * 64,
            ),
            lambda arm: arm["scope"].__setitem__(
                "evaluation_window_end",
                "2025-01-05T00:00:00Z",
            ),
        )
        for mutate in mutators:
            with self.subTest(mutate=mutate):
                arms = deepcopy(self.paired["source_arm_series"])
                mutate(arms["ai"])
                self.rehash(arms["ai"])
                with self.assertRaises(ValueError):
                    self.rebuild(arms["baseline"], arms["ai"])

    def test_wrong_series_kind_cannot_use_paired_or_leave_out_estimators(self):
        endpoint = self.paired["source_arm_series"]["ai"]
        result = self.execute(
            "ONE_SIDED_95_PAIRED_MOVING_BLOCK_BOOTSTRAP_V1",
            endpoint,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_KIND_MISMATCH",),
        )
        missing_fold = deepcopy(self.robustness)
        del missing_fold["observations"][0]["fold_id"]
        self.rehash(missing_fold)
        result = self.execute(
            "LEAVE_MAX_POSITIVE_FOLD_OUT_MBB_LCB95_V1",
            missing_fold,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_FOLD_ID_MISSING",),
        )

    def test_release_reference_binds_model_baseline_arms_and_sources(self):
        series = self.paired
        arm_hashes = [
            series["source_arm_series"][arm]["series_hash"]
            for arm in ("baseline", "ai")
        ]
        evidence = {
            **series["scope"],
            "model_bundle_id": series["model_bundle_id"],
            "model_bundle_hash": series["model_bundle_hash"],
            "ai_endpoint": series["ai_endpoint"],
            "experiment_manifest_id": series["experiment_manifest_id"],
            "experiment_manifest_hash": series["experiment_manifest_hash"],
            "approved_production_capital_usdt": series[
                "approved_production_capital_usdt"
            ],
            "policy_binding_hashes": {
                "accounting_policy_id": series["accounting_policy_hash"],
                "cost_allocation_policy_id": series[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": series["split_policy_hash"],
                "statistical_design_policy_id": series[
                    "statistical_design_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "statistical_series_snapshot": {
                    "artifact_id": series["series_id"],
                    "artifact_hash": series["series_hash"],
                }
            },
            "artifact_hashes": [
                series["series_hash"],
                *arm_hashes,
                *series["source_economic_snapshot_hashes"],
            ],
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash="a" * 64,
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "statistical_series_snapshot": series["series_hash"]
            },
            capital_values={},
            artifact_documents={
                "statistical_series_snapshot": series,
                "experiment_manifest": {
                    "baseline_recipe_release_id": series[
                        "baseline_recipe_release_id"
                    ],
                    "baseline_recipe_release_hash": series[
                        "baseline_recipe_release_hash"
                    ],
                },
            },
        )
        self.assertEqual(
            PolicyBundle._statistical_series_reference_reasons(
                evidence,
                trust,
            ),
            (),
        )

        wrong = deepcopy(evidence)
        wrong["model_bundle_hash"] = "9" * 64
        wrong["artifact_hashes"].remove(arm_hashes[0])
        reasons = PolicyBundle._statistical_series_reference_reasons(
            wrong,
            trust,
        )
        self.assertIn("PAIRED_SERIES_MODEL_BUNDLE_MISMATCH", reasons)
        self.assertIn("STATISTICAL_SERIES_SOURCE_HASH_MISSING", reasons)

    def test_ai_release_can_have_an_independent_baseline_ledger(self):
        baseline = deepcopy(self.economic)
        baseline["scope"]["evaluation_ledger"] = "BASELINE_LEDGER"
        baseline["scope"]["release_route"] = "AI_ENHANCED"
        baseline["scope"]["recipe_release_id"] = "baseline-recipe-v1"
        baseline["scope"]["recipe_release_hash"] = "1" * 64
        baseline["snapshot_hash"] = economic_snapshot_hash(baseline)
        self.assertNotIn(
            "ECONOMIC_SNAPSHOT_LEDGER_ROUTE_MISMATCH",
            economic_snapshot_reasons(baseline),
        )
        evidence = {
            **baseline["scope"],
            "recipe_release_id": "ai-recipe-v1",
            "recipe_release_hash": "2" * 64,
            "policy_binding_hashes": {
                "accounting_policy_id": baseline[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": baseline[
                    "cost_allocation_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "economic_ledger_snapshot": {
                    "artifact_id": baseline["snapshot_id"],
                    "artifact_hash": baseline["snapshot_hash"],
                }
            },
            "artifact_hashes": [
                baseline["snapshot_hash"],
                baseline["source_ledger_hash"],
                baseline["source_projection_hash"],
            ],
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash="a" * 64,
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "economic_ledger_snapshot": baseline["snapshot_hash"]
            },
            capital_values={},
            artifact_documents={
                "economic_ledger_snapshot": baseline,
                "experiment_manifest": {
                    "baseline_recipe_release_id": "baseline-recipe-v1",
                    "baseline_recipe_release_hash": "1" * 64,
                },
            },
        )
        self.assertEqual(
            PolicyBundle._economic_snapshot_reference_reasons(
                evidence,
                trust,
            ),
            (),
        )

        impossible = deepcopy(self.economic)
        impossible["scope"]["evaluation_ledger"] = "AI_LEDGER"
        impossible["scope"]["release_route"] = "BASELINE_ONLY"
        impossible["snapshot_hash"] = economic_snapshot_hash(impossible)
        self.assertIn(
            "ECONOMIC_SNAPSHOT_LEDGER_ROUTE_MISMATCH",
            economic_snapshot_reasons(impossible),
        )

    def test_supporting_observation_requires_both_arm_series_hashes(self):
        metric_id = "ai_paired_delta_economic_net_log_growth_lcb95"
        resolver = MetricResolver(
            load_json_strict(
                ROOT / "config" / "release-metrics-v1.1.json"
            )
        )
        definition = resolver.resolve(metric_id)
        estimator_inputs = {
            "statistical_series_snapshot": self.paired,
        }
        execution = self.registry.execute(
            definition["estimator_id"],
            estimator_inputs,
        )
        arm_hashes = [
            self.paired["source_arm_series"][arm]["series_hash"]
            for arm in ("baseline", "ai")
        ]
        source_hashes = [
            self.paired["series_hash"],
            *arm_hashes,
            *self.paired["source_economic_snapshot_hashes"],
        ]
        observation = {
            "observation_id": "paired-supporting-observation-1",
            "observation_hash": "0" * 64,
            "metric_id": metric_id,
            "metric_unit": definition["unit"],
            "estimator_id": definition["estimator_id"],
            "implementation_id": execution.implementation_id,
            "implementation_version": execution.implementation_version,
            "estimator_inputs": estimator_inputs,
            "status": execution.status,
            "value": execution.value,
            "reason_codes": list(execution.reason_codes),
            "estimator_execution_hash": execution.execution_hash,
            "source_artifact_hashes": source_hashes,
        }
        observation["observation_hash"] = supporting_observation_hash(
            observation
        )
        expected_scope = {
            **self.paired["scope"],
            "model_bundle_id": self.paired["model_bundle_id"],
            "model_bundle_hash": self.paired["model_bundle_hash"],
            "ai_endpoint": self.paired["ai_endpoint"],
            "policy_binding_hashes": {
                "accounting_policy_id": self.paired[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": self.paired[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": self.paired["split_policy_hash"],
                "statistical_design_policy_id": self.paired[
                    "statistical_design_policy_hash"
                ],
            },
            "experiment_manifest_id": self.paired[
                "experiment_manifest_id"
            ],
            "experiment_manifest_hash": self.paired[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": self.paired[
                "approved_production_capital_usdt"
            ],
        }
        signature = "P" * 86 + "=="
        bundle = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "paired-supporting-bundle-1",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(expected_scope),
            "policy_bundle_hash": "a" * 64,
            "evaluator_build_hash": "b" * 64,
            "computed_at": "2025-01-05T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "statistics-authority",
                "signed_at": "2025-01-05T00:00:02Z",
                "signature_base64": signature,
            },
        }
        bundle["bundle_hash"] = supporting_observation_bundle_hash(bundle)
        schema = load_json_strict(
            ROOT / "config" / "supporting-observation-bundle-v1.schema.json"
        )
        validation = validate_supporting_observation_bundle(
            bundle,
            schema=schema,
            expected_scope=expected_scope,
            policy_bundle_hash="a" * 64,
            evaluator_build_hash="b" * 64,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: bundle["bundle_hash"]},
            first_result_revealed_at="2025-01-04T00:00:00Z",
        )
        self.assertTrue(validation.valid, validation.reason_codes)

        incomplete = deepcopy(bundle)
        incomplete["observations"][0]["source_artifact_hashes"].remove(
            arm_hashes[0]
        )
        incomplete["observations"][0]["observation_hash"] = (
            supporting_observation_hash(incomplete["observations"][0])
        )
        incomplete["bundle_hash"] = supporting_observation_bundle_hash(
            incomplete
        )
        validation = validate_supporting_observation_bundle(
            incomplete,
            schema=schema,
            expected_scope=expected_scope,
            policy_bundle_hash="a" * 64,
            evaluator_build_hash="b" * 64,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={
                signature: incomplete["bundle_hash"],
            },
            first_result_revealed_at="2025-01-04T00:00:00Z",
        )
        self.assertFalse(validation.valid)
        self.assertIn(
            f"SUPPORTING_STATISTICAL_SOURCE_INCOMPLETE:{metric_id}",
            validation.reason_codes,
        )


if __name__ == "__main__":
    unittest.main()
