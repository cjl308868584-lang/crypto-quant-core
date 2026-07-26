import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from decimal import getcontext
from pathlib import Path

from crypto_quant.canonical import business_hash
from crypto_quant.economics import economic_snapshot_hash
from crypto_quant.estimators import EstimatorRegistry
from crypto_quant.evidence import EvidenceTrustContext
from crypto_quant.release import MetricResolver, PolicyBundle, load_json_strict
from crypto_quant.release_artifacts import (
    supporting_observation_bundle_hash,
    supporting_observation_hash,
    validate_supporting_observation_bundle,
)
from crypto_quant.statistics import (
    monthly_economic_series_snapshot,
    statistical_series_hash,
)


ROOT = Path(__file__).resolve().parents[1]
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
HASH_F = "f" * 64

STATISTICAL_EXPECTED = {
    "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1": 6,
    "ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1": "63",
    "MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1": "10.875",
    "COMPLETE_UTC_CALENDAR_MONTH_COUNT_V1": 8,
}


def next_month(value):
    return value.replace(
        year=value.year + (1 if value.month == 12 else 0),
        month=1 if value.month == 12 else value.month + 1,
    )


def render_time(value):
    return value.astimezone(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def monthly_economic_snapshot(index, start, pnl):
    end = next_month(start)
    start_text = render_time(start)
    end_text = render_time(end)
    ending_equity = str(1000 + pnl)
    snapshot = {
        "$schema": "./economic-ledger-snapshot-v1.schema.json",
        "schema_version": "1.0.0",
        "snapshot_id": f"economic-month-{index}",
        "snapshot_hash": "0" * 64,
        "hash_algorithm": "SHA-256",
        "canonicalization": "RFC8785_JCS",
        "source_ledger_hash": business_hash(
            {"month": index, "source": "ledger"}
        ),
        "source_projection_hash": business_hash(
            {"month": index, "source": "projection"}
        ),
        "accounting_policy_id": "accounting-v1",
        "accounting_policy_hash": HASH_C,
        "cost_allocation_policy_id": "cost-allocation-v1",
        "cost_allocation_policy_hash": HASH_D,
        "scope": {
            "account_id": "account-1",
            "evaluation_ledger": "AI_LEDGER",
            "release_route": "AI_ENHANCED",
            "direction": "LONG",
            "venue": "BINANCE_SPOT",
            "recipe_release_id": "recipe-1",
            "recipe_release_hash": HASH_E,
            "deployment_line_id": "line-1",
            "deployment_line_hash": HASH_F,
            "evaluation_window_start": start_text,
            "evaluation_window_end": end_text,
        },
        "reporting_asset": "USDT",
        "window_event_convention": "START_EXCLUSIVE_END_INCLUSIVE",
        "starting_liquidation_equity_usdt": "1000",
        "ending_liquidation_equity_usdt": ending_equity,
        "opening_positions": [],
        "fills": [],
        "funding_cashflows": [],
        "external_cash_flows": [],
        "allocated_costs": [],
        "equity_points": [
            {
                "equity_snapshot_id": f"equity-{index}-start",
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
                "equity_snapshot_id": f"equity-{index}-end",
                "as_of": end_text,
                "marked_equity_usdt": ending_equity,
                "liquidation_equity_usdt": ending_equity,
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
    return snapshot


class StatisticalEstimatorTests(unittest.TestCase):
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
        cls.series = golden["fixtures"]["statistical-monthly-series-valid"]
        cls.endpoint_series = golden["fixtures"][
            "statistical-endpoint-series-valid"
        ]
        cls.economic = golden["fixtures"]["economic-snapshot-valid"]

    def execute(self, estimator_id, series=None):
        if series is None:
            series = (
                self.endpoint_series
                if estimator_id
                in {
                    "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1",
                    "ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1",
                }
                else self.series
            )
        return self.registry.execute(
            estimator_id,
            {
                "statistical_series_snapshot": series
            },
        )

    def test_registered_statistics_match_frozen_golden_results(self):
        for estimator_id, expected in STATISTICAL_EXPECTED.items():
            with self.subTest(estimator_id=estimator_id):
                result = self.execute(estimator_id)
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.value, expected)
        growth = self.registry.execute(
            "CASH_FLOW_ADJUSTED_ECONOMIC_LOG_GROWTH_V1",
            {"economic_ledger_snapshot": self.economic},
        )
        self.assertEqual(growth.status, "COMPUTED")
        self.assertEqual(
            growth.value,
            "0.014407341930198021706023035344030901114934212593181",
        )
        wrong_kind = self.execute(
            "ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1",
            self.series,
        )
        self.assertEqual(wrong_kind.status, "FAIL")
        self.assertEqual(
            wrong_kind.reason_codes,
            ("STATISTICAL_SERIES_KIND_MISMATCH",),
        )
        wrong_month_count_kind = self.execute(
            "COMPLETE_UTC_CALENDAR_MONTH_COUNT_V1",
            self.endpoint_series,
        )
        self.assertEqual(wrong_month_count_kind.status, "FAIL")
        self.assertEqual(
            wrong_month_count_kind.reason_codes,
            ("STATISTICAL_SERIES_KIND_MISMATCH",),
        )

    def test_decimal_context_and_hashes_are_deterministic(self):
        original_precision = getcontext().prec
        try:
            expected = self.execute(
                "ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1"
            )
            hashes = set()
            values = set()
            for precision in (9, 18, 28, 60):
                getcontext().prec = precision
                for _ in range(25):
                    result = self.execute(
                        "ONE_SIDED_95_MOVING_BLOCK_BOOTSTRAP_V1"
                    )
                    hashes.add(result.execution_hash)
                    values.add(result.value)
            self.assertEqual(values, {expected.value})
            self.assertEqual(hashes, {expected.execution_hash})
        finally:
            getcontext().prec = original_precision

    def test_zero_variance_and_insufficient_blocks_are_inconclusive(self):
        constant = deepcopy(self.series)
        for observation in constant["observations"]:
            observation["value"] = "1"
        constant["series_hash"] = statistical_series_hash(constant)
        result = self.execute(
            "GEYER_INITIAL_POSITIVE_SEQUENCE_ESS_V1",
            constant,
        )
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_ZERO_VARIANCE",),
        )

        short = deepcopy(self.series)
        short["observations"] = short["observations"][:4]
        short["source_economic_snapshot_hashes"] = (
            short["source_economic_snapshot_hashes"][:4]
        )
        short["scope"]["evaluation_window_end"] = (
            short["observations"][-1]["period_end"]
        )
        short["series_hash"] = statistical_series_hash(short)
        result = self.execute(
            "MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1",
            short,
        )
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_INSUFFICIENT_BLOCKS",),
        )

    def test_partial_month_is_excluded_and_false_flag_is_detected(self):
        partial = deepcopy(self.series)
        partial["observations"][0]["period_start"] = (
            "2025-01-02T00:00:00Z"
        )
        partial["observations"][0]["calendar_month_complete"] = False
        partial["scope"]["evaluation_window_start"] = (
            "2025-01-02T00:00:00Z"
        )
        partial["series_hash"] = statistical_series_hash(partial)
        count = self.execute(
            "COMPLETE_UTC_CALENDAR_MONTH_COUNT_V1",
            partial,
        )
        self.assertEqual(count.status, "COMPUTED")
        self.assertEqual(count.value, 7)

        lying = deepcopy(partial)
        lying["observations"][0]["calendar_month_complete"] = True
        lying["series_hash"] = statistical_series_hash(lying)
        result = self.execute(
            "COMPLETE_UTC_CALENDAR_MONTH_COUNT_V1",
            lying,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(
            "STATISTICAL_SERIES_MONTH_COMPLETENESS_MISMATCH",
            result.reason_codes,
        )

    def test_schema_and_self_hash_tampering_fail_closed(self):
        tampered = deepcopy(self.series)
        tampered["observations"][0]["value"] = "9999"
        result = self.execute(
            "MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1",
            tampered,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertIn(
            "STATISTICAL_SERIES_SELF_HASH_MISMATCH",
            result.reason_codes,
        )

        binary_float = deepcopy(self.series)
        binary_float["observations"][0]["value"] = 1.0
        result = self.execute(
            "MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1",
            binary_float,
        )
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason_codes,
            ("STATISTICAL_SERIES_SCHEMA_INVALID",),
        )

    def test_monthly_series_is_built_from_same_scope_economic_snapshots(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        snapshots = []
        for index, pnl in enumerate((10, 12, 8, 15, 9, 14, 11, 13), 1):
            snapshots.append(monthly_economic_snapshot(index, start, pnl))
            start = next_month(start)
        series = monthly_economic_series_snapshot(
            series_id="monthly-economic-series-test-1",
            economic_snapshots=snapshots,
            approved_production_capital_usdt="1000",
            split_policy_id="split-v1",
            split_policy_hash=HASH_A,
            statistical_design_policy_id="statistics-v1",
            statistical_design_policy_hash=HASH_B,
            experiment_manifest_id="experiment-1",
            experiment_manifest_hash=HASH_C,
            block_length=2,
            minimum_block_count=3,
            resample_count=1000,
            seed=42,
            generated_at="2025-09-02T00:00:00Z",
        )
        result = self.execute(
            "MONTHLY_ECONOMIC_PNL_MBB_LCB95_V1",
            series,
        )
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.value, "10.875")
        self.assertEqual(
            series["source_economic_snapshot_hashes"],
            [snapshot["snapshot_hash"] for snapshot in snapshots],
        )

        wrong_policy = deepcopy(snapshots[-1])
        wrong_policy["accounting_policy_hash"] = HASH_A
        wrong_policy["snapshot_hash"] = economic_snapshot_hash(wrong_policy)
        with self.assertRaisesRegex(
            ValueError,
            "policies do not match",
        ):
            monthly_economic_series_snapshot(
                series_id="monthly-economic-series-invalid",
                economic_snapshots=[*snapshots[:-1], wrong_policy],
                approved_production_capital_usdt="1000",
                split_policy_id="split-v1",
                split_policy_hash=HASH_A,
                statistical_design_policy_id="statistics-v1",
                statistical_design_policy_hash=HASH_B,
                experiment_manifest_id="experiment-1",
                experiment_manifest_hash=HASH_C,
                block_length=2,
                minimum_block_count=3,
                resample_count=1000,
                seed=42,
                generated_at="2025-09-02T00:00:00Z",
            )

    def test_release_evidence_cannot_reuse_another_experiment_series(self):
        evidence = {
            **self.series["scope"],
            "experiment_manifest_id": self.series[
                "experiment_manifest_id"
            ],
            "experiment_manifest_hash": self.series[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": self.series[
                "approved_production_capital_usdt"
            ],
            "policy_binding_hashes": {
                "accounting_policy_id": self.series[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": self.series[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": self.series["split_policy_hash"],
                "statistical_design_policy_id": self.series[
                    "statistical_design_policy_hash"
                ],
            },
            "frozen_release_inputs": {
                "statistical_series_snapshot": {
                    "artifact_id": self.series["series_id"],
                    "artifact_hash": self.series["series_hash"],
                }
            },
            "artifact_hashes": [
                self.series["series_hash"],
                *self.series["source_economic_snapshot_hashes"],
            ],
        }
        trust = EvidenceTrustContext(
            policy_bundle_hash=HASH_A,
            binding_ids={},
            binding_hashes={},
            artifact_hashes={
                "statistical_series_snapshot": self.series["series_hash"]
            },
            capital_values={},
            artifact_documents={
                "statistical_series_snapshot": self.series
            },
        )
        self.assertEqual(
            PolicyBundle._statistical_series_reference_reasons(
                evidence,
                trust,
            ),
            (),
        )

        wrong = dict(evidence)
        wrong["experiment_manifest_hash"] = HASH_A
        wrong["approved_production_capital_usdt"] = "999"
        wrong["artifact_hashes"] = [self.series["series_hash"]]
        reasons = PolicyBundle._statistical_series_reference_reasons(
            wrong,
            trust,
        )
        self.assertIn(
            "STATISTICAL_SERIES_EXPERIMENT_MISMATCH",
            reasons,
        )
        self.assertIn(
            "STATISTICAL_SERIES_APPROVED_CAPITAL_MISMATCH",
            reasons,
        )
        self.assertIn(
            "STATISTICAL_SERIES_SOURCE_HASH_MISSING",
            reasons,
        )

    def test_supporting_observation_requires_complete_statistical_sources(self):
        catalog = load_json_strict(
            ROOT / "config" / "release-metrics-v1.1.json"
        )
        resolver = MetricResolver(catalog)
        metric_id = "baseline_full_risk_monthly_economic_pnl_usdt_lcb95"
        definition = resolver.resolve(metric_id)
        estimator_inputs = {
            "statistical_series_snapshot": self.series,
        }
        execution = self.registry.execute(
            definition["estimator_id"],
            estimator_inputs,
        )
        source_hashes = [
            self.series["series_hash"],
            *self.series["source_economic_snapshot_hashes"],
        ]
        observation = {
            "observation_id": "statistical-observation-1",
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
            **self.series["scope"],
            "policy_binding_hashes": {
                "accounting_policy_id": self.series[
                    "accounting_policy_hash"
                ],
                "cost_allocation_policy_id": self.series[
                    "cost_allocation_policy_hash"
                ],
                "split_policy_id": self.series["split_policy_hash"],
                "statistical_design_policy_id": self.series[
                    "statistical_design_policy_hash"
                ],
            },
            "experiment_manifest_id": self.series[
                "experiment_manifest_id"
            ],
            "experiment_manifest_hash": self.series[
                "experiment_manifest_hash"
            ],
            "approved_production_capital_usdt": self.series[
                "approved_production_capital_usdt"
            ],
        }
        signature = "F" * 86 + "=="
        bundle = {
            "$schema": "./supporting-observation-bundle-v1.schema.json",
            "schema_version": "1.0.0",
            "bundle_id": "statistical-supporting-bundle-1",
            "bundle_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "scope_hash": business_hash(expected_scope),
            "policy_bundle_hash": HASH_A,
            "evaluator_build_hash": HASH_B,
            "computed_at": "2025-09-02T00:00:01Z",
            "observations": [observation],
            "bundle_attestation": {
                "algorithm": "ED25519",
                "key_id": "statistics-authority",
                "signed_at": "2025-09-02T00:00:02Z",
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
            policy_bundle_hash=HASH_A,
            evaluator_build_hash=HASH_B,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={signature: bundle["bundle_hash"]},
            first_result_revealed_at="2025-09-01T00:00:00Z",
        )
        self.assertTrue(validation.valid, validation.reason_codes)

        incomplete = deepcopy(bundle)
        incomplete["observations"][0]["source_artifact_hashes"] = (
            source_hashes[:-1]
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
            policy_bundle_hash=HASH_A,
            evaluator_build_hash=HASH_B,
            resolve_metric=resolver.resolve,
            estimators=self.registry,
            allowed_source_hashes=set(source_hashes),
            verified_attestations={
                signature: incomplete["bundle_hash"],
            },
            first_result_revealed_at="2025-09-01T00:00:00Z",
        )
        self.assertFalse(validation.valid)
        self.assertIn(
            f"SUPPORTING_STATISTICAL_SOURCE_INCOMPLETE:{metric_id}",
            validation.reason_codes,
        )


if __name__ == "__main__":
    unittest.main()
