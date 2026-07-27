import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from crypto_quant.offline_paper import (
    PublicPaperHttpResponse,
    offline_paper_run_reasons,
)
from crypto_quant.offline_paper_cli import main
from tests.test_offline_paper import FakeTransport, valid_capture


class OfflinePaperCliTests(unittest.TestCase):
    def _inputs(self):
        capture, _ = valid_capture()
        responses = [
            PublicPaperHttpResponse(
                status=receipt["status"],
                final_url=receipt["final_url"],
                headers={"Date": receipt["http_date_or_null"]},
                body=receipt["response_body_utf8"].encode(),
                request_started_at=receipt["request_started_at"],
                response_received_at=receipt["response_received_at"],
            )
            for receipt in capture.receipts
        ]
        return FakeTransport(responses), lambda: "2026-07-27T12:00:02.000Z"

    def test_cli_atomically_publishes_replayable_paper_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            transport, clock = self._inputs()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "--symbol", "ETHUSDT",
                        "--output-root", directory,
                        "--run-id", "cli-offline-paper",
                    ],
                    transport=transport,
                    clock=clock,
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            artifact = Path(summary["artifact_path"])
            self.assertEqual(artifact.parent.name, "paper")
            run = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(
                offline_paper_run_reasons(
                    run, summary["trusted_attestation_hash"]
                ),
                (),
            )
            self.assertEqual(
                summary["profitability_eligibility"],
                "INSUFFICIENT_DURATION_AND_AI",
            )

    def test_same_run_is_idempotent_and_conflict_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "--symbol", "ETHUSDT",
                "--output-root", directory,
                "--run-id", "same-paper-run",
            ]
            transport, clock = self._inputs()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(arguments, transport=transport, clock=clock), 0
                )
            artifact = Path(directory) / "paper" / "same-paper-run.json"
            original = artifact.read_bytes()
            transport, clock = self._inputs()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(arguments, transport=transport, clock=clock), 0
                )
            self.assertFalse(json.loads(stdout.getvalue())["created"])
            changed, clock = self._inputs()
            changed.responses[0] = type(changed.responses[0])(
                **{
                    **changed.responses[0].__dict__,
                    "body": changed.responses[0].body.replace(
                        b'"2200"', b'"2300"'
                    ),
                }
            )
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(arguments, transport=changed, clock=clock), 1
                )
            self.assertEqual(artifact.read_bytes(), original)

    def test_cli_exposes_no_account_credential_or_order_arguments(self):
        for forbidden in (
            "--url",
            "--header",
            "--api-key",
            "--secret",
            "--account",
            "--order",
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
