import inspect
import unittest
from copy import deepcopy
from unittest.mock import patch

from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_fault_matrix import (
    ChallengerReplacementFaultMatrixError,
    EXPECTED_CASE_IDS,
    load_challenger_replacement_fault_matrix_bytes,
    run_challenger_replacement_fault_matrix,
)
import crypto_quant.challenger_replacement_fault_matrix as fault_module


BUILD = {
    "release_tag": "v0.76.0",
    "peeled_commit": "7" * 40,
    "package_version": "0.76.0",
    "manifest_version": "1.70.0",
    "manifest_hash": "8" * 64,
    "manifest_file_sha256": "9" * 64,
    "build_input_tree_hash": "a" * 64,
}


class ChallengerReplacementFaultMatrixTests(unittest.TestCase):
    def setUp(self):
        self.receipt = run_challenger_replacement_fault_matrix(
            build_identity=BUILD
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
        self.assertEqual(
            self.receipt["authority"],
            {"network_requests": 0, "account_requests": 0,
             "broker_requests": 0, "orders": 0, "fund_movement": 0,
             "production_state_writes": 0},
        )
        self.assertEqual(
            run_challenger_replacement_fault_matrix(build_identity=BUILD),
            self.receipt,
        )

    def test_loader_rebuilds_exact_receipt_and_rejects_any_case_or_build_drift(self):
        body = canonical_json(self.receipt).encode("utf-8")
        self.assertEqual(
            load_challenger_replacement_fault_matrix_bytes(
                body, build_identity=BUILD
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
                        build_identity=BUILD,
                    )
        other_build = dict(BUILD, peeled_commit="6" * 40)
        with self.assertRaises(ChallengerReplacementFaultMatrixError):
            load_challenger_replacement_fault_matrix_bytes(
                body, build_identity=other_build
            )

    def test_runner_has_no_caller_supplied_case_results_or_fault_callback(self):
        parameters = inspect.signature(
            run_challenger_replacement_fault_matrix
        ).parameters
        self.assertEqual(tuple(parameters), ("build_identity",))
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
                body, build_identity=BUILD
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


if __name__ == "__main__":
    unittest.main()
