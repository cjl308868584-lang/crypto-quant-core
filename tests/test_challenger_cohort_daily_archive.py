import contextlib
import copy
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_daily_archive import (
    ChallengerCohortDailyArchiveError,
    _build_receipt,
    _read_exact_plan,
    _verified_daily_source,
    acquire_challenger_cohort_daily_archives,
    challenger_cohort_daily_archive_receipt_hash,
    challenger_cohort_daily_archive_receipt_reasons,
    load_challenger_cohort_daily_archives,
)
from crypto_quant.challenger_cohort_daily_archive_cli import (
    main as acquisition_main,
)
from crypto_quant.market_data import HistoricalArchiveRequest, HttpResponse
from tests.test_challenger_cohort_episode_receipt import (
    COHORT_START,
    ONE_COHORT_EPISODE,
)
from tests.test_challenger_episode_economic_evaluator import daily_archive


ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)
EPISODE_DIRECTORY = "challenger-cohort-episode-receipts"
ARCHIVE_DIRECTORY = "challenger-cohort-daily-archives"


class FixtureTransport:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url not in self.responses:
            raise AssertionError(f"unexpected request: {url}")
        return self.responses[url]


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


def episode_receipt(
    ordinal,
    *,
    entry_scheduled,
    entry_recorded,
    exit_recorded,
    prior_ids=(),
):
    episode_id = (
        "challenger_episode_"
        + hashlib.sha256(f"episode-{ordinal}".encode()).hexdigest()
    )
    return {
        "receipt_id": (
            "challenger_cohort_episode_receipt_"
            + hashlib.sha256(f"receipt-{ordinal}".encode()).hexdigest()
        ),
        "receipt_hash": hashlib.sha256(
            f"receipt-hash-{ordinal}".encode()
        ).hexdigest(),
        "episode": {
            "ordinal": ordinal,
            "episode_id": episode_id,
            "entry_scheduled_for": entry_scheduled,
            "entry_recorded_at": entry_recorded,
            "exit_recorded_at": exit_recorded,
        },
        "prior_completed_episodes": {
            "count": len(prior_ids),
            "episode_ids": list(prior_ids),
        },
    }


def write_receipts(root, receipts):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    directory = root / EPISODE_DIRECTORY
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    for receipt in receipts:
        stamp = (
            receipt["episode"]["entry_scheduled_for"]
            .replace("-", "")
            .replace(":", "")
            .replace(".000", "")
        )
        path = directory / (
            f"{stamp}-{receipt['episode']['episode_id']}.json"
        )
        path.write_text(canonical_json(receipt), encoding="utf-8")
        path.chmod(0o600)


def fixture_loader(**kwargs):
    return json.loads(Path(kwargs["receipt_path"]).read_text())


class ChallengerCohortDailyArchiveTests(unittest.TestCase):
    def acquire(
        self,
        *,
        receipt_root,
        archive_root,
        transport,
        observed_at="2026-07-31T00:05:00.000Z",
        loader=fixture_loader,
    ):
        return acquire_challenger_cohort_daily_archives(
            cohort_plan_path=PLAN,
            episode_receipt_output_root=receipt_root,
            install_receipt_path=Path("/unused/install.json"),
            contract_path=Path("/unused/contract.json"),
            plist_path=Path("/unused/agent.plist"),
            archive_output_root=archive_root,
            observed_at=observed_at,
            transport=transport,
            receipt_loader=loader,
        )

    @staticmethod
    def first_receipt():
        return episode_receipt(
            1,
            entry_scheduled="2026-07-30T12:00:00.000Z",
            entry_recorded="2026-07-30T12:02:06.752Z",
            exit_recorded="2026-07-30T20:02:06.752Z",
        )

    def test_schema_mirrors_are_identical_and_valid(self):
        config = (
            ROOT
            / "config"
            / "challenger-cohort-daily-archive-receipt-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-daily-archive-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_no_completed_receipts_has_zero_requests_and_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            receipt_root.mkdir(mode=0o755)
            archive_root = base / "archives"
            result = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(),
            )
            self.assertEqual(
                result["status"],
                "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
            )
            self.assertEqual(result["required_day_count"], 0)
            self.assertEqual(result["network_request_count"], 0)
            self.assertFalse(archive_root.exists())

    def test_single_day_success_is_exact_loadable_and_retry_is_offline(self):
        archive, checksum = daily_archive("2026-07-30")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "archives"
            write_receipts(receipt_root, [self.first_receipt()])
            transport = FixtureTransport(
                period_responses("2026-07-30", archive, checksum)
            )
            result = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=transport,
            )
            self.assertEqual(
                result["status"], "COHORT_DAILY_ARCHIVE_COMPLETE"
            )
            self.assertEqual(result["network_request_count"], 2)
            self.assertEqual(
                result["days"][0]["required_execution_minutes"],
                [
                    "2026-07-30T12:03:00.000Z",
                    "2026-07-30T20:03:00.000Z",
                ],
            )
            day_root = archive_root / ARCHIVE_DIRECTORY / "2026-07-30"
            self.assertEqual(
                stat.S_IMODE(archive_root.stat().st_mode), 0o700
            )
            self.assertEqual(
                stat.S_IMODE(day_root.parent.stat().st_mode), 0o700
            )
            self.assertEqual(stat.S_IMODE(day_root.stat().st_mode), 0o700)
            self.assertEqual(len(tuple(day_root.iterdir())), 3)
            for path in day_root.iterdir():
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.stat().st_nlink, 1)
            receipt = json.loads(
                (day_root / "receipt.json").read_text()
            )
            self.assertEqual(
                receipt["receipt_hash"],
                challenger_cohort_daily_archive_receipt_hash(receipt),
            )
            plan, plan_sha = _read_exact_plan(PLAN)
            self.assertFalse(
                challenger_cohort_daily_archive_receipt_reasons(
                    receipt,
                    plan=plan,
                    plan_file_sha256=plan_sha,
                    archive_bytes=archive,
                    checksum_bytes=checksum,
                )
            )
            loaded = load_challenger_cohort_daily_archives(
                cohort_plan_path=PLAN,
                episode_receipt_output_root=receipt_root,
                install_receipt_path=Path("/unused/install.json"),
                contract_path=Path("/unused/contract.json"),
                plist_path=Path("/unused/agent.plist"),
                archive_output_root=archive_root,
                receipt_loader=fixture_loader,
            )
            self.assertEqual(loaded["2026-07-30"][:2], (archive, checksum))
            retry = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(),
                observed_at="2026-08-01T00:05:00.000Z",
            )
            self.assertEqual(retry["network_request_count"], 0)

    def test_production_loader_accepts_real_v045_fixture_receipt(self):
        from tests.test_challenger_cohort_episode_receipt import (
            ChallengerCohortEpisodeReceiptTests,
        )

        archive, checksum = daily_archive("2026-07-30")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            helper = ChallengerCohortEpisodeReceiptTests()
            environment = helper.environment(base / "runtime")
            helper.record(environment, ONE_COHORT_EPISODE)
            observed = helper.observe(
                environment,
                COHORT_START + timedelta(hours=8, minutes=2),
            )
            self.assertEqual(observed["completed_episode_count"], 1)
            result = acquire_challenger_cohort_daily_archives(
                cohort_plan_path=environment["cohort_plan_path"],
                episode_receipt_output_root=environment[
                    "receipt_output_root"
                ],
                install_receipt_path=environment[
                    "install_receipt_path"
                ],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
                archive_output_root=base / "archives",
                observed_at="2026-07-31T00:05:00.000Z",
                transport=FixtureTransport(
                    period_responses(
                        "2026-07-30", archive, checksum
                    )
                ),
            )
            self.assertEqual(
                result["status"], "COHORT_DAILY_ARCHIVE_COMPLETE"
            )
            self.assertEqual(result["episode_receipt_count"], 1)

    def test_later_same_day_episode_reuses_immutable_day_receipt(self):
        archive, checksum = daily_archive("2026-07-30")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "archives"
            first = self.first_receipt()
            write_receipts(receipt_root, [first])
            self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(
                    period_responses("2026-07-30", archive, checksum)
                ),
            )
            receipt_path = (
                archive_root
                / ARCHIVE_DIRECTORY
                / "2026-07-30"
                / "receipt.json"
            )
            exact = receipt_path.read_bytes()
            second = episode_receipt(
                2,
                entry_scheduled="2026-07-30T21:00:00.000Z",
                entry_recorded="2026-07-30T21:02:01.000Z",
                exit_recorded="2026-07-30T23:02:01.000Z",
                prior_ids=(first["episode"]["episode_id"],),
            )
            write_receipts(receipt_root, [second])
            reused = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(),
            )
            self.assertEqual(reused["episode_receipt_count"], 2)
            self.assertEqual(reused["required_day_count"], 1)
            self.assertEqual(reused["network_request_count"], 0)
            self.assertEqual(receipt_path.read_bytes(), exact)
            self.assertEqual(
                reused["days"][0]["required_execution_minutes"],
                [
                    "2026-07-30T12:03:00.000Z",
                    "2026-07-30T20:03:00.000Z",
                    "2026-07-30T21:03:00.000Z",
                    "2026-07-30T23:03:00.000Z",
                ],
            )

    def test_cross_day_partial_then_resume_fetches_only_missing_day(self):
        first = episode_receipt(
            1,
            entry_scheduled="2026-07-30T20:00:00.000Z",
            entry_recorded="2026-07-30T20:02:00.000Z",
            exit_recorded="2026-07-31T00:02:00.000Z",
        )
        archive_30, checksum_30 = daily_archive("2026-07-30")
        archive_31, checksum_31 = daily_archive("2026-07-31")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "archives"
            write_receipts(receipt_root, [first])
            initial = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(
                    period_responses(
                        "2026-07-30", archive_30, checksum_30
                    )
                ),
                observed_at="2026-07-31T00:05:00.000Z",
            )
            self.assertEqual(
                initial["status"], "COHORT_DAILY_ARCHIVE_PARTIAL"
            )
            self.assertEqual(initial["verified_day_count"], 1)
            self.assertEqual(initial["network_request_count"], 2)
            resumed = self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(
                    period_responses(
                        "2026-07-31", archive_31, checksum_31
                    )
                ),
                observed_at="2026-08-01T00:05:00.000Z",
            )
            self.assertEqual(
                resumed["status"], "COHORT_DAILY_ARCHIVE_COMPLETE"
            )
            self.assertEqual(resumed["network_request_count"], 2)

    def test_partial_exact_publish_recovers_and_conflict_fails(self):
        archive, checksum = daily_archive("2026-07-30")
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2026-07-30",
        )
        for partial_bytes, succeeds in (
            (archive, True),
            (b"conflicting-partial-archive", False),
        ):
            with self.subTest(succeeds=succeeds):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    receipt_root = base / "receipts"
                    archive_root = base / "archives"
                    write_receipts(
                        receipt_root, [self.first_receipt()]
                    )
                    day_root = (
                        archive_root
                        / ARCHIVE_DIRECTORY
                        / "2026-07-30"
                    )
                    day_root.mkdir(mode=0o700, parents=True)
                    archive_root.chmod(0o700)
                    day_root.parent.chmod(0o700)
                    partial = day_root / request.archive_filename
                    partial.write_bytes(partial_bytes)
                    partial.chmod(0o600)
                    transport = FixtureTransport(
                        period_responses(
                            "2026-07-30", archive, checksum
                        )
                    )
                    if succeeds:
                        result = self.acquire(
                            receipt_root=receipt_root,
                            archive_root=archive_root,
                            transport=transport,
                        )
                        self.assertEqual(
                            result["status"],
                            "COHORT_DAILY_ARCHIVE_COMPLETE",
                        )
                    else:
                        with self.assertRaises(
                            ChallengerCohortDailyArchiveError
                        ):
                            self.acquire(
                                receipt_root=receipt_root,
                                archive_root=archive_root,
                                transport=transport,
                            )
                        self.assertFalse(
                            (day_root / "receipt.json").exists()
                        )

    def test_unrequired_archive_inventory_fails_before_network(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "archives"
            write_receipts(receipt_root, [self.first_receipt()])
            extra = (
                archive_root
                / ARCHIVE_DIRECTORY
                / "2026-07-31"
            )
            extra.mkdir(mode=0o700, parents=True)
            archive_root.chmod(0o700)
            extra.parent.chmod(0o700)
            transport = FixtureTransport()
            with self.assertRaisesRegex(
                ChallengerCohortDailyArchiveError,
                "CHALLENGER_COHORT_DAILY_ARCHIVE_INVENTORY_INVALID",
            ):
                self.acquire(
                    receipt_root=receipt_root,
                    archive_root=archive_root,
                    transport=transport,
                )
            self.assertEqual(transport.calls, [])

    def test_time_gate_and_both_404_states_publish_no_success(self):
        archive, _checksum = daily_archive("2026-07-30")
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2026-07-30",
        )
        cases = (
            (
                "2026-07-31T00:04:59.000Z",
                {},
                "COHORT_DAILY_ARCHIVE_NOT_YET_ELIGIBLE",
                0,
            ),
            (
                "2026-07-31T00:05:00.000Z",
                {
                    request.archive_url: response(
                        request.archive_url, 404
                    )
                },
                "COHORT_DAILY_ARCHIVE_PENDING_ZIP_404",
                1,
            ),
            (
                "2026-07-31T00:05:00.000Z",
                {
                    request.archive_url: response(
                        request.archive_url, 200, archive
                    ),
                    request.checksum_url: response(
                        request.checksum_url, 404
                    ),
                },
                "COHORT_DAILY_ARCHIVE_PENDING_CHECKSUM_404",
                2,
            ),
        )
        for observed, responses, expected, count in cases:
            with self.subTest(status=expected):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    receipt_root = base / "receipts"
                    archive_root = base / "archives"
                    write_receipts(
                        receipt_root, [self.first_receipt()]
                    )
                    result = self.acquire(
                        receipt_root=receipt_root,
                        archive_root=archive_root,
                        transport=FixtureTransport(responses),
                        observed_at=observed,
                    )
                    self.assertEqual(
                        result["days"][0]["status"], expected
                    )
                    self.assertEqual(
                        result["network_request_count"], count
                    )
                    self.assertFalse(
                        (
                            archive_root
                            / ARCHIVE_DIRECTORY
                            / "2026-07-30"
                            / "receipt.json"
                        ).exists()
                    )

    def test_invalid_episode_sets_fail_before_network(self):
        first = self.first_receipt()
        duplicate = copy.deepcopy(first)
        duplicate["episode"]["ordinal"] = 2
        duplicate["episode"]["entry_scheduled_for"] = (
            "2026-07-30T16:00:00.000Z"
        )
        duplicate["prior_completed_episodes"] = {
            "count": 1,
            "episode_ids": [first["episode"]["episode_id"]],
        }
        missing = episode_receipt(
            2,
            entry_scheduled="2026-07-30T16:00:00.000Z",
            entry_recorded="2026-07-30T16:02:00.000Z",
            exit_recorded="2026-07-30T20:02:00.000Z",
            prior_ids=("challenger_episode_" + "1" * 64,),
        )
        for receipts in ([duplicate], [first, duplicate], [first, missing]):
            with self.subTest(count=len(receipts)):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    receipt_root = base / "receipts"
                    write_receipts(receipt_root, receipts)
                    transport = FixtureTransport()
                    with self.assertRaises(
                        ChallengerCohortDailyArchiveError
                    ):
                        self.acquire(
                            receipt_root=receipt_root,
                            archive_root=base / "archives",
                            transport=transport,
                        )
                    self.assertEqual(transport.calls, [])

    def test_unknown_file_symlink_and_bad_permission_fail_before_network(self):
        for kind in ("unknown", "symlink", "mode"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    receipt_root = base / "receipts"
                    write_receipts(
                        receipt_root, [self.first_receipt()]
                    )
                    receipt_directory = receipt_root / EPISODE_DIRECTORY
                    if kind == "unknown":
                        path = receipt_directory / "README"
                        path.write_text("unexpected")
                        path.chmod(0o600)
                    elif kind == "symlink":
                        target = base / "outside.json"
                        target.write_text("{}")
                        os.symlink(target, receipt_directory / "bad.json")
                    else:
                        path = next(receipt_directory.iterdir())
                        path.chmod(0o644)
                    transport = FixtureTransport()
                    with self.assertRaises(
                        ChallengerCohortDailyArchiveError
                    ):
                        self.acquire(
                            receipt_root=receipt_root,
                            archive_root=base / "archives",
                            transport=transport,
                        )
                    self.assertEqual(transport.calls, [])

    def test_bad_checksum_short_day_redirect_and_mutation_fail_closed(self):
        archive, checksum = daily_archive("2026-07-30")
        short_archive, short_checksum = daily_archive(
            "2026-07-30", row_count=1439
        )
        request = HistoricalArchiveRequest.create(
            market="SPOT",
            data_family="KLINES",
            symbol="ETHUSDT",
            interval_or_null="1m",
            period_kind="DAILY",
            period="2026-07-30",
        )
        cases = (
            period_responses(
                "2026-07-30", archive, checksum[:-1] + b"x"
            ),
            period_responses(
                "2026-07-30", short_archive, short_checksum
            ),
            {
                request.archive_url: response(
                    "https://example.invalid/file.zip", 200, archive
                )
            },
        )
        for responses in cases:
            with tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                receipt_root = base / "receipts"
                write_receipts(receipt_root, [self.first_receipt()])
                with self.assertRaises(
                    ChallengerCohortDailyArchiveError
                ):
                    self.acquire(
                        receipt_root=receipt_root,
                        archive_root=base / "archives",
                        transport=FixtureTransport(responses),
                    )

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "archives"
            write_receipts(receipt_root, [self.first_receipt()])
            self.acquire(
                receipt_root=receipt_root,
                archive_root=archive_root,
                transport=FixtureTransport(
                    period_responses("2026-07-30", archive, checksum)
                ),
            )
            receipt_path = (
                archive_root
                / ARCHIVE_DIRECTORY
                / "2026-07-30"
                / "receipt.json"
            )
            receipt = json.loads(receipt_path.read_text())
            receipt["retrieved_at"] = "2026-07-31T00:06:00.000Z"
            receipt["receipt_hash"] = (
                challenger_cohort_daily_archive_receipt_hash(receipt)
            )
            receipt_path.write_text(canonical_json(receipt))
            receipt_path.chmod(0o600)
            transport = FixtureTransport()
            with self.assertRaises(ChallengerCohortDailyArchiveError):
                self.acquire(
                    receipt_root=receipt_root,
                    archive_root=archive_root,
                    transport=transport,
                )
            self.assertEqual(transport.calls, [])

    def test_day_receipt_is_deterministic_across_100_builds(self):
        plan, plan_sha = _read_exact_plan(PLAN)
        archive, checksum = daily_archive("2026-07-30")
        source = _verified_daily_source(
            period="2026-07-30",
            archive_bytes=archive,
            checksum_bytes=checksum,
            retrieved_at="2026-07-31T00:05:00.000Z",
        )
        values = {
            canonical_json(
                _build_receipt(
                    plan=plan,
                    plan_file_sha256=plan_sha,
                    source=source,
                )
            )
            for _ in range(100)
        }
        self.assertEqual(len(values), 1)

    def test_cli_has_no_selectors_and_uses_loader(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = acquisition_main(["--help"])
        self.assertEqual(code, 0)
        help_text = stdout.getvalue()
        for forbidden in (
            "--episode-id",
            "--episode-path",
            "--date",
            "--period",
            "--url",
            "--symbol",
            "--price",
            "--pnl",
        ):
            self.assertNotIn(forbidden, help_text)

        archive, checksum = daily_archive("2026-07-30")
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            archive_root = base / "owner" / "archives"
            archive_root.parent.mkdir(mode=0o700)
            write_receipts(receipt_root, [self.first_receipt()])
            placeholders = [
                base / name
                for name in ("install.json", "contract.json", "agent.plist")
            ]
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = acquisition_main(
                    [
                        "--cohort-plan-path",
                        str(PLAN),
                        "--episode-receipt-output-root",
                        str(receipt_root),
                        "--install-receipt-path",
                        str(placeholders[0]),
                        "--contract-path",
                        str(placeholders[1]),
                        "--plist-path",
                        str(placeholders[2]),
                        "--archive-output-root",
                        str(archive_root),
                    ],
                    clock=lambda: "2026-07-31T00:05:00.000Z",
                    transport=FixtureTransport(
                        period_responses(
                            "2026-07-30", archive, checksum
                        )
                    ),
                    receipt_loader=fixture_loader,
                    allowed_output_base=archive_root.parent,
                )
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(stdout.getvalue())["status"],
                "COHORT_DAILY_ARCHIVE_COMPLETE",
            )


if __name__ == "__main__":
    unittest.main()
