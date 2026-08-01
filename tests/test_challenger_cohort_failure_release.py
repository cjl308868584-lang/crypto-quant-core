import os
import stat
import tempfile
import unittest
from pathlib import Path

from crypto_quant.challenger_cohort_failure import (
    load_challenger_cohort_failure_receipt,
)
from crypto_quant.challenger_cohort_failure_release import (
    ChallengerCohortFailureReleaseError,
    release_challenger_cohort_failure_receipt,
)
from crypto_quant.challenger_cohort_failure_release_cli import _parser
from tests import test_challenger_cohort_failure as failure_tests


ARTIFACT_NAME = (
    "challenger-cohort-missed-slot-failure-receipt-v0.54.0.json"
)


class ChallengerCohortFailureReleaseTests(unittest.TestCase):
    def environment(self, root: Path):
        helper = failure_tests.ChallengerCohortFailureTests()
        runtime = helper.environment(root / "runtime")
        observed = helper.observe(runtime)
        artifact_parent = root / "artifacts"
        artifact_parent.mkdir(mode=0o700)
        return {
            "runtime": runtime,
            "runtime_receipt": Path(observed["receipt_path"]),
            "artifact": artifact_parent / ARTIFACT_NAME,
        }

    def release(self, environment):
        runtime = environment["runtime"]
        return release_challenger_cohort_failure_receipt(
            runtime_receipt_path=environment["runtime_receipt"],
            artifact_output_path=environment["artifact"],
            cohort_plan_path=runtime["cohort_plan_path"],
            evaluation_plan_path=runtime["evaluation_plan_path"],
            install_receipt_path=runtime["install_receipt_path"],
            contract_path=runtime["contract_path"],
            plist_path=runtime["plist_path"],
        )

    def test_exact_release_is_loadable_owner_only_and_idempotent(self):
        """Catches transforming, overwriting, or failing to replay Git bytes."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            first = self.release(environment)
            artifact = environment["artifact"]
            before = artifact.stat()
            second = self.release(environment)
            after = artifact.stat()

            self.assertTrue(first["artifact_created"])
            self.assertFalse(second["artifact_created"])
            self.assertTrue(first["runtime_and_artifact_bytes_equal"])
            self.assertEqual(
                artifact.read_bytes(),
                environment["runtime_receipt"].read_bytes(),
            )
            self.assertEqual(stat.S_IMODE(after.st_mode), 0o600)
            self.assertEqual(after.st_ino, before.st_ino)
            self.assertEqual(after.st_mtime_ns, before.st_mtime_ns)
            receipt = load_challenger_cohort_failure_receipt(
                receipt_path=artifact,
                cohort_plan_path=environment["runtime"][
                    "cohort_plan_path"
                ],
                evaluation_plan_path=environment["runtime"][
                    "evaluation_plan_path"
                ],
                install_receipt_path=environment["runtime"][
                    "install_receipt_path"
                ],
                contract_path=environment["runtime"]["contract_path"],
                plist_path=environment["runtime"]["plist_path"],
            )
            self.assertEqual(receipt["receipt_id"], first["receipt_id"])

    def test_release_cli_has_no_runtime_or_economic_authority(self):
        """Catches adding a trigger, selector, or economic input to release."""

        destinations = {action.dest for action in _parser()._actions}
        self.assertEqual(
            destinations,
            {
                "help",
                "release_kind",
                "runtime_receipt_path",
                "artifact_output_path",
                "cohort_plan_path",
                "evaluation_plan_path",
                "install_receipt_path",
                "contract_path",
                "plist_path",
            },
        )
        self.assertFalse(
            destinations
            & {
                "clock",
                "service",
                "command",
                "launchctl",
                "runner",
                "maintenance",
                "network",
                "broker",
                "order",
                "date",
                "price",
                "fee",
                "pnl",
            }
        )

    def test_runtime_mutation_during_release_rolls_back_new_artifact(self):
        """Catches claiming equality after the runtime receipt changed."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            calls = 0

            def mutating_loader(**kwargs):
                nonlocal calls
                receipt = load_challenger_cohort_failure_receipt(**kwargs)
                calls += 1
                if calls == 1:
                    environment["runtime_receipt"].write_bytes(b"{}")
                    environment["runtime_receipt"].chmod(0o600)
                return receipt

            runtime = environment["runtime"]
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "REPLAY_INVALID",
            ):
                release_challenger_cohort_failure_receipt(
                    runtime_receipt_path=environment["runtime_receipt"],
                    artifact_output_path=environment["artifact"],
                    cohort_plan_path=runtime["cohort_plan_path"],
                    evaluation_plan_path=runtime["evaluation_plan_path"],
                    install_receipt_path=runtime["install_receipt_path"],
                    contract_path=runtime["contract_path"],
                    plist_path=runtime["plist_path"],
                    _receipt_loader=mutating_loader,
                )
            self.assertFalse(environment["artifact"].exists())

    def test_conflict_wrong_name_symlink_and_hardlink_fail_closed(self):
        """Catches overwrite, target selection, and aliased runtime sources."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            conflict = self.environment(root / "conflict")
            conflict["artifact"].write_bytes(b"do-not-overwrite")
            conflict["artifact"].chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "RELEASE_CONFLICT",
            ):
                self.release(conflict)
            self.assertEqual(
                conflict["artifact"].read_bytes(), b"do-not-overwrite"
            )

            wrong = self.environment(root / "wrong-name")
            wrong["artifact"] = wrong["artifact"].with_name("wrong.json")
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "TARGET_INVALID",
            ):
                self.release(wrong)

            symlinked = self.environment(root / "symlink")
            source = symlinked["runtime_receipt"]
            link = root / "runtime-link.json"
            link.symlink_to(source)
            symlinked["runtime_receipt"] = link
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "SOURCE_INVALID",
            ):
                self.release(symlinked)

            hardlinked = self.environment(root / "hardlink")
            os.link(
                hardlinked["runtime_receipt"], root / "runtime-hardlink.json"
            )
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "SOURCE_INVALID",
            ):
                self.release(hardlinked)

    def test_post_publish_loader_mismatch_removes_only_new_artifact(self):
        """Catches retaining bytes that production replay did not accept."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            calls = 0

            def mismatching_loader(**kwargs):
                nonlocal calls
                receipt = load_challenger_cohort_failure_receipt(**kwargs)
                calls += 1
                if calls == 2:
                    return dict(receipt, receipt_hash="f" * 64)
                return receipt

            runtime = environment["runtime"]
            with self.assertRaisesRegex(
                ChallengerCohortFailureReleaseError,
                "REPLAY_INVALID",
            ):
                release_challenger_cohort_failure_receipt(
                    runtime_receipt_path=environment["runtime_receipt"],
                    artifact_output_path=environment["artifact"],
                    cohort_plan_path=runtime["cohort_plan_path"],
                    evaluation_plan_path=runtime["evaluation_plan_path"],
                    install_receipt_path=runtime["install_receipt_path"],
                    contract_path=runtime["contract_path"],
                    plist_path=runtime["plist_path"],
                    _receipt_loader=mismatching_loader,
                )
            self.assertFalse(environment["artifact"].exists())
            self.assertTrue(environment["runtime_receipt"].exists())


if __name__ == "__main__":
    unittest.main()
