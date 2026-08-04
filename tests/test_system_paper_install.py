"""Preflight-gated atomic System Paper LaunchAgent installation tests."""

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from crypto_quant.system_paper_install import (
    LaunchctlResult,
    SystemPaperInstallError,
    _activation_window_safe,
    install_system_paper_launchd,
    load_system_paper_install_receipt,
)
from crypto_quant.system_paper_install_cli import main as install_main
from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
import tests.test_system_paper_preflight as preflight_helpers


LABEL = "local.crypto-quant.system-paper-v1"
SOURCE_CHECK_AT = "2026-08-04T05:09:58.000Z"
CHECK_AT = "2026-08-04T05:09:59.000Z"
INSTALL_AT = "2026-08-04T05:10:00.000Z"
VERIFY_AT = "2026-08-04T05:10:01.000Z"


class FakeLaunchctl:
    def __init__(
        self,
        *,
        contract,
        target,
        uid,
        preloaded=False,
        bootstrap_returncode=0,
        verified_bindings=True,
        after_first_print=None,
        after_bootstrap=None,
        post_print_returncode=0,
        post_print_raises=False,
    ):
        self.contract = contract
        self.target = target
        self.uid = uid
        self.preloaded = preloaded
        self.bootstrap_returncode = bootstrap_returncode
        self.verified_bindings = verified_bindings
        self.after_first_print = after_first_print
        self.after_bootstrap = after_bootstrap
        self.post_print_returncode = post_print_returncode
        self.post_print_raises = post_print_raises
        self.calls = []
        self.bootstrapped = False

    @property
    def domain(self):
        return f"gui/{self.uid}"

    @property
    def service(self):
        return f"{self.domain}/{LABEL}"

    def print_bytes(self):
        snapshot = self.contract["execution_snapshot"]["repository_root"]
        if not self.verified_bindings:
            snapshot = "/wrong/snapshot"
        arguments = "\n".join(
            "\t\t" + value for value in self.contract["program_arguments"]
        )
        return (
            f"{self.service} = {{\n"
            "\tactive count = 0\n"
            f"\tpath = {self.target}\n"
            "\ttype = LaunchAgent\n"
            "\tstate = not running\n"
            f"\tprogram = {self.contract['python_executable']}\n"
            "\targuments = {\n"
            f"{arguments}\n"
            "\t}\n"
            f"\tworking directory = {snapshot}\n"
            "\tenvironment = {\n"
            f"\t\tPYTHONPATH => {snapshot}/src\n"
            f"\t\tXPC_SERVICE_NAME => {LABEL}\n"
            "\t}\n"
            "\truns = 0\n"
            "\tlast exit code = (never exited)\n"
            "}\n"
        ).encode("utf-8")

    def __call__(self, argv):
        call = tuple(str(item) for item in argv)
        self.calls.append(call)
        if call == ("/bin/launchctl", "print", self.service):
            loaded = self.preloaded or self.bootstrapped
            print_count = len([item for item in self.calls if item[1] == "print"])
            if print_count > 1 and self.post_print_raises:
                raise OSError("post-bootstrap transport failed")
            if print_count > 1 and self.post_print_returncode:
                return LaunchctlResult(
                    self.post_print_returncode,
                    b"",
                    b"post-bootstrap print failed\n",
                )
            result = LaunchctlResult(
                0 if loaded else 113,
                self.print_bytes() if loaded else b"",
                b"" if loaded else b"service not found\n",
            )
            if print_count == 1:
                if self.after_first_print is not None:
                    self.after_first_print()
            return result
        if call == (
            "/bin/launchctl",
            "bootstrap",
            self.domain,
            str(self.target),
        ):
            if self.bootstrap_returncode == 0:
                self.bootstrapped = True
                if self.after_bootstrap is not None:
                    self.after_bootstrap()
            return LaunchctlResult(
                self.bootstrap_returncode,
                b"",
                b"" if self.bootstrap_returncode == 0 else b"failed\n",
            )
        raise AssertionError(f"unexpected authority: {call}")


class SystemPaperInstallTests(unittest.TestCase):
    def setUp(self):
        self.preflight = preflight_helpers.SystemPaperPreflightTests()
        self.preflight.setUp()
        self.addCleanup(self.preflight.tearDown)
        self.contract = json.loads(self.preflight.contract_path.read_text())
        self.target = (
            self.preflight.home
            / "Library"
            / "LaunchAgents"
            / f"{LABEL}.plist"
        )

    def verified_preflight(self):
        result, _runner, _ping = self.preflight.execute()
        return Path(result["receipt_path"])

    def verified_preflight_at(self, timestamp):
        moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        result, _runner, _ping = self.preflight.execute(
            clock=lambda: timestamp,
            server_time=preflight_helpers.FakeTimeTransport(
                preflight_helpers.fake_time_responses(base=moment)
            ),
        )
        return Path(result["receipt_path"])

    def values(self, receipt_path, runner):
        times = iter((SOURCE_CHECK_AT, CHECK_AT, INSTALL_AT, VERIFY_AT))
        return {
            "contract_path": self.preflight.contract_path,
            "plist_path": self.preflight.plist_path,
            "preflight_receipt_path": receipt_path,
            "clock": lambda: next(times),
            "_launchctl_runner": runner,
            "_machine_probe": self.preflight.machine,
            "_filesystem_probe": self.preflight.filesystem,
        }

    def runner(self, **kwargs):
        return FakeLaunchctl(
            contract=self.contract,
            target=self.target,
            uid=self.preflight.uid,
            **kwargs,
        )

    def test_missing_failed_or_expired_preflight_has_zero_authority_and_writes(self):
        runner = self.runner()
        missing = self.preflight.runtime_root / "preflight-receipts" / "missing.json"
        with self.assertRaises(Exception):
            install_system_paper_launchd(**self.values(missing, runner))
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())

        verified = self.verified_preflight()
        expired_values = self.values(verified, runner)
        expired_values["clock"] = lambda: "2026-08-04T05:31:00.000Z"
        with self.assertRaisesRegex(Exception, "EXPIRED"):
            install_system_paper_launchd(**expired_values)
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())
        self.assertFalse((self.preflight.runtime_root / "install-receipts").exists())

        failed, _runner, _ping = self.preflight.execute(
            runner=preflight_helpers.PreflightCommandRunner(
                uid=self.preflight.uid, sleep_minutes=30
            ),
            clock=lambda: "2026-08-04T05:01:00.000Z",
        )
        with self.assertRaisesRegex(SystemPaperInstallError, "PREFLIGHT"):
            install_system_paper_launchd(
                **self.values(Path(failed["receipt_path"]), runner)
            )
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())

    def test_frozen_credential_presence_blocks_install_with_zero_authority(self):
        environment = {
            "BINANCE_API_KEY": "secret",
            "BINANCE_API_SECRET": "secret",
            "BINANCE_SECRET_KEY": "secret",
            "CRYPTO_QUANT_API_KEY": "secret",
            "CRYPTO_QUANT_API_SECRET": "secret",
        }
        credential_paths = (
            self.preflight.home
            / ".config"
            / "crypto-quant"
            / "credentials.json",
            self.preflight.home
            / ".config"
            / "binance"
            / "credentials.json",
            self.preflight.home / ".binance" / "credentials.json",
            self.preflight.runtime_root / "credentials",
        )
        for path in credential_paths:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.write_text("secret", encoding="utf-8")
            os.chmod(path, 0o600)

        with patch.dict(os.environ, environment):
            failed, _preflight_runner, _ping = self.preflight.execute()
            receipt = json.loads(Path(failed["receipt_path"]).read_text())
            runner = self.runner()
            with self.assertRaisesRegex(SystemPaperInstallError, "PREFLIGHT"):
                install_system_paper_launchd(
                    **self.values(Path(failed["receipt_path"]), runner)
                )

        self.assertEqual(receipt["credential_boundary"]["credential_count"], 9)
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())
        self.assertFalse(
            (self.preflight.runtime_root / "install-receipts").exists()
        )

    def test_close_delay_activation_window_fails_before_launchctl_or_write(self):
        preflight_path = self.verified_preflight_at(
            "2026-08-04T04:01:00.000Z"
        )
        runner = self.runner()

        with self.assertRaisesRegex(
            SystemPaperInstallError,
            "SYSTEM_PAPER_INSTALL_ACTIVATION_WINDOW_UNSAFE",
        ):
            install_system_paper_launchd(
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                clock=lambda: "2026-08-04T04:02:00.000Z",
                _launchctl_runner=runner,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())
        self.assertFalse(
            (self.preflight.runtime_root / "install-receipts").exists()
        )

    def test_frozen_activation_window_has_inclusive_edges(self):
        self.assertFalse(_activation_window_safe("2026-08-04T04:29:59.999Z"))
        self.assertTrue(_activation_window_safe("2026-08-04T04:30:00.000Z"))
        self.assertTrue(_activation_window_safe("2026-08-04T07:30:00.000Z"))
        self.assertFalse(_activation_window_safe("2026-08-04T07:30:00.001Z"))

    def test_second_activation_check_blocks_clock_crossing_before_write(self):
        preflight_path = self.verified_preflight_at(
            "2026-08-04T07:28:00.000Z"
        )
        runner = self.runner()
        times = iter(
            (
                "2026-08-04T07:29:00.000Z",
                "2026-08-04T07:29:00.000Z",
                "2026-08-04T07:31:00.000Z",
            )
        )

        with self.assertRaisesRegex(
            SystemPaperInstallError,
            "SYSTEM_PAPER_INSTALL_ACTIVATION_WINDOW_UNSAFE",
        ):
            install_system_paper_launchd(
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                clock=lambda: next(times),
                _launchctl_runner=runner,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(runner.calls[0][1], "print")
        self.assertFalse(self.target.parent.exists())

    def test_source_replay_clock_advance_blocks_before_write(self):
        preflight_path = self.verified_preflight_at(
            "2026-08-04T07:28:00.000Z"
        )
        runner = self.runner()
        current = {"time": "2026-08-04T07:29:00.000Z"}
        probes = {"count": 0}

        def advancing_machine_probe():
            probes["count"] += 1
            if probes["count"] == 2:
                current["time"] = "2026-08-04T08:06:00.000Z"
            return self.preflight.machine()

        with self.assertRaisesRegex(
            SystemPaperInstallError,
            "SYSTEM_PAPER_INSTALL_ACTIVATION_WINDOW_UNSAFE",
        ):
            install_system_paper_launchd(
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                clock=lambda: current["time"],
                _launchctl_runner=runner,
                _machine_probe=advancing_machine_probe,
                _filesystem_probe=self.preflight.filesystem,
            )

        self.assertEqual(probes["count"], 2)
        self.assertEqual(len(runner.calls), 1)
        self.assertFalse(self.target.parent.exists())

    def test_loader_replays_frozen_activation_window(self):
        preflight_path = self.verified_preflight_at(
            "2026-08-04T07:28:00.000Z"
        )
        runner = self.runner()
        times = iter(
            (
                "2026-08-04T07:29:00.000Z",
                "2026-08-04T07:29:00.000Z",
                "2026-08-04T07:29:01.000Z",
                "2026-08-04T07:29:02.000Z",
            )
        )
        result = install_system_paper_launchd(
            contract_path=self.preflight.contract_path,
            plist_path=self.preflight.plist_path,
            preflight_receipt_path=preflight_path,
            clock=lambda: next(times),
            _launchctl_runner=runner,
            _machine_probe=self.preflight.machine,
            _filesystem_probe=self.preflight.filesystem,
        )
        receipt_path = Path(result["receipt_path"])
        changed = json.loads(receipt_path.read_text())
        changed["installed_at"] = "2026-08-04T07:31:00.000Z"
        changed["verified_at"] = "2026-08-04T07:31:01.000Z"
        changed["receipt_id"] = stable_id(
            "system_paper_install_receipt",
            {
                "contract_hash": changed["source_contract"]["contract_hash"],
                "preflight_receipt_hash": changed["preflight_receipt"]["receipt_hash"],
                "target_path": changed["target_path"],
                "target_inode": changed["target_stat"]["inode"],
                "install_action": changed["install_action"],
                "installation_status": changed["installation_status"],
                "installed_at": changed["installed_at"],
                "verified_at": changed["verified_at"],
            },
        )
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        changed_path = receipt_path.with_name(f"{changed['receipt_id']}.json")
        receipt_path.rename(changed_path)
        changed_path.write_bytes(canonical_json(changed).encode("utf-8"))

        with self.assertRaisesRegex(
            SystemPaperInstallError,
            "SYSTEM_PAPER_INSTALL_RECEIPT_INVALID",
        ):
            load_system_paper_install_receipt(
                receipt_path=changed_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_new_install_is_atomic_fixed_and_receipted_without_runtime_start(self):
        preflight_path = self.verified_preflight()
        runner = self.runner()
        result = install_system_paper_launchd(
            **self.values(preflight_path, runner)
        )
        receipt = load_system_paper_install_receipt(
            receipt_path=Path(result["receipt_path"]),
            contract_path=self.preflight.contract_path,
            plist_path=self.preflight.plist_path,
            preflight_receipt_path=preflight_path,
            _machine_probe=self.preflight.machine,
            _filesystem_probe=self.preflight.filesystem,
        )

        self.assertEqual(result["outcome"], "INSTALLED_AND_LOADED")
        self.assertEqual(result["install_action"], "INSTALLED_AND_BOOTSTRAPPED")
        self.assertEqual(self.target.read_bytes(), self.preflight.plist_path.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target.parent.stat().st_mode), 0o700)
        self.assertEqual(
            runner.calls,
            [
                ("/bin/launchctl", "print", runner.service),
                ("/bin/launchctl", "bootstrap", runner.domain, str(self.target)),
                ("/bin/launchctl", "print", runner.service),
            ],
        )
        self.assertEqual(receipt["preflight_receipt"]["receipt_id"], json.loads(preflight_path.read_text())["receipt_id"])
        self.assertEqual(receipt["security_boundary"]["runtime_invocation_count"], 0)
        self.assertEqual(receipt["security_boundary"]["credential_count"], 0)
        self.assertEqual(receipt["security_boundary"]["broker_request_count"], 0)
        self.assertEqual(receipt["security_boundary"]["order_submission_count"], 0)
        self.assertEqual(
            receipt["service_snapshot_or_null"]["environment"],
            {
                "PYTHONPATH": self.contract["execution_snapshot"][
                    "repository_root"
                ]
                + "/src",
                "XPC_SERVICE_NAME": LABEL,
            },
        )

    def test_bootstrap_failure_rolls_back_only_new_exact_inode(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(bootstrap_returncode=5)
        with self.assertRaisesRegex(SystemPaperInstallError, "BOOTSTRAP_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertFalse(self.target.exists())
        self.assertEqual(len(runner.calls), 2)

    def test_existing_file_conflict_is_preserved(self):
        preflight_path = self.verified_preflight()
        self.target.parent.mkdir(mode=0o700, parents=True)
        self.target.write_bytes(b"user-owned-conflict")
        self.target.chmod(0o600)
        runner = self.runner()
        with self.assertRaisesRegex(SystemPaperInstallError, "TARGET_CONFLICT"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertEqual(self.target.read_bytes(), b"user-owned-conflict")
        self.assertEqual(len(runner.calls), 1)

    def test_loaded_exact_service_is_idempotent_without_bootstrap(self):
        preflight_path = self.verified_preflight()
        self.target.parent.mkdir(mode=0o700, parents=True)
        self.target.write_bytes(self.preflight.plist_path.read_bytes())
        self.target.chmod(0o600)
        runner = self.runner(preloaded=True)
        result = install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertEqual(result["install_action"], "ALREADY_INSTALLED_AND_LOADED")
        self.assertEqual([call[1] for call in runner.calls], ["print", "print"])

    def test_preloaded_service_rejects_insecure_launchagents_parent(self):
        preflight_path = self.verified_preflight()
        self.target.parent.mkdir(mode=0o700, parents=True)
        self.target.write_bytes(self.preflight.plist_path.read_bytes())
        self.target.chmod(0o600)
        self.target.parent.chmod(0o777)

        with self.assertRaisesRegex(SystemPaperInstallError, "TARGET_PARENT_INVALID"):
            install_system_paper_launchd(
                **self.values(preflight_path, self.runner(preloaded=True))
            )

    def test_loader_rejects_insecure_launchagents_parent(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        self.target.parent.chmod(0o777)

        with self.assertRaisesRegex(SystemPaperInstallError, "RECEIPT_INVALID"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_loader_rejects_insecure_receipt_parent(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        receipt_path.parent.chmod(0o777)

        with self.assertRaisesRegex(SystemPaperInstallError, "READ_INVALID"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_post_bootstrap_print_failure_preserves_loaded_configuration(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(post_print_returncode=5)
        with self.assertRaisesRegex(SystemPaperInstallError, "PRINT_VERIFY_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertTrue(self.target.is_file())
        self.assertTrue(runner.bootstrapped)
        receipt_files = list(
            (self.preflight.runtime_root / "install-receipts").glob("*.json")
        )
        self.assertEqual(len(receipt_files), 1)
        receipt = json.loads(receipt_files[0].read_text())
        self.assertEqual(
            receipt["installation_status"], "LOADED_VERIFICATION_FAILED"
        )
        self.assertEqual(receipt["preflight_print"]["returncode"], 113)
        self.assertEqual(receipt["bootstrap_or_null"]["returncode"], 0)
        self.assertEqual(receipt["verified_print"]["returncode"], 5)
        self.assertEqual(receipt["security_boundary"]["launchctl_command_count"], 3)

        with self.assertRaisesRegex(SystemPaperInstallError, "NOT_AUTHORITY"):
            load_system_paper_install_receipt(
                receipt_path=receipt_files[0],
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_post_bootstrap_semantic_mismatch_publishes_forensic_receipt(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(verified_bindings=False)
        with self.assertRaisesRegex(SystemPaperInstallError, "PRINT_VERIFY_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        receipt_files = list(
            (self.preflight.runtime_root / "install-receipts").glob("*.json")
        )
        self.assertEqual(len(receipt_files), 1)
        receipt = json.loads(receipt_files[0].read_text())
        self.assertEqual(
            receipt["installation_status"], "LOADED_VERIFICATION_FAILED"
        )
        self.assertEqual(receipt["verified_print"]["returncode"], 0)
        self.assertIsNone(receipt["service_snapshot_or_null"])

    def test_forensic_semantic_failure_cannot_be_rehashed_into_authority(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(verified_bindings=False)
        with self.assertRaisesRegex(SystemPaperInstallError, "PRINT_VERIFY_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        receipt_path = next(
            (self.preflight.runtime_root / "install-receipts").glob("*.json")
        )
        changed = json.loads(receipt_path.read_text())
        snapshot = self.contract["execution_snapshot"]["repository_root"]
        changed["service_snapshot_or_null"] = {
            "label": LABEL,
            "service": runner.service,
            "path": str(self.target),
            "program": self.contract["python_executable"],
            "arguments": list(self.contract["program_arguments"]),
            "working_directory": snapshot,
            "environment": {
                "PYTHONPATH": snapshot + "/src",
                "XPC_SERVICE_NAME": LABEL,
            },
            "runs": 0,
            "state": "not running",
            "last_exit_status": None,
        }
        changed["installation_status"] = "INSTALLED_AND_LOADED"
        changed["receipt_id"] = stable_id(
            "system_paper_install_receipt",
            {
                "contract_hash": changed["source_contract"]["contract_hash"],
                "preflight_receipt_hash": changed["preflight_receipt"][
                    "receipt_hash"
                ],
                "target_path": changed["target_path"],
                "target_inode": changed["target_stat"]["inode"],
                "install_action": changed["install_action"],
                "installed_at": changed["installed_at"],
                "verified_at": changed["verified_at"],
                "installation_status": changed["installation_status"],
            },
        )
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        changed_path = receipt_path.with_name(f"{changed['receipt_id']}.json")
        receipt_path.rename(changed_path)
        changed_path.write_bytes(canonical_json(changed).encode("utf-8"))

        with self.assertRaisesRegex(SystemPaperInstallError, "RECEIPT_INVALID"):
            load_system_paper_install_receipt(
                receipt_path=changed_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_target_replacement_after_bootstrap_never_publishes_success(self):
        preflight_path = self.verified_preflight()

        def replace_target():
            data = self.target.read_bytes()
            self.target.unlink()
            self.target.write_bytes(data)
            self.target.chmod(0o600)

        runner = self.runner(after_bootstrap=replace_target)
        with self.assertRaisesRegex(SystemPaperInstallError, "TARGET_IDENTITY_CHANGED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        receipt_files = list(
            (self.preflight.runtime_root / "install-receipts").glob("*.json")
        )
        self.assertTrue(
            all(
                json.loads(path.read_text())["installation_status"]
                != "INSTALLED_AND_LOADED"
                for path in receipt_files
            )
        )

    def test_post_bootstrap_transport_failure_publishes_forensic_receipt(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(post_print_raises=True)
        with self.assertRaisesRegex(SystemPaperInstallError, "PRINT_VERIFY_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        receipt_files = list(
            (self.preflight.runtime_root / "install-receipts").glob("*.json")
        )
        self.assertEqual(len(receipt_files), 1)
        receipt = json.loads(receipt_files[0].read_text())
        self.assertEqual(
            receipt["installation_status"], "LOADED_VERIFICATION_FAILED"
        )
        self.assertEqual(
            receipt["verified_print"]["transport_status"], "FAILED"
        )
        self.assertEqual(receipt["verified_print"]["returncode"], 255)
        self.assertEqual(receipt["security_boundary"]["launchctl_command_count"], 3)

    def test_source_or_preflight_mutation_after_first_print_blocks_before_write(self):
        preflight_path = self.verified_preflight()

        def mutate():
            data = preflight_path.read_bytes()
            preflight_path.write_bytes(data + b"\n")

        runner = self.runner(after_first_print=mutate)
        with self.assertRaises(Exception):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertEqual(len(runner.calls), 1)
        self.assertFalse(self.target.exists())

    def test_parent_permission_race_is_rechecked_before_target_write(self):
        preflight_path = self.verified_preflight()
        import crypto_quant.system_paper_install as install_module

        original = install_module._ensure_target_parent

        def make_parent_insecure(home, uid):
            parent = original(home, uid)
            parent.chmod(0o777)
            return parent

        with patch(
            "crypto_quant.system_paper_install._ensure_target_parent",
            side_effect=make_parent_insecure,
        ):
            with self.assertRaisesRegex(
                SystemPaperInstallError, "TARGET_PARENT_INVALID"
            ):
                install_system_paper_launchd(
                    **self.values(preflight_path, self.runner())
                )
        self.assertFalse(self.target.exists())

    def test_loader_rejects_coordinated_rehash_and_duplicate_inventory(self):
        preflight_path = self.verified_preflight()
        runner = self.runner()
        result = install_system_paper_launchd(
            **self.values(preflight_path, runner)
        )
        receipt_path = Path(result["receipt_path"])
        original = receipt_path.read_bytes()
        changed = json.loads(original)
        changed["preflight_receipt"]["receipt_path"] = "/wrong/preflight.json"
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        receipt_path.write_bytes(canonical_json(changed).encode("utf-8"))
        with self.assertRaises(SystemPaperInstallError):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

        receipt_path.write_bytes(original)
        duplicate = receipt_path.parent / "duplicate.json"
        duplicate.write_bytes(original)
        duplicate.chmod(0o600)
        with self.assertRaisesRegex(SystemPaperInstallError, "INVENTORY"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_loader_rejects_target_rehash_away_from_frozen_source(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        changed = json.loads(receipt_path.read_text())
        replacement = b"not-the-frozen-plist"
        self.target.write_bytes(replacement)
        changed["target_stat"]["size_bytes"] = len(replacement)
        changed["target_stat"]["sha256"] = hashlib.sha256(replacement).hexdigest()
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        receipt_path.write_bytes(canonical_json(changed).encode("utf-8"))

        with self.assertRaisesRegex(SystemPaperInstallError, "RECEIPT_INVALID"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_loader_rejects_valid_looking_duplicate_receipt_filename(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        duplicate = receipt_path.with_name(
            "system_paper_install_receipt_" + "f" * 64 + ".json"
        )
        duplicate.write_bytes(receipt_path.read_bytes())
        duplicate.chmod(0o600)

        with self.assertRaisesRegex(SystemPaperInstallError, "INVENTORY"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_loader_rejects_non_object_inventory_as_closed_failure(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        invalid = receipt_path.parent / "invalid.json"
        invalid.write_bytes(b"[]")
        invalid.chmod(0o600)

        with self.assertRaisesRegex(SystemPaperInstallError, "INVENTORY"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_loader_rejects_rehashed_target_device_change(self):
        preflight_path = self.verified_preflight()
        result = install_system_paper_launchd(
            **self.values(preflight_path, self.runner())
        )
        receipt_path = Path(result["receipt_path"])
        changed = json.loads(receipt_path.read_text())
        changed["target_stat"]["device"] += 1
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        receipt_path.write_text(canonical_json(changed), encoding="utf-8")
        with self.assertRaisesRegex(SystemPaperInstallError, "RECEIPT_INVALID"):
            load_system_paper_install_receipt(
                receipt_path=receipt_path,
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
                _machine_probe=self.preflight.machine,
                _filesystem_probe=self.preflight.filesystem,
            )

    def test_cli_accepts_only_contract_plist_and_preflight(self):
        expected = {
            "outcome": "INSTALLED_AND_LOADED",
            "receipt_path": "/private/example/install.json",
        }
        preflight_path = self.verified_preflight()
        with patch(
            "crypto_quant.system_paper_install_cli.install_system_paper_launchd",
            return_value=expected,
        ) as install:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = install_main(
                    [
                        "--contract-path", str(self.preflight.contract_path),
                        "--plist-path", str(self.preflight.plist_path),
                        "--preflight-receipt-path", str(preflight_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            self.assertEqual(stderr.getvalue(), "")
            install.assert_called_once_with(
                contract_path=self.preflight.contract_path,
                plist_path=self.preflight.plist_path,
                preflight_receipt_path=preflight_path,
            )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                install_main(["--kickstart"])


if __name__ == "__main__":
    unittest.main()
