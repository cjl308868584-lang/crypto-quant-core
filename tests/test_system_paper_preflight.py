"""Fail-closed System Paper machine preflight evidence tests."""

import io
import json
import os
import shutil
import sys
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
        runtime_import_stdout=None,
        runtime_import_returncode=0,
    ):
        self.uid = uid
        self.sleep_minutes = sleep_minutes
        self.service_present = service_present
        self.domain_present = domain_present
        self.runtime_import_stdout = runtime_import_stdout
        self.runtime_import_returncode = runtime_import_returncode
        self.calls = []

    def __call__(self, argv, *, cwd=None, env=None):
        command = tuple(str(item) for item in argv)
        self.calls.append(command)
        self.call_details = getattr(self, "call_details", [])
        self.call_details.append(
            (command, None if cwd is None else str(cwd), env)
        )
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
        if len(command) == 3 and command[1] == "-c":
            return SimpleNamespace(
                returncode=self.runtime_import_returncode,
                stdout=(
                    self.runtime_import_stdout
                    if self.runtime_import_stdout is not None
                    else canonical_json(
                        {
                            "package_version": "0.58.0",
                            "sys_version": sys.version,
                        }
                    )
                    + "\n"
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
        credential=None,
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
            credential_probe=credential,
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
                (
                    json.loads(self.contract_path.read_text())["python_executable"],
                    "-c",
                    "import crypto_quant, crypto_quant.system_paper_runtime_cli, json, sys; "
                    "print(json.dumps({'package_version': crypto_quant.__version__, "
                    "'sys_version': sys.version}, sort_keys=True, separators=(',', ':')))",
                ),
            ],
        )
        contract = json.loads(self.contract_path.read_text())
        self.assertEqual(
            runner.call_details[-1][1],
            contract["execution_snapshot"]["repository_root"],
        )
        self.assertEqual(
            runner.call_details[-1][2],
            {
                "PYTHONPATH": str(
                    Path(contract["execution_snapshot"]["repository_root"])
                    / "src"
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
                "LANG": "C",
                "LC_ALL": "C",
            },
        )
        self.assertEqual(
            receipt["runtime_import"],
            {
                "status": "VERIFIED",
                "package_version_or_null": "0.58.0",
                "sys_version_or_null": sys.version,
                "command_evidence": {
                    "argv": list(runner.calls[-1]),
                    "transport_status": "COMPLETED",
                    "returncode": 0,
                    "stdout_sha256": receipt["runtime_import"]["command_evidence"][
                        "stdout_sha256"
                    ],
                    "stderr_sha256": receipt["runtime_import"]["command_evidence"][
                        "stderr_sha256"
                    ],
                },
            },
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

            def __call__(self, argv, *, cwd=None, env=None):
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
        self.assertEqual(len(runner.calls), 4)
        self.assertTrue(
            all(
                item["returncode"] == 255
                and item["transport_status"] == "FAILED"
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
        self.assertEqual(len(runner.calls), 4)
        self.assertEqual(ping.calls, 1)
        self.assertEqual(receipt["network_request_count"], 2)

    def test_loader_allows_free_space_drift_but_enforces_minimum(self):
        def with_free_bytes(free_bytes):
            def probe(path):
                entry = Path(path).stat()
                return {
                    "device": entry.st_dev,
                    "filesystem_id": entry.st_dev,
                    "free_bytes": free_bytes,
                    "is_local": True,
                }

            return probe

        result, _runner, _ping = self.execute(
            filesystem=with_free_bytes(10 * 1024 * 1024 * 1024)
        )
        receipt_path = Path(result["receipt_path"])
        loaded = load_system_paper_preflight_receipt(
            receipt_path=receipt_path,
            contract_path=self.contract_path,
            plist_path=self.plist_path,
            machine_probe=self.machine,
            filesystem_probe=with_free_bytes(9 * 1024 * 1024 * 1024),
            clock=lambda: "2026-08-04T05:20:00.000Z",
        )
        self.assertEqual(loaded["status"], "PREFLIGHT_VERIFIED_INSTALL_ELIGIBLE")
        with self.assertRaisesRegex(
            SystemPaperPreflightError, "DISK_SPACE_INSUFFICIENT"
        ):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=with_free_bytes(4 * 1024 * 1024 * 1024),
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )

    def test_frozen_credential_names_and_paths_fail_closed_without_values(self):
        environment_names = [
            "BINANCE_API_KEY",
            "BINANCE_API_SECRET",
            "BINANCE_SECRET_KEY",
            "CRYPTO_QUANT_API_KEY",
            "CRYPTO_QUANT_API_SECRET",
        ]
        file_paths = [
            str(self.home / ".config" / "crypto-quant" / "credentials.json"),
            str(self.home / ".config" / "binance" / "credentials.json"),
            str(self.home / ".binance" / "credentials.json"),
            str(self.runtime_root / "credentials"),
        ]
        secret = "must-never-appear"
        result, runner, _ping = self.execute(
            credential=lambda home, runtime_root: {
                "environment_names": environment_names,
                "file_paths": file_paths,
                "test_secret": secret,
            }
        )
        receipt_bytes = Path(result["receipt_path"]).read_bytes()
        receipt = json.loads(receipt_bytes)
        self.assertEqual(result["outcome"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(
            receipt["credential_boundary"],
            {
                "environment_names": environment_names,
                "file_paths": file_paths,
                "credential_count": 9,
            },
        )
        self.assertNotIn(secret.encode(), receipt_bytes)
        self.assertIn(
            "SYSTEM_PAPER_PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT",
            receipt["failure_reasons"],
        )
        self.assertEqual(len(runner.calls), 4)

    def test_loader_is_command_free_and_rejects_new_credential_presence(self):
        result, runner, _ping = self.execute()
        calls_after_publish = list(runner.calls)
        with self.assertRaisesRegex(SystemPaperPreflightError, "CREDENTIAL"):
            load_system_paper_preflight_receipt(
                receipt_path=Path(result["receipt_path"]),
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                credential_probe=lambda home, runtime_root: {
                    "environment_names": ["BINANCE_API_KEY"],
                    "file_paths": [],
                },
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )
        self.assertEqual(runner.calls, calls_after_publish)

    def test_failed_runtime_import_receipt_remains_command_free_loadable_evidence(self):
        runner = PreflightCommandRunner(
            uid=self.uid, runtime_import_stdout="not-json\n"
        )
        result, runner, _ping = self.execute(runner=runner)
        calls_after_publish = list(runner.calls)
        loaded = load_system_paper_preflight_receipt(
            receipt_path=Path(result["receipt_path"]),
            contract_path=self.contract_path,
            plist_path=self.plist_path,
            machine_probe=self.machine,
            filesystem_probe=self.filesystem,
            clock=lambda: "2026-08-04T05:20:00.000Z",
        )
        self.assertEqual(loaded["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(loaded["runtime_import"]["status"], "FAILED")
        self.assertEqual(runner.calls, calls_after_publish)

    def test_signal_terminated_runtime_import_publishes_bounded_failed_evidence(self):
        runner = PreflightCommandRunner(
            uid=self.uid, runtime_import_returncode=-9
        )
        result, _runner, _ping = self.execute(runner=runner)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(result["outcome"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(receipt["runtime_import"]["status"], "FAILED")
        self.assertEqual(
            receipt["runtime_import"]["command_evidence"]["returncode"], 255
        )
        self.assertEqual(
            receipt["runtime_import"]["command_evidence"]["transport_status"],
            "FAILED",
        )
        self.assertIn(
            "SYSTEM_PAPER_PREFLIGHT_RUNTIME_IMPORT_FAILED",
            receipt["failure_reasons"],
        )

    def test_real_exit_255_is_completed_invalid_import_not_transport_failure(self):
        runner = PreflightCommandRunner(
            uid=self.uid, runtime_import_returncode=255
        )
        result, _runner, _ping = self.execute(runner=runner)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        evidence = receipt["runtime_import"]["command_evidence"]
        self.assertEqual(result["outcome"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(evidence["returncode"], 255)
        self.assertEqual(evidence["transport_status"], "COMPLETED")
        self.assertIn(
            "SYSTEM_PAPER_PREFLIGHT_RUNTIME_IMPORT_INVALID",
            receipt["failure_reasons"],
        )
        self.assertNotIn(
            "SYSTEM_PAPER_PREFLIGHT_RUNTIME_IMPORT_FAILED",
            receipt["failure_reasons"],
        )

    def test_invalid_contract_or_plist_creates_zero_preflight_files(self):
        self.contract_path.write_text("{}", encoding="utf-8")
        preflight_root = self.runtime_root / "preflight-receipts"
        with self.assertRaises(Exception):
            self.execute()
        self.assertFalse(preflight_root.exists())

    def test_late_ping_source_mutation_fails_before_receipt_publication(self):
        original = self.plist_path.read_bytes()

        class MutatingPing(FakePingTransport):
            def get(inner_self):
                self.plist_path.write_bytes(original + b"\n")
                return super().get()

        with self.assertRaisesRegex(
            SystemPaperPreflightError, "RUNTIME_IDENTITY_CHANGED"
        ):
            self.execute(ping=MutatingPing())
        preflight_root = self.runtime_root / "preflight-receipts"
        self.assertEqual(
            [] if not preflight_root.exists() else list(preflight_root.glob("*.json")),
            [],
        )

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

    def test_rehashed_claimed_runtime_import_failure_rejects_success_evidence(self):
        result, _runner, _ping = self.execute()
        receipt_path = Path(result["receipt_path"])
        receipt = json.loads(receipt_path.read_text())
        receipt["status"] = "PREFLIGHT_FAILED_CLOSED"
        receipt["expires_at_or_null"] = None
        receipt["failure_reasons"] = [
            "SYSTEM_PAPER_PREFLIGHT_RUNTIME_IMPORT_FAILED"
        ]
        receipt["runtime_import"]["status"] = "FAILED"
        receipt["runtime_import"]["package_version_or_null"] = None
        receipt["runtime_import"]["sys_version_or_null"] = None
        receipt["receipt_hash"] = artifact_self_hash(receipt, "receipt_hash")
        receipt_path.write_text(canonical_json(receipt), encoding="utf-8")
        with self.assertRaisesRegex(SystemPaperPreflightError, "INVALID"):
            load_system_paper_preflight_receipt(
                receipt_path=receipt_path,
                contract_path=self.contract_path,
                plist_path=self.plist_path,
                machine_probe=self.machine,
                filesystem_probe=self.filesystem,
                clock=lambda: "2026-08-04T05:20:00.000Z",
            )

    def test_historical_credential_failure_loads_after_credential_remediation(self):
        result, _runner, _ping = self.execute(
            credential=lambda home, runtime_root: {
                "environment_names": ["BINANCE_API_KEY"],
                "file_paths": [],
            }
        )
        loaded = load_system_paper_preflight_receipt(
            receipt_path=Path(result["receipt_path"]),
            contract_path=self.contract_path,
            plist_path=self.plist_path,
            machine_probe=self.machine,
            filesystem_probe=self.filesystem,
            credential_probe=lambda home, runtime_root: {
                "environment_names": [],
                "file_paths": [],
            },
            clock=lambda: "2026-08-04T05:20:00.000Z",
        )
        self.assertEqual(loaded["status"], "PREFLIGHT_FAILED_CLOSED")
        self.assertEqual(loaded["credential_boundary"]["credential_count"], 1)

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
