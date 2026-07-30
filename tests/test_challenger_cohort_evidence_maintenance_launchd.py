import copy
import io
import json
import os
import plistlib
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator

from crypto_quant.challenger_cohort_evidence_maintenance_launchd import (
    ChallengerCohortEvidenceMaintenanceLaunchdError,
    build_challenger_cohort_evidence_maintenance_launchd_contract,
    challenger_cohort_evidence_maintenance_launchd_reasons,
    challenger_cohort_evidence_maintenance_launchd_trust_hash,
    load_challenger_cohort_evidence_maintenance_launchd_contract,
    publish_challenger_cohort_evidence_maintenance_launchd_contract,
)
from crypto_quant.challenger_cohort_evidence_maintenance_launchd_cli import (
    main as launchd_main,
)
from crypto_quant.evidence import artifact_self_hash


ROOT = Path(__file__).resolve().parents[1]
CREATED = datetime(2026, 7, 31, 4, 20, tzinfo=timezone.utc)


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
    paths = []
    for name in ("install.json", "strategy-contract.json", "strategy.plist"):
        path = root / name
        path.write_bytes(name.encode("ascii"))
        path.chmod(0o600)
        paths.append(path)
    return tuple(paths)


def inputs(root):
    runtime = root / "runtime"
    runtime.mkdir(mode=0o700)
    install, contract, plist = trust_files(root)
    return {
        "repository_root": ROOT,
        "runtime_root": runtime,
        "python_executable": Path(sys.executable),
        "install_receipt_path": install,
        "contract_path": contract,
        "plist_path": plist,
        "created_at": CREATED,
        "_strategy_loader": fixture_strategy_loader,
    }


class ChallengerCohortEvidenceMaintenanceLaunchdTests(unittest.TestCase):
    def test_fixed_daily_uncredentialed_contract_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            values = inputs(Path(directory))
            contract, body = (
                build_challenger_cohort_evidence_maintenance_launchd_contract(
                    **values
                )
            )
            trust = (
                challenger_cohort_evidence_maintenance_launchd_trust_hash(
                    contract
                )
            )
            self.assertEqual(
                challenger_cohort_evidence_maintenance_launchd_reasons(
                    contract,
                    body,
                    trust,
                    _strategy_loader=fixture_strategy_loader,
                ),
                (),
            )
            plist = plistlib.loads(body)
            self.assertEqual(
                plist["Label"],
                "local.crypto-quant."
                "challenger-cohort-evidence-maintenance",
            )
            self.assertEqual(
                plist["StartCalendarInterval"],
                [{"Hour": 8, "Minute": 10}],
            )
            self.assertFalse(plist["RunAtLoad"])
            self.assertEqual(
                plist["EnvironmentVariables"],
                {"PYTHONPATH": str(ROOT / "src")},
            )
            self.assertEqual(plist["Umask"], 0o077)
            arguments = plist["ProgramArguments"]
            self.assertEqual(
                arguments[1:3],
                [
                    "-m",
                    "crypto_quant."
                    "challenger_cohort_evidence_maintenance_cli",
                ],
            )
            self.assertEqual(arguments[3::2], [
                "--cohort-plan-path",
                "--economic-plan-path",
                "--episode-receipt-output-root",
                "--install-receipt-path",
                "--contract-path",
                "--plist-path",
                "--archive-output-root",
                "--result-output-root",
            ])
            self.assertNotIn(
                "challenger_forward_runner_cli", " ".join(arguments)
            )

    def test_schema_mirror_is_exact_and_valid(self):
        config = (
            ROOT
            / "config"
            / "challenger-cohort-evidence-maintenance-"
            "launchd-contract-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / config.name
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))

    def test_publish_load_permissions_idempotency_and_no_evidence_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            arguments = {
                name: value
                for name, value in values.items()
                if name != "created_at"
            }
            result = (
                publish_challenger_cohort_evidence_maintenance_launchd_contract(
                    output_root=root / "output",
                    clock=lambda: CREATED,
                    **arguments,
                )
            )
            retry = (
                publish_challenger_cohort_evidence_maintenance_launchd_contract(
                    output_root=root / "output",
                    clock=lambda: CREATED,
                    **arguments,
                )
            )
            self.assertEqual(result, retry)
            for name in ("contract_path", "plist_path"):
                path = Path(result[name])
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(
                stat.S_IMODE(Path(result["contract_path"]).parent.stat().st_mode),
                0o700,
            )
            self.assertEqual(
                stat.S_IMODE((root / "output").stat().st_mode),
                0o700,
            )
            self.assertEqual(
                stat.S_IMODE((root / "runtime" / "log").stat().st_mode),
                0o700,
            )
            for name in (
                "cohort-receipts",
                "cohort-archives",
                "cohort-results",
            ):
                self.assertFalse((root / "runtime" / name).exists())
            loaded = (
                load_challenger_cohort_evidence_maintenance_launchd_contract(
                    contract_path=Path(result["contract_path"]),
                    plist_path=Path(result["plist_path"]),
                    trusted_attestation_hash=result["contract_trust_hash"],
                    _strategy_loader=fixture_strategy_loader,
                )
            )
            self.assertEqual(loaded["contract_id"], result["contract_id"])
            self.assertEqual(result["outcome"], "GENERATED_NOT_INSTALLED")
            self.assertFalse(result["launchctl_invoked"])
            self.assertEqual(result["render_network_request_count"], 0)

    def test_loader_requires_independent_trusted_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            result = (
                publish_challenger_cohort_evidence_maintenance_launchd_contract(
                    output_root=root / "output",
                    clock=lambda: CREATED,
                    **{
                        name: value
                        for name, value in values.items()
                        if name != "created_at"
                    },
                )
            )
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceLaunchdError,
                "LAUNCHD_INVALID",
            ):
                load_challenger_cohort_evidence_maintenance_launchd_contract(
                    contract_path=Path(result["contract_path"]),
                    plist_path=Path(result["plist_path"]),
                    trusted_attestation_hash="0" * 64,
                    _strategy_loader=fixture_strategy_loader,
                )

    def test_semantic_mutations_fail_even_after_self_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            values = inputs(Path(directory))
            contract, body = (
                build_challenger_cohort_evidence_maintenance_launchd_contract(
                    **values
                )
            )
            mutations = (
                ("arguments", lambda value: value["program_arguments"].__setitem__(
                    -1, "/tmp/attacker"
                )),
                ("schedule", lambda value: value["cadence"].__setitem__(
                    "local_launch_minute", 11
                )),
                ("security", lambda value: value["security_boundary"].__setitem__(
                    "runner_invocation_count", 1
                )),
                ("environment", lambda value: value[
                    "environment_variable_names"
                ].append("HOME")),
            )
            for name, mutate in mutations:
                with self.subTest(name=name):
                    changed = copy.deepcopy(contract)
                    mutate(changed)
                    changed["contract_hash"] = artifact_self_hash(
                        changed, "contract_hash"
                    )
                    trust = (
                        challenger_cohort_evidence_maintenance_launchd_trust_hash(
                            changed
                        )
                    )
                    self.assertTrue(
                        challenger_cohort_evidence_maintenance_launchd_reasons(
                            changed,
                            body,
                            trust,
                            _strategy_loader=fixture_strategy_loader,
                        )
                    )

    def test_plist_or_strategy_source_change_fails_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            contract, body = (
                build_challenger_cohort_evidence_maintenance_launchd_contract(
                    **values
                )
            )
            trust = (
                challenger_cohort_evidence_maintenance_launchd_trust_hash(
                    contract
                )
            )
            self.assertTrue(
                challenger_cohort_evidence_maintenance_launchd_reasons(
                    contract,
                    body + b"x",
                    trust,
                    _strategy_loader=fixture_strategy_loader,
                )
            )
            values["install_receipt_path"].write_bytes(b"changed")
            self.assertTrue(
                challenger_cohort_evidence_maintenance_launchd_reasons(
                    contract,
                    body,
                    trust,
                    _strategy_loader=fixture_strategy_loader,
                )
            )

    def test_timezone_repository_runtime_python_and_trust_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            with patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_launchd."
                "_timezone_link_target",
                return_value="/var/db/timezone/zoneinfo/UTC",
            ), patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_launchd."
                "time.localtime",
                return_value=SimpleNamespace(tm_gmtoff=0, tm_isdst=0),
            ):
                with self.assertRaisesRegex(
                    ChallengerCohortEvidenceMaintenanceLaunchdError,
                    "TIMEZONE_INVALID",
                ):
                    build_challenger_cohort_evidence_maintenance_launchd_contract(
                        **values
                    )
            for key, bad in (
                ("repository_root", root / "missing"),
                ("runtime_root", root / "missing-runtime"),
                ("python_executable", root / "missing-python"),
            ):
                with self.subTest(key=key):
                    changed = dict(values)
                    changed[key] = bad
                    with self.assertRaises(
                        ChallengerCohortEvidenceMaintenanceLaunchdError
                    ):
                        build_challenger_cohort_evidence_maintenance_launchd_contract(
                            **changed
                        )
            values["install_receipt_path"].chmod(0o644)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceLaunchdError,
                "TRUST_INVALID",
            ):
                build_challenger_cohort_evidence_maintenance_launchd_contract(
                    **values
                )

    def test_output_inventory_conflict_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            scheduler = (
                root
                / "output"
                / "challenger-cohort-evidence-maintenance-scheduler"
            )
            scheduler.mkdir(parents=True)
            conflict = scheduler / "user-file"
            conflict.write_text("preserve")
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceLaunchdError,
                "INVENTORY_INVALID",
            ):
                publish_challenger_cohort_evidence_maintenance_launchd_contract(
                    output_root=root / "output",
                    clock=lambda: CREATED,
                    **{
                        name: value
                        for name, value in values.items()
                        if name != "created_at"
                    },
                )
            self.assertEqual(conflict.read_text(), "preserve")

    def test_contract_is_deterministic_one_hundred_times(self):
        with tempfile.TemporaryDirectory() as directory:
            values = inputs(Path(directory))
            expected = (
                build_challenger_cohort_evidence_maintenance_launchd_contract(
                    **values
                )
            )
            for _ in range(100):
                self.assertEqual(
                    build_challenger_cohort_evidence_maintenance_launchd_contract(
                        **values
                    ),
                    expected,
                )

    def test_cli_only_renders_and_exposes_no_install_or_runtime_selectors(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(launchd_main(["--help"]), 0)
        help_text = output.getvalue()
        for required in (
            "--repository-root",
            "--runtime-root",
            "--python-executable",
            "--install-receipt-path",
            "--contract-path",
            "--plist-path",
            "--output-root",
        ):
            self.assertIn(required, help_text)
        for forbidden in (
            "--bootstrap",
            "--install-target",
            "--load",
            "--launchctl",
            "--label",
            "--schedule",
            "--url",
            "--credential",
            "--api-key",
            "--order",
            "--state",
            "--runner",
        ):
            self.assertNotIn(forbidden, help_text)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(launchd_main([forbidden, "x"]), 2)
        source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_cohort_evidence_maintenance_launchd_cli.py"
        ).read_text()
        for forbidden in (
            "subprocess",
            "challenger_forward_runner",
            "Broker",
            "credential",
            "order_submission",
        ):
            self.assertNotIn(forbidden, source)

    def test_cli_renders_fixture_without_installing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            values = inputs(root)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = launchd_main(
                    [
                        "--repository-root",
                        str(values["repository_root"]),
                        "--runtime-root",
                        str(values["runtime_root"]),
                        "--python-executable",
                        str(values["python_executable"]),
                        "--install-receipt-path",
                        str(values["install_receipt_path"]),
                        "--contract-path",
                        str(values["contract_path"]),
                        "--plist-path",
                        str(values["plist_path"]),
                        "--output-root",
                        str(root / "output"),
                    ],
                    clock=lambda: CREATED,
                    strategy_loader=fixture_strategy_loader,
                )
            self.assertEqual(code, 0)
            summary = json.loads(stdout.getvalue())
            self.assertEqual(summary["outcome"], "GENERATED_NOT_INSTALLED")
            self.assertFalse(summary["launchctl_invoked"])


if __name__ == "__main__":
    unittest.main()
