import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import business_hash, canonical_decimal, utc_datetime
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.logistic_research import (
    build_logistic_archive_research,
    load_logistic_research,
    logistic_research_hash,
    logistic_research_reasons,
    publish_logistic_research,
)


def dataset_fixture():
    samples = []
    start = datetime(2023, 1, 1, 12, tzinfo=timezone.utc)
    for index in range(365):
        decision = start + timedelta(days=index)
        features = [
            (index % 23 - 11) / 10,
            (index % 17 - 8) / 10,
            (index % 13 + 1) / 10,
            (index % 11 + 1) / 100,
            (index % 7 + 1) / 10,
            (index % 19 - 9) / 10,
            (index % 29 - 14) / 10,
            (index % 5 - 2) / 1000,
            (index % 3 - 1) / 10000,
        ]
        label = 1 if features[0] + features[1] * 0.5 > 0 else 0
        realized = "0.01" if label else "-0.01"
        samples.append(
            {
                "sample_id": f"sample_{index:04d}",
                "decision_time": utc_datetime(decision),
                "label_end_time_exclusive": utc_datetime(
                    decision + timedelta(hours=24)
                ),
                "feature_values": [
                    canonical_decimal(str(value)) for value in features
                ],
                "y_take": label,
                "realized_net_return_24h": realized,
            }
        )
    dataset = {
        "dataset_id": "causal-dataset-fixture",
        "dataset_hash": "0" * 64,
        "research_eligibility": "ARCHIVE_CAUSAL_RESEARCH_ONLY",
        "feature_schema": {"feature_schema_hash": "a" * 64},
        "label_policy": {"label_policy_hash": "b" * 64},
        "samples": samples,
    }
    dataset["dataset_hash"] = artifact_self_hash(dataset, "dataset_hash")
    return dataset


def folds_fixture():
    return [
        {
            "fold_id": "research-fold-fixture-1",
            "fold_index": 1,
            "fit_window_start": "2023-01-01T00:00:00.000Z",
            "fit_window_end_exclusive": "2023-08-01T00:00:00.000Z",
            "calibration_window_start": "2023-08-01T00:00:00.000Z",
            "calibration_window_end_exclusive": "2023-09-01T00:00:00.000Z",
            "purge_duration_hours": 24,
            "embargo_duration_hours": 24,
            "oos_window_start": "2023-09-01T00:00:00.000Z",
            "oos_window_end_exclusive": "2024-01-01T00:00:00.000Z",
        }
    ]


class LogisticResearchTests(unittest.TestCase):
    def build(self):
        dataset = dataset_fixture()
        folds = folds_fixture()
        research = build_logistic_archive_research(
            dataset=dataset,
            folds=folds,
            recorded_at="2026-07-28T00:00:00.000Z",
        )
        return research, dataset, folds

    def test_fixed_recipe_is_deterministic_and_beats_constant_fixture(self):
        first, dataset, folds = self.build()
        for _ in range(4):
            self.assertEqual(
                build_logistic_archive_research(
                    dataset=dataset,
                    folds=folds,
                    recorded_at="2026-07-28T00:00:00.000Z",
                ),
                first,
            )
        self.assertLess(
            float(first["summary"]["logistic_brier"]),
            float(first["summary"]["constant_brier"]),
        )
        self.assertEqual(first["recipe"]["trial_count"], 1)
        self.assertFalse(first["recipe"]["shuffle"])
        self.assertEqual(first["research_hash"], logistic_research_hash(first))
        self.assertEqual(
            logistic_research_reasons(
                first,
                dataset=dataset,
                folds=folds,
            ),
            (),
        )

    def test_oos_label_change_cannot_change_fit_or_calibration_parameters(self):
        original, dataset, folds = self.build()
        candidate = json.loads(json.dumps(dataset))
        oos_start = folds[0]["oos_window_start"]
        target = next(
            sample
            for sample in candidate["samples"]
            if sample["decision_time"] >= oos_start
        )
        target["y_take"] = 1 - target["y_take"]
        target["realized_net_return_24h"] = (
            "0.01" if target["y_take"] else "-0.01"
        )
        candidate["dataset_hash"] = artifact_self_hash(
            candidate,
            "dataset_hash",
        )
        changed = build_logistic_archive_research(
            dataset=candidate,
            folds=folds,
            recorded_at="2026-07-28T00:00:00.000Z",
        )
        self.assertEqual(
            original["folds"][0]["parameters"],
            changed["folds"][0]["parameters"],
        )

    def test_rehashed_prediction_tamper_is_semantically_detected(self):
        research, dataset, folds = self.build()
        candidate = json.loads(json.dumps(research))
        candidate["predictions"][0]["accepted"] = (
            not candidate["predictions"][0]["accepted"]
        )
        candidate["predictions_root_hash"] = business_hash(
            candidate["predictions"]
        )
        candidate["research_hash"] = logistic_research_hash(candidate)
        self.assertIn(
            "LOGISTIC_RESEARCH_SEMANTIC_MISMATCH",
            logistic_research_reasons(
                candidate,
                dataset=dataset,
                folds=folds,
            ),
        )

    def test_publish_load_is_owner_only(self):
        research, _, _ = self.build()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "research" / "logistic.json"
            publish_logistic_research(research=research, output_path=path)
            self.assertEqual(load_logistic_research(path), research)
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (
                root / "config/logistic-archive-research-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "logistic-archive-research-v1.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
