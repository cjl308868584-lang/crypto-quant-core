import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
from urllib.request import ProxyHandler

from crypto_quant.capture_cli import main
from crypto_quant.contemporaneous_capture import (
    CaptureError,
    _public_market_opener,
    _read_bounded,
    capture_snapshot_attestation_hash,
    capture_snapshot_reasons,
)
from tests.test_contemporaneous_capture import FakeTransport, _responses


class _Stream:
    def __init__(self, payload):
        self.payload = payload
        self.offset = 0

    def read(self, amount):
        result = self.payload[self.offset:self.offset + amount]
        self.offset += len(result)
        return result


class CaptureTransportTests(unittest.TestCase):
    def test_production_opener_explicitly_disables_environment_proxies(self):
        with mock.patch.dict(
            "os.environ",
            {"HTTPS_PROXY": "http://credential@example.invalid:8080"},
        ):
            opener = _public_market_opener()
        self.assertFalse(
            any(
                isinstance(handler, ProxyHandler)
                for handler in opener.handlers
            )
        )
        self.assertEqual(len(opener.handle_open["https"]), 1)

    def test_response_reader_fails_before_accepting_oversized_body(self):
        with self.assertRaisesRegex(CaptureError, "CAPTURE_RESPONSE_TOO_LARGE"):
            _read_bounded(_Stream(b"x" * (2 * 1024 * 1024 + 1)))


class CaptureCliTests(unittest.TestCase):
    def _clock(self):
        return lambda: "2026-04-01T00:01:00.300Z"

    def test_structured_cli_writes_replayable_research_only_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = main(
                    [
                        "--symbol", "ETHUSDT",
                        "--output-root", directory,
                        "--session-id", "cli-smoke",
                    ],
                    transport=FakeTransport(_responses()),
                    clock=self._clock(),
                )
            self.assertEqual(result, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(
                summary["pit_eligibility"],
                "CONTEMPORANEOUS_RESEARCH_ONLY",
            )
            artifact = Path(summary["artifact_path"])
            self.assertTrue(artifact.is_file())
            snapshot = json.loads(artifact.read_text(encoding="utf-8"))
            anchor = capture_snapshot_attestation_hash(snapshot)
            self.assertEqual(anchor, summary["snapshot_attestation_hash"])
            self.assertEqual(
                capture_snapshot_reasons(
                    snapshot,
                    trusted_snapshot_attestation_hashes=[anchor],
                ),
                (),
            )

    def test_identical_session_is_idempotent_and_conflict_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = [
                "--symbol", "ETHUSDT",
                "--output-root", directory,
                "--session-id", "same-session",
            ]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        arguments,
                        transport=FakeTransport(_responses()),
                        clock=self._clock(),
                    ),
                    0,
                )
            artifact = Path(directory) / "market-data" / "same-session.json"
            original = artifact.read_bytes()
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(
                        arguments,
                        transport=FakeTransport(_responses()),
                        clock=self._clock(),
                    ),
                    0,
                )
            self.assertFalse(json.loads(stdout.getvalue())["created"])
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(
                        arguments,
                        transport=FakeTransport(
                            _responses(kline_close="2005.00")
                        ),
                        clock=self._clock(),
                    ),
                    1,
                )
            self.assertEqual(artifact.read_bytes(), original)

    def test_cli_has_no_url_header_key_account_or_order_arguments(self):
        for forbidden in (
            "--url", "--header", "--api-key", "--account", "--order"
        ):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
