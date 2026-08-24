import inspect
import hashlib
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from crypto_quant import challenger_replacement_binance_lifecycle as lifecycle_module
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_fixture_simulation import (
    run_challenger_replacement_fixture_simulation_opportunity,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityError,
    ChallengerReplacementOpportunityState,
    catch_up_missed_opportunities,
)
from crypto_quant.challenger_replacement_opportunity_evidence import (
    build_challenger_replacement_fixture_result_evidence,
)
from tests.challenger_replacement_v3_fixtures import (
    fixture_v071_signal_bars,
    fixture_v070_build_identity,
    fixture_v072_build_identity,
    fixture_v072_input_bytes,
    fixture_v3_plan,
)
from tests.test_challenger_replacement_events import EventWorkspace


def _event_types(projection):
    return tuple(json.loads(event.final_bytes)["event_type"] for event in projection["events"])


class ChallengerReplacementFixtureSimulationTests(unittest.TestCase):
    def setUp(self):
        self.files = EventWorkspace()
        self.root = open_challenger_replacement_event_root(self.files.identity())
        self.state = ChallengerReplacementOpportunityState(
            event_root=self.root,
            plan=fixture_v3_plan(),
            build_identity=fixture_v072_build_identity(),
        )

    def tearDown(self):
        self.root.close()
        self.files.close()

    def _run(self, data=None):
        return run_challenger_replacement_fixture_simulation_opportunity(
            state=self.state,
            input_bytes=(
                fixture_v072_input_bytes(bars=fixture_v071_signal_bars("LONG"))
                if data is None else data
            ),
            worker_id="fixture-worker",
        )

    def test_public_runner_has_only_retained_state_input_and_worker(self):
        self.assertEqual(
            tuple(inspect.signature(
                run_challenger_replacement_fixture_simulation_opportunity
            ).parameters),
            ("state", "input_bytes", "worker_id"),
        )

    def test_invalid_input_fails_before_any_event(self):
        for data in (b"", b"{}", b"not-json"):
            with self.subTest(data=data):
                with self.assertRaises(Exception):
                    self._run(data)
                self.assertEqual(self.state.replay()["events"], ())

    def test_valid_input_commits_input_result_observed_and_returns_v2_result(self):
        result = self._run()
        projection = self.state.replay()
        self.assertEqual(
            _event_types(projection),
            ("INPUT_PREPARED", "RESULT_PREPARED", "OPPORTUNITY_OBSERVED"),
        )
        self.assertEqual(result["schema_version"], "2.0.0")
        self.assertEqual(result["lifecycle"]["status"], "RECONCILED_FIXTURE")
        self.assertEqual(set(result["authority"].values()), {0, False})
        self.assertEqual(
            projection["latest_next_snapshot_or_null"], result["next_snapshot"]
        )
        slot = projection["opportunities"][result["opportunity"]["opportunity_id"]]
        self.assertEqual((slot["stage"], slot["outcome"]), (
            "OPPORTUNITY_OBSERVED", "OBSERVED"
        ))

    def test_terminal_exact_retry_replays_without_append_build_or_compute(self):
        first = self._run()
        with patch.object(self.state, "append", side_effect=AssertionError("append")), patch(
            "crypto_quant.challenger_replacement_fixture_simulation."
            "simulate_challenger_replacement_binance_lifecycle",
            side_effect=AssertionError("compute"),
        ), patch(
            "crypto_quant.challenger_replacement_fixture_simulation."
            "build_challenger_replacement_simulation_result_evidence",
            side_effect=AssertionError("build"),
        ):
            second = self._run()
        self.assertEqual(second, first)
        self.assertEqual(len(self.state.replay()["events"]), 3)

    def test_second_opportunity_uses_previous_observed_v2_snapshot(self):
        first = self._run()
        scheduled = "2026-08-24T04:00:00.000Z"
        second = self._run(fixture_v072_input_bytes(
            scheduled_for=scheduled,
            observed_at="2026-08-24T04:05:00.000Z",
            bars=fixture_v071_signal_bars("LONG", scheduled),
        ))
        self.assertEqual(
            second["previous_snapshot"]["snapshot_hash"],
            first["next_snapshot"]["snapshot_hash"],
        )
        self.assertEqual(
            second["next_snapshot"]["parent_snapshot_hash_or_null"],
            first["next_snapshot"]["snapshot_hash"],
        )
        self.assertEqual(len(self.state.replay()["events"]), 6)

    def test_result_boundary_cannot_be_reclassified_missed_and_resumes_observed(self):
        original_append = self.state.append

        def crash_before_observed(**kwargs):
            if kwargs["event_type"] == "OPPORTUNITY_OBSERVED":
                raise RuntimeError("test crash after durable result")
            return original_append(**kwargs)

        with patch.object(self.state, "append", side_effect=crash_before_observed):
            with self.assertRaisesRegex(RuntimeError, "durable result"):
                self._run()
        self.assertEqual(
            _event_types(self.state.replay()),
            ("INPUT_PREPARED", "RESULT_PREPARED"),
        )
        with self.assertRaises(ChallengerReplacementOpportunityError) as caught:
            catch_up_missed_opportunities(
                state=self.state,
                start_scheduled_for="2026-08-24T00:00:00.000Z",
                detected_at="2026-08-24T00:11:00.000Z",
                worker_id="fixture-worker",
                reason_code="PROCESS_NOT_RUNNING",
            )
        self.assertEqual(
            caught.exception.reason_code,
            "CHALLENGER_REPLACEMENT_OPPORTUNITY_ACTIVE_CONFLICT",
        )
        with patch(
            "crypto_quant.challenger_replacement_fixture_simulation."
            "simulate_challenger_replacement_binance_lifecycle",
            side_effect=AssertionError("must replay result"),
        ):
            result = self._run()
        self.assertEqual(result["lifecycle"]["status"], "RECONCILED_FIXTURE")
        self.assertEqual(len(self.state.replay()["events"]), 3)

    def test_nonflat_miss_preserves_position_and_sets_economic_gap_lock(self):
        first = self._run()
        catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T04:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        locked = self.state.replay()["latest_next_snapshot_or_null"]
        self.assertEqual(locked["position_state"], "SPOT_LONG")
        self.assertTrue(locked["economic_gap_locked"])
        self.assertNotEqual(locked["snapshot_hash"], first["next_snapshot"]["snapshot_hash"])

    def test_flat_miss_preserves_v072_genesis_without_gap_lock(self):
        catch_up_missed_opportunities(
            state=self.state,
            start_scheduled_for="2026-08-24T00:00:00.000Z",
            detected_at="2026-08-24T00:11:00.000Z",
            worker_id="fixture-worker",
            reason_code="PROCESS_NOT_RUNNING",
        )
        snapshot = self.state.replay()["latest_next_snapshot_or_null"]
        self.assertEqual(snapshot["position_state"], "FLAT")
        self.assertFalse(snapshot["economic_gap_locked"])

    def test_failed_lifecycle_is_observed_but_not_operationally_complete(self):
        original = lifecycle_module._normal_lifecycle_observations

        def missing_stop(*args):
            return (replace(original(*args)[0], stop_confirmed=False),)

        with patch.object(
            lifecycle_module,
            "_normal_lifecycle_observations",
            side_effect=missing_stop,
        ):
            result = self._run()
        self.assertEqual(result["lifecycle"]["status"], "FAILED_CLOSED")
        self.assertFalse(result["lifecycle"]["operationally_complete"])
        slot = self.state.replay()["opportunities"][
            result["opportunity"]["opportunity_id"]
        ]
        self.assertEqual((slot["stage"], slot["outcome"]), (
            "OPPORTUNITY_OBSERVED", "OBSERVED"
        ))

    def test_runner_rejects_v070_root_before_any_event(self):
        state = ChallengerReplacementOpportunityState(
            event_root=self.root,
            plan=fixture_v3_plan(),
            build_identity=fixture_v070_build_identity(),
        )
        with self.assertRaises(ChallengerReplacementOpportunityError):
            run_challenger_replacement_fixture_simulation_opportunity(
                state=state,
                input_bytes=fixture_v072_input_bytes(),
                worker_id="fixture-worker",
            )
        self.assertEqual(state.replay()["events"], ())

    def test_v1_result_cannot_be_appended_to_v072_root(self):
        def v1_result(*, lifecycle_result):
            source = json.loads(lifecycle_result.source_bytes)
            decision_hash = hashlib.sha256(lifecycle_result.decision_bytes).hexdigest()
            return build_challenger_replacement_fixture_result_evidence(
                opportunity_id=source["opportunity"]["opportunity_id"],
                scheduled_for=source["opportunity"]["scheduled_for"],
                observed_at=source["opportunity"]["observed_at"],
                source_bundle_sha256=hashlib.sha256(
                    lifecycle_result.source_bytes
                ).hexdigest(),
                decision_sha256=decision_hash,
            )

        with patch(
            "crypto_quant.challenger_replacement_fixture_simulation."
            "build_challenger_replacement_simulation_result_evidence",
            side_effect=v1_result,
        ):
            with self.assertRaises(ChallengerReplacementOpportunityError):
                self._run()
        projection = self.state.replay()
        self.assertEqual(_event_types(projection), ("INPUT_PREPARED",))


if __name__ == "__main__":
    unittest.main()
