import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from crypto_quant.market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    build_historical_market_data_snapshot,
    extract_expected_csv,
    fee_schedule_snapshot_hash,
    fee_schedule_snapshot_reasons,
    historical_market_data_snapshot_attestation_hash,
    historical_market_data_snapshot_hash,
    historical_market_data_snapshot_reasons,
    parse_market_facts,
    verify_official_checksum,
)


class HistoricalArchiveRequestTests(unittest.TestCase):
    def test_spot_daily_kline_request_has_exact_allowlisted_urls(self):
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2024-01-02",
        )

        self.assertEqual(
            request.archive_url,
            "https://data.binance.vision/data/spot/daily/klines/"
            "ETHUSDT/1m/ETHUSDT-1m-2024-01-02.zip",
        )
        self.assertEqual(
            request.checksum_url,
            "https://data.binance.vision/data/spot/daily/klines/"
            "ETHUSDT/1m/ETHUSDT-1m-2024-01-02.zip.CHECKSUM",
        )

    def test_spot_daily_aggtrade_request_has_exact_allowlisted_urls(self):
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="AGG_TRADES",
            symbol="BTCUSDT",
            interval_or_null=None,
            period_kind="DAILY",
            period="2024-01-02",
        )

        self.assertEqual(
            request.archive_url,
            "https://data.binance.vision/data/spot/daily/aggTrades/"
            "BTCUSDT/BTCUSDT-aggTrades-2024-01-02.zip",
        )
        self.assertEqual(
            request.checksum_url,
            "https://data.binance.vision/data/spot/daily/aggTrades/"
            "BTCUSDT/BTCUSDT-aggTrades-2024-01-02.zip.CHECKSUM",
        )

    def test_usdm_daily_mark_price_kline_request_has_exact_allowlisted_urls(self):
        request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="MARK_PRICE_KLINES",
            symbol="ETHUSDT",
            interval_or_null="4h",
            period_kind="DAILY",
            period="2024-01-02",
        )

        self.assertEqual(
            request.archive_url,
            "https://data.binance.vision/data/futures/um/daily/markPriceKlines/"
            "ETHUSDT/4h/ETHUSDT-4h-2024-01-02.zip",
        )
        self.assertEqual(
            request.checksum_url,
            "https://data.binance.vision/data/futures/um/daily/markPriceKlines/"
            "ETHUSDT/4h/ETHUSDT-4h-2024-01-02.zip.CHECKSUM",
        )

    def test_monthly_kline_requests_have_exact_official_urls(self):
        cases = (
            (
                {
                    "market": "SPOT",
                    "data_family": "KLINES",
                    "symbol": "ETHUSDT",
                    "interval_or_null": "4h",
                    "period_kind": "MONTHLY",
                    "period": "2024-02",
                },
                "https://data.binance.vision/data/spot/monthly/klines/"
                "ETHUSDT/4h/ETHUSDT-4h-2024-02.zip",
            ),
            (
                {
                    "market": "USD_M",
                    "data_family": "MARK_PRICE_KLINES",
                    "symbol": "ETHUSDT",
                    "interval_or_null": "4h",
                    "period_kind": "MONTHLY",
                    "period": "2024-02",
                },
                "https://data.binance.vision/data/futures/um/monthly/"
                "markPriceKlines/ETHUSDT/4h/ETHUSDT-4h-2024-02.zip",
            ),
        )
        for fields, expected_url in cases:
            with self.subTest(fields=fields):
                request = HistoricalArchiveRequest.create(**fields)
                self.assertEqual(request.archive_url, expected_url)
                self.assertEqual(request.checksum_url, expected_url + ".CHECKSUM")

    def test_monthly_usdm_funding_request_has_exact_urls_without_interval(self):
        request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="FUNDING_RATE",
            symbol="BTCUSDT",
            interval_or_null=None,
            period_kind="MONTHLY",
            period="2024-01",
        )

        self.assertEqual(
            request.archive_url,
            "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
            "BTCUSDT/BTCUSDT-fundingRate-2024-01.zip",
        )
        self.assertEqual(
            request.checksum_url,
            "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
            "BTCUSDT/BTCUSDT-fundingRate-2024-01.zip.CHECKSUM",
        )

    def test_request_rejects_unsupported_or_ambiguous_combinations(self):
        invalid_requests = (
            {"market": "SPOT", "data_family": "KLINES", "symbol": "SOLUSDT", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "SPOT", "data_family": "KLINES", "symbol": "ethusdt", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "USD_M", "data_family": "KLINES", "symbol": "ETHUSDT", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "SPOT", "data_family": "AGG_TRADES", "symbol": "ETHUSDT", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "USD_M", "data_family": "FUNDING_RATE", "symbol": "ETHUSDT", "interval_or_null": "1m", "period_kind": "MONTHLY", "period": "2024-01"},
            {"market": "USD_M", "data_family": "FUNDING_RATE", "symbol": "ETHUSDT", "interval_or_null": None, "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "SPOT", "data_family": "KLINES", "symbol": "ETHUSDT", "interval_or_null": "30m", "period_kind": "DAILY", "period": "2024-01-02"},
            {"market": "SPOT", "data_family": "KLINES", "symbol": "ETHUSDT", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-2-02"},
            {"market": "SPOT", "data_family": "KLINES", "symbol": "ETHUSDT", "interval_or_null": "1m", "period_kind": "DAILY", "period": "2024-02-30"},
            {"market": "USD_M", "data_family": "FUNDING_RATE", "symbol": "ETHUSDT", "interval_or_null": None, "period_kind": "MONTHLY", "period": "2024-13"},
        )

        for params in invalid_requests:
            with self.subTest(params=params):
                with self.assertRaises(MarketDataError) as raised:
                    HistoricalArchiveRequest.create(**params)
                self.assertEqual(raised.exception.reason_code, "REQUEST_INVALID")

    def test_request_cannot_be_constructed_without_allowlist_validation(self):
        direct_requests = (
            {
                "schema_version": "1.0.0",
                "provider": "BINANCE_PUBLIC_DATA",
                "market": "SPOT",
                "data_family": "KLINES",
                "symbol": "SOLUSDT",
                "interval_or_null": "1m",
                "period_kind": "DAILY",
                "period": "2024-01-02",
            },
            {
                "schema_version": "1.0.0",
                "provider": "BINANCE_PUBLIC_DATA",
                "market": "SPOT",
                "data_family": "KLINES",
                "symbol": "ETHUSDT",
                "interval_or_null": "../1m",
                "period_kind": "DAILY",
                "period": "2024-01-02",
            },
        )

        for fields in direct_requests:
            with self.subTest(fields=fields):
                with self.assertRaises(TypeError):
                    HistoricalArchiveRequest(**fields)

    def test_request_private_constructor_requires_internal_token(self):
        with self.assertRaises(TypeError):
            HistoricalArchiveRequest._from_validated(
                market="SPOT",
                data_family="KLINES",
                symbol="SOLUSDT",
                interval_or_null="1m",
                period_kind="DAILY",
                period="2024-01-02",
            )


def archive_request():
    return HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period="2024-01-02",
    )


def zip_bytes(*members):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)
    return output.getvalue()


def mutate_first_zip_member(data, *, encrypted=False, compressed_size=None, file_size=None):
    altered = bytearray(data)
    local = altered.index(b"PK\x03\x04")
    central = altered.index(b"PK\x01\x02")
    if encrypted:
        struct.pack_into("<H", altered, local + 6, 1)
        struct.pack_into("<H", altered, central + 8, 1)
    if compressed_size is not None:
        struct.pack_into("<I", altered, central + 20, compressed_size)
    if file_size is not None:
        struct.pack_into("<I", altered, central + 24, file_size)
    return bytes(altered)


class ArchiveIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.request = archive_request()
        self.archive_bytes = b"archive-bytes"
        self.checksum_bytes = (
            b"0c982986710a026635603031674053ca851fc0e3ea760094a34f59b84f7f6da6"
            b"  ETHUSDT-1m-2024-01-02.zip\n"
        )
        self.csv_bytes = b"open,high,low,close\n1,2,1,2\n"

    def assert_reason(self, expected, callable_object, *args):
        with self.assertRaises(MarketDataError) as raised:
            callable_object(*args)
        self.assertEqual(raised.exception.reason_code, expected)

    def checksum_for(self, archive_bytes):
        return (
            f"{hashlib.sha256(archive_bytes).hexdigest()}"
            f"  {self.request.archive_filename}\n"
        ).encode("ascii")

    def verified_archive(self, archive_bytes):
        return verify_official_checksum(
            self.request,
            archive_bytes,
            self.checksum_for(archive_bytes),
        )

    def test_checksum_accepts_exact_single_official_record(self):
        verify_official_checksum(
            self.request,
            self.archive_bytes,
            self.checksum_bytes,
        )

    def test_checksum_rejects_digest_filename_and_text_violations(self):
        cases = (
            (
                "CHECKSUM_DIGEST_MISMATCH",
                b"fc982986710a026635603031674053ca851fc0e3ea760094a34f59b84f7f6da6"
                b"  ETHUSDT-1m-2024-01-02.zip\n",
            ),
            (
                "CHECKSUM_FILENAME_MISMATCH",
                b"0c982986710a026635603031674053ca851fc0e3ea760094a34f59b84f7f6da6"
                b"  other.zip\n",
            ),
            ("CHECKSUM_MALFORMED", b"not a checksum\n"),
            ("CHECKSUM_TOO_LARGE", b"a" * 4097),
        )

        for reason_code, checksum_bytes in cases:
            with self.subTest(reason_code=reason_code):
                self.assert_reason(
                    reason_code,
                    verify_official_checksum,
                    self.request,
                    self.archive_bytes,
                    checksum_bytes,
                )

    def test_extracts_only_the_expected_csv_member(self):
        archive = zip_bytes(
            (self.request.expected_csv_name, self.csv_bytes),
        )
        verified_archive = self.verified_archive(archive)

        self.assertIsNotNone(verified_archive)
        self.assertEqual(
            extract_expected_csv(
                self.request,
                verified_archive=verified_archive,
            ),
            self.csv_bytes,
        )

    def test_zip_extraction_rejects_unverified_archive_bytes(self):
        archive = zip_bytes(
            (self.request.expected_csv_name, self.csv_bytes),
        )

        self.assert_reason(
            "ARCHIVE_UNVERIFIED",
            extract_expected_csv,
            self.request,
            archive,
        )

    def test_zip_rejects_member_count_and_name_violations(self):
        cases = (
            (
                "ZIP_MEMBER_COUNT",
                zip_bytes(
                    (self.request.expected_csv_name, self.csv_bytes),
                    ("extra.csv", self.csv_bytes),
                ),
            ),
            ("ZIP_MEMBER_NAME", zip_bytes(("unexpected.csv", self.csv_bytes))),
            ("ZIP_MEMBER_NAME", zip_bytes(("/absolute.csv", self.csv_bytes))),
            ("ZIP_MEMBER_NAME", zip_bytes(("../traversal.csv", self.csv_bytes))),
        )

        for reason_code, archive in cases:
            with self.subTest(reason_code=reason_code):
                self.assert_reason(
                    reason_code,
                    extract_expected_csv,
                    self.request,
                    self.verified_archive(archive),
                )

    def test_zip_rejects_encryption_and_declared_size_bombs(self):
        valid = zip_bytes((self.request.expected_csv_name, self.csv_bytes))
        cases = (
            ("ZIP_MEMBER_ENCRYPTED", mutate_first_zip_member(valid, encrypted=True)),
            (
                "ZIP_MEMBER_COMPRESSED_SIZE",
                mutate_first_zip_member(valid, compressed_size=64 * 1024 * 1024 + 1),
            ),
            (
                "ZIP_MEMBER_UNCOMPRESSED_SIZE",
                mutate_first_zip_member(valid, file_size=256 * 1024 * 1024 + 1),
            ),
            (
                "ZIP_COMPRESSION_RATIO",
                mutate_first_zip_member(valid, compressed_size=1, file_size=101),
            ),
        )

        for reason_code, archive in cases:
            with self.subTest(reason_code=reason_code):
                self.assert_reason(
                    reason_code,
                    extract_expected_csv,
                    self.request,
                    self.verified_archive(archive),
                )

    def test_zip_rejects_malformed_archive(self):
        self.assert_reason(
            "ZIP_MALFORMED",
            extract_expected_csv,
            self.request,
            self.verified_archive(b"not-a-zip"),
        )


class SpotParserTests(unittest.TestCase):
    def request(self, family="KLINES", period="2024-01-02"):
        return HistoricalArchiveRequest.create(
            market="SPOT",
            data_family=family,
            symbol="ETHUSDT",
            interval_or_null="1m" if family == "KLINES" else None,
            period_kind="DAILY",
            period=period,
        )

    def test_spot_kline_timestamp_unit_changes_at_2025_boundary(self):
        before = parse_market_facts(
            self.request(period="2024-12-31"),
            b"1735689540000,100.00,102.0,99.0,101.500,12,1735689599999,0,1,0,0,0\n",
            "2026-07-27T00:00:00Z",
        )
        after = parse_market_facts(
            self.request(period="2025-01-01"),
            b"open time,open,high,low,close,volume,close time,quote asset volume,number of trades,taker buy base asset volume,taker buy quote asset volume,ignore\n"
            b"1735689600123456,100.00,102.0,99.0,101.500,12,1735689660123455,0,1,0,0,0\n",
            "2026-07-27T00:00:00Z",
        )

        self.assertEqual(before[0]["event_time"], "2024-12-31T23:59:59.999Z")
        self.assertEqual(after[0]["event_time"], "2025-01-01T00:01:00.123455Z")
        self.assertEqual(after[0]["open"], "100")
        self.assertEqual(after[0]["close"], "101.5")
        self.assertEqual(after[0]["available_at"], "2026-07-27T00:00:00Z")

    def test_spot_aggtrade_normalizes_exact_decimal_and_business_id(self):
        facts = parse_market_facts(
            self.request("AGG_TRADES"),
            b"aggregate tradeId,price,quantity,first tradeId,last tradeId,transact time,is buyer maker,is best match\n"
            b"17,00001.2300,2.5000,100,102,1704153600123,true,false\n",
            "2026-07-27T00:00:00Z",
        )

        self.assertEqual(facts[0]["price"], "1.23")
        self.assertEqual(facts[0]["quantity"], "2.5")
        self.assertEqual(facts[0]["business_key"], "ETHUSDT:17")
        self.assertTrue(facts[0]["is_buyer_maker"])
        self.assertFalse(facts[0]["is_best_match"])
        self.assertTrue(facts[0]["fact_id"].startswith("mdf_"))

    def test_spot_aggtrade_uses_microseconds_from_2025(self):
        facts = parse_market_facts(
            self.request("AGG_TRADES", period="2025-01-01"),
            b"18,1.23,2.5,103,104,1735689600123456,false,true\n",
            "2026-07-27T00:00:00Z",
        )
        self.assertEqual(facts[0]["event_time"], "2025-01-01T00:00:00.123456Z")

    def test_market_fact_id_changes_when_source_row_content_changes(self):
        request = self.request()
        first = parse_market_facts(
            request, b"1704153600000,100,101,99,100.5,1,1704153659999,0,1,0,0,0\n",
            "2026-07-27T00:00:00Z",
        )
        revised = parse_market_facts(
            request, b"1704153600000,100,102,99,101,1,1704153659999,0,1,0,0,0\n",
            "2026-07-27T00:00:00Z",
        )
        self.assertNotEqual(first[0]["fact_id"], revised[0]["fact_id"])

    def test_spot_parsers_reject_malformed_business_values(self):
        cases = (
            (self.request(), b"1,2,3\n"),
            (self.request(), b"wrong,header\n1,2\n"),
            (self.request("AGG_TRADES"), b"1,1,1,3,2,1704153600123,true,false\n"),
            (self.request("AGG_TRADES"), b"1,nope,1,1,1,1704153600123,true,false\n"),
            (self.request("AGG_TRADES"), b"1,1,1,1,1,1735689600123456,true,false\n"),
            (self.request(), b"1704153600000,3,2,1,4,1,1704153659999,0,1,0,0,0\n"),
            (self.request("AGG_TRADES"), b"1,1,1,1,1,1704153600123,yes,false\n"),
        )
        for request, csv_bytes in cases:
            with self.subTest(csv_bytes=csv_bytes):
                with self.assertRaises(MarketDataError) as raised:
                    parse_market_facts(request, csv_bytes, "2026-07-27T00:00:00Z")
                self.assertEqual(raised.exception.reason_code, "MARKET_FACT_INVALID")

    def test_spot_rejects_microseconds_before_2025_boundary(self):
        with self.assertRaises(MarketDataError) as raised:
            parse_market_facts(
                self.request(period="2024-01-02"),
                b"1704153600000000,100,101,99,100.5,1,1704153659999999,0,1,0,0,0\n",
                "2026-07-27T00:00:00Z",
            )
        self.assertEqual(raised.exception.reason_code, "MARKET_FACT_INVALID")


class UsdMParserTests(unittest.TestCase):
    def request(self, family="MARK_PRICE_KLINES"):
        return HistoricalArchiveRequest.create(
            market="USD_M",
            data_family=family,
            symbol="BTCUSDT",
            interval_or_null="1m" if family == "MARK_PRICE_KLINES" else None,
            period_kind="DAILY" if family == "MARK_PRICE_KLINES" else "MONTHLY",
            period="2024-01-02" if family == "MARK_PRICE_KLINES" else "2024-01",
        )

    def test_usdm_mark_kline_enforces_millisecond_time_and_ohlc_rules(self):
        facts = parse_market_facts(
            self.request(),
            b"1704153600000,40000.00,40100,39900,40050.500,0,1704153659999,0,0,0,0,0\n",
            "2026-07-27T00:00:00Z",
        )
        self.assertEqual(facts[0]["event_time"], "2024-01-02T00:00:59.999Z")
        self.assertEqual(facts[0]["high"], "40100")

        with self.assertRaises(MarketDataError) as raised:
            parse_market_facts(
                self.request(),
                b"1704153600000000,4,5,3,4,0,1704153659999,0,0,0,0,0\n",
                "2026-07-27T00:00:00Z",
            )
        self.assertEqual(raised.exception.reason_code, "MARKET_FACT_INVALID")

    def test_usdm_kline_rejects_invalid_non_ohlc_business_columns(self):
        valid = [
            "1704153600000", "4", "5", "3", "4", "1", "1704153659999",
            "4", "1", "0.5", "2", "0",
        ]
        for index, value in ((5, "-1"), (7, "nope"), (8, "1.5"), (9, "-0.1"), (10, "NaN"), (11, "1")):
            row = list(valid)
            row[index] = value
            with self.subTest(index=index, value=value):
                with self.assertRaises(MarketDataError) as raised:
                    parse_market_facts(
                        self.request(), (",".join(row) + "\n").encode("ascii"),
                        "2026-07-27T00:00:00Z",
                    )
                self.assertEqual(raised.exception.reason_code, "MARKET_FACT_INVALID")

    def test_usdm_funding_preserves_signed_rate_and_validates_symbol_columns(self):
        facts = parse_market_facts(
            self.request("FUNDING_RATE"),
            b"calc_time,funding_interval_hours,last_funding_rate\n1704153600000,8,-0.00010000\n"
            b"1704182400000,8,+0.00020000\n",
            "2026-07-27T00:00:00Z",
        )
        self.assertEqual(facts[0]["funding_rate"], "-0.0001")
        self.assertEqual(facts[1]["funding_rate"], "0.0002")
        self.assertEqual(facts[0]["fact_type"], "FUNDING_RATE")
        with self.assertRaises(MarketDataError) as raised:
            parse_market_facts(
                self.request("FUNDING_RATE"),
                b"BTCUSDT,1704153600000,8,0.1\n",
                "2026-07-27T00:00:00Z",
            )
        self.assertEqual(raised.exception.reason_code, "MARKET_FACT_INVALID")


class MarketDataArtifactTests(unittest.TestCase):
    def setUp(self):
        self.request = HistoricalArchiveRequest.create(
            market="SPOT", data_family="KLINES", symbol="ETHUSDT",
            interval_or_null="1m", period_kind="DAILY", period="2024-01-02",
        )
        start = 1704153600000
        rows = []
        for index in range(1440):
            opened = start + index * 60_000
            rows.append(f"{opened},100,101,99,100.5,1,{opened + 59999},0,1,0,0,0")
        self.csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
        self.facts = parse_market_facts(
            self.request, self.csv_bytes,
            "2026-07-27T00:00:00Z",
        )
        archive = zip_bytes((self.request.expected_csv_name, self.csv_bytes))
        self.verified_archive = verify_official_checksum(
            self.request,
            archive,
            (
                f"{hashlib.sha256(archive).hexdigest()}"
                f"  {self.request.archive_filename}\n"
            ).encode("ascii"),
        )

    def build(self, facts=None, **overrides):
        verified_archive = self.verified_archive
        if facts is not None:
            csv_bytes = (
                "\n".join(",".join(fact["source_row"]) for fact in facts)
                + "\n"
            ).encode("utf-8")
            archive = zip_bytes((self.request.expected_csv_name, csv_bytes))
            verified_archive = verify_official_checksum(
                self.request,
                archive,
                (
                    f"{hashlib.sha256(archive).hexdigest()}"
                    f"  {self.request.archive_filename}\n"
                ).encode("ascii"),
            )
        fields = {
            "snapshot_id": "historical-ethusdt-20240102",
            "verified_archive": verified_archive,
            "retrieved_at": "2026-07-27T00:00:00Z",
            "ingested_at": "2026-07-27T00:00:00Z",
            "recorded_at": "2026-07-27T00:00:01Z",
        }
        fields.update(overrides)
        return build_historical_market_data_snapshot(**fields)

    def test_artifact_has_hashed_receipt_report_snapshot_and_deterministic_replay(self):
        snapshot = self.build()
        self.assertEqual(snapshot["snapshot_hash"], historical_market_data_snapshot_hash(snapshot))
        self.assertEqual(snapshot["source_receipt"]["receipt_hash"], hashlib.sha256(
            json.dumps(
                {key: value for key, value in snapshot["source_receipt"].items() if key != "receipt_hash"},
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest())
        self.assertEqual(snapshot["quality_report"]["report_hash"], hashlib.sha256(
            json.dumps(
                {key: value for key, value in snapshot["quality_report"].items() if key != "report_hash"},
                sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest())
        self.assertEqual(snapshot["pit_eligibility"], "ARCHIVE_REPLAY_ONLY")
        self.assertIn(
            "TRUSTED_SNAPSHOT_ATTESTATION_REQUIRED",
            historical_market_data_snapshot_reasons(snapshot),
        )
        self.assertEqual(
            historical_market_data_snapshot_reasons(
                snapshot,
                trusted_snapshot_attestation_hashes={
                    historical_market_data_snapshot_attestation_hash(snapshot)
                },
            ),
            (),
        )
        self.assertEqual(snapshot, self.build())

    def test_artifact_rejects_source_order_duplicates_gaps_and_time_order(self):
        gap = tuple(self.facts[:10]) + tuple(self.facts[11:])
        with self.assertRaises(MarketDataError) as raised:
            self.build(gap)
        self.assertEqual(
            raised.exception.reason_code,
            "MARKET_DATA_QUALITY_BLOCKING",
        )
        with self.assertRaises(MarketDataError) as raised:
            self.build(recorded_at="2026-07-26T23:59:59Z")
        self.assertEqual(raised.exception.reason_code, "MARKET_DATA_QUALITY_BLOCKING")

    def test_artifact_rejects_facts_missing_required_family_payload(self):
        snapshot = self.build()
        incomplete = json.loads(json.dumps(snapshot))
        incomplete["facts"][0].pop("close")
        incomplete["snapshot_hash"] = historical_market_data_snapshot_hash(
            incomplete
        )
        self.assertIn(
            "FACT_SOURCE_ROW_REPLAY_MISMATCH",
            historical_market_data_snapshot_reasons(
                incomplete,
                trusted_snapshot_attestation_hashes={
                    historical_market_data_snapshot_attestation_hash(snapshot)
                },
            ),
        )

    def test_artifact_binds_fact_identity_to_verified_archive_and_base_schema(self):
        first = self.build()
        revised_facts = [dict(fact) for fact in self.facts]
        revised_facts[0] = dict(revised_facts[0])
        revised_facts[0]["source_row"] = list(revised_facts[0]["source_row"])
        revised_facts[0]["source_row"][4] = "100.75"
        revised_archive = self.build(revised_facts)
        self.assertNotEqual(first["facts"][0]["fact_id"], revised_archive["facts"][0]["fact_id"])
        invalid_id = json.loads(json.dumps(first))
        invalid_id["facts"][0]["fact_id"] = 1
        invalid_id["snapshot_hash"] = historical_market_data_snapshot_hash(
            invalid_id
        )
        self.assertIn(
            "MARKET_DATA_SCHEMA_INVALID",
            historical_market_data_snapshot_reasons(
                invalid_id,
                trusted_snapshot_attestation_hashes={
                    historical_market_data_snapshot_attestation_hash(first)
                },
            ),
        )

    def test_artifact_allows_equal_aggtrade_times_when_business_ids_increase(self):
        request = HistoricalArchiveRequest.create(
            market="SPOT", data_family="AGG_TRADES", symbol="ETHUSDT",
            interval_or_null=None, period_kind="DAILY", period="2024-01-02",
        )
        facts = parse_market_facts(
            request,
            b"1,1,1,1,1,1704153600000,true,false\n2,1,1,2,2,1704153600000,false,true\n",
            "2026-07-27T00:00:00Z",
        )
        csv_bytes = b"\n".join(
            ",".join(fact["source_row"]).encode("ascii") for fact in facts
        ) + b"\n"
        archive = zip_bytes((request.expected_csv_name, csv_bytes))
        verified_archive = verify_official_checksum(
            request,
            archive,
            (
                f"{hashlib.sha256(archive).hexdigest()}"
                f"  {request.archive_filename}\n"
            ).encode("ascii"),
        )
        snapshot = build_historical_market_data_snapshot(
            snapshot_id="equal-aggtrade-times",
            verified_archive=verified_archive,
            retrieved_at="2026-07-27T00:00:00Z",
            ingested_at="2026-07-27T00:00:00Z", recorded_at="2026-07-27T00:00:01Z",
        )
        self.assertEqual(
            historical_market_data_snapshot_reasons(
                snapshot,
                trusted_snapshot_attestation_hashes={
                    historical_market_data_snapshot_attestation_hash(snapshot)
                },
            ),
            (),
        )

    def test_artifact_requires_complete_source_interval_funding_month(self):
        request = HistoricalArchiveRequest.create(
            market="USD_M", data_family="FUNDING_RATE", symbol="ETHUSDT",
            interval_or_null=None, period_kind="MONTHLY", period="2024-01",
        )
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(31 * 3):
            milliseconds = int((start + timedelta(hours=8 * index)).timestamp() * 1000)
            rows.append(f"{milliseconds},8,0.0001")
        for incomplete_rows in (rows[1:], rows[:10] + rows[11:], rows[:-1]):
            with self.subTest(length=len(incomplete_rows)):
                csv_bytes = ("\n".join(incomplete_rows) + "\n").encode("ascii")
                archive = zip_bytes((request.expected_csv_name, csv_bytes))
                verified_archive = verify_official_checksum(
                    request,
                    archive,
                    (
                        f"{hashlib.sha256(archive).hexdigest()}"
                        f"  {request.archive_filename}\n"
                    ).encode("ascii"),
                )
                with self.assertRaises(MarketDataError) as raised:
                    build_historical_market_data_snapshot(
                        snapshot_id="funding-202401",
                        verified_archive=verified_archive,
                        retrieved_at="2026-07-27T00:00:00Z",
                        ingested_at="2026-07-27T00:00:00Z", recorded_at="2026-07-27T00:00:01Z",
                    )
                self.assertEqual(raised.exception.reason_code, "MARKET_DATA_QUALITY_BLOCKING")

    def test_monthly_kline_coverage_handles_leap_month_and_spot_microseconds(self):
        cases = (
            ("2024-02", 29, "ms"),
            ("2025-01", 31, "us"),
        )
        for period, day_count, timestamp_unit in cases:
            with self.subTest(period=period):
                request = HistoricalArchiveRequest.create(
                    market="SPOT",
                    data_family="KLINES",
                    symbol="ETHUSDT",
                    interval_or_null="4h",
                    period_kind="MONTHLY",
                    period=period,
                )
                start = datetime.strptime(period, "%Y-%m").replace(
                    tzinfo=timezone.utc
                )
                rows = []
                for index in range(day_count * 6):
                    opened = start + timedelta(hours=4 * index)
                    if timestamp_unit == "us":
                        open_stamp = int(opened.timestamp() * 1_000_000)
                        close_stamp = open_stamp + 4 * 60 * 60 * 1_000_000 - 1
                    else:
                        open_stamp = int(opened.timestamp() * 1_000)
                        close_stamp = open_stamp + 4 * 60 * 60 * 1_000 - 1
                    rows.append(
                        f"{open_stamp},100,101,99,100.5,1,{close_stamp},"
                        "100.5,1,0.5,50.25,0"
                    )
                csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
                archive = zip_bytes((request.expected_csv_name, csv_bytes))
                verified_archive = verify_official_checksum(
                    request,
                    archive,
                    (
                        f"{hashlib.sha256(archive).hexdigest()}"
                        f"  {request.archive_filename}\n"
                    ).encode("ascii"),
                )
                snapshot = build_historical_market_data_snapshot(
                    snapshot_id=f"monthly-{period.replace('-', '')}",
                    verified_archive=verified_archive,
                    retrieved_at="2026-07-28T00:00:00Z",
                    ingested_at="2026-07-28T00:00:00Z",
                    recorded_at="2026-07-28T00:00:01Z",
                )
                self.assertEqual(
                    snapshot["quality_report"]["row_count"],
                    day_count * 6,
                )
                self.assertTrue(
                    snapshot["quality_report"]["expected_period_coverage"]
                )
                self.assertEqual(
                    snapshot["quality_report"]["missing_interval_count"],
                    0,
                )

    def test_monthly_mark_kline_accepts_exact_official_underscore_header(self):
        request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="MARK_PRICE_KLINES",
            symbol="ETHUSDT",
            interval_or_null="4h",
            period_kind="MONTHLY",
            period="2023-01",
        )
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        header = (
            "open_time,open,high,low,close,volume,close_time,quote_volume,"
            "count,taker_buy_volume,taker_buy_quote_volume,ignore"
        )
        rows = [header]
        for index in range(31 * 6):
            opened = int(
                (start + timedelta(hours=4 * index)).timestamp() * 1_000
            )
            rows.append(
                f"{opened},100,101,99,100.5,0,{opened + 14_399_999},"
                "0,14400,0,0,0"
            )
        csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
        archive = zip_bytes((request.expected_csv_name, csv_bytes))
        verified_archive = verify_official_checksum(
            request,
            archive,
            (
                f"{hashlib.sha256(archive).hexdigest()}"
                f"  {request.archive_filename}\n"
            ).encode("ascii"),
        )
        snapshot = build_historical_market_data_snapshot(
            snapshot_id="monthly-mark-official-header",
            verified_archive=verified_archive,
            retrieved_at="2026-07-28T00:00:00Z",
            ingested_at="2026-07-28T00:00:00Z",
            recorded_at="2026-07-28T00:00:01Z",
        )

        self.assertEqual(snapshot["parser_version"], "BINANCE_CSV_V2")
        self.assertEqual(snapshot["quality_report"]["row_count"], 186)
        self.assertTrue(snapshot["quality_report"]["expected_period_coverage"])

    def test_funding_coverage_accepts_subsecond_official_schedule_jitter(self):
        request = HistoricalArchiveRequest.create(
            market="USD_M",
            data_family="FUNDING_RATE",
            symbol="ETHUSDT",
            interval_or_null=None,
            period_kind="MONTHLY",
            period="2023-01",
        )
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        offsets = (0, 8, 0, 7)
        rows = ["calc_time,funding_interval_hours,last_funding_rate"]
        for index in range(31 * 3):
            scheduled = start + timedelta(hours=8 * index)
            milliseconds = (
                int(scheduled.timestamp() * 1_000)
                + offsets[index % len(offsets)]
            )
            rows.append(f"{milliseconds},8,0.0001")
        csv_bytes = ("\n".join(rows) + "\n").encode("ascii")
        archive = zip_bytes((request.expected_csv_name, csv_bytes))
        verified_archive = verify_official_checksum(
            request,
            archive,
            (
                f"{hashlib.sha256(archive).hexdigest()}"
                f"  {request.archive_filename}\n"
            ).encode("ascii"),
        )
        snapshot = build_historical_market_data_snapshot(
            snapshot_id="monthly-funding-official-jitter",
            verified_archive=verified_archive,
            retrieved_at="2026-07-28T00:00:00Z",
            ingested_at="2026-07-28T00:00:00Z",
            recorded_at="2026-07-28T00:00:01Z",
        )

        self.assertEqual(snapshot["quality_report"]["missing_interval_count"], 0)
        self.assertEqual(
            snapshot["quality_report"]["warning_findings"],
            ["FUNDING_CALC_TIME_JITTER_WITHIN_1S"],
        )
        self.assertEqual(snapshot["quality_eligibility"], "FORMAL_COMPLETE")

    def test_v1_snapshot_remains_verifiable_after_v2_parser_release(self):
        snapshot = self.build()
        snapshot["parser_version"] = "BINANCE_CSV_V1"
        snapshot["snapshot_hash"] = historical_market_data_snapshot_hash(
            snapshot
        )
        attestation = historical_market_data_snapshot_attestation_hash(snapshot)

        self.assertEqual(
            historical_market_data_snapshot_reasons(
                snapshot,
                trusted_snapshot_attestation_hashes={attestation},
            ),
            (),
        )

    def test_snapshot_replay_rejects_coordinated_archive_identity_mutation(self):
        snapshot = self.build()
        mutated = json.loads(json.dumps(snapshot))
        mutated["source_receipt"]["archive_sha256"] = "c" * 64
        mutated["source_receipt"]["receipt_hash"] = historical_market_data_snapshot_hash({
            "snapshot_hash": "discarded", **mutated["source_receipt"]
        })
        # The receipt has its own self-hash, then the whole snapshot is rehashed.
        mutated["source_receipt"]["receipt_hash"] = hashlib.sha256(json.dumps(
            {key: value for key, value in mutated["source_receipt"].items() if key != "receipt_hash"},
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        mutated["snapshot_hash"] = historical_market_data_snapshot_hash(mutated)
        self.assertIn("ARCHIVE_FACT_ID_MISMATCH", historical_market_data_snapshot_reasons(mutated))

    def test_artifact_hash_and_schema_reject_mutation_and_unknown_business_field(self):
        from jsonschema import Draft202012Validator

        snapshot = self.build()
        mutated = json.loads(json.dumps(snapshot))
        mutated["facts"][0]["close"] = "999"
        self.assertIn("SNAPSHOT_HASH_MISMATCH", historical_market_data_snapshot_reasons(mutated))
        schema = json.loads((
            __import__("pathlib").Path(__file__).parents[1] / "config" /
            "historical-market-data-snapshot-v1.schema.json"
        ).read_text())
        validator = Draft202012Validator(schema)
        self.assertFalse(list(validator.iter_errors(snapshot)))
        unknown = json.loads(json.dumps(snapshot))
        unknown["facts"][0]["unapproved_business_field"] = "no"
        self.assertTrue(list(validator.iter_errors(unknown)))
        funding = json.loads(json.dumps(snapshot))
        funding["facts"][0].update({"fact_type": "FUNDING_RATE", "data_family": "FUNDING_RATE", "market": "USD_M", "funding_interval_hours": 8, "funding_rate": "0.1"})
        self.assertTrue(list(validator.iter_errors(funding)))
        invalid_time = json.loads(json.dumps(snapshot))
        invalid_time["ingested_at"] = "2026-07-27 00:00:00Z"
        self.assertTrue(list(validator.iter_errors(invalid_time)))
        with self.assertRaises(MarketDataError) as raised:
            self.build(snapshot_id=" bad snapshot id ")
        self.assertEqual(raised.exception.reason_code, "MARKET_DATA_QUALITY_BLOCKING")

    def test_historical_schema_rejects_invalid_calendar_time_and_cross_family_fields(self):
        from jsonschema import Draft202012Validator

        snapshot = self.build()
        schema = json.loads((
            __import__("pathlib").Path(__file__).parents[1] / "config" /
            "historical-market-data-snapshot-v1.schema.json"
        ).read_text())
        validator = Draft202012Validator(schema)
        invalid_time = json.loads(json.dumps(snapshot))
        invalid_time["ingested_at"] = "2026-99-99T99:99:99Z"
        self.assertTrue(list(validator.iter_errors(invalid_time)))
        cross_family = json.loads(json.dumps(snapshot))
        cross_family["facts"][0]["price"] = "1"
        self.assertTrue(list(validator.iter_errors(cross_family)))

    def test_runtime_reasons_reject_rehashed_schema_contract_violations(self):
        snapshot = self.build()
        invalid_algorithm = json.loads(json.dumps(snapshot))
        invalid_algorithm["hash_algorithm"] = "BLAKE3"
        invalid_algorithm["snapshot_hash"] = historical_market_data_snapshot_hash(invalid_algorithm)
        self.assertIn("MARKET_DATA_SCHEMA_INVALID", historical_market_data_snapshot_reasons(invalid_algorithm))
        invalid_canonicalization = json.loads(json.dumps(snapshot))
        invalid_canonicalization["canonicalization"] = "OTHER"
        invalid_canonicalization["snapshot_hash"] = historical_market_data_snapshot_hash(invalid_canonicalization)
        self.assertIn("MARKET_DATA_SCHEMA_INVALID", historical_market_data_snapshot_reasons(invalid_canonicalization))


class FeeScheduleContractTests(unittest.TestCase):
    def schedule(self, *, environment="RESEARCH", second_start="2024-02-01T00:00:00Z"):
        snapshot = {
            "$schema": "./fee-schedule-snapshot-v1.schema.json",
            "schema_version": "1.0.0",
            "fee_schedule_id": "binance-usdm-standard",
            "content_hash": "0" * 64,
            "hash_algorithm": "SHA-256",
            "canonicalization": "RFC8785_JCS",
            "usage_environment": environment,
            "schedules": [
                {
                    "fee_id": "maker-jan", "venue": "BINANCE",
                    "product": "USD_M_PERPETUAL", "account_tier": "VIP_0",
                    "symbol": "BTCUSDT",
                    "effective_from": "2024-01-01T00:00:00Z",
                    "effective_to_or_null": second_start,
                    "maker_rate": "0.0002", "taker_rate": "0.0005",
                    "source_reference": "manual:fee-export:jan",
                    "recorded_at": "2024-01-02T00:00:00Z",
                    "lifecycle": "APPROVED",
                    "approval": {
                        "approved_by": "risk",
                        "approved_at": "2023-12-31T00:00:00Z",
                        "approval_reference": "research:jan",
                    },
                },
                {
                    "fee_id": "maker-feb", "venue": "BINANCE",
                    "product": "USD_M_PERPETUAL", "account_tier": "VIP_0",
                    "symbol": "BTCUSDT",
                    "effective_from": second_start,
                    "effective_to_or_null": None,
                    "maker_rate": "0.0001", "taker_rate": "0.0004",
                    "source_reference": "manual:fee-export:feb",
                    "recorded_at": "2024-02-02T00:00:00Z",
                    "lifecycle": "APPROVED",
                    "approval": {
                        "approved_by": "risk",
                        "approved_at": "2024-01-31T00:00:00Z",
                        "approval_reference": "research:feb",
                    },
                },
            ],
        }
        snapshot["content_hash"] = fee_schedule_snapshot_hash(snapshot)
        return snapshot

    def test_fee_schedule_is_independent_hashed_contract_with_approval_gates(self):
        schedule = self.schedule()
        self.assertEqual(fee_schedule_snapshot_reasons(schedule), ())
        self.assertEqual(schedule["content_hash"], fee_schedule_snapshot_hash(schedule))
        missing_lifecycle_approval = self.schedule()
        missing_lifecycle_approval["schedules"][0]["approval"] = {"approved_by": "risk"}
        missing_lifecycle_approval["content_hash"] = fee_schedule_snapshot_hash(missing_lifecycle_approval)
        self.assertIn("FEE_SCHEDULE_APPROVAL_INVALID", fee_schedule_snapshot_reasons(missing_lifecycle_approval))
        production = self.schedule(environment="PRODUCTION")
        self.assertIn("FEE_SCHEDULE_PRODUCTION_UNSUPPORTED", fee_schedule_snapshot_reasons(production))
        production["production_approval"] = {
            "approved_by": "risk",
            "approved_at": "2024-01-01T00:00:00Z",
            "approval_reference": "caller:self-filled",
        }
        production["content_hash"] = fee_schedule_snapshot_hash(production)
        self.assertIn("FEE_SCHEDULE_PRODUCTION_UNSUPPORTED", fee_schedule_snapshot_reasons(production))

    def test_fee_schedule_rejects_overlaps_invalid_rates_and_unknown_schema_fields(self):
        from jsonschema import Draft202012Validator

        overlap = self.schedule()
        overlap["schedules"][1]["effective_from"] = "2024-01-15T00:00:00Z"
        overlap["content_hash"] = fee_schedule_snapshot_hash(overlap)
        self.assertIn("FEE_SCHEDULE_EFFECTIVE_INTERVAL_OVERLAP", fee_schedule_snapshot_reasons(overlap))
        invalid_rate = self.schedule()
        invalid_rate["schedules"][0]["maker_rate"] = "NaN"
        self.assertIn("FEE_SCHEDULE_INVALID_DECIMAL", fee_schedule_snapshot_reasons(invalid_rate))
        schema = json.loads((
            __import__("pathlib").Path(__file__).parents[1] / "config" /
            "fee-schedule-snapshot-v1.schema.json"
        ).read_text())
        validator = Draft202012Validator(schema)
        self.assertFalse(list(validator.iter_errors(self.schedule())))
        self.assertFalse(list(validator.iter_errors(self.schedule(environment="PRODUCTION"))))
        unknown = self.schedule()
        unknown["schedules"][0]["rebate"] = "0"
        self.assertTrue(list(validator.iter_errors(unknown)))

        non_schema_consumer = self.schedule(environment="NOT_PRODUCTION")
        non_schema_consumer["schedules"][0].pop("fee_id")
        non_schema_consumer["schedules"][0]["product"] = "UNKNOWN"
        non_schema_consumer["schedules"][0]["symbol"] = "X"
        non_schema_consumer["content_hash"] = fee_schedule_snapshot_hash(non_schema_consumer)
        self.assertIn("FEE_SCHEDULE_INVALID", fee_schedule_snapshot_reasons(non_schema_consumer))
        draft = self.schedule()
        draft["schedules"][0]["lifecycle"] = "DRAFT"
        draft["schedules"][0]["approval"] = None
        draft["content_hash"] = fee_schedule_snapshot_hash(draft)
        self.assertEqual(fee_schedule_snapshot_reasons(draft), ())
        self.assertFalse(list(validator.iter_errors(draft)))

        whitespace_id = self.schedule()
        whitespace_id["fee_schedule_id"] = " invalid"
        whitespace_id["content_hash"] = fee_schedule_snapshot_hash(whitespace_id)
        self.assertIn("FEE_SCHEDULE_INVALID", fee_schedule_snapshot_reasons(whitespace_id))
        unknown_approval = self.schedule()
        unknown_approval["schedules"][0]["approval"]["unapproved"] = "x"
        unknown_approval["content_hash"] = fee_schedule_snapshot_hash(unknown_approval)
        self.assertIn("FEE_SCHEDULE_INVALID", fee_schedule_snapshot_reasons(unknown_approval))


class PackagedMarketSchemaTests(unittest.TestCase):
    def test_packaged_schemas_are_byte_identical_to_governance_schemas(self):
        from importlib import resources

        root = Path(__file__).parents[1]
        for filename in (
            "historical-market-data-snapshot-v1.schema.json",
            "fee-schedule-snapshot-v1.schema.json",
        ):
            with self.subTest(filename=filename):
                packaged = resources.files("crypto_quant").joinpath("schemas", filename).read_bytes()
                governed = (root / "config" / filename).read_bytes()
                self.assertEqual(hashlib.sha256(packaged).hexdigest(), hashlib.sha256(governed).hexdigest())
                self.assertEqual(packaged, governed)

    def test_wheel_reasons_work_outside_repository(self):
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            wheel_dir = temporary_path / "wheel"
            target = temporary_path / "site"
            outside = temporary_path / "outside"
            wheel_dir.mkdir()
            target.mkdir()
            outside.mkdir()
            pip_environment = dict(
                os.environ,
                PIP_NO_INDEX="1",
                PIP_DISABLE_PIP_VERSION_CHECK="1",
            )
            subprocess.run(
                [
                    sys.executable, "-m", "pip", "wheel",
                    "--no-deps", "--no-build-isolation",
                    "--wheel-dir", str(wheel_dir), str(root),
                ],
                env=pip_environment,
                check=True, capture_output=True, text=True,
            )
            wheel = next(wheel_dir.glob("*.whl"))
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(target), str(wheel)],
                env=pip_environment,
                check=True, capture_output=True, text=True,
            )
            smoke = """
from datetime import datetime, timedelta, timezone
import hashlib
import io
import zipfile
from crypto_quant.market_data import (HistoricalArchiveRequest, build_historical_market_data_snapshot, fee_schedule_snapshot_reasons, historical_market_data_snapshot_attestation_hash, historical_market_data_snapshot_reasons, verify_official_checksum)
request = HistoricalArchiveRequest.create(market='USD_M', data_family='FUNDING_RATE', symbol='ETHUSDT', interval_or_null=None, period_kind='MONTHLY', period='2024-01')
start = datetime(2024, 1, 1, tzinfo=timezone.utc)
rows = ('\\n'.join(f'{int((start + timedelta(hours=8 * index)).timestamp() * 1000)},8,0.0001' for index in range(93)) + '\\n').encode()
buffer = io.BytesIO()
with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr(request.expected_csv_name, rows)
archive_bytes = buffer.getvalue()
checksum = f"{hashlib.sha256(archive_bytes).hexdigest()}  {request.archive_filename}\\n".encode()
verified = verify_official_checksum(request, archive_bytes, checksum)
snapshot = build_historical_market_data_snapshot(snapshot_id='wheel-funding-202401', verified_archive=verified, retrieved_at='2026-07-27T00:00:00Z', ingested_at='2026-07-27T00:00:00Z', recorded_at='2026-07-27T00:00:01Z')
assert historical_market_data_snapshot_reasons(snapshot, trusted_snapshot_attestation_hashes={historical_market_data_snapshot_attestation_hash(snapshot)}) == ()
assert historical_market_data_snapshot_reasons({})
fee = {'$schema': './fee-schedule-snapshot-v1.schema.json', 'schema_version': '1.0.0', 'fee_schedule_id': 'wheel-fee', 'content_hash': '0' * 64, 'hash_algorithm': 'SHA-256', 'canonicalization': 'RFC8785_JCS', 'usage_environment': 'RESEARCH', 'schedules': [{'fee_id': 'fee-one', 'venue': 'BINANCE', 'product': 'USD_M_PERPETUAL', 'account_tier': 'VIP_0', 'symbol': 'ETHUSDT', 'effective_from': '2024-01-01T00:00:00Z', 'effective_to_or_null': None, 'maker_rate': '0.0002', 'taker_rate': '0.0005', 'source_reference': 'manual:wheel', 'recorded_at': '2024-01-02T00:00:00Z', 'lifecycle': 'APPROVED', 'approval': {'approved_by': 'risk', 'approved_at': '2023-12-31T00:00:00Z', 'approval_reference': 'research:wheel'}}]}
from crypto_quant.market_data import fee_schedule_snapshot_hash
fee['content_hash'] = fee_schedule_snapshot_hash(fee)
assert fee_schedule_snapshot_reasons(fee) == ()
assert fee_schedule_snapshot_reasons({})
"""
            environment = dict(os.environ, PYTHONPATH=str(target))
            subprocess.run(
                [sys.executable, "-c", smoke], cwd=outside, env=environment,
                check=True, capture_output=True, text=True,
            )

    def test_wheel_smoke_invokes_pip_in_enforced_offline_mode(self):
        calls = []
        mock_wheel_names = []

        def record_run(command, **kwargs):
            calls.append((command, kwargs))
            if command[1:4] == ["-m", "pip", "wheel"]:
                wheel_dir = Path(command[command.index("--wheel-dir") + 1])
                wheel_name = "crypto_quant_core-0.16.0-py3-none-any.whl"
                mock_wheel_names.append(wheel_name)
                (wheel_dir / wheel_name).touch()
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch("tests.test_market_data.subprocess.run", side_effect=record_run):
            self.test_wheel_reasons_work_outside_repository()

        pip_calls = [
            (command, kwargs)
            for command, kwargs in calls
            if command[1:3] == ["-m", "pip"]
        ]
        self.assertEqual(len(pip_calls), 2)
        self.assertEqual(
            mock_wheel_names,
            ["crypto_quant_core-0.16.0-py3-none-any.whl"],
        )
        wheel_command, wheel_kwargs = pip_calls[0]
        self.assertIn("--no-build-isolation", wheel_command)
        for _, kwargs in pip_calls:
            self.assertEqual(kwargs["env"]["PIP_NO_INDEX"], "1")
            self.assertEqual(kwargs["env"]["PIP_DISABLE_PIP_VERSION_CHECK"], "1")
