import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from crypto_quant.market_data import (
    HistoricalArchiveRequest,
    HttpResponse,
    build_historical_market_data_snapshot,
    fetch_historical_market_data,
    fee_schedule_snapshot_hash,
    fee_schedule_snapshot_reasons,
    historical_market_data_snapshot_hash,
    historical_market_data_snapshot_reasons,
    verify_official_checksum,
)


INGESTED_AT = "2026-07-27T00:00:00Z"
RECORDED_AT = "2026-07-27T00:00:01Z"


def kline_request():
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="4h",
        period_kind="DAILY",
        period="2026-07-25",
    )


def kline_csv(*, first_close="101.5"):
    rows = []
    day_start_us = 1784937600000000
    interval_us = 4 * 60 * 60 * 1_000_000
    for index in range(6):
        opened = day_start_us + index * interval_us
        closed = opened + interval_us - 1
        close = first_close if index == 0 else "101.5"
        rows.append(
            f"{opened},100,102,99,{close},12,{closed},1218,7,6,609,0"
        )
    return ("\n".join(rows) + "\n").encode("ascii")


def zip_archive(request, csv_bytes):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.expected_csv_name, csv_bytes)
    return output.getvalue()


def checksum_for(request, archive_bytes):
    return (
        f"{hashlib.sha256(archive_bytes).hexdigest()}"
        f"  {request.archive_filename}\n"
    ).encode("ascii")


class MemoryTransport:
    def __init__(self, request, csv_bytes):
        archive_bytes = zip_archive(request, csv_bytes)
        checksum_bytes = checksum_for(request, archive_bytes)
        self.responses = {
            request.archive_url: HttpResponse(
                200,
                request.archive_url,
                {
                    "ETag": '"archive-etag"',
                    "Last-Modified": "Sun, 26 Jul 2026 02:41:56 GMT",
                },
                archive_bytes,
            ),
            request.checksum_url: HttpResponse(
                200,
                request.checksum_url,
                {},
                checksum_bytes,
            ),
        }

    def get(self, url):
        return self.responses[url]


class ProvenanceAndApprovedContractTests(unittest.TestCase):
    def setUp(self):
        self.request = kline_request()
        self.csv_bytes = kline_csv()
        self.archive_bytes = zip_archive(self.request, self.csv_bytes)
        self.checksum_bytes = checksum_for(self.request, self.archive_bytes)
        self.verified_archive = verify_official_checksum(
            self.request,
            self.archive_bytes,
            self.checksum_bytes,
        )

    def fetch(self, csv_bytes=None):
        return fetch_historical_market_data(
            self.request,
            MemoryTransport(self.request, csv_bytes or self.csv_bytes),
            INGESTED_AT,
        )

    def test_builder_requires_verified_archive_and_emits_full_approved_contract(self):
        snapshot = build_historical_market_data_snapshot(
            snapshot_id="verified-builder",
            verified_archive=self.verified_archive,
            retrieved_at=INGESTED_AT,
            ingested_at=INGESTED_AT,
            recorded_at=RECORDED_AT,
            source_etag_or_null='"archive-etag"',
            source_last_modified_at_or_null="Sun, 26 Jul 2026 02:41:56 GMT",
        )

        receipt = snapshot["source_receipt"]
        self.assertEqual(
            set(receipt),
            {
                "request",
                "archive_url",
                "checksum_url",
                "retrieved_at",
                "archive_size_bytes",
                "checksum_size_bytes",
                "official_sha256",
                "archive_sha256",
                "checksum_file_sha256",
                "csv_member",
                "csv_sha256",
                "source_rows_root_hash",
                "facts_root_hash",
                "source_etag_or_null",
                "source_last_modified_at_or_null",
                "receipt_hash",
            },
        )
        self.assertEqual(receipt["request"], snapshot["request"])
        self.assertEqual(receipt["archive_url"], self.request.archive_url)
        self.assertEqual(receipt["checksum_url"], self.request.checksum_url)
        self.assertEqual(receipt["csv_member"], self.request.expected_csv_name)
        self.assertEqual(receipt["archive_size_bytes"], len(self.archive_bytes))
        self.assertEqual(receipt["checksum_size_bytes"], len(self.checksum_bytes))
        self.assertEqual(receipt["official_sha256"], receipt["archive_sha256"])

        report = snapshot["quality_report"]
        self.assertEqual(
            set(report),
            {
                "row_count",
                "first_event_time",
                "last_event_time",
                "duplicate_business_key_count",
                "source_order_regression_count",
                "missing_interval_count",
                "malformed_row_count",
                "rejected_row_count",
                "checksum_pass",
                "expected_period_coverage",
                "warning_findings",
                "blocking_findings",
                "report_hash",
            },
        )
        self.assertEqual(report["row_count"], 6)
        self.assertTrue(report["checksum_pass"])
        self.assertTrue(report["expected_period_coverage"])
        self.assertEqual(report["missing_interval_count"], 0)

        fact = snapshot["facts"][0]
        self.assertEqual(
            {
                "source_row",
                "source_row_hash",
                "payload_hash",
                "open_time",
                "close_time",
                "volume",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            }
            - set(fact),
            set(),
        )
        self.assertEqual(fact["source_row"][4], "101.5")
        self.assertEqual(fact["close"], "101.5")
        self.assertEqual(fact["volume"], "12")
        self.assertEqual(fact["quote_asset_volume"], "1218")
        self.assertEqual(fact["number_of_trades"], 7)
        self.assertEqual(snapshot["parser_version"], "BINANCE_CSV_V1")
        self.assertEqual(
            snapshot["availability_basis"],
            "OFFLINE_ARCHIVE_OBSERVED_AT_INGESTION",
        )
        self.assertEqual(snapshot["pit_eligibility"], "ARCHIVE_REPLAY_ONLY")
        self.assertEqual(snapshot["quality_eligibility"], "FORMAL_COMPLETE")

    def test_fact_contract_carries_ingested_at_and_schema_requires_it(self):
        from jsonschema import Draft202012Validator

        snapshot = self.fetch()
        self.assertEqual(
            {fact["ingested_at"] for fact in snapshot["facts"]},
            {snapshot["ingested_at"]},
        )
        schema = json.loads(
            (
                Path(__file__).parents[1]
                / "config"
                / "historical-market-data-snapshot-v1.schema.json"
            ).read_text()
        )
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(snapshot)), [])

        missing_fact_ingestion = json.loads(json.dumps(snapshot))
        missing_fact_ingestion["facts"][0].pop("ingested_at")
        self.assertTrue(list(validator.iter_errors(missing_fact_ingestion)))

    def test_fact_ingested_at_must_crosslink_snapshot_and_source_row_replay(self):
        snapshot = self.fetch()
        trusted_receipt = snapshot["source_receipt"]["receipt_hash"]
        mutated = json.loads(json.dumps(snapshot))
        mutated["facts"][0]["ingested_at"] = RECORDED_AT
        mutated["snapshot_hash"] = historical_market_data_snapshot_hash(mutated)

        reasons = historical_market_data_snapshot_reasons(
            mutated,
            trusted_receipt_hashes={trusted_receipt},
        )
        self.assertIn("MARKET_DATA_FACT_TIME_CROSSLINK", reasons)
        self.assertIn("FACT_SOURCE_ROW_REPLAY_MISMATCH", reasons)

    def test_validator_replays_raw_row_and_rejects_normalized_close_rehash_probe(self):
        snapshot = self.fetch()
        trusted_receipt = snapshot["source_receipt"]["receipt_hash"]
        self.assertEqual(
            historical_market_data_snapshot_reasons(
                snapshot,
                trusted_receipt_hashes={trusted_receipt},
            ),
            (),
        )

        mutated = json.loads(json.dumps(snapshot))
        mutated["facts"][0]["close"] = "101.75"
        mutated["snapshot_hash"] = historical_market_data_snapshot_hash(mutated)

        self.assertIn(
            "FACT_SOURCE_ROW_REPLAY_MISMATCH",
            historical_market_data_snapshot_reasons(
                mutated,
                trusted_receipt_hashes={trusted_receipt},
            ),
        )

    def test_coordinated_raw_archive_checksum_rehash_needs_original_trusted_receipt(self):
        original = self.fetch()
        forged = self.fetch(kline_csv(first_close="101.75"))
        original_anchor = original["source_receipt"]["receipt_hash"]

        self.assertNotEqual(
            forged["source_receipt"]["archive_sha256"],
            original["source_receipt"]["archive_sha256"],
        )
        self.assertNotEqual(
            forged["source_receipt"]["receipt_hash"],
            original_anchor,
        )
        self.assertIn(
            "TRUSTED_RECEIPT_ATTESTATION_REQUIRED",
            historical_market_data_snapshot_reasons(forged),
        )
        self.assertIn(
            "TRUSTED_RECEIPT_ATTESTATION_MISMATCH",
            historical_market_data_snapshot_reasons(
                forged,
                trusted_receipt_hashes={original_anchor},
            ),
        )


class ApprovedFeeScheduleTests(unittest.TestCase):
    def schedule(self, *, environment="RESEARCH", second_tier="VIP_0"):
        snapshot = {
            "$schema": "./fee-schedule-snapshot-v1.schema.json",
            "schema_version": "1.0.0",
            "fee_schedule_id": "binance-usdm-vip-fees",
            "content_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "usage_environment": environment,
            "schedules": [
                {
                    "fee_id": "vip0-jan",
                    "venue": "BINANCE",
                    "product": "USD_M_PERPETUAL",
                    "account_tier": "VIP_0",
                    "symbol": "ETHUSDT",
                    "maker_rate": "0.0002",
                    "taker_rate": "0.0005",
                    "effective_from": "2024-01-01T00:00:00Z",
                    "effective_to_or_null": "2024-02-01T00:00:00Z",
                    "source_reference": "manual:binance-account-fee-export:2024-01",
                    "recorded_at": "2024-01-02T00:00:00Z",
                    "lifecycle": "DRAFT",
                    "approval": None,
                },
                {
                    "fee_id": "tier-two",
                    "venue": "BINANCE",
                    "product": "USD_M_PERPETUAL",
                    "account_tier": second_tier,
                    "symbol": "ETHUSDT",
                    "maker_rate": "0.00018",
                    "taker_rate": "0.00045",
                    "effective_from": "2024-01-15T00:00:00Z",
                    "effective_to_or_null": None,
                    "source_reference": "manual:binance-account-fee-export:2024-01-15",
                    "recorded_at": "2024-01-16T00:00:00Z",
                    "lifecycle": "APPROVED",
                    "approval": {
                        "approved_by": "research-review",
                        "approved_at": "2024-01-16T01:00:00Z",
                        "approval_reference": "research-only:review-17",
                    },
                },
            ],
        }
        snapshot["content_hash"] = fee_schedule_snapshot_hash(snapshot)
        return snapshot

    def test_research_contract_has_approved_tier_fields_and_tier_scoped_overlap(self):
        independent_tiers = self.schedule(second_tier="VIP_1")
        self.assertEqual(fee_schedule_snapshot_reasons(independent_tiers), ())
        self.assertEqual(
            independent_tiers["content_hash"],
            fee_schedule_snapshot_hash(independent_tiers),
        )

        overlapping_same_tier = self.schedule(second_tier="VIP_0")
        self.assertIn(
            "FEE_SCHEDULE_EFFECTIVE_INTERVAL_OVERLAP",
            fee_schedule_snapshot_reasons(overlapping_same_tier),
        )

    def test_production_is_unconditionally_unsupported_without_external_approver(self):
        production = self.schedule(
            environment="PRODUCTION",
            second_tier="VIP_1",
        )
        production["production_approval"] = {
            "approved_by": "caller-controlled-name",
            "approved_at": "2024-01-16T01:00:00Z",
            "approval_reference": "caller-controlled-reference",
        }
        production["content_hash"] = fee_schedule_snapshot_hash(production)

        self.assertIn(
            "FEE_SCHEDULE_PRODUCTION_UNSUPPORTED",
            fee_schedule_snapshot_reasons(production),
        )

    def test_fee_schema_requires_full_effective_source_and_lifecycle_contract(self):
        from jsonschema import Draft202012Validator
        from pathlib import Path

        schema = json.loads(
            (
                Path(__file__).parents[1]
                / "config"
                / "fee-schedule-snapshot-v1.schema.json"
            ).read_text()
        )
        validator = Draft202012Validator(schema)
        valid = self.schedule(second_tier="VIP_1")
        self.assertEqual(list(validator.iter_errors(valid)), [])
        for missing in (
            "venue",
            "product",
            "account_tier",
            "effective_from",
            "effective_to_or_null",
            "source_reference",
            "recorded_at",
            "lifecycle",
            "approval",
        ):
            invalid = json.loads(json.dumps(valid))
            invalid["schedules"][0].pop(missing)
            with self.subTest(missing=missing):
                self.assertTrue(list(validator.iter_errors(invalid)))


def funding_request():
    return HistoricalArchiveRequest.create(
        market="USD_M",
        data_family="FUNDING_RATE",
        symbol="ETHUSDT",
        interval_or_null=None,
        period_kind="MONTHLY",
        period="2024-01",
    )


def variable_funding_rows():
    rows = []
    current = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 2, 1, tzinfo=timezone.utc)
    schedule_change = datetime(2024, 1, 16, tzinfo=timezone.utc)
    while current < end:
        interval_hours = 8 if current < schedule_change else 4
        rows.append(
            f"{int(current.timestamp() * 1000)},{interval_hours},0.0001"
        )
        current += timedelta(hours=interval_hours)
    return rows


def verified_funding_archive(rows):
    request = funding_request()
    csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
    archive_bytes = zip_archive(request, csv_bytes)
    return verify_official_checksum(
        request,
        archive_bytes,
        checksum_for(request, archive_bytes),
    )


class FundingScheduleAndDegradedResearchTests(unittest.TestCase):
    def build(self, rows, *, degraded=False):
        builder = build_historical_market_data_snapshot
        if degraded:
            from crypto_quant.market_data import (
                build_research_degraded_historical_market_data_snapshot,
            )

            builder = build_research_degraded_historical_market_data_snapshot
        return builder(
            snapshot_id="funding-2024-01",
            verified_archive=verified_funding_archive(rows),
            retrieved_at=INGESTED_AT,
            ingested_at=INGESTED_AT,
            recorded_at=RECORDED_AT,
        )

    def test_source_funding_intervals_allow_schedule_change_and_drive_continuity(self):
        rows = variable_funding_rows()
        snapshot = self.build(rows)
        intervals = {fact["funding_interval_hours"] for fact in snapshot["facts"]}
        self.assertEqual(intervals, {4, 8})
        self.assertEqual(snapshot["quality_report"]["missing_interval_count"], 0)
        self.assertTrue(snapshot["quality_report"]["expected_period_coverage"])
        self.assertEqual(
            historical_market_data_snapshot_reasons(
                snapshot,
                trusted_receipt_hashes={
                    snapshot["source_receipt"]["receipt_hash"]
                },
            ),
            (),
        )

    def test_funding_interval_is_a_strict_source_integer_in_safe_range(self):
        rows = variable_funding_rows()
        for invalid in ("0", "25", "1.5", "-1"):
            altered = list(rows)
            fields = altered[0].split(",")
            fields[1] = invalid
            altered[0] = ",".join(fields)
            with self.subTest(invalid=invalid):
                with self.assertRaises(Exception) as raised:
                    self.build(altered)
                self.assertEqual(
                    getattr(raised.exception, "reason_code", None),
                    "MARKET_FACT_INVALID",
                )

    def test_gap_is_explicit_and_only_buildable_as_research_degraded(self):
        rows = variable_funding_rows()
        rows.pop(10)
        with self.assertRaises(Exception) as raised:
            self.build(rows)
        self.assertEqual(
            getattr(raised.exception, "reason_code", None),
            "MARKET_DATA_QUALITY_BLOCKING",
        )

        degraded = self.build(rows, degraded=True)
        report = degraded["quality_report"]
        self.assertEqual(
            degraded["quality_eligibility"],
            "RESEARCH_ONLY_DEGRADED",
        )
        self.assertEqual(degraded["pit_eligibility"], "ARCHIVE_REPLAY_ONLY")
        self.assertGreater(report["missing_interval_count"], 0)
        self.assertFalse(report["expected_period_coverage"])
        self.assertIn("MARKET_DATA_FUNDING_GAP", report["blocking_findings"])
        self.assertIn(
            "MARKET_DATA_RESEARCH_ONLY_DEGRADED",
            historical_market_data_snapshot_reasons(
                degraded,
                trusted_receipt_hashes={
                    degraded["source_receipt"]["receipt_hash"]
                },
            ),
        )

    def test_research_degraded_path_does_not_admit_duplicate_source_facts(self):
        rows = variable_funding_rows()
        rows.insert(10, rows[10])
        with self.assertRaises(Exception) as raised:
            self.build(rows, degraded=True)
        self.assertEqual(
            getattr(raised.exception, "reason_code", None),
            "MARKET_DATA_QUALITY_BLOCKING",
        )

    def test_funding_quality_counts_each_missing_source_interval(self):
        rows = variable_funding_rows()
        del rows[10:12]
        degraded = self.build(rows, degraded=True)
        self.assertEqual(
            degraded["quality_report"]["missing_interval_count"],
            2,
        )


class ImmutablePublisherCommitPointTests(unittest.TestCase):
    def test_idempotent_commit_rejects_same_byte_final_name_inode_replacement(self):
        import crypto_quant.market_data_cli as cli

        payload = b'{"immutable":true}'
        artifact_name = "commit-point.json"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "market-data"
            output.mkdir()
            artifact = output / artifact_name
            artifact.write_bytes(payload)
            original_inode = artifact.stat().st_ino
            original_require = cli._require_attached_directory
            calls = 0

            def replace_during_final_attachment_check(root_fd, output_fd):
                nonlocal calls
                calls += 1
                original_require(root_fd, output_fd)
                if calls == 2:
                    artifact.rename(output / "superseded.json")
                    artifact.write_bytes(payload)

            with patch(
                "crypto_quant.market_data_cli._require_attached_directory",
                side_effect=replace_during_final_attachment_check,
            ):
                with self.assertRaises(Exception) as raised:
                    cli._publish_immutable(root, artifact_name, payload)

            self.assertEqual(
                getattr(raised.exception, "reason_code", None),
                "ARTIFACT_OUTPUT_INVALID",
            )
            self.assertNotEqual(artifact.stat().st_ino, original_inode)

    def test_collision_idempotent_commit_rejects_last_moment_final_replacement(self):
        import crypto_quant.market_data_cli as cli

        payload = b'{"immutable":true}'
        artifact_name = "collision-commit-point.json"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "market-data"
            output.mkdir()
            artifact = output / artifact_name
            original_link = cli.os.link
            original_require = cli._require_attached_directory
            attachment_checks = 0

            def collide(*args, **kwargs):
                artifact.write_bytes(payload)
                raise FileExistsError

            def replace_during_final_attachment_check(root_fd, output_fd):
                nonlocal attachment_checks
                attachment_checks += 1
                original_require(root_fd, output_fd)
                if attachment_checks == 3:
                    artifact.rename(output / "collision-superseded.json")
                    artifact.write_bytes(payload)

            with patch(
                "crypto_quant.market_data_cli.os.link",
                side_effect=collide,
            ), patch(
                "crypto_quant.market_data_cli._require_attached_directory",
                side_effect=replace_during_final_attachment_check,
            ):
                with self.assertRaises(Exception) as raised:
                    cli._publish_immutable(root, artifact_name, payload)

            self.assertEqual(
                getattr(raised.exception, "reason_code", None),
                "ARTIFACT_OUTPUT_INVALID",
            )
            self.assertTrue((output / "collision-superseded.json").exists())
