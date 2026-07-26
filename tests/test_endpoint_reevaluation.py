import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.evidence import artifact_self_hash
from crypto_quant.evidence import EvidenceTrustContext
from crypto_quant.release import PolicyBundle
from crypto_quant.reevaluation import (
    build_endpoint_reevaluation_snapshot,
    leave_max_positive_delta_event_out_endpoint_reevaluation,
    leave_max_positive_delta_fold_out_endpoint_reevaluation,
)
from crypto_quant.statistics import (
    paired_ai_delta_series_snapshot,
    statistical_series_hash,
)


ROOT = Path(__file__).resolve().parents[1]


class EndpointReevaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        golden = json.loads(
            (
                ROOT / "config" / "estimator-golden-vectors-v1.json"
            ).read_text(encoding="utf-8")
        )
        cls.source = golden["fixtures"][
            "statistical-paired-series-valid"
        ]
        cls.fold = golden["fixtures"][
            "endpoint-fold-reevaluation-valid"
        ]
        cls.event = golden["fixtures"][
            "endpoint-event-reevaluation-valid"
        ]
        cls.identity = {
            "release_gate_policy_id": "release-gates-v1.1",
            "release_gate_policy_version": "1.1.4",
            "metric_catalog_id": "release-metrics-v1.1",
            "metric_catalog_version": "1.1.3",
        }
        cls.schema = json.loads(
            (
                ROOT
                / "config"
                / "endpoint-reevaluation-snapshot-v1.schema.json"
            ).read_text(encoding="utf-8")
        )

    def inputs(self, snapshot, source=None):
        return {
            "endpoint_reevaluation_snapshot": snapshot,
            "statistical_series_snapshot": source or self.source,
            "endpoint_gate_definitions": snapshot[
                "endpoint_gate_definitions"
            ],
            "policy_identity": self.identity,
        }

    def computed_source(self):
        arms = deepcopy(self.source["source_arm_series"])
        for arm in arms.values():
            arm["bootstrap_design"]["minimum_block_count"] = 2
            arm["series_hash"] = statistical_series_hash(arm)
        return paired_ai_delta_series_snapshot(
            series_id="paired-reevaluation-computed",
            baseline_series_snapshot=arms["baseline"],
            ai_series_snapshot=arms["ai"],
            model_bundle_id=self.source["model_bundle_id"],
            model_bundle_hash=self.source["model_bundle_hash"],
            ai_endpoint=self.source["ai_endpoint"],
            generated_at=self.source["generated_at"],
        )

    def one_pair_source(self):
        arms = deepcopy(self.source["source_arm_series"])
        for arm in arms.values():
            arm["observations"] = arm["observations"][:1]
            arm["source_economic_snapshot_hashes"] = [
                arm["observations"][0][
                    "source_economic_snapshot_hash"
                ]
            ]
            arm["scope"]["evaluation_window_end"] = arm[
                "observations"
            ][0]["period_end"]
            arm["series_hash"] = statistical_series_hash(arm)
        return paired_ai_delta_series_snapshot(
            series_id="paired-one-pair",
            baseline_series_snapshot=arms["baseline"],
            ai_series_snapshot=arms["ai"],
            model_bundle_id=self.source["model_bundle_id"],
            model_bundle_hash=self.source["model_bundle_hash"],
            ai_endpoint=self.source["ai_endpoint"],
            generated_at=self.source["generated_at"],
        )

    def test_frozen_fold_and_event_artifacts_replay_exactly(self):
        cases = (
            (
                self.fold,
                leave_max_positive_delta_fold_out_endpoint_reevaluation,
                "fold-2",
            ),
            (
                self.event,
                leave_max_positive_delta_event_out_endpoint_reevaluation,
                (
                    "pair_570e54772edd52bab3b579a1e5a7341c"
                    "2f4e800edba21c11b636c51571132639"
                ),
            ),
        )
        for snapshot, estimator, excluded in cases:
            with self.subTest(method=snapshot["exclusion_method"]):
                self.assertFalse(
                    list(
                        Draft202012Validator(self.schema).iter_errors(
                            snapshot
                        )
                    )
                )
                self.assertEqual(
                    snapshot["reevaluation_hash"],
                    artifact_self_hash(
                        snapshot,
                        "reevaluation_hash",
                    ),
                )
                self.assertEqual(snapshot["excluded_unit_id"], excluded)
                self.assertEqual(snapshot["gate_results"], [])
                self.assertEqual(snapshot["result"], "INCONCLUSIVE")
                self.assertEqual(
                    estimator(self.inputs(snapshot)),
                    (
                        "INCONCLUSIVE",
                        None,
                        ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
                    ),
                )

    def test_builder_reruns_complete_growth_gate_after_exclusion(self):
        rebuilt = build_endpoint_reevaluation_snapshot(
            reevaluation_id=self.fold["reevaluation_id"],
            source_paired_series=self.source,
            endpoint_gate_group_id="AI_ENDPOINT.GROWTH",
            endpoint_gate_definitions=self.fold[
                "endpoint_gate_definitions"
            ],
            policy_identity=self.identity,
            exclusion_method="MAX_POSITIVE_DELTA_FOLD",
            generated_at=self.fold["generated_at"],
        )
        self.assertEqual(rebuilt, self.fold)
        self.assertEqual(len(rebuilt["endpoint_gate_definitions"]), 1)
        self.assertEqual(rebuilt["gate_results"], [])
        self.assertEqual(rebuilt["result"], "INCONCLUSIVE")

    def test_a_stricter_frozen_endpoint_threshold_returns_false(self):
        source = self.computed_source()
        gate = deepcopy(self.fold["endpoint_gate_definitions"][0])
        gate["threshold"] = "0.005"
        artifact = build_endpoint_reevaluation_snapshot(
            reevaluation_id="strict-threshold-reevaluation",
            source_paired_series=source,
            endpoint_gate_group_id="AI_ENDPOINT.GROWTH",
            endpoint_gate_definitions=[gate],
            policy_identity=self.identity,
            exclusion_method="MAX_POSITIVE_DELTA_FOLD",
            generated_at=self.fold["generated_at"],
        )
        self.assertEqual(artifact["result"], "FAIL")
        self.assertEqual(artifact["gate_results"][0]["result"], "FAIL")
        self.assertEqual(
            leave_max_positive_delta_fold_out_endpoint_reevaluation(
                self.inputs(artifact, source)
            ),
            ("COMPUTED", False, ()),
        )

    def test_removing_the_only_positive_pair_is_inconclusive(self):
        source = self.one_pair_source()
        artifact = build_endpoint_reevaluation_snapshot(
            reevaluation_id="empty-after-exclusion",
            source_paired_series=source,
            endpoint_gate_group_id="AI_ENDPOINT.GROWTH",
            endpoint_gate_definitions=self.fold[
                "endpoint_gate_definitions"
            ],
            policy_identity=self.identity,
            exclusion_method="MAX_POSITIVE_DELTA_FOLD",
            generated_at=self.fold["generated_at"],
        )
        self.assertEqual(artifact["result"], "INCONCLUSIVE")
        self.assertEqual(artifact["gate_results"], [])
        self.assertEqual(
            leave_max_positive_delta_fold_out_endpoint_reevaluation(
                self.inputs(artifact, source)
            ),
            (
                "INCONCLUSIVE",
                None,
                ("PAIRED_SERIES_EMPTY_AFTER_EXCLUSION",),
            ),
        )

    def test_builder_rejects_method_and_gate_group_mismatch(self):
        with self.assertRaisesRegex(
            ValueError,
            "ENDPOINT_REEVALUATION_GATE_GROUP_MISMATCH",
        ):
            build_endpoint_reevaluation_snapshot(
                reevaluation_id="wrong-group",
                source_paired_series=self.source,
                endpoint_gate_group_id="AUDIT_AI_ENDPOINT.GROWTH",
                endpoint_gate_definitions=self.fold[
                    "endpoint_gate_definitions"
                ],
                policy_identity=self.identity,
                exclusion_method="MAX_POSITIVE_DELTA_FOLD",
                generated_at=self.fold["generated_at"],
            )

    def test_artifact_source_policy_and_gate_tampering_fail_closed(self):
        cases = []

        hash_tampered = deepcopy(self.fold)
        hash_tampered["excluded_unit_id"] = "fold-1"
        cases.append(
            (
                hash_tampered,
                self.source,
                hash_tampered["endpoint_gate_definitions"],
                self.identity,
                "ENDPOINT_REEVALUATION_HASH_MISMATCH",
            )
        )

        source_tampered = deepcopy(self.source)
        source_tampered["series_hash"] = "f" * 64
        cases.append(
            (
                self.fold,
                source_tampered,
                self.fold["endpoint_gate_definitions"],
                self.identity,
                "ENDPOINT_REEVALUATION_SOURCE_HASH_MISMATCH",
            )
        )

        gate_tampered = deepcopy(self.fold["endpoint_gate_definitions"])
        gate_tampered[0]["threshold"] = "-1"
        cases.append(
            (
                self.fold,
                self.source,
                gate_tampered,
                self.identity,
                "ENDPOINT_REEVALUATION_GATE_SET_MISMATCH",
            )
        )

        policy_tampered = dict(self.identity)
        policy_tampered["release_gate_policy_version"] = "9.9.9"
        cases.append(
            (
                self.fold,
                self.source,
                self.fold["endpoint_gate_definitions"],
                policy_tampered,
                "ENDPOINT_REEVALUATION_POLICY_MISMATCH",
            )
        )

        for artifact, source, gates, identity, reason in cases:
            with self.subTest(reason=reason):
                result = (
                    leave_max_positive_delta_fold_out_endpoint_reevaluation(
                        {
                            "endpoint_reevaluation_snapshot": artifact,
                            "statistical_series_snapshot": source,
                            "endpoint_gate_definitions": gates,
                            "policy_identity": identity,
                        }
                    )
                )
                self.assertEqual(result, ("FAIL", None, (reason,)))

    def test_rehashed_claimed_output_tampering_is_detected_by_replay(self):
        tampered = deepcopy(self.fold)
        tampered["result"] = "PASS"
        tampered["reevaluation_hash"] = artifact_self_hash(
            tampered,
            "reevaluation_hash",
        )
        self.assertEqual(
            leave_max_positive_delta_fold_out_endpoint_reevaluation(
                self.inputs(tampered)
            ),
            (
                "FAIL",
                None,
                ("ENDPOINT_REEVALUATION_REPLAY_MISMATCH",),
            ),
        )

    def test_release_reference_binds_policy_scope_and_all_sources(self):
        bundle = PolicyBundle.load(ROOT / "config")
        source = self.source
        snapshot = self.fold
        arm_hashes = [
            source["source_arm_series"][arm]["series_hash"]
            for arm in ("baseline", "ai")
        ]
        evidence = {
            **source["scope"],
            "model_bundle_id": source["model_bundle_id"],
            "model_bundle_hash": source["model_bundle_hash"],
            "ai_endpoint": source["ai_endpoint"],
            "experiment_manifest_id": source[
                "experiment_manifest_id"
            ],
            "experiment_manifest_hash": source[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": source[
                "approved_production_capital_usdt"
            ],
            "policy_binding_hashes": {
                "accounting_policy_id": source[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": source[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": source["split_policy_hash"],
                "statistical_design_policy_id": source[
                    "statistical_design_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "statistical_series_snapshot": {
                    "artifact_id": source["series_id"],
                    "artifact_hash": source["series_hash"],
                },
                "endpoint_reevaluation_snapshot": {
                    "artifact_id": snapshot["reevaluation_id"],
                    "artifact_hash": snapshot["reevaluation_hash"],
                },
            },
            "artifact_hashes": [
                snapshot["reevaluation_hash"],
                snapshot["reevaluated_paired_series_hash"],
                source["series_hash"],
                *arm_hashes,
                *source["source_economic_snapshot_hashes"],
            ],
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash="a" * 64,
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "statistical_series_snapshot": source["series_hash"],
                "endpoint_reevaluation_snapshot": snapshot[
                    "reevaluation_hash"
                ],
            },
            capital_values={},
            artifact_documents={
                "statistical_series_snapshot": source,
                "endpoint_reevaluation_snapshot": snapshot,
                "experiment_manifest": {
                    "baseline_recipe_release_id": source[
                        "baseline_recipe_release_id"
                    ],
                    "baseline_recipe_release_hash": source[
                        "baseline_recipe_release_hash"
                    ],
                },
            },
        )
        self.assertEqual(
            bundle._endpoint_reevaluation_reference_reasons(
                evidence,
                trust,
                (
                    "LEAVE_MAX_POSITIVE_DELTA_FOLD_OUT_"
                    "ENDPOINT_REEVALUATION_V1"
                ),
            ),
            (),
        )

        missing = deepcopy(evidence)
        missing["artifact_hashes"].remove(
            snapshot["reevaluated_paired_series_hash"]
        )
        reasons = bundle._endpoint_reevaluation_reference_reasons(
            missing,
            trust,
            (
                "LEAVE_MAX_POSITIVE_DELTA_FOLD_OUT_"
                "ENDPOINT_REEVALUATION_V1"
            ),
        )
        self.assertIn(
            "ENDPOINT_REEVALUATION_SOURCE_HASH_MISSING",
            reasons,
        )


if __name__ == "__main__":
    unittest.main()
