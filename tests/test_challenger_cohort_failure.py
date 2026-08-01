import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_cohort_failure import (
    ChallengerCohortFailureError,
    challenger_cohort_failure_receipt_hash,
    load_challenger_cohort_failure_receipt,
    observe_challenger_cohort_missed_slot_failure,
)
from crypto_quant.challenger_cohort_failure_cli import _parser
from crypto_quant.challenger_launchd_install import LaunchctlResult
from crypto_quant.evidence import artifact_self_hash
from tests import test_challenger_cohort_episode_receipt as cohort_tests


ROOT = Path(__file__).resolve().parents[1]
EVALUATION_PLAN = (
    ROOT
    / "artifacts"
    / "challenger-forward"
    / "challenger-cohort-evaluation-plan-v0.44.0.json"
)
MISSED_SLOT_STDERR = b'{"error":"CHALLENGER_RUNNER_MISSED_SLOT"}\n'


class ChallengerCohortFailureTests(unittest.TestCase):
    def environment(self, root: Path):
        root = Path(root).resolve()
        helper = cohort_tests.ChallengerCohortEpisodeReceiptTests()
        environment = helper.environment(root)
        helper.record(
            environment,
            cohort_tests.PILOT_AND_REJECTIONS
            + [105, 106, 90, 90, 90, 110, 111, 80, 80, 80],
        )
        environment["evaluation_plan_path"] = EVALUATION_PLAN
        environment["failure_output_root"] = root / "cohort-failures"
        environment["service"].runs = 1
        environment["service"].last_exit_code = 1

        def failed_launchctl(argv):
            result = environment["service"](argv)
            return LaunchctlResult(
                result.returncode,
                result.stdout + b"state = not running\n",
                result.stderr,
            )

        environment["failed_launchctl"] = failed_launchctl
        environment["paths"]["stderr"].write_bytes(MISSED_SLOT_STDERR)
        environment["paths"]["stderr"].chmod(0o600)
        return environment

    def observe(self, environment):
        return observe_challenger_cohort_missed_slot_failure(
            cohort_plan_path=environment["cohort_plan_path"],
            evaluation_plan_path=environment["evaluation_plan_path"],
            install_receipt_path=environment["install_receipt_path"],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
            failure_output_root=environment["failure_output_root"],
            clock=lambda: "2026-08-01T08:27:01.000Z",
            _launchctl_runner=environment["failed_launchctl"],
        )

    def test_exact_missed_slot_publishes_loadable_failure_receipt(self):
        """Catches accepting a gap without an immutable loadable receipt."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            state_before = environment["paths"]["state"].read_bytes()
            calls_before = len(environment["service"].calls)

            summary = self.observe(environment)

            self.assertEqual(
                summary["status"], "COHORT_MISSED_SLOT_FAILURE_VERIFIED"
            )
            self.assertEqual(
                summary["next_required_slot"], "2026-08-01T04:00:00.000Z"
            )
            self.assertEqual(summary["market_request_count"], 0)
            self.assertEqual(summary["runner_invocation_count"], 0)
            self.assertEqual(
                len(environment["service"].calls), calls_before + 1
            )
            self.assertEqual(
                environment["paths"]["state"].read_bytes(), state_before
            )
            receipt_path = Path(summary["receipt_path"])
            receipt = load_challenger_cohort_failure_receipt(
                receipt_path=receipt_path,
                cohort_plan_path=environment["cohort_plan_path"],
                evaluation_plan_path=environment["evaluation_plan_path"],
                install_receipt_path=environment["install_receipt_path"],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
            )
            self.assertEqual(
                receipt["eligibility"]["old_cohort"],
                "PERMANENTLY_INELIGIBLE_CONTINUITY_GAP",
            )
            self.assertEqual(
                hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                summary["receipt_file_sha256"],
            )

    def test_cli_exposes_only_frozen_source_and_output_paths(self):
        """Catches adding an authority override to the failure observer CLI."""

        destinations = {action.dest for action in _parser()._actions}
        self.assertEqual(
            destinations,
            {
                "help",
                "cohort_plan_path",
                "evaluation_plan_path",
                "install_receipt_path",
                "contract_path",
                "plist_path",
                "failure_output_root",
            },
        )
        self.assertFalse(
            destinations
            & {
                "clock",
                "service",
                "state",
                "stderr",
                "slot",
                "command",
                "launchctl",
                "runner",
                "maintenance",
                "broker",
                "order",
            }
        )

    def test_schema_mirrors_validate_a_real_failure_receipt(self):
        """Catches shipping an unvalidated or non-packaged receipt shape."""

        config = ROOT / "config" / "challenger-cohort-failure-receipt-v1.schema.json"
        packaged = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-failure-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), packaged.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            summary = self.observe(environment)
            receipt = json.loads(Path(summary["receipt_path"]).read_bytes())
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(receipt))
        )

    def test_rehash_cannot_hide_removed_trusted_slots(self):
        """Catches a self-consistent hash that omits real cohort evidence."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
            summary = self.observe(environment)
            receipt = json.loads(Path(summary["receipt_path"]).read_bytes())
            changed = copy.deepcopy(receipt)
            changed["state"]["cohort_slots"] = []
            changed["state"]["cohort_slots_root_hash"] = business_hash([])
            changed["receipt_hash"] = challenger_cohort_failure_receipt_hash(
                changed
            )
            tampered = root / "tampered.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            tampered.chmod(0o600)

            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_RECEIPT_INVALID",
            ):
                load_challenger_cohort_failure_receipt(
                    receipt_path=tampered,
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                )

    def test_rehash_cannot_hide_running_service_evidence(self):
        """Catches a receipt rewritten to claim the failed job still runs."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
            summary = self.observe(environment)
            receipt = json.loads(Path(summary["receipt_path"]).read_bytes())
            changed = copy.deepcopy(receipt)
            evidence = changed["launchctl_print"]
            evidence["stdout_utf8"] = evidence["stdout_utf8"].replace(
                "state = not running", "state = running"
            )
            body = evidence["stdout_utf8"].encode("utf-8")
            evidence["stdout_size_bytes"] = len(body)
            evidence["stdout_sha256"] = hashlib.sha256(body).hexdigest()
            evidence["command_evidence_hash"] = artifact_self_hash(
                evidence, "command_evidence_hash"
            )
            changed["receipt_hash"] = challenger_cohort_failure_receipt_hash(
                changed
            )
            tampered = root / "tampered-service.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            tampered.chmod(0o600)

            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_RECEIPT_INVALID",
            ):
                load_challenger_cohort_failure_receipt(
                    receipt_path=tampered,
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                )

    def test_output_root_beneath_a_symlink_is_rejected(self):
        """Catches redirecting owner-only evidence through a symlink ancestor."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
            target = root / "redirect-target"
            target.mkdir(mode=0o700)
            link = root / "redirect-link"
            link.symlink_to(target, target_is_directory=True)
            environment["failure_output_root"] = link / "cohort-failures"
            calls_before = len(environment["service"].calls)

            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_OUTPUT_INVALID",
            ):
                self.observe(environment)
            self.assertEqual(
                len(environment["service"].calls), calls_before
            )

    def test_output_root_cannot_overlap_strategy_evidence(self):
        """Catches publishing receipts inside the strategy evidence tree."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            environment["failure_output_root"] = environment["paths"][
                "output"
            ]
            calls_before = len(environment["service"].calls)
            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_OUTPUT_INVALID",
            ):
                self.observe(environment)
            self.assertEqual(
                len(environment["service"].calls), calls_before
            )

    def test_not_late_and_wrong_stderr_fail_before_launchctl(self):
        """Catches declaring failure before the gap or without exact stderr."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            early = self.environment(root / "early")
            calls_before = len(early["service"].calls)
            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_NOT_LATE",
            ):
                observe_challenger_cohort_missed_slot_failure(
                    cohort_plan_path=early["cohort_plan_path"],
                    evaluation_plan_path=early["evaluation_plan_path"],
                    install_receipt_path=early["install_receipt_path"],
                    contract_path=early["contract_path"],
                    plist_path=early["plist_path"],
                    failure_output_root=early["failure_output_root"],
                    clock=lambda: "2026-08-01T04:30:00.000Z",
                    _launchctl_runner=early["failed_launchctl"],
                )
            self.assertEqual(len(early["service"].calls), calls_before)

            wrong = self.environment(root / "wrong-stderr")
            wrong["paths"]["stderr"].write_bytes(
                b'{"error":"SOMETHING_ELSE"}\n'
            )
            wrong["paths"]["stderr"].chmod(0o600)
            calls_before = len(wrong["service"].calls)
            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_STDERR_INVALID",
            ):
                self.observe(wrong)
            self.assertEqual(len(wrong["service"].calls), calls_before)

    def test_duplicate_bundle_and_hardlinked_state_fail_before_launchctl(self):
        """Catches ambiguous bundle evidence and non-exclusive state inodes."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            duplicate = self.environment(root / "duplicate")
            source = sorted(
                duplicate["paths"]["output"].glob(
                    "challenger-forward/source-bundles/*.json"
                )
            )[-1]
            shutil.copy2(source, source.parent / "duplicate.json")
            calls_before = len(duplicate["service"].calls)
            with self.assertRaises(ChallengerCohortFailureError):
                self.observe(duplicate)
            self.assertEqual(
                len(duplicate["service"].calls), calls_before
            )

            linked = self.environment(root / "hardlink")
            os.link(linked["paths"]["state"], root / "state-hardlink")
            calls_before = len(linked["service"].calls)
            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_SOURCE_INVALID",
            ):
                self.observe(linked)
            self.assertEqual(len(linked["service"].calls), calls_before)

    def test_dangling_wal_symlink_is_not_treated_as_absent(self):
        """Catches hiding a SQLite sidecar behind a dangling symlink."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
            wal = Path(f"{environment['paths']['state']}-wal")
            if wal.exists():
                wal.unlink()
            wal.symlink_to(root / "missing-wal-target")
            calls_before = len(environment["service"].calls)
            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_SOURCE_INVALID",
            ):
                self.observe(environment)
            self.assertEqual(
                len(environment["service"].calls), calls_before
            )

    def test_observation_rejects_log_mutation_during_launchctl(self):
        """Catches a snapshot assembled from two different runtime moments."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            stdout = environment["paths"]["stdout"]

            def mutating_launchctl(argv):
                result = environment["failed_launchctl"](argv)
                stdout.write_bytes(stdout.read_bytes() + b"{}\n")
                stdout.chmod(0o600)
                return result

            with self.assertRaisesRegex(
                ChallengerCohortFailureError,
                "CHALLENGER_COHORT_FAILURE_SOURCE_MUTATED",
            ):
                observe_challenger_cohort_missed_slot_failure(
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment["failure_output_root"],
                    clock=lambda: "2026-08-01T08:27:01.000Z",
                    _launchctl_runner=mutating_launchctl,
                )

    def test_identical_observation_is_exactly_idempotent(self):
        """Catches rewriting an already sealed identical failure receipt."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            first = self.observe(environment)
            path = Path(first["receipt_path"])
            before = path.stat()
            expected_bytes = path.read_bytes()
            expected_hash = first["receipt_hash"]
            for _ in range(9):
                current = self.observe(environment)
                self.assertEqual(current["receipt_hash"], expected_hash)
            after = path.stat()
            self.assertEqual(path.read_bytes(), expected_bytes)
            self.assertEqual(after.st_ino, before.st_ino)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
