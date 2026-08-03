"""Immutable System Paper 90-day start receipt tests."""

import io
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
