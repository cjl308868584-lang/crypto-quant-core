import io
import hashlib
import json
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from tests import test_challenger_replacement_live_runtime as live_fixture


class ReplacementInstalledRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = live_fixture.LiveRuntimeTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def _sources(self):
        return {
            "state": self.fixture._state(),
            "event_root": self.fixture.root,
            "worker_id": "challenger-replacement-natural-runner-v1",
            "first_eligible_scheduled_for": self.fixture.live_capture.document[
                "slot"
            ]["scheduled_for"],
        }

    def _install_inputs_for_fixture(self):
        from tests.test_challenger_replacement_install import install_inputs

        inputs = install_inputs()
        identity = self.fixture.workspace.identity()
        inputs["contract"]["event_root"].update({
            "path": identity.absolute_path, "device": identity.device,
            "inode": identity.inode, "owner_uid": identity.uid,
        })
        start_root = self.fixture.workspace.base / "start-receipts"
        start_root.mkdir(mode=0o700)
        inputs["contract"]["paths"]["start_receipt_root"] = str(start_root)
        return inputs

    def test_missing_verified_install_receipt_stops_before_capture_or_append(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime

        state = self.fixture._state()
        with mock.patch.object(
            runtime, "_load_fixed_runtime_sources",
            side_effect=runtime.ReplacementInstalledRuntimeError(
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED"
            ),
        ), mock.patch.object(runtime, "acquire_challenger_replacement_live_capture") as acquire, \
             mock.patch.object(state, "append") as append:
            with self.assertRaisesRegex(
                runtime.ReplacementInstalledRuntimeError,
                "CHALLENGER_REPLACEMENT_INSTALL_RECEIPT_REQUIRED",
            ):
                runtime.run_fixed_replacement_installed_invocation()
        acquire.assert_not_called()
        append.assert_not_called()

    def test_fixture_invocation_delegates_to_existing_three_event_core_and_closes(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime

        sources = self._sources()
        with mock.patch.object(
            runtime, "_load_fixed_runtime_sources", return_value=sources
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture",
            return_value=self.fixture.live_capture,
        ) as acquire, mock.patch.object(
            runtime, "_wall_now",
            return_value=datetime(2026, 8, 22, 4, 5, tzinfo=timezone.utc),
        ), mock.patch.object(
            sources["event_root"], "close", wraps=sources["event_root"].close
        ) as close:
            summary = runtime.run_fixed_replacement_installed_invocation()
        self.assertEqual(summary["terminal_stage"], "SLOT_SUCCEEDED")
        self.assertEqual(summary["event_count"], 3)
        projection = self.fixture._fresh_state().replay()
        self.assertEqual(
            [json.loads(event.final_bytes)["event_type"]
             for event in projection["events"]],
            ["INPUT_PREPARED", "RESULT_PREPARED", "SLOT_SUCCEEDED"],
        )
        acquire.assert_called_once()
        close.assert_called_once()

    def test_early_genesis_invocation_closes_without_capture_or_event(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime

        sources = self._sources()
        state = sources["state"]
        with mock.patch.object(
            runtime, "_load_fixed_runtime_sources", return_value=sources
        ), mock.patch.object(
            runtime, "_wall_now",
            return_value=datetime(2026, 8, 22, 4, 1, tzinfo=timezone.utc),
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture"
        ) as acquire, mock.patch.object(state, "append") as append:
            with self.assertRaisesRegex(
                runtime.ReplacementInstalledRuntimeError,
                "CHALLENGER_REPLACEMENT_RUNTIME_WINDOW_INVALID",
            ):
                runtime.run_fixed_replacement_installed_invocation()
        acquire.assert_not_called()
        append.assert_not_called()

    def test_fixed_source_loader_opens_only_receipt_bound_event_root(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime

        inputs = self._install_inputs_for_fixture()
        identity = self.fixture.workspace.identity()
        inputs["contract"]["event_root"].update({
            "path": identity.absolute_path, "device": identity.device,
            "inode": identity.inode, "owner_uid": identity.uid,
        })
        with mock.patch.object(
            runtime, "_load_fixed_successful_install_receipt",
            return_value=(inputs, {"status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT",
                                   "first_eligible_scheduled_for": "2026-08-22T04:00:00.000Z"},
                          b"receipt"),
        ), mock.patch.object(
            runtime, "_load_snapshot_plan_and_strategy",
            return_value=self.fixture.plan,
        ):
            sources = runtime._load_fixed_runtime_sources()
        try:
            self.assertEqual(sources["state"].plan, self.fixture.plan)
            self.assertEqual(sources["event_root"].inode, identity.inode)
            self.assertEqual(sources["first_eligible_scheduled_for"],
                             "2026-08-22T04:00:00.000Z")
        finally:
            sources["event_root"].close()

    def test_prestart_orphan_staging_stops_before_network_or_append(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime

        inputs = self._install_inputs_for_fixture()
        orphan = self.fixture.workspace.event_root / (
            ".stage-00000000000000000001-{}-{}.tmp".format(
                "a" * 64, "b" * 32
            )
        )
        orphan.write_bytes(b"partial")
        orphan.chmod(0o600)
        install_receipt = {
            "status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT",
            "first_eligible_scheduled_for": "2026-08-22T04:00:00.000Z",
        }
        with mock.patch.object(
            runtime, "_load_fixed_successful_install_receipt",
            return_value=(inputs, install_receipt, b"receipt"),
        ), mock.patch.object(
            runtime, "_load_snapshot_plan_and_strategy",
            return_value=self.fixture.plan,
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture"
        ) as acquire, mock.patch.object(
            runtime.ChallengerReplacementRuntimeState, "append"
        ) as append:
            with self.assertRaisesRegex(
                runtime.ReplacementInstalledRuntimeError,
                "CHALLENGER_REPLACEMENT_START_RECEIPT_REQUIRED",
            ):
                runtime.run_fixed_replacement_installed_invocation()

        acquire.assert_not_called()
        append.assert_not_called()
        self.assertEqual(orphan.read_bytes(), b"partial")

    def test_prestart_completed_slot_cannot_be_replayed_as_installed_success(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime
        from crypto_quant.challenger_replacement_runtime import (
            run_challenger_replacement_cohort_slot,
        )

        run_challenger_replacement_cohort_slot(
            state=self.fixture._state(),
            live_capture=self.fixture.live_capture,
            worker_id="preloaded-worker",
        )
        inputs = self._install_inputs_for_fixture()
        inputs["contract"]["strategy_core"].update(
            self.fixture.build_identity
        )
        install_receipt = {
            "status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT",
            "installed_at": "2026-08-22T04:15:00.000Z",
            "first_eligible_scheduled_for": "2026-08-22T08:00:00.000Z",
        }
        before = tuple(self.fixture._state().replay()["events"])
        with mock.patch.object(
            runtime, "_load_fixed_successful_install_receipt",
            return_value=(inputs, install_receipt, b"receipt"),
        ), mock.patch.object(
            runtime, "_load_snapshot_plan_and_strategy",
            return_value=self.fixture.plan,
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture"
        ) as acquire, mock.patch.object(
            runtime.ChallengerReplacementRuntimeState, "append"
        ) as append:
            with self.assertRaisesRegex(
                runtime.ReplacementInstalledRuntimeError,
                "CHALLENGER_REPLACEMENT_START_RECEIPT_REQUIRED",
            ):
                runtime.run_fixed_replacement_installed_invocation()

        acquire.assert_not_called()
        append.assert_not_called()
        self.assertEqual(tuple(self.fixture._state().replay()["events"]), before)

    def test_first_slot_input_crash_resumes_without_start_receipt(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime
        import crypto_quant.challenger_replacement_runtime as core

        state = self.fixture._state()
        original = state.append

        def crash_after_input(**kwargs):
            event = original(**kwargs)
            if kwargs["event_type"] == "INPUT_PREPARED":
                raise SystemExit("test crash")
            return event

        with mock.patch.object(state, "append", side_effect=crash_after_input):
            with self.assertRaises(SystemExit):
                core.run_challenger_replacement_cohort_slot(
                    state=state, live_capture=self.fixture.live_capture,
                    worker_id="crash-worker",
                )
        inputs = self._install_inputs_for_fixture()
        inputs["contract"]["strategy_core"].update(
            self.fixture.build_identity
        )
        install_receipt = {
            "status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT",
            "installed_at": "2026-08-22T00:15:00.000Z",
            "first_eligible_scheduled_for": "2026-08-22T04:00:00.000Z",
        }
        with mock.patch.object(
            runtime, "_load_fixed_successful_install_receipt",
            return_value=(inputs, install_receipt, b"receipt"),
        ), mock.patch.object(
            runtime, "_load_snapshot_plan_and_strategy",
            return_value=self.fixture.plan,
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture"
        ) as acquire:
            result = runtime.run_fixed_replacement_installed_invocation()

        self.assertEqual(result["terminal_stage"], "SLOT_SUCCEEDED")
        self.assertEqual(len(self.fixture._state().replay()["events"]), 3)
        acquire.assert_not_called()

    def test_first_slot_result_crash_resumes_without_start_receipt(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime
        import crypto_quant.challenger_replacement_runtime as core

        state = self.fixture._state()
        original = state.append

        def crash_after_result(**kwargs):
            event = original(**kwargs)
            if kwargs["event_type"] == "RESULT_PREPARED":
                raise SystemExit("test crash")
            return event

        with mock.patch.object(state, "append", side_effect=crash_after_result):
            with self.assertRaises(SystemExit):
                core.run_challenger_replacement_cohort_slot(
                    state=state, live_capture=self.fixture.live_capture,
                    worker_id="crash-worker",
                )
        inputs = self._install_inputs_for_fixture()
        inputs["contract"]["strategy_core"].update(
            self.fixture.build_identity
        )
        install_receipt = {
            "status": "INSTALLED_WAITING_FOR_FIRST_NATURAL_SLOT",
            "installed_at": "2026-08-22T00:15:00.000Z",
            "first_eligible_scheduled_for": "2026-08-22T04:00:00.000Z",
        }
        with mock.patch.object(
            runtime, "_load_fixed_successful_install_receipt",
            return_value=(inputs, install_receipt, b"receipt"),
        ), mock.patch.object(
            runtime, "_load_snapshot_plan_and_strategy",
            return_value=self.fixture.plan,
        ), mock.patch.object(
            runtime, "acquire_challenger_replacement_live_capture"
        ) as acquire:
            result = runtime.run_fixed_replacement_installed_invocation()

        self.assertEqual(result["terminal_stage"], "SLOT_SUCCEEDED")
        self.assertEqual(len(self.fixture._state().replay()["events"]), 3)
        acquire.assert_not_called()

    def test_snapshot_plan_loader_replays_strategy_bytes_before_state(self):
        import crypto_quant.challenger_replacement_installed_runtime as runtime
        import crypto_quant.challenger_replacement_install_trust as trust
        from tests.test_challenger_replacement_install_trust import (
            ROOT, temporary_workspace, valid_contract,
        )

        with temporary_workspace() as directory:
            repository = Path(directory) / "repository"
            snapshots = Path(directory) / "snapshots"
            repository.mkdir(mode=0o700)
            snapshots.mkdir(mode=0o700)
            contract = valid_contract()
            frozen_plan = json.loads(
                (ROOT / contract["plan"]["path"]).read_text(encoding="utf-8")
            )
            contract["plan"]["plan_id"] = frozen_plan["plan_id"]
            names = {
                **contract["strategy_core"]["file_hashes"],
                contract["plan"]["path"]: contract["plan"]["file_sha256"],
            }
            for name, digest in names.items():
                body = (ROOT / name).read_bytes()
                self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
                target = repository / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                target.chmod(0o600)
            snapshot = trust._publish_snapshot_from_inventory(
                repository, snapshots, names
            )
            contract["snapshot"] = {
                key: snapshot[key] for key in (
                    "root", "tree_hash", "file_count", "total_size_bytes",
                    "root_device", "root_inode",
                )
            }
            plan = runtime._load_snapshot_plan_and_strategy(contract)
            self.assertEqual(plan["plan_hash"], contract["plan"]["plan_hash"])
            target = Path(snapshot["root"]) / next(
                iter(contract["strategy_core"]["file_hashes"])
            )
            target.write_bytes(b"changed")
            target.chmod(0o600)
            with self.assertRaises(trust.ReplacementInstallTrustError):
                runtime._load_snapshot_plan_and_strategy(contract)

    def test_cli_rejects_arguments_before_loading_runtime_sources(self):
        from crypto_quant import challenger_replacement_installed_runtime_cli as cli

        stderr = io.StringIO()
        with mock.patch.object(cli, "run_fixed_replacement_installed_invocation") as run, \
             redirect_stderr(stderr):
            self.assertEqual(cli.main(["--start"]), 2)
        run.assert_not_called()
        self.assertIn("ARGUMENTS_FORBIDDEN", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
