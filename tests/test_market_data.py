import hashlib
import io
import struct
import unittest
import zipfile

from crypto_quant.market_data import (
    HistoricalArchiveRequest,
    MarketDataError,
    extract_expected_csv,
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
