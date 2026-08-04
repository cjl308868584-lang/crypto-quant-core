"""Immutable System Paper 90-day start receipt tests."""

import io
import copy
import json
import os
import stat
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_start_receipt import (
    SystemPaperStartReceiptError,
    load_system_paper_start_receipt,
    publish_system_paper_start_receipt,
)
from crypto_quant.system_paper_start_receipt_cli import main as start_main
import crypto_quant.system_paper_start_receipt as start_receipt_module
import tests.test_system_paper_observer as observer_helpers


class SystemPaperStartReceiptTests(unittest.TestCase):
    def setUp(self):
        self.observer = observer_helpers.SystemPaperObserverTests()
        self.observer.setUp()
        self.addCleanup(self.observer.doCleanups)

    @property
    def root(self):
        return self.observer.install.preflight.runtime_root / "start-receipts"

    def values(self, runner, observed_at):
        return {
            "contract_path": self.observer.install.preflight.contract_path,
            "plist_path": self.observer.install.preflight.plist_path,
            "preflight_receipt_path": self.observer.preflight_path,
            "install_receipt_path": self.observer.install_receipt_path,
            "_launchctl_runner": runner,
            "_machine_probe": self.observer.install.preflight.machine,
            "_filesystem_probe": self.observer.install.preflight.filesystem,
            "_clock": lambda: observed_at,
        }

    def load(self, path):
        return load_system_paper_start_receipt(
            receipt_path=path,
            contract_path=self.observer.install.preflight.contract_path,
            plist_path=self.observer.install.preflight.plist_path,
            preflight_receipt_path=self.observer.preflight_path,
            install_receipt_path=self.observer.install_receipt_path,
            _machine_probe=self.observer.install.preflight.machine,
            _filesystem_probe=self.observer.install.preflight.filesystem,
        )

    def test_pending_observation_creates_no_start_root_or_file(self):
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(
                    self.observer.install, runs=0, exit_code=None
                ),
                "2026-08-04T07:59:59.000Z",
            )
        )
        self.assertEqual(result["outcome"], "START_RECEIPT_PENDING")
        self.assertFalse(self.root.exists())

    def test_verified_first_slot_derives_exact_ninety_day_cohort_and_loads(self):
        summary = self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        receipt = self.load(path)
        self.assertEqual(receipt["cohort_started_at"], "2026-08-04T08:00:00.000Z")
        self.assertEqual(receipt["cohort_tail_end"], "2026-11-02T08:00:00.000Z")
        self.assertEqual(receipt["expected_slot_count"], 540)
        self.assertEqual(receipt["first_slot"]["slot_id"], summary["slot_id"])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(receipt["security_boundary"]["order_submission_count"], 0)

    def test_metadata_loader_validates_receipt_without_replaying_slot_economics(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        loader = getattr(
            start_receipt_module,
            "load_system_paper_start_receipt_metadata",
            None,
        )
        self.assertIsNotNone(loader)
        with patch.object(
            start_receipt_module,
            "replay_system_paper_first_slot_evidence",
            side_effect=AssertionError("metadata loader replayed slot economics"),
        ):
            receipt = loader(
                receipt_path=Path(result["receipt_path"]),
                contract_path=self.observer.install.preflight.contract_path,
                plist_path=self.observer.install.preflight.plist_path,
                preflight_receipt_path=self.observer.preflight_path,
                install_receipt_path=self.observer.install_receipt_path,
                _machine_probe=self.observer.install.preflight.machine,
                _filesystem_probe=self.observer.install.preflight.filesystem,
            )
        self.assertEqual(receipt["receipt_id"], result["receipt_id"])
        self.assertEqual(
            receipt["cohort_tail_end"], "2026-11-02T08:00:00.000Z"
        )

    def test_exact_bytes_are_idempotent_and_same_identity_conflict_is_preserved(self):
        self.observer.create_success()
        runner = observer_helpers.ObserverLaunchctl(self.observer.install, runs=1)
        first = publish_system_paper_start_receipt(
            **self.values(runner, "2026-08-04T08:10:00.000Z")
        )
        first_bytes = Path(first["receipt_path"]).read_bytes()
        second = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        self.assertEqual(second, first)
        self.assertEqual(Path(first["receipt_path"]).read_bytes(), first_bytes)
        with self.assertRaisesRegex(SystemPaperStartReceiptError, "CONFLICT"):
            publish_system_paper_start_receipt(
                **self.values(
                    observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                    "2026-08-04T08:11:00.000Z",
                )
            )

    def test_loader_rejects_coordinated_rehash_and_external_log_mutation(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        original = path.read_bytes()
        changed = json.loads(original)
        changed["expected_slot_count"] = 539
        changed["receipt_hash"] = artifact_self_hash(changed, "receipt_hash")
        path.write_bytes(canonical_json(changed).encode("utf-8"))
        with self.assertRaises(SystemPaperStartReceiptError):
            self.load(path)
        path.write_bytes(original)
        self.observer.stdout_path.write_bytes(b"changed\n")
        with self.assertRaisesRegex(SystemPaperStartReceiptError, "SOURCE"):
            self.load(path)

    def test_loader_replays_immutable_first_slot_against_coordinated_rehashes(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        original = path.read_bytes()

        def change_both_first(receipt, key, value):
            receipt["first_slot"][key] = copy.deepcopy(value)
            receipt["observation"]["first_slot"][key] = copy.deepcopy(value)

        mutations = {
            "event_chain": lambda value: change_both_first(
                value, "event_chain_end_hash", "0" * 64
            ),
            "prepared_input": lambda value: change_both_first(
                value, "prepared_input_sha256", "1" * 64
            ),
            "prepared_result": lambda value: change_both_first(
                value, "prepared_result_sha256", "2" * 64
            ),
            "runner_summary": lambda value: change_both_first(
                value,
                "runner_summary",
                {
                    **value["first_slot"]["runner_summary"],
                    "outcome": "RESUMED_INPUT",
                },
            ),
            "first_eligible": lambda value: value["observation"][
                "first_eligible_slot"
            ].__setitem__("due_at", "2026-08-04T08:06:00.000Z"),
            "terminal_count": lambda value: value["observation"].__setitem__(
                "terminal_slot_count", 2
            ),
            "launchd_semantics": lambda value: (
                value["observation"]["launchd"].__setitem__("run_count", 2),
                value["observation"]["launchd"]["service_snapshot"].__setitem__(
                    "runs", 2
                ),
            ),
        }
        try:
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    changed = json.loads(original)
                    mutate(changed)
                    changed["receipt_hash"] = artifact_self_hash(
                        changed, "receipt_hash"
                    )
                    path.write_bytes(canonical_json(changed).encode("utf-8"))
                    with self.assertRaisesRegex(
                        SystemPaperStartReceiptError, "INVALID"
                    ):
                        self.load(path)
        finally:
            path.write_bytes(original)
            path.chmod(0o600)

    def test_loader_accepts_later_append_only_slot_and_jsonl_growth(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        first_stdout = self.observer.stdout_path.read_bytes()
        self.observer.create_success("2026-08-04T12:00:00.000Z")
        second_stdout = self.observer.stdout_path.read_bytes()
        self.observer.stdout_path.write_bytes(first_stdout + second_stdout)
        self.observer.stdout_path.chmod(0o600)

        receipt = self.load(path)
        self.assertEqual(
            receipt["first_slot"]["scheduled_for"],
            "2026-08-04T08:00:00.000Z",
        )

    def test_loader_rejects_receipt_over_four_mib_before_json_parse(self):
        self.root.mkdir(mode=0o700, parents=False)
        path = self.root / ("system_paper_start_receipt_" + "0" * 64 + ".json")
        with path.open("wb") as handle:
            handle.truncate(4 * 1024 * 1024 + 1)
        path.chmod(0o600)

        original_read_bytes = Path.read_bytes
        calls = {"receipt": 0}

        def reject_oversized_read(candidate):
            if candidate == path:
                calls["receipt"] += 1
                raise AssertionError("oversized receipt bytes were read")
            return original_read_bytes(candidate)

        with patch.object(Path, "read_bytes", reject_oversized_read):
            with self.assertRaisesRegex(
                SystemPaperStartReceiptError, "READ_INVALID"
            ):
                self.load(path)
        self.assertEqual(calls["receipt"], 0)

    def test_loader_does_not_reopen_receipt_after_path_validation(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        original_read_bytes = Path.read_bytes
        calls = {"receipt": 0}

        def replace_before_path_read(candidate):
            if candidate == path:
                calls["receipt"] += 1
                candidate.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
                candidate.chmod(0o600)
            return original_read_bytes(candidate)

        with patch.object(Path, "read_bytes", replace_before_path_read):
            receipt = self.load(path)
        self.assertEqual(receipt["receipt_id"], result["receipt_id"])
        self.assertEqual(calls["receipt"], 0)

    def test_loader_retains_all_source_descriptors_until_final_replay(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        contract_path = self.observer.install.preflight.contract_path
        contract_bytes = contract_path.read_bytes()
        original_inode = contract_path.stat().st_ino
        original_open = start_receipt_module._RetainedSourceEvidence.open
        captured = {"count": 0}

        def retain_then_replace(evidence):
            retained = original_open(evidence)
            captured["count"] += 1
            if captured["count"] == 1:
                moved = contract_path.with_suffix(".retained-original")
                contract_path.rename(moved)
                contract_path.write_bytes(contract_bytes)
                contract_path.chmod(0o600)
                self.assertNotEqual(contract_path.stat().st_ino, original_inode)
            return retained

        with patch.object(
            start_receipt_module._RetainedSourceEvidence,
            "open",
            side_effect=retain_then_replace,
        ):
            with self.assertRaisesRegex(
                SystemPaperStartReceiptError, "SOURCE_CHANGED"
            ):
                self.load(path)

    def test_loader_reverifies_source_descriptors_after_slot_replay(self):
        self.observer.create_success()
        result = publish_system_paper_start_receipt(
            **self.values(
                observer_helpers.ObserverLaunchctl(self.observer.install, runs=1),
                "2026-08-04T08:10:00.000Z",
            )
        )
        path = Path(result["receipt_path"])
        contract_path = self.observer.install.preflight.contract_path
        contract_bytes = contract_path.read_bytes()
        original_replay = (
            start_receipt_module.replay_system_paper_first_slot_evidence
        )

        def replay_then_replace(*args, **kwargs):
            replay = original_replay(*args, **kwargs)
            retained_name = contract_path.with_suffix(".replay-retained")
            contract_path.rename(retained_name)
            contract_path.write_bytes(contract_bytes)
            contract_path.chmod(0o600)
            return replay

        with patch.object(
            start_receipt_module,
            "replay_system_paper_first_slot_evidence",
            side_effect=replay_then_replace,
        ):
            with self.assertRaisesRegex(
                SystemPaperStartReceiptError, "SOURCE_CHANGED"
            ):
                self.load(path)

    def test_publisher_retains_all_source_descriptors_before_publication(self):
        self.observer.create_success()
        contract_path = self.observer.install.preflight.contract_path
        contract_bytes = contract_path.read_bytes()
        original_inode = contract_path.stat().st_ino
        original_open = start_receipt_module._RetainedSourceEvidence.open
        captured = {"count": 0}

        def retain_then_replace(evidence):
            retained = original_open(evidence)
            captured["count"] += 1
            if captured["count"] == 1:
                moved = contract_path.with_suffix(".retained-original")
                contract_path.rename(moved)
                contract_path.write_bytes(contract_bytes)
                contract_path.chmod(0o600)
                self.assertNotEqual(contract_path.stat().st_ino, original_inode)
            return retained

        with patch.object(
            start_receipt_module._RetainedSourceEvidence,
            "open",
            side_effect=retain_then_replace,
        ):
            with self.assertRaisesRegex(
                SystemPaperStartReceiptError, "SOURCE_CHANGED"
            ):
                publish_system_paper_start_receipt(
                    **self.values(
                        observer_helpers.ObserverLaunchctl(
                            self.observer.install, runs=1
                        ),
                        "2026-08-04T08:10:00.000Z",
                    )
                )
        self.assertFalse(self.root.exists())

    def test_cli_accepts_only_four_source_paths(self):
        expected = {"outcome": "START_RECEIPT_PENDING"}
        with patch(
            "crypto_quant.system_paper_start_receipt_cli.publish_system_paper_start_receipt",
            return_value=expected,
        ) as publish:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = start_main(
                    [
                        "--contract-path", str(self.observer.install.preflight.contract_path),
                        "--plist-path", str(self.observer.install.preflight.plist_path),
                        "--preflight-receipt-path", str(self.observer.preflight_path),
                        "--install-receipt-path", str(self.observer.install_receipt_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            self.assertEqual(stderr.getvalue(), "")
            publish.assert_called_once_with(
                contract_path=self.observer.install.preflight.contract_path,
                plist_path=self.observer.install.preflight.plist_path,
                preflight_receipt_path=self.observer.preflight_path,
                install_receipt_path=self.observer.install_receipt_path,
            )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                start_main(["--cohort-start", "2026-01-01T00:00:00Z"])


if __name__ == "__main__":
    unittest.main()
