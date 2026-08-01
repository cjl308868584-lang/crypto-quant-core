import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from crypto_quant.challenger_cohort_decommission import (
    ChallengerCohortDecommissionError,
    DecommissionCommandResult,
    challenger_cohort_decommission_receipt_hash,
    decommission_failed_challenger_cohort,
    load_challenger_cohort_decommission_receipt,
)
import crypto_quant.challenger_cohort_decommission as decommission_module
from crypto_quant.challenger_cohort_decommission_cli import (
    ChallengerCohortDecommissionCLIError,
    _parser,
    _trusted_output_root as trusted_decommission_output_root,
)
from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from tests import test_challenger_cohort_failure as failure_tests


TEST_UID = os.getuid()
TEST_DOMAIN = f"gui/{TEST_UID}"
OLD_SERVICE = f"{TEST_DOMAIN}/local.crypto-quant.challenger-forward"
OLD_PRINT = ("/bin/launchctl", "print", OLD_SERVICE)
DOMAIN_PRINT = ("/bin/launchctl", "print", TEST_DOMAIN)
BOOTOUT = ("/bin/launchctl", "bootout", OLD_SERVICE)
NOT_FOUND = (
    b'Bad request.\nCould not find service '
    b'"local.crypto-quant.challenger-forward" '
    + f"in domain for user gui: {TEST_UID}\n".encode("utf-8")
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
                    f"{TEST_DOMAIN} = {{\nservices = {{\n".encode("utf-8")
                    + b"local.crypto-quant.challenger-forward\n}\n}\n"
                    + b"com.apple.private.sentinel /Users/example/secret\n"
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


class ReboundBeforeBootoutRunner(RecordingCommandRunner):
    def __call__(self, argv):
        call = tuple(argv)
        if call == OLD_PRINT and self.argv.count(OLD_PRINT) == 1:
            self.argv.append(call)
            result = self.environment["failed_launchctl"](call)
            return DecommissionCommandResult(
                result.returncode,
                result.stdout.replace(
                    b"last exit code = 1", b"last exit code = 0"
                ),
                result.stderr,
            )
        return super().__call__(argv)


class ReceiptReplacingFinalPrintRunner(RecordingCommandRunner):
    def __call__(self, argv):
        result = super().__call__(argv)
        if tuple(argv) == OLD_PRINT and self.argv.count(OLD_PRINT) == 2:
            receipt = self.environment["failure_receipt"]
            receipt.write_bytes(b"{}")
            receipt.chmod(0o600)
        return result


class RaisingBootoutRunner(RecordingCommandRunner):
    def __call__(self, argv):
        if tuple(argv) == BOOTOUT:
            self.argv.append(tuple(argv))
            raise TimeoutError("bootout result unavailable")
        return super().__call__(argv)


class RaisingAfterPrintRunner(RecordingCommandRunner):
    def __call__(self, argv):
        if tuple(argv) == OLD_PRINT and self.booted_out:
            self.argv.append(tuple(argv))
            raise TimeoutError("postcondition result unavailable")
        return super().__call__(argv)


class ChallengerCohortDecommissionTests(unittest.TestCase):
    def setUp(self):
        # Production is intentionally frozen to gui/501. Synthetic install
        # receipts use the executing test user's UID, so project that same
        # fixed identity into this test module without widening production.
        schema = json.loads(
            (
                ROOT
                / "config"
                / "challenger-cohort-decommission-receipt-v1.schema.json"
            ).read_bytes()
        )
        schema["properties"]["service"]["properties"]["identity"][
            "const"
        ] = OLD_SERVICE
        test_validator = Draft202012Validator(schema)
        identity = mock.patch.multiple(
            decommission_module,
            _OLD_SERVICE=OLD_SERVICE,
            _PRINT_ARGV=OLD_PRINT,
            _DOMAIN_PRINT_ARGV=DOMAIN_PRINT,
            _BOOTOUT_ARGV=BOOTOUT,
            _NOT_FOUND_STDERR=NOT_FOUND,
            _validator=mock.Mock(return_value=test_validator),
        )
        identity.start()
        self.addCleanup(identity.stop)

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
            self.assertEqual(
                runner.argv,
                [OLD_PRINT, DOMAIN_PRINT, OLD_PRINT, BOOTOUT, OLD_PRINT],
            )
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
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            expected = base / "challenger-forward-v1" / "cohort-failures"
            expected.mkdir(mode=0o700, parents=True)
            self.assertEqual(
                trusted_decommission_output_root(
                    str(expected), allowed_base=base
                ),
                expected,
            )
            wrong = base / "arbitrary"
            wrong.mkdir(mode=0o700)
            with self.assertRaises(ChallengerCohortDecommissionCLIError):
                trusted_decommission_output_root(
                    str(wrong), allowed_base=base
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
        schema_receipt = copy.deepcopy(receipt)
        schema_receipt["service"]["identity"] = (
            "gui/501/local.crypto-quant.challenger-forward"
        )
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(schema_receipt))
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

    def test_rehash_cannot_erase_domain_labels(self):
        """Catches claimed labels detached from persisted filtered evidence."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
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
            changed = copy.deepcopy(receipt)
            domain = changed["commands"]["domain_print"]
            domain["crypto_quant_labels"] = []
            domain["filtered_stdout_utf8"] = ""
            domain["filtered_stdout_sha256"] = hashlib.sha256(b"").hexdigest()
            domain["stdout_sha256"] = "0" * 64
            domain["command_evidence_hash"] = artifact_self_hash(
                domain, "command_evidence_hash"
            )
            changed["receipt_hash"] = (
                challenger_cohort_decommission_receipt_hash(changed)
            )
            tampered = root / "domain-tampered.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            tampered.chmod(0o600)

            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_RECEIPT_INVALID",
            ):
                load_challenger_cohort_decommission_receipt(
                    receipt_path=tampered,
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
                )

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

    def test_only_canonical_owner_only_failure_receipt_can_authorize(self):
        """Catches copied or relaxed-mode receipt authority."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            copied = self.environment(root / "copied")
            copied_path = root / "arbitrary-failure.json"
            copied_path.write_bytes(copied["failure_receipt"].read_bytes())
            copied_path.chmod(0o644)
            runner = RecordingCommandRunner(copied)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=copied_path,
                    cohort_plan_path=copied["cohort_plan_path"],
                    evaluation_plan_path=copied["evaluation_plan_path"],
                    install_receipt_path=copied["install_receipt_path"],
                    contract_path=copied["contract_path"],
                    plist_path=copied["plist_path"],
                    failure_output_root=copied["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertEqual(runner.argv, [])

            relaxed = self.environment(root / "relaxed")
            relaxed["failure_receipt"].chmod(0o644)
            runner = RecordingCommandRunner(relaxed)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=relaxed["failure_receipt"],
                    cohort_plan_path=relaxed["cohort_plan_path"],
                    evaluation_plan_path=relaxed["evaluation_plan_path"],
                    install_receipt_path=relaxed["install_receipt_path"],
                    contract_path=relaxed["contract_path"],
                    plist_path=relaxed["plist_path"],
                    failure_output_root=relaxed["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertEqual(runner.argv, [])

    def test_failure_receipt_replacement_after_load_blocks_all_commands(self):
        """Catches a receipt-path replacement between replay and snapshot."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            receipt_path = environment["failure_receipt"]
            runner = RecordingCommandRunner(environment)
            original_loader = (
                decommission_module.load_challenger_cohort_failure_receipt
            )

            def load_then_replace(**kwargs):
                receipt = original_loader(**kwargs)
                receipt_path.write_bytes(b"{}")
                receipt_path.chmod(0o600)
                return receipt

            with mock.patch.object(
                decommission_module,
                "load_challenger_cohort_failure_receipt",
                side_effect=load_then_replace,
            ):
                with self.assertRaisesRegex(
                    ChallengerCohortDecommissionError,
                    "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID",
                ):
                    decommission_failed_challenger_cohort(
                        failure_receipt_path=receipt_path,
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

    def test_service_rebind_detected_immediately_before_bootout(self):
        """Catches bootout after the fixed label changes post-domain check."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            runner = ReboundBeforeBootoutRunner(environment)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_PREFLIGHT_INVALID",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=environment["failure_receipt"],
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment["evaluation_plan_path"],
                    install_receipt_path=environment["install_receipt_path"],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertNotIn(BOOTOUT, runner.argv)

    def test_receipt_replacement_during_final_print_blocks_bootout(self):
        """Catches an authority swap during the final service observation."""

        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory).resolve())
            runner = ReceiptReplacingFinalPrintRunner(environment)
            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_SOURCE_MUTATED",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=environment["failure_receipt"],
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment["evaluation_plan_path"],
                    install_receipt_path=environment["install_receipt_path"],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertNotIn(BOOTOUT, runner.argv)

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

    def test_attempted_bootout_failures_publish_structured_forensics(self):
        """Catches losing command evidence after an irreversible attempt."""

        cases = (
            (BootoutFailureRunner, "BOOTOUT_FAILED"),
            (StillLoadedAfterBootoutRunner, "POSTCONDITION_INVALID"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for index, (runner_type, phase) in enumerate(cases):
                with self.subTest(phase=phase):
                    environment = self.environment(root / str(index))
                    with self.assertRaises(ChallengerCohortDecommissionError):
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
                            _command_runner=runner_type(environment),
                        )
                    failure_directory = (
                        environment["failure_output_root"]
                        / "challenger-cohort-decommission-failures"
                    )
                    files = list(failure_directory.glob("*.json"))
                    self.assertEqual(len(files), 1)
                    self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
                    receipt = json.loads(files[0].read_bytes())
                    self.assertEqual(
                        receipt["observation_status"],
                        "FAILED_CLOSED_DECOMMISSION_UNVERIFIED",
                    )
                    self.assertEqual(receipt["phase"], phase)
                    self.assertEqual(
                        receipt["receipt_hash"],
                        artifact_self_hash(receipt, "receipt_hash"),
                    )
                    self.assertIn("bootout", receipt["commands"])

    def test_command_exceptions_after_bootout_authority_are_forensic(self):
        """Catches losing evidence when an attempted command has no result."""

        cases = (
            (RaisingBootoutRunner, "BOOTOUT_COMMAND_EXCEPTION"),
            (RaisingAfterPrintRunner, "POSTCONDITION_COMMAND_EXCEPTION"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for index, (runner_type, phase) in enumerate(cases):
                with self.subTest(phase=phase):
                    environment = self.environment(root / str(index))
                    with self.assertRaises(ChallengerCohortDecommissionError):
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
                            _command_runner=runner_type(environment),
                        )
                    files = list(
                        (
                            environment["failure_output_root"]
                            / "challenger-cohort-decommission-failures"
                        ).glob("*.json")
                    )
                    self.assertEqual(len(files), 1)
                    receipt = json.loads(files[0].read_bytes())
                    self.assertEqual(receipt["phase"], phase)
                    self.assertIn(
                        "command_exception_type",
                        receipt["commands"][
                            "bootout"
                            if phase == "BOOTOUT_COMMAND_EXCEPTION"
                            else "after_print"
                        ],
                    )

    def test_decommission_receipt_symlink_fails_closed_with_forensics(self):
        """Catches redirecting the success receipt after bootout."""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            environment = self.environment(root / "environment")
            redirect = root / "redirect-target"
            redirect.mkdir(mode=0o700)
            (
                environment["failure_output_root"]
                / "challenger-cohort-decommission-receipts"
            ).symlink_to(redirect, target_is_directory=True)
            runner = RecordingCommandRunner(environment)

            with self.assertRaisesRegex(
                ChallengerCohortDecommissionError,
                "CHALLENGER_COHORT_DECOMMISSION_PUBLISH_FAILED",
            ):
                decommission_failed_challenger_cohort(
                    failure_receipt_path=environment["failure_receipt"],
                    cohort_plan_path=environment["cohort_plan_path"],
                    evaluation_plan_path=environment["evaluation_plan_path"],
                    install_receipt_path=environment["install_receipt_path"],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                    failure_output_root=environment["failure_output_root"],
                    _command_runner=runner,
                )
            self.assertEqual(list(redirect.iterdir()), [])
            forensic_files = list(
                (
                    environment["failure_output_root"]
                    / "challenger-cohort-decommission-failures"
                ).glob("*.json")
            )
            self.assertEqual(len(forensic_files), 1)
            forensic = json.loads(forensic_files[0].read_bytes())
            self.assertEqual(
                forensic["phase"], "DECOMMISSION_RECEIPT_PUBLISH_FAILED"
            )


if __name__ == "__main__":
    unittest.main()
