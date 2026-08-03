"""Read-only System Paper first-natural-slot observer tests."""

import io
import hashlib
import json
import os
import sqlite3
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_observer import (
    SystemPaperObserverError,
    observe_system_paper_first_slot,
)
from crypto_quant.system_paper_observer_cli import main as observer_main
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
    run_due_system_paper_slot,
)
import tests.test_system_paper_install as install_helpers
from tests.test_system_paper_scheduler import (
    RecordingProvider,
    capture_time_after_public_responses,
)


FIRST_SCHEDULED = "2026-08-04T08:00:00.000Z"
FIRST_DUE = "2026-08-04T08:05:00.000Z"


class ObserverLaunchctl:
    def __init__(self, fixture, *, runs=0, exit_code=0, callback=None):
        self.fixture = fixture
        self.runs = runs
        self.exit_code = exit_code
        self.callback = callback
        self.calls = []

    def __call__(self, argv):
        call = tuple(str(item) for item in argv)
        self.calls.append(call)
        expected = (
            "/bin/launchctl",
            "print",
            f"gui/{self.fixture.preflight.uid}/local.crypto-quant.system-paper-v1",
        )
        if call != expected:
            raise AssertionError(f"unexpected observer authority: {call}")
        values = [
            expected[-1],
            "local.crypto-quant.system-paper-v1",
            str(self.fixture.target),
            self.fixture.contract["python_executable"],
            "crypto_quant.system_paper_runtime_cli",
            self.fixture.contract["program_arguments"][4],
            self.fixture.contract["program_arguments"][6],
            self.fixture.contract["execution_snapshot"]["repository_root"],
            f"runs = {self.runs}",
        ]
        if self.exit_code is not None:
            values.append(f"last exit code = {self.exit_code}")
        result = install_helpers.LaunchctlResult(
            0, ("\n".join(values) + "\n").encode("utf-8"), b""
        )
        if self.callback is not None:
            self.callback()
        return result


class SystemPaperObserverTests(unittest.TestCase):
    def setUp(self):
        self.install = install_helpers.SystemPaperInstallTests()
        self.install.setUp()
        self.addCleanup(self.install.doCleanups)
        self.preflight_path = self.install.verified_preflight()
        install_runner = self.install.runner()
        self.install_result = install_helpers.install_system_paper_launchd(
            **self.install.values(self.preflight_path, install_runner)
        )
        self.install_receipt_path = Path(self.install_result["receipt_path"])
        self.state_path = self.install.preflight.runtime_root / "state" / "system-paper.sqlite"
        self.output_root = self.install.preflight.runtime_root / "artifacts"
        self.stdout_path = self.install.preflight.runtime_root / "log" / "system-paper.stdout.log"
        self.stderr_path = self.install.preflight.runtime_root / "log" / "system-paper.stderr.log"

    def values(self, runner, observed_at):
        return {
            "contract_path": self.install.preflight.contract_path,
            "plist_path": self.install.preflight.plist_path,
            "preflight_receipt_path": self.preflight_path,
            "install_receipt_path": self.install_receipt_path,
            "_launchctl_runner": runner,
            "_machine_probe": self.install.preflight.machine,
            "_filesystem_probe": self.install.preflight.filesystem,
            "_clock": lambda: observed_at,
        }

    def create_success(self, scheduled_for=FIRST_SCHEDULED):
        due = scheduled_for.replace(":00:00.000Z", ":05:11.000Z")
        captured = capture_time_after_public_responses(due)
        summary = run_due_system_paper_slot(
            state_path=self.state_path,
            output_root=self.output_root,
            plan=build_system_paper_plan(),
            worker_id="observer-fixture-worker",
            public_input_provider=RecordingProvider(captured),
            fill_scenario=FillScenario.immediate_full(),
            clock=lambda: due,
        )
        for path in self.state_path.parent.glob(self.state_path.name + "*"):
            path.chmod(0o600)
        self.stdout_path.write_bytes(canonical_json(summary).encode("utf-8") + b"\n")
        self.stderr_path.write_bytes(b"")
        self.stdout_path.chmod(0o600)
        self.stderr_path.chmod(0o600)
        return summary

    def test_waiting_states_are_read_only_and_use_one_fixed_print(self):
        before_runner = ObserverLaunchctl(self.install, runs=0, exit_code=None)
        before = observe_system_paper_first_slot(
            **self.values(before_runner, "2026-08-04T07:59:59.000Z")
        )
        self.assertEqual(before["status"], "WAITING_BEFORE_FIRST_NATURAL_SLOT")
        self.assertIsNone(before["launchd"]["last_exit_code"])
        self.assertEqual(len(before_runner.calls), 1)

        waiting_runner = ObserverLaunchctl(self.install, runs=0)
        waiting = observe_system_paper_first_slot(
            **self.values(waiting_runner, FIRST_DUE)
        )
        self.assertEqual(waiting["status"], "WAITING_FOR_FIRST_NATURAL_SLOT")
        self.assertEqual(waiting["successful_slot_count"], 0)
        self.assertEqual(waiting["security_boundary"]["state_write_count"], 0)
        self.assertEqual(waiting["security_boundary"]["network_request_count"], 0)
        self.assertEqual(waiting["security_boundary"]["runtime_invocation_count"], 0)
        self.assertFalse(self.state_path.exists())

    def test_one_exact_success_replays_state_prepared_result_artifact_and_logs(self):
        summary = self.create_success()
        runner = ObserverLaunchctl(self.install, runs=1)
        observation = observe_system_paper_first_slot(
            **self.values(runner, "2026-08-04T08:10:00.000Z")
        )

        self.assertEqual(observation["status"], "FIRST_NATURAL_SLOT_VERIFIED")
        self.assertEqual(observation["successful_slot_count"], 1)
        self.assertEqual(observation["terminal_slot_count"], 1)
        self.assertEqual(observation["first_slot"]["slot_id"], summary["slot_id"])
        self.assertEqual(observation["first_slot"]["scheduled_for"], FIRST_SCHEDULED)
        self.assertEqual(observation["first_slot"]["result_sha256"], summary["result_sha256_or_null"])
        self.assertEqual(observation["launchd"]["run_count"], 1)
        self.assertEqual(observation["launchd"]["last_exit_code"], 0)
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(
            observation["security_boundary"],
            {
                "launchctl_read_count": 1,
                "network_request_count": 0,
                "runtime_invocation_count": 0,
                "scheduler_invocation_count": 0,
                "state_write_count": 0,
                "credential_count": 0,
                "broker_request_count": 0,
                "order_submission_count": 0,
            },
        )

    def test_second_success_before_start_receipt_is_permanent_window_miss(self):
        self.create_success()
        self.create_success("2026-08-04T12:00:00.000Z")
        runner = ObserverLaunchctl(self.install, runs=2)
        with self.assertRaisesRegex(
            SystemPaperObserverError, "FIRST_SLOT_OBSERVATION_WINDOW_MISSED"
        ):
            observe_system_paper_first_slot(
                **self.values(runner, "2026-08-04T12:10:00.000Z")
            )

    def test_path_or_bytes_change_during_print_fails_closed(self):
        self.create_success()
        original = self.stdout_path.read_bytes()

        def mutate_bytes():
            with self.stdout_path.open("ab") as handle:
                handle.write(b"changed\n")

        with self.assertRaisesRegex(SystemPaperObserverError, "EVIDENCE_CHANGED"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1, callback=mutate_bytes),
                    "2026-08-04T08:10:00.000Z",
                )
            )
        self.stdout_path.write_bytes(original)
        self.stdout_path.chmod(0o600)

        def replace_path():
            old = self.stdout_path.with_suffix(".old")
            self.stdout_path.rename(old)
            self.stdout_path.write_bytes(original)
            self.stdout_path.chmod(0o600)

        with self.assertRaisesRegex(SystemPaperObserverError, "EVIDENCE_CHANGED"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1, callback=replace_path),
                    "2026-08-04T08:10:00.000Z",
                )
            )

    def test_state_bytes_change_during_print_fails_closed(self):
        self.create_success()

        def mutate_state():
            with self.state_path.open("ab") as handle:
                handle.write(b"changed")

        runner = ObserverLaunchctl(
            self.install, runs=1, callback=mutate_state
        )
        with self.assertRaisesRegex(SystemPaperObserverError, "EVIDENCE_CHANGED"):
            observe_system_paper_first_slot(
                **self.values(runner, "2026-08-04T08:10:00.000Z")
            )
        self.assertEqual(len(runner.calls), 1)

    def test_failed_scheduler_attempt_is_failed_closed_after_one_print(self):
        class BrokenProvider:
            def __call__(self, _request):
                raise ValueError("capture failed")

        with self.assertRaises(ValueError):
            run_due_system_paper_slot(
                state_path=self.state_path,
                output_root=self.output_root,
                plan=build_system_paper_plan(),
                worker_id="observer-failed-worker",
                public_input_provider=BrokenProvider(),
                fill_scenario=FillScenario.immediate_full(),
                clock=lambda: "2026-08-04T08:05:11.000Z",
            )
        for path in self.state_path.parent.glob(self.state_path.name + "*"):
            path.chmod(0o600)
        runner = ObserverLaunchctl(self.install, runs=0)
        with self.assertRaisesRegex(SystemPaperObserverError, "FAILED_CLOSED"):
            observe_system_paper_first_slot(
                **self.values(runner, "2026-08-04T08:10:00.000Z")
            )
        self.assertEqual(len(runner.calls), 1)

    def test_prepared_result_tamper_fails_replay(self):
        self.create_success()
        connection = sqlite3.connect(str(self.state_path))
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='prepared_results_no_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER prepared_results_no_update")
        changed = b"{}"
        connection.execute(
            "UPDATE prepared_results SET result_bytes=?, result_sha256=?",
            (changed, hashlib.sha256(changed).hexdigest()),
        )
        connection.execute(trigger)
        connection.commit()
        connection.close()
        self.state_path.chmod(0o600)
        runner = ObserverLaunchctl(self.install, runs=1)
        with self.assertRaisesRegex(SystemPaperObserverError, "FAILED_CLOSED"):
            observe_system_paper_first_slot(
                **self.values(runner, "2026-08-04T08:10:00.000Z")
            )

    def test_event_chain_tamper_fails_replay(self):
        self.create_success()
        connection = sqlite3.connect(str(self.state_path))
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='schedule_events_no_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER schedule_events_no_update")
        connection.execute(
            "UPDATE schedule_events SET event_hash=? WHERE sequence=(SELECT MAX(sequence) FROM schedule_events)",
            ("0" * 64,),
        )
        connection.execute(trigger)
        connection.commit()
        connection.close()
        self.state_path.chmod(0o600)
        with self.assertRaisesRegex(SystemPaperObserverError, "FAILED_CLOSED"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1),
                    "2026-08-04T08:10:00.000Z",
                )
            )

    def test_missed_or_expired_scheduler_slot_fails_closed(self):
        plan = build_system_paper_plan()
        policy = SystemPaperSchedulePolicy.create(plan)
        first = policy.slot_from_scheduled(FIRST_SCHEDULED)
        later = policy.slot_from_scheduled("2026-08-04T16:00:00.000Z")
        with SystemPaperScheduleState(self.state_path, policy) as state:
            state.claim(
                first,
                worker_id="observer-expired-worker",
                claimed_at="2026-08-04T08:05:11.000Z",
            )
            state.record_gaps(later, recorded_at="2026-08-04T16:05:11.000Z")
        for path in self.state_path.parent.glob(self.state_path.name + "*"):
            path.chmod(0o600)
        runner = ObserverLaunchctl(self.install, runs=0)
        with self.assertRaisesRegex(SystemPaperObserverError, "FAILED_CLOSED"):
            observe_system_paper_first_slot(
                **self.values(runner, "2026-08-04T16:10:00.000Z")
            )
        self.assertEqual(len(runner.calls), 1)

    def test_nonzero_exit_stderr_extra_or_hardlinked_result_fail_closed(self):
        summary = self.create_success()
        result_path = Path(summary["result_path_or_null"])
        with self.assertRaisesRegex(SystemPaperObserverError, "EXIT"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1, exit_code=1),
                    "2026-08-04T08:10:00.000Z",
                )
            )

        self.stderr_path.write_bytes(b"unexpected\n")
        with self.assertRaisesRegex(SystemPaperObserverError, "STDERR"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1),
                    "2026-08-04T08:10:00.000Z",
                )
            )
        self.stderr_path.write_bytes(b"")

        extra = result_path.parent / "extra.json"
        extra.write_bytes(result_path.read_bytes())
        extra.chmod(0o600)
        with self.assertRaisesRegex(SystemPaperObserverError, "ARTIFACT_INVENTORY"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1),
                    "2026-08-04T08:10:00.000Z",
                )
            )
        extra.unlink()
        hardlink = result_path.parent / "hardlink.json"
        os.link(result_path, hardlink)
        with self.assertRaisesRegex(SystemPaperObserverError, "ARTIFACT"):
            observe_system_paper_first_slot(
                **self.values(
                    ObserverLaunchctl(self.install, runs=1),
                    "2026-08-04T08:10:00.000Z",
                )
            )

    def test_cli_is_read_only_and_accepts_only_four_source_paths(self):
        expected = {"status": "WAITING_FOR_FIRST_NATURAL_SLOT"}
        with patch(
            "crypto_quant.system_paper_observer_cli.observe_system_paper_first_slot",
            return_value=expected,
        ) as observe:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = observer_main(
                    [
                        "--contract-path", str(self.install.preflight.contract_path),
                        "--plist-path", str(self.install.preflight.plist_path),
                        "--preflight-receipt-path", str(self.preflight_path),
                        "--install-receipt-path", str(self.install_receipt_path),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue()), expected)
            self.assertEqual(stderr.getvalue(), "")
            observe.assert_called_once_with(
                contract_path=self.install.preflight.contract_path,
                plist_path=self.install.preflight.plist_path,
                preflight_receipt_path=self.preflight_path,
                install_receipt_path=self.install_receipt_path,
            )
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                observer_main(["--output-root", "/tmp/not-allowed"])


if __name__ == "__main__":
    unittest.main()
