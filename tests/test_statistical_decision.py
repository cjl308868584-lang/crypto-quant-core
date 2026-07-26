import json
import unittest
from copy import deepcopy
from decimal import ROUND_DOWN, getcontext
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.statistical_decision import (
    achieved_power_at_mere,
    build_statistical_decision_snapshot,
    holm_family_adjusted_primary_pass,
    primary_endpoint_ci_width,
    statistical_decision_snapshot_hash,
    statistical_decision_snapshot_reasons,
    statistical_trial_registry_hash,
)
from crypto_quant.statistics import statistical_series_hash

from tests.factories import statistical_decision_inputs

ROOT = Path(__file__).resolve().parents[1]


def build_snapshot(**fixture_overrides):
    inputs = statistical_decision_inputs(**fixture_overrides)
    return build_statistical_decision_snapshot(
        snapshot_id="statistical-decision-fixture",
        release_gate_policy_id="release-gates-v1.1",
        release_gate_policy_version="1.1.5",
        metric_catalog_id="release-metrics-v1.1",
        metric_catalog_version="1.1.5",
        statistical_design_policy_id="statistics-replay",
        statistical_design_policy_hash="6" * 64,
        experiment_manifest_id="experiment-replay",
        experiment_manifest_hash="7" * 64,
        generated_at="2025-01-07T00:00:00Z",
        **inputs,
    )


class StatisticalDecisionTests(unittest.TestCase):
    def test_schema_accepts_computed_and_inconclusive_but_rejects_extra_fields(
        self,
    ):
        schema = json.loads(
            (
                ROOT / "config" / "statistical-decision-snapshot-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        computed = build_snapshot()
        inconclusive = build_snapshot(current_values=("1", "2", "3"))

        self.assertEqual(list(validator.iter_errors(computed)), [])
        self.assertEqual(list(validator.iter_errors(inconclusive)), [])
        tampered = deepcopy(computed)
        tampered["uploaded_power_claim"] = "1"
        self.assertTrue(list(validator.iter_errors(tampered)))

    def test_builder_replays_literal_ci_holm_ess_and_power(self):
        snapshot = build_snapshot()

        self.assertEqual(snapshot["analysis_status"], "COMPUTED")
        self.assertEqual(snapshot["analysis_reason_codes"], [])
        self.assertEqual(
            snapshot["family_results"],
            [
                {
                    "candidate_id": "candidate-competitor",
                    "candidate_status": "EVALUATED",
                    "raw_p_value": (
                        "0.000999000999000999000999000999000999000999000999001"
                    ),
                    "holm_rank": 1,
                    "holm_threshold": (
                        "0.016666666666666666666666666666666666666666666666667"
                    ),
                    "step_reached": True,
                    "rejected": True,
                },
                {
                    "candidate_id": "candidate-current",
                    "candidate_status": "EVALUATED",
                    "raw_p_value": (
                        "0.000999000999000999000999000999000999000999000999001"
                    ),
                    "holm_rank": 2,
                    "holm_threshold": "0.025",
                    "step_reached": True,
                    "rejected": True,
                },
                {
                    "candidate_id": "candidate-aborted",
                    "candidate_status": "ABORTED",
                    "raw_p_value": "1",
                    "holm_rank": 3,
                    "holm_threshold": "0.05",
                    "step_reached": True,
                    "rejected": False,
                },
            ],
        )
        self.assertEqual(
            snapshot["current_candidate_results"],
            {
                "observed_statistic": "39",
                "effective_event_count": 2,
                "ci_lower": "29",
                "ci_upper": "49",
                "ci_width": "20",
                "holm_adjusted_alpha": "0.025",
                "holm_rejected": True,
                "minimum_economic_effect": "2",
                "achieved_power": "0.031",
            },
        )
        self.assertEqual(
            primary_endpoint_ci_width(
                {"statistical_decision_snapshot": snapshot}
            ),
            ("COMPUTED", "20", ()),
        )
        self.assertEqual(
            achieved_power_at_mere(
                {"statistical_decision_snapshot": snapshot}
            ),
            ("COMPUTED", "0.031", ()),
        )
        self.assertEqual(
            holm_family_adjusted_primary_pass(
                {"statistical_decision_snapshot": snapshot}
            ),
            ("COMPUTED", True, ()),
        )

    def test_holm_ties_break_by_candidate_id(self):
        snapshot = build_snapshot()
        rows = snapshot["family_results"]

        self.assertEqual(rows[0]["raw_p_value"], rows[1]["raw_p_value"])
        self.assertEqual(
            [rows[0]["candidate_id"], rows[1]["candidate_id"]],
            ["candidate-competitor", "candidate-current"],
        )

    def test_holm_stops_after_first_failed_step(self):
        snapshot = build_snapshot(
            current_values=("-1", "0", "-1", "0", "-1", "0"),
            competitor_values=("-1", "0", "-1", "0", "-1", "0"),
        )

        self.assertEqual(snapshot["analysis_status"], "COMPUTED")
        reached = [
            row["candidate_id"]
            for row in snapshot["family_results"]
            if row["step_reached"]
        ]
        self.assertEqual(len(reached), 1)
        self.assertFalse(any(row["rejected"] for row in snapshot["family_results"]))

    def test_aborted_trial_remains_in_family_with_p_one(self):
        snapshot = build_snapshot()
        aborted = next(
            row
            for row in snapshot["family_results"]
            if row["candidate_id"] == "candidate-aborted"
        )

        self.assertEqual(len(snapshot["trial_registry"]), 3)
        self.assertEqual(aborted["raw_p_value"], "1")
        self.assertFalse(aborted["rejected"])

    def test_trial_registry_omission_or_hash_mismatch_fails(self):
        snapshot = build_snapshot()
        tampered = deepcopy(snapshot)
        tampered["trial_registry"].pop(0)
        tampered["snapshot_hash"] = statistical_decision_snapshot_hash(tampered)

        self.assertIn(
            "STATISTICAL_DECISION_TRIAL_COUNT_MISMATCH",
            statistical_decision_snapshot_reasons(tampered),
        )
        self.assertIn(
            "STATISTICAL_DECISION_TRIAL_REGISTRY_HASH_MISMATCH",
            statistical_decision_snapshot_reasons(tampered),
        )

    def test_source_series_tampering_fails_even_after_outer_rehash(self):
        snapshot = build_snapshot()
        tampered = deepcopy(snapshot)
        member = next(
            item
            for item in tampered["trial_registry"]
            if item["candidate_id"] == "candidate-current"
        )
        member["source_series_snapshot"]["observations"][0]["value"] = "400"
        tampered["snapshot_hash"] = statistical_decision_snapshot_hash(tampered)

        self.assertIn(
            "STATISTICAL_DECISION_SOURCE_SERIES_INVALID:candidate-current",
            statistical_decision_snapshot_reasons(tampered),
        )

    def test_cached_family_result_tampering_fails_after_outer_rehash(self):
        snapshot = build_snapshot()
        tampered = deepcopy(snapshot)
        tampered["family_results"][0]["rejected"] = False
        tampered["snapshot_hash"] = statistical_decision_snapshot_hash(tampered)

        self.assertEqual(
            statistical_decision_snapshot_reasons(tampered),
            ("STATISTICAL_DECISION_FAMILY_RESULTS_REPLAY_MISMATCH",),
        )

    def test_cached_ci_or_power_tampering_fails_after_outer_rehash(self):
        snapshot = build_snapshot()
        for field, value in (("ci_width", "19"), ("achieved_power", "0.99")):
            with self.subTest(field=field):
                tampered = deepcopy(snapshot)
                tampered["current_candidate_results"][field] = value
                tampered["snapshot_hash"] = statistical_decision_snapshot_hash(
                    tampered
                )
                self.assertEqual(
                    statistical_decision_snapshot_reasons(tampered),
                    (
                        "STATISTICAL_DECISION_CURRENT_RESULTS_REPLAY_MISMATCH",
                    ),
                )

    def test_current_candidate_must_be_evaluated(self):
        inputs = statistical_decision_inputs()
        inputs["current_candidate_id"] = "candidate-aborted"

        with self.assertRaisesRegex(
            ValueError,
            "STATISTICAL_DECISION_CURRENT_CANDIDATE_INVALID",
        ):
            build_statistical_decision_snapshot(
                snapshot_id="statistical-decision-invalid-current",
                release_gate_policy_id="release-gates-v1.1",
                release_gate_policy_version="1.1.5",
                metric_catalog_id="release-metrics-v1.1",
                metric_catalog_version="1.1.5",
                statistical_design_policy_id="statistics-replay",
                statistical_design_policy_hash="6" * 64,
                experiment_manifest_id="experiment-replay",
                experiment_manifest_hash="7" * 64,
                generated_at="2025-01-07T00:00:00Z",
                **inputs,
            )

    def test_candidate_bootstrap_design_must_match_frozen_design(self):
        inputs = statistical_decision_inputs()
        current = next(
            item
            for item in inputs["trial_registry"]
            if item["candidate_id"] == "candidate-current"
        )
        current["source_series_snapshot"]["bootstrap_design"]["seed"] = 30
        current["source_series_snapshot"]["series_hash"] = statistical_series_hash(
            current["source_series_snapshot"]
        )
        current["source_series_hash"] = current["source_series_snapshot"][
            "series_hash"
        ]
        inputs["expected_trial_registry_hash"] = statistical_trial_registry_hash(
            inputs["trial_registry"]
        )

        with self.assertRaisesRegex(
            ValueError,
            "STATISTICAL_DECISION_BOOTSTRAP_DESIGN_MISMATCH",
        ):
            build_statistical_decision_snapshot(
                snapshot_id="statistical-decision-design-mismatch",
                release_gate_policy_id="release-gates-v1.1",
                release_gate_policy_version="1.1.5",
                metric_catalog_id="release-metrics-v1.1",
                metric_catalog_version="1.1.5",
                statistical_design_policy_id="statistics-replay",
                statistical_design_policy_hash="6" * 64,
                experiment_manifest_id="experiment-replay",
                experiment_manifest_hash="7" * 64,
                generated_at="2025-01-07T00:00:00Z",
                **inputs,
            )

    def test_source_one_sided_lcb_and_decision_two_sided_ci_are_compatible(self):
        snapshot = build_snapshot()
        source_sides = {
            item["source_series_snapshot"]["bootstrap_design"][
                "confidence_side"
            ]
            for item in snapshot["trial_registry"]
            if item["candidate_status"] == "EVALUATED"
        }

        self.assertEqual(source_sides, {"LOWER_ONE_SIDED"})
        self.assertEqual(snapshot["design"]["confidence_side"], "TWO_SIDED")
        self.assertEqual(snapshot["analysis_status"], "COMPUTED")

    def test_insufficient_blocks_builds_replayable_inconclusive_snapshot(self):
        snapshot = build_snapshot(current_values=("1", "2", "3"))

        self.assertEqual(snapshot["analysis_status"], "INCONCLUSIVE")
        self.assertEqual(
            snapshot["analysis_reason_codes"],
            ["STATISTICAL_DECISION_INSUFFICIENT_BLOCKS:candidate-current"],
        )
        self.assertEqual(snapshot["family_results"], [])
        self.assertIsNone(snapshot["current_candidate_results"])
        self._assert_all_estimators_inconclusive(snapshot)

    def test_zero_variance_builds_replayable_inconclusive_snapshot(self):
        snapshot = build_snapshot(
            current_values=("1", "1", "1", "1", "1", "1")
        )

        self.assertEqual(snapshot["analysis_status"], "INCONCLUSIVE")
        self.assertEqual(
            snapshot["analysis_reason_codes"],
            ["STATISTICAL_DECISION_ZERO_VARIANCE:candidate-current"],
        )
        self._assert_all_estimators_inconclusive(snapshot)

    def test_bootstrap_resolution_below_holm_alpha_is_inconclusive(self):
        inputs = statistical_decision_inputs()
        for index in range(49):
            inputs["trial_registry"].append(
                {
                    "candidate_id": f"candidate-unused-{index:02d}",
                    "candidate_status": "INVALID",
                    "recipe_release_id": f"recipe-unused-{index:02d}",
                    "recipe_release_hash": f"{index + 10:064x}",
                    "source_series_snapshot": None,
                    "source_series_hash": None,
                }
            )
        inputs["trial_registry"].sort(key=lambda item: item["candidate_id"])
        inputs["expected_actual_total_trials"] = len(inputs["trial_registry"])
        inputs["expected_trial_registry_hash"] = statistical_trial_registry_hash(
            inputs["trial_registry"]
        )
        snapshot = build_statistical_decision_snapshot(
            snapshot_id="statistical-decision-resolution",
            release_gate_policy_id="release-gates-v1.1",
            release_gate_policy_version="1.1.5",
            metric_catalog_id="release-metrics-v1.1",
            metric_catalog_version="1.1.5",
            statistical_design_policy_id="statistics-replay",
            statistical_design_policy_hash="6" * 64,
            experiment_manifest_id="experiment-replay",
            experiment_manifest_hash="7" * 64,
            generated_at="2025-01-07T00:00:00Z",
            **inputs,
        )

        self.assertEqual(snapshot["analysis_status"], "INCONCLUSIVE")
        self.assertEqual(
            snapshot["analysis_reason_codes"],
            ["STATISTICAL_DECISION_BOOTSTRAP_RESOLUTION_INSUFFICIENT"],
        )

    def test_global_decimal_context_does_not_change_results_or_hash(self):
        original = build_snapshot()
        context = getcontext()
        old_precision = context.prec
        old_rounding = context.rounding
        try:
            context.prec = 7
            context.rounding = ROUND_DOWN
            changed = build_snapshot()
        finally:
            context.prec = old_precision
            context.rounding = old_rounding

        self.assertEqual(changed, original)

    def _assert_all_estimators_inconclusive(self, snapshot):
        for estimator in (
            primary_endpoint_ci_width,
            achieved_power_at_mere,
            holm_family_adjusted_primary_pass,
        ):
            with self.subTest(estimator=estimator.__name__):
                status, value, reasons = estimator(
                    {"statistical_decision_snapshot": snapshot}
                )
                self.assertEqual(status, "INCONCLUSIVE")
                self.assertIsNone(value)
                self.assertEqual(
                    reasons,
                    tuple(snapshot["analysis_reason_codes"]),
                )


if __name__ == "__main__":
    unittest.main()
