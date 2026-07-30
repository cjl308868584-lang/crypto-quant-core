import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from crypto_quant.challenger_cohort_evidence_maintenance_first_run import (
    ChallengerCohortEvidenceMaintenanceFirstRunError,
    _file_prefix_valid,
    _inventory_prefix_valid,
    _schedule,
    _summary,
    observe_challenger_cohort_evidence_maintenance_first_run,
)
from crypto_quant.challenger_cohort_evidence_maintenance_first_run_cli import (
    _parser,
)
from crypto_quant.challenger_cohort_evidence_maintenance_install import (
    MaintenanceLaunchctlResult,
    _command_evidence,
)


SCHEDULED = datetime(2026, 7, 31, 0, 10, tzinfo=timezone.utc)
SOURCE_TRUST = "a" * 64
CANDIDATE_TRUST = "b" * 64


def file_evidence(path: Path, body: bytes = b"x"):
    return {
        "path": str(path),
        "exists": True,
        "device": 1,
        "inode": 2,
        "owner_uid": 501,
        "mode_octal": "0600",
        "link_count": 1,
        "size_bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def inventory(path: Path):
    return {
        "path": str(path),
        "exists": False,
        "file_count": 0,
        "total_bytes": 0,
        "files": [],
        "inventory_hash": hashlib.sha256(b"[]").hexdigest(),
    }


def maintenance_summary(observed_at="2026-07-31T00:10:01.000Z"):
    return {
        "status": "COHORT_EVIDENCE_NO_COMPLETED_EPISODES",
        "observed_at": observed_at,
        "receipt_stage": {
            "executed": True,
            "status": "COHORT_NOT_STARTED_VERIFIED",
            "cohort_slot_count": 0,
            "completed_episode_count": 0,
            "receipt_created_count": 0,
        },
        "archive_stage": {
            "executed": True,
            "status": "COHORT_DAILY_ARCHIVE_NO_COMPLETED_EPISODES",
            "required_day_count": 0,
            "verified_day_count": 0,
            "network_request_count": 0,
        },
        "result_stage": {
            "executed": False,
            "status": "NOT_EXECUTED_NO_COMPLETED_EPISODES",
        },
        "network_request_count": 0,
        "broker_request_count": 0,
        "order_submission_count": 0,
        "strategy_state_write_count": 0,
        "runner_invocation_count": 0,
    }


class FirstNaturalMaintenanceRunTests(unittest.TestCase):
    def sources(self):
        manifest = {
            "manifest_id": "manifest",
            "manifest_hash": "c" * 64,
            "execution_snapshot": {"tree_hash": "d" * 64},
        }
        contract = {
            "contract_id": "contract",
            "contract_hash": "e" * 64,
            "launchd_plist_sha256": "f" * 64,
            "cadence": {
                "local_launch_hour": 8,
                "local_launch_minute": 10,
                "run_at_load": False,
            },
        }
        install = {
            "receipt_id": "install",
            "receipt_hash": "1" * 64,
            "verified_at": "2026-07-30T20:18:41.761Z",
            "service": (
                "gui/501/"
                "local.crypto-quant.challenger-cohort-evidence-maintenance"
            ),
            "target_path": (
                "/Users/test/Library/LaunchAgents/"
                "local.crypto-quant."
                "challenger-cohort-evidence-maintenance.plist"
            ),
            "target_stat": {"sha256": "2" * 64},
        }
        return manifest, contract, install

    def paths_and_snapshot(self, root: Path, stdout_body=b""):
        paths = {
            "strategy_state": root / "state.sqlite",
            "strategy_stdout": root / "strategy.stdout",
            "strategy_stderr": root / "strategy.stderr",
            "maintenance_stdout": root / "maintenance.stdout",
            "maintenance_stderr": root / "maintenance.stderr",
            "receipt_root": root / "receipts",
            "archive_root": root / "archives",
            "result_root": root / "results",
        }
        paths["maintenance_stdout"].write_bytes(stdout_body)
        paths["maintenance_stderr"].write_bytes(b"")
        snapshot = {
            "strategy_state": file_evidence(paths["strategy_state"]),
            "strategy_stdout": file_evidence(paths["strategy_stdout"]),
            "strategy_stderr": file_evidence(paths["strategy_stderr"]),
            "maintenance_stdout": file_evidence(
                paths["maintenance_stdout"], stdout_body
            ),
            "maintenance_stderr": file_evidence(
                paths["maintenance_stderr"], b""
            ),
            "receipt_inventory": inventory(paths["receipt_root"]),
            "archive_inventory": inventory(paths["archive_root"]),
            "result_inventory": inventory(paths["result_root"]),
        }
        return paths, snapshot

    def observe(
        self,
        *,
        clock,
        runs,
        exit_code,
        service_state="not running",
        stdout_body=b"",
    ):
        root_context = tempfile.TemporaryDirectory()
        self.addCleanup(root_context.cleanup)
        root = Path(root_context.name)
        paths, snapshot = self.paths_and_snapshot(root, stdout_body)
        manifest, contract, install = self.sources()
        print_result = MaintenanceLaunchctlResult(
            returncode=0,
            stdout=b"trusted print",
            stderr=b"",
        )
        evidence = _command_evidence(
            ("/bin/launchctl", "print", install["service"]),
            print_result,
        )
        patches = (
            patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_load_sources",
                return_value=(manifest, contract, install),
            ),
            patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_observation_paths",
                return_value=paths,
            ),
            patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_snapshot",
                side_effect=[snapshot, snapshot],
            ),
            patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_launchctl",
                return_value=(
                    evidence,
                    runs,
                    exit_code,
                    service_state,
                ),
            ),
            patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_publish",
                return_value=root / "receipt.json",
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            return observe_challenger_cohort_evidence_maintenance_first_run(
                install_receipt_path=root / "install.json",
                manifest_path=root / "manifest.json",
                trusted_source_attestation_hash=SOURCE_TRUST,
                trusted_candidate_attestation_hash=CANDIDATE_TRUST,
                receipt_output_root=root / "output",
                clock=lambda: clock,
            )

    def test_schedule_is_first_0810_strictly_after_install(self):
        _, contract, install = self.sources()
        scheduled, rendered, deadline = _schedule(install, contract)
        self.assertEqual(scheduled, SCHEDULED)
        self.assertEqual(rendered, "2026-07-31T00:10:00.000Z")
        self.assertEqual(deadline, "2026-07-31T00:20:00.000Z")

    def test_waiting_uses_launchctl_once_and_publishes_nothing(self):
        result = self.observe(
            clock=SCHEDULED - timedelta(seconds=1),
            runs=0,
            exit_code="(never exited)",
        )
        self.assertEqual(
            result["status"],
            "WAITING_BEFORE_FIRST_NATURAL_MAINTENANCE_RUN",
        )
        self.assertEqual(result["launchctl_print_count"], 1)
        self.assertFalse(result["receipt_published"])
        self.assertEqual(result["maintenance_invocation_count"], 0)

    def test_pending_only_exists_within_fixed_deadline(self):
        result = self.observe(
            clock=SCHEDULED + timedelta(minutes=5),
            runs=0,
            exit_code="(never exited)",
        )
        self.assertEqual(
            result["status"], "FIRST_NATURAL_MAINTENANCE_RUN_PENDING"
        )
        with self.assertRaisesRegex(
            ChallengerCohortEvidenceMaintenanceFirstRunError,
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_MISSED",
        ):
            self.observe(
                clock=SCHEDULED + timedelta(minutes=11),
                runs=0,
                exit_code="(never exited)",
            )

    def test_running_service_is_pending_not_completed(self):
        result = self.observe(
            clock=SCHEDULED + timedelta(minutes=1),
            runs=1,
            exit_code="0",
            service_state="running",
        )
        self.assertEqual(
            result["status"], "FIRST_NATURAL_MAINTENANCE_RUN_PENDING"
        )
        self.assertFalse(result["receipt_published"])

    def test_nonzero_exit_fails_without_receipt(self):
        with self.assertRaisesRegex(
            ChallengerCohortEvidenceMaintenanceFirstRunError,
            "CHALLENGER_COHORT_MAINTENANCE_FIRST_RUN_FAILED",
        ):
            self.observe(
                clock=SCHEDULED + timedelta(minutes=1),
                runs=1,
                exit_code="1",
            )

    def test_success_validates_one_summary_and_builds_receipt(self):
        body = (
            json.dumps(
                maintenance_summary(),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        result = self.observe(
            clock=SCHEDULED + timedelta(minutes=2),
            runs=1,
            exit_code="0",
            stdout_body=body,
        )
        self.assertEqual(
            result["status"],
            "FIRST_NATURAL_MAINTENANCE_RUN_COMPLETED_VERIFIED",
        )
        self.assertTrue(result["receipt_published"])
        self.assertEqual(
            result["maintenance_status"],
            "COHORT_EVIDENCE_NO_COMPLETED_EPISODES",
        )
        self.assertEqual(result["network_request_count"], 0)
        self.assertEqual(result["strategy_state_write_count"], 0)

    def test_summary_rejects_extra_line_and_security_tamper(self):
        good = maintenance_summary()
        encoded = json.dumps(good).encode()
        with self.assertRaisesRegex(
            ChallengerCohortEvidenceMaintenanceFirstRunError,
            "SUMMARY_INVALID",
        ):
            _summary(
                encoded + b"\n{}\n",
                scheduled=SCHEDULED,
                observed=SCHEDULED + timedelta(minutes=1),
            )
        changed = dict(good, order_submission_count=1)
        with self.assertRaisesRegex(
            ChallengerCohortEvidenceMaintenanceFirstRunError,
            "SUMMARY_INVALID",
        ):
            _summary(
                json.dumps(changed).encode(),
                scheduled=SCHEDULED,
                observed=SCHEDULED + timedelta(minutes=1),
            )

    def test_observation_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, snapshot = self.paths_and_snapshot(root)
            changed = dict(snapshot)
            changed["strategy_state"] = dict(
                snapshot["strategy_state"], sha256="9" * 64
            )
            manifest, contract, install = self.sources()
            with patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_load_sources",
                return_value=(manifest, contract, install),
            ), patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_observation_paths",
                return_value=paths,
            ), patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_snapshot",
                side_effect=[snapshot, changed],
            ), patch(
                "crypto_quant."
                "challenger_cohort_evidence_maintenance_first_run."
                "_launchctl",
                return_value=(
                    {},
                    0,
                    "(never exited)",
                    "not running",
                ),
            ):
                with self.assertRaisesRegex(
                    ChallengerCohortEvidenceMaintenanceFirstRunError,
                    "OBSERVATION_DRIFT",
                ):
                    observe_challenger_cohort_evidence_maintenance_first_run(
                        install_receipt_path=root / "install",
                        manifest_path=root / "manifest",
                        trusted_source_attestation_hash=SOURCE_TRUST,
                        trusted_candidate_attestation_hash=CANDIDATE_TRUST,
                        receipt_output_root=root / "output",
                        clock=lambda: SCHEDULED - timedelta(seconds=1),
                    )

    def test_loader_prefix_rules_allow_only_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "maintenance.stdout"
            log.write_bytes(b"first\n")
            observed = {
                **file_evidence(log, b"first\n"),
                "path": str(log.resolve()),
                "device": log.stat().st_dev,
                "inode": log.stat().st_ino,
                "owner_uid": log.stat().st_uid,
            }
            log.chmod(0o600)
            log.write_bytes(b"first\nsecond\n")
            self.assertTrue(_file_prefix_valid(observed, log))
            log.write_bytes(b"other\nsecond\n")
            self.assertFalse(_file_prefix_valid(observed, log))

            evidence_root = root / "evidence"
            evidence_root.mkdir(mode=0o700)
            first = evidence_root / "one.json"
            first.write_bytes(b"one")
            first.chmod(0o600)
            frozen = {
                "path": str(evidence_root.resolve()),
                "exists": True,
                "file_count": 1,
                "total_bytes": 3,
                "files": [
                    {
                        "path": "one.json",
                        "size_bytes": 3,
                        "sha256": hashlib.sha256(b"one").hexdigest(),
                    }
                ],
                "inventory_hash": hashlib.sha256(
                    json.dumps(
                        [
                            {
                                "path": "one.json",
                                "sha256": hashlib.sha256(
                                    b"one"
                                ).hexdigest(),
                                "size_bytes": 3,
                            }
                        ],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
            second = evidence_root / "two.json"
            second.write_bytes(b"two")
            second.chmod(0o600)
            self.assertTrue(
                _inventory_prefix_valid(frozen, evidence_root)
            )
            first.write_bytes(b"changed")
            self.assertFalse(
                _inventory_prefix_valid(frozen, evidence_root)
            )

    def test_schema_mirror_and_cli_authority(self):
        root = Path(__file__).resolve().parents[1]
        config = (
            root
            / "config"
            / "challenger-cohort-evidence-maintenance-first-run-"
            "receipt-v1.schema.json"
        )
        package = (
            root
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-evidence-maintenance-first-run-"
            "receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        Draft202012Validator.check_schema(json.loads(config.read_text()))
        actions = {action.dest for action in _parser()._actions}
        self.assertEqual(
            actions,
            {
                "help",
                "install_receipt_path",
                "manifest_path",
                "trusted_source_attestation_hash",
                "trusted_candidate_attestation_hash",
                "receipt_output_root",
            },
        )
        forbidden = {
            "kickstart",
            "bootstrap",
            "runner",
            "broker",
            "order",
            "network",
            "maintenance_now",
            "service",
            "label",
            "uid",
            "schedule",
            "log",
        }
        self.assertFalse(actions & forbidden)


if __name__ == "__main__":
    unittest.main()
