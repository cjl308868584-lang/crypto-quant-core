"""Boundary tests for the fixed-path System Paper evaluation CLI."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import ast
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from crypto_quant.canonical import canonical_json
from crypto_quant.system_paper_evaluation import SystemPaperEvaluationError
from crypto_quant.system_paper_evaluation_cli import main


class SystemPaperEvaluationCliTests(unittest.TestCase):
    def evaluator_patch(self, evaluator):
        return patch(
            "crypto_quant.system_paper_evaluation_cli._evaluate",
            new=evaluator,
        )

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

    def assert_argument_failure(self, argv):
        status, stdout, stderr = self.invoke(argv)
        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertLessEqual(len(stderr.encode("utf-8")), 512)
        self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))
        self.assertEqual(
            json.loads(stderr)["reason_code"],
            "SYSTEM_PAPER_EVALUATION_CLI_ARGUMENT_INVALID",
        )

    def test_parser_rejects_help_and_unknown_help_without_success_output(self):
        for argv in (["--help"], ["-h"], ["--unknown", "x", "--help"]):
            with self.subTest(argv=argv):
                self.assert_argument_failure(argv)

    def test_parser_rejects_each_forbidden_selector_and_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.arguments(Path(directory))
            for forbidden in (
                "--clock", "--date", "--slot", "--pnl", "--fee", "--price",
                "--return", "--label", "--threshold", "--result-id", "--filename",
                "--probe",
            ):
                with self.subTest(forbidden=forbidden):
                    self.assert_argument_failure(
                        arguments + [forbidden, "operator-value"]
                    )

            relative = list(arguments)
            relative[1] = "plan.json"
            status, stdout, stderr = self.invoke(relative)
            self.assertEqual((status, stdout), (1, ""))
            self.assertEqual(
                json.loads(stderr)["reason_code"],
                "SYSTEM_PAPER_EVALUATION_CLI_PATH_INVALID",
            )

    def test_parser_requires_each_path_once_and_allows_equals_syntax(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.arguments(Path(directory))
            self.assert_argument_failure(arguments[:-2])
            self.assert_argument_failure(arguments + ["--plan-path", "/tmp/other"])

            equals_arguments = [
                f"{arguments[index]}={arguments[index + 1]}"
                for index in range(0, len(arguments), 2)
            ]
            evaluator = Mock(return_value={"status": "SYSTEM_PAPER_GATE_PASS"})
            with self.evaluator_patch(evaluator):
                status, stdout, stderr = self.invoke(equals_arguments)

        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(
            json.loads(stdout)["status"], "SYSTEM_PAPER_GATE_PASS"
        )
        self.assertEqual(evaluator.call_count, 1)

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
        evaluator = Mock(return_value=result)
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator):
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
        evaluator = Mock(
            side_effect=SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_COHORT_INCOMPLETE"
            )
        )
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator):
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
        evaluator = Mock(return_value={"invalid": object()})
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator):
            status, stdout, stderr = self.invoke(self.arguments(Path(directory)))

        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertLessEqual(len(stderr.encode("utf-8")), 512)
        self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))
        self.assertEqual(
            json.loads(stderr)["reason_code"], "SYSTEM_PAPER_EVALUATION_CLI_FAILED"
        )

    def test_recursive_evaluator_result_uses_the_failure_envelope(self):
        loop = []
        loop.append(loop)
        evaluator = Mock(return_value={"loop": loop})
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator):
            status, stdout, stderr = self.invoke(self.arguments(Path(directory)))

        self.assertEqual((status, stdout), (1, ""))
        self.assertEqual(len(stderr.splitlines()), 1)
        self.assertLessEqual(len(stderr.encode("utf-8")), 512)
        self.assertEqual(canonical_json(json.loads(stderr)), stderr.rstrip("\n"))

    def test_stdout_write_broken_pipe_uses_the_failure_envelope(self):
        class BrokenWriter:
            def write(self, _value):
                raise BrokenPipeError()

            def flush(self):
                return None

        evaluator = Mock(return_value={"status": "SYSTEM_PAPER_GATE_PASS"})
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator), patch(
            "crypto_quant.system_paper_evaluation_cli.sys.stdout", BrokenWriter()
        ), patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
            status = main(self.arguments(Path(directory)))

        self.assertEqual(status, 1)
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertEqual(canonical_json(json.loads(stderr.getvalue())), stderr.getvalue().rstrip("\n"))

    def test_stdout_flush_broken_pipe_uses_the_failure_envelope(self):
        class BrokenFlusher:
            def write(self, value):
                return len(value)

            def flush(self):
                raise BrokenPipeError()

        evaluator = Mock(return_value={"status": "SYSTEM_PAPER_GATE_PASS"})
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator), patch(
            "crypto_quant.system_paper_evaluation_cli.sys.stdout", BrokenFlusher()
        ), patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
            status = main(self.arguments(Path(directory)))

        self.assertEqual(status, 1)
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertEqual(canonical_json(json.loads(stderr.getvalue())), stderr.getvalue().rstrip("\n"))

    def test_stdout_small_writes_emit_the_complete_canonical_result(self):
        class ChunkingWriter:
            def __init__(self):
                self.body = ""
                self._sizes = iter((1, 2, 7))

            def write(self, value):
                try:
                    size = next(self._sizes)
                except StopIteration:
                    size = 1
                accepted = min(size, len(value))
                self.body += value[:accepted]
                return accepted

            def flush(self):
                return None

        evaluator = Mock(return_value={"status": "SYSTEM_PAPER_GATE_PASS"})
        stdout = ChunkingWriter()
        stderr = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(evaluator), patch(
            "crypto_quant.system_paper_evaluation_cli.sys.stdout", stdout
        ), patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
            status = main(self.arguments(Path(directory)))

        self.assertEqual((status, stderr.getvalue()), (0, ""))
        self.assertEqual(
            stdout.body,
            canonical_json({"status": "SYSTEM_PAPER_GATE_PASS"}) + "\n",
        )

    def test_stderr_small_writes_emit_the_complete_canonical_error(self):
        class ChunkingWriter:
            def __init__(self):
                self.body = ""
                self._sizes = iter((1, 3, 2))

            def write(self, value):
                try:
                    size = next(self._sizes)
                except StopIteration:
                    size = 1
                accepted = min(size, len(value))
                self.body += value[:accepted]
                return accepted

            def flush(self):
                return None

        stderr = ChunkingWriter()
        with patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
            status = main(["--plan-path", "relative"])

        self.assertEqual(status, 1)
        self.assertEqual(
            stderr.body,
            canonical_json(
                {
                    "error": "SYSTEM_PAPER_EVALUATION_CLI_INVOCATION_FAILED",
                    "reason_code": "SYSTEM_PAPER_EVALUATION_CLI_ARGUMENT_INVALID",
                }
            )
            + "\n",
        )

    def test_invalid_write_counts_fail_without_looping(self):
        class InvalidWriter:
            def __init__(self, result):
                self.result = result

            def write(self, value):
                return len(value) + 1 if self.result == "too_many" else self.result

            def flush(self):
                return None

        evaluator = Mock(return_value={"status": "SYSTEM_PAPER_GATE_PASS"})
        for result in (0, None, -1, "too_many"):
            with self.subTest(result=result):
                stderr = io.StringIO()
                with tempfile.TemporaryDirectory() as directory, self.evaluator_patch(
                    evaluator
                ), patch(
                    "crypto_quant.system_paper_evaluation_cli.sys.stdout",
                    InvalidWriter(result),
                ), patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
                    status = main(self.arguments(Path(directory)))

                self.assertEqual(status, 1)
                self.assertEqual(len(stderr.getvalue().splitlines()), 1)
                self.assertEqual(
                    canonical_json(json.loads(stderr.getvalue())),
                    stderr.getvalue().rstrip("\n"),
                )

    def test_closed_stderr_never_escapes_the_failure_boundary(self):
        stderr = io.StringIO()
        stderr.close()

        with patch("crypto_quant.system_paper_evaluation_cli.sys.stderr", stderr):
            status = main(["--plan-path", "relative"])

        self.assertEqual(status, 1)

    def test_cli_import_does_not_load_operational_authority_modules(self):
        source_root = str(Path(__file__).parents[1] / "src")
        environment = dict(os.environ, PYTHONPATH=source_root)
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import crypto_quant.system_paper_evaluation_cli; "
                "blocked=('network','scheduler','runtime','broker','order','runner',"
                "'urllib','socket','http','httpx','requests','aiohttp'); "
                "raise SystemExit(any(any(token in name.lower() for token in blocked) "
                "for name in sys.modules))",
            ],
            capture_output=True,
            check=False,
            env=environment,
            text=True,
        )

        self.assertEqual((process.returncode, process.stdout, process.stderr), (0, "", ""))

    def test_cli_source_has_no_forbidden_direct_import_or_operational_call(self):
        source = Path(__file__).parents[1] / "src" / "crypto_quant" / "system_paper_evaluation_cli.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        top_level_modules = {
            node.module or ""
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        top_level_modules.update(
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        forbidden = (
            "network", "runner", "scheduler", "runtime", "broker", "order",
            "urllib", "socket", "http", "httpx", "requests", "aiohttp",
        )
        self.assertFalse(
            [
                module
                for module in top_level_modules
                if any(token in module.lower() for token in forbidden)
            ]
        )
        call_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertFalse(
            {
                "run_due_system_paper_slot",
                "run_system_paper_slot",
                "SystemPaperBroker",
                "Order",
            }
            & call_names
        )


if __name__ == "__main__":
    unittest.main()
