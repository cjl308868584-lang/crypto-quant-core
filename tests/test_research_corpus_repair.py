import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.market_data import (
    HistoricalArchiveRequest,
    build_historical_market_data_snapshot,
    build_research_degraded_historical_market_data_snapshot,
    historical_market_data_snapshot_attestation_hash,
    verify_official_checksum,
)
from crypto_quant.research_corpus import (
    ResearchCorpusError,
    build_default_research_corpus_plan,
    build_research_corpus_snapshot,
)
from crypto_quant.research_corpus_repair import (
    build_research_corpus_repair_bundle,
    publish_research_corpus_repair_artifacts,
    repair_requests_for_degraded_sources,
    research_corpus_repair_bundle_hash,
    research_corpus_repair_bundle_reasons,
)


def archive_for(request, rows):
    csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.expected_csv_name, csv_bytes)
    archive_bytes = output.getvalue()
    return verify_official_checksum(
        request,
        archive_bytes,
        (
            f"{hashlib.sha256(archive_bytes).hexdigest()}"
            f"  {request.archive_filename}\n"
        ).encode("ascii"),
    )


def mark_rows(start, count, missing_day=None):
    rows = [
        "open_time,open,high,low,close,volume,close_time,quote_volume,"
        "count,taker_buy_volume,taker_buy_quote_volume,ignore"
    ]
    for index in range(count):
        opened_at = start + timedelta(hours=4 * index)
        if missing_day is not None and opened_at.date() == missing_day.date():
            continue
        opened = int(opened_at.timestamp() * 1_000)
        rows.append(
            f"{opened},100,101,99,100.5,0,{opened + 14_399_999},"
            "0,14400,0,0,0"
        )
    return rows


class CompletedCorpusStateStub:
    def __init__(self, plan, degraded_item_id, degraded_snapshot):
        self.states = {}
        degraded_attestation = historical_market_data_snapshot_attestation_hash(
            degraded_snapshot
        )
        for item in plan["items"]:
            if item["corpus_item_id"] == degraded_item_id:
                snapshot_hash = degraded_snapshot["snapshot_hash"]
                attestation = degraded_attestation
                source_snapshot = degraded_snapshot
            else:
                snapshot_hash = hashlib.sha256(
                    (item["corpus_item_id"] + "-snapshot").encode("ascii")
                ).hexdigest()
                attestation = hashlib.sha256(
                    (item["corpus_item_id"] + "-attestation").encode("ascii")
                ).hexdigest()
                source_snapshot = {"quality_eligibility": "FORMAL_COMPLETE"}
            self.states[item["corpus_item_id"]] = {
                "status": "SUCCEEDED",
                "attempt": 1,
                "worker_id": "fixture",
                "recorded_at": "2026-07-28T00:00:00.000Z",
                "row": {
                    "source_bytes_sha256_or_null": hashlib.sha256(
                        (item["corpus_item_id"] + "-bytes").encode("ascii")
                    ).hexdigest(),
                    "source_snapshot_hash_or_null": snapshot_hash,
                    "expected_attestation_hash_or_null": attestation,
                },
                "snapshot": source_snapshot,
            }

    def replay(self):
        return {
            "states": self.states,
            "event_count": 336,
            "event_chain_end_hash": "b" * 64,
            "physical_get_count": 336,
        }


class ResearchCorpusRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_default_research_corpus_plan()
        cls.plan_item = next(
            item
            for item in cls.plan["items"]
            if item["stream_id"] == "ETH_MARK_4H"
            and item["month"] == "2023-01"
        )
        monthly_request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="MARK_PRICE_KLINES",
            symbol="ETHUSDT",
            interval_or_null="4h",
            period_kind="MONTHLY",
            period="2023-01",
        )
        month_start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        missing_day = datetime(2023, 1, 10, tzinfo=timezone.utc)
        cls.base = build_research_degraded_historical_market_data_snapshot(
            snapshot_id="degraded-monthly-mark-202301",
            verified_archive=archive_for(
                monthly_request,
                mark_rows(month_start, 31 * 6, missing_day),
            ),
            retrieved_at="2026-07-28T00:00:00Z",
            ingested_at="2026-07-28T00:00:00Z",
            recorded_at="2026-07-28T00:00:00Z",
        )
        daily_request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="MARK_PRICE_KLINES",
            symbol="ETHUSDT",
            interval_or_null="4h",
            period_kind="DAILY",
            period="2023-01-10",
        )
        cls.patch = build_historical_market_data_snapshot(
            snapshot_id="daily-mark-20230110",
            verified_archive=archive_for(
                daily_request,
                mark_rows(missing_day, 6),
            ),
            retrieved_at="2026-07-28T00:00:01Z",
            ingested_at="2026-07-28T00:00:01Z",
            recorded_at="2026-07-28T00:00:01Z",
        )
        state = CompletedCorpusStateStub(
            cls.plan,
            cls.plan_item["corpus_item_id"],
            cls.base,
        )
        cls.corpus_snapshot = build_research_corpus_snapshot(
            plan=cls.plan,
            state=state,
            recorded_at="2026-07-28T00:00:02.000Z",
        )
        cls.base_snapshots = {
            cls.plan_item["corpus_item_id"]: cls.base,
        }

    def build(self):
        return build_research_corpus_repair_bundle(
            plan=self.plan,
            corpus_snapshot=self.corpus_snapshot,
            base_snapshots=self.base_snapshots,
            patch_snapshots=[self.patch],
            recorded_at="2026-07-28T00:00:03.000Z",
        )

    def test_derives_exact_daily_request_from_monthly_gap(self):
        requests = repair_requests_for_degraded_sources(
            plan=self.plan,
            corpus_snapshot=self.corpus_snapshot,
            base_snapshots=self.base_snapshots,
        )

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].period_kind, "DAILY")
        self.assertEqual(requests[0].period, "2023-01-10")
        self.assertEqual(requests[0].data_family, "MARK_PRICE_KLINES")

    def test_bundle_proves_exact_combined_coverage_and_stays_non_pit(self):
        bundle = self.build()
        repair = bundle["repairs"][0]

        self.assertEqual(bundle["summary"]["base_corpus_item_count"], 168)
        self.assertEqual(bundle["summary"]["base_degraded_item_count"], 1)
        self.assertEqual(bundle["summary"]["missing_interval_count"], 6)
        self.assertEqual(bundle["summary"]["repaired_interval_count"], 6)
        self.assertEqual(bundle["summary"]["unresolved_interval_count"], 0)
        self.assertEqual(repair["combined_interval_count"], 186)
        self.assertEqual(repair["missing_open_times"], repair["repaired_open_times"])
        self.assertEqual(
            bundle["research_training_readiness"],
            "READY_FOR_ARCHIVE_RESEARCH_FEATURE_BUILD_WITH_EXPLICIT_DAILY_REPAIRS",
        )
        self.assertEqual(bundle["formal_pit_eligibility"], "INELIGIBLE_ARCHIVE_REPLAY")
        self.assertEqual(
            bundle["repair_bundle_hash"],
            research_corpus_repair_bundle_hash(bundle),
        )
        self.assertEqual(
            research_corpus_repair_bundle_reasons(
                bundle,
                plan=self.plan,
                corpus_snapshot=self.corpus_snapshot,
                base_snapshots=self.base_snapshots,
                patch_snapshots=[self.patch],
            ),
            (),
        )

    def test_missing_wrong_or_duplicate_patch_fails_closed(self):
        with self.assertRaises(ResearchCorpusError) as missing:
            build_research_corpus_repair_bundle(
                plan=self.plan,
                corpus_snapshot=self.corpus_snapshot,
                base_snapshots=self.base_snapshots,
                patch_snapshots=[],
                recorded_at="2026-07-28T00:00:03.000Z",
            )
        self.assertEqual(
            missing.exception.reason_code,
            "CORPUS_REPAIR_PATCH_SET_INCOMPLETE",
        )
        with self.assertRaises(ResearchCorpusError) as duplicate:
            build_research_corpus_repair_bundle(
                plan=self.plan,
                corpus_snapshot=self.corpus_snapshot,
                base_snapshots=self.base_snapshots,
                patch_snapshots=[self.patch, self.patch],
                recorded_at="2026-07-28T00:00:03.000Z",
            )
        self.assertEqual(
            duplicate.exception.reason_code,
            "CORPUS_REPAIR_PATCH_SCOPE_INVALID",
        )

    def test_rehashed_bundle_semantic_tamper_is_detected(self):
        bundle = self.build()
        bundle["summary"]["missing_interval_count"] = 7
        bundle["repair_bundle_hash"] = research_corpus_repair_bundle_hash(bundle)

        self.assertIn(
            "CORPUS_REPAIR_SEMANTIC_MISMATCH",
            research_corpus_repair_bundle_reasons(
                bundle,
                plan=self.plan,
                corpus_snapshot=self.corpus_snapshot,
                base_snapshots=self.base_snapshots,
                patch_snapshots=[self.patch],
            ),
        )

    def test_publish_is_owner_only_and_conflict_rejecting(self):
        bundle = self.build()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            publish_research_corpus_repair_artifacts(
                bundle=bundle,
                patch_snapshots=[self.patch],
                output_root=root,
            )
            patch_path = (
                root
                / "repairs/source/"
                "USD_M_MARK_PRICE_KLINES_ETHUSDT/2023-01-10.json"
            )
            bundle_path = (
                root
                / "repairs/bundles"
                / f"{bundle['repair_bundle_id']}.json"
            )
            self.assertEqual(os.stat(patch_path).st_mode & 0o777, 0o600)
            self.assertEqual(os.stat(bundle_path).st_mode & 0o777, 0o600)
            for directory in (
                root,
                root / "repairs",
                root / "repairs/source",
                root / "repairs/bundles",
                patch_path.parent,
            ):
                self.assertEqual(os.stat(directory).st_mode & 0o777, 0o700)
            publish_research_corpus_repair_artifacts(
                bundle=bundle,
                patch_snapshots=[self.patch],
                output_root=root,
            )
            patch_path.write_text("tampered", encoding="utf-8")
            with self.assertRaises(ResearchCorpusError) as raised:
                publish_research_corpus_repair_artifacts(
                    bundle=bundle,
                    patch_snapshots=[self.patch],
                    output_root=root,
                )
            self.assertEqual(
                raised.exception.reason_code,
                "CORPUS_PUBLISH_CONFLICT",
            )

    def test_publish_revalidates_bundle_and_exact_patch_set(self):
        bundle = self.build()
        with tempfile.TemporaryDirectory() as directory:
            tampered = json.loads(json.dumps(bundle))
            tampered["summary"]["repaired_interval_count"] = 7
            with self.assertRaises(ResearchCorpusError) as bad_bundle:
                publish_research_corpus_repair_artifacts(
                    bundle=tampered,
                    patch_snapshots=[self.patch],
                    output_root=Path(directory),
                )
            self.assertEqual(
                bad_bundle.exception.reason_code,
                "CORPUS_REPAIR_BUNDLE_INVALID",
            )
            with self.assertRaises(ResearchCorpusError) as missing_patch:
                publish_research_corpus_repair_artifacts(
                    bundle=bundle,
                    patch_snapshots=[],
                    output_root=Path(directory),
                )
            self.assertEqual(
                missing_patch.exception.reason_code,
                "CORPUS_REPAIR_PATCH_SET_INCOMPLETE",
            )

    def test_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (
                root / "config/historical-research-corpus-repair-v1.schema.json"
            ).read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "historical-research-corpus-repair-v1.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
