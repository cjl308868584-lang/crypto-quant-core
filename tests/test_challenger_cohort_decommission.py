import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.challenger_cohort_decommission import (
    ChallengerCohortDecommissionError,
    DecommissionCommandResult,
    decommission_failed_challenger_cohort,
    load_challenger_cohort_decommission_receipt,
)
from crypto_quant.challenger_cohort_decommission_cli import _parser
from tests import test_challenger_cohort_failure as failure_tests


OLD_SERVICE = "gui/501/local.crypto-quant.challenger-forward"
OLD_PRINT = ("/bin/launchctl", "print", OLD_SERVICE)
DOMAIN_PRINT = ("/bin/launchctl", "print", "gui/501")
BOOTOUT = ("/bin/launchctl", "bootout", OLD_SERVICE)
NOT_FOUND = (
    b'Bad request.\nCould not find service '
    b'"local.crypto-quant.challenger-forward" '
    b'in domain for user gui: 501\n'
)
ROOT = Path(__file__).resolve().parents[1]


class RecordingCommandRunner:
    def __init__(self, environment):
        self.environment = environment
        self.argv = []
        self.booted_out = False

    def __call__(self, argv):
        call = tuple(argv)
        self.argv.append(call)
        if call == OLD_PRINT and not self.booted_out:
            result = self.environment["failed_launchctl"](call)
            return DecommissionCommandResult(
                result.returncode, result.stdout, result.stderr
            )
        if call == DOMAIN_PRINT:
            return DecommissionCommandResult(
                0,
                (
                    b"gui/501 = {\nservices = {\n"
                    b"local.crypto-quant.challenger-forward\n}\n}\n"
                    b"com.apple.private.sentinel /Users/example/secret\n"
                ),
                b"",
            )
        if call == BOOTOUT and not self.booted_out:
            self.booted_out = True
            return DecommissionCommandResult(0, b"", b"")
        if call == OLD_PRINT and self.booted_out:
            return DecommissionCommandResult(113, b"", NOT_FOUND)
        raise AssertionError(f"unexpected command: {call}")


class ReplacementPresentRunner(RecordingCommandRunner):
    def __call__(self, argv):
        call = tuple(argv)
        if call == DOMAIN_PRINT:
            self.argv.append(call)
            return DecommissionCommandResult(
                0,
                b"local.crypto-quant.system-paper-v1\n",
                b"",
            )
        return super().__call__(argv)


class BootoutFailureRunner(RecordingCommandRunner):
    def __call__(self, argv):
        call = tuple(argv)
        if call == BOOTOUT:
            self.argv.append(call)
            return DecommissionCommandResult(5, b"", b"bootout failed\n")
        return super().__call__(argv)


class StillLoadedAfterBootoutRunner(RecordingCommandRunner):
    def __call__(self, argv):
        call = tuple(argv)
        if call == OLD_PRINT and self.booted_out:
            self.argv.append(call)
            result = self.environment["failed_launchctl"](call)
            return DecommissionCommandResult(
                result.returncode, result.stdout, result.stderr
            )
        return super().__call__(argv)


class MutatingBootoutRunner(RecordingCommandRunner):
    def __call__(self, argv):
        result = super().__call__(argv)
        if tuple(argv) == BOOTOUT:
            stderr = self.environment["paths"]["stderr"]
            stderr.write_bytes(stderr.read_bytes() + b"changed\n")
            stderr.chmod(0o600)
        return result


class ChallengerCohortDecommissionTests(unittest.TestCase):
    def environment(self, root: Path):
        helper = failure_tests.ChallengerCohortFailureTests()
        environment = helper.environment(root)
        failure = helper.observe(environment)
        environment["failure_receipt"] = Path(failure["receipt_path"])
        return environment

    def test_verified_failure_runs_one_fixed_bootout_and_preserves_files(self):
        """Catches decommission without receipt-first, fixed-command evidence."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            before = {
                name: path.read_bytes()
                for name, path in environment["paths"].items()
                if name in {"state", "stdout", "stderr"}
            }
            runner = RecordingCommandRunner(environment)

            summary = decommission_failed_challenger_cohort(
                failure_receipt_path=environment["failure_receipt"],
                cohort_plan_path=environment["cohort_plan_path"],
                evaluation_plan_path=environment["evaluation_plan_path"],
                install_receipt_path=environment["install_receipt_path"],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
                failure_output_root=environment["failure_output_root"],
                _command_runner=runner,
            )

            self.assertEqual(
                summary["status"], "FAILED_COHORT_DECOMMISSIONED_VERIFIED"
            )
            self.assertEqual(runner.argv, [OLD_PRINT, DOMAIN_PRINT, BOOTOUT, OLD_PRINT])
            self.assertEqual(runner.argv.count(BOOTOUT), 1)
            self.assertEqual(
                {
                    name: path.read_bytes()
                    for name, path in environment["paths"].items()
                    if name in {"state", "stdout", "stderr"}
                },
                before,
            )
            receipt = load_challenger_cohort_decommission_receipt(
                receipt_path=Path(summary["receipt_path"]),
                failure_receipt_path=environment["failure_receipt"],
                cohort_plan_path=environment["cohort_plan_path"],
                evaluation_plan_path=environment["evaluation_plan_path"],
                install_receipt_path=environment["install_receipt_path"],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
            )
            self.assertEqual(
                receipt["eligibility"]["service"], "DECOMMISSIONED"
            )

    def test_cli_exposes_no_command_service_force_or_delete_override(self):
        """Catches widening the one-service decommission authority."""

        destinations = {action.dest for action in _parser()._actions}
        self.assertEqual(
            destinations,
            {
                "help",
                "failure_receipt_path",
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
                "command",
                "launchctl",
                "force",
                "delete",
                "runner",
                "maintenance",
                "broker",
                "order",
            }
        )

    def test_schema_mirrors_validate_real_decommission_receipt(self):
        """Catches shipping a decommission receipt without packaged Schema."""

        config = (
            ROOT
            / "config"
            / "challenger-cohort-decommission-receipt-v1.schema.json"
        )
        packaged = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-cohort-decommission-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), packaged.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            summary = decommission_failed_challenger_cohort(
                failure_receipt_path=environment["failure_receipt"],
                cohort_plan_path=environment["cohort_plan_path"],
                evaluation_plan_path=environment["evaluation_plan_path"],
                install_receipt_path=environment["install_receipt_path"],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
                failure_output_root=environment["failure_output_root"],
                _command_runner=RecordingCommandRunner(environment),
            )
            receipt = json.loads(Path(summary["receipt_path"]).read_bytes())
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(receipt))
        )

    def test_domain_inventory_is_filtered_before_receipt_publication(self):
        """Catches leaking unrelated user-domain services into Git evidence."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            summary = decommission_failed_challenger_cohort(
                failure_receipt_path=environment["failure_receipt"],
                cohort_plan_path=environment["cohort_plan_path"],
                evaluation_plan_path=environment["evaluation_plan_path"],
                install_receipt_path=environment["install_receipt_path"],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
                failure_output_root=environment["failure_output_root"],
                _command_runner=RecordingCommandRunner(environment),
            )
            body = Path(summary["receipt_path"]).read_bytes()
        self.assertNotIn(b"com.apple.private.sentinel", body)
        self.assertNotIn(b"/Users/example/secret", body)

    def test_invalid_failure_receipt_never_reaches_launchctl(self):
        """Catches bootout authority surviving a failed receipt replay."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            receipt = environment["failure_receipt"]
            receipt.write_bytes(b"{}")
            receipt.chmod(0o600)
            runner = RecordingCommandRunner(environment)

            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=receipt,
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment[
                        "failure_output_root"
                    ],
                    _command_runner=runner,
                )
            self.assertEqual(runner.argv, [])

    def test_invalid_clock_is_rejected_before_any_launchctl_command(self):
        """Catches discovering malformed receipt identity after bootout."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            runner = RecordingCommandRunner(environment)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_TIME_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=environment["failure_receipt"],
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment[
                        "failure_output_root"
                    ],
                    clock=lambda: "garbageZ",
                    _command_runner=runner,
                )
            self.assertEqual(runner.argv, [])

    def test_replacement_or_wrong_old_service_blocks_bootout(self):
        """Catches stopping the predecessor after a successor became active."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            replacement = self.environment(root / "replacement")
            runner = ReplacementPresentRunner(replacement)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "REPLACEMENT_PRESENT",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=replacement["failure_receipt"],
                    cohort_plan_path=replacement["cohort_plan_path"],
                    evaluation_plan_path=replacement[
                        "evaluation_plan_path"
                    ],
                    install_receipt_path=replacement[
                        "install_receipt_path"
                    ],
                    contract_path=replacement["contract_path"],
                    plist_path=replacement["plist_path"],
                    failure_output_root=replacement[
                        "failure_output_root"
                    ],
                    _command_runner=runner,
                )
            self.assertNotIn(BOOTOUT, runner.argv)

            wrong = self.environment(root / "wrong-exit")
            wrong["service"].last_exit_code = 0
            runner = RecordingCommandRunner(wrong)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "PREFLIGHT_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=wrong["failure_receipt"],
                    cohort_plan_path=wrong["cohort_plan_path"],
                    evaluation_plan_path=wrong["evaluation_plan_path"],
                    install_receipt_path=wrong["install_receipt_path"],
                    contract_path=wrong["contract_path"],
                    plist_path=wrong["plist_path"],
                    failure_output_root=wrong["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertNotIn(BOOTOUT, runner.argv)

    def test_bootout_failure_loaded_postcondition_and_mutation_fail_closed(self):
        """Catches claiming decommission on any failed postcondition."""

        cases = (
            (BootoutFailureRunner, "BOOTOUT_FAILED"),
            (StillLoadedAfterBootoutRunner, "POSTCONDITION_INVALID"),
            (MutatingBootoutRunner, "SOURCE_MUTATED"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for index, (runner_type, reason) in enumerate(cases):
                with self.subTest(reason=reason):
                    environment = self.environment(root / str(index))
                    runner = runner_type(environment)
                    with self.assertRaisesRegex(
                        ChallengerCohortDecommissionError, reason
                    ):
                        decommission_failed_challenger_cohort(
                            failure_receipt_path=environment[
                                "failure_receipt"
                            ],
                            cohort_plan_path=environment[
                                "cohort_plan_path"
                            ],
                            evaluation_plan_path=environment[
                                "evaluation_plan_path"
                            ],
                            install_receipt_path=environment[
                                "install_receipt_path"
                            ],
                            contract_path=environment["contract_path"],
                            plist_path=environment["plist_path"],
                            failure_output_root=environment[
                                "failure_output_root"
                            ],
                            _command_runner=runner,
                        )
                    self.assertEqual(runner.argv.count(BOOTOUT), 1)


if __name__ == "__main__":
    unittest.main()
