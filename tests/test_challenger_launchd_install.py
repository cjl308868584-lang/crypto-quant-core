import copy
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from crypto_quant.challenger_launchd import (
    load_challenger_launchd_contract,
    publish_challenger_launchd_contract,
)
from crypto_quant.challenger_launchd_install import (
    ChallengerLaunchdInstallError,
    LaunchctlResult,
    challenger_install_receipt_hash,
    install_challenger_launchd,
    load_challenger_install_receipt,
)
from crypto_quant.challenger_launchd_install_cli import (
    main as install_main,
)
from crypto_quant.canonical import canonical_json, stable_id


ROOT = Path(__file__).resolve().parents[1]
CREATED = datetime(2026, 7, 28, 6, tzinfo=timezone.utc)
INSTALLED = datetime(2026, 7, 28, 7, tzinfo=timezone.utc)
VERIFIED = datetime(2026, 7, 28, 7, 0, 1, tzinfo=timezone.utc)
LABEL = "local.crypto-quant.challenger-forward"


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
    ):
        self.contract = contract
        self.target = target
        self.uid = uid
        self.preloaded = preloaded
        self.bootstrap_returncode = bootstrap_returncode
        self.verified_bindings = verified_bindings
        self.calls = []
        self.bootstrapped = False

    @property
    def service(self):
        return f"gui/{self.uid}/{LABEL}"

    def valid_print(self):
        values = [
            self.service,
            LABEL,
            str(self.target),
            self.contract["python_executable"],
            "crypto_quant.challenger_forward_runner_cli",
            self.contract["program_arguments"][4],
            self.contract["program_arguments"][6],
        ]
        if not self.verified_bindings:
            values[-1] = "/wrong/output"
        return ("\n".join(values) + "\n").encode("utf-8")

    def __call__(self, argv):
        call = tuple(argv)
        self.calls.append(call)
        if call[1] == "print":
            if self.preloaded or self.bootstrapped:
                return LaunchctlResult(0, self.valid_print(), b"")
            return LaunchctlResult(113, b"", b"service not found\n")
        if call[1] == "bootstrap":
            if self.bootstrap_returncode == 0:
                self.bootstrapped = True
            return LaunchctlResult(
                self.bootstrap_returncode,
                b"",
                b"" if self.bootstrap_returncode == 0 else b"failed\n",
            )
        raise AssertionError(f"unexpected command: {call}")


class ChallengerLaunchdInstallTests(unittest.TestCase):
    def source(self, root):
        deployment = root / "runtime" / "deployment" / "test-snapshot"
        deployment.mkdir(parents=True, mode=0o700)
        shutil.copy2(ROOT / "pyproject.toml", deployment / "pyproject.toml")
        shutil.copytree(
            ROOT / "src" / "crypto_quant",
            deployment / "src" / "crypto_quant",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for entry in deployment.rglob("*"):
            entry.chmod(0o700 if entry.is_dir() else 0o600)
        result = publish_challenger_launchd_contract(
            repository_root=deployment,
            runtime_root=root / "runtime",
            python_executable=Path(sys.executable),
            output_root=root / "source",
            clock=lambda: CREATED,
        )
        contract_path = Path(result["contract_path"])
        plist_path = Path(result["plist_path"])
        contract = load_challenger_launchd_contract(
            contract_path=contract_path,
            plist_path=plist_path,
        )
        return contract, contract_path, plist_path

    def install_inputs(self, root):
        contract, contract_path, plist_path = self.source(root)
        home = root / "home"
        target = (
            home.resolve()
            / "Library"
            / "LaunchAgents"
            / f"{LABEL}.plist"
        )
        runner = FakeLaunchctl(
            contract=contract,
            target=target,
            uid=os.getuid(),
        )
        times = iter((INSTALLED, VERIFIED))
        values = {
            "contract_path": contract_path,
            "plist_path": plist_path,
            "receipt_output_root": root / "receipts",
            "clock": lambda: next(times),
            "_home_directory": home,
            "_uid": os.getuid(),
            "_launchctl_runner": runner,
        }
        return contract, target, runner, values

    def test_new_install_is_fixed_atomic_and_receipted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, target, runner, values = self.install_inputs(root)
            real_run = subprocess.run
            with patch(
                "crypto_quant.challenger_launchd_install.subprocess.run",
                wraps=real_run,
            ) as preflight_run:
                result = install_challenger_launchd(**values)
            self.assertEqual(preflight_run.call_count, 1)
            self.assertEqual(
                preflight_run.call_args.kwargs["env"],
                {
                    "HOME": str(Path.home()),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONPATH": str(
                        Path(contract["repository_root"]) / "src"
                    ),
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                },
            )
            receipt_path = Path(result["receipt_path"])
            receipt = load_challenger_install_receipt(
                receipt_path=receipt_path,
                contract_path=values["contract_path"],
                plist_path=values["plist_path"],
            )
            self.assertEqual(result["outcome"], "INSTALLED_AND_LOADED")
            self.assertEqual(
                result["install_action"], "INSTALLED_AND_BOOTSTRAPPED"
            )
            self.assertEqual(target.read_bytes(), values["plist_path"].read_bytes())
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)
            self.assertEqual(receipt["receipt_hash"], result["receipt_hash"])
            self.assertEqual(receipt["security_boundary"]["launchctl_command_count"], 3)
            self.assertEqual(receipt["security_boundary"]["credential_count"], 0)
            self.assertEqual(receipt["security_boundary"]["order_submission_count"], 0)
            self.assertEqual(
                runner.calls,
                [
                    ("/bin/launchctl", "print", runner.service),
                    (
                        "/bin/launchctl",
                        "bootstrap",
                        f"gui/{os.getuid()}",
                        str(target),
                    ),
                    ("/bin/launchctl", "print", runner.service),
                ],
            )
            self.assertEqual(
                receipt["source_contract"]["contract_hash"],
                contract["contract_hash"],
            )

    def test_bootstrap_failure_removes_only_new_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target, runner, values = self.install_inputs(root)
            runner.bootstrap_returncode = 5
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_BOOTSTRAP_FAILED",
            ):
                install_challenger_launchd(**values)
            self.assertFalse(target.exists())
            self.assertEqual(len(runner.calls), 2)

    def test_target_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target, runner, values = self.install_inputs(root)
            target.parent.mkdir(parents=True, mode=0o700)
            target.write_bytes(b"user-owned-conflict")
            target.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_TARGET_CONFLICT",
            ):
                install_challenger_launchd(**values)
            self.assertEqual(target.read_bytes(), b"user-owned-conflict")
            self.assertEqual(len(runner.calls), 1)

    def test_loaded_exact_service_is_idempotent_without_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract, target, runner, values = self.install_inputs(root)
            target.parent.mkdir(parents=True, mode=0o700)
            target.write_bytes(values["plist_path"].read_bytes())
            target.chmod(0o600)
            runner.preloaded = True
            result = install_challenger_launchd(**values)
            self.assertEqual(
                result["install_action"], "ALREADY_INSTALLED_AND_LOADED"
            )
            self.assertEqual([call[1] for call in runner.calls], ["print", "print"])
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            self.assertIsNone(receipt["bootstrap_or_null"])
            self.assertEqual(receipt["security_boundary"]["launchctl_command_count"], 2)
            self.assertEqual(contract["label"], LABEL)

    def test_post_bootstrap_print_failure_preserves_loaded_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, target, runner, values = self.install_inputs(root)
            runner.verified_bindings = False
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_PRINT_VERIFY_FAILED",
            ):
                install_challenger_launchd(**values)
            self.assertTrue(target.is_file())
            self.assertTrue(runner.bootstrapped)

    def test_receipt_tamper_fails_even_after_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, _, _, values = self.install_inputs(root)
            result = install_challenger_launchd(**values)
            receipt_path = Path(result["receipt_path"])
            changed = copy.deepcopy(json.loads(receipt_path.read_text()))
            changed["security_boundary"]["order_submission_count"] = 1
            changed["receipt_hash"] = challenger_install_receipt_hash(changed)
            tampered = root / "tampered.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_RECEIPT_INVALID",
            ):
                load_challenger_install_receipt(
                    receipt_path=tampered,
                    contract_path=values["contract_path"],
                    plist_path=values["plist_path"],
                )

    def test_loader_allows_only_reboot_device_number_drift(self):
        """Catches binding a permanent receipt to a boot-volatile st_dev."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            contract, _, _, values = self.install_inputs(root)
            result = install_challenger_launchd(**values)
            receipt = json.loads(Path(result["receipt_path"]).read_bytes())
            changed = copy.deepcopy(receipt)
            changed["target_stat"]["device"] += 1
            identity = {
                "source_contract_hash": contract["contract_hash"],
                "target_path": changed["target_path"],
                "target_device": changed["target_stat"]["device"],
                "target_inode": changed["target_stat"]["inode"],
                "install_action": changed["install_action"],
                "installed_at": changed["installed_at"],
                "verified_at": changed["verified_at"],
                "preflight_print_hash": changed["preflight_print"][
                    "command_evidence_hash"
                ],
                "bootstrap_hash": changed["bootstrap_or_null"][
                    "command_evidence_hash"
                ],
                "verified_print_hash": changed["verified_print"][
                    "command_evidence_hash"
                ],
            }
            changed["receipt_id"] = stable_id(
                "challenger_launchd_install_receipt", identity
            )
            changed["receipt_hash"] = challenger_install_receipt_hash(
                changed
            )
            drifted = root / "device-drifted-receipt.json"
            drifted.write_bytes(canonical_json(changed).encode("utf-8"))
            loaded = load_challenger_install_receipt(
                receipt_path=drifted,
                contract_path=values["contract_path"],
                plist_path=values["plist_path"],
            )
            self.assertEqual(
                loaded["target_stat"]["device"],
                receipt["target_stat"]["device"] + 1,
            )

            wrong_inode = copy.deepcopy(changed)
            wrong_inode["target_stat"]["inode"] += 1
            identity["target_inode"] = wrong_inode["target_stat"]["inode"]
            wrong_inode["receipt_id"] = stable_id(
                "challenger_launchd_install_receipt", identity
            )
            wrong_inode["receipt_hash"] = challenger_install_receipt_hash(
                wrong_inode
            )
            forged = root / "wrong-inode-receipt.json"
            forged.write_bytes(canonical_json(wrong_inode).encode("utf-8"))
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_RECEIPT_INVALID",
            ):
                load_challenger_install_receipt(
                    receipt_path=forged,
                    contract_path=values["contract_path"],
                    plist_path=values["plist_path"],
                )

    def test_development_tree_is_rejected_and_snapshot_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            direct = publish_challenger_launchd_contract(
                repository_root=ROOT,
                runtime_root=root / "direct-runtime",
                python_executable=Path(sys.executable),
                output_root=root / "direct-source",
                clock=lambda: CREATED,
            )
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_EXECUTION_SNAPSHOT_INVALID",
            ):
                install_challenger_launchd(
                    contract_path=Path(direct["contract_path"]),
                    plist_path=Path(direct["plist_path"]),
                    receipt_output_root=root / "direct-receipts",
                    _home_directory=root / "home",
                    _uid=os.getuid(),
                    _launchctl_runner=lambda _argv: self.fail(
                        "launchctl must not run"
                    ),
                )
            _, _, _, values = self.install_inputs(root / "valid")
            result = install_challenger_launchd(**values)
            contract = load_challenger_launchd_contract(
                contract_path=values["contract_path"],
                plist_path=values["plist_path"],
            )
            package_init = (
                Path(contract["repository_root"])
                / "src"
                / "crypto_quant"
                / "__init__.py"
            )
            package_init.write_bytes(package_init.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                ChallengerLaunchdInstallError,
                "CHALLENGER_INSTALL_RECEIPT_INVALID",
            ):
                load_challenger_install_receipt(
                    receipt_path=Path(result["receipt_path"]),
                    contract_path=values["contract_path"],
                    plist_path=values["plist_path"],
                )

    def test_schema_mirror_and_cli_authority_are_strict(self):
        self.assertEqual(
            (
                ROOT
                / "config"
                / "challenger-launchd-install-receipt-v1.schema.json"
            ).read_bytes(),
            (
                ROOT
                / "src"
                / "crypto_quant"
                / "schemas"
                / "challenger-launchd-install-receipt-v1.schema.json"
            ).read_bytes(),
        )
        source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_launchd_install_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--target",
            "--domain",
            "--uid",
            "--label",
            "--command",
            "--launchctl",
            "--credential",
            "--api-key",
        ):
            self.assertNotIn(forbidden, source)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(install_main([forbidden, "x"]), 2)


if __name__ == "__main__":
    unittest.main()
