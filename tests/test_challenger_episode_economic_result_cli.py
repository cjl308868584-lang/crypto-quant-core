import contextlib
import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_episode_archive_acquisition import (
    acquire_challenger_episode_archives,
)
from crypto_quant.challenger_episode_economic_result_cli import (
    main as result_main,
)
from tests.test_challenger_episode_archive_acquisition import (
    FixtureTransport,
    period_responses,
)
from tests.test_challenger_episode_economic_evaluator import (
    PLAN_PATH,
    completion_receipt,
    daily_archive,
)


class ChallengerEpisodeEconomicResultCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.plan_sha = hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest()

    def fixture(
        self,
        base,
        *,
        vertical=False,
        complete=True,
    ):
        completion, completion_sha = completion_receipt(
            vertical=vertical
        )
        completion_path = base / "completion.json"
        completion_path.write_bytes(canonical_json(completion).encode())
        completion_path.chmod(0o600)
        trusted = []
        for name in ("install.json", "contract.json", "agent.plist"):
            path = base / name
            path.write_text("{}")
            path.chmod(0o600)
            trusted.append(path)
        owner = base / "owner"
        owner.mkdir(mode=0o700)
        archive_root = owner / "archives"
        result_root = owner / "results"
        if complete:
            periods = ("2026-07-29", "2026-07-30") if vertical else (
                "2026-07-29",
            )
            responses = {}
            for period in periods:
                selected = {}
                if period == "2026-07-29":
                    selected["2026-07-29T00:03:00.000Z"] = (
                        "2000.01",
                        "1999",
                    )
                    if not vertical:
                        selected["2026-07-29T08:03:00.000Z"] = (
                            "2101",
                            "2100.01",
                        )
                else:
                    selected["2026-07-30T00:03:00.000Z"] = (
                        "2201",
                        "2200.01",
                    )
                archive, checksum = daily_archive(
                    period,
                    selected_prices=selected,
                )
                responses.update(
                    period_responses(period, archive, checksum)
                )
            acquired = acquire_challenger_episode_archives(
                plan=self.plan,
                plan_file_sha256=self.plan_sha,
                completion_receipt=completion,
                completion_receipt_file_sha256=completion_sha,
                output_root=archive_root,
                observed_at=(
                    "2026-07-31T00:05:00.000Z"
                    if vertical
                    else "2026-07-30T00:05:00.000Z"
                ),
                transport=FixtureTransport(responses),
            )
            self.assertEqual(
                acquired["status"], "ARCHIVE_ACQUISITION_COMPLETE"
            )
        arguments = [
            "--economic-plan-path",
            str(PLAN_PATH),
            "--completion-receipt-path",
            str(completion_path),
            "--install-receipt-path",
            str(trusted[0]),
            "--contract-path",
            str(trusted[1]),
            "--plist-path",
            str(trusted[2]),
            "--archive-output-root",
            str(archive_root),
            "--result-output-root",
            str(result_root),
        ]

        def loader(**kwargs):
            self.assertEqual(
                kwargs["receipt_path"], completion_path
            )
            self.assertEqual(
                kwargs["install_receipt_path"], trusted[0]
            )
            self.assertEqual(kwargs["contract_path"], trusted[1])
            self.assertEqual(kwargs["plist_path"], trusted[2])
            return completion

        return arguments, loader, archive_root, result_root

    def invoke(self, arguments, loader, base):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
            stderr
        ):
            code = result_main(
                arguments,
                receipt_loader=loader,
                allowed_output_base=base,
            )
        return code, stdout.getvalue(), stderr.getvalue()

    def test_help_exposes_paths_but_no_economic_or_market_overrides(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = result_main(["--help"])
        self.assertEqual(code, 0)
        help_text = stdout.getvalue()
        for allowed in (
            "--economic-plan-path",
            "--completion-receipt-path",
            "--install-receipt-path",
            "--contract-path",
            "--plist-path",
            "--archive-output-root",
            "--result-output-root",
        ):
            self.assertIn(allowed, help_text)
        for forbidden in (
            "--url",
            "--period",
            "--symbol",
            "--execution-minute",
            "--price",
            "--quantity",
            "--slippage",
            "--fee",
            "--capital",
            "--pnl",
            "--label",
            "--result-id",
            "--result-filename",
            "--state",
            "--order",
            "--evaluated-at",
        ):
            self.assertNotIn(forbidden, help_text)

    def test_success_publishes_and_reloads_owner_only_exact_result(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, archive_root, result_root = self.fixture(
                base
            )
            code, stdout, stderr = self.invoke(
                arguments, loader, base
            )
            self.assertEqual(code, 0, stderr)
            summary = json.loads(stdout)
            self.assertEqual(
                summary["status"],
                "COMPLETED_ARCHIVE_FORWARD_ECONOMIC_PROXY",
            )
            self.assertEqual(
                summary["evaluated_at"],
                "2026-07-30T00:05:00.000Z",
            )
            self.assertEqual(
                summary["security_boundary"]["market_request_count"],
                0,
            )
            self.assertEqual(
                summary["security_boundary"][
                    "runner_invocation_count"
                ],
                0,
            )
            result_path = Path(summary["result_path"])
            self.assertEqual(
                result_path.parent, result_root.resolve()
            )
            self.assertEqual(
                result_path.name,
                f"{summary['result_id']}.json",
            )
            self.assertEqual(
                stat.S_IMODE(result_root.stat().st_mode), 0o700
            )
            self.assertEqual(
                stat.S_IMODE(result_path.stat().st_mode), 0o600
            )
            self.assertEqual(
                hashlib.sha256(result_path.read_bytes()).hexdigest(),
                summary["result_file_sha256"],
            )
            self.assertTrue(archive_root.exists())
            self.assertEqual(stderr, "")

    def test_identical_retry_produces_same_path_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, _ = self.fixture(base)
            first = self.invoke(arguments, loader, base)
            self.assertEqual(first[0], 0, first[2])
            first_summary = json.loads(first[1])
            path = Path(first_summary["result_path"])
            first_bytes = path.read_bytes()
            first_stat = path.stat()
            second = self.invoke(arguments, loader, base)
            self.assertEqual(second[0], 0, second[2])
            second_summary = json.loads(second[1])
            self.assertEqual(second_summary, first_summary)
            self.assertEqual(path.read_bytes(), first_bytes)
            self.assertEqual(path.stat().st_ino, first_stat.st_ino)
            self.assertEqual(path.stat().st_mtime_ns, first_stat.st_mtime_ns)

    def test_cross_day_uses_latest_archive_receipt_time(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, _ = self.fixture(
                base,
                vertical=True,
            )
            code, stdout, stderr = self.invoke(
                arguments, loader, base
            )
            self.assertEqual(code, 0, stderr)
            summary = json.loads(stdout)
            self.assertEqual(
                summary["evaluated_at"],
                "2026-07-31T00:05:00.000Z",
            )

    def test_incomplete_archive_set_fails_without_result(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, result_root = self.fixture(
                base,
                complete=False,
            )
            code, stdout, stderr = self.invoke(
                arguments, loader, base
            )
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("ARCHIVE_SET_INCOMPLETE", stderr)
            self.assertFalse(result_root.exists())

    def test_plan_receipt_and_output_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, result_root = self.fixture(base)
            bad_plan = base / "plan-link.json"
            os.symlink(PLAN_PATH, bad_plan)
            cases = (
                (
                    [
                        str(bad_plan)
                        if value == str(PLAN_PATH)
                        else value
                        for value in arguments
                    ],
                    loader,
                ),
                (
                    [
                        "relative.json"
                        if value.endswith("completion.json")
                        else value
                        for value in arguments
                    ],
                    loader,
                ),
                (
                    [
                        str(base / "outside")
                        if value == str(result_root)
                        else value
                        for value in arguments
                    ],
                    loader,
                ),
            )
            for case_arguments, case_loader in cases:
                with self.subTest(arguments=case_arguments):
                    code, stdout, stderr = self.invoke(
                        case_arguments,
                        case_loader,
                        base / "owner",
                    )
                    self.assertEqual(code, 1)
                    self.assertEqual(stdout, "")
                    self.assertTrue(stderr)

    def test_existing_insecure_or_symlink_result_root_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, result_root = self.fixture(base)
            result_root.mkdir(mode=0o755)
            result_root.chmod(0o755)
            code, _, stderr = self.invoke(arguments, loader, base)
            self.assertEqual(code, 1)
            self.assertIn("OUTPUT_INVALID", stderr)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, archive_root, result_root = self.fixture(
                base
            )
            arguments = [
                str(archive_root)
                if value == str(result_root)
                else value
                for value in arguments
            ]
            code, _, stderr = self.invoke(arguments, loader, base)
            self.assertEqual(code, 1)
            self.assertIn("OUTPUT_INVALID", stderr)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            arguments, loader, _, result_root = self.fixture(base)
            target = base / "owner" / "target"
            target.mkdir(mode=0o700)
            os.symlink(target, result_root)
            code, _, stderr = self.invoke(arguments, loader, base)
            self.assertEqual(code, 1)
            self.assertIn("OUTPUT_INVALID", stderr)


if __name__ == "__main__":
    unittest.main()
