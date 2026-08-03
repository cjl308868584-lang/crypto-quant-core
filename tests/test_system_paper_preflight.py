"""Fail-closed System Paper machine preflight evidence tests."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_preflight import (
    PublicPingHttpResponse,
    SystemPaperPreflightError,
    load_system_paper_preflight_receipt,
    run_system_paper_preflight,
)
from crypto_quant.system_paper_preflight_cli import main as preflight_main
from tests.test_runtime_health import FakeTimeTransport, fake_time_responses
import tests.test_system_paper_launchd as launchd_helpers


UTC = timezone.utc
VERIFIED_AT = "2026-08-04T05:00:00.000Z"
FIVE_GIB = 5 * 1024 * 1024 * 1024


class PreflightCommandRunner:
    def __init__(
        self,
        *,
        uid,
        sleep_minutes=0,
        service_present=False,
        domain_present=True,
    ):
        self.uid = uid
        self.sleep_minutes = sleep_minutes
        self.service_present = service_present
        self.domain_present = domain_present
        self.calls = []

    def __call__(self, argv):
        command = tuple(str(item) for item in argv)
        self.calls.append(command)
        if command == ("/bin/launchctl", "print", f"gui/{self.uid}"):
            return SimpleNamespace(
                returncode=0 if self.domain_present else 113,
                stdout="domain = gui\n" if self.domain_present else "",
                stderr="" if self.domain_present else "domain absent\n",
            )
        if command == (
            "/bin/launchctl",
            "print",
            f"gui/{self.uid}/local.crypto-quant.system-paper-v1",
        ):
            return SimpleNamespace(
                returncode=0 if self.service_present else 113,
                stdout="service present\n" if self.service_present else "",
                stderr="" if self.service_present else "Could not find service\n",
            )
        if command == ("/usr/bin/pmset", "-g", "custom"):
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "Battery Power:\n sleep 5\n"
                    f"AC Power:\n sleep {self.sleep_minutes}\n"
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=99, stdout="", stderr="unexpected")


class FakePingTransport:
    def __init__(self, *, status=200, body=b"{}"):
        self.status = status
        self.body = body
        self.calls = 0

    def get(self):
        self.calls += 1
        return PublicPingHttpResponse(
            status=self.status,
            final_url="https://data-api.binance.vision/api/v3/ping",
            headers={"Date": "Tue, 04 Aug 2026 05:00:01 GMT"},
            body=self.body,
        )


class SystemPaperPreflightTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.base = Path(self.directory.name).resolve()
        launchd = launchd_helpers.SystemPaperLaunchdTests()
        (
            self.contract_result,
            _repository,
            self.runtime_root,
            _output,
            _runner,
        ) = launchd.publish(self.base)
        self.contract_path = Path(self.contract_result["contract_path"])
        self.plist_path = Path(self.contract_result["plist_path"])
        self.home = self.base / "home"
        self.home.mkdir(mode=0o700)
        self.uid = os.getuid()

    def tearDown(self):
        self.directory.cleanup()

    def machine(self, *, hostname="test-host"):
        return {
            "uid": self.uid,
            "home": str(self.home),
            "hostname": hostname,
            "timezone": "Asia/Shanghai",
        }

    @staticmethod
    def filesystem(path):
        entry = Path(path).stat()
        return {
            "device": entry.st_dev,
            "filesystem_id": entry.st_dev,
            "free_bytes": FIVE_GIB + 1024,
            "is_local": True,
        }

    def execute(
        self,
        *,
        runner=None,
        machine=None,
        filesystem=None,
        ping=None,
        server_time=None,
        clock=None,
    ):
        command_runner = runner or PreflightCommandRunner(uid=self.uid)
        ping_transport = ping or FakePingTransport()
        result = run_system_paper_preflight(
            contract_path=self.contract_path,
            plist_path=self.plist_path,
            command_runner=command_runner,
            machine_probe=machine or self.machine,
            filesystem_probe=filesystem or self.filesystem,
            server_time_transport=server_time or FakeTimeTransport(
                fake_time_responses(
                    base=datetime(2026, 8, 4, 5, 0, 0, tzinfo=UTC)
                )
            ),
            ping_transport=ping_transport,
            clock=clock or (lambda: VERIFIED_AT),
        )
        return result, command_runner, ping_transport

    def test_verified_receipt_binds_machine_roots_power_clock_and_public_ping(self):
        result, runner, ping = self.execute()
        receipt = load_system_paper_preflight_receipt(
            receipt_path=Path(result["receipt_path"]),
            contract_path=self.contract_path,
            plist_path=self.plist_path,
            machine_probe=self.machine,
            filesystem_probe=self.filesystem,
            clock=lambda: "2026-08-04T05:20:00.000Z",
        )

        self.assertEqual(
            result["outcome"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
        )
        self.assertEqual(
            receipt["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE"
        )
        self.assertEqual(receipt["network_request_count"], 4)
        self.assertEqual(receipt["clock_probe"]["sample_count"], 3)
        self.assertEqual(receipt["ping_probe"]["request_count"], 1)
        self.assertGreaterEqual(receipt["disk"]["minimum_free_bytes"], FIVE_GIB)
        self.assertTrue(receipt["power"]["ac_sleep_safe"])
        self.assertTrue(receipt["launchd"]["login_domain_present"])
        self.assertFalse(receipt["launchd"]["service_present"])
        self.assertFalse(receipt["launchd"]["target_plist_present"])
        self.assertEqual(
            runner.calls,
            [
                ("/bin/launchctl", "print", f"gui/{self.uid}"),
                (
                    "/bin/launchctl",
                    "print",
                    f"gui/{self.uid}/local.crypto-quant.system-paper-v1",
                ),
                ("/usr/bin/pmset", "-g", "custom"),
            ],
        )
        self.assertEqual(ping.calls, 1)
        self.assertEqual(
            receipt["security_boundary"],
            {
                "production_activation_enabled": False,
                "launchctl_mutation_count": 0,
                "runtime_invocation_count": 0,
                "network_request_count": 4,
                "credential_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
            },
        )
        receipt_path = Path(result["receipt_path"])
        self.assertEqual(receipt_path.parent, self.runtime_root / "preflight-receipts")
        self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)

    def test_valid_contract_probe_failure_publishes_failed_closed_receipt(self):
        result, _runner, _ping = self.execute(
            runner=PreflightCommandRunner(uid=self.uid, sleep_minutes=30)
        )
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(result["outcome"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertIn("SYSTEM_PAPER_PREFLIGHT_AC_SLEEP_UNSAFE", receipt["failure_reasons"])
        self.assertIsNone(receipt["expires_at_or_null"])

    def test_command_transport_failure_is_bounded_failed_closed_evidence(self):
        class BrokenRunner:
            def __init__(self):
                self.calls = []

            def __call__(self, argv):
                self.calls.append(tuple(argv))
                raise OSError("command transport unavailable")

        runner = BrokenRunner()
        result, _runner, _ping = self.execute(runner=runner)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertIn(
            "SYSTEM_PAPER_PREFLIGHT_COMMAND_FAILED",
            receipt["failure_reasons"],
        )
        self.assertEqual(len(runner.calls), 3)
        self.assertTrue(
            all(
                item["returncode"] == 255
                for item in receipt["launchd"]["command_evidence"]
            )
        )

    def test_all_machine_readiness_probe_failures_are_preserved_as_evidence(self):
        class FailingTimeTransport:
            def __init__(self):
                self.calls = 0

            def get(self):
                self.calls += 1
                raise RuntimeError("time transport unavailable")

        def unsafe_filesystem(path):
            entry = Path(path).stat()
            return {
                "device": entry.st_dev,
                "filesystem_id": entry.st_dev,
                "free_bytes": 1024,
                "is_local": False,
            }

        result, runner, ping = self.execute(
            runner=PreflightCommandRunner(
                uid=self.uid,
                sleep_minutes=60,
                service_present=True,
                domain_present=False,
            ),
            filesystem=unsafe_filesystem,
            server_time=FailingTimeTransport(),
            ping=FakePingTransport(status=503, body=b""),
            clock=lambda: "2026-08-04T05:01:00.000Z",
        )
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertTrue(
            {
                "SYSTEM_PAPER_PREFLIGHT_LOGIN_DOMAIN_ABSENT",
                "SYSTEM_PAPER_PREFLIGHT_SERVICE_NOT_ABSENT",
                "SYSTEM_PAPER_PREFLIGHT_AC_SLEEP_UNSAFE",
                "SYSTEM_PAPER_PREFLIGHT_NETWORK_FILESYSTEM",
                "SYSTEM_PAPER_PREFLIGHT_DISK_SPACE_INSUFFICIENT",
                "SYSTEM_PAPER_PREFLIGHT_CLOCK_PROBE_FAILED",
                "SYSTEM_PAPER_PREFLIGHT_PING_RESPONSE_INVALID",
                "SYSTEM_PAPER_PREFLIGHT_NETWORK_COUNT_INVALID",
            }.issubset(set(receipt["failure_reasons"]))
        )
        self.assertEqual(len(runner.calls), 3)
        self.assertEqual(ping.calls, 1)
        self.assertEqual(receipt["network_request_count"], 2)

    def test_invalid_contract_or_plist_creates_zero_preflight_files(self):
        self.contract_path.write_text("{}", encoding="utf-8")
        preflight_root = self.runtime_root / "preflight-receipts"
        with self.assertRaises(Exception):
            self.execute()
        self.assertFalse(preflight_root.exists())

    def test_loader_rejects_expiry_machine_drift_root_replacement_and_duplicate(self):
        result, _runner, _ping = self.execute()
        receipt_path = Path(result["receipt_path"])
        with self.assertRaisesRegex(SystemPaperPreflightError, "EXPIRED"):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:31:00.000Z",
            )
        with self.assertRaisesRegex(SystemPaperPreflightError, "MACHINE"):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=lambda: self.machine(hostname="different-host"),
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )

        old_state = self.runtime_root / "state"
        moved = self.runtime_root / "state-old"
        old_state.rename(moved)
        old_state.mkdir(mode=0o700)
        with self.assertRaisesRegex(SystemPaperPreflightError, "ROOT"):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )
        shutil.rmtree(old_state)
        moved.rename(old_state)

        duplicate = receipt_path.parent / "duplicate.json"
        duplicate.write_bytes(receipt_path.read_bytes())
        os.chmod(duplicate, 0o600)
        with self.assertRaisesRegex(SystemPaperPreflightError, "INVENTORY"):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )

    def test_rehashed_mutation_and_same_identity_conflict_fail_closed(self):
        result, _runner, _ping = self.execute()
        receipt_path = Path(result["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        receipt["power"]["ac_sleep_minutes"] = 1
        receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
        receipt_path.write_text(canonical_json(receipt), encoding="utf-8")
        with self.assertRaises(SystemPaperPreflightError):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )

    def test_exact_publication_is_idempotent_and_same_identity_conflict_is_preserved(self):
        first, _runner, _ping = self.execute()
        first_bytes = Path(first["receipt_path"]).read_bytes()
        second, _runner, _ping = self.execute()
        self.assertEqual(second, first)
        self.assertEqual(Path(first["receipt_path"]).read_bytes(), first_bytes)

        with self.assertRaisesRegex(
            SystemPaperPreflightError, "PUBLISH_CONFLICT"
        ):
            self.execute(
                runner=PreflightCommandRunner(uid=self.uid, sleep_minutes=30)
            )
        self.assertEqual(Path(first["receipt_path"]).read_bytes(), first_bytes)

    def test_cli_accepts_only_contract_and_plist_paths(self):
        expected = {
            "outcome": "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE",
            "receipt_path": "/private/example/receipt.json",
            "receipt_id": "system_paper_preflight_receipt_" + "a" * 64,
            "receipt_hash": "b" * 64,
        }
        with patch(
            "crypto_quant.system_paper_preflight_cli.run_system_paper_preflight",
            return_value=expected,
        ) as run:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = preflight_main(
                    [
                        "--contract-path",
                        str(self.contract_path),
                        "--plist-path",
                        str(self.plist_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            run.assert_called_once_with(
                contract_path=self.contract_path,
                plist_path=self.plist_path,
            )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                preflight_main(["--output-root", str(self.base)])


if __name__ == "__main__":
    unittest.main()
