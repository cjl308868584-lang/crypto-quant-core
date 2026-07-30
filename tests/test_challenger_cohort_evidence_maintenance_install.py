import copy
import hashlib
import io
import json
import os
import plistlib
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_evidence_maintenance_deployment import (
    ChallengerCohortEvidenceMaintenanceDeploymentError,
    _read_source_files,
    deployment_manifest_hash,
    load_challenger_cohort_evidence_maintenance_deployment,
    prepare_challenger_cohort_evidence_maintenance_deployment,
)
from crypto_quant.challenger_cohort_evidence_maintenance_deployment_cli import (
    main as deployment_main,
)
from crypto_quant.challenger_cohort_evidence_maintenance_install import (
    ChallengerCohortEvidenceMaintenanceInstallError,
    MaintenanceLaunchctlResult,
    install_challenger_cohort_evidence_maintenance_launchd,
    load_challenger_cohort_evidence_maintenance_install_receipt,
    maintenance_install_receipt_hash,
)
from crypto_quant.challenger_cohort_evidence_maintenance_install_cli import (
    main as install_main,
)
from crypto_quant.challenger_cohort_evidence_maintenance_launchd import (
    publish_challenger_cohort_evidence_maintenance_launchd_contract,
)


ROOT = Path(__file__).resolve().parents[1]
PREPARED = datetime(2026, 7, 31, 5, tzinfo=timezone.utc)
INSTALLED = datetime(2026, 7, 31, 6, tzinfo=timezone.utc)
VERIFIED = datetime(2026, 7, 31, 6, 0, 1, tzinfo=timezone.utc)
LABEL = "local.crypto-quant.challenger-cohort-evidence-maintenance"


def fixture_strategy_loader(**_paths):
    return (
        {
            "contract_id": "challenger_launchd_contract_" + "a" * 64,
            "contract_hash": "b" * 64,
            "launchd_plist_sha256": "c" * 64,
            "installation_status": "NOT_INSTALLED_NO_EXTERNAL_RECEIPT",
        },
        {
            "receipt_id": (
                "challenger_launchd_install_receipt_" + "d" * 64
            ),
            "receipt_hash": "e" * 64,
        },
    )


def trust_files(root):
    values = []
    for name in (
        "strategy-install.json",
        "strategy-contract.json",
        "strategy.plist",
    ):
        path = root / name
        path.write_bytes(name.encode("ascii"))
        path.chmod(0o600)
        values.append(path)
    return tuple(values)


def source_contract(root):
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    install, contract, plist = trust_files(root)
    result = (
        publish_challenger_cohort_evidence_maintenance_launchd_contract(
            output_root=root / "source",
            repository_root=ROOT,
            runtime_root=runtime,
            python_executable=Path(sys.executable),
            install_receipt_path=install,
            contract_path=contract,
            plist_path=plist,
            clock=lambda: PREPARED,
            _strategy_loader=fixture_strategy_loader,
        )
    )
    return runtime, result


def prepared_inputs(root):
    runtime, source = source_contract(root)
    result = prepare_challenger_cohort_evidence_maintenance_deployment(
        source_contract_path=Path(source["contract_path"]),
        source_plist_path=Path(source["plist_path"]),
        trusted_source_attestation_hash=source["contract_trust_hash"],
        output_root=root / "deployment-output",
        clock=lambda: PREPARED,
        _strategy_loader=fixture_strategy_loader,
    )
    return runtime, source, result


class FakeMaintenanceLaunchctl:
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
        self.bootstrapped = False
        self.calls = []

    @property
    def service(self):
        return f"gui/{self.uid}/{LABEL}"

    def valid_print(self):
        values = [
            self.service,
            LABEL,
            str(self.target),
            self.contract["python_executable"],
            self.contract["repository_root"],
            "crypto_quant.challenger_cohort_evidence_maintenance_cli",
            *self.contract["program_arguments"][3:],
        ]
        if not self.verified_bindings:
            values[-1] = "/wrong/result-root"
        return ("\n".join(values) + "\n").encode("utf-8")

    def __call__(self, argv):
        call = tuple(argv)
        self.calls.append(call)
        if call[1] == "print":
            if self.preloaded or self.bootstrapped:
                return MaintenanceLaunchctlResult(
                    0, self.valid_print(), b""
                )
            return MaintenanceLaunchctlResult(
                113, b"", b"service not found\n"
            )
        if call[1] == "bootstrap":
            if self.bootstrap_returncode == 0:
                self.bootstrapped = True
            return MaintenanceLaunchctlResult(
                self.bootstrap_returncode,
                b"",
                (
                    b""
                    if self.bootstrap_returncode == 0
                    else b"failed\n"
                ),
            )
        raise AssertionError(f"unexpected command: {call}")


def install_inputs(root):
    _runtime, source, deployment = prepared_inputs(root)
    manifest = json.loads(Path(deployment["manifest_path"]).read_text())
    contract = json.loads(
        Path(deployment["candidate_contract_path"]).read_text()
    )
    home = root / "home"
    target = (
        home
        / "Library"
        / "LaunchAgents"
        / f"{LABEL}.plist"
    ).resolve()
    runner = FakeMaintenanceLaunchctl(
        contract=contract,
        target=target,
        uid=os.getuid(),
    )
    times = iter((INSTALLED, VERIFIED))
    values = {
        "manifest_path": Path(deployment["manifest_path"]),
        "trusted_source_attestation_hash": (
            source["contract_trust_hash"]
        ),
        "trusted_candidate_attestation_hash": (
            deployment["candidate_contract_trust_hash"]
        ),
        "receipt_output_root": root / "receipts",
        "clock": lambda: next(times),
        "_home_directory": home,
        "_uid": os.getuid(),
        "_launchctl_runner": runner,
        "_strategy_loader": fixture_strategy_loader,
    }
    return manifest, contract, target, runner, values


class ChallengerCohortEvidenceMaintenanceDeploymentTests(
    unittest.TestCase
):
    def test_snapshot_manifest_is_deterministic_one_hundred_times(self):
        first_records, first_data = _read_source_files(ROOT)
        first_hashes = {
            name: json.dumps(
                {
                    "size": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                },
                sort_keys=True,
            )
            for name, body in first_data.items()
        }
        for _ in range(99):
            records, data = _read_source_files(ROOT)
            self.assertEqual(records, first_records)
            self.assertEqual(
                {
                    name: json.dumps(
                        {
                            "size": len(body),
                            "sha256": hashlib.sha256(body).hexdigest(),
                        },
                        sort_keys=True,
                    )
                    for name, body in data.items()
                },
                first_hashes,
            )

    def test_source_symlink_and_hardlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            (root / "src").mkdir(parents=True)
            shutil.copy2(ROOT / "pyproject.toml", root / "pyproject.toml")
            shutil.copytree(
                ROOT / "src" / "crypto_quant",
                root / "src" / "crypto_quant",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            for relative in (
                "artifacts/challenger-forward/"
                "challenger-episode-cohort-plan-v0.43.0.json",
                "artifacts/challenger-forward/"
                "challenger-episode-economic-plan-v0.37.0.json",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            package_init = (
                root / "src" / "crypto_quant" / "__init__.py"
            )
            original = package_init.read_bytes()
            package_init.unlink()
            package_init.symlink_to(ROOT / "src" / "crypto_quant" / "__init__.py")
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
            ):
                _read_source_files(root)
            package_init.unlink()
            package_init.write_bytes(original)
            hardlink = root / "src" / "crypto_quant" / "hardlink.py"
            os.link(package_init, hardlink)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_SOURCE_INVALID",
            ):
                _read_source_files(root)

    def test_schema_mirrors_are_exact_and_valid(self):
        for name in (
            "challenger-cohort-evidence-maintenance-"
            "deployment-manifest-v1.schema.json",
            "challenger-cohort-evidence-maintenance-"
            "launchd-install-receipt-v1.schema.json",
        ):
            config = ROOT / "config" / name
            package = (
                ROOT / "src" / "crypto_quant" / "schemas" / name
            )
            self.assertEqual(config.read_bytes(), package.read_bytes())
            Draft202012Validator.check_schema(
                json.loads(config.read_text())
            )

    def test_private_snapshot_candidate_and_manifest_are_exact_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime, source, first = prepared_inputs(root)
            second = (
                prepare_challenger_cohort_evidence_maintenance_deployment(
                    source_contract_path=Path(source["contract_path"]),
                    source_plist_path=Path(source["plist_path"]),
                    trusted_source_attestation_hash=(
                        source["contract_trust_hash"]
                    ),
                    output_root=root / "deployment-output",
                    clock=lambda: PREPARED,
                    _strategy_loader=fixture_strategy_loader,
                )
            )
            comparable = dict(second)
            comparable["snapshot_created"] = True
            self.assertEqual(first, comparable)
            self.assertFalse(second["snapshot_created"])
            manifest_path = Path(first["manifest_path"])
            manifest = (
                load_challenger_cohort_evidence_maintenance_deployment(
                    manifest_path=manifest_path,
                    trusted_source_attestation_hash=(
                        source["contract_trust_hash"]
                    ),
                    trusted_candidate_attestation_hash=(
                        first["candidate_contract_trust_hash"]
                    ),
                    _strategy_loader=fixture_strategy_loader,
                )
            )
            self.assertEqual(manifest["manifest_id"], first["manifest_id"])
            self.assertEqual(
                manifest["security_boundary"]["launchctl_command_count"], 0
            )
            self.assertEqual(
                manifest["security_boundary"]["maintenance_invocation_count"],
                0,
            )
            snapshot = Path(first["snapshot_root"])
            self.assertTrue(
                snapshot.is_relative_to(runtime.resolve() / "deployment")
            )
            for entry in snapshot.rglob("*"):
                self.assertFalse(entry.is_symlink())
                self.assertEqual(
                    stat.S_IMODE(entry.stat().st_mode),
                    0o700 if entry.is_dir() else 0o600,
                )
            for key in (
                "manifest_path",
                "candidate_contract_path",
                "candidate_plist_path",
            ):
                self.assertEqual(
                    stat.S_IMODE(Path(first[key]).stat().st_mode), 0o600
                )

    def test_external_trust_and_snapshot_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _runtime, source, deployment = prepared_inputs(root)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVALID",
            ):
                load_challenger_cohort_evidence_maintenance_deployment(
                    manifest_path=Path(deployment["manifest_path"]),
                    trusted_source_attestation_hash="0" * 64,
                    trusted_candidate_attestation_hash=(
                        deployment["candidate_contract_trust_hash"]
                    ),
                    _strategy_loader=fixture_strategy_loader,
                )
            snapshot_init = (
                Path(deployment["snapshot_root"])
                / "src"
                / "crypto_quant"
                / "__init__.py"
            )
            snapshot_init.write_bytes(snapshot_init.read_bytes() + b"\n")
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_INVALID",
            ):
                load_challenger_cohort_evidence_maintenance_deployment(
                    manifest_path=Path(deployment["manifest_path"]),
                    trusted_source_attestation_hash=(
                        source["contract_trust_hash"]
                    ),
                    trusted_candidate_attestation_hash=(
                        deployment["candidate_contract_trust_hash"]
                    ),
                    _strategy_loader=fixture_strategy_loader,
                )

    def test_candidate_inventory_extra_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _runtime, source, deployment = prepared_inputs(root)
            extra = Path(deployment["manifest_path"]).parent / "extra"
            extra.write_bytes(b"unexpected")
            extra.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_READ_FAILED",
            ):
                load_challenger_cohort_evidence_maintenance_deployment(
                    manifest_path=Path(deployment["manifest_path"]),
                    trusted_source_attestation_hash=(
                        source["contract_trust_hash"]
                    ),
                    trusted_candidate_attestation_hash=(
                        deployment["candidate_contract_trust_hash"]
                    ),
                    _strategy_loader=fixture_strategy_loader,
                )

    def test_cli_authority_excludes_install_and_runtime_triggers(self):
        deployment_source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_cohort_evidence_maintenance_deployment_cli.py"
        ).read_text()
        install_source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_cohort_evidence_maintenance_install_cli.py"
        ).read_text()
        for forbidden in (
            "--target",
            "--uid",
            "--domain",
            "--label",
            "--command",
            "--launchctl",
            "--kickstart",
            "--bootout",
            "--maintenance-now",
            "--credential",
            "--api-key",
            "--order",
            "--state",
            "--runner",
        ):
            self.assertNotIn(forbidden, deployment_source)
            self.assertNotIn(forbidden, install_source)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(deployment_main([forbidden, "x"]), 2)
                self.assertEqual(install_main([forbidden, "x"]), 2)


class ChallengerCohortEvidenceMaintenanceInstallTests(
    unittest.TestCase
):
    def test_new_install_is_fixed_loaded_and_receipted_without_running(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, _contract, target, runner, values = install_inputs(
                root
            )
            result = (
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            )
            receipt = (
                load_challenger_cohort_evidence_maintenance_install_receipt(
                    receipt_path=Path(result["receipt_path"]),
                    manifest_path=values["manifest_path"],
                    trusted_source_attestation_hash=values[
                        "trusted_source_attestation_hash"
                    ],
                    trusted_candidate_attestation_hash=values[
                        "trusted_candidate_attestation_hash"
                    ],
                    _strategy_loader=fixture_strategy_loader,
                )
            )
            self.assertEqual(
                result["outcome"],
                "INSTALLED_AND_LOADED_WAITING_FOR_NATURAL_SCHEDULE",
            )
            self.assertEqual(
                result["install_action"], "INSTALLED_AND_BOOTSTRAPPED"
            )
            self.assertFalse(result["run_at_load"])
            self.assertEqual(result["maintenance_invocation_count"], 0)
            self.assertEqual(
                receipt["execution_snapshot"]["tree_hash"],
                manifest["execution_snapshot"]["tree_hash"],
            )
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(
                [call[1] for call in runner.calls],
                ["print", "bootstrap", "print"],
            )

    def test_loaded_exact_service_is_idempotent_without_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, target, runner, values = install_inputs(
                root
            )
            target.parent.mkdir(parents=True, mode=0o700)
            manifest = json.loads(values["manifest_path"].read_text())
            target.write_bytes(
                Path(
                    manifest["install_candidate"]["plist_path"]
                ).read_bytes()
            )
            target.chmod(0o600)
            runner.preloaded = True
            result = (
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            )
            self.assertEqual(
                result["install_action"],
                "ALREADY_INSTALLED_AND_LOADED",
            )
            self.assertEqual(
                [call[1] for call in runner.calls], ["print", "print"]
            )

    def test_target_conflict_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, target, runner, values = install_inputs(
                root
            )
            target.parent.mkdir(parents=True, mode=0o700)
            target.write_bytes(b"user-conflict")
            target.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceInstallError,
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_TARGET_CONFLICT",
            ):
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            self.assertEqual(target.read_bytes(), b"user-conflict")
            self.assertEqual([call[1] for call in runner.calls], ["print"])

    def test_unexpected_preflight_failure_does_not_install(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, target, runner, values = install_inputs(
                root
            )

            def failed_preflight(argv):
                runner.calls.append(tuple(argv))
                return MaintenanceLaunchctlResult(
                    5, b"", b"permission denied\n"
                )

            values["_launchctl_runner"] = failed_preflight
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceInstallError,
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PREFLIGHT_FAILED",
            ):
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            self.assertFalse(target.exists())
            self.assertEqual([call[1] for call in runner.calls], ["print"])

    def test_bootstrap_failure_rolls_back_only_new_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, target, runner, values = install_inputs(
                root
            )
            runner.bootstrap_returncode = 5
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceInstallError,
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_BOOTSTRAP_FAILED",
            ):
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            self.assertFalse(target.exists())
            self.assertEqual(
                [call[1] for call in runner.calls], ["print", "bootstrap"]
            )

    def test_post_bootstrap_print_failure_preserves_loaded_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, target, runner, values = install_inputs(
                root
            )
            runner.verified_bindings = False
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceInstallError,
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_PRINT_VERIFY_FAILED",
            ):
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            self.assertTrue(target.is_file())
            self.assertTrue(runner.bootstrapped)

    def test_receipt_tamper_fails_after_coordinated_self_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _manifest, _contract, _target, _runner, values = (
                install_inputs(root)
            )
            result = (
                install_challenger_cohort_evidence_maintenance_launchd(
                    **values
                )
            )
            receipt = json.loads(Path(result["receipt_path"]).read_text())
            changed = copy.deepcopy(receipt)
            changed["security_boundary"]["maintenance_invocation_count"] = 1
            changed["receipt_hash"] = maintenance_install_receipt_hash(
                changed
            )
            tampered = root / "tampered-receipt.json"
            tampered.write_bytes(
                canonical_json(changed).encode("utf-8")
            )
            tampered.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceInstallError,
                "CHALLENGER_COHORT_MAINTENANCE_INSTALL_RECEIPT_INVALID",
            ):
                load_challenger_cohort_evidence_maintenance_install_receipt(
                    receipt_path=tampered,
                    manifest_path=values["manifest_path"],
                    trusted_source_attestation_hash=values[
                        "trusted_source_attestation_hash"
                    ],
                    trusted_candidate_attestation_hash=values[
                        "trusted_candidate_attestation_hash"
                    ],
                    _strategy_loader=fixture_strategy_loader,
                )

    def test_manifest_coordinated_rehash_cannot_change_snapshot_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _runtime, source, deployment = prepared_inputs(root)
            original = json.loads(
                Path(deployment["manifest_path"]).read_text()
            )
            changed = copy.deepcopy(original)
            changed["execution_snapshot"]["tree_hash"] = "f" * 64
            changed["manifest_hash"] = deployment_manifest_hash(changed)
            tampered = root / "tampered-manifest.json"
            tampered.write_bytes(
                canonical_json(changed).encode("utf-8")
            )
            tampered.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceDeploymentError,
                "CHALLENGER_COHORT_MAINTENANCE_DEPLOYMENT_READ_FAILED",
            ):
                load_challenger_cohort_evidence_maintenance_deployment(
                    manifest_path=tampered,
                    trusted_source_attestation_hash=(
                        source["contract_trust_hash"]
                    ),
                    trusted_candidate_attestation_hash=(
                        deployment["candidate_contract_trust_hash"]
                    ),
                    _strategy_loader=fixture_strategy_loader,
                )


if __name__ == "__main__":
    unittest.main()
