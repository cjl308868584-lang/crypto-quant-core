import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.canonical import business_hash, utc_datetime
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.causal_research import (
    build_causal_feature_label_dataset,
    causal_dataset_hash,
    causal_dataset_reasons,
    feature_input_facts_root_hash,
    load_causal_dataset,
    publish_causal_dataset,
)


def kline(symbol, family, index, close_offset="0"):
    opened_at = datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(
        hours=4 * index
    )
    close = 100 + index + int(close_offset)
    return {
        "data_family": family,
        "symbol": symbol,
        "open_time": utc_datetime(opened_at),
        "close_time": utc_datetime(
            opened_at + timedelta(hours=4) - timedelta(milliseconds=1)
        ),
        "open": str(close - 1),
        "high": str(close + 2),
        "low": str(close - 2),
        "close": str(close),
        "quote_asset_volume": "100000",
        "taker_buy_quote_asset_volume": "51000",
        "source_row_hash": business_hash(
            {"symbol": symbol, "family": family, "index": index}
        ),
    }


def fixture_sources(length=40):
    eth = [kline("ETHUSDT", "KLINES", index) for index in range(length)]
    btc = [
        kline("BTCUSDT", "KLINES", index, close_offset="1000")
        for index in range(length)
    ]
    mark = [
        kline("ETHUSDT", "MARK_PRICE_KLINES", index)
        for index in range(length)
    ]
    funding = [
        {
            "data_family": "FUNDING_RATE",
            "symbol": "ETHUSDT",
            "event_time": "2023-01-01T00:00:00.000Z",
            "funding_rate": "0.0001",
        }
    ]
    required = []
    index = 20
    while index < length - 6:
        exit_index = index + 6
        for selected_index in (index, exit_index):
            decision = datetime.fromisoformat(
                eth[selected_index]["close_time"].replace("Z", "+00:00")
            )
            required.append(
                (decision + timedelta(minutes=1)).replace(
                    second=0,
                    microsecond=0,
                )
            )
        index = exit_index + 1
    rows = [
        {
            "open_time": utc_datetime(value),
            "high": "100",
            "low": "110",
            "source_row_hash": business_hash(
                {"execution_open_time": utc_datetime(value)}
            ),
        }
        for value in required
    ]
    source = {
        "source_hash": "0" * 64,
        "request": {"period": "2023-01"},
        "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        "quality_eligibility": "FORMAL_COMPLETE",
        "selected_rows": rows,
    }
    source["source_hash"] = artifact_self_hash(source, "source_hash")
    execution_root = business_hash(
        [{"period": "2023-01", "source_hash": source["source_hash"]}]
    )
    roots = {
        "corpus_plan_hash": "a" * 64,
        "corpus_snapshot_hash": "b" * 64,
        "corpus_repair_bundle_hash": "c" * 64,
        "execution_source_root_hash": execution_root,
        "feature_input_facts_root_hash": feature_input_facts_root_hash(
            eth_spot_facts=eth,
            btc_context_facts=btc,
            eth_mark_facts=mark,
            eth_funding_facts=funding,
        ),
    }
    return eth, btc, mark, funding, [source], roots


class CausalResearchTests(unittest.TestCase):
    def build(self, length=40):
        eth, btc, mark, funding, execution, roots = fixture_sources(length)
        dataset = build_causal_feature_label_dataset(
            eth_spot_facts=eth,
            btc_context_facts=btc,
            eth_mark_facts=mark,
            eth_funding_facts=funding,
            execution_sources=execution,
            source_roots=roots,
            recorded_at="2026-07-28T00:00:00.000Z",
        )
        return dataset, (eth, btc, mark, funding, execution)

    def test_builds_nonoverlapping_causal_costed_long_samples(self):
        dataset, _ = self.build()
        self.assertEqual(dataset["summary"]["sample_count"], 2)
        self.assertEqual(dataset["summary"]["feature_count"], 9)
        self.assertEqual(dataset["summary"]["positive_label_count"], 2)
        for left, right in zip(dataset["samples"], dataset["samples"][1:]):
            self.assertLess(
                left["label_end_time_exclusive"],
                right["decision_time"],
            )
        for sample in dataset["samples"]:
            self.assertLessEqual(
                sample["max_feature_event_time"],
                sample["decision_time"],
            )
            self.assertLess(sample["decision_time"], sample["entry_open_time"])
            self.assertEqual(sample["holding_hours"], 24)
            self.assertEqual(len(sample["feature_values"]), 9)
            self.assertEqual(sample["entry_fill_price"], "100.1")
            self.assertEqual(sample["exit_fill_price"], "109.89")
            self.assertEqual(sample["y_take"], 1)
        self.assertEqual(dataset["dataset_hash"], causal_dataset_hash(dataset))

    def test_prefix_build_matches_full_for_every_completed_sample(self):
        full, _ = self.build(40)
        prefix, _ = self.build(34)
        self.assertEqual(prefix["samples"], full["samples"])
        self.assertEqual(
            prefix["samples_root_hash"],
            full["samples_root_hash"],
        )

    def test_rehashed_feature_or_label_tamper_is_semantically_detected(self):
        dataset, sources = self.build()
        candidate = json.loads(json.dumps(dataset))
        candidate["samples"][0]["feature_values"][0] = "999"
        candidate["samples_root_hash"] = business_hash(candidate["samples"])
        candidate["dataset_hash"] = causal_dataset_hash(candidate)
        eth, btc, mark, funding, execution = sources
        self.assertIn(
            "CAUSAL_RESEARCH_SEMANTIC_MISMATCH",
            causal_dataset_reasons(
                candidate,
                eth_spot_facts=eth,
                btc_context_facts=btc,
                eth_mark_facts=mark,
                eth_funding_facts=funding,
                execution_sources=execution,
            ),
        )

    def test_no_prior_funding_fact_fails_closed(self):
        eth, btc, mark, funding, execution, roots = fixture_sources()
        funding[0]["event_time"] = "2023-02-01T00:00:00.000Z"
        roots["feature_input_facts_root_hash"] = feature_input_facts_root_hash(
            eth_spot_facts=eth,
            btc_context_facts=btc,
            eth_mark_facts=mark,
            eth_funding_facts=funding,
        )
        with self.assertRaisesRegex(ValueError, "CAUSAL_RESEARCH_FUNDING_MISSING"):
            build_causal_feature_label_dataset(
                eth_spot_facts=eth,
                btc_context_facts=btc,
                eth_mark_facts=mark,
                eth_funding_facts=funding,
                execution_sources=execution,
                source_roots=roots,
                recorded_at="2026-07-28T00:00:00.000Z",
            )

    def test_publish_load_is_owner_only_and_idempotent(self):
        dataset, _ = self.build()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset" / "causal.json"
            publish_causal_dataset(dataset=dataset, output_path=path)
            self.assertEqual(load_causal_dataset(path), dataset)
            self.assertEqual(os.stat(path.parent).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            publish_causal_dataset(dataset=dataset, output_path=path)

    def test_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (
                root / "config/causal-feature-label-dataset-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "causal-feature-label-dataset-v1.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
