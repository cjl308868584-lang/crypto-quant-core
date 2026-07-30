import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from crypto_quant.challenger_cohort_evidence_maintenance import (
    ChallengerCohortEvidenceMaintenanceError,
    maintain_challenger_cohort_evidence,
)
from crypto_quant.challenger_cohort_evidence_maintenance_cli import (
    main as maintenance_main,
)


OBSERVED = datetime(2026, 7, 31, 4, 10, tzinfo=timezone.utc)
OBSERVED_TEXT = "2026-07-31T04:10:00.000Z"


class Transport:
    def get(self, _url):
        raise AssertionError("fixture transport must not be called")


def receipt_summary(count=0, created=0):
    return {
        "status": "COHORT_CONTINUITY_COLLECTING_VERIFIED",
        "observed_at": OBSERVED_TEXT,
        "cohort_slot_count": 5,
        "completed_episode_count": count,
        "receipt_created_count": created,
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
    }


def archive_summary(status, *, receipts, required, verified, requests=0):
    return {
        "status": status,
        "observed_at": OBSERVED_TEXT,
        "episode_receipt_count": receipts,
        "required_day_count": required,
        "verified_day_count": verified,
        "network_request_count": requests,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "runner_invocation_count": 0,
    }


def result_summary(count=1, new=1):
    return {
        "status": "DESCRIPTIVE_NO_EARLY_SUCCESS",
        "episode_receipt_count": count,
        "result_count": count,
        "index_count": count,
        "new_result_count": new,
        "new_index_count": new,
        "market_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "state_write_count": 0,
        "runner_invocation_count": 0,
    }


class ChallengerCohortEvidenceMaintenanceTests(unittest.TestCase):
    def maintain(self, *, observer, acquirer, publisher):
        return maintain_challenger_cohort_evidence(
            cohort_plan_path=Path("/plans/cohort.json"),
            economic_plan_path=Path("/plans/economic.json"),
            episode_receipt_output_root=Path("/output/receipts"),
            install_receipt_path=Path("/trust/install.json"),
            contract_path=Path("/trust/contract.json"),
            plist_path=Path("/trust/agent.plist"),
            archive_output_root=Path("/output/archives"),
            result_output_root=Path("/output/results"),
            observed_at=OBSERVED,
            transport=Transport(),
            observer=observer,
            archive_acquirer=acquirer,
            result_publisher=publisher,
        )

    def test_no_completed_episode_is_zero_request_no_result_noop(self):
        calls = []

        def observer(**kwargs):
            calls.append(("receipt", kwargs))
            self.assertEqual(kwargs["clock"](), OBSERVED_TEXT)
            return receipt_summary()

        def acquirer(**kwargs):
            calls.append(("archive", kwargs))
            self.assertEqual(kwargs["observed_at"], OBSERVED_TEXT)
            return archive_summary(
                "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
                receipts=0,
                required=0,
                verified=0,
            )

        def publisher(**_kwargs):
            raise AssertionError("result publisher must be gated")

        summary = self.maintain(
            observer=observer, acquirer=acquirer, publisher=publisher
        )
        self.assertEqual(
            summary["status"], "COHORT_EVIDENCE_NO_COMPLETED_EPISODES"
        )
        self.assertEqual([item[0] for item in calls], ["receipt", "archive"])
        self.assertFalse(summary["result_stage"]["executed"])
        self.assertEqual(summary["network_request_count"], 0)

    def test_pending_and_partial_archives_gate_result(self):
        for status, verified in (
            ("COHORT_DAILY_ARCHIVE_PENDING", 0),
            ("COHORT_DAILY_ARCHIVE_PARTIAL", 1),
        ):
            with self.subTest(status=status):
                calls = []

                def observer(**_kwargs):
                    calls.append("receipt")
                    return receipt_summary(2, 1)

                def acquirer(**_kwargs):
                    calls.append("archive")
                    return archive_summary(
                        status,
                        receipts=2,
                        required=2,
                        verified=verified,
                        requests=1,
                    )

                def publisher(**_kwargs):
                    calls.append("result")
                    raise AssertionError("result publisher must be gated")

                summary = self.maintain(
                    observer=observer,
                    acquirer=acquirer,
                    publisher=publisher,
                )
                self.assertEqual(
                    summary["status"],
                    "COHORT_EVIDENCE_WAITING_ARCHIVES",
                )
                self.assertEqual(calls, ["receipt", "archive"])
                self.assertEqual(summary["network_request_count"], 1)

    def test_complete_archives_publish_results_in_fixed_order(self):
        calls = []

        def observer(**kwargs):
            calls.append(("receipt", kwargs))
            return receipt_summary(1, 1)

        def acquirer(**kwargs):
            calls.append(("archive", kwargs))
            return archive_summary(
                "COHORT_DAILY_ARCHIVE_COMPLETE",
                receipts=1,
                required=1,
                verified=1,
                requests=2,
            )

        def publisher(**kwargs):
            calls.append(("result", kwargs))
            return result_summary()

        summary = self.maintain(
            observer=observer, acquirer=acquirer, publisher=publisher
        )
        self.assertEqual(
            [item[0] for item in calls],
            ["receipt", "archive", "result"],
        )
        self.assertEqual(
            summary["status"],
            "COHORT_EVIDENCE_MAINTAINED_DESCRIPTIVE_NO_EARLY_SUCCESS",
        )
        self.assertEqual(summary["network_request_count"], 2)
        self.assertEqual(summary["result_stage"]["new_result_count"], 1)
        self.assertEqual(
            calls[0][1]["receipt_output_root"],
            calls[1][1]["episode_receipt_output_root"],
        )
        self.assertEqual(
            calls[1][1]["archive_output_root"],
            calls[2][1]["archive_output_root"],
        )

    def test_receipt_failure_prevents_later_phases(self):
        calls = []

        def observer(**_kwargs):
            calls.append("receipt")
            raise RuntimeError("continuity failed")

        def forbidden(**_kwargs):
            calls.append("forbidden")
            return {}

        with self.assertRaisesRegex(RuntimeError, "continuity failed"):
            self.maintain(
                observer=observer,
                acquirer=forbidden,
                publisher=forbidden,
            )
        self.assertEqual(calls, ["receipt"])

    def test_archive_failure_prevents_result(self):
        calls = []

        def observer(**_kwargs):
            calls.append("receipt")
            return receipt_summary(1)

        def acquirer(**_kwargs):
            calls.append("archive")
            raise RuntimeError("archive failed")

        def publisher(**_kwargs):
            calls.append("result")
            return result_summary()

        with self.assertRaisesRegex(RuntimeError, "archive failed"):
            self.maintain(
                observer=observer,
                acquirer=acquirer,
                publisher=publisher,
            )
        self.assertEqual(calls, ["receipt", "archive"])

    def test_unknown_or_nonzero_security_summary_fails_closed(self):
        cases = [
            (
                lambda: dict(
                    receipt_summary(),
                    status="COHORT_UNREGISTERED_SUCCESS",
                ),
                lambda: archive_summary(
                    "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
                    receipts=0,
                    required=0,
                    verified=0,
                ),
                "RECEIPT_SUMMARY_INVALID",
            ),
            (
                lambda: receipt_summary(1),
                lambda: dict(
                    archive_summary(
                        "COHORT_DAILY_ARCHIVE_PENDING",
                        receipts=1,
                        required=1,
                        verified=0,
                    ),
                    strategy_state_write_count=1,
                ),
                "ARCHIVE_SUMMARY_INVALID",
            ),
        ]
        for receipt_factory, archive_factory, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    ChallengerCohortEvidenceMaintenanceError, message
                ):
                    self.maintain(
                        observer=lambda **_kwargs: receipt_factory(),
                        acquirer=lambda **_kwargs: archive_factory(),
                        publisher=lambda **_kwargs: result_summary(),
                    )

    def test_result_count_mismatch_or_market_request_fails_closed(self):
        for mutation in (
            {"result_count": 0},
            {"market_request_count": 1},
            {"status": "PASS"},
        ):
            with self.subTest(mutation=mutation):
                def result(**_kwargs):
                    return dict(result_summary(), **mutation)

                with self.assertRaisesRegex(
                    ChallengerCohortEvidenceMaintenanceError,
                    "RESULT_SUMMARY_INVALID",
                ):
                    self.maintain(
                        observer=lambda **_kwargs: receipt_summary(1),
                        acquirer=lambda **_kwargs: archive_summary(
                            "COHORT_DAILY_ARCHIVE_COMPLETE",
                            receipts=1,
                            required=1,
                            verified=1,
                        ),
                        publisher=result,
                    )

    def test_naive_clock_is_rejected_before_any_phase(self):
        called = []
        with self.assertRaisesRegex(
            ChallengerCohortEvidenceMaintenanceError, "TIME_INVALID"
        ):
            maintain_challenger_cohort_evidence(
                cohort_plan_path=Path("/plans/cohort.json"),
                economic_plan_path=Path("/plans/economic.json"),
                episode_receipt_output_root=Path("/output/receipts"),
                install_receipt_path=Path("/trust/install.json"),
                contract_path=Path("/trust/contract.json"),
                plist_path=Path("/trust/agent.plist"),
                archive_output_root=Path("/output/archives"),
                result_output_root=Path("/output/results"),
                observed_at=datetime(2026, 7, 31),
                transport=Transport(),
                observer=lambda **_kwargs: called.append(True),
            )
        self.assertEqual(called, [])


class ChallengerCohortEvidenceMaintenanceCLITests(unittest.TestCase):
    def test_help_has_only_fixed_paths_and_no_selectors(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(maintenance_main(["--help"]), 0)
        help_text = output.getvalue()
        for required in (
            "--cohort-plan-path",
            "--economic-plan-path",
            "--episode-receipt-output-root",
            "--install-receipt-path",
            "--contract-path",
            "--plist-path",
            "--archive-output-root",
            "--result-output-root",
        ):
            self.assertIn(required, help_text)
        for forbidden in (
            "--clock",
            "--state",
            "--episode-id",
            "--date",
            "--url",
            "--symbol",
            "--price",
            "--pnl",
            "--stage",
            "--retry",
        ):
            self.assertNotIn(forbidden, help_text)

    def test_cli_no_completed_uses_owner_roots_and_one_clock(self):
        observed_calls = []
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            receipt_root = base / "receipts"
            receipt_root.mkdir(mode=0o755)
            archive_root = base / "archives"
            result_root = base / "results"

            def observer(**kwargs):
                observed_calls.append(kwargs["clock"]())
                return receipt_summary()

            output = io.StringIO()
            with redirect_stdout(output):
                code = maintenance_main(
                    [
                        "--cohort-plan-path",
                        "/plans/cohort.json",
                        "--economic-plan-path",
                        "/plans/economic.json",
                        "--episode-receipt-output-root",
                        str(receipt_root),
                        "--install-receipt-path",
                        "/trust/install.json",
                        "--contract-path",
                        "/trust/contract.json",
                        "--plist-path",
                        "/trust/agent.plist",
                        "--archive-output-root",
                        str(archive_root),
                        "--result-output-root",
                        str(result_root),
                    ],
                    clock=lambda: OBSERVED,
                    transport=Transport(),
                    observer=observer,
                    archive_acquirer=lambda **_kwargs: archive_summary(
                        "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
                        receipts=0,
                        required=0,
                        verified=0,
                    ),
                    result_publisher=lambda **_kwargs: self.fail(
                        "result publisher must be gated"
                    ),
                    allowed_output_base=base,
                )
            self.assertEqual(code, 0)
            self.assertEqual(observed_calls, [OBSERVED_TEXT])
            self.assertIn(
                '"status":"COHORT_EVIDENCE_NO_COMPLETED_EPISODES"',
                output.getvalue(),
            )
            self.assertFalse(archive_root.exists())
            self.assertFalse(result_root.exists())

    def test_cli_rejects_overlapping_roots_before_phases(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "evidence"
            root.mkdir(mode=0o700)
            error = io.StringIO()
            with redirect_stderr(error):
                code = maintenance_main(
                    [
                        "--cohort-plan-path",
                        "/plans/cohort.json",
                        "--economic-plan-path",
                        "/plans/economic.json",
                        "--episode-receipt-output-root",
                        str(root),
                        "--install-receipt-path",
                        "/trust/install.json",
                        "--contract-path",
                        "/trust/contract.json",
                        "--plist-path",
                        "/trust/agent.plist",
                        "--archive-output-root",
                        str(root),
                        "--result-output-root",
                        str(base / "results"),
                    ],
                    allowed_output_base=base,
                )
            self.assertEqual(code, 1)
            self.assertIn("ROOT_OVERLAP", error.getvalue())

    def test_cli_source_has_no_runner_broker_order_or_evaluator_import(self):
        source = (
            Path(__file__).parents[1]
            / "src"
            / "crypto_quant"
            / "challenger_cohort_evidence_maintenance_cli.py"
        ).read_text()
        for forbidden in (
            "challenger_forward_runner",
            "kickstart",
            "bootstrap",
            "Broker",
            "credential",
            "order_submission",
            "challenger_cohort_cumulative_evaluation",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
