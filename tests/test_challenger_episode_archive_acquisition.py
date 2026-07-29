import contextlib
import copy
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_episode_archive_acquisition import (
    ChallengerEpisodeArchiveAcquisitionError,
    acquire_challenger_episode_archives,
    challenger_episode_archive_receipt_hash,
    challenger_episode_archive_receipt_reasons,
    load_challenger_episode_daily_archives,
)
from crypto_quant.challenger_episode_archive_acquisition_cli import (
    main as acquisition_main,
)
from crypto_quant.market_data import HistoricalArchiveRequest, HttpResponse
from tests.test_challenger_episode_economic_evaluator import (
    PLAN_FILE_SHA256,
    PLAN_PATH,
    completion_receipt,
    daily_archive,
)


ROOT = Path(__file__).resolve().parents[1]


class FixtureTransport:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        response = self.responses.get(url)
        if response is None:
            raise AssertionError(f"unexpected request: {url}")
        return response


def response(url, status, body=b""):
    return HttpResponse(
        status=status,
        final_url=url,
        headers={},
        body=body,
    )


def period_responses(period, archive, checksum):
    request = HistoricalArchiveRequest.create(
        market="SPOT",
        data_family="KLINES",
        symbol="ETHUSDT",
        interval_or_null="1m",
        period_kind="DAILY",
        period=period,
    )
    return {
        request.archive_url: response(
            request.archive_url, 200, archive
        ),
        request.checksum_url: response(
            request.checksum_url, 200, checksum
        ),
    }


class ChallengerEpisodeArchiveAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.receipt, cls.receipt_sha = completion_receipt()
        cls.archive, cls.checksum = daily_archive(
            "2026-07-29",
            selected_prices={
                "2026-07-29T00:03:00.000Z": ("2000", "1990"),
                "2026-07-29T08:03:00.000Z": ("2100", "2090"),
            },
        )

    def acquire(self, output_root, transport, **overrides):
        arguments = {
            "plan": self.plan,
            "plan_file_sha256": PLAN_FILE_SHA256,
            "completion_receipt": self.receipt,
            "completion_receipt_file_sha256": self.receipt_sha,
            "output_root": output_root,
            "observed_at": "2026-07-30T00:05:00.000Z",
            "transport": transport,
        }
        arguments.update(overrides)
        return acquire_challenger_episode_archives(**arguments)

    def test_schema_mirrors_are_identical_and_valid(self):
        config = (
            ROOT
            / "config"
            / "challenger-episode-archive-receipt-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-episode-archive-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_early_gate_has_zero_requests_and_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            transport = FixtureTransport()
            result = self.acquire(
                root,
                transport,
                observed_at="2026-07-30T00:04:59.000Z",
            )
            self.assertEqual(result["status"], "ARCHIVE_ACQUISITION_PENDING")
            self.assertEqual(
                result["periods"][0]["status"],
                "ARCHIVE_ACQUISITION_NOT_YET_ELIGIBLE",
            )
            self.assertEqual(result["network_request_count"], 0)
            self.assertEqual(transport.calls, [])
            self.assertFalse(root.exists())

    def test_invalid_plan_or_completion_receipt_has_zero_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            cases = (
                {"plan_file_sha256": "0" * 64},
                {"completion_receipt_file_sha256": "not-a-hash"},
            )
            for override in cases:
                transport = FixtureTransport()
                with self.subTest(override=override):
                    with self.assertRaises(
                        ChallengerEpisodeArchiveAcquisitionError
                    ):
                        self.acquire(root, transport, **override)
                    self.assertEqual(transport.calls, [])
                    self.assertFalse(root.exists())

    def test_zip_and_checksum_404_are_pending_without_success_files(self):
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2026-07-29",
        )
        cases = (
            (
                {
                    request.archive_url: response(
                        request.archive_url, 404
                    )
                },
                1,
                "ARCHIVE_ACQUISITION_PENDING_ZIP_404",
            ),
            (
                {
                    request.archive_url: response(
                        request.archive_url, 200, self.archive
                    ),
                    request.checksum_url: response(
                        request.checksum_url, 404
                    ),
                },
                2,
                "ARCHIVE_ACQUISITION_PENDING_CHECKSUM_404",
            ),
        )
        for responses, count, status_value in cases:
            with self.subTest(status=status_value):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory) / "archives"
                    transport = FixtureTransport(responses)
                    result = self.acquire(root, transport)
                    self.assertEqual(
                        result["periods"][0]["status"], status_value
                    )
                    self.assertEqual(
                        result["network_request_count"], count
                    )
                    self.assertFalse(root.exists())

    def test_success_is_exact_loadable_and_retry_uses_zero_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            transport = FixtureTransport(
                period_responses(
                    "2026-07-29", self.archive, self.checksum
                )
            )
            result = self.acquire(root, transport)
            self.assertEqual(
                result["status"], "ARCHIVE_ACQUISITION_COMPLETE"
            )
            self.assertEqual(result["network_request_count"], 2)
            period_root = root / "2026-07-29"
            files = tuple(period_root.iterdir())
            self.assertEqual(len(files), 3)
            self.assertEqual(
                stat.S_IMODE(root.stat().st_mode), 0o700
            )
            self.assertEqual(
                stat.S_IMODE(period_root.stat().st_mode), 0o700
            )
            for path in files:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            receipt = json.loads(
                (period_root / "receipt.json").read_text()
            )
            self.assertEqual(
                receipt["receipt_hash"],
                challenger_episode_archive_receipt_hash(receipt),
            )
            self.assertFalse(
                challenger_episode_archive_receipt_reasons(
                    receipt,
                    plan=self.plan,
                    plan_file_sha256=PLAN_FILE_SHA256,
                    completion_receipt=self.receipt,
                    completion_receipt_file_sha256=self.receipt_sha,
                    archive_bytes=self.archive,
                    checksum_bytes=self.checksum,
                )
            )
            loaded = load_challenger_episode_daily_archives(
                plan=self.plan,
                plan_file_sha256=PLAN_FILE_SHA256,
                completion_receipt=self.receipt,
                completion_receipt_file_sha256=self.receipt_sha,
                output_root=root,
            )
            self.assertEqual(
                loaded["2026-07-29"][:2],
                (self.archive, self.checksum),
            )
            retry = self.acquire(root, FixtureTransport())
            self.assertEqual(
                retry["status"], "ARCHIVE_ACQUISITION_COMPLETE"
            )
            self.assertEqual(retry["network_request_count"], 0)

    def test_bad_checksum_coverage_and_redirect_fail_closed(self):
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2026-07-29",
        )
        short_archive, short_checksum = daily_archive(
            "2026-07-29", row_count=1439
        )
        cases = (
            period_responses(
                "2026-07-29",
                self.archive,
                self.checksum[:-1] + b"x",
            ),
            period_responses(
                "2026-07-29", short_archive, short_checksum
            ),
            {
                request.archive_url: response(
                    "https://example.com/file.zip",
                    200,
                    self.archive,
                )
            },
        )
        for responses in cases:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "archives"
                with self.assertRaises(
                    ChallengerEpisodeArchiveAcquisitionError
                ):
                    self.acquire(root, FixtureTransport(responses))
                self.assertFalse((root / "2026-07-29" / "receipt.json").exists())

    def test_cross_day_partial_then_resume_fetches_only_missing_day(self):
        receipt, receipt_sha = completion_receipt(vertical=True)
        first_archive, first_checksum = daily_archive("2026-07-29")
        second_archive, second_checksum = daily_archive("2026-07-30")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            first_transport = FixtureTransport(
                period_responses(
                    "2026-07-29", first_archive, first_checksum
                )
            )
            first = self.acquire(
                root,
                first_transport,
                completion_receipt=receipt,
                completion_receipt_file_sha256=receipt_sha,
            )
            self.assertEqual(first["status"], "ARCHIVE_ACQUISITION_PARTIAL")
            self.assertEqual(first["network_request_count"], 2)
            self.assertEqual(first["verified_period_count"], 1)
            second_transport = FixtureTransport(
                period_responses(
                    "2026-07-30", second_archive, second_checksum
                )
            )
            second = self.acquire(
                root,
                second_transport,
                completion_receipt=receipt,
                completion_receipt_file_sha256=receipt_sha,
                observed_at="2026-07-31T00:05:00.000Z",
            )
            self.assertEqual(
                second["status"], "ARCHIVE_ACQUISITION_COMPLETE"
            )
            self.assertEqual(second["network_request_count"], 2)
            self.assertEqual(second["verified_period_count"], 2)

    def test_symlink_and_coordinated_receipt_mutation_fail_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            period_root = root / "2026-07-29"
            period_root.mkdir(parents=True)
            target = Path(directory) / "target.zip"
            target.write_bytes(b"outside")
            target.chmod(0o600)
            request = HistoricalArchiveRequest.create(
                market="SPOT",
                data_family="KLINES",
                symbol="ETHUSDT",
                interval_or_null="1m",
                period_kind="DAILY",
                period="2026-07-29",
            )
            os.symlink(target, period_root / request.archive_filename)
            transport = FixtureTransport()
            with self.assertRaises(
                ChallengerEpisodeArchiveAcquisitionError
            ):
                self.acquire(root, transport)
            self.assertEqual(transport.calls, [])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "archives"
            self.acquire(
                root,
                FixtureTransport(
                    period_responses(
                        "2026-07-29", self.archive, self.checksum
                    )
                ),
            )
            receipt_path = root / "2026-07-29" / "receipt.json"
            receipt = json.loads(receipt_path.read_text())
            mutated = copy.deepcopy(receipt)
            mutated["retrieved_at"] = "2026-07-30T00:06:00.000Z"
            mutated["receipt_hash"] = challenger_episode_archive_receipt_hash(
                mutated
            )
            receipt_path.write_text(canonical_json(mutated))
            receipt_path.chmod(0o600)
            transport = FixtureTransport()
            with self.assertRaises(
                ChallengerEpisodeArchiveAcquisitionError
            ):
                self.acquire(root, transport)
            self.assertEqual(transport.calls, [])

    def test_cli_has_no_url_or_period_override_and_uses_trusted_loader(self):
        parser_output = io.StringIO()
        with contextlib.redirect_stdout(parser_output):
            code = acquisition_main(["--help"])
        self.assertEqual(code, 0)
        help_text = parser_output.getvalue()
        self.assertNotIn("--url", help_text)
        self.assertNotIn("--period", help_text)
        self.assertNotIn("--price", help_text)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            output = base / "owner" / "archives"
            output.parent.mkdir()
            receipt_path = base / "completion.json"
            receipt_path.write_bytes(canonical_json(self.receipt).encode())
            receipt_path.chmod(0o600)
            placeholders = []
            for name in ("install.json", "contract.json", "agent.plist"):
                path = base / name
                path.write_text("{}")
                path.chmod(0o600)
                placeholders.append(path)
            transport = FixtureTransport(
                period_responses(
                    "2026-07-29", self.archive, self.checksum
                )
            )
            loaded = []

            def loader(**kwargs):
                loaded.append(kwargs)
                return self.receipt

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = acquisition_main(
                    [
                        "--economic-plan-path",
                        str(PLAN_PATH),
                        "--completion-receipt-path",
                        str(receipt_path),
                        "--install-receipt-path",
                        str(placeholders[0]),
                        "--contract-path",
                        str(placeholders[1]),
                        "--plist-path",
                        str(placeholders[2]),
                        "--archive-output-root",
                        str(output),
                    ],
                    clock=lambda: "2026-07-30T00:05:00.000Z",
                    transport=transport,
                    receipt_loader=loader,
                    allowed_output_base=output.parent,
                )
            self.assertEqual(code, 0)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(
                json.loads(stdout.getvalue())["status"],
                "ARCHIVE_ACQUISITION_COMPLETE",
            )


if __name__ == "__main__":
    unittest.main()
