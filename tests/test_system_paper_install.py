"""Preflight-gated atomic System Paper LaunchAgent installation tests."""

import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from crypto_quant.system_paper_install import (
    LaunchctlResult,
    SystemPaperInstallError,
    install_system_paper_launchd,
    load_system_paper_install_receipt,
)
from crypto_quant.system_paper_install_cli import main as install_main
from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
import tests.test_system_paper_preflight as preflight_helpers


LABEL = "local.crypto-quant.system-paper-v1"
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
    ):
        self.contract = contract
        self.target = target
        self.uid = uid
        self.preloaded = preloaded
        self.bootstrap_returncode = bootstrap_returncode
        self.verified_bindings = verified_bindings
        self.after_first_print = after_first_print
        self.calls = []
        self.bootstrapped = False

    @property
    def domain(self):
        return f"gui/{self.uid}"

    @property
    def service(self):
        return f"{self.domain}/{LABEL}"

    def print_bytes(self):
        values = [
            self.service,
            LABEL,
            str(self.target),
            self.contract["python_executable"],
            "crypto_quant.system_paper_runtime_cli",
            self.contract["program_arguments"][4],
            self.contract["program_arguments"][6],
            self.contract["execution_snapshot"]["repository_root"],
        ]
        if not self.verified_bindings:
            values[-1] = "/wrong/snapshot"
        return ("\n".join(values) + "\n").encode("utf-8")

    def __call__(self, argv):
        call = tuple(str(item) for item in argv)
        self.calls.append(call)
        if call == ("/bin/launchctl", "print", self.service):
            loaded = self.preloaded or self.bootstrapped
            result = LaunchctlResult(
                0 if loaded else 113,
                self.print_bytes() if loaded else b"",
                b"" if loaded else b"service not found\n",
            )
            if len([item for item in self.calls if item[1] == "print"]) == 1:
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

    def values(self, receipt_path, runner):
        times = iter((INSTALL_AT, VERIFY_AT))
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

        verified = self.verified_preflight()
        expired_values = self.values(verified, runner)
        expired_values["clock"] = lambda: "2026-08-04T05:31:00.000Z"
        with self.assertRaisesRegex(Exception, "EXPIRED"):
            install_system_paper_launchd(**expired_values)
        self.assertEqual(runner.calls, [])
        self.assertFalse(self.target.parent.exists())

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

    def test_post_bootstrap_print_failure_preserves_loaded_configuration(self):
        preflight_path = self.verified_preflight()
        runner = self.runner(verified_bindings=False)
        with self.assertRaisesRegex(SystemPaperInstallError, "PRINT_VERIFY_FAILED"):
            install_system_paper_launchd(**self.values(preflight_path, runner))
        self.assertTrue(self.target.is_file())
        self.assertTrue(runner.bootstrapped)

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
