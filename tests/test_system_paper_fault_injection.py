"""Full real-SQLite fault and recovery matrix for System Paper scheduling."""

import hashlib
import inspect
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import crypto_quant.system_paper_scheduler as scheduler_module
import crypto_quant.system_paper_runtime as runtime_module
from crypto_quant.system_paper_broker import FillScenario, SimulatedBroker
from crypto_quant.system_paper_plan import build_system_paper_plan
from crypto_quant.errors import ContractError
from crypto_quant.system_paper_scheduler import (
    SYSTEM_PAPER_FROZEN_FAULT_POINTS,
    SystemPaperFaultInjector,
    SystemPaperInjectedFault,
    SystemPaperInputCapture,
    SystemPaperInputRequest,
    SystemPaperScheduleError,
    SystemPaperSchedulePolicy,
    SystemPaperScheduleState,
    run_due_system_paper_slot,
)
from crypto_quant.system_paper_runtime import (
    SystemPaperRuntimeError,
    load_system_paper_slot_result_bytes,
)
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

LITERAL_FROZEN_FAULT_POINT_SET = frozenset((
    "AFTER_CLAIM_COMMIT",
    "BEFORE_CLAIM_COMMIT",
    "BEFORE_INPUT_PROVIDER",
    "AFTER_INPUT_PROVIDER_BEFORE_COMMIT",
    "BEFORE_INPUT_PREPARED_COMMIT",
    "AFTER_INPUT_PREPARED_COMMIT",
    "AFTER_RUNTIME_BEFORE_RESULT_COMMIT",
    "BEFORE_RESULT_PREPARED_COMMIT",
    "AFTER_RESULT_PREPARED_COMMIT",
    "DURING_ARTIFACT_WRITE",
    "AFTER_ARTIFACT_FSYNC_BEFORE_COMMIT",
    "AFTER_ARTIFACT_PUBLISH_BEFORE_SUCCESS",
    "BEFORE_SUCCESS_COMMIT",
))

# (provider calls, network captures, candidate runtime calls, production loader calls)
FROZEN_INVOCATION_BUDGETS = {
    "BEFORE_CLAIM_COMMIT": ((0, 0, 0, 0), (1, 4, 1, 8)),
    "AFTER_CLAIM_COMMIT": ((0, 0, 0, 0), (1, 4, 1, 8)),
    "BEFORE_INPUT_PROVIDER": ((0, 0, 0, 0), (1, 4, 1, 8)),
    "AFTER_INPUT_PROVIDER_BEFORE_COMMIT": ((1, 4, 0, 0), (1, 4, 1, 8)),
    "BEFORE_INPUT_PREPARED_COMMIT": ((1, 4, 0, 0), (1, 4, 1, 8)),
    "AFTER_INPUT_PREPARED_COMMIT": ((1, 4, 0, 0), (0, 0, 1, 8)),
    "AFTER_RUNTIME_BEFORE_RESULT_COMMIT": ((1, 4, 1, 0), (0, 0, 1, 8)),
    "BEFORE_RESULT_PREPARED_COMMIT": ((1, 4, 1, 1), (0, 0, 1, 8)),
    "AFTER_RESULT_PREPARED_COMMIT": ((1, 4, 1, 1), (0, 0, 0, 13)),
    "DURING_ARTIFACT_WRITE": ((1, 4, 1, 5), (0, 0, 0, 13)),
    "AFTER_ARTIFACT_FSYNC_BEFORE_COMMIT": ((1, 4, 1, 5), (0, 0, 0, 13)),
    "AFTER_ARTIFACT_PUBLISH_BEFORE_SUCCESS": ((1, 4, 1, 5), (0, 0, 0, 13)),
    "BEFORE_SUCCESS_COMMIT": ((1, 4, 1, 8), (0, 0, 0, 13)),
}


class DeterministicPublicProvider:
    """The provider is real deterministic test input, not a business mock."""

    def __init__(self, captured_at, *, network_request_count=4):
        self.invocations = 0
        self.network_requests = 0
        self.credential_reads = 0
        self.account_requests = 0
        self.captured_at = captured_at
        self.network_request_count = network_request_count

    @property
    def credentials(self):
        self.credential_reads += 1
        raise AssertionError("System Paper provider must not read credentials")

    @property
    def account(self):
        self.account_requests += 1
        raise AssertionError("System Paper provider must not request an account")

    def __call__(self, request):
        self.invocations += 1
        capture = SystemPaperInputCapture(
            public_market_bundle=make_bundle(observed_at=request.scheduled_for),
            capture_attempt_id="fault-capture-" + request.slot_id[-12:],
            captured_at=self.captured_at,
            request_families=request.request_families,
            network_request_count=self.network_request_count,
        )
        self.network_requests += capture.network_request_count
        return capture


class InvocationEvidence:
    """Count passthrough calls at real scheduler/runtime boundaries."""

    def __init__(self):
        self.candidate_runtime_calls = 0
        self.production_loader_calls = 0
        self.constructed_brokers = []
        self._real_candidate_runtime = scheduler_module.run_system_paper_slot
        self._real_loader = scheduler_module.load_system_paper_slot_result_bytes
        self._real_simulated_broker = runtime_module.SimulatedBroker

    def candidate_runtime(self, *args, **kwargs):
        self.candidate_runtime_calls += 1
        return self._real_candidate_runtime(*args, **kwargs)

    def loader(self, *args, **kwargs):
        self.production_loader_calls += 1
        return self._real_loader(*args, **kwargs)

    def simulated_broker_factory(self, *args, **kwargs):
        broker = self._real_simulated_broker(*args, **kwargs)
        if type(broker) is not self._real_simulated_broker:
            raise AssertionError("runtime must construct the exact production SimulatedBroker")
        self.constructed_brokers.append(broker)
        return broker

    @contextmanager
    def patched(self):
        with patch.object(
            scheduler_module, "run_system_paper_slot", self.candidate_runtime
        ), patch.object(
            scheduler_module, "load_system_paper_slot_result_bytes", self.loader
        ), patch.object(
            runtime_module, "SimulatedBroker", self.simulated_broker_factory
        ):
            yield self

    @staticmethod
    def counts(provider, evidence):
        return (
            provider.invocations,
            provider.network_requests,
            evidence.candidate_runtime_calls,
            evidence.production_loader_calls,
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

    def run_first_invocation(self, *, evidence=None):
        return self.run(
            worker_id="fault-worker-a",
            clock_at=self.now,
            provider=self.provider,
            injector=SystemPaperFaultInjector({self.point: self.mode}),
            evidence=evidence,
        )

    def run(
        self, *, worker_id, clock_at, provider, injector=None, scenario=None,
        evidence=None,
    ):
        kwargs = {
            "state_path": self.state_path,
            "output_root": self.output_root,
            "plan": self.plan,
            "worker_id": worker_id,
            "public_input_provider": provider,
            "fill_scenario": scenario or FillScenario.immediate_full(),
            "clock": lambda: clock_at,
            "fault_injector": injector,
        }
        if evidence is None:
            return run_due_system_paper_slot(**kwargs)
        with evidence.patched():
            return run_due_system_paper_slot(**kwargs)

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
        policy = SystemPaperSchedulePolicy.create(self.plan)
        slot = policy.current_slot(self.now)
        with SystemPaperScheduleState(self.state_path, policy) as state:
            prepared = state.connection.execute(
                "SELECT result_bytes, result_sha256 FROM prepared_results WHERE slot_id=?",
                (slot.slot_id,),
            ).fetchone()
            parents = state.successful_parent_result_bodies(
                slot, output_root=self.output_root
            )
        if prepared is None:
            raise AssertionError("completed slot is missing its immutable prepared result")
        if body != prepared["result_bytes"]:
            raise AssertionError("published bytes differ from immutable prepared result bytes")
        if hashlib.sha256(body).hexdigest() != prepared["result_sha256"]:
            raise AssertionError("published SHA-256 differs from immutable prepared result")
        loaded = load_system_paper_slot_result_bytes(body, parent_result_bodies=parents)
        if loaded["slot_id"] != summary["slot_id"]:
            raise AssertionError("full bytes-loader replay differs from runner summary")
        if loaded["ledger"]["debits_usdt"] != loaded["ledger"]["credits_usdt"]:
            raise AssertionError("full bytes-loader replay produced an unbalanced ledger")
        if self.durable_facts() != ("RESULT", 1, 1, 1, "SUCCEEDED"):
            raise AssertionError(f"final durable facts: {self.durable_facts()!r}")


class SystemPaperFaultWiringTests(unittest.TestCase):
    def test_public_failpoint_contract_equals_the_literal_frozen_set(self):
        self.assertIsInstance(SYSTEM_PAPER_FROZEN_FAULT_POINTS, frozenset)
        self.assertEqual(SYSTEM_PAPER_FROZEN_FAULT_POINTS, LITERAL_FROZEN_FAULT_POINT_SET)

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


class SystemPaperSafetyBoundaryTests(unittest.TestCase):
    def test_public_runner_and_provider_surfaces_are_credential_account_and_live_broker_free(self):
        self.assertEqual(tuple(inspect.signature(run_due_system_paper_slot).parameters), (
            "state_path", "output_root", "plan", "worker_id", "public_input_provider",
            "fill_scenario", "clock", "fault_injector",
        ))
        self.assertEqual(tuple(SystemPaperInputRequest.__dataclass_fields__), (
            "plan_hash", "slot_id", "scheduled_for", "capture_deadline",
            "request_families",
        ))
        self.assertEqual(tuple(SystemPaperInputCapture.__dataclass_fields__), (
            "public_market_bundle", "capture_attempt_id", "captured_at",
            "request_families", "network_request_count",
        ))
        self.assertIs(runtime_module.SimulatedBroker, SimulatedBroker)


class InvocationEvidenceRegressionTests(unittest.TestCase):
    def test_network_evidence_uses_the_provider_returned_count_not_an_invocation_multiple(self):
        harness = FaultScenarioHarness(point="BEFORE_CLAIM_COMMIT", mode="CRASH")
        evidence = InvocationEvidence()
        try:
            provider = DeterministicPublicProvider(harness.now, network_request_count=3)
            with self.assertRaises(SystemPaperScheduleError):
                harness.run(
                    worker_id="network-probe", clock_at=harness.now,
                    provider=provider, evidence=evidence,
                )
            self.assertEqual(InvocationEvidence.counts(provider, evidence), (1, 3, 0, 0))
            self.assertNotEqual(InvocationEvidence.counts(provider, evidence), (1, 4, 0, 0))
        finally:
            harness.close()

    def test_broker_evidence_records_exact_real_production_objects(self):
        harness = FaultScenarioHarness(point="BEFORE_CLAIM_COMMIT", mode="CRASH")
        evidence = InvocationEvidence()
        try:
            harness.run(
                worker_id="broker-probe", clock_at=harness.now,
                provider=harness.provider, evidence=evidence,
            )
            self.assertGreater(len(evidence.constructed_brokers), 0)
            self.assertTrue(
                all(type(broker) is SimulatedBroker for broker in evidence.constructed_brokers)
            )
            self.assertEqual(
                len(evidence.constructed_brokers),
                evidence.candidate_runtime_calls + evidence.production_loader_calls,
            )
        finally:
            harness.close()


class SystemPaperFaultRecoveryTests(unittest.TestCase):
    def test_crash_matrix_recovers_once_from_every_durable_stage(self):
        for point, durable_stage, artifact_count in FROZEN_FAILPOINTS:
            with self.subTest(point=point):
                harness = FaultScenarioHarness(point=point, mode="CRASH")
                try:
                    first_evidence = InvocationEvidence()
                    with self.assertRaises(SystemPaperInjectedFault):
                        harness.run_first_invocation(evidence=first_evidence)
                    harness.assert_durable_stage_matches_contract(
                        durable_stage, artifact_count
                    )
                    self.assertEqual(
                        InvocationEvidence.counts(harness.provider, first_evidence),
                        FROZEN_INVOCATION_BUDGETS[point][0],
                    )
                    self.assertEqual(
                        len(first_evidence.constructed_brokers),
                        first_evidence.candidate_runtime_calls
                        + first_evidence.production_loader_calls,
                    )
                    self.assertTrue(
                        all(
                            type(broker) is SimulatedBroker
                            for broker in first_evidence.constructed_brokers
                        )
                    )
                    self.assertEqual(
                        (harness.provider.credential_reads, harness.provider.account_requests),
                        (0, 0),
                    )
                    published_before = None
                    if artifact_count:
                        artifact = next((harness.output_root / "system-paper-slots").iterdir())
                        published_before = (artifact.read_bytes(), artifact.stat().st_ino)
                    recovery_provider = DeterministicPublicProvider(
                        "2026-08-02T12:20:12.000Z"
                    )
                    recovery_evidence = InvocationEvidence()
                    recovered = harness.run(
                        worker_id="fault-worker-b",
                        clock_at="2026-08-02T12:20:12.000Z",
                        provider=recovery_provider,
                        evidence=recovery_evidence,
                    )
                    expected_outcome = (
                        "RESUMED_INPUT" if durable_stage == "INPUT" else
                        "RESUMED_RESULT" if durable_stage == "RESULT" else "EXECUTED"
                    )
                    harness.assert_finished(recovered, expected_outcome=expected_outcome)
                    recovery_budget = FROZEN_INVOCATION_BUDGETS[point][1]
                    self.assertEqual(
                        InvocationEvidence.counts(recovery_provider, recovery_evidence),
                        recovery_budget,
                    )
                    self.assertEqual(
                        tuple(recovered[key] for key in (
                            "provider_invocation_count", "network_request_count",
                            "candidate_runtime_invocation_count",
                        )), recovery_budget[:3],
                    )
                    self.assertEqual(recovered["loader_replay_count"], 1)
                    self.assertEqual(
                        len(recovery_evidence.constructed_brokers),
                        recovery_evidence.candidate_runtime_calls
                        + recovery_evidence.production_loader_calls,
                    )
                    self.assertTrue(
                        all(
                            type(broker) is SimulatedBroker
                            for broker in recovery_evidence.constructed_brokers
                        )
                    )
                    self.assertEqual(
                        (recovery_provider.credential_reads, recovery_provider.account_requests),
                        (0, 0),
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

    def test_artifact_enospc_recovers_exact_result_without_false_terminal_event(self):
        for point in (
            "DURING_ARTIFACT_WRITE",
            "AFTER_ARTIFACT_FSYNC_BEFORE_COMMIT",
        ):
            with self.subTest(point=point):
                harness = FaultScenarioHarness(point=point, mode="ENOSPC")
                try:
                    with self.assertRaises(OSError) as raised:
                        harness.run_first_invocation()
                    self.assertEqual(raised.exception.errno, 28)
                    self.assertEqual(
                        harness.durable_facts(), ("RESULT", 0, 1, 1, None)
                    )
                    slots = harness.output_root / "system-paper-slots"
                    self.assertEqual(tuple(slots.iterdir()), ())
                    policy = SystemPaperSchedulePolicy.create(harness.plan)
                    slot = policy.current_slot(harness.now)
                    with SystemPaperScheduleState(harness.state_path, policy) as state:
                        event_types = [event["event_type"] for event in state.events()]
                        input_before = state.connection.execute(
                            "SELECT input_bytes, input_sha256 FROM prepared_inputs "
                            "WHERE slot_id=?", (slot.slot_id,)
                        ).fetchone()
                        result_before = state.connection.execute(
                            "SELECT result_bytes, result_sha256 FROM prepared_results "
                            "WHERE slot_id=?", (slot.slot_id,)
                        ).fetchone()
                    self.assertNotIn("FAILED", event_types)
                    self.assertNotIn("SUCCEEDED", event_types)
                    self.assertEqual(
                        hashlib.sha256(input_before["input_bytes"]).hexdigest(),
                        input_before["input_sha256"],
                    )
                    self.assertEqual(
                        hashlib.sha256(result_before["result_bytes"]).hexdigest(),
                        result_before["result_sha256"],
                    )

                    recovery_provider = DeterministicPublicProvider(
                        "2026-08-02T12:20:12.000Z"
                    )
                    recovery_evidence = InvocationEvidence()
                    recovered = harness.run(
                        worker_id="enospc-recovery-worker",
                        clock_at="2026-08-02T12:20:12.000Z",
                        provider=recovery_provider,
                        evidence=recovery_evidence,
                    )
                    self.assertEqual(recovered["outcome"], "RESUMED_RESULT")
                    self.assertEqual(
                        (
                            recovery_provider.invocations,
                            recovery_provider.network_requests,
                            recovery_evidence.candidate_runtime_calls,
                            recovered["loader_replay_count"],
                        ),
                        (0, 0, 0, 1),
                    )
                    artifact = Path(recovered["result_path_or_null"])
                    self.assertEqual(
                        tuple(path.resolve() for path in slots.iterdir()),
                        (artifact.resolve(),),
                    )
                    self.assertEqual(artifact.read_bytes(), result_before["result_bytes"])
                    self.assertEqual(
                        hashlib.sha256(artifact.read_bytes()).hexdigest(),
                        result_before["result_sha256"],
                    )
                    result = load_system_paper_slot_result_bytes(artifact.read_bytes())
                    self.assertEqual(
                        result["ledger"]["debits_usdt"],
                        result["ledger"]["credits_usdt"],
                    )
                    with SystemPaperScheduleState(harness.state_path, policy) as state:
                        self.assertEqual(
                            state.connection.execute(
                                "SELECT COUNT(*) FROM prepared_results"
                            ).fetchone()[0],
                            1,
                        )
                        self.assertEqual(
                            [event["event_type"] for event in state.events()].count(
                                "SUCCEEDED"
                            ),
                            1,
                        )
                        self.assertNotIn(
                            "FAILED", [event["event_type"] for event in state.events()]
                        )
                    self.assertFalse(
                        any(path.name.startswith(".market-data-") for path in slots.iterdir())
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
            return self._capture(now, request, captured_at="2026-08-02T12:04:59.999Z")

        def changed_hash(request):
            bundle = make_bundle(observed_at=request.scheduled_for)
            bundle["bbo"] = {"bid_price": "98.99", "ask_price": "100.01"}
            return self._capture(now, request, public_market_bundle=bundle)

        def binary_float(request):
            bundle = make_bundle(observed_at=request.scheduled_for)
            bundle["bbo"] = {"bid_price": 99.99, "ask_price": "100.01"}
            return self._capture(now, request, public_market_bundle=bundle)

        def private_account(request):
            return self._capture(now, request, request_families=(
                "SPOT_AGG_TRADE", "SPOT_BBO", "SPOT_EXCHANGE_INFO", "SPOT_ACCOUNT",
            ))

        cases = (
            ("malformed", malformed, "SYSTEM_PAPER_SCHEDULE_INPUT_CAPTURE_INVALID"),
            ("duplicate", duplicate, "SYSTEM_PAPER_SCHEDULE_INPUT_REQUEST_INVALID"),
            ("reordered", reordered, "SYSTEM_PAPER_SCHEDULE_INPUT_REQUEST_INVALID"),
            ("count", wrong_count, "SYSTEM_PAPER_SCHEDULE_INPUT_REQUEST_INVALID"),
            ("stale", stale, "SYSTEM_PAPER_SCHEDULE_INPUT_CAPTURE_WINDOW_INVALID"),
            ("changed_hash", changed_hash, "SYSTEM_PAPER_SCHEDULE_INPUT_BUNDLE_INVALID"),
            ("float", binary_float, "SYSTEM_PAPER_SCHEDULE_INPUT_BUNDLE_INVALID"),
            ("private_account", private_account, "SYSTEM_PAPER_SCHEDULE_INPUT_REQUEST_INVALID"),
        )
        for name, provider, reason_code in cases:
            with self.subTest(case=name):
                harness = self._harness()
                try:
                    with self.assertRaises(SystemPaperScheduleError) as raised:
                        harness.run(
                            worker_id="provider-worker", clock_at=now, provider=provider
                        )
                    self.assertEqual(raised.exception.reason_code, reason_code)
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
    def assert_exact_broker_evidence(self, evidence):
        self.assertEqual(
            len(evidence.constructed_brokers),
            evidence.candidate_runtime_calls + evidence.production_loader_calls,
        )
        self.assertTrue(
            all(type(broker) is SimulatedBroker for broker in evidence.constructed_brokers)
        )

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
                    evidence = InvocationEvidence()
                    summary = harness.run(
                        worker_id="order-worker", clock_at=harness.now,
                        provider=harness.provider, scenario=scenario, evidence=evidence,
                    )
                    self.assert_exact_broker_evidence(evidence)
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
        evidence = InvocationEvidence()
        try:
            with self.assertRaises(ContractError):
                harness.run(
                    worker_id="overfill-worker", clock_at=harness.now,
                    provider=harness.provider, scenario=FillScenario.impossible_overfill(),
                    evidence=evidence,
                )
            self.assert_exact_broker_evidence(evidence)
            stage, artifacts, inputs, results, terminal = harness.durable_facts()
            self.assertEqual((stage, artifacts, inputs, results, terminal), ("INPUT", 0, 1, 0, None))
            policy = SystemPaperSchedulePolicy.create(harness.plan)
            with SystemPaperScheduleState(harness.state_path, policy) as state:
                projection = state.slot_projection()[policy.current_slot(harness.now).slot_id]
            self.assertEqual(projection["attempt_status"], "FAILED")
        finally:
            harness.close()
