import unittest
import multiprocessing
from datetime import datetime, timezone
from unittest.mock import patch

from crypto_quant import challenger_replacement_v3_runtime as runtime_module

from crypto_quant.challenger_replacement_economic_plan import (
    build_challenger_replacement_economic_plan,
)
from crypto_quant.challenger_replacement_events import (
    open_challenger_replacement_event_root,
)
from crypto_quant.challenger_replacement_opportunities import (
    ChallengerReplacementOpportunityState,
)
from crypto_quant.challenger_replacement_public_market_capture import (
    load_challenger_replacement_public_market_capture_bytes,
)
from crypto_quant.challenger_replacement_public_simulation_contract import (
    build_challenger_replacement_public_simulation_contract,
)
from crypto_quant.challenger_replacement_simulation_contract import (
    build_challenger_replacement_simulation_contract,
)
from crypto_quant.challenger_replacement_v3_runtime import (
    run_challenger_replacement_v3_opportunity,
)
from tests.challenger_replacement_v3_fixtures import fixture_v3_plan
from tests.test_challenger_replacement_events import EventWorkspace
from tests.test_challenger_replacement_public_market_capture import (
    COMMITTED_CAPTURE,
    V076_BUILD,
)


def _runtime_race_worker(identity_values, barrier, queue):
    from crypto_quant.challenger_replacement_events import (
        ChallengerReplacementEventRootIdentity,
    )

    plan = fixture_v3_plan()
    economic = build_challenger_replacement_economic_plan()
    predecessor = build_challenger_replacement_simulation_contract(plan=plan)
    public_contract = build_challenger_replacement_public_simulation_contract(
        plan=plan,
        economic_plan=economic,
        predecessor_contract=predecessor,
    )
    capture = load_challenger_replacement_public_market_capture_bytes(
        COMMITTED_CAPTURE.read_bytes(),
        plan=plan,
        build_identity=V076_BUILD,
        previous_source_bundle=None,
    )
    identity = ChallengerReplacementEventRootIdentity(**identity_values)
    try:
        with open_challenger_replacement_event_root(identity) as root, patch.object(
            runtime_module, "_acquire", return_value=capture
        ), patch.object(
            runtime_module, "_wall_now",
            return_value=datetime(2026, 8, 26, 4, 5, tzinfo=timezone.utc),
        ):
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=plan, build_identity=V076_BUILD
            )
            barrier.wait(timeout=10)
            result = run_challenger_replacement_v3_opportunity(
                state=state, event_root=root, plan=plan,
                economic_plan=economic, predecessor_contract=predecessor,
                public_contract=public_contract, build_identity=V076_BUILD,
            )
            queue.put(("result", result["status"]))
    except BaseException as error:
        queue.put(("error", type(error).__name__, str(error)))


class ChallengerReplacementV3RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.workspace = EventWorkspace()
        self.addCleanup(self.workspace.close)
        self.plan = fixture_v3_plan()
        self.economic_plan = build_challenger_replacement_economic_plan()
        self.predecessor = build_challenger_replacement_simulation_contract(
            plan=self.plan
        )
        self.public_contract = (
            build_challenger_replacement_public_simulation_contract(
                plan=self.plan,
                economic_plan=self.economic_plan,
                predecessor_contract=self.predecessor,
            )
        )
        self.capture = load_challenger_replacement_public_market_capture_bytes(
            COMMITTED_CAPTURE.read_bytes(),
            plan=self.plan,
            build_identity=V076_BUILD,
            previous_source_bundle=None,
        )

    def test_natural_capture_commits_one_public_result_and_replays_terminal(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root,
                plan=self.plan,
                build_identity=V076_BUILD,
            )
            with patch(
                "crypto_quant.challenger_replacement_v3_runtime._acquire",
                return_value=self.capture,
            ), patch.object(
                runtime_module, "_wall_now",
                return_value=datetime(2026, 8, 26, 4, 5, tzinfo=timezone.utc),
            ):
                first = run_challenger_replacement_v3_opportunity(
                    state=state,
                    event_root=root,
                    plan=self.plan,
                    economic_plan=self.economic_plan,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public_contract,
                    build_identity=V076_BUILD,
                )
            with patch.object(
                runtime_module, "_acquire",
                side_effect=AssertionError("terminal replay must not acquire"),
            ), patch.object(
                runtime_module, "_wall_now",
                return_value=datetime(2026, 8, 26, 4, 5, tzinfo=timezone.utc),
            ):
                replayed = run_challenger_replacement_v3_opportunity(
                    state=state,
                    event_root=root,
                    plan=self.plan,
                    economic_plan=self.economic_plan,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public_contract,
                    build_identity=V076_BUILD,
                )

            projection = state.replay()
            slot = projection["opportunities"][
                "ETHUSDT@2026-08-26T04:00:00.000Z"
            ]
            self.assertEqual(first["status"], "OBSERVED")
            self.assertEqual(replayed["status"], "ALREADY_TERMINAL")
            self.assertEqual(first["result"], replayed["result"])
            self.assertEqual(slot["stage"], "OPPORTUNITY_OBSERVED")
            self.assertEqual(projection["terminal_opportunity_count"], 1)
            self.assertEqual(projection["observed_opportunity_count"], 1)
            self.assertEqual(len(projection["events"]), 3)
            self.assertEqual(
                slot["source_bundle_bytes"],
                self.capture.canonical_bytes,
            )
            self.assertEqual(
                first["result"]["evidence_qualification"],
                "PUBLIC_MARKET_DETERMINISTIC_SIMULATION_NO_ACCOUNT_NO_BROKER_NO_REAL_ORDER",
            )
            self.assertEqual(
                first["result"]["authority"]["orders_submitted_to_venue"], 0
            )

    def test_fresh_state_resumes_after_durable_input_without_reacquiring(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            original_append = runtime_module._append
            calls = 0

            def append_then_crash(*args, **kwargs):
                nonlocal calls
                publication = original_append(*args, **kwargs)
                calls += 1
                if calls == 1:
                    raise RuntimeError("test crash after durable input")
                return publication

            with patch.object(runtime_module, "_acquire", return_value=self.capture), patch.object(
                runtime_module, "_append", side_effect=append_then_crash
            ):
                with self.assertRaisesRegex(RuntimeError, "after durable input"):
                    run_challenger_replacement_v3_opportunity(
                        state=state, event_root=root, plan=self.plan,
                        economic_plan=self.economic_plan,
                        predecessor_contract=self.predecessor,
                        public_contract=self.public_contract,
                        build_identity=V076_BUILD,
                    )

            fresh = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            with patch.object(
                runtime_module, "_acquire",
                side_effect=AssertionError("resume must not reacquire"),
            ):
                recovered = run_challenger_replacement_v3_opportunity(
                    state=fresh, event_root=root, plan=self.plan,
                    economic_plan=self.economic_plan,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public_contract,
                    build_identity=V076_BUILD,
                )

            self.assertEqual(recovered["status"], "OBSERVED")
            self.assertEqual(len(fresh.replay()["events"]), 3)

    def test_later_scheduler_call_records_expired_gap_before_current_capture(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            with patch.object(runtime_module, "_acquire", return_value=self.capture):
                run_challenger_replacement_v3_opportunity(
                    state=state, event_root=root, plan=self.plan,
                    economic_plan=self.economic_plan,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public_contract,
                    build_identity=V076_BUILD,
                )
            with patch.object(
                runtime_module, "_wall_now",
                return_value=datetime(2026, 8, 26, 12, 5, tzinfo=timezone.utc),
            ), patch.object(
                runtime_module, "_acquire",
                side_effect=AssertionError("current capture reached"),
            ):
                with self.assertRaisesRegex(AssertionError, "current capture reached"):
                    run_challenger_replacement_v3_opportunity(
                        state=state, event_root=root, plan=self.plan,
                        economic_plan=self.economic_plan,
                        predecessor_contract=self.predecessor,
                        public_contract=self.public_contract,
                        build_identity=V076_BUILD,
                    )

            projection = state.replay()
            missed = projection["opportunities"][
                "ETHUSDT@2026-08-26T08:00:00.000Z"
            ]
            self.assertEqual(missed["outcome"], "MISSED")
            self.assertEqual(missed["reason_code"], "CAPTURE_WINDOW_EXPIRED")
            self.assertTrue(
                projection["latest_next_snapshot_or_null"]["economic_gap_locked"]
            )
            self.assertEqual(
                projection["next_required_opportunity"]["scheduled_for"],
                "2026-08-26T12:00:00.000Z",
            )

    def test_fresh_state_promotes_durable_result_without_reacquiring(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            original_append = runtime_module._append
            calls = 0

            def append_result_then_crash(*args, **kwargs):
                nonlocal calls
                publication = original_append(*args, **kwargs)
                calls += 1
                if calls == 2:
                    raise RuntimeError("test crash after durable result")
                return publication

            with patch.object(runtime_module, "_acquire", return_value=self.capture), patch.object(
                runtime_module, "_append", side_effect=append_result_then_crash
            ):
                with self.assertRaisesRegex(RuntimeError, "after durable result"):
                    run_challenger_replacement_v3_opportunity(
                        state=state, event_root=root, plan=self.plan,
                        economic_plan=self.economic_plan,
                        predecessor_contract=self.predecessor,
                        public_contract=self.public_contract,
                        build_identity=V076_BUILD,
                    )

            fresh = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            with patch.object(
                runtime_module, "_acquire",
                side_effect=AssertionError("result recovery must not reacquire"),
            ):
                recovered = run_challenger_replacement_v3_opportunity(
                    state=fresh, event_root=root, plan=self.plan,
                    economic_plan=self.economic_plan,
                    predecessor_contract=self.predecessor,
                    public_contract=self.public_contract,
                    build_identity=V076_BUILD,
                )

            self.assertEqual(recovered["status"], "OBSERVED")
            self.assertEqual(len(fresh.replay()["events"]), 3)

    def test_two_processes_publish_one_economic_chain(self):
        context = multiprocessing.get_context("spawn")
        barrier = context.Barrier(2)
        queue = context.Queue()
        identity_values = dict(self.workspace.identity().__dict__)
        processes = [
            context.Process(
                target=_runtime_race_worker,
                args=(identity_values, barrier, queue),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        outcomes = [queue.get(timeout=20) for _ in processes]
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(process.exitcode, 0)

        self.assertEqual(
            sorted(outcomes),
            [("result", "ALREADY_TERMINAL"), ("result", "OBSERVED")],
        )
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            projection = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            ).replay()
        self.assertEqual(len(projection["events"]), 3)
        self.assertEqual(projection["observed_opportunity_count"], 1)

    def test_unlock_failure_does_not_hide_primary_runtime_failure(self):
        with open_challenger_replacement_event_root(
            self.workspace.identity()
        ) as root:
            state = ChallengerReplacementOpportunityState(
                event_root=root, plan=self.plan, build_identity=V076_BUILD
            )
            lock_calls = 0

            def lock_then_unlock_failure(_descriptor, _operation):
                nonlocal lock_calls
                lock_calls += 1
                if lock_calls == 2:
                    raise OSError("unlock failed")

            primary = RuntimeError("primary runtime failure")
            with patch.object(
                runtime_module.fcntl, "flock",
                side_effect=lock_then_unlock_failure,
            ), patch.object(runtime_module, "_run_locked", side_effect=primary):
                with self.assertRaises(RuntimeError) as raised:
                    run_challenger_replacement_v3_opportunity(
                        state=state, event_root=root, plan=self.plan,
                        economic_plan=self.economic_plan,
                        predecessor_contract=self.predecessor,
                        public_contract=self.public_contract,
                        build_identity=V076_BUILD,
                    )

            self.assertIs(raised.exception, primary)
            self.assertEqual(
                getattr(raised.exception, "unlock_failure_reason_code", None),
                "CHALLENGER_REPLACEMENT_OPPORTUNITY_EVENT_ROOT_CHANGED",
            )


if __name__ == "__main__":
    unittest.main()
