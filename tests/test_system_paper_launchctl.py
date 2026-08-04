"""Strict bounded parsing tests for macOS launchctl print evidence."""

from pathlib import Path
import unittest

from crypto_quant.system_paper_launchctl import (
    SystemPaperLaunchctlParseError,
    parse_system_paper_launchctl_print,
)


FIXTURES = Path(__file__).parent / "fixtures" / "launchctl"


class SystemPaperLaunchctlParserTests(unittest.TestCase):
    def fixture(self, name):
        return (FIXTURES / name).read_bytes()

    def expected(self, *, runs, last_exit_status):
        root = "/Users/test/Library/Application Support/CryptoQuant/system-paper-v1"
        snapshot = root + "/deployment/system-paper-snapshots/tree"
        return {
            "label": "local.crypto-quant.system-paper-v1",
            "service": "gui/501/local.crypto-quant.system-paper-v1",
            "path": "/Users/test/Library/LaunchAgents/local.crypto-quant.system-paper-v1.plist",
            "program": "/usr/bin/python3",
            "arguments": [
                "/usr/bin/python3",
                "-m",
                "crypto_quant.system_paper_runtime_cli",
                "--state-path",
                root + "/state/system-paper.sqlite",
                "--output-root",
                root + "/artifacts",
            ],
            "working_directory": snapshot,
            "environment": {
                "PYTHONPATH": snapshot + "/src",
                "XPC_SERVICE_NAME": "local.crypto-quant.system-paper-v1",
            },
            "runs": runs,
            "state": "not running",
            "last_exit_status": last_exit_status,
        }

    def test_parses_not_running_and_first_success_fixtures_exactly(self):
        self.assertEqual(
            parse_system_paper_launchctl_print(
                self.fixture("system-paper-not-running.txt")
            ),
            self.expected(runs=0, last_exit_status=None),
        )
        self.assertEqual(
            parse_system_paper_launchctl_print(
                self.fixture("system-paper-first-success.txt")
            ),
            self.expected(runs=1, last_exit_status=0),
        )

    def test_rejects_duplicate_named_field_and_missing_argument(self):
        original = self.fixture("system-paper-not-running.txt")
        duplicate = original.replace(
            b"\tpath = ", b"\tpath = /wrong\n\tpath = ", 1
        )
        duplicate_path_block = original.replace(
            b"\tpath = ", b"\tpath = {\n\t\tignored = 1\n\t}\n\tpath = ", 1
        )
        duplicate_environment_scalar = original.replace(
            b"\tenvironment = {\n",
            b"\tenvironment = ignored\n\tenvironment = {\n",
            1,
        )
        duplicate_arguments_scalar = original.replace(
            b"\targuments = {\n",
            b"\targuments = ignored\n\targuments = {\n",
            1,
        )
        missing = original.replace(b"\t\t--state-path\n", b"", 1)
        for data in (
            duplicate,
            duplicate_path_block,
            duplicate_environment_scalar,
            duplicate_arguments_scalar,
            missing,
        ):
            with self.subTest(data=data[:80]), self.assertRaises(
                SystemPaperLaunchctlParseError
            ):
                parse_system_paper_launchctl_print(data)

    def test_rejects_reordered_arguments_extra_environment_and_comment_injection(self):
        original = self.fixture("system-paper-not-running.txt")
        reordered = original.replace(
            b"\t\t--state-path\n\t\t/Users/test/",
            b"\t\t/Users/test/\n\t\t--state-path",
            1,
        )
        extra_environment = original.replace(
            b"\t\tXPC_SERVICE_NAME => local.crypto-quant.system-paper-v1\n\t}",
            b"\t\tXPC_SERVICE_NAME => local.crypto-quant.system-paper-v1\n"
            b"\t\tBINANCE_API_KEY => should-not-be-accepted\n\t}",
            1,
        )
        comment_injection = original.replace(
            b"\tpath = /Users/test/",
            b"\tpath = /wrong\n\t# /Users/test/",
            1,
        )
        for data in (reordered, extra_environment):
            self.assertNotEqual(data, original)
            with self.subTest(data=data[:100]), self.assertRaises(
                SystemPaperLaunchctlParseError
            ):
                parse_system_paper_launchctl_print(data)
        with self.assertRaises(SystemPaperLaunchctlParseError):
            parse_system_paper_launchctl_print(comment_injection)

    def test_rejects_displaced_fields_blocks_and_early_closing_brace(self):
        original = (FIXTURES / "system-paper-not-running.txt").read_bytes()
        displaced_path = original.replace(b"\tpath = ", b"\t\tpath = ", 1)
        displaced_duplicate = original.replace(
            b"\tpath = ", b"\t\tpath = /wrong\n\tpath = ", 1
        )
        displaced_arguments = original.replace(
            b"\targuments = {\n", b"\t\targuments = {\n", 1
        )
        early_closing = original.replace(b"\truns = 0\n", b"\t}\n\truns = 0\n", 1)
        slash_comment = original.replace(
            b"\tpath = ", b"\t// path = /wrong\n\tpath = ", 1
        )

        for data in (
            displaced_path,
            displaced_duplicate,
            displaced_arguments,
            early_closing,
            slash_comment,
        ):
            with self.subTest(data=data):
                with self.assertRaises(SystemPaperLaunchctlParseError):
                    parse_system_paper_launchctl_print(data)

    def test_rejects_duplicate_blocks_invalid_integer_oversize_and_non_utf8(self):
        original = self.fixture("system-paper-first-success.txt")
        duplicate_block = original.replace(
            b"\tenvironment = {",
            b"\targuments = {\n\t\tduplicate\n\t}\n\tenvironment = {",
            1,
        )
        invalid_integer = original.replace(b"\truns = 1", b"\truns = -1", 1)
        for data in (
            duplicate_block,
            invalid_integer,
            b"x" * (64 * 1024 + 1),
            b"\xff\xfe",
        ):
            with self.subTest(size=len(data)), self.assertRaises(
                SystemPaperLaunchctlParseError
            ):
                parse_system_paper_launchctl_print(data)


if __name__ == "__main__":
    unittest.main()
