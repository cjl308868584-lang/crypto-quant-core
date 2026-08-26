import inspect
import subprocess
import unittest
from copy import deepcopy
from unittest.mock import patch

from crypto_quant.canonical import business_hash, canonical_json
from crypto_quant.challenger_replacement_fault_matrix import (
    ChallengerReplacementFaultMatrixError,
    EXPECTED_CASE_IDS,
    load_challenger_replacement_fault_matrix_bytes,
    run_challenger_replacement_fault_matrix,
)
import crypto_quant.challenger_replacement_fault_matrix as fault_module
import crypto_quant.challenger_replacement_binance_lifecycle as lifecycle_module
import crypto_quant.challenger_replacement_simulation as simulation_module
import crypto_quant.challenger_replacement_public_http as http_module
import crypto_quant.challenger_replacement_public_market_capture as capture_module
import crypto_quant.challenger_replacement_v3_observer as observer_module
import crypto_quant.operations_projection_v3 as projection_module


CORE = {
    "src/crypto_quant/challenger_replacement_events.py": "b" * 64,
    "src/crypto_quant/challenger_replacement_fault_matrix.py": "c" * 64,
}
BUILD = {
    "reviewed_code_checkpoint": "7" * 40,
    "package_version": "0.76.0",
    "predecessor_manifest_identity": {
        "repository": "cjl308868584-lang/crypto-quant-core",
        "visibility": "PUBLIC",
        "release_tag": "v0.75.0",
        "tag_object": "4bd4b2e21c760d6fad2a27903c67ee509ac116c9",
        "peeled_commit": "a51ed15d5a484e5bb9a54dc75a7fef4e8876e4d5",
        "package_version": "0.75.0",
        "manifest_version": "1.69.0",
        "manifest_hash": "b15479590536c302e173a41a758c9113cd7452b0000d8b6c5cb5c2ad8b9404d9",
        "manifest_file_sha256": "df1695827975cbeb9c094b8182839e132219a52a19dc4166677a742d48442220",
        "build_input_tree_hash": "07812c0a352dabab3742aa1c3417eaa8a8363e46a5059e49323f2b1c0d8a4a78",
        "main_ci_run": 32869868571,
    },
    "executable_core_hash": business_hash(CORE),
}


class ChallengerReplacementFaultMatrixTests(unittest.TestCase):
    def setUp(self):
        self.receipt = run_challenger_replacement_fault_matrix(
            build_identity=BUILD, runtime_core_identity=CORE,
        )

    def test_exact_order_all_cases_pass_and_receipt_is_deterministic(self):
        self.assertEqual(len(EXPECTED_CASE_IDS), 36)
        self.assertEqual(
            tuple(item["case_id"] for item in self.receipt["cases"]),
            EXPECTED_CASE_IDS,
        )
        self.assertTrue(all(item["passed"] is True for item in self.receipt["cases"]))
        for item in self.receipt["cases"]:
            self.assertEqual(
                set(item),
                {"case_id", "expected_boundary", "observed_boundary", "passed",
                 "fixture_sha256", "result_sha256"},
            )
            self.assertRegex(item["fixture_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(item["result_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.receipt["status"], "FAULT_MATRIX_PASSED")
        self.assertEqual(self.receipt["build_identity"], BUILD)
        self.assertEqual(self.receipt["runtime_core_identity"], CORE)
        self.assertRegex(self.receipt["runtime_core_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.receipt["executable_core_hash"], business_hash(CORE))
        self.assertEqual(
            self.receipt["authority"],
            {"network_requests": 0, "account_requests": 0,
             "broker_requests": 0, "orders": 0, "fund_movement": 0,
             "production_state_writes": 0},
        )
        self.assertEqual(
            run_challenger_replacement_fault_matrix(
                build_identity=BUILD, runtime_core_identity=CORE
            ),
            self.receipt,
        )

    def test_runtime_core_adds_exact_deployment_artifact_to_executable_core(self):
        expanded = dict(CORE)
        expanded[
            "artifacts/challenger-replacement/"
            "challenger-replacement-v3-deployment-v0.76.0.json"
        ] = "d" * 64
        receipt = run_challenger_replacement_fault_matrix(
            build_identity=BUILD, runtime_core_identity=expanded,
        )
        self.assertEqual(receipt["executable_core_hash"], business_hash(CORE))
        self.assertNotEqual(receipt["runtime_core_hash"], receipt["executable_core_hash"])

    def test_loader_rebuilds_exact_receipt_and_rejects_any_case_or_build_drift(self):
        body = canonical_json(self.receipt).encode("utf-8")
        self.assertEqual(
            load_challenger_replacement_fault_matrix_bytes(
                body, build_identity=BUILD, runtime_core_identity=CORE,
            ),
            self.receipt,
        )
        mutations = []
        missing = deepcopy(self.receipt)
        missing["cases"].pop()
        mutations.append(missing)
        extra = deepcopy(self.receipt)
        extra["cases"].append(deepcopy(extra["cases"][-1]))
        mutations.append(extra)
        reordered = deepcopy(self.receipt)
        reordered["cases"][0], reordered["cases"][1] = (
            reordered["cases"][1], reordered["cases"][0]
        )
        mutations.append(reordered)
        failed = deepcopy(self.receipt)
        failed["cases"][0]["passed"] = False
        mutations.append(failed)
        changed = deepcopy(self.receipt)
        changed["cases"][0]["expected_boundary"] = "CHANGED"
        mutations.append(changed)
        for mutation in mutations:
            with self.subTest(case=mutation["cases"][0]["case_id"]):
                with self.assertRaises(ChallengerReplacementFaultMatrixError):
                    load_challenger_replacement_fault_matrix_bytes(
                        canonical_json(mutation).encode("utf-8"),
                        build_identity=BUILD, runtime_core_identity=CORE,
                    )
        other_build = dict(BUILD, reviewed_code_checkpoint="5" * 40)
        with self.assertRaises(ChallengerReplacementFaultMatrixError):
            load_challenger_replacement_fault_matrix_bytes(
                body, build_identity=other_build, runtime_core_identity=CORE,
            )

    def test_runner_has_no_caller_supplied_case_results_or_fault_callback(self):
        parameters = inspect.signature(
            run_challenger_replacement_fault_matrix
        ).parameters
        self.assertEqual(
            tuple(parameters), ("build_identity", "runtime_core_identity")
        )
        source = inspect.getsource(run_challenger_replacement_fault_matrix)
        self.assertNotIn("fault_injector", source)
        self.assertNotIn("case_results", source)

    def test_loader_verifies_frozen_receipt_without_rerunning_faults(self):
        body = canonical_json(self.receipt).encode("utf-8")
        with patch(
            "crypto_quant.challenger_replacement_fault_matrix._probe_boundary",
            side_effect=AssertionError("strict replay must not execute probes"),
        ):
            loaded = load_challenger_replacement_fault_matrix_bytes(
                body, build_identity=BUILD, runtime_core_identity=CORE,
            )
        self.assertEqual(loaded, self.receipt)

    def test_process_termination_cases_reopen_each_distinct_durable_boundary(self):
        cases = EXPECTED_CASE_IDS[:6]
        expected_counts = (0, 1, 1, 2, 2, 3)
        original = fault_module.replay_challenger_replacement_events
        for case_id, expected in zip(cases, expected_counts):
            counts = []
            def recorded(root):
                value = original(root)
                counts.append(len(value.events))
                return value
            with self.subTest(case_id=case_id), patch.object(
                fault_module, "replay_challenger_replacement_events",
                side_effect=recorded,
            ):
                self.assertEqual(
                    fault_module._probe_boundary(case_id, BUILD),
                    "IDEMPOTENT_EVENT_REPLAY",
                )
            self.assertEqual(counts[0], expected)

    def test_process_termination_and_fresh_replay_use_a_new_interpreter(self):
        original = subprocess.Popen
        for case_id in (
            "PROCESS_TERMINATION_AFTER_INPUT_APPEND",
            "FRESH_PROCESS_REPLAY_IDEMPOTENT_RETRY",
        ):
            with self.subTest(case_id=case_id), patch.object(
                subprocess, "Popen", wraps=original,
            ) as invoked:
                fault_module._probe_boundary(case_id, BUILD)
            self.assertEqual(invoked.call_count, 1)

    def test_lifecycle_fault_cases_execute_the_existing_deterministic_kernel(self):
        cases = (
            "PARTIAL_SIMULATED_FILL", "LATE_SIMULATED_FILL",
            "SIMULATED_CANCEL_RACE", "UNRESOLVED_UNKNOWN_CLASSIFICATION",
            "PROTECTIVE_STOP_MODEL_FAILURE",
            "PROTECTIVE_STOP_REPLACE_MODEL_FAILURE",
            "ENGINE_VENUE_MODEL_LEDGER_DISAGREEMENT",
        )
        original = lifecycle_module.simulate_challenger_replacement_binance_lifecycle
        for case_id in cases:
            with self.subTest(case_id=case_id), patch.object(
                lifecycle_module,
                "simulate_challenger_replacement_binance_lifecycle",
                wraps=original,
            ) as invoked:
                fault_module._probe_boundary(case_id, BUILD)
            self.assertEqual(invoked.call_count, 1)

    def test_economic_and_risk_cases_execute_accounting_boundaries(self):
        with patch.object(
            lifecycle_module,
            "simulate_challenger_replacement_binance_lifecycle",
            wraps=lifecycle_module.simulate_challenger_replacement_binance_lifecycle,
        ) as lifecycle:
            fault_module._probe_boundary("FEE_REPLAY", BUILD)
        self.assertEqual(lifecycle.call_count, 1)
        for case_id, boundary_name in (
            ("FUNDING_REPLAY", "_prepare_boundary"),
            ("DAILY_LOSS_LOCK", "_risk"),
            ("DRAWDOWN_LOCK", "_risk"),
        ):
            original = getattr(simulation_module, boundary_name)
            with self.subTest(case_id=case_id), patch.object(
                simulation_module, boundary_name, wraps=original,
            ) as invoked:
                fault_module._probe_boundary(case_id, BUILD)
            self.assertGreaterEqual(invoked.call_count, 1)

    def test_public_input_clock_and_projection_cases_hit_real_boundaries(self):
        groups = (
            (EXPECTED_CASE_IDS[7:10], http_module, "open_fixed_public_request"),
            (EXPECTED_CASE_IDS[10:14], capture_module, "_selected_payload"),
            (EXPECTED_CASE_IDS[16:20], capture_module, "_strict_document"),
            (("PROJECTION_SOURCE_UNAVAILABLE",), observer_module,
             "observe_challenger_replacement_v3"),
            (("PROJECTION_SOURCE_INVALID",), projection_module,
             "load_operations_projection_v3_bytes"),
        )
        for cases, module, name in groups:
            original = getattr(module, name)
            for case_id in cases:
                with self.subTest(case_id=case_id), patch.object(
                    module, name, wraps=original,
                ) as invoked:
                    fault_module._probe_boundary(case_id, BUILD)
                self.assertGreaterEqual(invoked.call_count, 1)
        after_receipt = next(
            item for item in self.receipt["cases"]
            if item["case_id"] == "NETWORK_LOSS_AFTER_RESPONSE_RECEIPT"
        )
        self.assertEqual(
            after_receipt["observed_boundary"], "RESPONSE_RECEIPT_REPLAYED"
        )

    def test_network_faults_cross_transport_and_durable_receipt_boundaries(self):
        calls = []
        original_open = fault_module._ProbeOpener.open
        def tracked_open(instance, *args, **kwargs):
            calls.append(args)
            return original_open(instance, *args, **kwargs)
        with patch.object(fault_module._ProbeOpener, "open", new=tracked_open):
            fault_module._probe_boundary("NETWORK_LOSS_BEFORE_REQUEST", BUILD)
        self.assertEqual(len(calls), 0)
        with patch.object(fault_module._ProbeOpener, "open", new=tracked_open):
            fault_module._probe_boundary(
                "NETWORK_LOSS_AFTER_REQUEST_BEFORE_RESPONSE", BUILD
            )
        self.assertEqual(len(calls), 1)

        with patch.object(
            fault_module, "publish_challenger_replacement_event",
            wraps=fault_module.publish_challenger_replacement_event,
        ) as published, patch.object(
            fault_module, "replay_challenger_replacement_events",
            wraps=fault_module.replay_challenger_replacement_events,
        ) as replayed:
            fault_module._probe_boundary("NETWORK_LOSS_AFTER_RESPONSE_RECEIPT", BUILD)
        self.assertGreaterEqual(published.call_count, 1)
        self.assertGreaterEqual(replayed.call_count, 1)


if __name__ == "__main__":
    unittest.main()
