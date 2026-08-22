import json
import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from crypto_quant import challenger_replacement_runtime as runtime_module
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_runtime import (
    ChallengerReplacementRuntimeState,
)
from tests import test_challenger_replacement_live_input as live_fixture_module
from tests.challenger_replacement_v2_fixtures import fixture_capture
from tests.test_challenger_replacement_events import EventWorkspace


class LiveRuntimeTests(unittest.TestCase):
    def setUp(self):
        acquisition = live_fixture_module.LiveAcquisitionTests()
        acquisition.setUp()
        self.plan = acquisition.plan
        self.build_identity = acquisition.build_identity
        self.live_capture = acquisition._acquire_with(
            live_fixture_module._TimeTransport().responses
            + [acquisition._kline_response()]
        )
        self.workspace = EventWorkspace()
        self.root = open_challenger_replacement_event_root(
            self.workspace.identity()
        )

    def tearDown(self):
        self.root.close()
        self.workspace.close()

    def _state(self):
        return ChallengerReplacementRuntimeState(
            event_root=self.root,
            plan=self.plan,
            build_identity=self.build_identity,
        )

    def _crash_after(self, event_type):
        state = self._state()
        real_append = state.append

        def append_then_crash(**kwargs):
            event = real_append(**kwargs)
            if kwargs["event_type"] == event_type:
                raise SystemExit("test-only crash")
            return event

        with patch.object(state, "append", side_effect=append_then_crash):
            with self.assertRaises(SystemExit):
                runtime_module.run_challenger_replacement_cohort_slot(
                    state=state,
                    live_capture=self.live_capture,
                    worker_id="replacement-live-crash-worker",
                )

    def _fresh_state(self):
        self.root.close()
        self.root = open_challenger_replacement_event_root(
            self.workspace.identity()
        )
        return self._state()

    def test_cohort_slot_uses_three_events_and_success_retry_is_replay_only(self):
        state = self._state()
        result = runtime_module.run_challenger_replacement_cohort_slot(
            state=state,
            live_capture=self.live_capture,
            worker_id="replacement-live-fixture-worker",
        )
        self.assertEqual(result["stage"], "SLOT_SUCCEEDED")
        projection = self._state().replay()
        self.assertEqual(
            [json.loads(event.final_bytes)["event_type"] for event in projection["events"]],
            ["INPUT_PREPARED", "RESULT_PREPARED", "SLOT_SUCCEEDED"],
        )
        slot = projection["slots"][self.live_capture.document["slot"]["slot_id"]]
        self.assertEqual(
            slot["source_bundle"]["evidence_qualification"],
            "REPLACEMENT_CONFIRMATORY_COHORT_EVIDENCE",
        )
        with patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_source_bundle",
            side_effect=AssertionError("source rebuild forbidden"),
            create=True,
        ), patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_decision",
            side_effect=AssertionError("decision rebuild forbidden"),
            create=True,
        ):
            replayed = runtime_module.run_challenger_replacement_cohort_slot(
                state=self._state(),
                live_capture=self.live_capture,
                worker_id="replacement-live-retry-worker",
            )
        self.assertEqual(replayed["stage"], "SLOT_SUCCEEDED")
        self.assertEqual(len(self._state().replay()["events"]), 3)

    def test_resume_after_input_uses_embedded_cohort_source_without_capture(self):
        self._crash_after("INPUT_PREPARED")
        state = self._fresh_state()
        with patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_source_bundle",
            side_effect=AssertionError("source rebuild forbidden"),
        ) as source_build, patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_decision",
            wraps=runtime_module.build_challenger_replacement_cohort_decision,
        ) as decision_build:
            result = runtime_module.resume_challenger_replacement_slot(
                state=state,
                worker_id="replacement-live-resume-worker",
            )
        self.assertEqual(result["stage"], "SLOT_SUCCEEDED")
        self.assertEqual((source_build.call_count, decision_build.call_count), (0, 1))

    def test_resume_after_result_rebuilds_nothing(self):
        self._crash_after("RESULT_PREPARED")
        state = self._fresh_state()
        with patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_source_bundle",
            side_effect=AssertionError("source rebuild forbidden"),
        ) as source_build, patch.object(
            runtime_module,
            "build_challenger_replacement_cohort_decision",
            side_effect=AssertionError("decision rebuild forbidden"),
        ) as decision_build:
            result = runtime_module.resume_challenger_replacement_slot(
                state=state,
                worker_id="replacement-live-resume-worker",
            )
        self.assertEqual(result["stage"], "SLOT_SUCCEEDED")
        self.assertEqual((source_build.call_count, decision_build.call_count), (0, 0))

    def test_live_invocation_replays_before_one_acquisition(self):
        from crypto_quant import challenger_replacement_live_runtime_cli as cli

        state = self._state()
        with patch.object(
            cli,
            "_load_fixed_runtime_contract",
            return_value={
                "state": state,
                "worker_id": "replacement-live-cli-worker",
            },
        ) as contract_load, patch.object(
            cli,
            "acquire_challenger_replacement_live_capture",
            return_value=self.live_capture,
        ) as acquire:
            summary = cli._run_live_invocation()
        self.assertEqual((contract_load.call_count, acquire.call_count), (1, 1))
        self.assertEqual(summary, {
            "event_count": 3,
            "next_required_slot": {
                "scheduled_for": "2026-08-22T08:00:00.000Z",
                "sequence": 2,
            },
            "reason_code": "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
            "scheduled_for": "2026-08-22T04:00:00.000Z",
            "slot_id": self.live_capture.document["slot"]["slot_id"],
            "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
            "terminal_stage": "SLOT_SUCCEEDED",
        })

    def test_cohort_entry_rejects_mapping_and_v1_fixture_without_events(self):
        for capture in ({}, fixture_capture()):
            with self.subTest(capture=capture), self.assertRaisesRegex(
                runtime_module.ChallengerReplacementRuntimeError,
                "CHALLENGER_REPLACEMENT_RUNTIME_INPUT_INVALID",
            ):
                runtime_module.run_challenger_replacement_cohort_slot(
                    state=self._state(),
                    live_capture=capture,
                    worker_id="replacement-live-fixture-worker",
                )
        self.assertEqual(len(self._state().replay()["events"]), 0)

    def test_live_invocation_resumes_durable_input_without_acquisition(self):
        from crypto_quant import challenger_replacement_live_runtime_cli as cli

        self._crash_after("INPUT_PREPARED")
        state = self._fresh_state()
        with patch.object(
            cli,
            "_load_fixed_runtime_contract",
            return_value={
                "state": state,
                "worker_id": "replacement-live-cli-worker",
            },
        ), patch.object(
            cli,
            "acquire_challenger_replacement_live_capture",
            side_effect=AssertionError("network forbidden"),
        ) as acquire:
            summary = cli._run_live_invocation()
        self.assertEqual(acquire.call_count, 0)
        self.assertEqual(summary["terminal_stage"], "SLOT_SUCCEEDED")
        self.assertEqual(len(state.replay()["events"]), 3)


class LiveRuntimeCliTests(unittest.TestCase):
    def test_every_argument_is_rejected_before_contract_or_network(self):
        from crypto_quant import challenger_replacement_live_runtime_cli as cli

        for argument in ("--slot", "x", "--contract", "--url", "--fixture"):
            with self.subTest(argument=argument), patch.object(
                cli,
                "_load_fixed_runtime_contract",
                side_effect=AssertionError("contract load forbidden"),
            ) as contract_load, patch.object(
                cli,
                "acquire_challenger_replacement_live_capture",
                side_effect=AssertionError("network forbidden"),
            ) as acquire, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main([argument]), 2)
            self.assertEqual((contract_load.call_count, acquire.call_count), (0, 0))

    def test_success_writes_one_canonical_summary_and_returns_zero(self):
        from crypto_quant import challenger_replacement_live_runtime_cli as cli

        summary = {
            "event_count": 3,
            "next_required_slot": {"scheduled_for": "2026-08-22T08:00:00.000Z", "sequence": 2},
            "reason_code": "CHALLENGER_REPLACEMENT_SLOT_SUCCEEDED_VERIFIED",
            "scheduled_for": "2026-08-22T04:00:00.000Z",
            "slot_id": "replacement-slot-fixture",
            "status": "CHALLENGER_REPLACEMENT_LIVE_RUNTIME_SUCCEEDED",
            "terminal_stage": "SLOT_SUCCEEDED",
        }
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, "_run_live_invocation", return_value=summary), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.main([])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), json.dumps(
            summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ) + "\n")

    def test_transient_and_permanent_failures_have_bounded_exit_mapping(self):
        from crypto_quant import challenger_replacement_live_runtime_cli as cli
        from crypto_quant.challenger_replacement_live_input import (
            ChallengerReplacementLiveInputError,
        )
        from crypto_quant.challenger_replacement_runtime import (
            ChallengerReplacementRuntimeError,
        )

        cases = (
            (ChallengerReplacementLiveInputError(
                "CHALLENGER_REPLACEMENT_LIVE_INPUT_RETRIES_EXHAUSTED"), 75),
            (ChallengerReplacementRuntimeError(
                "CHALLENGER_REPLACEMENT_RUNTIME_CONTRACT_INVALID"), 1),
        )
        for error, expected_exit in cases:
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(reason=error.reason_code), patch.object(
                cli, "_run_live_invocation", side_effect=error
            ), redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = cli.main([])
            self.assertEqual(exit_code, expected_exit)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), error.reason_code + "\n")


if __name__ == "__main__":
    unittest.main()
