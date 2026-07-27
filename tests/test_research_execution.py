import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crypto_quant.evidence import artifact_self_hash
from crypto_quant.market_data import HistoricalArchiveRequest
from crypto_quant.research_corpus import ResearchCorpusError
from crypto_quant.research_execution import (
    ResearchExecutionError,
    build_execution_source,
    execution_source_reasons,
    load_execution_source,
    publish_execution_source,
)


def archive_fixture(period):
    start = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    end = (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )
    microseconds = start >= datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = [
        "open_time,open,high,low,close,volume,close_time,quote_volume,"
        "count,taker_buy_volume,taker_buy_quote_volume,ignore"
    ]
    def raw_time(value):
        delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
        seconds = delta.days * 86_400 + delta.seconds
        return (
            seconds * 1_000_000 + delta.microseconds
            if microseconds
            else seconds * 1_000 + delta.microseconds // 1_000
        )

    cursor = start
    while cursor < end:
        opened = raw_time(cursor)
        close_time = cursor + timedelta(minutes=1) - (
            timedelta(microseconds=1)
            if microseconds
            else timedelta(milliseconds=1)
        )
        closed = raw_time(close_time)
        rows.append(
            f"{opened},100,101,99,100.5,10,{closed},1000,10,5,500,0"
        )
        cursor += timedelta(minutes=1)
    request = HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="MONTHLY",
        period=period,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.expected_csv_name, "\n".join(rows) + "\n")
    archive_bytes = output.getvalue()
    checksum = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}"
        f"  {request.archive_filename}\n"
    ).encode("ascii")
    return archive_bytes, checksum


def daily_archive_fixture(day):
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    microseconds = start >= datetime(2025, 1, 1, tzinfo=timezone.utc)

    def raw_time(value):
        delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
        seconds = delta.days * 86_400 + delta.seconds
        return (
            seconds * 1_000_000 + delta.microseconds
            if microseconds
            else seconds * 1_000 + delta.microseconds // 1_000
        )

    rows = [
        "open_time,open,high,low,close,volume,close_time,quote_volume,"
        "count,taker_buy_volume,taker_buy_quote_volume,ignore"
    ]
    for minute in range(1440):
        opened_at = start + timedelta(minutes=minute)
        closed_at = opened_at + timedelta(minutes=1) - (
            timedelta(microseconds=1)
            if microseconds
            else timedelta(milliseconds=1)
        )
        rows.append(
            f"{raw_time(opened_at)},100,101,99,100.5,10,"
            f"{raw_time(closed_at)},1000,10,5,500,0"
        )
    request = HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=day,
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(request.expected_csv_name, "\n".join(rows) + "\n")
    archive_bytes = output.getvalue()
    checksum = (
        f"{hashlib.sha256(archive_bytes).hexdigest()}"
        f"  {request.archive_filename}\n"
    ).encode("ascii")
    return archive_bytes, checksum


class ResearchExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.period = "2025-02"
        cls.archive_bytes, cls.checksum_bytes = archive_fixture(cls.period)
        cls.required = (
            "2025-02-01T00:00:00.000Z",
            "2025-02-28T23:59:00.000Z",
        )
        cls.snapshot = build_execution_source(
            period=cls.period,
            archive_bytes=cls.archive_bytes,
            checksum_bytes=cls.checksum_bytes,
            required_open_times=cls.required,
            retrieved_at="2026-07-28T00:00:00.000Z",
        )

    def test_full_month_is_verified_but_only_required_rows_are_retained(self):
        self.assertEqual(self.snapshot["csv_row_count"], 28 * 24 * 60)
        self.assertEqual(
            self.snapshot["csv_row_count"],
            self.snapshot["expected_row_count"],
        )
        self.assertEqual(
            tuple(row["open_time"] for row in self.snapshot["selected_rows"]),
            self.required,
        )
        self.assertEqual(len(self.snapshot["selected_rows"]), 2)
        self.assertEqual(self.snapshot["quality_eligibility"], "FORMAL_COMPLETE")
        self.assertEqual(
            self.snapshot["formal_pit_eligibility"],
            "INELIGIBLE_ARCHIVE_REPLAY",
        )
        self.assertEqual(
            execution_source_reasons(
                self.snapshot,
                archive_bytes=self.archive_bytes,
                checksum_bytes=self.checksum_bytes,
            ),
            (),
        )

    def test_required_times_must_be_sorted_unique_aligned_and_in_month(self):
        for required in (
            (self.required[1], self.required[0]),
            (self.required[0], self.required[0]),
            ("2025-02-01T00:00:01.000Z",),
            ("2025-03-01T00:00:00.000Z",),
        ):
            with self.subTest(required=required):
                with self.assertRaises(ResearchExecutionError) as raised:
                    build_execution_source(
                        period=self.period,
                        archive_bytes=self.archive_bytes,
                        checksum_bytes=self.checksum_bytes,
                        required_open_times=required,
                        retrieved_at="2026-07-28T00:00:00.000Z",
                    )
                self.assertEqual(
                    raised.exception.reason_code,
                    "EXECUTION_SOURCE_REQUIRED_TIME_INVALID",
                )

    def test_checksum_row_and_coverage_corruption_fail_closed(self):
        with self.assertRaises(ResearchExecutionError) as checksum:
            build_execution_source(
                period=self.period,
                archive_bytes=self.archive_bytes,
                checksum_bytes=b"0" * 64 + b"  wrong.zip\n",
                required_open_times=self.required,
                retrieved_at="2026-07-28T00:00:00.000Z",
            )
        self.assertEqual(
            checksum.exception.reason_code,
            "EXECUTION_SOURCE_ARCHIVE_INVALID",
        )
        bad_archive, bad_checksum = archive_fixture(self.period)
        with zipfile.ZipFile(io.BytesIO(bad_archive)) as source:
            text = source.read(source.namelist()[0]).decode("ascii")
        lines = text.splitlines()
        del lines[1]
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="MONTHLY",
            period=self.period,
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(request.expected_csv_name, "\n".join(lines) + "\n")
        missing_archive = output.getvalue()
        missing_checksum = (
            f"{hashlib.sha256(missing_archive).hexdigest()}"
            f"  {request.archive_filename}\n"
        ).encode("ascii")
        with self.assertRaises(ResearchExecutionError) as missing:
            build_execution_source(
                period=self.period,
                archive_bytes=missing_archive,
                checksum_bytes=missing_checksum,
                required_open_times=self.required,
                retrieved_at="2026-07-28T00:00:00.000Z",
            )
        self.assertEqual(
            missing.exception.reason_code,
            "EXECUTION_SOURCE_REQUIRED_ROWS_MISSING",
        )

    def test_rehashed_semantic_mutation_is_detected(self):
        candidate = json.loads(json.dumps(self.snapshot))
        candidate["selected_rows"][0]["high"] = "102"
        candidate["source_hash"] = artifact_self_hash(candidate, "source_hash")
        self.assertIn(
            "EXECUTION_SOURCE_SEMANTIC_MISMATCH",
            execution_source_reasons(
                candidate,
                archive_bytes=self.archive_bytes,
                checksum_bytes=self.checksum_bytes,
            ),
        )

    def test_exact_official_daily_archive_repairs_monthly_gap(self):
        with zipfile.ZipFile(io.BytesIO(self.archive_bytes)) as source:
            name = source.namelist()[0]
            lines = source.read(name).decode("ascii").splitlines()
        missing_time = "2025-02-01T12:40:00.000Z"
        del lines[1 + 12 * 60 + 40]
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="MONTHLY",
            period=self.period,
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(request.expected_csv_name, "\n".join(lines) + "\n")
        monthly = output.getvalue()
        monthly_checksum = (
            f"{hashlib.sha256(monthly).hexdigest()}"
            f"  {request.archive_filename}\n"
        ).encode("ascii")
        daily, daily_checksum = daily_archive_fixture("2025-02-01")
        repaired = build_execution_source(
            period=self.period,
            archive_bytes=monthly,
            checksum_bytes=monthly_checksum,
            required_open_times=(missing_time,),
            retrieved_at="2026-07-28T00:00:00.000Z",
            daily_repair_archives={
                "2025-02-01": (daily, daily_checksum),
            },
        )
        self.assertEqual(
            repaired["quality_eligibility"],
            "FORMAL_COMPLETE_WITH_EXPLICIT_DAILY_REPAIRS",
        )
        self.assertEqual(
            repaired["monthly_csv_row_count"],
            repaired["expected_row_count"] - 1,
        )
        self.assertEqual(repaired["daily_repairs"][0]["added_row_count"], 1)
        self.assertEqual(
            repaired["selected_rows"][0]["open_time"],
            missing_time,
        )
        self.assertEqual(
            execution_source_reasons(
                repaired,
                archive_bytes=monthly,
                checksum_bytes=monthly_checksum,
                daily_repair_archives={
                    "2025-02-01": (daily, daily_checksum),
                },
            ),
            (),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "execution"
            publish_execution_source(
                snapshot=repaired,
                archive_bytes=monthly,
                checksum_bytes=monthly_checksum,
                daily_repair_archives={
                    "2025-02-01": (daily, daily_checksum),
                },
                output_root=root,
            )
            loaded, _, _, repairs = load_execution_source(
                period=self.period,
                output_root=root,
            )
            self.assertEqual(loaded, repaired)
            self.assertEqual(repairs["2025-02-01"], (daily, daily_checksum))
            self.assertEqual(
                os.stat(root / self.period / "repairs").st_mode & 0o777,
                0o700,
            )

    def test_unrequired_source_gap_is_explicit_but_required_gap_fails(self):
        with zipfile.ZipFile(io.BytesIO(self.archive_bytes)) as source:
            name = source.namelist()[0]
            lines = source.read(name).decode("ascii").splitlines()
        gap_time = "2025-02-01T12:40:00.000Z"
        del lines[1 + 12 * 60 + 40]
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="MONTHLY",
            period=self.period,
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(request.expected_csv_name, "\n".join(lines) + "\n")
        archive_bytes = output.getvalue()
        checksum_bytes = (
            f"{hashlib.sha256(archive_bytes).hexdigest()}"
            f"  {request.archive_filename}\n"
        ).encode("ascii")
        degraded = build_execution_source(
            period=self.period,
            archive_bytes=archive_bytes,
            checksum_bytes=checksum_bytes,
            required_open_times=self.required,
            retrieved_at="2026-07-28T00:00:00.000Z",
        )
        self.assertEqual(degraded["source_gap_count"], 1)
        self.assertEqual(degraded["source_gap_open_times"], [gap_time])
        self.assertEqual(
            degraded["quality_eligibility"],
            "RESEARCH_REQUIRED_ROWS_COMPLETE_WITH_SOURCE_GAPS",
        )
        with self.assertRaises(ResearchExecutionError) as required_gap:
            build_execution_source(
                period=self.period,
                archive_bytes=archive_bytes,
                checksum_bytes=checksum_bytes,
                required_open_times=(gap_time,),
                retrieved_at="2026-07-28T00:00:00.000Z",
            )
        self.assertEqual(
            required_gap.exception.reason_code,
            "EXECUTION_SOURCE_REQUIRED_ROWS_MISSING",
        )

    def test_publish_load_permissions_idempotency_and_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "execution"
            publish_execution_source(
                snapshot=self.snapshot,
                archive_bytes=self.archive_bytes,
                checksum_bytes=self.checksum_bytes,
                output_root=root,
            )
            (
                loaded,
                archive_bytes,
                checksum_bytes,
                repair_archives,
            ) = load_execution_source(
                period=self.period,
                output_root=root,
            )
            self.assertEqual(loaded, self.snapshot)
            self.assertEqual(archive_bytes, self.archive_bytes)
            self.assertEqual(checksum_bytes, self.checksum_bytes)
            self.assertEqual(repair_archives, {})
            period_root = root / self.period
            self.assertEqual(os.stat(root).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(period_root).st_mode & 0o777, 0o700)
            for path in period_root.iterdir():
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            publish_execution_source(
                snapshot=self.snapshot,
                archive_bytes=self.archive_bytes,
                checksum_bytes=self.checksum_bytes,
                output_root=root,
            )
            archive_path = (
                period_root / self.snapshot["request"]["archive_filename"]
            )
            archive_path.write_bytes(b"tampered")
            with self.assertRaises(ResearchCorpusError) as conflict:
                publish_execution_source(
                    snapshot=self.snapshot,
                    archive_bytes=self.archive_bytes,
                    checksum_bytes=self.checksum_bytes,
                    output_root=root,
                )
            self.assertEqual(
                conflict.exception.reason_code,
                "CORPUS_PUBLISH_CONFLICT",
            )

    def test_schema_mirror_is_exact(self):
        root = Path(__file__).parents[1]
        self.assertEqual(
            (root / "config/historical-execution-source-v1.schema.json").read_bytes(),
            (
                root
                / "src/crypto_quant/schemas/"
                "historical-execution-source-v1.schema.json"
            ).read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
