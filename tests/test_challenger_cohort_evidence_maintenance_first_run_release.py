import hashlib
import ast
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_evidence_maintenance_first_run_release import (
    ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
    release_challenger_cohort_evidence_maintenance_first_run_receipt,
)
from crypto_quant.challenger_cohort_evidence_maintenance_first_run_release_cli import (
    _parser,
    main,
)


SOURCE_TRUST = "a" * 64
CANDIDATE_TRUST = "b" * 64


class FirstNaturalMaintenanceRunReleaseTests(unittest.TestCase):
    def receipt(self):
        return {
            "$schema": (
                "./challenger-cohort-evidence-maintenance-first-run-"
                "receipt-v1.schema.json"
            ),
            "schema_version": "1.0.0",
            "receipt_id": (
                "challenger_cohort_evidence_maintenance_first_run_"
                "receipt_" + "c" * 64
            ),
            "receipt_hash": "d" * 64,
            "observation_status": (
                "FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED"
            ),
        }

    def environment(self, root: Path, *, canonical=True):
        receipt = self.receipt()
        runtime_parent = root / "maintenance-first-run-receipts"
        runtime_parent.mkdir(mode=0o700, parents=True)
        runtime = runtime_parent / f"{receipt['receipt_id']}.json"
        if canonical:
            body = canonical_json(receipt).encode()
        else:
            body = (json.dumps(receipt, indent=2) + "\n").encode()
        runtime.write_bytes(body)
        runtime.chmod(0o600)
        artifact_parent = root / "artifact"
        artifact_parent.mkdir(mode=0o700, parents=True)
        return {
            "runtime": runtime,
            "artifact": (
                artifact_parent
                / "challenger-cohort-evidence-maintenance-first-run-"
                "receipt-v0.53.0.json"
            ),
            "receipt": receipt,
            "body": body,
        }

    def release(self, environment, *, loader=None):
        selected_loader = (
            loader
            if loader is not None
            else lambda **_kwargs: environment["receipt"]
        )
        return (
            release_challenger_cohort_evidence_maintenance_first_run_receipt(
                runtime_receipt_path=environment["runtime"],
                install_receipt_path=Path("/trust/install.json"),
                manifest_path=Path("/trust/manifest.json"),
                trusted_source_attestation_hash=SOURCE_TRUST,
                trusted_candidate_attestation_hash=CANDIDATE_TRUST,
                artifact_output_path=environment["artifact"],
                _receipt_loader=selected_loader,
            )
        )

    def test_exact_release_is_owner_only_loadable_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            calls = []

            def loader(**kwargs):
                calls.append(kwargs)
                return environment["receipt"]

            first = self.release(environment, loader=loader)
            second = self.release(environment, loader=loader)
            artifact = environment["artifact"]
            self.assertEqual(
                artifact.read_bytes(), environment["runtime"].read_bytes()
            )
            self.assertEqual(
                first["file_sha256"],
                hashlib.sha256(environment["body"]).hexdigest(),
            )
            self.assertTrue(first["artifact_created"])
            self.assertFalse(second["artifact_created"])
            self.assertTrue(first["runtime_and_artifact_bytes_equal"])
            self.assertEqual(stat.S_IMODE(artifact.stat().st_mode), 0o600)
            self.assertEqual(len(calls), 4)
            self.assertEqual(
                calls[0]["receipt_path"], environment["runtime"].resolve()
            )
            self.assertEqual(calls[1]["receipt_path"], artifact.resolve())
            self.assertEqual(first["maintenance_invocation_count"], 0)
            self.assertEqual(first["launchctl_command_count"], 0)

    def test_noncanonical_runtime_receipt_fails_without_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(
                Path(directory), canonical=False
            )
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "RECEIPT_INVALID",
            ):
                self.release(environment)
            self.assertFalse(environment["artifact"].exists())

    def test_conflict_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            environment["artifact"].write_bytes(b"different")
            environment["artifact"].chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "RELEASE_CONFLICT",
            ):
                self.release(environment)
            self.assertEqual(
                environment["artifact"].read_bytes(), b"different"
            )

    def test_source_symlink_and_hardlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root)
            original = environment["runtime"]
            link = root / "link.json"
            link.symlink_to(original)
            environment["runtime"] = link
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "SOURCE_INVALID",
            ):
                self.release(environment)
            environment["runtime"] = original
            hardlink = root / "hardlink.json"
            os.link(original, hardlink)
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "SOURCE_INVALID",
            ):
                self.release(environment)

    def test_replay_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            calls = 0

            def loader(**_kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return environment["receipt"]
                return dict(environment["receipt"], receipt_hash="e" * 64)

            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "REPLAY_INVALID",
            ):
                self.release(environment, loader=loader)
            self.assertFalse(environment["artifact"].exists())

    def test_cli_missing_runtime_receipt_is_structured_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "artifact"
            parent.mkdir(mode=0o700)
            artifact = (
                parent
                / "challenger-cohort-evidence-maintenance-first-run-"
                "receipt-v0.53.0.json"
            )
            output = StringIO()
            errors = StringIO()
            with redirect_stdout(output), redirect_stderr(errors):
                status = main(
                    [
                        "--runtime-receipt-path",
                        str(root / "missing.json"),
                        "--install-receipt-path",
                        "/trust/install.json",
                        "--manifest-path",
                        "/trust/manifest.json",
                        "--trusted-source-attestation-hash",
                        SOURCE_TRUST,
                        "--trusted-candidate-attestation-hash",
                        CANDIDATE_TRUST,
                        "--artifact-output-path",
                        str(artifact),
                    ]
                )
            self.assertEqual(status, 1)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(
                json.loads(errors.getvalue()),
                {
                    "error": (
                        "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_"
                        "RELEASE_SOURCE_INVALID"
                    )
                },
            )
            self.assertFalse(artifact.exists())

    def test_wrong_runtime_identity_or_artifact_name_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root)
            wrong_runtime = root / "wrong.json"
            environment["runtime"].replace(wrong_runtime)
            environment["runtime"] = wrong_runtime
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "RECEIPT_INVALID",
            ):
                self.release(environment)
            environment = self.environment(root / "second")
            environment["artifact"] = (
                environment["artifact"].parent / "wrong-name.json"
            )
            with self.assertRaisesRegex(
                ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
                "TARGET_INVALID",
            ):
                self.release(environment)

    def test_source_imports_have_no_runtime_or_network_authority(self):
        root = Path(__file__).resolve().parents[1]
        sources = [
            root
            / "src"
            / "crypto_quant"
            / "challenger_cohort_evidence_maintenance_first_run_release.py",
            root
            / "src"
            / "crypto_quant"
            / (
                "challenger_cohort_evidence_maintenance_first_run_"
                "release_cli.py"
            ),
        ]
        imported = set()
        texts = []
        for source in sources:
            text = source.read_text(encoding="utf-8")
            texts.append(text)
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
        self.assertFalse(
            imported
            & {
                "subprocess",
                "urllib",
                "urllib.request",
                "requests",
                "socket",
                "crypto_quant.challenger_cohort_evidence_maintenance",
                "crypto_quant.challenger_forward_runner",
            }
        )
        joined = "\n".join(texts)
        for forbidden in (
            "/bin/launchctl",
            "kickstart",
            "bootstrap",
            "2026-07-31T00:10:00.000Z",
            "/Users/chenm4/Library/Application Support/CryptoQuant",
        ):
            self.assertNotIn(forbidden, joined)

    def test_cli_authority_has_no_runtime_trigger_or_selectors(self):
        actions = {action.dest for action in _parser()._actions}
        self.assertEqual(
            actions,
            {
                "help",
                "runtime_receipt_path",
                "install_receipt_path",
                "manifest_path",
                "trusted_source_attestation_hash",
                "trusted_candidate_attestation_hash",
                "artifact_output_path",
            },
        )
        forbidden = {
            "clock",
            "schedule",
            "service",
            "log",
            "state",
            "status",
            "summary",
            "pnl",
            "date",
            "url",
            "network",
            "credential",
            "broker",
            "order",
            "runner",
            "maintenance_now",
            "command",
            "launchctl",
            "kickstart",
            "bootstrap",
        }
        self.assertFalse(actions & forbidden)


if __name__ == "__main__":
    unittest.main()
