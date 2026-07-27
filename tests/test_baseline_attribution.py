import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from crypto_quant.baseline_attribution import (
    baseline_attribution_hash,
    baseline_attribution_reasons,
    build_baseline_failure_attribution,
    load_baseline_attribution,
    publish_baseline_attribution,
)
from crypto_quant.canonical import (
    business_hash,
    canonical_decimal,
    utc_datetime,
)
from crypto_quant.evidence import artifact_self_hash


FEATURE_NAMES = [
    "eth_log_return_5",
    "eth_sma20_distance",
    "eth_annualized_volatility_20",
    "eth_mean_range_ratio_6",
    "eth_taker_buy_quote_ratio_6",
    "btc_log_return_5",
    "btc_sma20_distance",
    "eth_mark_basis",
    "eth_latest_funding_rate",
]


def dataset_fixture():
    samples = []
    decision_times = [
        datetime(2023, 1, 2, 12, tzinfo=timezone.utc)
        + timedelta(days=index)
        for index in range(8)
    ] + [
        datetime(2023, 1, 12, 12, tzinfo=timezone.utc)
        + timedelta(days=index)
        for index in range(8)
    ]
    sma_values = ["0.001", "0.006", "0.015", "0.03"]
    vol_values = ["0.3", "0.6", "1", "1.5"]
    range_values = ["0.005", "0.015", "0.03", "0.05"]
    for index, decision in enumerate(decision_times):
        gross = (
            Decimal("5")
            if index % 3 == 0
            else (Decimal("2") if index % 3 == 1 else Decimal("-2"))
        )
        entry_fee = Decimal("1.5")
        exit_fee = Decimal("1.5")
        net = gross - entry_fee - exit_fee
        realized = net / Decimal("1000")
        samples.append(
            {
                "sample_id": f"sample_{index:02d}",
                "decision_time": utc_datetime(decision),
                "label_end_time_exclusive": utc_datetime(
                    decision + timedelta(hours=24)
                ),
                "feature_values": [
                    "-0.01" if index % 2 == 0 else "0.01",
                    sma_values[index % 4],
                    vol_values[index % 4],
                    range_values[index % 4],
                    "0.5",
                    "0.01",
                    "0.01",
                    "0",
                    "0.0001",
                ],
                "gross_pnl_usdt": canonical_decimal(gross),
                "entry_fee_usdt": canonical_decimal(entry_fee),
                "exit_fee_usdt": canonical_decimal(exit_fee),
                "net_pnl_usdt": canonical_decimal(net),
                "realized_net_return_24h": canonical_decimal(realized),
                "y_take": int(realized > 0),
                "holding_hours": 8 if index % 2 else 24,
                "exit_reason": (
                    "SMA20_EXIT_AFTER_MIN_HOLD"
                    if index % 2
                    else "VERTICAL_24H_EXIT"
                ),
            }
        )
    dataset = {
        "dataset_id": "causal_dataset_fixture",
        "dataset_hash": "0" * 64,
        "samples_root_hash": business_hash(samples),
        "research_eligibility": "ARCHIVE_CAUSAL_RESEARCH_ONLY",
        "feature_schema": {"ordered_feature_names": FEATURE_NAMES},
        "label_policy": {"reference_notional_usdt": "1000"},
        "samples": samples,
    }
    dataset["dataset_hash"] = artifact_self_hash(dataset, "dataset_hash")
    return dataset


def folds_fixture():
    values = []
    for index, start_day in enumerate((1, 11), 1):
        start = datetime(
            2023,
            1,
            start_day,
            tzinfo=timezone.utc,
        )
        end = start + timedelta(days=10)
        values.append(
            {
                "fold_id": f"fold_{index}",
                "fold_index": index,
                "purge_duration_hours": 24,
                "embargo_duration_hours": 24,
                "oos_window_start": utc_datetime(start),
                "oos_window_end_exclusive": utc_datetime(end),
            }
        )
    return values


class BaselineAttributionTests(unittest.TestCase):
    def build(self):
        dataset = dataset_fixture()
        folds = folds_fixture()
        attribution = build_baseline_failure_attribution(
            dataset=dataset,
            folds=folds,
            recorded_at="2026-07-28T12:00:00.000Z",
        )
        return attribution, dataset, folds

    def test_fixed_groups_cover_pooled_oos_and_decompose_fees(self):
        attribution, _, _ = self.build()
        all_metrics = attribution["all_event_metrics"]
        pooled = attribution["pooled_archive_oos_metrics"]
        self.assertEqual(all_metrics["sample_count"], 16)
        self.assertEqual(pooled["sample_count"], 16)
        self.assertEqual(all_metrics["total_fee_usdt_sum"], "48")
        self.assertEqual(all_metrics["fee_flip_count"], 5)
        dimensions = {}
        for group in attribution["groups"]:
            dimensions.setdefault(group["dimension"], 0)
            dimensions[group["dimension"]] += group["metrics"][
                "sample_count"
            ]
        for dimension, count in dimensions.items():
            if dimension == "OOS_FOLD":
                self.assertEqual(count, pooled["sample_count"])
            else:
                self.assertEqual(count, pooled["sample_count"], dimension)
        self.assertEqual(
            attribution["attribution_hash"],
            baseline_attribution_hash(attribution),
        )

    def test_hypothesis_is_preregistered_once_and_never_backtested(self):
        first, dataset, folds = self.build()
        registration = first["hypothesis_registration"]
        self.assertEqual(registration["economic_hypothesis_count"], 1)
        self.assertEqual(registration["parameter_combination_count"], 1)
        self.assertEqual(registration["sma20_distance_minimum"], "0.005")
        self.assertEqual(
            registration["challenger_evaluation_status"],
            "NOT_RUN_PREREGISTERED_FORWARD_ONLY",
        )
        for _ in range(100):
            self.assertEqual(
                build_baseline_failure_attribution(
                    dataset=dataset,
                    folds=folds,
                    recorded_at=first["recorded_at"],
                ),
                first,
            )

    def test_input_order_and_economic_inconsistency_fail_closed(self):
        dataset = dataset_fixture()
        folds = folds_fixture()
        dataset["samples"][0], dataset["samples"][1] = (
            dataset["samples"][1],
            dataset["samples"][0],
        )
        dataset["samples_root_hash"] = business_hash(dataset["samples"])
        dataset["dataset_hash"] = artifact_self_hash(
            dataset,
            "dataset_hash",
        )
        with self.assertRaisesRegex(
            ValueError,
            "BASELINE_ATTRIBUTION_SAMPLE_ORDER_INVALID",
        ):
            build_baseline_failure_attribution(
                dataset=dataset,
                folds=folds,
                recorded_at="2026-07-28T12:00:00.000Z",
            )
        dataset = dataset_fixture()
        dataset["samples"][0]["net_pnl_usdt"] = "999"
        dataset["samples_root_hash"] = business_hash(dataset["samples"])
        dataset["dataset_hash"] = artifact_self_hash(
            dataset,
            "dataset_hash",
        )
        with self.assertRaisesRegex(
            ValueError,
            "BASELINE_ATTRIBUTION_SAMPLE_INVALID",
        ):
            build_baseline_failure_attribution(
                dataset=dataset,
                folds=folds,
                recorded_at="2026-07-28T12:00:00.000Z",
            )

    def test_rehashed_result_tamper_is_semantically_detected(self):
        attribution, dataset, folds = self.build()
        candidate = json.loads(json.dumps(attribution))
        candidate["groups"][0]["metrics"]["net_pnl_usdt_sum"] = "999"
        candidate["groups_root_hash"] = business_hash(candidate["groups"])
        candidate["attribution_hash"] = baseline_attribution_hash(candidate)
        self.assertIn(
            "BASELINE_ATTRIBUTION_SEMANTIC_MISMATCH",
            baseline_attribution_reasons(
                candidate,
                dataset=dataset,
                folds=folds,
            ),
        )

    def test_publish_load_is_owner_only_and_idempotent(self):
        attribution, _, _ = self.build()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attribution" / "result.json"
            publish_baseline_attribution(
                attribution=attribution,
                output_path=path,
            )
            self.assertEqual(load_baseline_attribution(path), attribution)
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            publish_baseline_attribution(
                attribution=attribution,
                output_path=path,
            )

    def test_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (
                root / "config/baseline-failure-attribution-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "baseline-failure-attribution-v1.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
