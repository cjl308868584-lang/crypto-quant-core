import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from crypto_quant.paper_scheduler_cli import main
from tests.test_paper_scheduler import paper_transport


class PaperSchedulerCliTests(unittest.TestCase):
    def test_cli_publishes_cycle_and_schedule_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "--state-path", str(root / "runtime" / "paper.sqlite"),
                        "--output-root", str(root / "artifacts"),
                        "--worker-id", "cli-worker",
                    ],
                    transport=paper_transport(),
                    clock=lambda: "2026-07-27T12:05:11.000Z",
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["outcome"], "EXECUTED")
            self.assertTrue(Path(summary["artifact_path"]).is_file())
            self.assertTrue(Path(summary["schedule_snapshot_path"]).is_file())
            self.assertEqual(summary["network_request_count"], 4)

    def test_cli_has_no_time_url_account_key_or_order_overrides(self):
        for forbidden in (
            "--now",
            "--slot",
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
