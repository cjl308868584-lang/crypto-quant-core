import contextlib
import hashlib
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_daily_archive import (
    acquire_challenger_cohort_daily_archives,
)
from crypto_quant.challenger_cohort_economic_result_cli import (
    main as result_main,
)
from crypto_quant.challenger_cohort_economic_results import (
    ChallengerCohortEconomicResultError,
    challenger_cohort_episode_economic_result_hash,
    publish_all_cohort_economic_results,
)
from tests.test_challenger_cohort_daily_archive import (
    FixtureTransport,
    episode_receipt,
    fixture_loader,
    period_responses,
    write_receipts,
)
from tests.test_challenger_episode_economic_evaluator import daily_archive


ROOT = Path(__file__).resolve().parents[1]
COHORT_PLAN = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-cohort-plan-v0.43.0.json"
)
ECONOMIC_PLAN = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-episode-economic-plan-v0.37.0.json"
)
RESULT_DIRECTORY = "challenger-cohort-economic-results"
INDEX_DIRECTORY = "challenger-cohort-economic-result-index"


def complete_receipt(
    ordinal,
    *,
    entry_scheduled,
    entry_recorded,
    exit_recorded,
    prior_ids=(),
    positive=True,
):
    receipt = episode_receipt(
        ordinal,
        entry_scheduled=entry_scheduled,
        entry_recorded=entry_recorded,
        exit_recorded=exit_recorded,
        prior_ids=prior_ids,
    )
    receipt["episode"].update(
        {
            "entry_decision_id": (
                "challenger_decision_"
                + hashlib.sha256(f"entry-{ordinal}".encode()).hexdigest()
            ),
            "entry_decision_hash": hashlib.sha256(
                f"entry-hash-{ordinal}".encode()
            ).hexdigest(),
            "exit_decision_id": (
                "challenger_decision_"
                + hashlib.sha256(f"exit-{ordinal}".encode()).hexdigest()
            ),
            "exit_decision_hash": hashlib.sha256(
                f"exit-hash-{ordinal}".encode()
            ).hexdigest(),
            "exit_action": (
                "EXIT_LONG_SMA20"
                if positive
                else "EXIT_LONG_VERTICAL_24H"
            ),
        }
    )
    return receipt


class ChallengerCohortEconomicResultTests(unittest.TestCase):
    def fixture(self, base, *, receipts=1):
        receipt_root = base / "receipts"
        archive_root = base / "archives"
        result_root = base / "results"
        first = complete_receipt(
            1,
            entry_scheduled="2026-07-30T12:00:00.000Z",
            entry_recorded="2026-07-30T12:02:06.752Z",
            exit_recorded="2026-07-30T20:02:06.752Z",
        )
        values = [first]
        periods = ["2026-07-30"]
        if receipts == 2:
            second = complete_receipt(
                2,
                entry_scheduled="2026-07-31T00:00:00.000Z",
                entry_recorded="2026-07-31T00:02:06.752Z",
                exit_recorded="2026-07-31T08:02:06.752Z",
                prior_ids=(first["episode"]["episode_id"],),
                positive=False,
            )
            values.append(second)
            periods.append("2026-07-31")
        write_receipts(receipt_root, values)
        responses = {}
        for period in periods:
            selected = {}
            if period == "2026-07-30":
                selected = {
                    "2026-07-30T12:03:00.000Z": ("2000.01", "1999"),
                    "2026-07-30T20:03:00.000Z": ("2101", "2100.01"),
                }
            if period == "2026-07-31":
                selected = {
                    "2026-07-31T00:03:00.000Z": ("2200.01", "2199"),
                    "2026-07-31T08:03:00.000Z": ("2001", "2000.01"),
                }
            archive, checksum = daily_archive(
                period, selected_prices=selected
            )
            responses.update(period_responses(period, archive, checksum))
        acquired = acquire_challenger_cohort_daily_archives(
            cohort_plan_path=COHORT_PLAN,
            episode_receipt_output_root=receipt_root,
            install_receipt_path=Path("/unused/install.json"),
            contract_path=Path("/unused/contract.json"),
            plist_path=Path("/unused/agent.plist"),
            archive_output_root=archive_root,
            observed_at=(
                "2026-08-01T00:05:00.000Z"
                if receipts == 2
                else "2026-07-31T00:05:00.000Z"
            ),
            transport=FixtureTransport(responses),
            receipt_loader=fixture_loader,
        )
        self.assertEqual(acquired["status"], "COHORT_DAILY_ARCHIVE_COMPLETE")
        return receipt_root, archive_root, result_root, values

    def publish(self, receipt_root, archive_root, result_root, **kwargs):
        return publish_all_cohort_economic_results(
            cohort_plan_path=COHORT_PLAN,
            economic_plan_path=ECONOMIC_PLAN,
            episode_receipt_output_root=receipt_root,
            install_receipt_path=Path("/unused/install.json"),
            contract_path=Path("/unused/contract.json"),
            plist_path=Path("/unused/agent.plist"),
            archive_output_root=archive_root,
            result_output_root=result_root,
            receipt_loader=fixture_loader,
            **kwargs,
        )

    def test_schema_mirrors_are_identical_and_valid(self):
        names = (
            "challenger-cohort-episode-economic-result-v1.schema.json",
            "challenger-cohort-economic-result-index-v1.schema.json",
        )
        for name in names:
            with self.subTest(name=name):
                config = ROOT / "config" / name
                package = ROOT / "src" / "crypto_quant" / "schemas" / name
                self.assertEqual(config.read_bytes(), package.read_bytes())
                Draft202012Validator.check_schema(
                    json.loads(config.read_text())
                )

    def test_no_completed_episode_is_zero_write_and_offline(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            summary = self.publish(
                base / "missing-receipts",
                base / "missing-archives",
                base / "missing-results",
            )
            self.assertEqual(
                summary["status"],
                "COHORT_ECONOMIC_RESULT_NO_COMPLETED_EPISODES",
            )
            self.assertEqual(summary["new_result_count"], 0)
            self.assertEqual(summary["market_request_count"], 0)
            self.assertFalse((base / "missing-results").exists())

    def test_single_result_is_costed_ineligible_exact_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root, _ = self.fixture(base)
            first = self.publish(receipt_root, archive_root, result_root)
            self.assertEqual(first["status"], "DESCRIPTIVE_NO_EARLY_SUCCESS")
            self.assertEqual(first["new_result_count"], 1)
            self.assertEqual(first["new_index_count"], 1)
            result_path = next((result_root / RESULT_DIRECTORY).iterdir())
            index_path = next((result_root / INDEX_DIRECTORY).iterdir())
            result = json.loads(result_path.read_text())
            self.assertEqual(result["economics"]["entry_fill_price"], "2002.02")
            self.assertEqual(result["economics"]["exit_fill_price"], "2097.9")
            self.assertEqual(result["economics"]["positive_label"], 1)
            self.assertEqual(
                result["eligibility"]["profitability"],
                "INELIGIBLE_INTERIM_COHORT",
            )
            self.assertEqual(
                result["result_hash"],
                challenger_cohort_episode_economic_result_hash(result),
            )
            for path in (result_root, result_path.parent, index_path.parent):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
            for path in (result_path, index_path):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.stat().st_nlink, 1)
            before = {
                path: (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns)
                for path in (result_path, index_path)
            }
            for _ in range(100):
                second = self.publish(receipt_root, archive_root, result_root)
                self.assertEqual(second["new_result_count"], 0)
                self.assertEqual(second["new_index_count"], 0)
            for path, expected in before.items():
                self.assertEqual(
                    (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns),
                    expected,
                )

    def test_two_results_append_cumulative_index_and_retain_negative(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root, _ = self.fixture(
                base, receipts=2
            )
            summary = self.publish(receipt_root, archive_root, result_root)
            self.assertEqual(summary["result_count"], 2)
            self.assertEqual(summary["index_count"], 2)
            results = [
                json.loads(path.read_text())
                for path in sorted((result_root / RESULT_DIRECTORY).iterdir())
            ]
            self.assertEqual(
                [value["economics"]["positive_label"] for value in results],
                [1, 0],
            )
            indexes = [
                json.loads(path.read_text())
                for path in sorted((result_root / INDEX_DIRECTORY).iterdir())
            ]
            self.assertEqual([value["entry_count"] for value in indexes], [1, 2])
            self.assertEqual(
                indexes[1]["previous_index_hash"], indexes[0]["index_hash"]
            )
            self.assertEqual(
                [entry["positive_label"] for entry in indexes[1]["entries"]],
                [1, 0],
            )

    def test_result_only_crash_recovers_without_rewriting_result(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root, _ = self.fixture(base)

            def crash(_ordinal, _record):
                raise RuntimeError("simulated crash")

            with self.assertRaisesRegex(RuntimeError, "simulated crash"):
                self.publish(
                    receipt_root,
                    archive_root,
                    result_root,
                    after_result_hook=crash,
                )
            result_path = next((result_root / RESULT_DIRECTORY).iterdir())
            before = (
                result_path.read_bytes(),
                result_path.stat().st_ino,
                result_path.stat().st_mtime_ns,
            )
            self.assertFalse((result_root / INDEX_DIRECTORY).exists())
            summary = self.publish(receipt_root, archive_root, result_root)
            self.assertEqual(summary["new_result_count"], 0)
            self.assertEqual(summary["new_index_count"], 1)
            self.assertEqual(
                (
                    result_path.read_bytes(),
                    result_path.stat().st_ino,
                    result_path.stat().st_mtime_ns,
                ),
                before,
            )

    def test_result_and_index_tampering_fail_closed(self):
        for target in ("result", "index"):
            with self.subTest(target=target):
                with tempfile.TemporaryDirectory() as directory:
                    base = Path(directory)
                    receipt_root, archive_root, result_root, _ = self.fixture(base)
                    self.publish(receipt_root, archive_root, result_root)
                    path = next(
                        (
                            result_root
                            / (
                                RESULT_DIRECTORY
                                if target == "result"
                                else INDEX_DIRECTORY
                            )
                        ).iterdir()
                    )
                    value = json.loads(path.read_text())
                    if target == "result":
                        value["economics"]["net_pnl_usdt"] = "999"
                    else:
                        value["entries"][0]["positive_label"] = 0
                    path.write_text(canonical_json(value))
                    path.chmod(0o600)
                    with self.assertRaises(
                        ChallengerCohortEconomicResultError
                    ):
                        self.publish(receipt_root, archive_root, result_root)

    def test_index_without_result_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root, _ = self.fixture(base)
            self.publish(receipt_root, archive_root, result_root)
            next((result_root / RESULT_DIRECTORY).iterdir()).unlink()
            with self.assertRaisesRegex(
                ChallengerCohortEconomicResultError,
                "INDEX_WITHOUT_RESULT",
            ):
                self.publish(receipt_root, archive_root, result_root)

    def test_extra_result_or_missing_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, archive_root, result_root, _ = self.fixture(base)
            result_root.mkdir(mode=0o700)
            result_dir = result_root / RESULT_DIRECTORY
            result_dir.mkdir(mode=0o700)
            extra = result_dir / "extra.json"
            extra.write_text("{}")
            extra.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEconomicResultError, "INVENTORY"
            ):
                self.publish(receipt_root, archive_root, result_root)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root, _archive_root, result_root, _ = self.fixture(base)
            with self.assertRaisesRegex(Exception, "INCOMPLETE"):
                self.publish(
                    receipt_root, base / "missing-archive", result_root
                )

    def test_cli_help_has_paths_and_no_selectors(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = result_main(["--help"])
        self.assertEqual(code, 0)
        help_text = stdout.getvalue()
        for allowed in (
            "--cohort-plan-path",
            "--economic-plan-path",
            "--episode-receipt-output-root",
            "--archive-output-root",
            "--result-output-root",
        ):
            self.assertIn(allowed, help_text)
        for forbidden in (
            "--episode-id",
            "--ordinal",
            "--date",
            "--period",
            "--price",
            "--fee",
            "--pnl",
            "--label",
            "--result-id",
            "--filename",
            "--evaluated-at",
            "--url",
        ):
            self.assertNotIn(forbidden, help_text)

    def test_cli_no_episode_summary_uses_owner_only_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            owner = base / "owner"
            owner.mkdir(mode=0o700)
            arguments = [
                "--cohort-plan-path",
                str(COHORT_PLAN),
                "--economic-plan-path",
                str(ECONOMIC_PLAN),
                "--episode-receipt-output-root",
                str(owner / "receipts"),
                "--install-receipt-path",
                "/unused/install.json",
                "--contract-path",
                "/unused/contract.json",
                "--plist-path",
                "/unused/agent.plist",
                "--archive-output-root",
                str(owner / "archives"),
                "--result-output-root",
                str(owner / "results"),
            ]
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
                stderr
            ):
                code = result_main(
                    arguments,
                    receipt_loader=fixture_loader,
                    allowed_output_base=owner,
                )
            self.assertEqual(code, 0, stderr.getvalue())
            summary = json.loads(stdout.getvalue())
            self.assertEqual(
                summary["status"],
                "COHORT_ECONOMIC_RESULT_NO_COMPLETED_EPISODES",
            )
            self.assertEqual(stderr.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
