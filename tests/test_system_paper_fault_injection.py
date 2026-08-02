"""Full real-SQLite fault and recovery matrix for System Paper scheduling."""

import os
import tempfile
import unittest
from pathlib import Path

from crypto_quant.system_paper_broker import FillScenario
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.errors import ContractError
from crypto_quant.system_paper_scheduler import (
    SystemPaperFaultInjector,
    SystemPaperInjectedFault,
    SystemPaperInputCapture,
    SystemPaperScheduleError,
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
    run_due_system_paper_slot,
)
from crypto_quant.system_paper_runtime import (
    SystemPaperRuntimeError,
    load_system_paper_slot_result_bytes,
)
from crypto_quant.evidence import artifact_self_hash
from tests.test_system_paper_runtime import make_bundle


# This is deliberately a literal, independently reviewed 13-point contract.
FROZEN_FAILPOINTS = (
    ("BEFORE_CLAIM_COMMIT", "NONE", 0),
    ("AFTER_CLAIM_COMMIT", "NONE", 0),
    ("BEFORE_INPUT_PROVIDER", "NONE", 0),
    ("AFTER_INPUT_PROVIDER_BEFORE_COMMIT", "NONE", 0),
    ("BEFORE_INPUT_PREPARED_COMMIT", "NONE", 0),
    ("AFTER_INPUT_PREPARED_COMMIT", "INPUT", 0),
    ("AFTER_RUNTIME_BEFORE_RESULT_COMMIT", "INPUT", 0),
    ("BEFORE_RESULT_PREPARED_COMMIT", "INPUT", 0),
    ("AFTER_RESULT_PREPARED_COMMIT", "RESULT", 0),
    ("DURING_ARTIFACT_WRITE", "RESULT", 0),
    ("AFTER_ARTIFACT_FSYNC_BEFORE_COMMIT", "RESULT", 0),
    ("AFTER_ARTIFACT_PUBLISH_BEFORE_SUCCESS", "RESULT", 1),
    ("BEFORE_SUCCESS_COMMIT", "RESULT", 1),
)


class DeterministicPublicProvider:
    """The provider is real deterministic test input, not a business mock."""

    def __init__(self, captured_at):
        self.invocations = 0
        self.captured_at = captured_at

    def __call__(self, request):
        self.invocations += 1
        return SystemPaperInputCapture(
            public_market_bundle=make_bundle(observed_at=request.scheduled_for),
            capture_attempt_id="fault-capture-" + request.slot_id[-12:],
            captured_at=self.captured_at,
            request_families=request.request_families,
            network_request_count=4,
        )


class FaultScenarioHarness:
    def __init__(self, *, point, mode):
        self.point = point
        self.mode = mode
        self.temp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp.name) / "state.sqlite"
        self.output_root = Path(self.temp.name) / "output"
        self.output_root.mkdir(mode=0o700)
        os.chmod(self.output_root, 0o700)
        self.plan = build_system_paper_plan()
        self.now = "2026-08-02T12:05:11.000Z"
        self.provider = DeterministicPublicProvider(self.now)

    def close(self):
        self.temp.cleanup()

    def run_first_invocation(self):
        return self.run(
            worker_id="fault-worker-a",
            clock_at=self.now,
            provider=self.provider,
            injector=SystemPaperFaultInjector({self.point: self.mode}),
        )

    def run(self, *, worker_id, clock_at, provider, injector=None, scenario=None):
        return run_due_system_paper_slot(
            state_path=self.state_path,
            output_root=self.output_root,
            plan=self.plan,
            worker_id=worker_id,
            public_input_provider=provider,
            fill_scenario=scenario or FillScenario.immediate_full(),
            clock=lambda: clock_at,
            fault_injector=injector,
        )

    def durable_facts(self):
        policy = SystemPaperSchedulePolicy.create(self.plan)
        slot = policy.current_slot(self.now)
        with SystemPaperScheduleState(self.state_path, policy) as state:
            projection = state.slot_projection().get(slot.slot_id)
            stage = "NONE" if projection is None else projection["durable_stage"]
            prepared_inputs = state.connection.execute(
                "SELECT COUNT(*) FROM prepared_inputs"
            ).fetchone()[0]
            prepared_results = state.connection.execute(
                "SELECT COUNT(*) FROM prepared_results"
            ).fetchone()[0]
            terminal = None if projection is None else projection["terminal_state"]
        directory = self.output_root / "system-paper-slots"
        artifacts = 0 if not directory.exists() else len(tuple(directory.iterdir()))
        return stage, artifacts, prepared_inputs, prepared_results, terminal

    def assert_durable_stage_matches_contract(self, expected_stage, expected_artifacts):
        stage, artifacts, inputs, results, terminal = self.durable_facts()
        if (stage, artifacts) != (expected_stage, expected_artifacts):
            raise AssertionError(
                "durable stage/artifact mismatch: "
                f"got {(stage, artifacts)!r}, want {(expected_stage, expected_artifacts)!r}"
            )
        if inputs != (1 if expected_stage in ("INPUT", "RESULT") else 0):
            raise AssertionError(f"prepared input count: got {inputs!r}")
        if results != (1 if expected_stage == "RESULT" else 0):
            raise AssertionError(f"prepared result count: got {results!r}")
        if terminal is not None:
            raise AssertionError(f"fault must not append a terminal event: {terminal!r}")

    def assert_finished(self, summary, *, expected_outcome):
        if summary["outcome"] != expected_outcome:
            raise AssertionError(f"outcome: got {summary['outcome']!r}")
        if summary["loader_replay_count"] != 1:
            raise AssertionError("completed slot must perform exactly one loader replay")
        expected_safety = {
            "credential_reads": 0,
            "account_requests": 0,
            "real_broker_calls": 0,
            "real_order_writes": 0,
        }
        if summary["safety_counts"] != expected_safety:
            raise AssertionError(f"safety counts: {summary['safety_counts']!r}")
        path = Path(summary["result_path_or_null"])
        body = path.read_bytes()
        if load_system_paper_slot_result_bytes(body)["slot_id"] != summary["slot_id"]:
            raise AssertionError("full bytes-loader replay differs from runner summary")
        if self.durable_facts() != ("RESULT", 1, 1, 1, "SUCCEEDED"):
            raise AssertionError(f"final durable facts: {self.durable_facts()!r}")


class SystemPaperFaultWiringTests(unittest.TestCase):
    def test_every_frozen_failpoint_is_reached_at_its_exact_stage(self):
        for point, durable_stage, artifact_count in FROZEN_FAILPOINTS:
            with self.subTest(point=point):
                harness = FaultScenarioHarness(point=point, mode="CRASH")
                try:
                    with self.assertRaises(SystemPaperInjectedFault):
                        harness.run_first_invocation()
                    harness.assert_durable_stage_matches_contract(
                        durable_stage, artifact_count
                    )
                finally:
                    harness.close()


class SystemPaperFaultRecoveryTests(unittest.TestCase):
    def test_crash_matrix_recovers_once_from_every_durable_stage(self):
        for point, durable_stage, artifact_count in FROZEN_FAILPOINTS:
            with self.subTest(point=point):
                harness = FaultScenarioHarness(point=point, mode="CRASH")
                try:
                    with self.assertRaises(SystemPaperInjectedFault):
                        harness.run_first_invocation()
                    harness.assert_durable_stage_matches_contract(
                        durable_stage, artifact_count
                    )
                    published_before = None
                    if artifact_count:
                        artifact = next((harness.output_root / "system-paper-slots").iterdir())
                        published_before = (artifact.read_bytes(), artifact.stat().st_ino)
                    recovered = harness.run(
                        worker_id="fault-worker-b",
                        clock_at="2026-08-02T12:20:12.000Z",
                        provider=DeterministicPublicProvider("2026-08-02T12:20:12.000Z"),
                    )
                    expected_outcome = (
                        "RESUMED_INPUT" if durable_stage == "INPUT" else
                        "RESUMED_RESULT" if durable_stage == "RESULT" else "EXECUTED"
                    )
                    harness.assert_finished(recovered, expected_outcome=expected_outcome)
                    expected_counts = (
                        (0, 0, 1) if durable_stage == "INPUT" else
                        (0, 0, 0) if durable_stage == "RESULT" else (1, 4, 1)
                    )
                    self.assertEqual(
                        tuple(recovered[key] for key in (
                            "provider_invocation_count", "network_request_count",
                            "candidate_runtime_invocation_count",
                        )), expected_counts,
                    )
                    if published_before is not None:
                        artifact = next((harness.output_root / "system-paper-slots").iterdir())
                        self.assertEqual((artifact.read_bytes(), artifact.stat().st_ino), published_before)
                finally:
                    harness.close()

    def test_enospc_commit_matrix_rolls_back_without_false_terminal_event(self):
        cases = (
            ("BEFORE_CLAIM_COMMIT", "NONE", 0, 0),
            ("BEFORE_INPUT_PREPARED_COMMIT", "NONE", 0, 0),
            ("BEFORE_RESULT_PREPARED_COMMIT", "INPUT", 1, 0),
            ("BEFORE_SUCCESS_COMMIT", "RESULT", 1, 1),
        )
        for point, durable_stage, input_count, result_count in cases:
            with self.subTest(point=point):
                harness = FaultScenarioHarness(point=point, mode="ENOSPC")
                try:
                    with self.assertRaises(OSError) as raised:
                        harness.run_first_invocation()
                    self.assertEqual(raised.exception.errno, 28)
                    stage, artifacts, inputs, results, terminal = harness.durable_facts()
                    self.assertEqual((stage, inputs, results), (
                        durable_stage, input_count, result_count
                    ))
                    self.assertEqual(artifacts, 1 if point == "BEFORE_SUCCESS_COMMIT" else 0)
                    self.assertIsNone(terminal)
                    policy = SystemPaperSchedulePolicy.create(harness.plan)
                    with SystemPaperScheduleState(harness.state_path, policy) as state:
                        self.assertNotIn(
                            "FAILED", [event["event_type"] for event in state.events()]
                        )
                        self.assertNotIn(
                            "SUCCEEDED", [event["event_type"] for event in state.events()]
                        )
                finally:
                    harness.close()


class ProviderFaultMatrixTests(unittest.TestCase):
    def _harness(self):
        return FaultScenarioHarness(point="BEFORE_CLAIM_COMMIT", mode="CRASH")

    @staticmethod
    def _capture(now, request, **changes):
        values = {
            "public_market_bundle": make_bundle(observed_at=request.scheduled_for),
            "capture_attempt_id": "provider-fault-" + request.slot_id[-12:],
            "captured_at": now,
            "request_families": request.request_families,
            "network_request_count": 4,
        }
        values.update(changes)
        return SystemPaperInputCapture(**values)

    def test_provider_faults_fail_closed_before_input_is_prepared(self):
        # Each literal fixture catches a distinct capture-boundary validation break.
        now = "2026-08-02T12:05:11.000Z"

        def malformed(_request):
            return {"not": "a capture"}

        def duplicate(request):
            return self._capture(now, request, request_families=(
                "SPOT_AGG_TRADE", "SPOT_AGG_TRADE", "SPOT_EXCHANGE_INFO",
                "SPOT_KLINE_4H_WARMUP",
            ))

        def reordered(request):
            return self._capture(now, request, request_families=tuple(reversed(request.request_families)))

        def wrong_count(request):
            return self._capture(now, request, network_request_count=3)

        def stale(request):
            return self._capture(now, request, captured_at="2026-08-02T12:20:11.000Z")

        def changed_hash(request):
            bundle = make_bundle(observed_at=request.scheduled_for)
            bundle["bbo"] = {"bid_price": "98.99", "ask_price": "100.01"}
            return self._capture(now, request, public_market_bundle=bundle)

        def binary_float(request):
            bundle = make_bundle(observed_at=request.scheduled_for)
            bundle["bbo"] = {"bid_price": 99.99, "ask_price": "100.01"}
            bundle["bundle_hash"] = artifact_self_hash(bundle, "bundle_hash")
            return self._capture(now, request, public_market_bundle=bundle)

        def private_account(request):
            return self._capture(now, request, request_families=(
                "SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_EXCHANGE_INFO", "SPOT_ACCOUNT",
            ))

        cases = (
            ("malformed", malformed), ("duplicate", duplicate), ("reordered", reordered),
            ("count", wrong_count), ("stale", stale), ("changed_hash", changed_hash),
            ("float", binary_float), ("private_account", private_account),
        )
        for name, provider in cases:
            with self.subTest(case=name):
                harness = self._harness()
                try:
                    with self.assertRaises((SystemPaperScheduleError, ValueError, TypeError)):
                        harness.run(
                            worker_id="provider-worker", clock_at=now, provider=provider
                        )
                    stage, artifacts, inputs, results, terminal = harness.durable_facts()
                    self.assertEqual((stage, artifacts, inputs, results, terminal), (
                        "NONE", 0, 0, 0, None
                    ))
                    policy = SystemPaperSchedulePolicy.create(harness.plan)
                    with SystemPaperScheduleState(harness.state_path, policy) as state:
                        projection = state.slot_projection()[policy.current_slot(now).slot_id]
                    self.assertEqual(projection["attempt_status"], "FAILED")
                finally:
                    harness.close()


class OrderFaultMatrixTests(unittest.TestCase):
    @staticmethod
    def _abstract_outcome(summary, result):
        """The public runner keeps frozen outcome names; matrix uses brief labels."""
        if result["runtime_snapshot"]["risk_state"] == "LOCKED":
            return "LOCKED"
        if summary["outcome"] in ("EXECUTED", "RESUMED_INPUT", "RESUMED_RESULT"):
            return "RECOVERED"
        return "FAILED_CLOSED"

    def test_v056_fill_scenarios_produce_one_economic_result_or_fail_closed(self):
        # These factories exercise the real deterministic broker and runtime, never a broker double.
        cases = (
            ("reject", FillScenario.rejected(), "RECOVERED"),
            ("cancel_before_fill", FillScenario.cancel_before_fill(), "RECOVERED"),
            ("fill_before_cancel", FillScenario.fill_before_cancel("0.30"), "RECOVERED"),
            ("partial_then_full", FillScenario.partial_then_full("0.40"), "RECOVERED"),
            ("timeout", FillScenario.timeout_after_ack(), "LOCKED"),
            ("disconnect_then_full", FillScenario.disconnect_then_full(), "RECOVERED"),
            ("permanent_unknown", FillScenario.disconnect_after_submit(), "LOCKED"),
            ("duplicate_fill", FillScenario.fill_before_ack_with_duplicate("0.40"), "RECOVERED"),
        )
        for name, scenario, expected in cases:
            with self.subTest(scenario=name):
                harness = FaultScenarioHarness(point="BEFORE_CLAIM_COMMIT", mode="CRASH")
                try:
                    summary = harness.run(
                        worker_id="order-worker", clock_at=harness.now,
                        provider=harness.provider, scenario=scenario,
                    )
                    path = Path(summary["result_path_or_null"])
                    result = load_system_paper_slot_result_bytes(path.read_bytes())
                    self.assertEqual(self._abstract_outcome(summary, result), expected)
                    self.assertIn(self._abstract_outcome(summary, result), {
                        "RECOVERED", "LOCKED", "FAILED_CLOSED"
                    })
                    self.assertEqual(result["ledger"]["debits_usdt"], result["ledger"]["credits_usdt"])
                    self.assertEqual(summary["safety_counts"], {
                        "credential_reads": 0, "account_requests": 0,
                        "real_broker_calls": 0, "real_order_writes": 0,
                    })
                    self.assertEqual(harness.durable_facts(), ("RESULT", 1, 1, 1, "SUCCEEDED"))
                    if name == "permanent_unknown":
                        self.assertEqual(result["order"]["state"], "UNKNOWN")
                        self.assertEqual(result["runtime_snapshot"]["risk_state"], "LOCKED")
                        self._assert_locked_slot_blocks_next_risk_increase(harness)
                finally:
                    harness.close()

    def _assert_locked_slot_blocks_next_risk_increase(self, harness):
        next_now = "2026-08-02T16:05:11.000Z"
        with self.assertRaises(SystemPaperRuntimeError):
            harness.run(
                worker_id="next-slot-worker",
                clock_at=next_now,
                provider=DeterministicPublicProvider(next_now),
                scenario=FillScenario.immediate_full(),
            )
        policy = SystemPaperSchedulePolicy.create(harness.plan)
        next_slot = policy.current_slot(next_now)
        with SystemPaperScheduleState(harness.state_path, policy) as state:
            projection = state.slot_projection()[next_slot.slot_id]
            self.assertEqual(
                state.connection.execute("SELECT COUNT(*) FROM prepared_results").fetchone()[0], 1
            )
        self.assertEqual((projection["durable_stage"], projection["attempt_status"]), ("INPUT", "FAILED"))
        self.assertEqual(len(tuple((harness.output_root / "system-paper-slots").iterdir())), 1)

    def test_impossible_overfill_forms_no_prepared_result_or_artifact(self):
        harness = FaultScenarioHarness(point="BEFORE_CLAIM_COMMIT", mode="CRASH")
        try:
            with self.assertRaises(ContractError):
                harness.run(
                    worker_id="overfill-worker", clock_at=harness.now,
                    provider=harness.provider, scenario=FillScenario.impossible_overfill(),
                )
            stage, artifacts, inputs, results, terminal = harness.durable_facts()
            self.assertEqual((stage, artifacts, inputs, results, terminal), ("INPUT", 0, 1, 0, None))
            policy = SystemPaperSchedulePolicy.create(harness.plan)
            with SystemPaperScheduleState(harness.state_path, policy) as state:
                projection = state.slot_projection()[policy.current_slot(harness.now).slot_id]
            self.assertEqual(projection["attempt_status"], "FAILED")
        finally:
            harness.close()
