import copy
import hashlib
import io
import json
import shutil
import stat
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_first_episode_receipt import (
    ChallengerFirstEpisodeReceiptError,
    challenger_first_episode_receipt_hash,
    load_challenger_first_episode_receipt,
    observe_challenger_first_episode,
)
from crypto_quant.challenger_first_episode_receipt_cli import (
    main as observer_main,
)
from crypto_quant.challenger_forward_runner import (
    run_challenger_forward_cycle,
)
from tests import test_challenger_first_slot_receipt as first_slot_tests
from tests.test_challenger_forward_runner import (
    KlineTransport,
    gate_at,
    raw_window,
)


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 7, 29, tzinfo=timezone.utc)


class ChallengerFirstEpisodeReceiptTests(unittest.TestCase):
    def environment(self, root):
        helper = first_slot_tests.ChallengerFirstSlotReceiptTests()
        environment = helper.environment(root)
        environment["receipt_output_root"] = root / "episode-receipts"
        return environment

    def record(self, environment, stream):
        results = []
        for index in range(len(stream) - 20):
            slot = START + timedelta(hours=4 * index)
            now = slot + timedelta(minutes=1)
            gate, _source = gate_at(now)
            result = run_challenger_forward_cycle(
                state_path=environment["paths"]["state"],
                output_root=environment["paths"]["output"],
                runtime_gate=gate,
                kline_transport=KlineTransport(
                    raw_window(slot, stream[index : index + 21]),
                    now,
                ),
            )
            results.append(result)
        stdout = environment["paths"]["stdout"]
        stderr = environment["paths"]["stderr"]
        stdout.parent.mkdir(parents=True, exist_ok=True)
        stdout.write_bytes(
            b"".join(
                (
                    json.dumps(
                        result,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                for result in results
            )
        )
        stderr.write_bytes(b"")
        stdout.chmod(0o600)
        stderr.chmod(0o600)
        return results

    def observe(self, environment, clock):
        return observe_challenger_first_episode(
            install_receipt_path=environment[
                "install_receipt_path"
            ],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
            receipt_output_root=environment["receipt_output_root"],
            clock=lambda: clock,
            _launchctl_runner=environment["service"],
        )

    def load(self, environment, receipt_path):
        return load_challenger_first_episode_receipt(
            receipt_path=receipt_path,
            install_receipt_path=environment[
                "install_receipt_path"
            ],
            contract_path=environment["contract_path"],
            plist_path=environment["plist_path"],
        )

    def test_in_progress_is_verified_read_only_and_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, [100] * 20 + [102])
            before = environment["paths"]["state"].read_bytes()
            observed = self.observe(
                environment, START + timedelta(hours=1)
            )
            self.assertEqual(
                observed["status"],
                "FIRST_EPISODE_IN_PROGRESS_VERIFIED",
            )
            self.assertEqual(observed["decision_count"], 1)
            self.assertEqual(
                observed["next_scheduled_for"],
                "2026-07-29T04:00:00.000Z",
            )
            self.assertFalse(observed["receipt_published"])
            self.assertEqual(observed["network_request_count"], 0)
            self.assertEqual(observed["state_write_count"], 0)
            self.assertEqual(
                before, environment["paths"]["state"].read_bytes()
            )
            self.assertFalse(
                environment["receipt_output_root"].exists()
            )

    def test_missing_next_slot_fails_at_its_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(environment, [100] * 20 + [102])
            with self.assertRaisesRegex(
                ChallengerFirstEpisodeReceiptError,
                "CHALLENGER_FIRST_EPISODE_SLOT_MISSED",
            ):
                self.observe(
                    environment, START + timedelta(hours=8)
                )

    def test_sma_exit_publishes_canonical_loadable_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            results = self.record(
                environment, [100] * 20 + [102, 103, 99]
            )
            self.assertEqual(
                [result["decision_count"] for result in results],
                [1, 2, 3],
            )
            observed = self.observe(
                environment, START + timedelta(hours=8, minutes=2)
            )
            self.assertEqual(
                observed["status"],
                "FIRST_EPISODE_COMPLETED_VERIFIED",
            )
            self.assertEqual(observed["exit_action"], "EXIT_LONG_SMA20")
            self.assertTrue(observed["receipt_published"])
            receipt_path = Path(observed["receipt_path"])
            self.assertEqual(
                stat.S_IMODE(receipt_path.stat().st_mode), 0o600
            )
            receipt = self.load(environment, receipt_path)
            self.assertEqual(receipt["receipt_hash"], observed["receipt_hash"])
            self.assertEqual(receipt["state"]["episode_decision_count"], 3)
            self.assertEqual(len(receipt["source_bundles"]), 3)
            self.assertEqual(
                receipt_path.read_bytes(),
                canonical_json(receipt).encode("utf-8"),
            )

    def test_vertical_exit_uses_seven_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            self.record(
                environment,
                [100] * 20 + [102, 103, 104, 105, 106, 107, 108],
            )
            observed = self.observe(
                environment, START + timedelta(hours=24, minutes=2)
            )
            self.assertEqual(
                observed["exit_action"], "EXIT_LONG_VERTICAL_24H"
            )
            receipt = self.load(
                environment, Path(observed["receipt_path"])
            )
            self.assertEqual(receipt["state"]["episode_decision_count"], 7)
            self.assertEqual(len(receipt["logs"]["stdout"]["matched_records"]), 7)

    def test_later_state_and_log_append_preserve_bound_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = self.environment(Path(directory))
            stream = [100] * 20 + [102, 103, 99]
            results = self.record(environment, stream)
            observed = self.observe(
                environment, START + timedelta(hours=8, minutes=2)
            )
            stdout = environment["paths"]["stdout"]
            original_log = stdout.read_bytes()
            slot = START + timedelta(hours=12)
            now = slot + timedelta(minutes=1)
            gate, _source = gate_at(now)
            appended = run_challenger_forward_cycle(
                state_path=environment["paths"]["state"],
                output_root=environment["paths"]["output"],
                runtime_gate=gate,
                kline_transport=KlineTransport(
                    raw_window(slot, (stream + [99])[3:]),
                    now,
                ),
            )
            stdout.write_bytes(
                original_log
                + (
                    json.dumps(
                        appended,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
            stdout.chmod(0o600)
            receipt = self.load(
                environment, Path(observed["receipt_path"])
            )
            self.assertEqual(receipt["state"]["episode_decision_count"], 3)
            self.assertEqual(results[-1]["decision_count"], 3)
            self.assertEqual(appended["decision_count"], 4)

    def test_duplicate_bundle_and_log_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle_environment = self.environment(root / "bundle")
            results = self.record(
                bundle_environment, [100] * 20 + [102]
            )
            source = Path(results[0]["source_bundle_path"])
            duplicate = source.parent / "duplicate.json"
            shutil.copy2(source, duplicate)
            duplicate.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstEpisodeReceiptError,
                "CHALLENGER_FIRST_EPISODE_BUNDLE_COUNT_INVALID",
            ):
                self.observe(
                    bundle_environment, START + timedelta(hours=1)
                )

            log_environment = self.environment(root / "log")
            self.record(log_environment, [100] * 20 + [102])
            stdout = log_environment["paths"]["stdout"]
            stdout.write_bytes(stdout.read_bytes() * 2)
            stdout.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstEpisodeReceiptError,
                "CHALLENGER_FIRST_EPISODE_LOG_MATCH_INVALID",
            ):
                self.observe(log_environment, START + timedelta(hours=1))

    def test_rehash_cannot_hide_boundary_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment = self.environment(root)
            self.record(
                environment, [100] * 20 + [102, 103, 99]
            )
            observed = self.observe(
                environment, START + timedelta(hours=8, minutes=2)
            )
            receipt = json.loads(
                Path(observed["receipt_path"]).read_text()
            )
            changed = copy.deepcopy(receipt)
            changed["security_boundary"]["order_submission_count"] = 1
            changed["receipt_hash"] = (
                challenger_first_episode_receipt_hash(changed)
            )
            tampered = root / "tampered.json"
            tampered.write_bytes(canonical_json(changed).encode("utf-8"))
            tampered.chmod(0o600)
            with self.assertRaisesRegex(
                ChallengerFirstEpisodeReceiptError,
                "CHALLENGER_FIRST_EPISODE_RECEIPT_INVALID",
            ):
                self.load(environment, tampered)

    def test_schema_mirror_and_cli_authority_are_strict(self):
        config = (
            ROOT
            / "config"
            / "challenger-first-episode-receipt-v1.schema.json"
        )
        package = (
            ROOT
            / "src"
            / "crypto_quant"
            / "schemas"
            / "challenger-first-episode-receipt-v1.schema.json"
        )
        self.assertEqual(config.read_bytes(), package.read_bytes())
        schema = json.loads(config.read_bytes())
        Draft202012Validator.check_schema(schema)
        source = (
            ROOT
            / "src"
            / "crypto_quant"
            / "challenger_first_episode_receipt_cli.py"
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

    def test_committed_v036_in_progress_evidence_is_frozen(self):
        artifact_path = (
            ROOT
            / "artifacts"
            / "challenger-forward"
            / "challenger-first-episode-in-progress-v0.36.0.json"
        )
        artifact_bytes = artifact_path.read_bytes()
        artifact = json.loads(artifact_bytes)
        self.assertEqual(
            hashlib.sha256(artifact_bytes).hexdigest(),
            "9be7781856e9d6f3270b9ee1f78a69da"
            "5c1a0adbbb65bd7d72d5b4cd44fcfcce",
        )
        self.assertEqual(
            artifact["status"],
            "FIRST_EPISODE_IN_PROGRESS_VERIFIED",
        )
        self.assertEqual(artifact["episode"]["decision_count"], 1)
        self.assertFalse(
            artifact["observer_execution"]["receipt_published"]
        )
        self.assertEqual(
            artifact["observer_execution"],
            {
                "receipt_published": False,
                "launchctl_command_count": 1,
                "network_request_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
                "state_write_count": 0,
            },
        )
        self.assertEqual(
            artifact["source_integrity"]["state"]["sha256_before"],
            artifact["source_integrity"]["state"]["sha256_after"],
        )
        self.assertEqual(
            artifact["source_integrity"]["stdout"]["sha256_before"],
            artifact["source_integrity"]["stdout"]["sha256_after"],
        )
        self.assertEqual(
            artifact["eligibility"]["profitability"],
            "INELIGIBLE",
        )


if __name__ == "__main__":
    unittest.main()
