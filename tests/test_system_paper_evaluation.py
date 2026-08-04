"""Fixed-tail System Paper evaluation authority tests."""

import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json, stable_id
from crypto_quant.evidence import artifact_self_hash
from crypto_quant.system_paper_evaluation import (
    SystemPaperEvaluationError,
    observe_system_paper_evaluation_readiness,
)
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
)
from crypto_quant.system_paper_start_receipt import (
    publish_system_paper_start_receipt,
)
import tests.test_system_paper_observer as observer_helpers
import tests.test_system_paper_start_receipt as start_helpers


class SystemPaperEvaluationAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.start = start_helpers.SystemPaperStartReceiptTests()
        self.start.setUp()
        self.addCleanup(self.start.doCleanups)
        self.start.observer.create_success()
        published = publish_system_paper_start_receipt(
            **self.start.values(
                observer_helpers.ObserverLaunchctl(
                    self.start.observer.install, runs=1
                ),
                "2026-08-04T08:10:00.000Z",
            )
        )
        self.start_receipt_path = Path(published["receipt_path"])
        preflight = self.start.observer.install.preflight
        self.contract_path = preflight.contract_path
        self.install_receipt_path = self.start.observer.install_receipt_path
        self.runtime_root = preflight.runtime_root
        self.slot_root = self.runtime_root / "artifacts" / "system-paper-slots"
        self.output_root = self.runtime_root / "evaluations"
        self.plan_path = self.runtime_root / "system-paper-plan.json"
        self.plan_path.write_bytes(
            canonical_json(build_system_paper_plan()).encode("utf-8")
        )
        self.plan_path.chmod(0o600)

    def values(self, **overrides):
        values = {
            "plan_path": self.plan_path,
            "start_receipt_path": self.start_receipt_path,
            "install_receipt_path": self.install_receipt_path,
            "contract_path": self.contract_path,
            "slot_root": self.slot_root,
            "runtime_root": self.runtime_root,
            "output_root": self.output_root,
            "_clock": lambda: "2026-08-05T08:10:00.000Z",
            "_machine_probe": self.start.observer.install.preflight.machine,
            "_filesystem_probe": (
                self.start.observer.install.preflight.filesystem
            ),
        }
        values.update(overrides)
        return values

    def mutate_state_metadata(self, table, column, value):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            connection.execute(
                "UPDATE " + table + " SET " + column + "=?",
                (value,),
            )
            for _name, sql in triggers:
                connection.execute(sql)

    def remove_result_constraints_and_duplicate_row(self):
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='trigger' ORDER BY name"
            ).fetchall()
            for name, _sql in triggers:
                connection.execute("DROP TRIGGER " + name)
            connection.execute(
                "ALTER TABLE prepared_results RENAME TO old_prepared_results"
            )
            connection.execute(
                "CREATE TABLE prepared_results ("
                "source_event_id TEXT, slot_id TEXT, result_bytes BLOB, "
                "result_sha256 TEXT, slot_hash TEXT, runtime_snapshot_hash TEXT, "
                "parent_slot_hash TEXT, output_root_hash TEXT)"
            )
            columns = (
                "source_event_id, slot_id, result_bytes, result_sha256, "
                "slot_hash, runtime_snapshot_hash, parent_slot_hash, "
                "output_root_hash"
            )
            connection.execute(
                "INSERT INTO prepared_results (" + columns + ") SELECT "
                + columns
                + " FROM old_prepared_results"
            )
            connection.execute(
                "INSERT INTO prepared_results (" + columns + ") SELECT "
                + columns
                + " FROM old_prepared_results"
            )
            connection.execute("DROP TABLE old_prepared_results")
            for _name, sql in triggers:
                connection.execute(sql)

    def test_pre_tail_observation_is_allowlisted_and_reads_no_slot_economics(self):
        forbidden = AssertionError("pre-tail economic or publication path called")
        with patch(
            "crypto_quant.system_paper_scheduler."
            "load_system_paper_slot_result_bytes",
            side_effect=forbidden,
        ), patch(
            "crypto_quant.system_paper_start_receipt."
            "replay_system_paper_first_slot_evidence",
            side_effect=forbidden,
        ) as start_replay, patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            side_effect=forbidden,
        ) as economic, patch(
            "crypto_quant.system_paper_evaluation.publish_owner_exact",
            side_effect=forbidden,
        ) as publisher:
            result = observe_system_paper_evaluation_readiness(**self.values())

        self.assertEqual(
            set(result),
            {
                "status",
                "observed_at",
                "cohort_started_at",
                "tail_end",
                "elapsed_days",
                "verified_terminal_slot_count",
                "incident_count",
                "next_required_slot",
                "evidence_health",
            },
        )
        self.assertEqual(
            result["status"], "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL"
        )
        self.assertEqual(result["elapsed_days"], 1)
        self.assertEqual(result["verified_terminal_slot_count"], 1)
        self.assertEqual(result["incident_count"], 0)
        self.assertEqual(result["evidence_health"], "VERIFIED")
        self.assertFalse(self.output_root.exists())
        start_replay.assert_not_called()
        economic.assert_not_called()
        publisher.assert_not_called()
        encoded = canonical_json(result).lower()
        for forbidden_name in (
            "pnl",
            "return",
            "win_rate",
            "drawdown",
            "cost",
            "profit",
            "confidence",
        ):
            self.assertNotIn(forbidden_name, encoded)

    def test_absent_state_sidecar_appearing_during_replay_fails_closed(self):
        from crypto_quant import system_paper_evaluation as module

        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        wal_path = Path(str(state_path) + "-wal")
        shm_path = Path(str(state_path) + "-shm")
        for path in (wal_path, shm_path):
            if path.exists():
                path.unlink()
        original = module._copy_event_metadata

        def replay_then_create(*args, **kwargs):
            replay = original(*args, **kwargs)
            wal_path.write_bytes(b"appeared-during-replay")
            wal_path.chmod(0o600)
            return replay

        with patch.object(
            module, "_copy_event_metadata", side_effect=replay_then_create
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_sidecar_created_between_file_open_and_absence_capture_fails_closed(self):
        from crypto_quant import system_paper_evaluation as module

        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with sqlite3.connect(str(state_path)) as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        wal_path = Path(str(state_path) + "-wal")
        shm_path = Path(str(state_path) + "-shm")
        for path in (wal_path, shm_path):
            if path.exists():
                path.unlink()
        original_open = module._RetainedAuthorityFile.open
        created = {"done": False}

        def open_then_create(path, **kwargs):
            if Path(path) == wal_path and not created["done"]:
                created["done"] = True
                wal_path.write_bytes(b"appeared-before-absence-capture")
                wal_path.chmod(0o600)
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return original_open(path, **kwargs)

        with patch.object(
            module._RetainedAuthorityFile,
            "open",
            side_effect=open_then_create,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_coordinated_prepared_input_metadata_mutation(self):
        self.mutate_state_metadata("prepared_inputs", "plan_hash", "0" * 64)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_coordinated_prepared_result_metadata_mutation(self):
        self.mutate_state_metadata("prepared_results", "slot_hash", "0" * 64)
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_rejects_removed_constraints_and_duplicate_prepared_rows(self):
        self.remove_result_constraints_and_duplicate_row()
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "STATE_REPLAY_INVALID"
        ):
            observe_system_paper_evaluation_readiness(**self.values())

    def test_pre_tail_incident_count_includes_failed_attempt_events(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        state_path = self.runtime_root / "state" / "system-paper.sqlite"
        with SystemPaperScheduleState(state_path, policy) as state:
            slot = policy.slot_from_scheduled("2026-08-04T12:00:00.000Z")
            claim = state.claim(
                slot,
                worker_id="failed-attempt-test",
                claimed_at="2026-08-04T12:05:01.000Z",
            )
            state.fail(
                claim,
                reason_code="SYSTEM_PAPER_RUNTIME_INTERRUPTED",
                failed_at="2026-08-04T12:05:02.000Z",
            )
        result = observe_system_paper_evaluation_readiness(**self.values())
        self.assertEqual(result["verified_terminal_slot_count"], 1)
        self.assertEqual(result["incident_count"], 1)
        self.assertEqual(result["evidence_health"], "INCIDENT_DETECTED")

    def test_all_seven_authority_paths_must_be_absolute_and_exact(self):
        path_names = (
            "plan_path",
            "start_receipt_path",
            "install_receipt_path",
            "contract_path",
            "slot_root",
            "runtime_root",
            "output_root",
        )
        for name in path_names:
            with self.subTest(name=name), self.assertRaisesRegex(
                SystemPaperEvaluationError, "PATH_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(**{name: Path("relative")})
                )
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "ROOT_MISMATCH"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(runtime_root=self.runtime_root / "other")
            )
        with self.assertRaisesRegex(
            SystemPaperEvaluationError, "ROOT_MISMATCH"
        ):
            observe_system_paper_evaluation_readiness(
                **self.values(slot_root=self.runtime_root / "artifacts")
            )

    def test_install_preview_is_bounded_before_json_parse(self):
        oversized = self.runtime_root / "oversized-install.json"
        with oversized.open("wb") as handle:
            handle.truncate(2 * 1024 * 1024 + 1)
        oversized.chmod(0o600)
        original_read_bytes = Path.read_bytes
        calls = {"oversized": 0}

        def reject_path_read(candidate):
            if candidate == oversized:
                calls["oversized"] += 1
                raise AssertionError("oversized install preview was read")
            return original_read_bytes(candidate)

        with patch.object(Path, "read_bytes", reject_path_read):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "INSTALL_PREVIEW_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(install_receipt_path=oversized)
                )
        self.assertEqual(calls["oversized"], 0)

    def test_install_preview_rejects_noncanonical_bytes_before_strict_loader(self):
        noncanonical = self.runtime_root / "noncanonical-install.json"
        noncanonical.write_bytes(b'{"preflight_receipt": {"receipt_path": "/x"}}\n')
        noncanonical.chmod(0o600)
        with patch(
            "crypto_quant.system_paper_evaluation."
            "load_system_paper_install_receipt",
            side_effect=AssertionError("strict loader reached"),
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "INSTALL_PREVIEW_INVALID"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(install_receipt_path=noncanonical)
                )

    def test_install_preview_cannot_redirect_derived_authority(self):
        original_bytes = self.install_receipt_path.read_bytes()
        forged = json.loads(original_bytes)
        redirected_target = Path(
            json.loads(self.start_receipt_path.read_bytes())["first_slot"][
                "result_path"
            ]
        )
        forged["target_path"] = str(redirected_target)
        identity = {
            "contract_hash": forged["source_contract"]["contract_hash"],
            "preflight_receipt_hash": forged["preflight_receipt"]["receipt_hash"],
            "target_path": forged["target_path"],
            "target_inode": forged["target_stat"]["inode"],
            "install_action": forged["install_action"],
            "installed_at": forged["installed_at"],
            "verified_at": forged["verified_at"],
            "installation_status": forged["installation_status"],
        }
        forged["receipt_id"] = stable_id(
            "system_paper_install_receipt", identity
        )
        forged["receipt_hash"] = artifact_self_hash(forged, "receipt_hash")
        original_stash = self.runtime_root / "original-install-receipt.json"
        self.install_receipt_path.rename(original_stash)
        forged_path = self.install_receipt_path.parent / (
            forged["receipt_id"] + ".json"
        )
        forged_path.write_bytes(canonical_json(forged).encode("utf-8"))
        forged_path.chmod(0o600)
        from crypto_quant import system_paper_install as install_module

        original_target_stat = install_module._target_stat
        redirected_reads = {"count": 0}

        def reject_redirected_target(path, *args, **kwargs):
            if Path(path) == redirected_target:
                redirected_reads["count"] += 1
                raise AssertionError("redirected target was opened")
            return original_target_stat(path, *args, **kwargs)

        try:
            with patch.object(
                install_module,
                "_target_stat",
                side_effect=reject_redirected_target,
            ):
                with self.assertRaises(SystemPaperEvaluationError):
                    observe_system_paper_evaluation_readiness(
                        **self.values(install_receipt_path=forged_path)
                    )
        finally:
            if forged_path.exists():
                forged_path.unlink()
            original_stash.rename(self.install_receipt_path)
            self.install_receipt_path.write_bytes(original_bytes)
            self.install_receipt_path.chmod(0o600)
        self.assertEqual(redirected_reads["count"], 0)

    def test_source_replacement_after_capture_fails_before_return(self):
        from crypto_quant import system_paper_evaluation as module

        original_open = module._RetainedAuthorityFile.open
        captured = {"plan": 0}
        plan_bytes = self.plan_path.read_bytes()
        original_inode = self.plan_path.stat().st_ino

        def retain_then_replace(path, **kwargs):
            retained = original_open(path, **kwargs)
            if Path(path) == self.plan_path and captured["plan"] == 0:
                captured["plan"] += 1
                moved = self.plan_path.with_suffix(".retained-original")
                self.plan_path.rename(moved)
                self.plan_path.write_bytes(plan_bytes)
                self.plan_path.chmod(0o600)
                self.assertNotEqual(self.plan_path.stat().st_ino, original_inode)
            return retained

        with patch.object(
            module._RetainedAuthorityFile,
            "open",
            side_effect=retain_then_replace,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_installed_target_is_retained_through_state_replay(self):
        from crypto_quant import system_paper_evaluation as module

        install = json.loads(self.install_receipt_path.read_bytes())
        target_path = Path(install["target_path"])
        target_bytes = target_path.read_bytes()
        original = module._copy_event_metadata

        def replay_then_replace(*args, **kwargs):
            replay = original(*args, **kwargs)
            retained_name = target_path.with_suffix(".evaluation-retained")
            target_path.rename(retained_name)
            target_path.write_bytes(target_bytes)
            target_path.chmod(0o600)
            return replay

        with patch.object(
            module, "_copy_event_metadata", side_effect=replay_then_replace
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(**self.values())

    def test_post_tail_result_reverifies_all_retained_sources_before_return(self):
        plan_bytes = self.plan_path.read_bytes()

        def mutate_then_return(**_kwargs):
            retained_name = self.plan_path.with_suffix(".post-tail-retained")
            self.plan_path.rename(retained_name)
            self.plan_path.write_bytes(plan_bytes)
            self.plan_path.chmod(0o600)
            return {"status": "POST_TAIL_TEST_RESULT"}

        with patch(
            "crypto_quant.system_paper_evaluation._evaluate_complete_cohort",
            side_effect=mutate_then_return,
        ):
            with self.assertRaisesRegex(
                SystemPaperEvaluationError, "SOURCE_CHANGED"
            ):
                observe_system_paper_evaluation_readiness(
                    **self.values(
                        _clock=lambda: "2026-11-02T08:05:00.000Z"
                    )
                )


if __name__ == "__main__":
    unittest.main()
