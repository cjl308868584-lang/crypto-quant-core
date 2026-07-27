import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_quant.research_corpus_cli import main


class ResearchCorpusCliTests(unittest.TestCase):
    def test_plan_and_verify_plan_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "plan.json"
            self.assertEqual(main(["plan", "--output", str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                main(["verify-plan", "--input", str(output)]),
                0,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["item_count"], 168)

    def test_run_passes_only_bounded_local_arguments(self):
        result = {
            "snapshot_id": "snapshot",
            "snapshot_hash": "a" * 64,
            "summary": {"succeeded_item_count": 0},
            "research_training_readiness": "NOT_READY_INCOMPLETE_OR_INVALID",
            "formal_pit_eligibility": "INELIGIBLE_ARCHIVE_REPLAY",
        }
        with patch(
            "crypto_quant.research_corpus_cli.run_historical_research_corpus",
            return_value=result,
        ) as run:
            code = main(
                [
                    "run",
                    "--state",
                    "/tmp/corpus-state.sqlite3",
                    "--output-root",
                    "/tmp/corpus-output",
                    "--worker-id",
                    "worker-a",
                    "--max-items",
                    "4",
                ]
            )
        self.assertEqual(code, 0)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["worker_id"], "worker-a")
        self.assertEqual(kwargs["max_items"], 4)
        self.assertNotIn("transport", kwargs)
        self.assertNotIn("url", kwargs)
        self.assertNotIn("credential", kwargs)

    def test_parser_rejects_url_credentials_proxy_and_command_overrides(self):
        root = Path(__file__).parents[1]
        base = [
            sys.executable,
            "-m",
            "crypto_quant.research_corpus_cli",
            "run",
            "--state",
            "/tmp/state.sqlite3",
            "--output-root",
            "/tmp/output",
            "--worker-id",
            "worker-a",
        ]
        for flag, value in (
            ("--url", "https://example.com"),
            ("--api-key", "secret"),
            ("--proxy", "http://example.com"),
            ("--command", "echo"),
        ):
            with self.subTest(flag=flag):
                completed = subprocess.run(
                    base + [flag, value],
                    cwd=root,
                    env={"PYTHONPATH": str(root / "src")},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
