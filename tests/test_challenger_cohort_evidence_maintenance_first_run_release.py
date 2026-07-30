import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_evidence_maintenance_first_run_release import (
    ChallengerCohortEvidenceMaintenanceFirstRunReleaseError,
    release_challenger_cohort_evidence_maintenance_first_run_receipt,
)
from crypto_quant.challenger_cohort_evidence_maintenance_first_run_release_cli import (
    _parser,
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
        runtime = root / "runtime.json"
        receipt = self.receipt()
        if canonical:
            body = canonical_json(receipt).encode()
        else:
            body = (json.dumps(receipt, indent=2) + "\n").encode()
        runtime.write_bytes(body)
        runtime.chmod(0o600)
        artifact_parent = root / "artifact"
        artifact_parent.mkdir(mode=0o700)
        return {
            "runtime": runtime,
            "artifact": artifact_parent / "receipt.json",
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
