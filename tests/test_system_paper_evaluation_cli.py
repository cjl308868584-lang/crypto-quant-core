"""Boundary tests for the fixed-path System Paper evaluation CLI."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.system_paper_evaluation import SystemPaperEvaluationError
from crypto_quant.system_paper_evaluation_cli import main


class SystemPaperEvaluationCliTests(unittest.TestCase):
    def arguments(self, base: Path):
        return [
            "--plan-path", str(base / "plan.json"),
            "--start-receipt-path", str(base / "start.json"),
            "--install-receipt-path", str(base / "install.json"),
            "--contract-path", str(base / "contract.json"),
            "--slot-root", str(base / "slots"),
            "--runtime-root", str(base / "runtime"),
            "--output-root", str(base / "output"),
        ]

    def invoke(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(argv)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_parser_exposes_exactly_seven_path_options(self):
        status, stdout, stderr = self.invoke(["--help"])

        self.assertEqual((status, stderr), (0, ""))
        for allowed in (
            "--plan-path", "--start-receipt-path", "--install-receipt-path",
            "--contract-path", "--slot-root", "--runtime-root", "--output-root",
        ):
            with self.subTest(allowed=allowed):
                self.assertIn(allowed, stdout)
        for forbidden in (
            "--clock", "--date", "--pnl", "--fee", "--price",
            "--return", "--label", "--threshold", "--result-id", "--filename",
            "--probe",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, stdout)

    def test_parser_rejects_each_forbidden_selector_and_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.arguments(Path(directory))
            for forbidden in (
                "--clock", "--date", "--slot", "--pnl", "--fee", "--price",
                "--return", "--label", "--threshold", "--result-id", "--filename",
                "--probe",
            ):
                with self.subTest(forbidden=forbidden):
                    status, stdout, stderr = self.invoke(
                        arguments + [forbidden, "operator-value"]
                    )
                    self.assertEqual((status, stdout), (1, ""))
                    self.assertEqual(len(stderr.splitlines()), 1)
                    self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))
                    self.assertEqual(
                        json.loads(stderr)["reason_code"],
                        "SYSTEM_PAPER_EVALUATION_CLI_ARGUMENT_INVALID",
                    )

            relative = list(arguments)
            relative[1] = "plan.json"
            status, stdout, stderr = self.invoke(relative)
            self.assertEqual((status, stdout), (1, ""))
            self.assertEqual(
                json.loads(stderr)["reason_code"],
                "SYSTEM_PAPER_EVALUATION_CLI_PATH_INVALID",
            )

    def test_pending_result_is_one_canonical_stdout_line(self):
        result = {
            "status": "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL",
            "observed_at": "2026-08-04T00:00:00.000Z",
        }
        self.assert_stdout_result(result)

    def test_pass_result_is_one_canonical_stdout_line(self):
        self.assert_stdout_result({"status": "SYSTEM_PAPER_GATE_PASS", "result_id": "fixed"})

    def test_did_not_pass_result_is_one_canonical_stdout_line(self):
        self.assert_stdout_result({"status": "SYSTEM_PAPER_GATE_DID_NOT_PASS", "result_id": "fixed"})

    def test_inconclusive_result_is_one_canonical_stdout_line(self):
        self.assert_stdout_result({"status": "INCONCLUSIVE_INSUFFICIENT_EVIDENCE", "result_id": "fixed"})

    def assert_stdout_result(self, result):
        with tempfile.TemporaryDirectory() as directory, patch(
            "crypto_quant.system_paper_evaluation_cli.evaluate_system_paper",
            return_value=result,
        ) as evaluator:
            status, stdout, stderr = self.invoke(self.arguments(Path(directory)))

        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(stdout, canonical_json(result) + "\n")
        self.assertEqual(len(stdout.splitlines()), 1)
        self.assertEqual(canonical_json(json.loads(stdout)), stdout.rstrip("\n"))
        self.assertEqual(
            evaluator.call_args.kwargs,
            {
                "plan_path": Path(directory) / "plan.json",
                "start_receipt_path": Path(directory) / "start.json",
                "install_receipt_path": Path(directory) / "install.json",
                "contract_path": Path(directory) / "contract.json",
                "slot_root": Path(directory) / "slots",
                "runtime_root": Path(directory) / "runtime",
                "output_root": Path(directory) / "output",
            },
        )

    def test_structured_evaluation_failure_is_bounded_canonical_stderr(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "crypto_quant.system_paper_evaluation_cli.evaluate_system_paper",
            side_effect=SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
            ),
        ):
            status, stdout, stderr = self.invoke(self.arguments(Path(directory)))

        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertLessEqual(len(stderr.encode("utf-8")), 512)
        self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))
        self.assertEqual(
            json.loads(stderr),
            {
                "error": "SYSTEM_PAPER_EVALUATION_CLI_INVOCATION_FAILED",
                "reason_code": "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE",
            },
        )

    def test_unserializable_evaluator_result_uses_the_failure_envelope(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "crypto_quant.system_paper_evaluation_cli.evaluate_system_paper",
            return_value={"invalid": object()},
        ):
            status, stdout, stderr = self.invoke(self.arguments(Path(directory)))

        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertLessEqual(len(stderr.encode("utf-8")), 512)
        self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))
        self.assertEqual(
            json.loads(stderr)["reason_code"], "SYSTEM_PAPER_EVALUATION_CLI_FAILED"
        )


if __name__ == "__main__":
    unittest.main()
