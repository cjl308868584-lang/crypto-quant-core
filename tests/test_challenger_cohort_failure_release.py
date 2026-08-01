import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_cohort_decommission import (
    challenger_cohort_decommission_receipt_hash,
)
from crypto_quant.challenger_cohort_failure import (
    challenger_cohort_failure_receipt_hash,
    load_challenger_cohort_failure_receipt,
)
from crypto_quant.challenger_cohort_failure_release import (
    ChallengerCohortFailureReleaseError,
    release_challenger_cohort_decommission_receipt,
    release_challenger_cohort_failure_receipt,
)
from crypto_quant.challenger_cohort_failure_release_cli import _parser
from tests import test_challenger_cohort_failure as failure_tests
from tests import test_challenger_cohort_decommission as decommission_tests


ARTIFACT_NAME = (
    "challenger-cohort-missed-slot-failure-receipt-v0.54.0.json"
)
DECOMMISSION_ARTIFACT_NAME = (
    "challenger-cohort-decommission-receipt-v0.54.0.json"
)
ROOT = Path(__file__).resolve().parents[1]


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
                "failure_receipt_path",
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

    def test_exact_decommission_release_replays_fixed_git_bytes(self):
        """Catches publishing a transformed or unverified stop receipt."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            helper = decommission_tests.ChallengerCohortDecommissionTests()
            runtime = helper.environment(root / "runtime")
            result = decommission_tests.decommission_failed_challenger_cohort(
                failure_receipt_path=runtime["failure_receipt"],
                cohort_plan_path=runtime["cohort_plan_path"],
                evaluation_plan_path=runtime["evaluation_plan_path"],
                install_receipt_path=runtime["install_receipt_path"],
                contract_path=runtime["contract_path"],
                plist_path=runtime["plist_path"],
                failure_output_root=runtime["failure_output_root"],
                _command_runner=decommission_tests.RecordingCommandRunner(
                    runtime
                ),
            )
            runtime_receipt = Path(result["receipt_path"])
            artifact_parent = root / "artifacts"
            artifact_parent.mkdir(mode=0o700)
            artifact = artifact_parent / DECOMMISSION_ARTIFACT_NAME

            summary = release_challenger_cohort_decommission_receipt(
                runtime_receipt_path=runtime_receipt,
                artifact_output_path=artifact,
                failure_receipt_path=runtime["failure_receipt"],
                cohort_plan_path=runtime["cohort_plan_path"],
                evaluation_plan_path=runtime["evaluation_plan_path"],
                install_receipt_path=runtime["install_receipt_path"],
                contract_path=runtime["contract_path"],
                plist_path=runtime["plist_path"],
            )

            self.assertEqual(
                artifact.read_bytes(), runtime_receipt.read_bytes()
            )
            self.assertTrue(summary["artifact_created"])
            self.assertEqual(
                summary["status"], "EXACT_DECOMMISSION_RECEIPT_RELEASED"
            )

    def test_committed_v054_receipts_are_canonical_and_frozen(self):
        """Catches changing or omitting the exact production evidence."""

        cases = (
            {
                "artifact": ARTIFACT_NAME,
                "schema": "challenger-cohort-failure-receipt-v1.schema.json",
                "size": 55482,
                "file_sha256": (
                    "7907b97d4447039c686f53dc62694c37"
                    "836417b4ae555d3322b16478319b85ae"
                ),
                "receipt_id": (
                    "challenger_cohort_failure_receipt_"
                    "955e47c773683f1ae4ba7997a84badc3"
                    "73d3daf5afb24763bdc88d1b95d30545"
                ),
                "receipt_hash": (
                    "3b2bcc2651bb80f58fb44d08ac4dfb2b"
                    "dd9ab6c3ada4cfd83de00627ec8480b3"
                ),
                "hash_function": challenger_cohort_failure_receipt_hash,
                "status": "COHORT_MISSED_SLOT_FAILURE_VERIFIED",
            },
            {
                "artifact": DECOMMISSION_ARTIFACT_NAME,
                "schema": (
                    "challenger-cohort-decommission-receipt-v1.schema.json"
                ),
                "size": 40011,
                "file_sha256": (
                    "540b831797228c950d954ee75b183fbea"
                    "c08d63679463e14121fefc44fdf851f"
                ),
                "receipt_id": (
                    "challenger_cohort_decommission_receipt_"
                    "30f87c50715e9f4c09b9b21072cb8c3f"
                    "6fecf932d2703300adcf153fbab9323e"
                ),
                "receipt_hash": (
                    "56cfaa3f44b23e6dbc282f5947676ea9"
                    "3b4b92a89dcf90539a19eeb865b0bae7"
                ),
                "hash_function": (
                    challenger_cohort_decommission_receipt_hash
                ),
                "status": "FAILED_COHORT_DECOMMISSIONED_VERIFIED",
            },
        )
        for case in cases:
            with self.subTest(artifact=case["artifact"]):
                artifact = (
                    ROOT / "artifacts" / "challenger-forward" / case["artifact"]
                )
                body = artifact.read_bytes()
                receipt = json.loads(body)
                schema = json.loads((ROOT / "config" / case["schema"]).read_bytes())
                self.assertEqual(body, canonical_json(receipt).encode("utf-8"))
                self.assertFalse(
                    tuple(Draft202012Validator(schema).iter_errors(receipt))
                )
                self.assertEqual(len(body), case["size"])
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(), case["file_sha256"]
                )
                self.assertEqual(receipt["receipt_id"], case["receipt_id"])
                self.assertEqual(receipt["receipt_hash"], case["receipt_hash"])
                self.assertEqual(
                    receipt["receipt_hash"], case["hash_function"](receipt)
                )
                self.assertEqual(
                    receipt["observation_status"], case["status"]
                )

        failure = json.loads(
            (ROOT / "artifacts" / "challenger-forward" / ARTIFACT_NAME).read_bytes()
        )
        self.assertEqual(failure["logs"]["stderr"]["occurrence_count"], 2)
        self.assertFalse(failure["failure"]["historical_backfill_allowed"])
        self.assertEqual(
            failure["failure"]["equivalent_evaluator_status"],
            "FAILED_CLOSED_NO_BACKFILL",
        )
        decommission = json.loads(
            (
                ROOT
                / "artifacts"
                / "challenger-forward"
                / DECOMMISSION_ARTIFACT_NAME
            ).read_bytes()
        )
        self.assertEqual(decommission["security_boundary"]["bootout_count"], 1)
        self.assertEqual(decommission["service"]["state_after"], "NOT_LOADED")


if __name__ == "__main__":
    unittest.main()
