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
