import json
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_decimal
from crypto_quant.economics import (
    economic_snapshot_hash,
    economic_snapshot_reasons,
)
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.release import MetricResolver, load_json_strict
from crypto_quant.release_artifacts import (
    supporting_observation_bundle_hash,
    supporting_observation_hash,
    validate_supporting_observation_bundle,
)
from crypto_quant.statistics import (
    statistical_series_hash,
    statistical_series_reasons,
)


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64


def render_time(value):
    return value.astimezone(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def economic_snapshot(
    *,
    arm,
    index,
    start,
    ratio,
    recipe_id,
    recipe_hash,
):
    end = start + timedelta(days=1)
    start_text = render_time(start)
    end_text = render_time(end)
    with localcontext() as context:
        context.prec = 50
        ending = canonical_decimal(Decimal("1000") * Decimal(ratio))
    snapshot = {
        "$schema": "./economic-ledger-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": f"{arm}-economic-{index}",
        "snapshot_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_ledger_hash": business_hash(
            {"arm": arm, "index": index, "source": "ledger"}
        ),
        "source_projection_hash": business_hash(
            {"arm": arm, "index": index, "source": "projection"}
        ),
        "accounting_policy_id": "accounting-v1",
        "accounting_policy_hash": HASH_A,
        "cost_allocation_policy_id": "cost-v1",
        "cost_allocation_policy_hash": HASH_B,
        "scope": {
            "account_id": "account-1",
            "evaluation_ledger": (
                "BASELINE_LEDGER" if arm == "reference" else "AI_LEDGER"
            ),
            "release_route": "AI_ENHANCED",
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "recipe_release_id": recipe_id,
            "recipe_release_hash": recipe_hash,
            "deployment_line_id": "line-1",
            "deployment_line_hash": HASH_F,
            "evaluation_window_start": start_text,
            "evaluation_window_end": end_text,
        },
        "reporting_asset": "USDT",
        "window_event_convention": "START_EXCLUSIVE_END_INCLUSIVE",
        "starting_liquidation_equity_usdt": "1000",
        "ending_liquidation_equity_usdt": ending,
        "opening_positions": [],
        "fills": [],
        "funding_cashflows": [],
        "external_cash_flows": [],
        "allocated_costs": [],
        "equity_points": [
            {
                "equity_snapshot_id": f"{arm}-equity-{index}-start",
                "as_of": start_text,
                "marked_equity_usdt": "1000",
                "liquidation_equity_usdt": "1000",
                "spot_notional_usdt": "0",
                "perp_notional_usdt": "0",
                "active_order_risk_increasing_notional_usdt": "0",
                "active_order_unknown_notional_usdt": "0",
                "expected_exit_fee_accrued_usdt": "0",
                "conservative_close_verified": True,
                "is_utc_day_start": True,
                "position_cost_bases": [],
            },
            {
                "equity_snapshot_id": f"{arm}-equity-{index}-end",
                "as_of": end_text,
                "marked_equity_usdt": ending,
                "liquidation_equity_usdt": ending,
                "spot_notional_usdt": "0",
                "perp_notional_usdt": "0",
                "active_order_risk_increasing_notional_usdt": "0",
                "active_order_unknown_notional_usdt": "0",
                "expected_exit_fee_accrued_usdt": "0",
                "conservative_close_verified": True,
                "is_utc_day_start": True,
                "position_cost_bases": [],
            },
        ],
        "generated_at": end_text,
        "replay_verified": True,
    }
    snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
    assert economic_snapshot_reasons(snapshot) == ()
    return snapshot


def arm_series(*, arm, ratios, recipe_id, recipe_hash):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    snapshots = [
        economic_snapshot(
            arm=arm,
            index=index,
            start=start + timedelta(days=index),
            ratio=ratio,
            recipe_id=recipe_id,
            recipe_hash=recipe_hash,
        )
        for index, ratio in enumerate(ratios, start=1)
    ]
    observations = []
    for index, snapshot in enumerate(snapshots, start=1):
        with localcontext() as context:
            context.prec = 50
            value = canonical_decimal(
                (
                    Decimal(snapshot["ending_liquidation_equity_usdt"])
                    / Decimal(snapshot["starting_liquidation_equity_usdt"])
                ).ln()
            )
        observations.append(
            {
                "observation_id": f"{arm}-observation-{index}",
                "period_start": snapshot["scope"][
                    "evaluation_window_start"
                ],
                "period_end": snapshot["scope"]["evaluation_window_end"],
                "value": value,
                "calendar_month_complete": False,
                "source_economic_snapshot_hash": snapshot["snapshot_hash"],
                "proposal_id": f"proposal-{index}",
                "decision_time": snapshot["scope"][
                    "evaluation_window_start"
                ],
                "fold_id": f"fold-{index}",
                "recommended_action": (
                    "HOLD_CURRENT" if arm == "reference" else "SET_TARGET"
                ),
                "absolute_exposure_ratio": (
                    "0.25" if arm == "reference" else "0.20"
                ),
            }
        )
    series = {
        "$schema": "./statistical-series-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "series_id": f"{arm}-risk-series",
        "series_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_economic_snapshot_hashes": [
            snapshot["snapshot_hash"] for snapshot in snapshots
        ],
        "accounting_policy_id": "accounting-v1",
        "accounting_policy_hash": HASH_A,
        "cost_allocation_policy_id": "cost-v1",
        "cost_allocation_policy_hash": HASH_B,
        "split_policy_id": "split-v1",
        "split_policy_hash": HASH_C,
        "statistical_design_policy_id": "design-v1",
        "statistical_design_policy_hash": HASH_D,
        "experiment_manifest_id": "experiment-v1",
        "experiment_manifest_hash": HASH_E,
        "scope": {
            "account_id": "account-1",
            "evaluation_ledger": (
                "BASELINE_LEDGER" if arm == "reference" else "AI_LEDGER"
            ),
            "release_route": "AI_ENHANCED",
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "recipe_release_id": recipe_id,
            "recipe_release_hash": recipe_hash,
            "deployment_line_id": "line-1",
            "deployment_line_hash": HASH_F,
            "evaluation_window_start": observations[0]["period_start"],
            "evaluation_window_end": observations[-1]["period_end"],
        },
        "approved_production_capital_usdt": "1000",
        "capital_normalization": "APPROVED_CAPITAL_EVALUATION_WINDOW",
        "series_kind": "PRIMARY_ENDPOINT_CONTRIBUTION",
        "aggregation": "SUM",
        "observations": observations,
        "bootstrap_design": {
            "block_length": 1,
            "minimum_block_count": 3,
            "resample_count": 1000,
            "seed": 42,
            "confidence_level": "0.95",
            "confidence_side": "LOWER_ONE_SIDED",
            "sampling_rule": (
                "OVERLAPPING_NON_CIRCULAR_MBB_TRUNCATE_TO_N"
            ),
            "quantile_rule": "CONSERVATIVE_NEAREST_RANK_V1",
        },
        "generated_at": render_time(
            start + timedelta(days=len(observations) + 1)
        ),
        "replay_verified": True,
    }
    series["series_hash"] = statistical_series_hash(series)
    assert statistical_series_reasons(series) == ()
    return series, snapshots


class PairedRiskArtifactTests(unittest.TestCase):
    def setUp(self):
        self.reference, reference_snapshots = arm_series(
            arm="reference",
            ratios=("1.10", "0.80", "1.05", "0.90", "1.02", "0.95"),
            recipe_id="baseline-recipe-v1",
            recipe_hash="1" * 64,
        )
        self.candidate, candidate_snapshots = arm_series(
            arm="candidate",
            ratios=("1.08", "0.90", "1.04", "0.96", "1.01", "0.98"),
            recipe_id="candidate-recipe-v1",
            recipe_hash="2" * 64,
        )
        self.economic_snapshots = [
            *reference_snapshots,
            *candidate_snapshots,
        ]

    def build(self, **overrides):
        try:
            from crypto_quant.paired_risk import (
                build_paired_risk_evaluation_snapshot,
            )
        except ModuleNotFoundError as exc:
            self.fail(f"paired-risk implementation is missing: {exc}")
        arguments = {
            "snapshot_id": "paired-risk-ai-v1",
            "comparison_role": "AI_VS_RECIPE_BASELINE",
            "reference_subject": {
                "role": "RECIPE_BASELINE",
                "subject_type": "RECIPE_RELEASE",
                "subject_id": "baseline-recipe-v1",
                "subject_hash": "1" * 64,
            },
            "candidate_subject": {
                "role": "AI_CANDIDATE",
                "subject_type": "MODEL_BUNDLE",
                "subject_id": "model-bundle-v1",
                "subject_hash": "3" * 64,
            },
            "reference_series_snapshot": self.reference,
            "candidate_series_snapshot": self.candidate,
            "economic_snapshots": self.economic_snapshots,
            "generated_at": "2025-01-09T00:00:00Z",
        }
        arguments.update(overrides)
        return build_paired_risk_evaluation_snapshot(**arguments)

    def test_builder_derives_pairs_and_replays_log_return_segments(self):
        snapshot = self.build()
        self.assertEqual(snapshot["schema_version"], "1.0.0")
        self.assertEqual(snapshot["ai_endpoint"], "RISK_EFFICIENCY")
        self.assertEqual(snapshot["pairing_report"]["matched_pair_count"], 6)
        self.assertEqual(
            snapshot["pairing_report"]["changed_pair_count"],
            6,
        )
        self.assertEqual(
            snapshot["paired_segments"][1]["reference_log_returns"],
            [self.reference["observations"][1]["value"]],
        )
        self.assertEqual(
            snapshot["paired_segments"][1]["candidate_log_returns"],
            [self.candidate["observations"][1]["value"]],
        )
        self.assertEqual(
            snapshot["source_economic_snapshot_hashes"],
            [
                item["snapshot_hash"]
                for item in self.economic_snapshots
            ],
        )
        self.assertTrue(snapshot["replay_verified"])

    def test_schema_accepts_exact_artifact_and_rejects_unknown_field(self):
        snapshot = self.build()
        schema = json.loads(
            (
                ROOT
                / "config"
                / "paired-risk-evaluation-snapshot-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(snapshot)), [])
        malformed = deepcopy(snapshot)
        malformed["untrusted_scalar_mdd"] = "0.01"
        self.assertNotEqual(list(validator.iter_errors(malformed)), [])

    def test_minor_candidate_vs_active_has_distinct_arm_roles(self):
        reference = deepcopy(self.reference)
        reference["scope"]["evaluation_ledger"] = "AI_LEDGER"
        reference["scope"]["recipe_release_id"] = "candidate-recipe-v1"
        reference["scope"]["recipe_release_hash"] = "2" * 64
        reference["series_hash"] = statistical_series_hash(reference)
        economic = deepcopy(self.economic_snapshots)
        for snapshot in economic[:6]:
            snapshot["scope"]["evaluation_ledger"] = "AI_LEDGER"
            snapshot["scope"]["recipe_release_id"] = "candidate-recipe-v1"
            snapshot["scope"]["recipe_release_hash"] = "2" * 64
            snapshot["snapshot_hash"] = economic_snapshot_hash(snapshot)
        for observation, snapshot in zip(
            reference["observations"],
            economic[:6],
        ):
            observation["source_economic_snapshot_hash"] = snapshot[
                "snapshot_hash"
            ]
        reference["source_economic_snapshot_hashes"] = [
            snapshot["snapshot_hash"] for snapshot in economic[:6]
        ]
        reference["series_hash"] = statistical_series_hash(reference)
        snapshot = self.build(
            comparison_role="MINOR_CANDIDATE_VS_ACTIVE_BUNDLE",
            reference_subject={
                "role": "ACTIVE_BUNDLE",
                "subject_type": "MODEL_BUNDLE",
                "subject_id": "active-bundle-v1",
                "subject_hash": "4" * 64,
            },
            candidate_subject={
                "role": "MINOR_CANDIDATE",
                "subject_type": "MODEL_BUNDLE",
                "subject_id": "model-bundle-v1",
                "subject_hash": "3" * 64,
            },
            reference_series_snapshot=reference,
            economic_snapshots=economic,
        )
        self.assertEqual(
            snapshot["reference_arm"]["role"],
            "ACTIVE_BUNDLE",
        )
        self.assertEqual(
            snapshot["candidate_arm"]["role"],
            "MINOR_CANDIDATE",
        )

    def test_nested_series_tampering_fails_after_outer_rehash(self):
        snapshot = self.build()
        snapshot["reference_arm"]["statistical_series_snapshot"][
            "observations"
        ][0]["value"] = "9"
        from crypto_quant.paired_risk import (
            paired_risk_evaluation_snapshot_hash,
            paired_risk_evaluation_snapshot_reasons,
        )

        snapshot["snapshot_hash"] = paired_risk_evaluation_snapshot_hash(
            snapshot
        )
        self.assertIn(
            "PAIRED_RISK_SOURCE_SERIES_INVALID",
            paired_risk_evaluation_snapshot_reasons(snapshot),
        )


class PairedRiskEstimatorTests(PairedRiskArtifactTests):
    def test_max_drawdown_uses_initial_and_prior_log_equity_high_watermarks(
        self,
    ):
        try:
            from crypto_quant.paired_risk import _max_drawdown
        except ImportError as exc:
            self.fail(f"paired MDD kernel is missing: {exc}")
        with localcontext() as context:
            context.prec = 50
            returns = (
                Decimal("1.10").ln(),
                Decimal("0.80").ln(),
                Decimal("1.25").ln(),
            )
        self.assertEqual(
            canonical_decimal(_max_drawdown(returns)),
            "0.2",
        )

    def test_es95_is_mean_of_largest_ceil_five_percent_losses(self):
        try:
            from crypto_quant.paired_risk import _empirical_es95
        except ImportError as exc:
            self.fail(f"paired ES95 kernel is missing: {exc}")
        returns = [
            Decimal("-0.50"),
            Decimal("-0.25"),
            *([Decimal("-0.01")] * 37),
            Decimal("0.10"),
        ]
        self.assertEqual(
            canonical_decimal(_empirical_es95(returns)),
            "0.375",
        )

    def test_es95_tail_count_has_minimum_one_and_no_interpolation(self):
        try:
            from crypto_quant.paired_risk import _empirical_es95
        except ImportError as exc:
            self.fail(f"paired ES95 kernel is missing: {exc}")
        self.assertEqual(
            canonical_decimal(
                _empirical_es95(
                    (
                        Decimal("0.1"),
                        Decimal("-0.02"),
                        Decimal("-0.01"),
                    )
                )
            ),
            "0.02",
        )

    def constant_risk_snapshot(self):
        reference, reference_economics = arm_series(
            arm="reference",
            ratios=("0.90",) * 6,
            recipe_id="baseline-recipe-v1",
            recipe_hash="1" * 64,
        )
        candidate, candidate_economics = arm_series(
            arm="candidate",
            ratios=("0.95",) * 6,
            recipe_id="candidate-recipe-v1",
            recipe_hash="2" * 64,
        )
        return self.build(
            reference_series_snapshot=reference,
            candidate_series_snapshot=candidate,
            economic_snapshots=[
                *reference_economics,
                *candidate_economics,
            ],
        )

    def test_paired_estimators_recompute_risk_inside_each_replicate(self):
        try:
            from crypto_quant.paired_risk import (
                paired_es95_relative_improvement_lcb95,
                paired_max_drawdown_relative_improvement_lcb95,
            )
        except ImportError as exc:
            self.fail(f"paired risk estimators are missing: {exc}")
        snapshot = self.constant_risk_snapshot()
        mdd = paired_max_drawdown_relative_improvement_lcb95(
            {"paired_risk_evaluation_snapshot": snapshot}
        )
        es95 = paired_es95_relative_improvement_lcb95(
            {"paired_risk_evaluation_snapshot": snapshot}
        )
        self.assertEqual(
            mdd,
            (
                "COMPUTED",
                "0.43463233152068362788891046805204894154204699941735",
                (),
            ),
        )
        self.assertEqual(
            es95,
            (
                "COMPUTED",
                "0.51316397734676037470101922702151960759678732407446",
                (),
            ),
        )

    def test_unchanged_pairs_remain_in_risk_path(self):
        try:
            from crypto_quant.paired_risk import (
                paired_max_drawdown_relative_improvement_lcb95,
                paired_risk_evaluation_snapshot_hash,
            )
        except ImportError as exc:
            self.fail(f"paired risk estimators are missing: {exc}")
        snapshot = self.build()
        segment = snapshot["paired_segments"][0]
        segment["action_changed"] = False
        segment["absolute_exposure_changed"] = False
        segment["changed"] = False
        snapshot["pairing_report"]["changed_pair_count"] = 5
        snapshot["pairing_report"]["unchanged_pair_count"] = 1
        reference = snapshot["reference_arm"]["statistical_series_snapshot"]
        candidate = snapshot["candidate_arm"]["statistical_series_snapshot"]
        candidate["observations"][0]["recommended_action"] = reference[
            "observations"
        ][0]["recommended_action"]
        candidate["observations"][0]["absolute_exposure_ratio"] = reference[
            "observations"
        ][0]["absolute_exposure_ratio"]
        candidate["series_hash"] = statistical_series_hash(candidate)
        for paired_segment in snapshot["paired_segments"]:
            paired_segment["candidate_series_hash"] = candidate[
                "series_hash"
            ]
        snapshot["snapshot_hash"] = paired_risk_evaluation_snapshot_hash(
            snapshot
        )
        status, value, reasons = (
            paired_max_drawdown_relative_improvement_lcb95(
                {"paired_risk_evaluation_snapshot": snapshot}
            )
        )
        self.assertEqual(status, "COMPUTED")
        self.assertIsNotNone(value)
        self.assertEqual(reasons, ())

    def test_no_changed_pair_and_unpaired_window_are_inconclusive(self):
        try:
            from crypto_quant.paired_risk import (
                paired_es95_relative_improvement_lcb95,
            )
        except ImportError as exc:
            self.fail(f"paired risk estimators are missing: {exc}")
        reference, reference_economics = arm_series(
            arm="reference",
            ratios=("0.90",) * 6,
            recipe_id="baseline-recipe-v1",
            recipe_hash="1" * 64,
        )
        candidate = deepcopy(reference)
        candidate["series_id"] = "candidate-unchanged"
        candidate["scope"]["evaluation_ledger"] = "AI_LEDGER"
        candidate["scope"]["recipe_release_id"] = "candidate-recipe-v1"
        candidate["scope"]["recipe_release_hash"] = "2" * 64
        candidate_economics = deepcopy(reference_economics)
        for source in candidate_economics:
            source["snapshot_id"] = source["snapshot_id"].replace(
                "reference",
                "candidate",
            )
            source["scope"]["evaluation_ledger"] = "AI_LEDGER"
            source["scope"]["recipe_release_id"] = "candidate-recipe-v1"
            source["scope"]["recipe_release_hash"] = "2" * 64
            source["source_ledger_hash"] = business_hash(
                {"candidate": source["snapshot_id"]}
            )
            source["snapshot_hash"] = economic_snapshot_hash(source)
        candidate["source_economic_snapshot_hashes"] = [
            source["snapshot_hash"] for source in candidate_economics
        ]
        for observation, source in zip(
            candidate["observations"],
            candidate_economics,
        ):
            observation["observation_id"] = observation[
                "observation_id"
            ].replace("reference", "candidate")
            observation["source_economic_snapshot_hash"] = source[
                "snapshot_hash"
            ]
        candidate["series_hash"] = statistical_series_hash(candidate)
        snapshot = self.build(
            reference_series_snapshot=reference,
            candidate_series_snapshot=candidate,
            economic_snapshots=[
                *reference_economics,
                *candidate_economics,
            ],
        )
        result = paired_es95_relative_improvement_lcb95(
            {"paired_risk_evaluation_snapshot": snapshot}
        )
        self.assertEqual(
            result,
            (
                "INCONCLUSIVE",
                None,
                ("PAIRED_RISK_NO_CHANGED_PAIRS",),
            ),
        )


class PairedRiskRegistryTests(PairedRiskEstimatorTests):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        cls.registry = EstimatorRegistry.load(ROOT / "config", cls.catalog)

    def test_catalog_risk_metrics_resolve_to_executable_estimators(self):
        resolver = MetricResolver(self.catalog)
        expected = {
            "ai_max_drawdown_relative_improvement_lcb95": (
                "PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1"
            ),
            "ai_es95_loss_relative_improvement_lcb95": (
                "PAIRED_ES95_RELATIVE_IMPROVEMENT_LCB95_V1"
            ),
            "audit_ai_max_drawdown_relative_improvement_lcb95": (
                "PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1"
            ),
            "audit_ai_es95_loss_relative_improvement_lcb95": (
                "PAIRED_ES95_RELATIVE_IMPROVEMENT_LCB95_V1"
            ),
            (
                "minor_risk_efficiency_candidate_minus_active_"
                "mdd_improvement_lcb95"
            ): "PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1",
            (
                "minor_risk_efficiency_candidate_minus_active_"
                "es95_improvement_lcb95"
            ): "PAIRED_ES95_RELATIVE_IMPROVEMENT_LCB95_V1",
        }
        snapshot = self.constant_risk_snapshot()
        for metric_id, estimator_id in expected.items():
            with self.subTest(metric_id=metric_id):
                self.assertEqual(
                    resolver.resolve(metric_id)["estimator_id"],
                    estimator_id,
                )
                result = self.registry.execute(
                    estimator_id,
                    {"paired_risk_evaluation_snapshot": snapshot},
                )
                self.assertEqual(result.status, "COMPUTED")
                self.assertIsNotNone(result.value)

    def test_registry_rejects_schema_invalid_paired_risk_input(self):
        snapshot = self.constant_risk_snapshot()
        snapshot["unknown"] = True
        result = self.registry.execute(
            "PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1",
            {"paired_risk_evaluation_snapshot": snapshot},
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("PAIRED_RISK_SNAPSHOT_SCHEMA_INVALID",),
        )

    def test_registry_executes_exact_risk_values(self):
        snapshot = self.constant_risk_snapshot()
        expected = {
            "PAIRED_MAX_DRAWDOWN_RELATIVE_IMPROVEMENT_LCB95_V1": (
                "0.43463233152068362788891046805204894154204699941735"
            ),
            "PAIRED_ES95_RELATIVE_IMPROVEMENT_LCB95_V1": (
                "0.51316397734676037470101922702151960759678732407446"
            ),
        }
        for estimator_id, value in expected.items():
            with self.subTest(estimator_id=estimator_id):
                result = self.registry.execute(
                    estimator_id,
                    {"paired_risk_evaluation_snapshot": snapshot},
                )
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, value)

    def test_supporting_observation_requires_complete_risk_source_chain(
        self,
    ):
        metric_id = "ai_max_drawdown_relative_improvement_lcb95"
        resolver = MetricResolver(self.catalog)
        definition = resolver.resolve(metric_id)
        snapshot = self.constant_risk_snapshot()
        estimator_inputs = {
            "paired_risk_evaluation_snapshot": snapshot,
        }
        execution = self.registry.execute(
            definition["estimator_id"],
            estimator_inputs,
        )
        series_hashes = [
            snapshot[f"{arm}_arm"]["statistical_series_snapshot"][
                "series_hash"
            ]
            for arm in ("reference", "candidate")
        ]
        source_hashes = [
            snapshot["snapshot_hash"],
            *series_hashes,
            *snapshot["source_economic_snapshot_hashes"],
        ]
        observation = {
            "observation_id": "paired-risk-supporting-observation-1",
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
            **snapshot["scope"],
            "model_bundle_id": snapshot["candidate_arm"]["subject_id"],
            "model_bundle_hash": snapshot["candidate_arm"]["subject_hash"],
            "ai_endpoint": snapshot["ai_endpoint"],
            "policy_binding_hashes": {
                "accounting_policy_id": snapshot["accounting_policy_hash"],
                "cost_allocation_policy_id": snapshot[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": snapshot["split_policy_hash"],
                "statistical_design_policy_id": snapshot[
                    "statistical_design_policy_hash"
                ],
            },
            "experiment_manifest_id": snapshot["experiment_manifest_id"],
            "experiment_manifest_hash": snapshot[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": snapshot[
                "approved_production_capital_usdt"
            ],
        }
        signature = "R" * 86 + "=="
        bundle = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "paired-risk-supporting-bundle-1",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(expected_scope),
            "policy_bundle_hash": HASH_A,
            "evaluator_build_hash": HASH_B,
            "computed_at": "2025-01-09T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "statistics-authority",
                "signed_at": "2025-01-09T00:00:02Z",
                "signature_base64": signature,
            },
        }
        bundle["bundle_hash"] = supporting_observation_bundle_hash(bundle)
        schema = load_json_strict(
            ROOT / "config" / "supporting-observation-bundle-v1.schema.json"
        )
        valid = validate_supporting_observation_bundle(
            bundle,
            schema=schema,
            expected_scope=expected_scope,
            policy_bundle_hash=HASH_A,
            evaluator_build_hash=HASH_B,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: bundle["bundle_hash"]},
            first_result_revealed_at="2025-01-09T00:00:00Z",
        )
        self.assertTrue(valid.valid, valid.reason_codes)

        incomplete = deepcopy(bundle)
        incomplete["observations"][0]["source_artifact_hashes"].remove(
            series_hashes[0]
        )
        incomplete["observations"][0]["observation_hash"] = (
            supporting_observation_hash(incomplete["observations"][0])
        )
        incomplete["bundle_hash"] = supporting_observation_bundle_hash(
            incomplete
        )
        invalid = validate_supporting_observation_bundle(
            incomplete,
            schema=schema,
            expected_scope=expected_scope,
            policy_bundle_hash=HASH_A,
            evaluator_build_hash=HASH_B,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: incomplete["bundle_hash"]},
            first_result_revealed_at="2025-01-09T00:00:00Z",
        )
        self.assertFalse(invalid.valid)
        self.assertIn(
            f"SUPPORTING_PAIRED_RISK_SOURCE_INCOMPLETE:{metric_id}",
            invalid.reason_codes,
        )
