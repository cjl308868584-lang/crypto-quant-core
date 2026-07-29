import copy
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_first_slot_receipt import (
    ChallengerFirstSlotReceiptError,
    challenger_first_slot_receipt_hash,
    load_challenger_first_slot_receipt,
    observe_challenger_first_slot,
)
from crypto_quant.challenger_first_slot_receipt_cli import (
    main as observer_main,
)
from crypto_quant.challenger_forward import ChallengerForwardState
from crypto_quant.challenger_forward_runner import (
    run_challenger_forward_cycle,
)
from crypto_quant.challenger_launchd import (
    load_challenger_launchd_contract,
    publish_challenger_launchd_contract,
)
from crypto_quant.challenger_launchd_install import (
    LaunchctlResult,
    install_challenger_launchd,
)
from tests.test_challenger_forward_runner import (
    KlineTransport,
    gate_at,
    raw_window,
)


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 7, 29, tzinfo=timezone.utc)
CREATED = datetime(2026, 7, 28, 6, tzinfo=timezone.utc)
INSTALLED = datetime(2026, 7, 28, 7, tzinfo=timezone.utc)
VERIFIED = datetime(2026, 7, 28, 7, 0, 1, tzinfo=timezone.utc)
LABEL = "local.crypto-quant.challenger-forward"


class FakeService:
    def __init__(self, *, contract, target):
        self.contract = contract
        self.target = target
        self.uid = os.getuid()
        self.loaded = False
        self.runs = 3
        self.last_exit_code = 0
        self.calls = []

    @property
    def service(self):
        return f"gui/{self.uid}/{LABEL}"

    def print_bytes(self):
        runtime = Path(self.contract["runtime_root"])
        values = [
            self.service,
            LABEL,
            str(self.target),
            self.contract["python_executable"],
            "crypto_quant.challenger_forward_runner_cli",
            self.contract["program_arguments"][4],
            self.contract["program_arguments"][6],
            str(runtime / "log" / "challenger-forward.stdout.log"),
            str(runtime / "log" / "challenger-forward.stderr.log"),
            f"runs = {self.runs}",
            f"last exit code = {self.last_exit_code}",
        ]
        return ("\n".join(values) + "\n").encode("utf-8")

    def __call__(self, argv):
        call = tuple(argv)
        self.calls.append(call)
        if call[1] == "print":
            if self.loaded:
                return LaunchctlResult(0, self.print_bytes(), b"")
            return LaunchctlResult(113, b"", b"not found\n")
        if call[1] == "bootstrap":
            self.loaded = True
            return LaunchctlResult(0, b"", b"")
        raise AssertionError(f"unexpected command: {call}")


class ChallengerFirstSlotReceiptTests(unittest.TestCase):
    def environment(self, root):
        deployment = root / "runtime" / "deployment" / "test-snapshot"
        deployment.mkdir(parents=True, mode=0o700)
        shutil.copy2(ROOT / "pyproject.toml", deployment / "pyproject.toml")
        shutil.copytree(
            ROOT / "src" / "crypto_quant",
            deployment / "src" / "crypto_quant",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        for entry in deployment.rglob("*"):
            entry.chmod(0o700 if entry.is_dir() else 0o600)
        source = publish_challenger_launchd_contract(
            repository_root=deployment,
            runtime_root=root / "runtime",
            python_executable=Path(sys.executable),
            output_root=root / "contract-output",
            clock=lambda: CREATED,
        )
        contract_path = Path(source["contract_path"])
        plist_path = Path(source["plist_path"])
        contract = load_challenger_launchd_contract(
            contract_path=contract_path,
            plist_path=plist_path,
        )
        home = root / "home"
        target = (
            home.resolve()
            / "Library"
            / "LaunchAgents"
            / f"{LABEL}.plist"
        )
        service = FakeService(contract=contract, target=target)
        times = iter((INSTALLED, VERIFIED))
        installed = install_challenger_launchd(
            contract_path=contract_path,
            plist_path=plist_path,
            receipt_output_root=root / "install-receipts",
            clock=lambda: next(times),
            _home_directory=home,
            _uid=os.getuid(),
            _launchctl_runner=service,
        )
        paths = {
            "state": Path(contract["program_arguments"][4]),
            "output": Path(contract["program_arguments"][6]),
            "stdout": (
                Path(contract["runtime_root"])
                / "log"
                / "challenger-forward.stdout.log"
            ),
            "stderr": (
                Path(contract["runtime_root"])
                / "log"
                / "challenger-forward.stderr.log"
            ),
        }
        return {
            "contract": contract,
            "contract_path": contract_path,
            "plist_path": plist_path,
            "install_receipt_path": Path(installed["receipt_path"]),
            "receipt_output_root": root / "first-slot-receipts",
            "service": service,
            "paths": paths,
        }

    def empty_state(self, environment):
        with ChallengerForwardState(environment["paths"]["state"]):
            pass

    def successful_state(self, environment):
        now = START + timedelta(minutes=1)
        gate, _source = gate_at(now)
        result = run_challenger_forward_cycle(
            state_path=environment["paths"]["state"],
            output_root=environment["paths"]["output"],
            runtime_gate=gate,
            kline_transport=KlineTransport(
                raw_window(START, [100] * 21),
                now,
            ),
        )
        stdout = environment["paths"]["stdout"]
        stderr = environment["paths"]["stderr"]
        stdout.parent.mkdir(parents=True, exist_ok=True)
        stdout.write_bytes(
            (
                json.dumps(
                    {
                        "status": "NOT_DUE",
                        "server_time_request_count": 3,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
                + json.dumps(
                    result,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )
        stderr.write_bytes(b"")
        stdout.chmod(0o600)
        stderr.chmod(0o600)
        return result

    def observe(self, environment, *, clock):
        return observe_challenger_first_slot(
            install_receipt_path=environment[
                "install_receipt_path"
            ],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
            receipt_output_root=environment["receipt_output_root"],
            clock=lambda: clock,
            _launchctl_runner=environment["service"],
        )

    def test_waiting_and_pending_publish_nothing_and_do_not_call_launchctl(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.empty_state(environment)
            calls = len(environment["service"].calls)
            waiting = self.observe(
                environment, clock=START - timedelta(seconds=1)
            )
            pending = self.observe(
                environment, clock=START + timedelta(hours=1)
            )
            self.assertEqual(
                waiting["status"], "WAITING_BEFORE_FIRST_SLOT"
            )
            self.assertEqual(
                pending["status"],
                "OBSERVATION_PENDING_WITHIN_RECORD_DEADLINE",
            )
            self.assertFalse(waiting["receipt_published"])
            self.assertFalse(pending["receipt_published"])
            self.assertEqual(len(environment["service"].calls), calls)
            self.assertFalse(
                environment["receipt_output_root"].exists()
            )

    def test_missing_first_slot_fails_after_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.empty_state(environment)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_MISSED",
            ):
                self.observe(
                    environment,
                    clock=START + timedelta(hours=4),
                )

    def test_success_is_read_only_published_and_loadable(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            result = self.successful_state(environment)
            state_path = environment["paths"]["state"]
            before = state_path.read_bytes()
            observed = self.observe(
                environment, clock=START + timedelta(minutes=2)
            )
            after = state_path.read_bytes()
            self.assertEqual(before, after)
            self.assertEqual(
                observed["status"], "FIRST_SLOT_RECORDED_VERIFIED"
            )
            self.assertEqual(observed["decision_hash"], result["decision_hash"])
            self.assertEqual(observed["network_request_count"], 0)
            self.assertEqual(observed["state_write_count"], 0)
            receipt_path = Path(observed["receipt_path"])
            self.assertEqual(stat.S_IMODE(receipt_path.stat().st_mode), 0o600)
            receipt = load_challenger_first_slot_receipt(
                receipt_path=receipt_path,
                install_receipt_path=environment[
                    "install_receipt_path"
                ],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
            )
            self.assertEqual(receipt["receipt_hash"], observed["receipt_hash"])
            self.assertEqual(receipt["state"]["decision_count"], 1)

    def test_stdout_append_is_allowed_but_prefix_mutation_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.successful_state(environment)
            observed = self.observe(
                environment, clock=START + timedelta(minutes=2)
            )
            stdout = environment["paths"]["stdout"]
            original = stdout.read_bytes()
            stdout.write_bytes(
                original
                + b'{"status":"NOT_DUE","server_time_request_count":3}\n'
            )
            stdout.chmod(0o600)
            load_challenger_first_slot_receipt(
                receipt_path=Path(observed["receipt_path"]),
                install_receipt_path=environment[
                    "install_receipt_path"
                ],
                contract_path=environment["contract_path"],
                plist_path=environment["plist_path"],
            )
            stdout.write_bytes(b"X" + stdout.read_bytes()[1:])
            stdout.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_RECEIPT_INVALID",
            ):
                load_challenger_first_slot_receipt(
                    receipt_path=Path(observed["receipt_path"]),
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                )

    def test_receipt_rehash_cannot_hide_security_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root)
            self.successful_state(environment)
            observed = self.observe(
                environment, clock=START + timedelta(minutes=2)
            )
            receipt = json.loads(Path(observed["receipt_path"]).read_text())
            changed = copy.deepcopy(receipt)
            changed["security_boundary"]["order_submission_count"] = 1
            changed["receipt_hash"] = challenger_first_slot_receipt_hash(
                changed
            )
            tampered = root / "tampered.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            tampered.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_RECEIPT_INVALID",
            ):
                load_challenger_first_slot_receipt(
                    receipt_path=tampered,
                    install_receipt_path=environment[
                        "install_receipt_path"
                    ],
                    contract_path=environment["contract_path"],
                    plist_path=environment["plist_path"],
                )

    def test_wal_multiple_bundle_and_bad_service_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            result = self.successful_state(environment)
            wal = Path(f"{environment['paths']['state']}-wal")
            wal.write_bytes(b"busy")
            wal.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_STATE_BUSY",
            ):
                self.observe(
                    environment, clock=START + timedelta(minutes=2)
                )
            wal.unlink()
            bundle = Path(result["source_bundle_path"])
            duplicate = bundle.parent / "duplicate.json"
            shutil.copy2(bundle, duplicate)
            duplicate.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_BUNDLE_COUNT_INVALID",
            ):
                self.observe(
                    environment, clock=START + timedelta(minutes=2)
                )
            duplicate.unlink()
            environment["service"].last_exit_code = 1
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_SERVICE_INVALID",
            ):
                self.observe(
                    environment, clock=START + timedelta(minutes=2)
                )

    def test_state_bundle_and_permission_tamper_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata_environment = self.environment(root / "metadata")
            self.successful_state(metadata_environment)
            connection = sqlite3.connect(
                str(metadata_environment["paths"]["state"])
            )
            connection.execute(
                "UPDATE metadata SET policy_hash=? WHERE singleton=1",
                ("f" * 64,),
            )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.close()
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_STATE_BINDING_INVALID",
            ):
                self.observe(
                    metadata_environment,
                    clock=START + timedelta(minutes=2),
                )

            bundle_environment = self.environment(root / "bundle")
            result = self.successful_state(bundle_environment)
            bundle = Path(result["source_bundle_path"])
            bundle.write_bytes(bundle.read_bytes() + b"\n")
            bundle.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_BUNDLE_INVALID",
            ):
                self.observe(
                    bundle_environment,
                    clock=START + timedelta(minutes=2),
                )

            mode_environment = self.environment(root / "mode")
            self.successful_state(mode_environment)
            mode_environment["paths"]["state"].chmod(0o644)
            with self.assertRaisesRegex(
                ChallengerFirstSlotReceiptError,
                "CHALLENGER_FIRST_SLOT_STATE_INVALID",
            ):
                self.observe(
                    mode_environment,
                    clock=START + timedelta(minutes=2),
                )

    def test_schema_mirror_and_cli_authority_are_strict(self):
        self.assertEqual(
            (
                ROOT
                / "config"
                / "challenger-first-slot-receipt-v1.schema.json"
            ).read_bytes(),
            (
                ROOT
                / "src"
                / "crypto_quant"
                / "schemas"
                / "challenger-first-slot-receipt-v1.schema.json"
            ).read_bytes(),
        )
        source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_first_slot_receipt_cli.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "--state",
            "--bundle",
            "--stdout",
            "--stderr",
            "--service",
            "--command",
            "--url",
            "--credential",
            "--order",
            "--clock",
        ):
            self.assertNotIn(forbidden, source)
            with self.subTest(forbidden=forbidden), redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(observer_main([forbidden, "x"]), 2)

    def test_committed_v035_receipt_is_canonical_and_frozen(self):
        artifact_path = (
            ROOT
            / "artifacts"
            / "challenger-forward"
            / "challenger-first-slot-receipt-v0.35.0.json"
        )
        artifact_bytes = artifact_path.read_bytes()
        receipt = json.loads(artifact_bytes)
        schema = json.loads(
            (
                ROOT
                / "config"
                / "challenger-first-slot-receipt-v1.schema.json"
            ).read_bytes()
        )
        self.assertEqual(
            artifact_bytes,
            canonical_json(receipt).encode("utf-8"),
        )
        self.assertFalse(
            tuple(Draft202012Validator(schema).iter_errors(receipt))
        )
        self.assertEqual(
            hashlib.sha256(artifact_bytes).hexdigest(),
            "b1b03bbe584386d3199cef3561fe22b4c"
            "92c3f359429ec43838d2b00a9566e43",
        )
        self.assertEqual(
            receipt["receipt_id"],
            "challenger_first_slot_receipt_"
            "fcc86fe447ab8b2728a9bcd80371c26c9"
            "a30f59cec0b01306b278392b28d3c2b",
        )
        self.assertEqual(
            receipt["receipt_hash"],
            challenger_first_slot_receipt_hash(receipt),
        )
        self.assertEqual(
            receipt["observation_status"],
            "FIRST_SLOT_RECORDED_VERIFIED",
        )
        self.assertEqual(
            receipt["state"]["first_decision"]["scheduled_for"],
            "2026-07-29T00:00:00.000Z",
        )
        self.assertEqual(
            receipt["state"]["first_decision"]["decision_eligibility"],
            "LOCAL_PREQUENTIAL_RESEARCH_ONLY",
        )
        self.assertEqual(
            receipt["state"]["first_decision"]["broker_eligibility"],
            "INELIGIBLE_NO_BROKER_ACCESS",
        )
        self.assertEqual(
            receipt["security_boundary"],
            {
                "arbitrary_command_allowed": False,
                "broker_request_count": 0,
                "launchctl_print_count": 1,
                "network_request_count": 0,
                "order_submission_count": 0,
                "shell_invoked": False,
                "state_write_count": 0,
            },
        )
        self.assertEqual(receipt["eligibility"]["profitability"], "INELIGIBLE")
        self.assertIn("NO_PROFITABILITY_CLAIM", receipt["warnings"])


if __name__ == "__main__":
    unittest.main()
